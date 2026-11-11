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
    StrictBool,
    Tag,
    ValidationError,
    model_validator,
)

from ventoux.case.freshness import seconds_in
from ventoux.core.before_activity import given_as_reference
from ventoux.core.expressions import FieldType, ListType, ReferenceType, StringType
from ventoux.core.expressions.check import a_type
from ventoux.core.plan import (
    WRITTEN_FLAT,
    ActivityReference,
    DeclaredType,
    Display,
    EventName,
    PlanExpression,
    RoleName,
    Source,
    Whole,
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


def a_wait(age: str) -> str:
    """How long a timer waits after its moment: an age, at least a minute, fired once
    (brief, D44). Kept as written, as an age is."""
    if seconds_in(age) == 0:  # `seconds_in` refuses anything that isn't `30m`, `12h` or `1d`
        raise ValueError("a timer waits at least 1m: write a later age")
    return age


CaseName = Annotated[str, matching(r"[a-z][a-z0-9-]*", 'a case name looks like "refund"')]
# A field, step or milestone: no `.`, so `review.outcome` is never a field's name.
Name = Annotated[str, matching(r"[a-z][a-z0-9_]*", 'a name looks like "approved_amount"')]
Roles = Annotated[tuple[RoleName, ...], AfterValidator(some_roles)]
# A plan, by its name and version: `refund-order@1` (brief, D28).
PlanReference = Annotated[
    str, matching(r"[a-z][a-z0-9-]*@[1-9][0-9]*", 'a plan reference looks like "refund-order@1"')
]
# A child case, by its name and the release its parent pins: `repair@3` (brief, D74).
CaseReference = Annotated[
    str, matching(r"[a-z][a-z0-9-]*@[1-9][0-9]*", 'a case reference looks like "repair@3"')
]


class Shape(BaseModel):
    """Every part of a case definition: frozen, and an unknown field is refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseField(Shape):
    """A field of the case file: its type, what people read, and a declared untrusted source."""

    # The published schema says the type flat, as written (brief, D60). `ventoux schema` reads this.
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=WRITTEN_FLAT)

    declared: DeclaredType  # its type, written beside `display` (`"type": "number"`)
    display: Display  # what people read
    source: Source | None = None  # `untrusted:<label>`, never trusted (brief, D12)
    # Who may see it, narrowing the default: anyone holding a role the case names (brief, D30).
    visible_to: Roles | None = None
    # Personal data a decision needs: encrypted with the case's key, never written out (brief, D31).
    # Pydantic: `StrictBool` reads `true` and `false` only, never "no", "on", 1 or 1.0, as the
    # published schema says (brief, D60).
    sensitive: StrictBool = False

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


# A system the platform team registered, written as a label is: `portal`, `claims-archive`.
SystemName = Annotated[str, matching(r"[a-z][a-z0-9-]*", 'a system name looks like "portal"')]


def some_senders(roles: tuple[str, ...]) -> tuple[str, ...]:
    """No roles would let nobody send it, or be read as anyone: refused (brief, D22)."""
    if not roles:
        raise ValueError("an event sent by people names at least one role that may send it")
    return roles


class SentBy(Shape):
    """Who may send an event: one sender, a system or people, never both (brief, D41)."""

    system: SystemName | None = None  # a system the platform team registered, such as `portal`
    # People holding one of these roles, checked as for a close reason (brief, D10) (brief, D22).
    roles: Annotated[tuple[RoleName, ...], AfterValidator(some_senders)] | None = None

    # Pydantic: a validator with `mode="after"` runs on the whole object, once its fields passed.
    @model_validator(mode="after")
    def one_sender(self) -> "SentBy":
        """One sender, so each value an event carries comes from one writer (brief, D41)."""
        if (self.system is None) == (self.roles is None):
            raise ValueError(
                'an event is sent by one sender: a system ({"system": "portal"}) or people '
                '({"roles": ["support"]})'
            )
        return self


class PayloadField(Shape):
    """One value an event carries: its type, what people read, and a declared untrusted source."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=WRITTEN_FLAT)

    declared: DeclaredType  # its type, written beside `display` (`"type": "string"`)
    display: Display  # what people read
    # `untrusted:<label>`, added to its sender whoever sends it, never trusted (brief, D12).
    source: Source | None = None

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

    @model_validator(mode="after")
    def no_list(self) -> "PayloadField":
        """A list waits until a list value can be checked, and is never packed into a text
        meanwhile, which a list type would later have to read differently (brief, D41)."""
        if isinstance(self.declared, ListType):
            # Pydantic reports a ValueError raised here as the field's problem; a TypeError
            # would escape it.
            raise ValueError(  # noqa: TRY004
                "an event carries no list yet: a list comes once a list value can be checked"
            )
        return self


class DeclaredEvent(Shape):
    """An event from outside the case: who may send it, and what it carries (brief, D41)."""

    display: Display
    sent_by: SentBy
    # Each value it carries, landing in the case file as `<event>.<field>`, every field given on
    # every arrival.
    payload: dict[Name, PayloadField] = {}


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


class ForEach(Shape):
    """A step run once per item of a list field, each run named by a number the engine gives its
    item's key the first time it sees it (brief, D73)."""

    over: Name  # the list field whose items it runs for
    key: Name  # the text field of each item that tells one item from another


class Assign(Shape):
    """Who is asked when each entry opens: the person who opened the case, or whoever gave a
    task's latest answer. Only people the case already knows, each named by the trusted caller,
    so untrusted data never routes work (brief, D71)."""

    to: Literal["opener", "answered"]  # whom: the opener, or a task's latest answerer
    step: Name | None = None  # for `answered`: the task whose latest answer's person is asked

    def aloud(self) -> str:
        """The rule as a reader says it: `asked of whoever answered review`."""
        if self.to == "opener":
            return "asked of whoever opened the case"
        return f"asked of whoever answered {self.step}"

    @model_validator(mode="after")
    def names_a_step_when_answered(self) -> "Assign":
        """`answered` names its task; `opener` names none."""
        if self.to == "answered" and self.step is None:
            raise ValueError('"answered" names the task whose answerer is asked: add "step"')
        if self.to == "opener" and self.step is not None:
            raise ValueError('"opener" is the person who opened the case: remove "step"')
        return self


class Approval(Shape):
    """`count` different people with one of `roles` approve running the step, when `when` holds
    (brief, D11) (brief, D47)."""

    when: PlanExpression | None = None  # None: every run needs it
    roles: Roles  # who may approve; every approver holds one of them
    # A whole number of at least 1, as written: `"2"` is refused, never read as 2 (brief, D47).
    count: Annotated[
        int, Whole(1, "how many people must approve: a whole number of at least 1, such as 2")
    ] = 1  # how many people must approve
    display: ApprovalDisplay
    assign: Assign | None = None  # who is asked when it is asked; None: its queue (brief, D71)


def sent_by(declared: DeclaredEvent) -> str:
    """Who sends an event, as the inbox says it: `from portal`, `by support or fraud`."""
    if declared.sent_by.system is not None:
        return f"from {declared.sent_by.system}"
    return f"by {' or '.join(declared.sent_by.roles or ())}"


class CloseReason(Shape):
    """A declared reason a person may close the case with, and who may (brief, D10)."""

    display: Display
    roles: Roles  # who may close the case with it


class Step(Shape):
    """What every kind of step says about when it may start (admission)."""

    display: Display
    requires: tuple[Name, ...] = ()  # milestones reached, or steps whose latest run is done
    when: PlanExpression | None = None  # read once `requires` are met
    automatic: StrictBool = True  # starts by itself once admitted, at most once
    proposed_by: tuple[RoleName, ...] = ()  # who may propose it
    repeatable: StrictBool = False  # may run again, when proposed
    reaches: tuple[Name, ...] = ()  # milestones reached when it completes
    # Owed by the case: it doesn't close by itself until this step's latest run is done
    # (brief, D72).
    required: StrictBool = False


class TaskStep(Step):
    """A question to people with one of `roles`, answered with one of its outcomes (brief, D9)."""

    kind: Literal["task"]
    roles: Roles  # who may answer
    outcomes: Annotated[dict[EventName, Outcome], Field(min_length=1)]
    assign: Assign | None = None  # who is asked when each run opens; None: its queue (brief, D71)
    for_each: ForEach | None = None  # one run per item of a list field (brief, D73)


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
    for_each: ForEach | None = None  # one run per item of a list field (brief, D73)

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


class WaitStep(Step):
    """A step that waits for an event from outside: its run is open until the event's next
    arrival, which makes it done. Pending work, unlike a rule listening for it (brief, D10)
    (brief, D41)."""

    kind: Literal["wait"]
    event: Name  # the declared event it waits for


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


class CaseStep(Step):
    """A whole case opened from this step, a child of this case: its opening given from the case
    file, and its end report read back as the step's outputs (brief, D74)."""

    kind: Literal["case"]
    case: CaseReference  # the child, with the release this case pins
    inputs: dict[Name, PlanExpression] = {}  # each of the child's opening fields, from the file
    max_age: MaxAge = {}  # how old each fact it reads may be when it runs (brief, D18)

    @model_validator(mode="before")
    @classmethod
    def no_approval(cls, data: Any) -> Any:
        """A case step has no approval: the child's own steps ask for theirs (brief, D74)."""
        if isinstance(data, dict) and "approval" in data:
            raise ValueError("a case step has no approval: its child's steps ask for their own")
        return data


class Then(Shape):
    """What a rule does when it fires: stop steps (brief, D40), set fields (brief, D42), reach
    milestones (brief, D38), start steps (brief, D39). Done in that order."""

    # Fields of the case file it sets, each from an expression read on the case file as it was
    # when the condition was read (brief, D42).
    set: dict[Name, PlanExpression] = {}
    reach: tuple[Name, ...] = ()  # milestones it reaches
    # Steps it proposes a run of: the engine proposes, admission decides (brief, D39).
    start: tuple[Name, ...] = ()
    # Steps whose run going on now it stops, as a close would; a step may start again later
    # (brief, D40). A list of names now; an item may become an object with options later.
    stop: tuple[Name, ...] = ()

    # Pydantic: a validator with `mode="after"` runs on the whole object, once its fields passed.
    @model_validator(mode="after")
    def does_something(self) -> "Then":
        """A rule that does nothing is refused, so a typo never hides a rule."""
        if not self.reach and not self.start and not self.stop and not self.set:
            raise ValueError(
                "a rule reaches a milestone, starts a step, stops one or sets a field, at least one"
            )
        return self

    @model_validator(mode="after")
    def no_restart(self) -> "Then":
        """A rule doesn't stop and start one step: that restart would mean one thing for a task,
        cancelled at once, and another for an activity, which runs on (brief, D40)."""
        for step in self.stop:
            if step in self.start:
                raise ValueError(
                    f"{step} is both stopped and started: a rule can't restart a step; stop it "
                    "here, and start it from another rule"
                )
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


class EventArrived(Shape):
    """The moment an event from outside arrives: each arrival (brief, D41)."""

    event: Name  # the declared event


# The moments named by a step, a milestone, a task or an event. A closed list: a new moment is a
# decision recorded in the brief, like an operator (brief, D38) (brief, D39) (brief, D41).
KINDS_OF_MOMENT = ("started", "reached", "answered", "event")


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
    | Annotated[AnsweredTask, Tag("answered moment")]
    | Annotated[EventArrived, Tag("event moment")],
    Discriminator(moment_of),
]

