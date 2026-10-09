"""A case definition: its case file, milestones and steps, shape only (layer 8).

A case has no position (brief, idea 4): it declares what may happen, and the runtime works out,
after every event, which steps may start. Whether its expressions fit its fields and whether it
can deadlock is case validation's (layer 10); running it is the runtime's.
See docs/layers/08-case.md.
"""

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    model_validator,
)

from ventoux.core.plan import (
    ActivityReference,
    DeclaredType,
    Display,
    EventName,
    PlanExpression,
    RoleName,
    Source,
    matching,
    some_roles,
)

CaseName = Annotated[str, matching(r"[a-z][a-z0-9-]*", 'a case name looks like "refund"')]
# A field, step or milestone: no `.`, so `review.outcome` is never a field's name.
Name = Annotated[str, matching(r"[a-z][a-z0-9_]*", 'a name looks like "approved_amount"')]
Roles = Annotated[tuple[RoleName, ...], AfterValidator(some_roles)]


class Shape(BaseModel):
    """Every part of a case definition: frozen, and an unknown field is refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseField(Shape):
    """A field of the case file: its type, what people read, and a declared untrusted source."""

    declared: DeclaredType  # its type, written beside `display` (`"type": "number"`)
    display: Display  # what people read
    source: Source | None = None  # `untrusted:<label>`, never trusted (brief, D12)

    # Pydantic: a validator with `mode="before"` runs first, on the raw data (here a dict).
    @model_validator(mode="before")
    @classmethod
    def type_apart(cls, data: Any) -> Any:
        """The field's type (`type` and what goes with it) gathered under `declared`."""
        if not isinstance(data, dict):
            return data
        around = ("display", "source")
        declared = {key: value for key, value in data.items() if key not in around}
        return {"declared": declared} | {key: data[key] for key in around if key in data}


class Milestone(Shape):
    """A fact the case has reached, such as `paid`: recorded, never undone."""

    display: Display


class Outcome(Shape):
    """One answer a task offers (brief, D9)."""

    display: Display
    sets: tuple[Name, ...] = ()  # the case-file fields its form sets
    reaches: tuple[Name, ...] = ()  # milestones reached when a task is answered with it


class ApprovalDisplay(Shape):
    """What an approver reads: why the approval is asked."""

    reason: str = Field(min_length=1)


class Approval(Shape):
    """A person with one of `roles` approves running the step, when `when` holds (brief, D11)."""

    when: PlanExpression | None = None  # None: every run needs it
    roles: Roles  # who may approve
    display: ApprovalDisplay


class CloseReason(Shape):
    """A declared reason a person may close the case with, and who may (brief, D10)."""

    display: Display
    roles: Roles  # who may close the case with it


class Step(Shape):
    """What every kind of step says about when it may start (admission)."""

    display: Display
    requires: tuple[Name, ...] = ()  # milestones reached, or steps whose latest run is done
    when: PlanExpression | None = None  # read once `requires` are met
    automatic: bool = True  # starts by itself once admitted, at most once
    proposed_by: tuple[RoleName, ...] = ()  # who may propose it
    repeatable: bool = False  # may run again, when proposed
    reaches: tuple[Name, ...] = ()  # milestones reached when it completes


class TaskStep(Step):
    """A question to people with one of `roles`, answered with one of its outcomes (brief, D9)."""

    kind: Literal["task"]
    roles: Roles  # who may answer
    outcomes: Annotated[dict[EventName, Outcome], Field(min_length=1)]


class ActivityStep(Step):
    """One call to an activity from the catalog, perhaps behind an approval."""

    kind: Literal["activity"]
    activity: ActivityReference
    inputs: dict[str, PlanExpression] = {}
    approval: Approval | None = None


def kind_of(step: object) -> str | None:
    """The kind a step says it is, which picks its shape; None if it says none."""
    if isinstance(step, dict):
        kind = step.get("kind")
        return f"{kind} step" if isinstance(kind, str) else None
    return None


type AnyStep = Annotated[
    Annotated[TaskStep, Tag("task step")] | Annotated[ActivityStep, Tag("activity step")],
    Discriminator(kind_of),
]


