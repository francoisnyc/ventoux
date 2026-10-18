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

from ventoux.case.freshness import seconds_in
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
from ventoux.core.provenance import fields_read


def an_age(age: str) -> str:
    """An age a step needs a fact within: a whole number and a unit, at least a minute
    (brief, D33). Kept as written, so the definition reads back as it was stored."""
    if seconds_in(age) == 0:  # `seconds_in` refuses anything that isn't `30m`, `12h` or `1d`
        raise ValueError("an age is at least 1m")
    return age


# How old each fact a step reads may be when it runs: `{"check_order.status": "1d"}` (brief, D18).
MaxAge = dict[str, Annotated[str, AfterValidator(an_age)]]

CaseName = Annotated[str, matching(r"[a-z][a-z0-9-]*", 'a case name looks like "refund"')]
# A field, step or milestone: no `.`, so `review.outcome` is never a field's name.
Name = Annotated[str, matching(r"[a-z][a-z0-9_]*", 'a name looks like "approved_amount"')]
Roles = Annotated[tuple[RoleName, ...], AfterValidator(some_roles)]
# A plan, by its name and version: `refund-order@1` (brief, D28).
PlanReference = Annotated[
    str, matching(r"[a-z][a-z0-9-]*@[1-9][0-9]*", 'a plan reference looks like "refund-order@1"')
]


class Shape(BaseModel):
    """Every part of a case definition: frozen, and an unknown field is refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseField(Shape):
    """A field of the case file: its type, what people read, and a declared untrusted source."""

    declared: DeclaredType  # its type, written beside `display` (`"type": "number"`)
    display: Display  # what people read
    source: Source | None = None  # `untrusted:<label>`, never trusted (brief, D12)
    # Who may see it, narrowing the default: anyone holding a role the case names (brief, D30).
    visible_to: Roles | None = None
    # Personal data a decision needs: encrypted with the case's key, never written out (brief, D31).
    sensitive: bool = False

    # Pydantic: a validator with `mode="before"` runs first, on the raw data (here a dict).
    @model_validator(mode="before")
    @classmethod
    def type_apart(cls, data: Any) -> Any:
        """The field's type (`type` and what goes with it) gathered under `declared`."""
        if not isinstance(data, dict):
            return data
        around = ("display", "source", "visible_to", "sensitive")
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


class CallStep(Step):
    """A step that calls what a contract in the catalog promises, perhaps behind an approval: an
    activity, or an existing workflow. Both are checked the same way before they start."""

    inputs: dict[str, PlanExpression] = {}  # each input the contract takes, from the case file
    approval: Approval | None = None
    max_age: MaxAge = {}  # how old each fact it reads may be when it runs (brief, D18)

    @property
    def called(self) -> str:
        """The reference of the contract it calls: `payments.refund@2`, `kyc.check@1`."""
        raise NotImplementedError


class ActivityStep(CallStep):
    """One call to an activity from the catalog."""

    kind: Literal["activity"]
    activity: ActivityReference

    @property
    def called(self) -> str:
        return self.activity


class WorkflowStep(CallStep):
    """An existing Temporal workflow, run as one step: its contract in the catalog, where it runs
    bound by the deployment (brief, D6)."""

    kind: Literal["workflow"]
    workflow: ActivityReference  # its workflow contract's reference, such as `kyc.check@1`

    @property
    def called(self) -> str:
        return self.workflow


class PlanStep(Step):
    """A plan the deployment supplies, run as one step: its fields given from the case file
    (brief, D28). A case references a plan, never defines one."""

    kind: Literal["plan"]
    plan: PlanReference
    inputs: dict[Name, PlanExpression] = {}  # each of the plan's fields, read from the case file
    max_age: MaxAge = {}  # how old each fact it reads may be when it runs (brief, D18)

    # Pydantic: a validator with `mode="before"` runs first, on the raw data (here a dict).
    @model_validator(mode="before")
    @classmethod
    def no_approval(cls, data: Any) -> Any:
        """A plan step has no approval: the plan carries its own, checked when it is read."""
        if isinstance(data, dict) and "approval" in data:
            raise ValueError("a plan step has no approval: its plan asks for its own")
        return data


