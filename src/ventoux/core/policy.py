"""Input policies: which sources an activity's input accepts (brief, D21).

A policy is written on the input field it guards, in the activity's input model. See
docs/guides/activities.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import GetJsonSchemaHandler
from pydantic_core import CoreSchema

from ventoux.core.expressions import Expression
from ventoux.core.provenance import CASE, fields_read, is_trusted, is_untrusted


@dataclass(frozen=True)
class Policy:
    """What every kind of input policy can do. The kinds are a closed list (`KINDS`, below)."""

    def refuses(self, sources: frozenset[str]) -> str | None:
        """Why a value with these sources can't go in, or None if it can."""
        raise NotImplementedError

    def describe(self) -> str:
        """The policy as people read it, after the input's name."""
        raise NotImplementedError

    def promise(self) -> dict[str, Any]:
        """The policy as data, in the input's JSON Schema: `{"kind": "trusted_only"}`."""
        raise NotImplementedError

    # Pydantic: on an object inside `Annotated[...]`, `__get_pydantic_json_schema__` is called when
    # the model's JSON Schema is made, and may add to the field's schema.
    def __get_pydantic_json_schema__(
        self, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        # The policy goes into the published schema, which the contract hash covers: adding or
        # changing a policy changes the contract (brief, D21).
        schema: dict[str, Any] = handler(core_schema)
        schema.setdefault("x-input-policies", []).append(self.promise())
        return schema


@dataclass(frozen=True)
class TrustedOnly(Policy):
    """Only from a system or a person, never from untrusted data."""

    def refuses(self, sources: frozenset[str]) -> str | None:
        """Why a value with these sources can't go in, or None if it can."""
        # Fail closed: a source that is neither trusted nor declared untrusted is unknown, and an
        # unknown source is refused, never taken as trusted.
        refused = [
            source if is_untrusted(source) else f"{source}, a source Ventoux doesn't recognise"
            for source in sorted(sources)
            if not is_trusted(source)
        ]
        return f"it comes from {'; '.join(refused)}" if refused else None

    def describe(self) -> str:
        """The policy as people read it, after the input's name."""
        return "only from a system or a person, never from untrusted data"

    def promise(self) -> dict[str, Any]:
        return {"kind": "trusted_only"}


def trusted_only() -> TrustedOnly:
    return TrustedOnly()


@dataclass(frozen=True)
class OnlyFrom(Policy):
    """Only from the systems named."""

    systems: tuple[str, ...]  # the system names a value must come from, such as "payments"

    # Dataclass: `__post_init__` runs once the fields are set, every time an object is built.
    def __post_init__(self) -> None:
        if not self.systems:
            raise ValueError(
                "only_from names at least one system: with none, no value could ever pass."
            )

    def refuses(self, sources: frozenset[str]) -> str | None:
        """Why a value with these sources can't go in, or None if it can."""
        # A value with no source comes from no system, so from none of those named.
        if not sources:
            return "it comes from no system"
        # Every source must be one of the named systems: one other source is enough to refuse.
        allowed = {f"system:{system}" for system in self.systems}
        refused = sorted(sources - allowed)
        return f"it comes from {', '.join(refused)}" if refused else None

    def describe(self) -> str:
        """The policy as people read it, after the input's name."""
        return f"only from {' or '.join(self.systems)}"

    def promise(self) -> dict[str, Any]:
        return {"kind": "only_from", "systems": list(self.systems)}


def only_from(*systems: str) -> OnlyFrom:
    return OnlyFrom(systems)


# The kinds of policy, a closed list fixed by the engine. Adding one is a design decision recorded
# in the brief, like an expression operator (brief, D21).
KINDS: tuple[type[Policy], ...] = (TrustedOnly, OnlyFrom)
KIND_NAMES = "trusted_only and only_from"


def origins(expression: Expression, sources: Mapping[str, frozenset[str]], policy: Policy) -> str:
    """Where the refused value comes from: each field read whose own sources the policy refuses."""
    refused = [
        field
        for field in dict.fromkeys(fields_read(expression))  # each field once, in order
        if policy.refuses(sources[field]) is not None
    ]
    if not refused:
        return "a value written in the plan"
    return ", ".join(
        f"{field}, which the case gives the plan"
        if sources[field] == {CASE}
        else f"{field} ({', '.join(sorted(sources[field]))})"
        for field in refused
    )


def refusal(
    reference: str,
    field: str,
    policy: Policy,
    expression: Expression,
    sources: Mapping[str, frozenset[str]],
) -> str:
    """The input policy's refusal as one sentence, the same in `validate` and before an activity
    runs: `letters.draft@2 takes to_customer only from …, and this value comes from …`."""
    return (
        f"{reference} takes {field} {policy.describe()}, and this value comes from "
        f"{origins(expression, sources, policy)}"
    )