MOMENTS = (
    '"opened", {"started": <step>}, {"reached": <milestone>}, {"answered": <task>} or '
    '{"event": <event>}'
)


class After(Shape):
    """The moment a timer fires: time passing after another moment, once (brief, D44)."""

    after: Annotated[str, AfterValidator(a_wait)]  # an age: `30m`, `12h`, `2d`; one firing
    # The moment it is set on: one of the five others, never a timer (brief, D44).
    since: Moment


def rule_moment_of(on: object) -> str:
    """Whether a rule's `on` is a timer (it names `after`) or one of the five other moments, whose
    own shape is picked next."""
    return "timer moment" if isinstance(on, dict) and "after" in on else "moment"


# What a rule's `on` takes: the five moments, or a timer set on one of them (brief, D44).
type RuleMoment = Annotated[
    Annotated[Moment, Tag("moment")] | Annotated[After, Tag("timer moment")],
    Discriminator(rule_moment_of),
]

RULE_MOMENTS = f'{MOMENTS.replace(" or ", ", ")} or {{"after": <age>, "since": <moment>}}'


def anchor(on: object) -> object:
    """The moment a rule's timer is set on, or the rule's own moment if it has no timer: what a
    check reads, since a timer fires only once its moment has come (brief, D44)."""
    return on.since if isinstance(on, After) else on


