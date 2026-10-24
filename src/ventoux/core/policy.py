"""Input policies: which sources an activity's input accepts (brief, D21).

A policy is written on the input field it guards, in the activity's input model. See
docs/guides/activities.md.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

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


class UnknownPolicy(ValueError):
    """A policy whose kind the engine doesn't know: it can't be compared, so nothing is said."""


# What a list of policies accepts, among sets of sources: one of three shapes, from the widest.
ANY = "any"  # no policy: every set of sources
TRUSTED = "trusted"  # trusted_only: sets whose every source is trusted, none included
SYSTEMS = "systems"  # only_from: non-empty sets of the systems every only_from on it names


def accepted(policies: Sequence[Policy]) -> tuple[str, frozenset[str]]:
    """What an input with `policies` accepts: its shape, and for only_from the systems a value may
    come from. Every policy applies (brief, D21), so only_from's systems are those all of them
    name, and trusted_only adds nothing to an only_from: a system is trusted."""
    systems: frozenset[str] | None = None
    for policy in policies:
        # Fail closed: a kind not in the closed list can't be compared, never read as "the same".
        if type(policy) not in KINDS:
            raise UnknownPolicy(
                f"an input policy of a kind Ventoux doesn't know ({type(policy).__name__}): "
                f"the kinds are {KIND_NAMES}"
            )
        if isinstance(policy, OnlyFrom):
            named = frozenset(policy.systems)
            systems = named if systems is None else systems & named
    if systems is not None:
        return (SYSTEMS, systems)
    if any(isinstance(policy, TrustedOnly) for policy in policies):
        return (TRUSTED, frozenset())
    return (ANY, frozenset())


def within(inner: tuple[str, frozenset[str]], outer: tuple[str, frozenset[str]]) -> bool:
    """Whether every set of sources `inner` accepts, `outer` accepts too."""
    shape, systems = inner
    outer_shape, outer_systems = outer
    if outer_shape == ANY:
        return True
    if shape == ANY:
        return False  # an untrusted source is accepted by `inner` only
    if outer_shape == TRUSTED:
        return True  # a trusted set, or one of systems, which are trusted
    if shape == TRUSTED:
        return False  # a person's answer is trusted, and from no system
    return systems <= outer_systems


def compared(
    old: Sequence[Policy], new: Sequence[Policy]
) -> Literal["same", "wider", "narrower", "neither"]:
    """How what an input accepts changed from `old` policies to `new`: the same sets of sources,
    strictly more (wider), strictly fewer (narrower), or neither, each a proof for every value.
    A kind the engine doesn't know is refused (`UnknownPolicy`)."""
    before, after = accepted(old), accepted(new)
    grows, shrinks = within(before, after), within(after, before)
    if grows and shrinks:
        return "same"
    if grows:
        return "wider"
    return "narrower" if shrinks else "neither"


def origins(
    expression: Expression,
    sources: Mapping[str, frozenset[str]],
    policy: Policy,
    named: Callable[[str], str] = str,
) -> str:
    """Where the refused value comes from: each field read whose own sources the policy refuses,
    each source said as `named` says it."""
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
        else f"{field} ({', '.join(sorted(named(source) for source in sources[field]))})"
        for field in refused
    )


def refusal(
    reference: str,
    field: str,
    policy: Policy,
    expression: Expression,
    sources: Mapping[str, frozenset[str]],
    named: Callable[[str], str] = str,
) -> str:
    """The input policy's refusal as one sentence, the same in `validate`, in case validation and
    before an activity runs: `letters.draft@2 takes to_customer only from …, and this value comes
    from …`. `named` says a source as a message shows it: case validation's stand-ins."""
    return (
        f"{reference} takes {field} {policy.describe()}, and this value comes from "
        f"{origins(expression, sources, policy, named)}"
    )
