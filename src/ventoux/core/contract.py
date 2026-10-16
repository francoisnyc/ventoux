"""A contract: what one activity promises, and what a contract refuses.

A definition only names an activity (`payments.refund@1`); its contract, written by the platform
team, says what that name promises. See docs/guides/activities.md.
"""

import re
from decimal import Decimal
from types import UnionType
from typing import Any, Literal, Self, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ventoux.core.expressions import BooleanType, FieldType, NumberType, OutcomeType, StringType
from ventoux.core.output_sources import HELD, HELD_NAMES, OutputSource, is_output_source
from ventoux.core.policy import KIND_NAMES, KINDS, Policy
from ventoux.core.references import marks

# A contract never changes once written, down to its parts (brief, D5); and a field it doesn't
# know is refused, never silently dropped (fail closed).
# Pydantic: `model_config` sets how a model behaves. `frozen=True` refuses any assignment after the
# object is built; `extra="forbid"` refuses a field the model doesn't declare.
# `revalidate_instances="always"` makes validating an object that is already built check it again,
# its parts included: `model_copy(update=...)` builds a copy without any check, so `Catalog.register`
# re-checks every contract it receives (learning question 31).
FROZEN = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

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


# What an input may be, as people read it: what a case's value can be exactly (brief, D36).
INPUT_NAMES = (
    "a decimal (Decimal), a text (str), true or false (bool) or one of some texts (a Literal of "
    "str), each possibly optional"
)


def held_input(annotation: Any) -> FieldType | None:
    """The type of a case's value an input of type `annotation` takes, or None if no value of a
    case is ever one: a `Decimal` is a number, a `str` a string, a `bool` a boolean, a `Literal`
    of texts one of them (an outcome type), each possibly optional. Inputs are validated
    strictly, so a value is never converted to fit (brief, D36)."""
    # typing: `Decimal | None` is a union; its other member is what a value must be.
    if get_origin(annotation) in (Union, UnionType):
        members = [member for member in get_args(annotation) if member is not type(None)]
        if len(members) != 1:
            return None
        annotation = members[0]
    if annotation is Decimal:
        return NumberType()
    if annotation is str:
        return StringType()
    if annotation is bool:
        return BooleanType()
    # typing: `Literal["low", "high"]` takes exactly those values; get_args gives them.
    if get_origin(annotation) is Literal and all(isinstance(a, str) for a in get_args(annotation)):
        return OutcomeType(outcomes=tuple(get_args(annotation)))
    return None


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


