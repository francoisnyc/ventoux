"""A case definition, built in Python: each call writes one entry of the JSON (layer 14a, 14b)
(brief, D58).

The builder is one-to-one with the JSON: `refund.task("review", …)` writes `steps.review`, with the
same names. It writes data and decides nothing: whether the definition holds together is
`ventoux check`'s, against the catalog, and running it is the engine's, on the JSON. It refuses
only what keeps it from writing the JSON as given (choice 25).
See docs/layers/14-builder.md, docs/guides/builder.md and docs/QUICKSTART.md, section 2.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from ventoux.tooling.builder.common import called_from, display, field_name, given
from ventoux.tooling.builder.entries import (
    Approval,
    Event,
    Milestone,
    Moment,
    Outcome,
    Payload,
    SentBy,
    Step,
    Task,
    Then,
    Timer,
)
from ventoux.tooling.builder.expressions import Expr, ReferenceExpr
from ventoux.tooling.builder.fields import Data, Field, FieldType
from ventoux.tooling.builder.plan import Plan

# Whether a request may forget a case (brief, D32).
type Forgetting = Literal["allowed", "while_open", "never"]


class Case:
    """A case definition, built one entry at a time, in the order the calls are made: steps are
    admitted, and rules on one moment act, in the order written (brief, D38)."""

    def __init__(
        self,
        name: str,
        title: str,
        description: str | None = None,
        stays_open: bool | None = None,
        forgetting: Forgetting | None = None,
    ) -> None:
        self.name = name
        self.display = display(title, description)
        self.fields: dict[str, Data] = {}
        self.milestones: dict[str, Data] = {}
        self.steps: dict[str, Data] = {}
        self.order: list[str] = []  # `sequence`: each step requires the one before it
        self.rules: dict[str, Data] = {}
        self.events: dict[str, Data] = {}
        self.close_reasons: dict[str, Data] = {}
        self.closing: list[str] = []  # `closes_when`: milestones that close it once all are reached
        self.stays_open = stays_open  # True: it never closes by itself; a person closes it
        self.forgetting = forgetting
        self.plans: dict[str, Plan] = {}  # the plans its plan steps run, by reference
        # Where each entry was written, by its path (`steps.pay`), `""` the case itself: where
        # `ventoux check` says a problem (brief, D59).
        self.where: dict[str, str] = {"": called_from()}

    # The case file.

    def field[E: Expr[Any]](
        self,
        name: str,
        kind: FieldType[E],
        title: str,
        description: str | None = None,
        source: str | None = None,
        visible_to: Sequence[str] | None = None,
        sensitive: bool | None = None,
    ) -> E:
        """A field of the case file, `fields.<name>`, read in expressions as itself."""
        entry: Data = {**kind.declared, "display": display(title, description)}
        if source is not None:
            entry["source"] = source  # `untrusted:<label>`, never trusted (brief, D12)
        if visible_to is not None:
            entry["visible_to"] = list(visible_to)  # who may see it (brief, D30)
        if sensitive is not None:
            entry["sensitive"] = sensitive  # encrypted with the case's key (brief, D31)
        self.fields[self.new_name(name, self.fields, "field")] = entry
        self.where[f"fields.{name}"] = called_from()
        return kind.reads_as({"var": name})

    def reference(
        self,
        name: str,
        system: str,
        title: str,
        description: str | None = None,
        source: str | None = None,
        visible_to: Sequence[str] | None = None,
        sensitive: bool | None = None,
    ) -> ReferenceExpr:
        """A reference to a record kept in `system`: its ID, never a copy (brief, D8)
        (brief, D16). The same as `field(name, Field.reference(system), …)`."""
        return self.field(
            name, Field.reference(system), title, description, source, visible_to, sensitive
        )

    def milestone(self, name: str, title: str, description: str | None = None) -> Milestone:
        """A fact the case reaches, such as `paid`: recorded, never undone."""
        self.milestones[self.new_name(name, self.milestones, "milestone")] = {
            "display": display(title, description)
        }
        self.where[f"milestones.{name}"] = called_from()
        return Milestone(name)

    # Steps. Every kind takes the same keywords for when it may start (`requires`, `when`,
    # `automatic`, `proposed_by`, `repeatable`) and what it reaches, written after its own keys.

    def task(
        self,
        name: str,
        title: str,
        roles: Sequence[str],
        outcomes: Mapping[str, Outcome],
        description: str | None = None,
        requires: Sequence[Step | Milestone] = (),
        when: Expr[bool] | None = None,
        automatic: bool | None = None,
        proposed_by: Sequence[str] | None = None,
        repeatable: bool | None = None,
        reaches: Sequence[Milestone] | None = None,
    ) -> Task:
        """A task for a person holding one of `roles`, answered with one of `outcomes`."""
        entry: Data = {"kind": "task", "display": display(title, description), "roles": list(roles)}
        entry |= starting(requires, when, automatic, proposed_by, repeatable, reaches)
        entry["outcomes"] = {key: answer(outcome) for key, outcome in outcomes.items()}
        self.add(name, entry)
        return Task(name)

    def activity(
        self,
        name: str,
        activity: str,
        title: str,
        inputs: Mapping[str, Expr[Any]] | None = None,
        description: str | None = None,
        requires: Sequence[Step | Milestone] = (),
        when: Expr[bool] | None = None,
        automatic: bool | None = None,
        proposed_by: Sequence[str] | None = None,
        repeatable: bool | None = None,
        reaches: Sequence[Milestone] | None = None,
        approval: Approval | None = None,
        max_age: Mapping[str, str] | None = None,
    ) -> Step:
        """A call to `activity` (`payments.refund@2`), a contract in the catalog, with `inputs`
        read from the case file."""
        entry: Data = {"kind": "activity", "display": display(title, description)}
        entry["activity"] = activity
        entry |= calling(inputs)
        entry |= starting(requires, when, automatic, proposed_by, repeatable, reaches)
        entry |= guarded(approval, max_age)
        self.add(name, entry)
        return Step(name)

    def workflow(
        self,
        name: str,
        workflow: str,
        title: str,
        inputs: Mapping[str, Expr[Any]] | None = None,
        description: str | None = None,
        requires: Sequence[Step | Milestone] = (),
        when: Expr[bool] | None = None,
        automatic: bool | None = None,
        proposed_by: Sequence[str] | None = None,
        repeatable: bool | None = None,
        reaches: Sequence[Milestone] | None = None,
        approval: Approval | None = None,
        max_age: Mapping[str, str] | None = None,
    ) -> Step:
        """An existing Temporal workflow, run as one step: its workflow contract in the catalog
        (`kyc.check@1`), where it runs bound by the deployment (brief, D6)."""
        entry: Data = {"kind": "workflow", "display": display(title, description)}
        entry["workflow"] = workflow
        entry |= calling(inputs)
        entry |= starting(requires, when, automatic, proposed_by, repeatable, reaches)
        entry |= guarded(approval, max_age)
        self.add(name, entry)
        return Step(name)

    def wait(
        self,
        name: str,
        event: Event,
        title: str,
        description: str | None = None,
        requires: Sequence[Step | Milestone] = (),
        when: Expr[bool] | None = None,
        automatic: bool | None = None,
        proposed_by: Sequence[str] | None = None,
        repeatable: bool | None = None,
        reaches: Sequence[Milestone] | None = None,
    ) -> Step:
        """A step that waits for `event`'s next arrival (brief, D41)."""
        entry: Data = {"kind": "wait", "display": display(title, description), "event": event.name}
        entry |= starting(requires, when, automatic, proposed_by, repeatable, reaches)
        self.add(name, entry)
        return Step(name)

    def plan_step(
        self,
        name: str,
        plan: Plan,
        title: str,
        inputs: Mapping[str, Expr[Any]] | None = None,
        description: str | None = None,
        requires: Sequence[Step | Milestone] = (),
        when: Expr[bool] | None = None,
        automatic: bool | None = None,
        proposed_by: Sequence[str] | None = None,
        repeatable: bool | None = None,
        reaches: Sequence[Milestone] | None = None,
        max_age: Mapping[str, str] | None = None,
    ) -> Step:
        """`plan`, run as one step, its fields given from the case file (brief, D28). It joins
        the case's package (brief, D50)."""
        entry: Data = {"kind": "plan", "display": display(title, description)}
        entry["plan"] = plan.reference
        entry |= calling(inputs)
        entry |= starting(requires, when, automatic, proposed_by, repeatable, reaches)
        entry |= guarded(None, max_age)
        self.add(name, entry)
        self.plans[plan.reference] = plan
        return Step(name)

    def sequence(self, *steps: Step) -> None:
        """`steps` run in this order, each starting by itself when the one before is done."""
        if self.order:
            # One `sequence` per case: a second would replace the first without a word.
            raise ValueError(f"{self.name} already has a sequence: give it every step once")
        self.order = [step.name for step in steps]
        self.where["sequence"] = called_from()

    # Events, rules and the two patterns (brief, D41) (brief, D38) (brief, D46).

    def event(
        self,
        name: str,
        title: str,
        sent_by: SentBy,
        payload: Mapping[str, Payload] | None = None,
        description: str | None = None,
    ) -> Event:
        """An event from outside: who may send it, and what it carries (brief, D41)."""
        sender: Data = {}
        if sent_by.system is not None:
            sender["system"] = sent_by.system
        if sent_by.roles is not None:
            sender["roles"] = list(sent_by.roles)
        entry: Data = {"display": display(title, description), "sent_by": sender}
        if payload is not None:
            entry["payload"] = {key: carried(value) for key, value in payload.items()}
        self.events[self.new_name(name, self.events, "event")] = entry
        self.where[f"events.{name}"] = called_from()
        types = {key: str(value.kind.declared["type"]) for key, value in (payload or {}).items()}
        return Event(name, types)

    def rule(
        self,
        name: str,
        title: str,
        on: Moment | Timer,
        then: Then,
        when: Expr[bool] | None = None,
        description: str | None = None,
    ) -> None:
        """On a moment, when a condition holds, then act on the case (brief, D38)."""
        entry: Data = {"display": display(title, description), "on": on.data}
        if when is not None:
            entry["when"] = given(when).data
        entry["then"] = acting(then)
        self.rules[self.new_name(name, self.rules, "rule")] = entry
        self.where[f"rules.{name}"] = called_from()

    def sla(
        self,
        name: str,
        title: str,
        step: Step,
        within: str,
        then: Then,
        when: Expr[bool] | None = None,
        description: str | None = None,
    ) -> None:
        """When a run of `step` isn't done within an age of its own start, act (brief, D46).
        Measured from each run's start: `since=first_start` isn't offered."""
        entry: Data = {"display": display(title, description)}
        entry["sla"] = {"step": step.name, "within": within}
        if when is not None:
            entry["when"] = given(when).data
        entry["then"] = acting(then)
        self.rules[self.new_name(name, self.rules, "rule")] = entry
        self.where[f"rules.{name}"] = called_from()

    def reminder(
        self,
        name: str,
        title: str,
        task: Task,
        after: Sequence[str],
        start: Step,
        when: Expr[bool] | None = None,
        description: str | None = None,
    ) -> None:
        """While a run of `task` is open, start `start` after each age (brief, D46)."""
        entry: Data = {"display": display(title, description)}
        entry["reminder"] = {"task": task.name, "after": list(after), "start": start.name}
        if when is not None:
            entry["when"] = given(when).data
        self.rules[self.new_name(name, self.rules, "rule")] = entry
        self.where[f"rules.{name}"] = called_from()

    # Closing (brief, D10).

    def close_reason(
        self, name: str, title: str, roles: Sequence[str], description: str | None = None
    ) -> None:
        """A reason a person holding one of `roles` may close the case with."""
        entry: Data = {"display": display(title, description), "roles": list(roles)}
        self.close_reasons[self.new_name(name, self.close_reasons, "close reason")] = entry
        self.where[f"close_reasons.{name}"] = called_from()

    def closes_when(self, *milestones: Milestone) -> None:
        """The case closes once all `milestones` are reached: said once."""
        if self.closing:
            raise ValueError(f"{self.name} already closes when {', '.join(self.closing)}")
        self.closing = [milestone.name for milestone in milestones]
        self.where["closes_when"] = called_from()

    # Writing.

    def add(self, name: str, entry: Data) -> None:
        self.steps[self.new_name(name, self.steps, "step")] = entry
        self.where[f"steps.{name}"] = called_from()

    def new_name(self, name: str, taken: Mapping[str, object], what: str) -> str:
        """`name`, refused if this case already has a `what` of that name: a second entry would
        replace the first without a word."""
        if name in taken:
            raise ValueError(
                f"{self.name} already has a {what} named {name}: give this one another"
            )
        return name

    def definition(self) -> Data:
        """The case's JSON, as plain data, its keys in the order the format writes them."""
        data: Data = {"case": self.name, "display": self.display}
        for key, value in (
            ("fields", self.fields),
            ("milestones", self.milestones),
            ("steps", self.steps),
            ("sequence", self.order),
            ("rules", self.rules),
            ("events", self.events),
            ("close_reasons", self.close_reasons),
            ("closes_when", self.closing),
        ):
            if value or key == "steps":
                data[key] = value
        if self.stays_open is not None:
            data["stays_open"] = self.stays_open
        if self.forgetting is not None:
            data["forgetting"] = self.forgetting
        return data