class Rule(Shape):
    """On a moment, when a condition holds, then act on the case (brief, D38)."""

    display: Display
    # The moment it reacts to: the case opened, a step's run started, a milestone reached, a task
    # answered, an event arrived, or time passing after one of these. A closed list: a new moment
    # is a decision recorded in the brief (brief, D38) (brief, D44).
    on: RuleMoment
    when: PlanExpression | None = None  # read once the moment has come, on the case file then
    then: Then


# Patterns: a named shape written in `rules`, which expands into raw rules when the definition is
# read. A pattern adds no engine capability: it is data for raw rules (brief, D7) (brief, D46).


class Sla(Shape):
    """What an sla measures: each run of a step, from its own start (brief, D46)."""

    step: Name  # the step whose runs are measured
    # How long a run may go on before the sla acts: an age, at least a minute.
    within: Annotated[str, AfterValidator(a_wait)]


class SlaRule(Shape):
    """An sla: when a run of a step isn't done, rejected or stopped within an age of its start,
    act. Expands into one timer set on each run's start, which ends with that run (brief, D44)."""

    display: Display
    sla: Sla
    when: PlanExpression | None = None  # read when the timer fires, as a raw timer's is
    then: Then


def some_ages(ages: tuple[str, ...]) -> tuple[str, ...]:
    """A reminder comes at least once: a reminder of nothing would hide a typo."""
    if not ages:
        raise ValueError('a reminder comes after at least one age: list them, such as ["2d"]')
    return ages


class Reminder(Shape):
    """What a reminder nudges: a task left open, after each of some ages (brief, D46)."""

    task: Name  # the task whose open runs are reminded of
    # After how long each reminder comes, from the run's start: one firing each, never a repeat.
    after: Annotated[tuple[Annotated[str, AfterValidator(a_wait)], ...], AfterValidator(some_ages)]
    start: Name  # the repeatable step each reminder starts, such as one drafting a letter


