"""A contract: what one activity promises, and what a contract refuses.

A definition only names an activity (`payments.refund@1`); its contract, written by the platform
team, says what that name promises. See docs/guides/activities.md.
"""

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A contract never changes once written, down to its parts (brief, D5); and a field it doesn't
# know is refused, never silently dropped (fail closed).
# Pydantic: `model_config` sets how a model behaves. `frozen=True` refuses any assignment after the
# object is built; `extra="forbid"` refuses a field the model doesn't declare.
FROZEN = ConfigDict(frozen=True, extra="forbid")

# How a reference is written, `payments.refund@1`, read left to right:
#   [a-z][a-z0-9_]*            a first word: a lowercase letter, then letters, digits or `_`
#   (\.[a-z][a-z0-9_]*)*       any number of further words, each after a dot (`.refund`)
#   @[1-9][0-9]*               `@`, then a whole number from 1, with no leading 0 and no `.0`
# Plans use the same pattern (`plan.py`), so a plan can only name what the catalog could register.
REFERENCE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*@[1-9][0-9]*")


def is_reference(text: str) -> bool:
    """Whether `text` is a whole reference, `name@N`: `payments.refund@1` is, `payments.refund@1.0`
    and `Payments Refund@1` aren't."""
    return REFERENCE.fullmatch(text) is not None


class Timeouts(BaseModel):
    """In seconds. `schedule_to_start` makes an activity no worker picks up fail loudly."""

    model_config = FROZEN

    # Pydantic: `Field(gt=0)` adds a check to the type: an int, and greater than 0.
    start_to_close: int = Field(gt=0)  # the longest one attempt may run
    schedule_to_start: int = Field(gt=0)  # the longest it may wait for a worker to pick it up


class RetryPolicy(BaseModel):
    """How Temporal retries the activity; intervals in seconds."""

    model_config = FROZEN

    maximum_attempts: int = Field(gt=0)  # attempts in all, the first included; 0 would mean
    # "retry forever" to Temporal
    initial_interval: int = Field(gt=0)  # the wait before the first retry
    backoff_coefficient: float = Field(ge=1)  # each wait is the last one times this; below 1,
    # each retry would come sooner


class Display(BaseModel):
    """What people read: presentation, so outside the contract's hash."""

    model_config = FROZEN

    title: str  # the activity's name for people: "Refund a customer"
    description: str  # one sentence on what it does
    outcomes: dict[str, str] = {}  # each declared outcome's title: "declined" -> "The ... declined"


class ActivityContract(BaseModel):
    """What one activity promises (brief, D17). Where it runs is a deployment binding, not this."""

    model_config = FROZEN

    name: str  # dotted lowercase, `payments.refund`
    version: int  # a whole number from 1; the reference is `name@version`
    # Pydantic: `type[BaseModel]` holds a model class itself, not an object of it.
    input: type[BaseModel]  # what the activity takes; published as JSON Schema
    output: type[BaseModel]  # what it returns; published as JSON Schema
    # Pydantic: `Literal[...]` accepts exactly one of the values listed, nothing else.
    risk: Literal["low", "medium", "high"]  # how bad a mistake would be; high needs an approval
    effect: Literal["read", "compute", "write", "notify"]  # what it does to the world
    timeouts: Timeouts  # how long it may wait and run
    retry: RetryPolicy  # how Temporal retries it
    idempotency_key: str | None  # the input field carrying the key a retry repeats, if any
    outcomes: tuple[str, ...]  # declared business failures, such as "declined" (brief, D17)
    display: Display  # what people read; outside the hash

    # Pydantic: a validator with `mode="before"` runs first, on the raw input (here a dict), before
    # any field is checked.
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

    # Pydantic: a validator with `mode="after"` runs once every field is checked, on the whole
    # object, so a rule can compare fields. It raises `ValueError`, which Pydantic reports inside a
    # `ValidationError`.
    @model_validator(mode="after")
    def can_be_named(self) -> Self:
        # Whatever is registered can be looked up: the same check `Catalog.get` makes.
        if not is_reference(self.reference):
            raise ValueError(
                f"{self.reference!r}: no reference could name it. A name is dotted lowercase "
                "(payments.refund), and a version a whole number from 1."
            )
        return self

    @model_validator(mode="after")
    def side_effects_are_idempotent(self) -> Self:
        # Anything that changes the world sends a key, so a retry can't do it twice (brief, D17).
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
        # People read outcomes by their titles (brief, D1), and a title for no outcome is a typo.
        if set(self.outcomes) != set(self.display.outcomes):
            raise ValueError(
                f"{self.reference}: outcomes and their display titles must match: outcomes "
                f"{sorted(self.outcomes)}, titles for {sorted(self.display.outcomes)}."
            )
        return self

    @property
    def reference(self) -> str:
        """How definitions name this contract: `payments.refund@1`."""
        return f"{self.name}@{self.version}"