class CaseDefinition(Shape):
    """A case: its case file's fields, milestones, steps, and a `sequence` shorthand (brief, D2)."""

    case: CaseName
    display: Display
    fields: dict[Name, CaseField] = {}
    milestones: dict[Name, Milestone] = {}
    steps: Annotated[dict[Name, AnyStep], Field(min_length=1)]
    sequence: tuple[Name, ...] = ()  # each step requires the one before it
    close_reasons: dict[Name, CloseReason] = {}  # how a person may close it, and who (brief, D10)
    closes_when: tuple[Name, ...] = ()  # milestones that close it once all are reached
    stays_open: bool = False  # True: it never closes by itself; a person closes it

    # Pydantic: a validator with `mode="after"` runs on the whole object, once its fields passed.
    @model_validator(mode="after")
    def names_name_something(self) -> "CaseDefinition":
        """Every name used is declared, and every step can start."""
        problems = [
            *(
                f"sequence: {name} is not a step"
                for name in self.sequence
                if name not in self.steps
            ),
            *(
                f"milestones.{name}: a milestone is not named like a step"
                for name in self.milestones
                if name in self.steps
            ),
        ]
        problems += [
            f"closes_when: {name} is not a milestone"
            for name in self.closes_when
            if name not in self.milestones
        ]
        # A case nobody could ever close: fail closed when it is read, not when it is stuck.
        if self.stays_open and not self.close_reasons:
            problems.append(
                "stays_open: a case that stays open names close_reasons, or nobody could close it"
            )
        for name, step in self.steps.items():
            problems += step_problems(f"steps.{name}", step, self)
        if problems:
            raise ValueError("\n".join(problems))
        return self


def step_problems(path: str, step: TaskStep | ActivityStep, case: CaseDefinition) -> list[str]:
    """What `step` names that `case` doesn't declare, and whether anyone can start it."""
    problems = [
        f"{path}.requires: {name} is neither a milestone nor a step"
        for name in step.requires
        if name not in case.milestones and name not in case.steps
    ]
    problems += reaching(f"{path}.reaches", step.reaches, case)
    if isinstance(step, TaskStep):
        for outcome_name, outcome in step.outcomes.items():
            where = f"{path}.outcomes.{outcome_name}"
            problems += [
                f"{where}.sets: {name} is not a field"
                for name in outcome.sets
                if name not in case.fields
            ]
            problems += reaching(f"{where}.reaches", outcome.reaches, case)
    # A step nobody may propose and that doesn't start by itself could never run.
    if not step.automatic and not step.proposed_by:
        problems.append(
            f"{path}: a step that doesn't start by itself names proposed_by, who may propose it"
        )
    # A step starts by itself at most once, so a step runs again only when someone proposes it.
    elif step.repeatable and not step.proposed_by:
        problems.append(
            f"{path}: a repeatable step runs again only when proposed: name proposed_by, who may "
            "propose it"
        )
    return problems


def reaching(path: str, names: tuple[str, ...], case: CaseDefinition) -> list[str]:
    return [f"{path}: {name} is not a milestone" for name in names if name not in case.milestones]


class CaseInvalid(Exception):
    """A case definition that can't be accepted: one line per problem, each with its path."""


def parse_case(data: object) -> CaseDefinition:
    """The case definition stored as `data`, or `CaseInvalid` listing every problem."""
    try:
        return CaseDefinition.model_validate(data)
    except ValidationError as error:
        raise CaseInvalid("\n".join(problem(e) for e in error.errors())) from None


STEP_KINDS = "a task or an activity"


def problem(error: Any) -> str:
    """One of Pydantic's errors as a line for the author: `steps.pay.activity: required`."""
    loc = [str(part) for part in error["loc"]]
    # Pydantic's own markers aren't in the definition: the shape it picked (`task step`), `[key]`,
    # and a field's type gathered under `declared` with the type it picked.
    if "declared" in loc:
        at = loc.index("declared")
        loc = loc[:at] + loc[at + 2 :]
    path = ".".join(part for part in loc if not part.endswith(" step") and part != "[key]")
    kind = error["type"]
    if kind in ("union_tag_invalid", "union_tag_not_found") and loc[:1] == ["steps"]:
        tag = error.get("ctx", {}).get("tag", "").removesuffix(" step")
        found = f", and this one is {tag!r}" if tag else ", and this one says none"
        return f"{path}.kind: a step is {STEP_KINDS}{found}"
    if kind == "missing":
        message = "required"
    elif kind == "extra_forbidden":
        message = "not a field here"
    else:
        message = str(error["msg"]).removeprefix("Value error, ")
    return f"{path}: {message}" if path else message