class ReminderRule(Shape):
    """A reminder: while a run of a task is open, start a step after each age. It informs, it
    never decides: it only starts its step. Expands into one rule per age (brief, D46)."""

    display: Display
    reminder: Reminder
    when: PlanExpression | None = None  # read when each reminder's timer fires


def rule_kind_of(entry: object) -> str | None:
    """Whether an entry of `rules` is a raw rule (it names `on`) or a pattern (it names `sla` or
    `reminder`); None if it is neither."""
    if isinstance(entry, dict):
        for key, kind in (("on", "raw rule"), ("sla", "sla rule"), ("reminder", "reminder rule")):
            if key in entry:
                return kind
    return None


# What an entry of `rules` takes: a raw rule, or a pattern that expands into raw rules.
type AnyRule = Annotated[
    Annotated[Rule, Tag("raw rule")]
    | Annotated[SlaRule, Tag("sla rule")]
    | Annotated[ReminderRule, Tag("reminder rule")],
    Discriminator(rule_kind_of),
]

RULE_SHAPES = "a rule is a raw rule, with on, when and then, or a pattern: sla or reminder"


def expanded(name: str, entry: Rule | SlaRule | ReminderRule) -> dict[str, Rule]:
    """The raw rules an entry of `rules` stands for, by name: a raw rule itself; an sla's one
    timer, under its own name; a reminder's timer for each age, `<name>_<age>`. A pure function of
    the entry alone, so a name never depends on anything written elsewhere (brief, D46)."""
    # Pydantic: `model_construct` builds an object without checking it again: each part was
    # checked as the pattern was read.
    if isinstance(entry, SlaRule):
        on = After.model_construct(
            after=entry.sla.within, since=Started.model_construct(started=entry.sla.step)
        )
        return {
            name: Rule.model_construct(
                display=entry.display, on=on, when=entry.when, then=entry.then
            )
        }
    if isinstance(entry, ReminderRule):
        since = Started.model_construct(started=entry.reminder.task)
        then = Then.model_construct(start=(entry.reminder.start,))
        return {
            f"{name}_{age}": Rule.model_construct(
                display=entry.display,
                on=After.model_construct(after=age, since=since),
                when=entry.when,
                then=then,
            )
            for age in entry.reminder.after
        }
    return {name: entry}


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
    | Annotated[CaseStep, Tag("case step")]
    | Annotated[WorkflowStep, Tag("workflow step")]
    | Annotated[WaitStep, Tag("wait step")],
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
    # What the case does on a moment, as written: raw rules and patterns (brief, D46). Written
    # `rules` in the JSON; the rules the engine runs are read from `rules`, below.
    written: dict[Name, AnyRule] = Field(default={}, alias="rules")
    events: dict[
        Name, DeclaredEvent
    ] = {}  # what may come from outside, and who sends it (brief, D41)
    close_reasons: dict[Name, CloseReason] = {}  # how a person may close it, and who (brief, D10)
    closes_when: tuple[Name, ...] = ()  # milestones that close it once all are reached
    stays_open: StrictBool = False  # True: it never closes by itself; a person closes it
    # Whether a request may forget it (brief, D32): `allowed` open or closed; `while_open`, refused
    # once it is closed (books and records); `never`, always refused.
    forgetting: Literal["allowed", "while_open", "never"] = "allowed"
    # What its end report carries when it closes as a child: its own fields, read by its parent
    # as the case step's outputs (brief, D74).
    reports: tuple[Name, ...] = ()

    @property
    def rules(self) -> dict[str, Rule]:
        """Every rule the engine runs, in the order written: each raw rule, and each pattern's
        expansion where the pattern is written. Worked out from what is written each time it is
        read, so no reader of rules can miss one, nor see one written since (brief, D46)."""
        return {
            rule: raw
            for name, entry in self.written.items()
            for rule, raw in expanded(name, entry).items()
        }

    def pattern_of(self, rule: str) -> str | None:
        """The pattern `rule` was expanded from, by the name it is written under; None for a raw
        rule, or a name that is no rule."""
        for name, entry in self.written.items():
            if not isinstance(entry, Rule) and rule in expanded(name, entry):
                return name
        return None

    # Pydantic: a validator with `mode="after"` runs on the whole object, once its fields passed.
    @model_validator(mode="after")
    def names_name_something(self) -> "CaseDefinition":
        """Every name used is declared, and every step can start."""
        # A pattern that can't expand is said first, and nothing below is checked: its rules
        # would be read from it (one cause, one issue).
        problems = self.expand()
        if problems:
            raise ValueError("\n".join(problems))
        problems += [
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
        problems += list_problems(self)
        problems += report_problems(self)
        started_by_rules = {step for rule in self.rules.values() for step in rule.then.start}
        for name, step in self.steps.items():
            problems += step_problems(f"steps.{name}", step, self, name in started_by_rules)
        for name in self.events:
            # An arrival is an entry beside step runs and firings (`cancelled#1`), and its values
            # are read as `<event>.<field>` beside a step's: so no name is shared.
            if name in self.steps or name in self.milestones or name in self.rules | self.written:
                problems.append(
                    f"events.{name}: an event is not named like a step, a milestone or a rule"
                )
        for name, rule in self.rules.items():
            # A rule's firings are entries beside step runs (`flag_large#1`), so no name is shared.
            if name in self.steps or name in self.milestones:
                problems.append(
                    f"{self.where(name)}: a rule is not named like a step or a milestone"
                )
            on = f"rules.{name}.on.since" if isinstance(rule.on, After) else f"rules.{name}.on"
            problems += moment_problems(on, anchor(rule.on), self)
            problems += reaching(f"rules.{name}.then.reach", rule.then.reach, self)
            problems += set_problems(f"rules.{name}", rule, self)
            problems += [
                f"rules.{name}.then.{action}: {step} is not a step"
                for action, steps in (("start", rule.then.start), ("stop", rule.then.stop))
                for step in steps
                if step not in self.steps
            ]
        if problems:
            raise ValueError("\n".join(problems))
        return self

    def expand(self) -> list[str]:
        """What keeps a pattern from expanding into the rules the engine runs (brief, D46): a
        problem of its own, or a rule it gives that is already a rule."""
        problems: list[str] = []
        given: set[str] = set()
        for name, entry in self.written.items():
            found = pattern_problems(f"rules.{name}", entry, self)
            if found:
                problems += found
                continue
            for rule in expanded(name, entry):
                if rule != name and (rule in self.written or rule in given):
                    problems.append(
                        f"rules.{name}: it gives the rule {rule}, which is already a rule: rename "
                        "one of them"
                    )
                given.add(rule)
        return problems

    def where(self, rule: str) -> str:
        """Where a rule is written: its own entry, or the pattern it was expanded from."""
        return f"rules.{self.pattern_of(rule) or rule}"


def pattern_problems(
    path: str, entry: Rule | SlaRule | ReminderRule, case: "CaseDefinition"
) -> list[str]:
    """What a pattern names that `case` doesn't declare, or can't mean (brief, D46). A raw rule
    has none here: its own are checked as any rule's."""
    if isinstance(entry, SlaRule):
        if entry.sla.step not in case.steps:
            return [f"{path}.sla.step: {entry.sla.step} is not a step"]
        return []
    if isinstance(entry, ReminderRule):
        reminder = entry.reminder
        problems: list[str] = []
        if not isinstance(case.steps.get(reminder.task), TaskStep):
            problems.append(f"{path}.reminder.task: {reminder.task} is not a task")
        started = case.steps.get(reminder.start)
        if started is None:
            problems.append(f"{path}.reminder.start: {reminder.start} is not a step")
        elif not started.repeatable:
            # Each reminder is its own run: a second start of a step that has run would only be
            # recorded, and nothing would be sent.
            problems.append(
                f"{path}.reminder.start: {reminder.start} isn't repeatable, so only its first "
                f"reminder would ever run: make {reminder.start} repeatable"
            )
        seen: dict[int, str] = {}  # each age's time in seconds, and the age first written for it
        for age in reminder.after:
            if seconds_in(age) in seen:
                problems.append(
                    f"{path}.reminder.after: {seen[seconds_in(age)]} and {age} are the same time: "
                    "give each reminder its own"
                )
                break
            seen[seconds_in(age)] = age
        return problems
    return []


def moment_problems(path: str, moment: object, case: CaseDefinition) -> list[str]:
    """What a moment names that `case` doesn't declare: a step, a milestone, a task, an event."""
    if isinstance(moment, Started) and moment.started not in case.steps:
        return [f"{path}.started: {moment.started} is not a step"]
    if isinstance(moment, Reached):
        return reaching(f"{path}.reached", (moment.reached,), case)
    if isinstance(moment, AnsweredTask) and not isinstance(
        case.steps.get(moment.answered), TaskStep
    ):
        return [f"{path}.answered: {moment.answered} is not a task"]
    if isinstance(moment, EventArrived) and moment.event not in case.events:
        return [f"{path}.event: {moment.event} is not an event"]
    return []


def for_each_problems(path: str, for_each: ForEach, case: CaseDefinition) -> list[str]:
    """What keeps a step from repeating over `for_each.over`: it is a list field (brief, D73)."""
    field = case.fields.get(for_each.over)
    if field is None:
        return [f"{path}: {for_each.over} is not a field"]
    if not isinstance(field.declared, ListType):
        declared = a_type(field.declared)
        return [
            f"{path}: {for_each.over} is {declared}, not a list: a step repeats over a list field"
        ]
    # A run is matched to its item by the key, so every item has one, as a text (brief, D73).
    if not isinstance(field.declared.fields.get(for_each.key), StringType):
        where = f"{for_each.key} is not a text field of {for_each.over}"
        return [f"{path}: {where}: a key is a text field every item has"]
    return []


def repeated_step_problems(
    path: str, name: str, step: TaskStep | ActivityStep, case: CaseDefinition
) -> list[str]:
    """A repeated step starts by itself, a run per item, and has no approval yet: a proposal or a
    rule's start names a step, never an item (brief, D73)."""
    problems = []
    keys = [
        *(["automatic"] if not step.automatic else []),
        *(["proposed_by"] if step.proposed_by else []),
        *(["repeatable"] if step.repeatable else []),
    ]
    starts_by_itself = f"{path}: a repeated step starts by itself, a run per item"
    if keys:
        problems.append(f"{starts_by_itself}: drop {' and '.join(keys)}")
    for rule_name, rule in case.rules.items():
        if name in rule.then.start:
            problems.append(f"{starts_by_itself}: no rule starts it, and {rule_name} does")
    if isinstance(step, ActivityStep) and step.approval is not None:
        # Open approvals are kept one per step, never per run: a deliberate limit (brief, D48).
        problems.append(f"{path}.approval: a repeated step has no approval yet")
    return problems + one_run_shapes(path, name, step)


def one_run_shapes(path: str, name: str, step: TaskStep | ActivityStep) -> list[str]:
    """What assumes one run per step, refused on a repeated one for now: a milestone it reaches,
    a field its answer sets, a fact it needs fresh, whom a rule asks. Each a deliberate limit, a
    door for later (brief, D48) (brief, D73)."""
    reach = f"a repeated step reaches no milestone yet: reach it from a step that requires {name}"
    problems = [f"{path}.reaches: {reach}"] if step.reaches else []
    if isinstance(step, TaskStep):
        for outcome_name, outcome in step.outcomes.items():
            where = f"{path}.outcomes.{outcome_name}"
            if outcome.reaches:
                problems.append(f"{where}.reaches: {reach}")
            if outcome.sets:
                problems.append(
                    f"{where}.sets: a repeated task's answer sets no field yet: each answer would "
                    "overwrite the last"
                )
        if step.assign is not None:
            problems.append(f"{path}.assign: a repeated task is asked of its queue yet")
    if isinstance(step, ActivityStep) and step.max_age:
        problems.append(f"{path}.max_age: a repeated step needs no fact fresh yet")
    return problems


def list_problems(case: CaseDefinition) -> list[str]:
    """What a list may not be yet, and the name a repeated step reads its item by (brief, D73)."""
    problems = [
        f"{kind}.{EACH}: {EACH} is the name a repeated step reads its item by: name it otherwise"
        for kind, names in (
            ("fields", case.fields),
            ("steps", case.steps),
            ("milestones", case.milestones),
            ("events", case.events),
        )
        if EACH in names
    ]
    lists = {name for name, field in case.fields.items() if isinstance(field.declared, ListType)}
    problems += [
        f"fields.{name}: a list is never sensitive yet: keep the personal data out of it"
        for name in lists
        if case.fields[name].sensitive
    ]
    # A list is given at the opening only, for now: never by a person's form (brief, D73).
    problems += [
        f"steps.{step_name}.outcomes.{outcome_name}.sets: {field} is a list, and a form never "
        "gives a list yet: a list is given at the opening"
        for step_name, step in case.steps.items()
        if isinstance(step, TaskStep)
        for outcome_name, outcome in step.outcomes.items()
        for field in outcome.sets
        if field in lists
    ]
    return problems + misread_problems(case)


# The name a repeated step reads its own item by: `each.amount` (brief, D73).
EACH = "each"


def misread_problems(case: CaseDefinition) -> list[str]:
    """`each` read where no item is, and a repeated step's outcome or output read at all: several
    runs have no one outcome (brief, D73)."""
    repeated = {name for name, step in case.steps.items() if is_repeated(step)}
    problems = []
    for where, owner, expression in expressions_in(case):
        for read in fields_read(expression):
            first = read.split(".")[0]
            if first == EACH and owner not in repeated:
                problems.append(f"{where}: {EACH} is read only in a repeated step")
            elif first in repeated:
                problems.append(f"{where}: {read}: a repeated step has no one outcome")
    return problems


def is_repeated(step: object) -> bool:
    """Whether the step runs once per item of a list (brief, D73)."""
    return isinstance(step, TaskStep | ActivityStep) and step.for_each is not None


def expressions_in(case: CaseDefinition) -> list[tuple[str, str | None, PlanExpression]]:
    """Every expression the definition holds, where it is, and the step it belongs to (None for
    a rule's): each step's `when`, its approval's `when`, its inputs; each rule's `when` and what
    it sets."""
    found: list[tuple[str, str | None, PlanExpression]] = []
    for name, step in case.steps.items():
        if step.when is not None:
            found.append((f"steps.{name}.when", name, step.when))
        approval = step.approval if isinstance(step, CallStep) else None
        if approval is not None and approval.when is not None:
            found.append((f"steps.{name}.approval.when", name, approval.when))
        if isinstance(step, CallStep | PlanStep):
            found += [
                (f"steps.{name}.inputs.{field}", name, expression)
                for field, expression in step.inputs.items()
            ]
    for name, rule in case.rules.items():
        where = case.where(name)
        if rule.when is not None:
            found.append((f"{where}.when", None, rule.when))
        found += [
            (f"{where}.then.set.{field}", None, expression)
            for field, expression in rule.then.set.items()
        ]
    return found


def report_problems(case: CaseDefinition) -> list[str]:
    """What a report can't carry: a field the case doesn't have; a sensitive one, for now; a list,
    since an output is an exact value (brief, D29) (brief, D74)."""
    problems: list[str] = []
    for name in case.reports:
        path = f"reports.{name}"
        field = case.fields.get(name)
        if field is None:
            problems.append(
                f"{path}: {case.case} has no field {name}: a report lists the case's own fields"
            )
        elif field.sensitive:
            problems.append(
                f"{path}: {name} is sensitive, and a report carries no sensitive field yet"
            )
        elif isinstance(field.declared, ListType):
            problems.append(f"{path}: {name} is a list, and a report carries no list")
    return problems


def step_problems(
    path: str,
    step: TaskStep | CallStep | PlanStep | CaseStep | WaitStep,
    case: CaseDefinition,
    rule_starts: bool,
) -> list[str]:
    """What `step` names that `case` doesn't declare, and whether anyone can start it: itself, a
    person who proposes it, or a rule (`rule_starts`)."""
    problems = [
        f"{path}.requires: {name} is neither a milestone nor a step"
        for name in step.requires
        if name not in case.milestones and name not in case.steps
    ]
    problems += reaching(f"{path}.reaches", step.reaches, case)
    # A required step is owed in every case, so no condition may excuse it (brief, D72).
    if step.required and step.when is not None:
        problems.append(
            f"{path}: a required step is owed in every case, so it has no when: start it from a "
            "rule, or drop required"
        )
    if isinstance(step, TaskStep | ActivityStep) and step.for_each is not None:
        problems += for_each_problems(f"{path}.for_each", step.for_each, case)
        problems += repeated_step_problems(path, path.removeprefix("steps."), step, case)
    if isinstance(step, TaskStep):
        for outcome_name, outcome in step.outcomes.items():
            where = f"{path}.outcomes.{outcome_name}"
            problems += [
                f"{where}.sets: {name} is not a field"
                for name in outcome.sets
                if name not in case.fields
            ]
            problems += reaching(f"{where}.reaches", outcome.reaches, case)
    if isinstance(step, CallStep | PlanStep):
        problems += stale_names(path, step)
    if isinstance(step, WaitStep) and step.event not in case.events:
        problems.append(f"{path}.event: {step.event} is not an event")
    if isinstance(step, TaskStep) and step.assign is not None:
        problems += assign_problems(f"{path}.assign", step.assign, case)
    if isinstance(step, CallStep) and step.approval is not None and step.approval.assign:
        problems += assign_problems(f"{path}.approval.assign", step.approval.assign, case)
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


def assign_problems(path: str, rule: Assign, case: CaseDefinition) -> list[str]:
    """What an assignment rule names that the case doesn't have: `answered` asks whoever answered
    a task, so the step it names is one, since only a task is answered by a person (brief, D71)."""
    if rule.step is None:
        return []
    named = case.steps.get(rule.step)
    if named is None:
        return [f"{path}.step: {rule.step} is not a step"]
    if not isinstance(named, TaskStep):
        kind = an(named.kind)
        return [f"{path}.step: {rule.step} is {kind} step; only a task is answered by a person"]
    return []


def an(word: str) -> str:
    """`an activity`, `a plan`: the article a sentence puts before a step's kind."""
    return f"an {word}" if word[0] in "aeiou" else f"a {word}"


def set_problems(path: str, rule: Rule, case: CaseDefinition) -> list[str]:
    """What a rule's `set` names that it may not set (brief, D42)."""
    problems: list[str] = []
    read = [*rule.then.set.values(), *([rule.when] if rule.when is not None else [])]
    if rule.then.set and not any(fields_read(expression) for expression in read):
        # A value comes from everything its rule read; reading nothing, it would come from
        # nobody, which no value of a case file does (brief, D36) (brief, D42).
        problems.append(
            f"{path}.then.set: {path.removeprefix('rules.')} reads no field, so what it sets would "
            "come from nobody: read a field in its when or its values, or reach a milestone "
            "instead"
        )
    answered = form_fields(case)
    for name in rule.then.set:
        field = case.fields.get(name)
        if field is None:
            problems.append(f"{path}.then.set: {name} is not a field")
        elif isinstance(field.declared, ListType):
            problems.append(
                f"{path}.then.set.{name}: {name} is a list, and a rule never sets a list yet: a "
                "list comes once a list value can be checked"
            )
        elif isinstance(field.declared, ReferenceType) and (
            given_as_reference(rule.then.set[name], declared_types(case))[0]
            != field.declared.system
        ):
            # A reference goes only where its system is expected, read as it is (brief, D30).
            system = field.declared.system
            problems.append(
                f"{path}.then.set.{name}: {name} is a reference to {system}, and is set only "
                f"from a reference field of {system}, read as it is"
            )
        elif name in answered:
            # One kind of writer per field: a rule never undoes a person's answer (brief, D9).
            problems.append(
                f"{path}.then.set.{name}: {name} is set by a person in {answered[name]}, so a rule "
                f"never sets it: set another field, and read {name} there"
            )
        else:
            problems += revealing(f"{path}.then.set.{name}", name, rule, case)
    return problems


def revealing(path: str, name: str, rule: Rule, case: CaseDefinition) -> list[str]:
    """What a set value would reveal: it is computed from every field its value and its rule's
    condition read, so it is as sensitive as the most sensitive of them (brief, D31), and seen by
    no role that can't see each of them (brief, D30). A view may hide more than its source, never
    less (brief, D42)."""
    written = case.fields[name]
    read = [rule.then.set[name], *([rule.when] if rule.when is not None else [])]
    problems: list[str] = []
    for source in sorted({field for expression in read for field in fields_read(expression)}):
        field = case.fields.get(source)
        if field is None:
            continue  # an outcome, an output or a payload value: seen by every role of the case
        if field.sensitive and not written.sensitive:
            problems.append(
                f"{path}: {name} is set from {source}, which is sensitive: declare {name} sensitive"
            )
        hidden = field.visible_to
        if hidden is not None and (
            written.visible_to is None or not set(written.visible_to) <= set(hidden)
        ):
            seen = (
                "every role of the case"
                if written.visible_to is None
                else " or ".join(written.visible_to)
            )
            only = " or ".join(hidden)
            problems.append(
                f"{path}: {name} is seen by {seen}, and is set from {source}, which only {only} "
                f"sees: let only {only} see {name}"
            )
    return problems


def declared_types(case: CaseDefinition) -> dict[str, FieldType]:
    """Each field of the case file, and its declared type."""
    return {name: field.declared for name, field in case.fields.items()}


def rule_fields(case: CaseDefinition) -> dict[str, str]:
    """Each field a rule sets, and the first rule that sets it (brief, D42)."""
    found: dict[str, str] = {}
    for name, rule in case.rules.items():
        for field in rule.then.set:
            found.setdefault(field, name)
    return found


def form_fields(case: CaseDefinition) -> dict[str, str]:
    """Each field a task's form sets, and the first task that sets it."""
    found: dict[str, str] = {}
    for name, step in case.steps.items():
        if isinstance(step, TaskStep):
            for outcome in step.outcomes.values():
                for field in outcome.sets:
                    found.setdefault(field, name)
    return found


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

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        super().__init__("\n".join(line(path, said) for path, said in problems))
        # Where each problem is, as its line says it: what the conformance suite compares, since
        # reading gives no code and wording is never compared (brief, D80). "" is the root.
        self.paths = tuple(path for path, _ in problems)


def line(path: str, said: str) -> str:
    """A problem as the author reads it: `steps.pay.activity: required`, or what is wrong alone at
    the root."""
    return f"{path}: {said}" if path else said


def parse_case(data: object) -> CaseDefinition:
    """The case definition stored as `data`, or `CaseInvalid` listing every problem."""
    try:
        return CaseDefinition.model_validate(data)
    except ValidationError as error:
        raise CaseInvalid([problem(e) for e in error.errors()]) from None


STEP_KINDS = "a task, an activity, a plan, a case, a workflow or a wait"


def problem(error: Any) -> tuple[str, str]:
    """One of Pydantic's errors for the author: its path and what is wrong, `("steps.pay.activity",
    "required")`."""
    loc = [str(part) for part in error["loc"]]
    # Pydantic's own markers aren't in the definition: the shape it picked (`task step`), `[key]`,
    # and a field's type gathered under `declared` with the type it picked.
    if "declared" in loc:
        at = loc.index("declared")
        loc = loc[:at] + loc[at + 2 :]
    path = ".".join(
        part
        for part in loc
        if not part.endswith(" step")
        and not part.endswith(" moment")
        and not part.endswith(" rule")
        and part not in ("[key]", "moment")
    )
    kind = error["type"]
    if kind == "union_tag_not_found" and loc[:1] == ["rules"] and len(loc) == 2:
        # An entry of `rules` that is neither a raw rule nor a pattern (brief, D46).
        return path, RULE_SHAPES
    if kind in ("union_tag_invalid", "union_tag_not_found") and loc[:1] == ["rules"]:
        # A timer's own moment takes the five others; a rule's `on`, a timer too.
        return path, f"a moment is {MOMENTS if loc[-1] == 'since' else RULE_MOMENTS}"
    if kind in ("union_tag_invalid", "union_tag_not_found") and loc[:1] == ["steps"]:
        tag = error.get("ctx", {}).get("tag", "").removesuffix(" step")
        found = f", and this one is {tag!r}" if tag else ", and this one says none"
        return f"{path}.kind", f"a step is {STEP_KINDS}{found}"
    if kind == "missing":
        message = "required"
    elif kind == "extra_forbidden":
        message = "not a field here"
    else:
        message = str(error["msg"]).removeprefix("Value error, ")
    return path, message
