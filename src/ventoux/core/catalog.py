"""The catalog: the activities a definition can call, each with its contract.

A definition only names an activity (`payments.refund@1`); its contract, written by the platform
team, says what that name promises. See docs/guides/activities.md.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

# A contract never changes once written (D5), down to its parts.
FROZEN = ConfigDict(frozen=True)

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
        # A name stands for one content for good (D5): a changed promise needs a new version.
        registered = self._contracts.get(contract.reference)
        if registered == contract:
            return  # the same promise again (a worker restarting, say): nothing changes
        if registered is not None:
            latest = max(c.version for c in self._contracts.values() if c.name == contract.name)
            raise ContractConflict(
                f"{contract.reference} is already registered with different content: "
                f"register it as {contract.name}@{latest + 1}."
            )
        self._contracts[contract.reference] = contract

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