class Then(Shape):
    """What a rule does when it fires: reach milestones (brief, D38), start steps (brief, D39)."""

    reach: tuple[Name, ...] = ()  # milestones it reaches
    # Steps it proposes a run of: the engine proposes, admission decides (brief, D39).
    start: tuple[Name, ...] = ()

    # Pydantic: a validator with `mode="after"` runs on the whole object, once its fields passed.
    @model_validator(mode="after")
    def does_something(self) -> "Then":
        """A rule that does nothing is refused, so a typo never hides a rule."""
        if not self.reach and not self.start:
            raise ValueError("a rule reaches a milestone or starts a step, at least one")
        return self


class Started(Shape):
    """The moment a run of a step starts: each run, a refresh included (brief, D38)."""

    started: Name  # the step


class Reached(Shape):
    """The moment a milestone is reached: once, since it is never undone (brief, D38)."""

    reached: Name  # the milestone


class AnsweredTask(Shape):
    """The moment a run of a task is answered, whatever the outcome: each answer (brief, D39)."""

    answered: Name  # the task


# The moments named by a step or a milestone. A closed list: a new moment is a decision recorded in
# the brief, like an operator (brief, D38) (brief, D39).
KINDS_OF_MOMENT = ("started", "reached", "answered")


def moment_of(on: object) -> str | None:
    """The kind of moment `on` names, which picks its shape; None if it names none."""
    if on == "opened":
        return "opened moment"
    if isinstance(on, dict) and len(on) == 1 and next(iter(on)) in KINDS_OF_MOMENT:
        return f"{next(iter(on))} moment"
    return None


# Pydantic: `Discriminator` picks one shape from the data, as for steps, so a wrong moment gets one
# line, not one per shape it could have been.
type Moment = Annotated[
    Annotated[Literal["opened"], Tag("opened moment")]
    | Annotated[Started, Tag("started moment")]
    | Annotated[Reached, Tag("reached moment")]
    | Annotated[AnsweredTask, Tag("answered moment")],
    Discriminator(moment_of),
]

MOMENTS = '"opened", {"started": <step>}, {"reached": <milestone>} or {"answered": <task>}'


class Rule(Shape):
    """On a moment, when a condition holds, then act on the case (brief, D38)."""

    display: Display
    # The moment it reacts to: the case opened, a step's run started, a milestone reached, a task
    # answered. A closed list: a new moment is a decision recorded in the brief (brief, D38).
    on: Moment
    when: PlanExpression | None = None  # read once the moment has come, on the case file then
    then: Then


def kind_of(step: object) -> str | None:
    """The kind a step says it is, which picks its shape; None if it says none."""
    if isinstance(step, dict):
        kind = step.get("kind")
        return f"{kind} step" if isinstance(kind, str) else None
    return None


