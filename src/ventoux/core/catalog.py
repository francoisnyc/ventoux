"""The catalog: the activities a definition can call, each with its contract.

A definition only names an activity (`payments.refund@1`); its contract, written by the platform
team, says what that name promises. See docs/guides/activities.md.
"""

import hashlib
import json
import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

# A contract never changes once written (D5), down to its parts; and fail closed: a field it
# doesn't know is refused, never silently dropped.
FROZEN = ConfigDict(frozen=True, extra="forbid")

# `payments.refund@1`: a dotted lowercase name, then a whole-number version from 1.
REFERENCE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*@[1-9][0-9]*")


class Timeouts(BaseModel):
    """In seconds. `schedule_to_start` makes an activity no worker picks up fail loudly."""

    model_config = FROZEN

    start_to_close: int
    schedule_to_start: int


class RetryPolicy(BaseModel):
    """How Temporal retries the activity; intervals in seconds."""

    model_config = FROZEN

    maximum_attempts: int
    initial_interval: int
    backoff_coefficient: float


class Display(BaseModel):
    """What people read: presentation, so outside the contract's hash."""

    model_config = FROZEN

    title: str
    description: str
    outcomes: dict[str, str] = {}


class ActivityContract(BaseModel):
    """What one activity promises (D17). Where it runs is a deployment binding, not this."""

    model_config = FROZEN

    name: str
    version: int
    input: type[BaseModel]
    output: type[BaseModel]
    risk: Literal["low", "medium", "high"]
    effect: Literal["read", "compute", "write", "notify"]
    timeouts: Timeouts
    retry: RetryPolicy
    idempotency_key: str | None
    outcomes: tuple[str, ...]
    display: Display

    @model_validator(mode="before")
    @classmethod
    def no_unknown_fields(cls, data: Any) -> Any:
        # Fail closed: a field the contract doesn't know is refused, never silently dropped.
        unknown = sorted(set(data) - set(cls.model_fields)) if isinstance(data, dict) else []
        if unknown:
            raise ValueError(
                f"a contract has no field {', '.join(map(repr, unknown))}. A contract says what "
                "an activity promises; where it runs (task queue, namespace, worker) belongs in a "
                "deployment binding."
            )
        return data

    @model_validator(mode="after")
    def can_be_named(self) -> Self:
        # The same pattern `Catalog.get` reads, so whatever is registered can be looked up.
        if not REFERENCE.fullmatch(self.reference):
            raise ValueError(
                f"{self.reference!r}: no reference could name it. A name is dotted lowercase "
                "(payments.refund), and a version a whole number from 1."
            )
        return self

    @model_validator(mode="after")
    def side_effects_are_idempotent(self) -> Self:
        # D17: anything that changes the world sends a key, so a retry can't do it twice.
        if self.effect in ("write", "notify") and self.idempotency_key is None:
            raise ValueError(
                f"{self.reference} has effect {self.effect!r}: a side-effecting activity must say "
                "which input carries its idempotency key, or a retry could do it twice."
            )
        if self.idempotency_key is not None and self.idempotency_key not in self.input.model_fields:
            raise ValueError(
                f"{self.reference}: idempotency key {self.idempotency_key!r} is not a field of its "
                f"input ({self.input.__name__}), so the engine would have nowhere to put the key."
            )
        return self

    @model_validator(mode="after")
    def outcomes_have_titles(self) -> Self:
        # People read outcomes by their titles (D1), and a title for no outcome is a typo.
        if set(self.outcomes) != set(self.display.outcomes):
            raise ValueError(
                f"{self.reference}: outcomes and their display titles must match: outcomes "
                f"{sorted(self.outcomes)}, titles for {sorted(self.display.outcomes)}."
            )
        return self

    @property
    def reference(self) -> str:
        return f"{self.name}@{self.version}"


class NotInCatalog(LookupError):
    """A reference the catalog doesn't hold."""


class ContractConflict(ValueError):
    """A second, different contract under a reference already in the catalog."""


class Catalog:
    """Contracts by reference. Contracts only, never implementations: `core` runs no I/O."""

    def __init__(self) -> None:
        self._contracts: dict[str, ActivityContract] = {}

    def register(self, contract: ActivityContract) -> None:
        # A name stands for one promise for good (D5): a changed promise needs a new version.
        registered = self._contracts.get(contract.reference)
        if registered is not None and contract_hash(registered) != contract_hash(contract):
            raise ContractConflict(
                f"{contract.reference} is already registered with different content: "
                f"register it as {self.next_reference(contract.name)}."
            )
        # New, the same promise again (a worker restarting), or new wording, which applies at once.
        self._contracts[contract.reference] = contract

    def next_reference(self, name: str) -> str:
        """The reference a changed contract should take: one past the latest version."""
        versions = [c.version for c in self._contracts.values() if c.name == name]
        return f"{name}@{max(versions, default=0) + 1}"

    def contracts(self) -> list[ActivityContract]:
        """Every registered contract, by reference."""
        return sorted(self._contracts.values(), key=lambda c: c.reference)

    def get(self, reference: str) -> ActivityContract:
        if not REFERENCE.fullmatch(reference):
            raise NotInCatalog(
                f"{reference!r} is not a reference: a reference is name@N, such as "
                "payments.refund@1, with a whole-number version."
            )
        if reference in self._contracts:
            return self._contracts[reference]
        # Fail closed: an unknown reference is an error, never None a caller could ignore.
        name = reference.split("@")[0]
        same_name = sorted(
            (c for c in self._contracts.values() if c.name == name), key=lambda c: c.version
        )
        registered = ", ".join(c.reference for c in same_name)
        hint = f" Registered: {registered}." if registered else ""
        raise NotInCatalog(f"{reference} is not in the catalog.{hint}")


def contract_hash(contract: ActivityContract) -> str:
    """SHA-256 of what the contract promises: everything but `display`, schemas as JSON Schema."""
    promise = contract.model_dump(mode="json", exclude={"display", "input", "output"})
    promise["input"] = contract.input.model_json_schema()
    promise["output"] = contract.output.model_json_schema()
    # Canonical JSON: the same promise always gives the same bytes, so the same hash.
    canonical = json.dumps(promise, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def check_hashes(catalog: Catalog, recorded: dict[str, str]) -> list[str]:
    """What CI reports: contracts changed without a new version (D5), and unrecorded ones."""
    problems: list[str] = []
    for contract in catalog.contracts():
        digest = contract_hash(contract)
        if contract.reference not in recorded:
            problems.append(
                f'{contract.reference} is not recorded yet: add "{contract.reference}": "{digest}".'
            )
        elif digest != recorded[contract.reference]:
            problems.append(
                f"{contract.reference} changed without a new version: "
                f"register it as {catalog.next_reference(contract.name)}."
            )
    return problems
