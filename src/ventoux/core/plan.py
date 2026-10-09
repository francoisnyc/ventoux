"""Plans: a state machine written as data, shape only (layer 2).

A plan's states call an activity, wait for an answer, ask for an approval, or end. Whether its references exist and its
states are reachable is the validator's (layer 3); running it is the interpreter's (layer 5).
Drawn on the prototype's `src/core/schema.ts`: each state is dispatched on its distinguishing key,
so an error points at the right fields.
"""

import re
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    model_validator,
)

from ventoux.core.contract import REFERENCE
from ventoux.core.expressions import (
    BooleanType,
    Expression,
    ExpressionInvalid,
    ListType,
    NumberType,
    OutcomeType,
    ReferenceType,
    StringType,
    parse_expression,
)
from ventoux.core.provenance import UNTRUSTED_ORIGIN, is_label

KINDS = ("activity", "wait", "approval", "final")

# An approval's outcomes: always these two, never written in a plan (brief, D23).
APPROVE, REJECT = "approve", "reject"


def matching(pattern: str, message: str) -> AfterValidator:
    """A check that a text matches `pattern`, refusing it with `message`."""
    compiled = re.compile(pattern)

    def check(text: str) -> str:
        if not compiled.fullmatch(text):
            raise ValueError(message)
        return text

    return AfterValidator(check)


def expression(data: object) -> Expression:
    """`data` parsed as an expression, its refusal turned into a plan problem."""
    try:
        return parse_expression(data)
    except ExpressionInvalid as refused:
        raise ValueError(str(refused)) from None


def version(number: int) -> int:
    if number < 1:
        raise ValueError("a version is a whole number, 1 or more")
    return number


def some_outcomes(outcomes: tuple[str, ...]) -> tuple[str, ...]:
    if not outcomes:
        raise ValueError("a wait has at least one outcome")
    return outcomes


def some_roles(roles: tuple[str, ...]) -> tuple[str, ...]:
    # No roles would mean anyone may answer: a permissive default (brief, D22).
    if not roles:
        raise ValueError("a wait or an approval names at least one role that may answer it")
    return roles


def final_outcome(outcome: str) -> str:
    if outcome not in ("succeeded", "failed"):
        raise ValueError("a final state is succeeded or failed")
    return outcome


def declared_source(source: str) -> str:
    """A field's declared source: `untrusted:` and a label, never trusted (brief, D12)."""
    if source.startswith("trusted:"):
        raise ValueError(
            "a field can be declared untrusted, never trusted: trust comes from a contract the "
            "platform team owns, or a person's answer"
        )
    # A developer declares only untrusted sources; a system or a person is never declared, it is
    # what the engine records (brief, D12).
    origin, _, label = source.partition(":")
    if f"{origin}:" != UNTRUSTED_ORIGIN or not is_label(label):
        raise ValueError(
            'a source looks like "untrusted:customer": untrusted, and a lowercase label the '
            "platform team registered"
        )
    return source


def shorthand(transitions: object) -> object:
    """A bare state name in `on` is shorthand for one transition with no condition."""
    return [{"target": transitions}] if isinstance(transitions, str) else transitions


PlanName = Annotated[str, matching(r"[a-z][a-z0-9-]*", 'a plan name looks like "refund-pay"')]
StateName = Annotated[str, matching(r"[a-z][a-z0-9_]*", 'a state name looks like "await_approval"')]
RoleName = Annotated[str, matching(r"[a-z][a-z0-9-]*", 'a role looks like "support-lead"')]
EventName = Annotated[str, matching(r"[a-z][a-z0-9_]*", 'an event name looks like "approve"')]
ActivityReference = Annotated[
    str, matching(REFERENCE.pattern, 'an activity reference looks like "payments.refund@1"')
]
Duration = Annotated[
    str, matching(r"[1-9][0-9]*[smhd]", 'a duration looks like "30s", "5m", "48h" or "7d"')
]
PlanExpression = Annotated[Expression, BeforeValidator(expression)]
Source = Annotated[str, AfterValidator(declared_source)]
DeclaredType = Annotated[
    NumberType | StringType | BooleanType | OutcomeType | ReferenceType | ListType,
    Field(discriminator="type"),
]


class Shape(BaseModel):
    """Every part of a plan: frozen, and an unknown field is refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Display(Shape):
    """What people read: presentation, outside the plan's behaviour (brief, D5)."""

    title: str = Field(min_length=1)
    description: str = ""


class Transition(Shape):
    """Where to go next, if `when` holds (or always, with no `when`)."""

    target: StateName
    when: PlanExpression | None = None


type Transitions = Annotated[tuple[Transition, ...], BeforeValidator(shorthand)]


class ActivityState(Shape):
    """Call one activity from the catalog, then move on by what happened: `done` or an outcome."""

    activity: ActivityReference
    inputs: dict[str, PlanExpression] = {}
    on: dict[EventName, Transitions]


class Wait(Shape):
    """A closed list of answers, who may give one, and how long to wait (brief, D9)."""

    outcomes: Annotated[tuple[EventName, ...], AfterValidator(some_outcomes)]
    roles: Annotated[tuple[RoleName, ...], AfterValidator(some_roles)]  # who may answer
    # The plan fields each outcome's form sets, such as `{"accept": ["approved_amount"]}`.
    sets: dict[EventName, tuple[str, ...]] = {}
    timeout: Duration | None = None