type AnyStep = Annotated[
    Annotated[TaskStep, Tag("task step")]
    | Annotated[ActivityStep, Tag("activity step")]
    | Annotated[PlanStep, Tag("plan step")]
    | Annotated[WorkflowStep, Tag("workflow step")],
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
    rules: dict[Name, Rule] = {}  # what the case does on a moment (brief, D38)
    close_reasons: dict[Name, CloseReason] = {}  # how a person may close it, and who (brief, D10)
    closes_when: tuple[Name, ...] = ()  # milestones that close it once all are reached
    stays_open: bool = False  # True: it never closes by itself; a person closes it
    # Whether a request may forget it (brief, D32): `allowed` open or closed; `while_open`, refused
    # once it is closed (books and records); `never`, always refused.
    forgetting: Literal["allowed", "while_open", "never"] = "allowed"

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
        # A sensitive value is seen only by the roles its field lists (brief, D16), so it lists
        # them: no default reaches it.
        problems += [
            f"{name} is sensitive, so it must say who may see it: add visible_to"
            for name, field in self.fields.items()
            if field.sensitive and field.visible_to is None
        ]
        started_by_rules = {step for rule in self.rules.values() for step in rule.then.start}
        for name, step in self.steps.items():
            problems += step_problems(f"steps.{name}", step, self, name in started_by_rules)
        for name, rule in self.rules.items():
            # A rule's firings are entries beside step runs (`flag_large#1`), so no name is shared.
            if name in self.steps or name in self.milestones:
                problems.append(f"rules.{name}: a rule is not named like a step or a milestone")
            if isinstance(rule.on, Started) and rule.on.started not in self.steps:
                problems.append(f"rules.{name}.on.started: {rule.on.started} is not a step")
            if isinstance(rule.on, Reached):
                problems += reaching(f"rules.{name}.on.reached", (rule.on.reached,), self)
            if isinstance(rule.on, AnsweredTask) and not isinstance(
                self.steps.get(rule.on.answered), TaskStep
            ):
                problems.append(f"rules.{name}.on.answered: {rule.on.answered} is not a task")
            problems += reaching(f"rules.{name}.then.reach", rule.then.reach, self)
            problems += [
                f"rules.{name}.then.start: {step} is not a step"
                for step in rule.then.start
                if step not in self.steps
            ]
        if problems:
            raise ValueError("\n".join(problems))
        return self


def step_problems(
    path: str, step: TaskStep | CallStep | PlanStep, case: CaseDefinition, rule_starts: bool
) -> list[str]:
    """What `step` names that `case` doesn't declare, and whether anyone can start it: itself, a
    person who proposes it, or a rule (`rule_starts`)."""
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
    if not isinstance(step, TaskStep):
        problems += stale_names(path, step)
    # A step nobody may propose and that doesn't start by itself could never run; and a step starts
    # by itself at most once, so a repeatable one runs again only when proposed. Unless a rule
    # starts it: 11b's one loosening (brief, D39).
    if not step.proposed_by and not rule_starts:
        if not step.automatic:
            problems.append(
                f"{path}: a step that doesn't start by itself names proposed_by, who may propose "
                "it, or a rule starts it"
            )
        elif step.repeatable:
            problems.append(
                f"{path}: a repeatable step runs again only when proposed or started by a rule: "
                "name proposed_by, who may propose it"
            )
    return problems


def stale_names(path: str, step: CallStep | PlanStep) -> list[str]:
    """Each field `max_age` names that the step doesn't read: freshness belongs where a fact is
    used (brief, D18), so a step says it only of what it reads."""
    name = path.removeprefix("steps.")
    reads = {field for expression in read_by(step) for field in fields_read(expression)}
    return [
        f"{path}.max_age: {name} doesn't read {field} in its inputs, its when or its approval: "
        "name only what it reads"
        for field in step.max_age
        if field not in reads
    ]


def read_by(step: CallStep | PlanStep) -> list[PlanExpression]:
    """Every expression the step reads: its inputs, its `when` and its approval's `when`."""
    expressions = [*step.inputs.values()]
    if step.when is not None:
        expressions.append(step.when)
    if isinstance(step, CallStep) and step.approval is not None and step.approval.when is not None:
        expressions.append(step.approval.when)
    return expressions


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


STEP_KINDS = "a task, an activity, a plan or a workflow"


def problem(error: Any) -> str:
    """One of Pydantic's errors as a line for the author: `steps.pay.activity: required`."""
    loc = [str(part) for part in error["loc"]]
    # Pydantic's own markers aren't in the definition: the shape it picked (`task step`), `[key]`,
    # and a field's type gathered under `declared` with the type it picked.
    if "declared" in loc:
        at = loc.index("declared")
        loc = loc[:at] + loc[at + 2 :]
    path = ".".join(
        part
        for part in loc
        if not part.endswith(" step") and not part.endswith(" moment") and part != "[key]"
    )
    kind = error["type"]
    if kind in ("union_tag_invalid", "union_tag_not_found") and loc[:1] == ["rules"]:
        return f"{path}: a moment is {MOMENTS}"
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