class Contract(BaseModel):
    """What every contract promises, an activity's or a workflow's (brief, D6). Where it runs
    is a deployment binding, never the contract."""

    model_config = FROZEN

    name: str  # dotted lowercase, `payments.refund`
    version: int  # a whole number from 1; the reference is `name@version`
    # Pydantic: `type[BaseModel]` holds a model class itself, not an object of it.
    input: type[BaseModel]  # what it takes; published as JSON Schema
    output: type[BaseModel]  # what it gives, with each field's source; published as JSON Schema
    # Pydantic: `Literal[...]` accepts exactly one of the values listed, nothing else.
    risk: Literal["low", "medium", "high"]  # how bad a mistake would be; high needs an approval
    effect: Literal["read", "compute", "write", "notify"]  # what it does to the world
    idempotency_key: str | None  # the input field carrying the key a retry repeats, if any
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
                f"input ({self.input.__name__}), so the engine would have nowhere to put the key. "
                f"Name one of its fields: {', '.join(sorted(self.input.model_fields))}."
            )
        return self

    @model_validator(mode="after")
    def policies_are_known(self) -> Self:
        # Fail closed: a kind of policy the engine doesn't know is refused, never ignored, since
        # nothing would check it (brief, D21).
        for name, field in self.input.model_fields.items():
            for policy in field.metadata:
                if isinstance(policy, Policy) and type(policy) not in KINDS:
                    raise ValueError(
                        f"{self.reference}: input {name} has a policy Ventoux doesn't know "
                        f"({type(policy).__name__}). The kinds are {KIND_NAMES}; a new kind is "
                        "added to the engine, never in a contract."
                    )
        return self

    @model_validator(mode="after")
    def references_are_texts_of_one_system(self) -> Self:
        # A reference is the ID of a record in one system: a text, as a case file holds it, and
        # one system, or the engine couldn't say which records it names (brief, D30).
        for name, field in self.input.model_fields.items():
            found = marks(self.input, name)
            if len(found) > 1:
                raise ValueError(
                    f"{self.reference}: input {name} names {len(found)} systems. A reference "
                    "names one: the system whose records it names."
                )
            if found and field.annotation is not str:
                kind = getattr(field.annotation, "__name__", str(field.annotation))
                raise ValueError(
                    f"{self.reference}: input {name} is a reference, so it is a text (str), and "
                    f"this one is {kind}."
                )
        return self

    @model_validator(mode="after")
    def output_sources_are_systems_or_labels(self) -> Self:
        # Trust comes from a system the platform team vouches for, or a person's answer, never
        # from a contract calling its output "trusted" (brief, D12).
        for name, field in self.output.model_fields.items():
            sources = [m for m in field.metadata if isinstance(m, OutputSource)]
            # Fail closed: two sources can't both be right, and the engine won't pick one.
            if len(sources) > 1:
                raise ValueError(
                    f"{self.reference}: output {name} has {len(sources)} sources. Declare one: "
                    "where its content really comes from."
                )
            for declared in sources:
                if not is_output_source(declared.source):
                    raise ValueError(
                        f"{self.reference}: output {name} has the source {declared.source!r}. "
                        "An output's source is system:<name> or untrusted:<label>: an activity "
                        "is never a person, and trust is earned, not declared."
                    )
        return self

    @model_validator(mode="after")
    def inputs_are_held_exactly(self) -> Self:
        # An input is given a case's value, never converted to fit: so it takes only a type a
        # case's value is, as an output does (brief, D29) (brief, D36).
        for name, field in self.input.model_fields.items():
            if held_input(field.annotation) is None:
                kind = getattr(field.annotation, "__name__", str(field.annotation))
                raise ValueError(
                    f"{self.reference}: input {name} is {kind}, which no value of a case is. An "
                    f"input is {INPUT_NAMES}: numbers are exact decimals, never binary floats "
                    "(brief, D20)."
                )
        return self

    @model_validator(mode="after")
    def outputs_are_held_exactly(self) -> Self:
        # An output lands in the case file, which holds values exactly: never a binary float, never
        # a Python object (brief, D20). Checked by the field's type, before any value arrives.
        for name, field in self.output.model_fields.items():
            if field.annotation not in HELD:
                kind = getattr(field.annotation, "__name__", str(field.annotation))
                raise ValueError(
                    f"{self.reference}: output {name} is {kind}, which the case file can't hold "
                    f"exactly. An output is {HELD_NAMES}: numbers are exact decimals, never "
                    "binary floats (brief, D20)."
                )
        return self

    @model_validator(mode="after")
    def no_output_named_outcome(self) -> Self:
        # Outputs land in the case file as `<step>.<field>`, where `<step>.outcome` is the step's
        # outcome: one name, one value (brief, D29).
        if "outcome" in self.output.model_fields:
            raise ValueError(
                f"{self.reference}: an output can't be named outcome: <step>.outcome is the "
                "step's outcome. Rename the field."
            )
        return self

    def policies(self, field: str) -> list[Policy]:
        """The input policies written on input `field`, each of which applies."""
        if field not in self.input.model_fields:
            return []  # not an input: validate reports it as UNKNOWN_INPUT
        # Pydantic: `metadata` holds what `Annotated[...]` attached to the field.
        return [m for m in self.input.model_fields[field].metadata if isinstance(m, Policy)]

    @property
    def reference(self) -> str:
        """How definitions name this contract: `payments.refund@1`."""
        return f"{self.name}@{self.version}"


class ActivityContract(Contract):
    """What one activity promises (brief, D17): the parts every contract has, and how Temporal
    runs and retries it, and the business failures it declares."""

    timeouts: Timeouts  # how long it may wait and run
    retry: RetryPolicy  # how Temporal retries it
    outcomes: tuple[str, ...]  # declared business failures, such as "declined" (brief, D17)

    @model_validator(mode="after")
    def outcomes_have_titles(self) -> Self:
        # People read outcomes by their titles (brief, D1), and a title for no outcome is a typo.
        if set(self.outcomes) != set(self.display.outcomes):
            raise ValueError(
                f"{self.reference}: outcomes and their display titles must match: outcomes "
                f"{sorted(self.outcomes)}, titles for {sorted(self.display.outcomes)}. Give each "
                "outcome exactly one title in display.outcomes."
            )
        return self