class WaitState(Shape):
    """Wait for one of a closed list of answers, then move on by which one came."""

    wait: Wait
    on: dict[EventName, Transitions]


class Approval(Shape):
    """A person with one of `roles` approves or rejects running the activity state `of`: its own
    act, never read from an outcome's name (brief, D23)."""

    of: StateName  # the activity state it approves; its `approve` must lead there
    roles: Annotated[tuple[RoleName, ...], AfterValidator(some_roles)]  # who may approve
    timeout: Duration | None = None


class ApprovalState(Shape):
    """Ask for an approval, then move on by the answer: `approve`, `reject`, or `timeout`."""

    approval: Approval
    on: dict[EventName, Transitions]


def asked(state: WaitState | ApprovalState) -> Wait:
    """What a state that waits for a person asks: an approval asks `approve` or `reject`, by its
    roles, and sets no field."""
    if isinstance(state, WaitState):
        return state.wait
    approval = state.approval
    return Wait(outcomes=(APPROVE, REJECT), roles=approval.roles, timeout=approval.timeout)


class FinalState(Shape):
    """The plan has ended, and how."""

    final: Annotated[str, AfterValidator(final_outcome)]


def kind_of(state: object) -> str | None:
    """Which kind of state `state` is, by the one key that says so: its tag, `activity state`."""
    if isinstance(state, dict):
        kinds = [kind for kind in KINDS if kind in state]
        return f"{kinds[0]} state" if len(kinds) == 1 else None
    return None


def one_kind(state: object) -> object:
    """`state`, if it is exactly one kind; else a message saying what it is."""
    if isinstance(state, dict) and kind_of(state) is None:
        kinds = [kind for kind in KINDS if kind in state]
        raise ValueError(
            "a state is one of activity, wait, approval or final, "
            f"and this one is {' and '.join(kinds) or 'none'}"
        )
    return state


type State = Annotated[
    Annotated[ActivityState, Tag("activity state")]
    | Annotated[WaitState, Tag("wait state")]
    | Annotated[ApprovalState, Tag("approval state")]
    | Annotated[FinalState, Tag("final state")],
    Discriminator(kind_of),
    BeforeValidator(one_kind),
]


class Plan(Shape):
    """A plan: its fields, where it starts, and its states."""

    plan: PlanName
    version: Annotated[int, AfterValidator(version)]
    display: Display
    fields: dict[str, DeclaredType] = {}  # each field's type, which expressions are checked against
    # Each field's declared source, written on the field (`"source": "untrusted:llm"`) and kept
    # here, beside its type: an untrusted `string` is still a `string` to the expression check.
    sources: dict[str, Source] = {}
    initial: StateName
    states: dict[StateName, State]

    # Pydantic: a validator with `mode="before"` runs first, on the raw data (here a dict).
    @model_validator(mode="before")
    @classmethod
    def sources_beside_types(cls, data: Any) -> Any:
        """Each field's `source` moved out of the field, into `sources`."""
        if not isinstance(data, dict):
            return data  # not a plan's shape: the field checks say what is wrong
        # One place to write a source, on its field: a `sources` of the plan's own is refused.
        if "sources" in data:
            raise ValueError("sources: not a field here: write each source on its field")
        fields = data.get("fields", {})
        if not isinstance(fields, dict):
            return data
        types = {name: without_source(field) for name, field in fields.items()}
        sources = {
            name: field["source"]
            for name, field in fields.items()
            if isinstance(field, dict) and "source" in field
        }
        return {**data, "fields": types, "sources": sources}


def without_source(field: object) -> object:
    """A field's declaration without its `source`: its type alone."""
    if isinstance(field, dict):
        return {key: value for key, value in field.items() if key != "source"}
    return field


def set_by(plan: Plan) -> dict[str, str]:
    """Each field a person's form sets, and the first wait that sets it."""
    found: dict[str, str] = {}
    for name, state in plan.states.items():
        if isinstance(state, WaitState):
            for fields in state.wait.sets.values():
                for field in fields:
                    found.setdefault(field, name)
    return found


class PlanInvalid(Exception):
    """A plan that can't be accepted: one line per problem, each starting with its path."""


def parse_plan(data: object) -> Plan:
    """The plan stored as `data`, or `PlanInvalid` listing every problem with its path."""
    try:
        return Plan.model_validate(data)
    except ValidationError as error:
        raise PlanInvalid("\n".join(problem(e) for e in error.errors())) from None


FIELD_TYPES = "number, string, boolean, outcome, reference or list"


def problem(error: Any) -> str:
    """One of Pydantic's errors as a line for the plan's author: `states.pay.activity: …`."""
    # Pydantic's own markers (the tag of the kind it picked, `[key]` for a key) aren't in the plan.
    loc = [str(part) for part in error["loc"]]
    # A source is written on its field, so its problem is shown there: `fields.amount.source`.
    if loc[:1] == ["sources"]:
        loc = ["fields", *loc[1:], "source"]
    path = ".".join(part for part in loc if not part.endswith(" state") and part != "[key]")
    if error["type"] == "missing":
        message = "required"
    elif error["type"] == "extra_forbidden":
        message = "not a field here"
    elif error["type"] == "union_tag_invalid":
        message = f"a field's type is one of {FIELD_TYPES}, and this one is {error['ctx']['tag']}"
    else:
        message = str(error["msg"]).removeprefix("Value error, ")
    return f"{path}: {message}" if path else message