def starting(
    requires: Sequence[Step | Milestone],
    when: Expr[bool] | None,
    automatic: bool | None,
    proposed_by: Sequence[str] | None,
    repeatable: bool | None,
    reaches: Sequence[Milestone] | None,
) -> Data:
    """When a step may start, and what it reaches when it completes."""
    data: Data = {}
    if requires:
        data["requires"] = [entry.name for entry in requires]
    if when is not None:
        data["when"] = given(when).data
    if automatic is not None:
        data["automatic"] = automatic  # False: it starts only when proposed
    if proposed_by is not None:
        data["proposed_by"] = list(proposed_by)
    if repeatable is not None:
        data["repeatable"] = repeatable
    if reaches is not None:
        data["reaches"] = [milestone.name for milestone in reaches]
    return data


def calling(inputs: Mapping[str, Expr[Any]] | None) -> Data:
    """What a step gives what it calls: each input, read from the case file."""
    if not inputs:
        return {}
    return {"inputs": {key: given(value).data for key, value in inputs.items()}}


def guarded(approval: Approval | None, max_age: Mapping[str, str] | None) -> Data:
    """A call's approval, and how old each fact it reads may be (brief, D18)."""
    data: Data = {}
    if approval is not None:
        data["approval"] = approved_by(approval)
    if max_age is not None:
        data["max_age"] = dict(max_age)
    return data


def answer(outcome: Outcome) -> Data:
    """An outcome's JSON: what people read, the fields its form sets, the milestones it reaches."""
    data: Data = {"display": display(outcome.title, outcome.description)}
    if outcome.sets:
        data["sets"] = [field_name(field) for field in outcome.sets]
    if outcome.reaches:
        data["reaches"] = [milestone.name for milestone in outcome.reaches]
    return data


def approved_by(approval: Approval) -> Data:
    """An approval's JSON: when, who, how many, and the reason people read."""
    data: Data = {}
    if approval.when is not None:
        data["when"] = given(approval.when).data
    data["roles"] = list(approval.roles)
    if approval.count is not None:
        data["count"] = approval.count  # how many distinct people (brief, D47)
    data["display"] = {"reason": approval.reason}
    return data


def acting(then: Then) -> Data:
    """A rule's `then`: fields set, milestones reached, steps started and stopped."""
    data: Data = {}
    if then.set:
        data["set"] = {field_name(field): given(value).data for field, value in then.set}
    if then.reach:
        data["reach"] = [milestone.name for milestone in then.reach]
    if then.start:
        data["start"] = [step.name for step in then.start]
    if then.stop:
        data["stop"] = [step.name for step in then.stop]
    return data


def carried(value: Payload) -> Data:
    """A payload field's JSON: its type, what people read, and a declared untrusted source."""
    data: Data = {**value.kind.declared, "display": display(value.title, value.description)}
    if value.source is not None:
        data["source"] = value.source
    return data
