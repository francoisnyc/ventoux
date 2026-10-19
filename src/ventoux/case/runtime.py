"""The case runtime: one event in; the case's new state and the commands to carry out out.

`decide` reads no clock, randomness or I/O, so the same events give the same decisions in memory
and, in layer 8c, inside a Temporal workflow on replay. A driver carries out the commands
(`case/memory.py` in tests) and feeds back what happened as the next event.
See docs/layers/08-case.md.
"""

import copy
from collections.abc import Mapping
from typing import Literal

from pydantic import ValidationError

from ventoux.case.admission import (
    ProposalRefused,
    RetryRefused,
    StepStopped,
    ended_requirement,
    holds,
    latest_run,
    proposal_refusal,
    requirements_met,
)
from ventoux.case.answers import AnswerRefused, decided_by, judge_approval, judge_task
from ventoux.case.approvals import ask, asked_anyway, follow, lapsed, needs_approval
from ventoux.case.called import called
from ventoux.case.closing import (
    begin_closing,
    close_held,
    close_when_reached,
    refuse_to_close,
    settle,
)
from ventoux.case.definition import (
    ActivityStep,
    CallStep,
    CaseDefinition,
    DeclaredEvent,
    PlanStep,
    TaskStep,
    WaitStep,
    WorkflowStep,
    form_fields,
    rule_fields,
)
from ventoux.case.forgetting import forget
from ventoux.case.freshness import Stale, ago, as_said, refuse_unless_whole, stale_facts
from ventoux.case.rules import fire_rules, reach, retry_rule
from ventoux.case.sequence import requirements
from ventoux.case.state import (
    CLOSING,
    Answered,
    CaseState,
    CloseAsked,
    Command,
    Completed,
    Event,
    Failed,
    ForgetApproved,
    GivenApproval,
    Obtained,
    OpenApproval,
    Opened,
    PlanCancelled,
    Proposed,
    Retried,
    RuleStart,
    Schedule,
    Sent,
    Shown,
    StartPlan,
    StartWorkflow,
    StepRun,
    WorkflowCancelled,
)
from ventoux.case.stopping import stop_children
from ventoux.case.types import expression_problem
from ventoux.case.visibility import may_see, seen_by
from ventoux.case.writers import OPENER, read_sources, untrusted_of
from ventoux.core.approval import inputs_digest
from ventoux.core.before_activity import (
    InputRefused,
    Steering,
    checked_inputs,
    given_as_reference,
    one_line,
)
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import ActivityContract, Contract
from ventoux.core.expressions import (
    Expression,
    ExpressionError,
    ReferenceType,
    a_kind,
    evaluate,
    render,
)
from ventoux.core.expressions.check import a_type
from ventoux.core.form import fits
from ventoux.core.output_sources import is_held, output_sources
from ventoux.core.person import identifier_problem
from ventoux.core.plan import APPROVE
from ventoux.core.provenance import NoSources, Sourced, fields_read, provenance
from ventoux.core.references import unregistered
from ventoux.core.roles import role_that_counts
from ventoux.core.sensitive import Sensitive, plain
from ventoux.core.sensitive_inputs import kept_sensitive, reads_sensitive

# The outcome of an activity that did what it was asked, or of a plan that succeeded.
DONE = "done"
# The outcome of a plan step whose plan ended in a failed final state (brief, D28).
FAILED = "failed"


class CaseRefused(Exception):
    """A case the engine won't open: what is wrong with its first values."""


class StoppedRefresh(StepStopped):
    """A step needs a fact whose refresh a rule stopped: it fails, and an operator's retry of
    its run fetches the fact again; a person's proposal of it is refused (brief, D40)."""

    def __init__(self, stopped: str, entry: str, refresh: str) -> None:
        super().__init__(f"{stopped}; retry {entry} to fetch it again")
        self.stopped = stopped  # what is wrong, without what to do
        self.refresh = refresh  # the stopped refresh's run, such as `check_order#2`

    def to_proposer(self, step: str) -> str:
        """The refusal a person proposing `step` reads: nothing failed, so nothing is retried."""
        return f"{self.stopped}; propose {step} again once {self.refresh} has landed"


class ShownRefused(Exception):
    """A record shown that the case won't record, because it couldn't have been: why."""


class EventRefused(Exception):
    """An event from outside the case won't take: why, naming the event and its sender, never a
    value it carries (brief, D41)."""


def decide(
    case: CaseDefinition, catalog: Catalog, state: CaseState, event: Event
) -> tuple[CaseState, list[Command]]:
    """The case's state after `event`, and the activities to schedule. A refused event raises
    (`AnswerRefused`, `ProposalRefused`, `CaseRefused`, `TimeRefused`) and changes nothing; a step the engine
    can't run fails, and the case needs attention (brief, D17)."""
    refuse_unless_whole(event.at)  # time is only ever event data, so it is checked first
    state = copy.deepcopy(state)  # the state passed in is never changed
    state.started_by_rules.clear()  # a guard for this decision only (brief, D39)
    commands: list[Command] = []
    was_open = state.phase == "open"
    if isinstance(event, Opened):
        open_case(case, catalog, state, event)
    elif isinstance(event, Answered):
        if state.phase != "open":
            raise AnswerRefused(f"the case is {state.phase}: nothing waits for an answer")
        answer(case, catalog, state, event)
    elif isinstance(event, Proposed):
        propose(case, catalog, state, event, commands)
    elif isinstance(event, Failed):
        failed(state, event)
    elif isinstance(event, PlanCancelled):
        plan_cancelled(state, event)
    elif isinstance(event, WorkflowCancelled):
        workflow_cancelled(state, event)
    elif isinstance(event, Retried):
        retry(case, catalog, state, event, commands)
    elif isinstance(event, Shown):
        record_shown(case, catalog, state, event)
    elif isinstance(event, Sent):
        receive(case, catalog, state, event)
    elif isinstance(event, ForgetApproved):
        forget(case, catalog, state, event)
    elif isinstance(event, CloseAsked):
        role = refuse_to_close(case, catalog, state, event)
        state.history.append(f"{event.by} closed the case as {event.reason}, as {role}")
        why = f"closed as {event.reason} by {event.by}"
        begin_closing(state, why, f"{event.reason}, by {event.by}")
    else:
        complete(case, catalog, state, event)
    close_when_reached(case, state)
    if state.phase == "open":
        admit(case, catalog, state, commands, event.at)  # nothing new starts once closing
        close_when_reached(case, state)  # a rule may have reached the last of closes_when
    if was_open and state.phase == "closing":
        stop_children(case, catalog, state, commands)
    # Moments left because the case is no longer open: each rule on them says it wasn't applied
    # (brief, D38).
    fire_rules(case, catalog, state, commands, event.at)
    left_unstarted(case, state)  # none is taken up once the case no longer decides (brief, D38)
    state.started_by_rules.clear()
    settle(case, state)
    return state, commands


def receive(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Sent) -> None:
    """An event from outside reaches the case (brief, D41)."""
    if event.event not in case.events:
        known = listed(list(case.events)) if case.events else "none"
        raise EventRefused(f"{event.event} is not an event of {case.case}: its events are {known}")
    declared = case.events[event.event]
    role = sender_role(catalog, event.event, declared, event)  # who sent it, before what it carries
    refuse_payload(event.event, declared, event.payload)
    # An event is never a way back into a closed case (brief, D41). On Temporal its workflow has
    # ended, so the client's send is refused first; this holds on nothing it did.
    if state.phase == "closed":
        raise EventRefused("the case is closed: it takes no more events")
    if state.phase == "closing":
        # Refused, and the case flagged: a signal has no reply, so nobody would hear of it
        # otherwise (brief, D41). Nothing it carries lands; no rule hears it.
        sender = event.by.removeprefix("system:")
        state.history.append(
            f"refused {event.event} from {sender}: the case is closing, so it takes no more events"
        )
        flag(
            state,
            f"{event.event} from {sender} arrived while the case was closing, and was refused",
        )
        return
    arrive(case, state, event, role)


def arrive(case: CaseDefinition, state: CaseState, event: Sent, role: str | None) -> None:
    """The event has arrived: an entry of its own, each value it carries in the case file as
    `<event>.<field>`, from its sender and the field's declared mark, obtained now and by this
    arrival (brief, D12) (brief, D33) (brief, D41). The arrival is a moment for rules."""
    name = event.event
    state.arrived[name] = state.arrived.get(name, 0) + 1
    entry = f"{name}#{state.arrived[name]}"
    # A system's own name, or the person who sent it: trusted as that sender is (brief, D41).
    sender = event.by if event.by.startswith("system:") else f"person:{event.by}"
    given: list[str] = []
    for field, declared in case.events[name].payload.items():
        value = f"{name}.{field}"
        state.values[value] = event.payload[field]
        # A mark adds distrust, never removes it, whoever sends it (brief, D12).
        state.sources[value] = frozenset(
            {sender} | ({declared.source} if declared.source else set())
        )
        state.obtained[value] = Obtained(event.at, entry)
        given.append(f"{field} from {', '.join(sorted(state.sources[value]))}")
    who = (
        f"from {event.by.removeprefix('system:')}" if role is None else f"by {event.by}, as {role}"
    )
    giving = f", giving {'; '.join(given)}" if given else ""
    state.history.append(f"{entry} {who}{giving}")
    state.moments.append(f"event {name}")
    # Each wait open for it is done: only an arrival after a wait opens ends it (brief, D41).
    for run in state.runs:
        waits = case.steps[run.step]
        if run.status == "open" and isinstance(waits, WaitStep) and waits.event == name:
            run.status = "done"
            del state.waiting[run.entry]
            state.history.append(f"{run.entry} done: {entry} arrived")
            reach(state, waits.reaches)


def sent_by(declared: DeclaredEvent) -> str:
    """Who sends an event, as the inbox says it: `from portal`, `by support or fraud`."""
    if declared.sent_by.system is not None:
        return f"from {declared.sent_by.system}"
    return f"by {' or '.join(declared.sent_by.roles or ())}"


def sender_role(catalog: Catalog, name: str, declared: DeclaredEvent, event: Sent) -> str | None:
    """The role that lets a person send the event, None if a system sends it; or `EventRefused`.
    One sender, as declared: its system, or a person holding one of its roles, checked as for a
    close reason (brief, D22) (brief, D41)."""
    sent_by = declared.sent_by
    if sent_by.system is not None:
        if event.by != f"system:{sent_by.system}":
            raise EventRefused(
                f"{name} is sent by {sent_by.system}, and this one comes from {event.by}"
            )
        return None
    assert sent_by.roles is not None  # one sender: a system or people (`SentBy`)
    roles = " or ".join(sent_by.roles)
    if event.by.startswith("system:"):
        raise EventRefused(f"{name} is sent by {roles}, and this one comes from {event.by}")
    # Who sent it is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise EventRefused(wrong)
    role = role_that_counts(sent_by.roles, event.roles, catalog.roles)
    if role is None:
        counted = sorted(r for r in event.roles if r in catalog.roles)
        known = listed(counted) if counted else "no role"
        raise EventRefused(f"{name} is sent by {roles}, and {event.by} has {known}")
    return role


def refuse_payload(name: str, declared: DeclaredEvent, payload: Mapping[str, object]) -> None:
    """Refuse a payload that isn't exactly the declared one: every field given, each of its type,
    and nothing else. The type, never the value: a refusal reaches people who may not see it
    (brief, D30) (brief, D41)."""
    problems = [
        f"{name}'s payload has no {field}" for field in declared.payload if field not in payload
    ]
    fields = listed(list(declared.payload)) if declared.payload else "none"
    problems += [
        f"{name}'s payload has no field {given}: its fields are {fields}"
        for given in payload
        if given not in declared.payload
    ]
    problems += [
        f"{name}.{field} is {a_type(kind.declared)}, and the event gives {a_kind(payload[field])}"
        for field, kind in declared.payload.items()
        if field in payload and not fits(payload[field], kind.declared)
    ]
    if problems:
        raise EventRefused("\n".join(problems))


def record_shown(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Shown) -> None:
    """Record that `event.by` was shown the record behind a reference: its system and reference,
    never its content (brief, D16). Refused if it couldn't have happened (brief, D30)."""
    if (wrong := identifier_problem(event.by)) is not None:
        raise ShownRefused(wrong)
    if state.phase == "closed":
        raise ShownRefused("the case is closed: nothing records it any more")
    if event.field not in case.fields:
        raise ShownRefused(f"{event.field} is not a field of {case.case}")
    declared = case.fields[event.field].declared
    if not isinstance(declared, ReferenceType):
        raise ShownRefused(f"{event.field} is not a reference: there is no record to show")
    if not may_see(case, event.field, event.roles, catalog.roles):
        needs = " or ".join(seen_by(case, event.field))
        raise ShownRefused(f"{event.by} can't see {event.field}: it needs {needs}")
    if event.field not in state.values:
        raise ShownRefused(f"{event.field} is not set: there is no record to show")
    reference = state.values[event.field]
    state.history.append(f"{event.by} was shown {event.field} ({declared.system} {reference})")


def open_case(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Opened) -> None:
    """The case file's first values, each of its field's type and saying where it came from:
    the person who opened the case, or the system that did (brief, D12)."""
    if event.by is not None and (wrong := identifier_problem(event.by)) is not None:
        raise CaseRefused(wrong)
    refuse_to_open(case, catalog, event.file)
    refuse_unless_wrapped(case, event.file, CaseRefused)
    state.opened_by = event.by
    origin = OPENER if event.by is None else f"person:{event.by}"
    for name, value in event.file.items():
        state.values[name] = value
        state.sources[name] = marked(case, name, origin)
        state.obtained[name] = Obtained(event.at, None)  # from the opening, by no step run
    state.history.append(f"opened by {event.by or OPENER}, with {listed(sorted(event.file))}")
    state.moments.append("opened")


def refuse_to_open(case: CaseDefinition, catalog: Catalog, file: Mapping[str, object]) -> None:
    """Refuse a case whose references name systems nobody registered, or whose fields are
    declared untrusted with labels nobody registered, and first values that aren't the case's
    fields, of their types, given at the opening."""
    setters = form_fields(case)
    computed = rule_fields(case)
    declared_types = {name: field.declared for name, field in case.fields.items()}
    problems = unregistered(declared_types, catalog.systems)
    # A label the engine doesn't know is refused, never taken as a new kind of untrusted
    # (brief, D12) (brief, D35).
    problems += [
        f"{name} is declared {field.source}, a label nobody registered"
        for name, field in case.fields.items()
        if field.source is not None
        and field.source.removeprefix("untrusted:") not in catalog.labels
    ]
    # So for what an event says of itself: its sender and its marks (brief, D30) (brief, D41).
    for name, event in case.events.items():
        if event.sent_by.system is not None and event.sent_by.system not in catalog.systems:
            problems.append(f"{name} is sent by {event.sent_by.system}, a system nobody registered")
        problems += [
            f"{name}.{field} is declared {carried.source}, a label nobody registered"
            for field, carried in event.payload.items()
            if carried.source is not None
            and carried.source.removeprefix("untrusted:") not in catalog.labels
        ]
    for name, value in file.items():
        if name not in case.fields:
            fields = listed(sorted(case.fields))
            problems.append(f"{name} is not a field of {case.case}: its fields are {fields}")
        # One source per field: a person's form sets it, so the opening never gives it.
        elif name in setters:
            problems.append(
                f"{name} is set by a person in {setters[name]}, never given at the opening"
            )
        elif name in computed:
            problems.append(
                f"{name} is set by rules, in {computed[name]}, never given at the opening"
            )
        elif not fits(plain(value), declared := case.fields[name].declared):
            # The type, never the value: refusals reach people who may not see it (brief, D30).
            problems.append(f"{name} is {a_type(declared)}, and the opening gives {a_kind(value)}")
    if problems:
        raise CaseRefused("\n".join(problems))


def refuse_unless_wrapped(
    case: CaseDefinition,
    values: Mapping[str, object],
    refused: type[CaseRefused] | type[AnswerRefused],
) -> None:
    """Refuse a sensitive field's value that arrived unwrapped: it has already crossed in plain
    text, so the case says so loudly. Checked here, on nothing the client did (brief, D31)."""
    for name, value in values.items():
        if name in case.fields and case.fields[name].sensitive and not isinstance(value, Sensitive):
            raise refused(
                f"{name} is sensitive and was given in plain text: send it through "
                "ventoux.temporal.cases, which encrypts it"
            )


def kept(case: CaseDefinition, name: str, value: object) -> object:
    """A form's value as the case file keeps it: wrapped for a sensitive field, plain otherwise.
    The client wraps every value of a form, since it can't tell which are sensitive."""
    return value if name in case.fields and case.fields[name].sensitive else plain(value)


def marked(case: CaseDefinition, name: str, origin: str) -> frozenset[str]:
    """Where a value of the field `name` came from: `origin`, and the field's declared mark. A
    mark adds distrust, never removes it (brief, D12)."""
    declared = case.fields[name].source if name in case.fields else None
    return frozenset({origin} | ({declared} if declared else set()))


def answer(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Answered) -> None:
    """Record a person's answer, once judged (brief, D23); or `AnswerRefused`."""
    # Who answered is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise AnswerRefused(wrong)
    found = open_entry(state, event.entry)
    if isinstance(found, StepRun) and isinstance(waits := case.steps[found.step], WaitStep):
        # Only its event ends it, sent by its sender: nobody answers it (brief, D41).
        raise AnswerRefused(f"{found.entry} waits for {waits.event}: it is sent, never answered")
    if isinstance(found, StepRun):
        answer_task(case, catalog, state, found, event)
    else:
        answer_approval(case, catalog, state, found, event)


def open_entry(state: CaseState, entry: str) -> StepRun | OpenApproval:
    """The open task run or approval `entry` names; a step's name names its open one."""
    for run in state.runs:
        if run.status == "open" and entry in (run.entry, run.step):
            return run
    for approval in state.approvals.values():
        if entry in (approval.entry, approval.step):
            return approval
    if entry in state.withdrawn:
        raise AnswerRefused(f"{entry} was withdrawn: {state.withdrawn[entry]}")
    # Which it was, as on a plan's waits (layer 6): an entry that has been open is closed (a
    # double click, a late answer); one that hasn't isn't open (an answer sent too early).
    if has_been_open(state, entry):
        raise AnswerRefused(f"{entry} is closed")
    raise AnswerRefused(f"{entry} isn't open")


def has_been_open(state: CaseState, entry: str) -> bool:
    """Whether `entry` names a step run the case has had, or an approval it has asked for."""
    if any(run.entry == entry for run in state.runs):
        return True
    step, _, count = entry.partition(".approval#")  # `pay.approval#2`: `pay`, `2`
    return count.isdigit() and 1 <= int(count) <= state.asked.get(step, 0)


def propose(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    event: Proposed,
    commands: list[Command],
) -> None:
    """Start the step a person proposes, if they may and admission accepts it; or
    `ProposalRefused`. The engine decides, a person only asks."""
    # Who proposed is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise ProposalRefused(wrong)
    if state.phase != "open":
        raise ProposalRefused(f"the case is {state.phase}: nothing starts")
    if close_held(case, state):
        raise ProposalRefused(held_close_refusal(case, state))
    if event.step not in case.steps:
        raise ProposalRefused(f"{event.step} is not a step of {case.case}")
    step = case.steps[event.step]
    if not step.proposed_by:
        # A step that doesn't start by itself and names nobody is started only by a rule: the
        # definition is refused otherwise (brief, D39).
        how = "starts by itself" if step.automatic else "is started only by a rule"
        raise ProposalRefused(f"{event.step} {how}: nobody proposes it")
    role = role_that_counts(step.proposed_by, event.roles, catalog.roles)
    if role is None:
        counted = sorted(r for r in event.roles if r in catalog.roles)
        known = listed(counted) if counted else "no role"
        raise ProposalRefused(
            f"{event.step} is proposed by {' or '.join(step.proposed_by)}, and {event.by} has "
            f"{known}"
        )
    refusal = proposal_refusal(case, event.step, requirements(case)[event.step], state)
    if refusal is not None:
        raise ProposalRefused(refusal)
    # Its expressions checked over the case's types before any is read (brief, D35).
    if (problem := expression_problem(case, catalog, event.step)) is not None:
        raise ProposalRefused(problem)
    state.history.append(f"{event.by} proposed {event.step} as {role}")
    state.proposers[event.step] = event.by  # never its approver (brief, D25)
    # Hers is the proposal now: a rule's start whose approval was withdrawn is over (brief, D39).
    state.proposed_by_rules.pop(event.step, None)
    # Freshness first, before the condition, the approval and the start, as for any start
    # (brief, D33): a stale read is fetched again and the proposal waits for it; a fact nothing
    # can fetch again refuses the proposal, saying why (brief, D39). A refusal changes nothing.
    if isinstance(step, CallStep | PlanStep):  # a task or a wait needs no fact fresh
        try:
            fresh = refresh_stale(case, catalog, state, event.step, step, event.at, commands)
        except StoppedRefresh as stopped:
            raise ProposalRefused(stopped.to_proposer(event.step)) from None
        except StepStopped as stale:
            raise ProposalRefused(str(stale)) from None
        if fresh != "fresh":
            state.waiting_to_start.append(event.step)  # admission takes it up once it lands
            return
    if step.when is not None:
        try:
            decided = holds(step.when, state.values, f"{event.step}'s condition")
        except StepStopped as unreadable:
            raise ProposalRefused(str(unreadable)) from None  # fail closed: nothing starts
        if not decided:
            raise ProposalRefused(f"{event.step} doesn't run now: {render(step.when)} is false")
    try:
        start(case, catalog, state, event.step, step, commands)
    except (StepStopped, InputRefused, NotInCatalog) as error:
        # Accepted, and it can't be made: the run fails and waits for a person, as when the step
        # starts by itself, never raised out of the decision (brief, D17) (brief, D39).
        fail(state, event.step, str(error))


def proposed_by_a_rule(state: CaseState, asked: RuleStart) -> None:
    """The step's coming run is the rule's proposal, with what its condition read, kept with the
    run until it starts (brief, D38) (brief, D39). A person's earlier proposal, whose approval was
    withdrawn, is over."""
    state.proposed_by_rules[asked.step] = asked
    state.proposers.pop(asked.step, None)


def left_unstarted(case: CaseDefinition, state: CaseState) -> None:
    """Record each start a rule asked for that no admission took up: the case stopped deciding
    first, as when a retried rule reaches the last `closes_when` milestone. Never dropped in
    silence (brief, D39)."""
    for asked in state.rule_starts:
        if case.closes_when and all(m in state.milestones for m in case.closes_when):
            why = nothing_new(case, state)
        else:
            why = f"the case is {state.phase}, so nothing new starts"
        state.history.append(f"{asked.entry} on {asked.moment}: {asked.step} not started: {why}")
    state.rule_starts.clear()


def nothing_new(case: CaseDefinition, state: CaseState) -> str:
    """Why nothing new starts once every `closes_when` milestone is reached: the case closes,
    now or once what failed is retried (brief, D34)."""
    if holding(state):
        return held_close_refusal(case, state)
    verb = "is" if len(case.closes_when) == 1 else "are"
    return f"{listed(list(case.closes_when))} {verb} reached, so the case closes and nothing new starts"


def holding(state: CaseState) -> list[str]:
    """The failed runs and rules the close waits for, as their entries: each waits for a person
    (brief, D26) (brief, D38)."""
    runs = [run.entry for run in state.runs if run.status in ("failed", "retrying")]
    return runs + [firing.entry for firing in state.firings if firing.status == "failed"]


def held_close_refusal(case: CaseDefinition, state: CaseState) -> str:
    """Why nothing starts while a failed run holds the close: what was reached, and what the case
    waits for before it closes (brief, D34)."""
    reached = listed(list(case.closes_when))
    verb = "is" if len(case.closes_when) == 1 else "are"
    failed = holding(state)
    retried = "is" if len(failed) == 1 else "are"
    return (
        f"{reached} {verb} reached, so the case closes once {listed(failed)} {retried} retried, "
        "or a person closes it: nothing new starts"
    )


def answer_task(
    case: CaseDefinition, catalog: Catalog, state: CaseState, run: StepRun, event: Answered
) -> None:
    """The task run is done; its outcome, and the fields its form sets, land in the case file."""
    step = case.steps[run.step]
    assert isinstance(step, TaskStep)  # only a task's run is ever open
    role = judge_task(case, catalog, run.entry, run.step, step, event)
    refuse_unless_wrapped(case, event.form or {}, AnswerRefused)
    run.status = "done"
    del state.waiting[run.entry]
    who = f"person:{event.by}"
    # The latest answer is the outcome (brief, D9), and a form's values replace earlier ones.
    state.values[f"{run.step}.outcome"] = event.outcome
    state.sources[f"{run.step}.outcome"] = frozenset({who})
    state.obtained[f"{run.step}.outcome"] = Obtained(event.at, None)  # from a person, not a run
    sets = step.outcomes[event.outcome].sets
    for name in sets:
        state.values[name] = kept(case, name, (event.form or {})[name])
        state.sources[name] = marked(case, name, who)
        state.obtained[name] = Obtained(event.at, None)
    setting = f", setting {listed(list(sets))}" if sets else ""
    state.history.append(f"{event.by} answered {run.entry} {event.outcome} as {role}{setting}")
    state.history.append(f"{run.entry} done")
    state.moments.append(f"answered {run.step}")  # each answer, whatever the outcome (brief, D39)
    reach(state, (*step.outcomes[event.outcome].reaches, *step.reaches))


def answer_approval(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    approval: OpenApproval,
    event: Answered,
) -> None:
    """An approval given, tied to the inputs it saw; or a rejection: the step won't run."""
    step = case.steps[approval.step]
    assert isinstance(step, CallStep)  # only an activity or a workflow is asked for one
    role = judge_approval(case, catalog, state, approval.entry, approval.step, step, event)
    del state.approvals[approval.step]
    del state.waiting[approval.entry]
    state.history.append(f"{event.by} answered {approval.entry} {event.outcome} as {role}")
    if event.outcome == APPROVE:
        try:
            digest = inputs_digest(step.inputs, state.values)
        except ExpressionError as error:
            # Fail closed: an approval of inputs nobody can read approves nothing.
            fail(state, approval.step, f"the inputs of {approval.step} can't be read: {error}")
            return
        state.given[approval.step] = GivenApproval(approval.entry, event.by, digest, approval.seen)
        return
    latest = latest_run(state, approval.step)
    if latest is not None and latest.status == "retrying":
        # A rejected rescue resolves nothing: the failed run may or may not have acted, so it
        # needs attention again, as the run it is, never a new one (brief, D17) (brief, D26).
        latest.status = "failed"
        latest.reason = (
            f"{event.by} rejected {approval.entry}, the approval of its retry: retry it to ask "
            "again, or close the case"
        )
        state.history.append(
            f"{latest.entry} won't run: {event.by} rejected {approval.entry}, so it needs "
            "attention again"
        )
        return
    # A rejection is an outcome: the step doesn't run (brief, D23).
    entry = next_entry(state, approval.step)
    proposal_spent(state, approval.step)  # the proposed run is over
    state.runs.append(StepRun(entry, approval.step, "rejected", started=False))
    state.history.append(f"{entry} won't run: {event.by} rejected {approval.entry}")


def complete(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Completed) -> None:
    """A scheduled activity, a workflow or a plan finished: its outcome lands in the case file,
    tagged with the contract (or plan) that declares it, and so does an activity's or a workflow's
    output, each field tagged with its contract's source (brief, D29)."""
    run = next(run for run in state.runs if run.entry == event.entry)
    step = case.steps[run.step]
    assert isinstance(step, CallStep | PlanStep)  # only an activity, a workflow or a plan completes
    if isinstance(step, PlanStep):
        declares, problem = step.plan, plan_outcome_problem(step, event)
    else:
        contract = called(catalog, step)
        declares, problem = contract.reference, outcome_problem(contract, event)
    if problem is not None:
        failed(state, Failed(event.entry, problem, at=event.at))
        return
    run.status = "done"
    state.values[f"{run.step}.outcome"] = event.outcome
    # Trusted: the contract, owned by the platform team, or the reviewed plan, declares the
    # outcomes (brief, D12).
    state.sources[f"{run.step}.outcome"] = frozenset({f"system:{declares}"})
    state.obtained[f"{run.step}.outcome"] = Obtained(event.at, run.entry)  # by this run
    if event.outcome != DONE:
        state.history.append(f"{run.entry} gave {event.outcome}")
        flag_if_stopping(state, run)
        return  # a step's milestones are reached only when it is done with `done`
    given = {} if isinstance(step, PlanStep) else write_outputs(state, run.step, contract, event)
    giving = "; ".join(f"{name} from {given[name]}" for name in sorted(given))
    state.history.append(f"{run.entry} done{f', giving {giving}' if giving else ''}")
    reach(state, step.reaches)
    flag_if_stopping(state, run)


def flag_if_stopping(state: CaseState, run: StepRun) -> None:
    """Flag a run that completed though a close or a stop was asked: what it did stands, and a
    person decides on a reversal (brief, D10) (brief, D40)."""
    if state.phase == "closing":
        flag(state, f"{run.entry} completed after the close was requested")
    elif run.stop_requested:
        flag(state, f"{run.entry} completed after its stop was requested by {run.stop_requested}")


def write_outputs(
    state: CaseState, step: str, contract: Contract, event: Completed
) -> dict[str, str]:
    """Each field the contract declares lands in the case file as `<step>.<field>`, tagged with
    the source the contract declares for it, never one the activity sends back (brief, D29).
    Gives each field's source, for the history."""
    # Pydantic: `model_validate` checks a dict against the model's fields and builds the model; a
    # field the model doesn't declare is left out, so it never reaches the case file.
    given = contract.output.model_validate(event.output)
    sources = output_sources(contract.output)
    for name, source in sources.items():
        state.values[f"{step}.{name}"] = getattr(given, name)
        state.sources[f"{step}.{name}"] = frozenset({source})
        state.obtained[f"{step}.{name}"] = Obtained(event.at, event.entry)  # by this run
    return sources


def plan_outcome_problem(step: PlanStep, event: Completed) -> str | None:
    """Why how the plan ended can't be taken, or None: a plan ends done (it succeeded) or
    `failed` (a failed final state), and gives no output to the case (brief, D28)."""
    if event.outcome not in (DONE, FAILED):
        return f"{step.plan} ended with {event.outcome}: a plan ends done or failed"
    return None


def outcome_problem(contract: Contract, event: Completed) -> str | None:
    """Why what the activity gave can't be taken, or None: an outcome its contract doesn't
    declare, or an output its contract doesn't describe. Fail closed: neither is read as done."""
    if event.outcome != DONE:
        # A workflow declares no outcomes: its business result is in its output (brief, D29).
        outcomes = contract.outcomes if isinstance(contract, ActivityContract) else ()
        if event.outcome in outcomes:
            return None
        declared = ", ".join(outcomes) or "none"
        return (
            f"{contract.reference} gave the outcome {event.outcome}, which its contract doesn't "
            f"declare: its outcomes are {declared}"
        )
    try:
        # Pydantic: `model_validate` checks a dict against the model's fields, or raises.
        given = contract.output.model_validate(event.output)
    except ValidationError as error:
        return (
            f"{contract.reference} gave an output its contract doesn't declare: {one_line(error)}"
        )
    # Checked again here, on nothing registration did: the case file holds values exactly, so a
    # value it can't hold fails the step, and nothing the step gave lands (brief, D20).
    for name in contract.output.model_fields:
        value = getattr(given, name)
        if not is_held(value):
            return (
                f"{contract.reference} gave {name} as {a_kind(value)}, which the case file "
                "can't hold exactly (brief, D20)"
            )
    return None


def failed(state: CaseState, event: Failed) -> None:
    """A scheduled activity failed after its retries: its run fails, and waits for a person. While
    the case is closing, nobody will retry it: it is cancelled, and the case is flagged."""
    run = next(run for run in state.runs if run.entry == event.entry)
    run.status, run.reason = "failed", event.reason
    # A run that fails after its stop was asked needs attention like any other: nobody knows what
    # it did, and a later run would get a new key (brief, D17) (brief, D40).
    after = f" after its stop was requested by {run.stop_requested}" if run.stop_requested else ""
    state.history.append(f"{run.entry} failed{after}: {event.reason}")
    if state.phase == "closing":
        run.status = "cancelled"
        flag(state, f"{run.entry} failed after the close was requested: {event.reason}")


def plan_cancelled(state: CaseState, event: PlanCancelled) -> None:
    """A plan stopped by the close or by a rule has ended: its step run is cancelled, and the case
    can close. Each activity in it that finished or failed after the stop flags the case, as a
    step's run would (brief, D10): a payment made after a close never disappears into
    "cancelled" (brief, D28) (brief, D40)."""
    run = next(run for run in state.runs if run.entry == event.entry)
    if run.status != "running":
        return  # it ended before the stop reached it: what it gave is already recorded
    run.status = "cancelled"
    state.history.append(f"{run.entry} cancelled: {stopped_because(run)}")
    for ended in event.after_stop:
        flag(state, f"{run.entry}: {ended}")


def workflow_cancelled(state: CaseState, event: WorkflowCancelled) -> None:
    """A cancellable workflow step, asked to stop, ended cancelled: its run is cancelled, and the
    case is flagged, since what it did before the request stands (brief, D40)."""
    run = next(run for run in state.runs if run.entry == event.entry)
    if run.status != "running":
        return  # it ended before the cancellation reached it: what it gave is already recorded
    if not run.stop_requested and state.phase != "closing":
        # Fail closed: the case asked nothing of it, so nothing explains it; never read as a close.
        why = "it ended cancelled, though the case asked nothing of it: retry it, or close the case"
        failed(state, Failed(run.entry, why, at=event.at))
        return
    run.status = "cancelled"
    state.history.append(f"{run.entry} cancelled: {stopped_because(run)}")
    if run.stop_requested:
        flag(state, f"{run.entry} cancelled after its stop was requested by {run.stop_requested}")
    else:
        flag(state, f"{run.entry} cancelled after the close was requested")


def stopped_because(run: StepRun) -> str:
    """Why a run asked to stop ended cancelled: a rule's stop, naming its entry, or the close."""
    return f"stopped by {run.stop_requested}" if run.stop_requested else CLOSING


def flag(state: CaseState, why: str) -> None:
    """Flag the case for a person: something happened that a close didn't stop (brief, D10)."""
    state.flags.append(why)
    state.history.append(f"flagged: {why}")


def fail(state: CaseState, name: str, reason: str) -> None:
    """The step's coming run fails before it is scheduled, with the reason (brief, D17). An
    approval given for it goes with the failed run, which a retry keeps (brief, D26): left
    given, it would admit the step again in the same decision, and fail it for ever."""
    run = coming_run(state, name, "failed")
    run.reason = reason
    given = state.given.pop(name, None)
    if given is not None:
        run.approved = given
    state.history.append(f"{run.entry} failed: {reason}")


def operating_role(catalog: Catalog, event: Retried) -> str:
    """The role that lets `event`'s person retry: one the catalog marks as operating
    (brief, D26); or `RetryRefused`."""
    counted = sorted(role for role in event.roles if role in catalog.operators)
    if not counted:
        registered = sorted(role for role in event.roles if role in catalog.roles)
        known = listed(registered) if registered else ""
        raise RetryRefused(
            f"{event.entry} is retried by an operating role "
            f"({', '.join(catalog.operators) or 'none registered'}), and {event.by} has "
            f"{known or 'no role'}"
        )
    return counted[0]


def retry(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    event: Retried,
    commands: list[Command],
) -> None:
    """An operator retries a failed run: it runs again as the same run, with the same key, once
    the step is checked again (brief, D26). Or `RetryRefused`."""
    # Who retried is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise RetryRefused(wrong)
    if state.phase != "open":
        raise RetryRefused(f"the case is {state.phase}: nothing starts")
    firing = next((f for f in state.firings if f.entry == event.entry), None)
    if firing is not None and firing.status == "failed":
        role = operating_role(catalog, event)
        try:
            retried = f"{event.by} retried {event.entry} as {role}"
            retry_rule(case, catalog, state, firing, retried, commands, event.at)
        except StepStopped as unreadable:
            raise RetryRefused(f"{event.entry} can't be retried: {unreadable}") from None
        return
    run = next((run for run in state.runs if run.entry == event.entry), None)
    if run is None or run.status != "failed":
        raise RetryRefused(f"{event.entry} has not failed: nothing to retry")
    latest = latest_run(state, run.step)
    if latest is not None and latest is not run:
        # Only a step's latest run runs again, so a retry of an earlier one could never start:
        # refused, rather than left waiting for nothing (brief, D26).
        failed_too = latest.status == "failed"
        then = f"retry {latest.entry}, or close the case" if failed_too else "close the case"
        raise RetryRefused(
            f"{event.entry} can't be retried: {latest.entry} has run since, and only a step's "
            f"latest run runs again: {then}"
        )
    counted = [operating_role(catalog, event)]
    step = case.steps[run.step]
    # The step is checked again: what made it fail may still hold. Fail closed: nothing starts.
    for requirement in requirements(case)[run.step]:
        if not requirements_met((requirement,), state):
            raise RetryRefused(
                f"{event.entry} can't be retried: {run.step} requires {requirement}, which "
                "hasn't completed"
            )
    if (problem := expression_problem(case, catalog, run.step)) is not None:
        raise RetryRefused(f"{event.entry} can't be retried: {problem}")
    if step.when is not None:
        try:
            decided = holds(step.when, state.values, f"{run.step}'s condition")
        except StepStopped as unreadable:
            raise RetryRefused(f"{event.entry} can't be retried: {unreadable}") from None
        # A stale fact is fetched again, never trusted to refuse: the retry is taken, and
        # admission fetches the fact, if anything can, before it reads the condition again; if
        # nothing can, the run fails at once on its age (brief, D18) (brief, D33).
        if not decided and not reads_a_stale_fact(step, state, event.at):
            raise RetryRefused(f"{event.entry} can't be retried: {render(step.when)} is false now")
    # A person decided to try again: no longer a run whose stop was asked (brief, D40).
    run.status, run.reason, run.stop_requested = "retrying", "", ""
    state.history.append(f"{event.by} retried {event.entry} as {counted[0]}")
    # A person decided to try again: a fact the step needs fresh may be fetched again, unless a
    # refresh of it is still on its way (brief, D33). A stopped refresh counts for nothing, even
    # while it runs on (brief, D40).
    for field in step.max_age if isinstance(step, CallStep | PlanStep) else {}:
        prior = state.refreshing.get(field)
        if prior is None:
            continue
        refresh = next(r for r in state.runs if r.entry == prior)
        if refresh.status in ("done", "failed") or refresh.stop_requested:
            del state.refreshing[field]


def reads_a_stale_fact(
    step: TaskStep | CallStep | PlanStep | WaitStep, state: CaseState, at: int
) -> bool:
    """Whether the step's condition reads a fact the step needs fresh that is too old at `at`."""
    if not isinstance(step, CallStep | PlanStep) or step.when is None:
        return False
    read = fields_read(step.when)
    return any(stale.field in read for stale in stale_facts(step.max_age, state, at))


def admit(
    case: CaseDefinition, catalog: Catalog, state: CaseState, commands: list[Command], at: int
) -> None:
    """Start every step that may start now, until no more can: no position, only admission.
    `at` is the time of the event being decided, against which facts' ages are measured."""
    required = requirements(case)
    started = True
    while started:
        started = False
        # The moments that came, before any step is asked again.
        fire_rules(case, catalog, state, commands, at)
        # An open approval follows the case file (brief, D25), before any start is decided: a
        # start is refused only by an approval that still stands.
        follow(case, state)
        # The engine's proposals, from the rules that fired: admission decides (brief, D39).
        if start_from_rules(case, catalog, state, commands, at):
            started = True
        for name, step in case.steps.items():
            if not free_to_start(state, name, step):
                continue
            latest = latest_run(state, name)
            retried = latest if latest is not None and latest.status == "retrying" else None
            # Once the close is only held by a failed run, nothing new starts, whatever the
            # step's requirements: only the run an operator retries (brief, D34).
            if close_held(case, state) and retried is None:
                let_go_while_held(case, state, name)
                continue
            if not requirements_met(required[name], state):
                # A retry or an approval given waits for it, until admission settles (below).
                drop_waiting(state, name, "its requirements are no longer met")
                continue
            try:
                # Every expression it reads is checked over the case's types first, so a misspelt
                # outcome fails the step instead of reading as false (brief, D35).
                if (problem := expression_problem(case, catalog, name)) is not None:
                    raise StepStopped(problem)
                # Freshness first, before the condition, the approval and the start, so each
                # reads fresh facts (brief, D18) (brief, D33).
                if isinstance(step, CallStep | PlanStep):  # a task or a wait needs none fresh
                    waits = refresh_stale(case, catalog, state, name, step, at, commands)
                    if waits == "refreshing":
                        started = True  # a refresh was scheduled: admission goes round again
                    if waits != "fresh":
                        continue
                # Read only once `requires` are met: a field nobody has set fails the step.
                if step.when is not None and not holds(
                    step.when, state.values, f"{name}'s condition"
                ):
                    if retried is not None:  # nothing can let it start now
                        why = f"{render(step.when)} is false now"
                        retry_fails(state, retried, why, "retry it once it holds")
                    drop_waiting(state, name, f"{render(step.when)} is false")
                    continue
                taken_up(state, name)
                start(case, catalog, state, name, step, commands)
            except (StepStopped, InputRefused, NotInCatalog) as error:
                # Nothing is skipped automatically: the step fails, and waits for a person; the
                # other steps go on (brief, D17).
                taken_up(state, name)
                fail(state, name, str(error))
            started = True
    nothing_on_its_way(case, state, required)


def nothing_on_its_way(
    case: CaseDefinition, state: CaseState, required: dict[str, tuple[str, ...]]
) -> None:
    """Once admission has settled, what waits for a step's requirement that ended without
    completing waits for nothing: an approval given lapses, then a retried run fails again, each
    saying which. Read on the settled state, so a requirement a rule stopped and another started
    again in this decision is on its way. A requirement still on its way keeps both: the approval
    tied to the values it saw, the retry shown through it (brief, D11) (brief, D17) (brief, D26)."""
    for name in case.steps:
        ended = ended_requirement(state, required[name])
        if ended is None:
            continue
        why = f"{name} requires {ended}, which hasn't completed"
        if (given := state.given.pop(name, None)) is not None:
            state.history.append(f"lapsed {given.entry}: {why}")
        latest = latest_run(state, name)
        if latest is not None and latest.status == "retrying":
            retry_fails(state, latest, why, "retry it once it has")


def let_go_while_held(case: CaseDefinition, state: CaseState, name: str) -> None:
    """While the close is held nothing new starts, so nothing waits to: an approval given for
    the step is let go, and a person's proposal waiting for its fact is dropped, each saying
    why, never kept as pending work nobody sees (brief, D34) (brief, D39)."""
    why = nothing_new(case, state)
    if state.given.pop(name, None) is not None:
        state.history.append(f"{name} not started: {why}")
    drop_waiting(state, name, why)


def retry_fails(state: CaseState, run: StepRun, why: str, then: str) -> None:
    """A retried run that nothing can let start any more goes back to failed, saying why and
    what to do, never kept waiting for nothing: an operator retries it again, or closes the case
    (brief, D17) (brief, D26)."""
    run.status = "failed"
    run.reason = f"its retry can't start: {why}: {then}, or close the case"
    state.history.append(f"{run.entry} failed again: its retry can't start: {why}")


def refresh_stale(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: CallStep | PlanStep,
    at: int,
    commands: list[Command],
) -> Literal["fresh", "refreshing", "waiting"]:
    """Whether every fact the step needs fresh is: `fresh`; or one is being fetched again,
    `refreshing` (scheduled now) or `waiting` (on its way). A stale fact is refreshed, never
    trusted: only one a read-only activity step obtained can be fetched again, and only once for
    the same need; any other stops the step, and a person decides (brief, D17) (brief, D33)."""
    for stale in stale_facts(step.max_age, state, at):
        if stale.age is None:  # fail closed: an age that can't be told is never fresh
            raise StepStopped(f"{stale.field} has no time obtained, so {name} can't tell its age")
        said = f"{stale.field} was obtained {ago(stale.age)} ago"
        needed = f"{name} needs it at most {as_said(stale.limit)} old"
        prior = state.refreshing.get(stale.field)
        if prior is not None and prior != stale.run:  # fetched again, and still the old value
            run = next(run for run in state.runs if run.entry == prior)
            if run.stop_requested and run.status == "running":
                # A stopped refresh counts for nothing: what needed it fails, never waits and
                # asks again, which could loop in one decision (brief, D39) (brief, D40).
                stopped = (
                    f"{said}, and {needed}: its refresh {prior} was stopped by "
                    f"{run.stop_requested}, so it counts for nothing"
                )
                raise StoppedRefresh(stopped, coming_entry(state, name), prior)
            if run.status not in ("done", "failed"):
                return "waiting"  # on its way: running, or retried by an operator
            gave = (
                f"gave {state.values[f'{run.step}.outcome']}" if run.status == "done" else "failed"
            )
            raise StepStopped(
                f"{prior} {gave}, so {stale.field} is still {ago(stale.age)} old, and {needed}"
            )
        source, why_not = refreshable(case, catalog, state, stale)
        if source is None:
            raise StepStopped(f"{said}, and {needed}: {why_not}")
        state.history.append(
            f"refreshing {stale.field} for {name}: obtained {ago(stale.age)} ago, at most "
            f"{as_said(stale.limit)}"
        )
        refreshing = case.steps[source]
        assert isinstance(refreshing, ActivityStep)  # only a read-only activity is refreshed
        schedule(case, catalog, state, source, refreshing, None, commands)  # a new run: its own key
        run = state.runs[-1]
        run.refresh = True
        state.refreshing[stale.field] = run.entry
        return "refreshing"
    return "fresh"


def refreshable(
    case: CaseDefinition, catalog: Catalog, state: CaseState, stale: Stale
) -> tuple[str | None, str]:
    """The step whose run obtained the stale fact, if running it again is safe: an activity whose
    contract only reads (brief, D33). Otherwise None, and why it can't be fetched again."""
    if stale.run is not None and stale.run.partition("#")[0] in case.events:
        # Sent from outside: nothing in the case can ask its sender again (brief, D41).
        return (
            None,
            f"it came from the event {stale.run}, sent from outside, so it can't be fetched again",
        )
    run = next((run for run in state.runs if run.entry == stale.run), None)
    if run is None:
        # Not from a run: from a person (their answer, or the opening a person made), or from the
        # system that opened the case. Nothing can ask either again.
        came = "a person" if is_from_a_person(state, stale.field) else "the opening"
        return None, f"it came from {came}, so it can't be fetched again"
    step = case.steps[run.step]
    if isinstance(step, PlanStep):
        return None, f"{run.step} is a plan step, so it isn't run again unasked"
    if isinstance(step, WorkflowStep):
        # Another team's workflow, which may run for minutes: never re-run unasked (brief, D33).
        return None, f"{run.step} is a workflow step, so it isn't run again unasked"
    assert isinstance(step, ActivityStep)  # only a task has no contract, and it gives no run's fact
    effect = called(catalog, step).effect
    if effect == "compute":
        # The same inputs give the same answer: its age is its inputs' age (brief, D33).
        return None, (
            f"{run.step} computes it from its inputs (compute), so running it again gives "
            "nothing new"
        )
    if effect != "read":
        return None, f"{run.step} has side effects ({effect}), so it can't be run again"
    # A refresh is a run like any other: it passes the same gate as a start, or doesn't run.
    # Fail closed: it never asks for an approval itself, so a step that needs one now isn't run
    # again, and a person decides (brief, D33).
    for requirement in requirements(case)[run.step]:
        if not requirements_met((requirement,), state):
            return None, (
                f"{run.step} requires {requirement}, which hasn't completed, so it isn't run again"
            )
    if step.when is not None and not holds(step.when, state.values, f"{run.step}'s condition"):
        return None, f"{run.step}'s condition is false now, so it isn't run again"
    needed = needs_approval(state, run.step, step)
    if needed or asked_anyway(case, catalog, state, step) is not None:
        return None, f"{run.step} needs an approval to run, so it isn't run again unasked"
    return run.step, ""


def is_from_a_person(state: CaseState, field: str) -> bool:
    """Whether a person gave the field's value: their answer, or the case they opened."""
    return any(source.startswith("person:") for source in state.sources.get(field, ()))


def free_to_start(
    state: CaseState, name: str, step: TaskStep | CallStep | PlanStep | WaitStep
) -> bool:
    """Whether the step may start by itself: it isn't waiting for its approval, and it starts by
    itself and hasn't started before; or its approval was just given; or a person proposed it,
    and it waited for a fact fetched again."""
    if name in state.approvals:
        return False  # waiting for its approval
    if name in state.given:
        return True  # approved, so it starts now
    if name in state.waiting_to_start:
        return True  # proposed, and waiting for a fact fetched again (brief, D39)
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying":
        return True  # an operator retried it
    # A step starts by itself at most once; again, or at all if not automatic, only if proposed.
    return step.automatic and latest_run(state, name) is None


def proposal_spent(state: CaseState, name: str) -> None:
    """The proposed run started, or is over: who proposed it, a person or a rule, is forgotten."""
    state.proposers.pop(name, None)
    state.proposed_by_rules.pop(name, None)


def start_from_rules(
    case: CaseDefinition, catalog: Catalog, state: CaseState, commands: list[Command], at: int
) -> bool:
    """Take each start the rules asked for, in order: the engine proposes, and admission decides,
    as for a person's proposal (brief, D39). A start it refuses is recorded, and nothing runs; one
    that can't be made fails the step, which waits for a person. Whether any started."""
    required = requirements(case)
    started = False
    while state.rule_starts:
        asked = state.rule_starts.pop(0)
        name, said = asked.step, f"{asked.entry} on {asked.moment}"
        step = case.steps[name]
        # Read first: a rule that stopped a step could otherwise start it again, for ever, in one
        # decision (brief, D39).
        if name in state.started_by_rules:
            refusal: str | None = "a rule already started it in this decision"
        elif close_held(case, state):
            # Once every closes_when milestone is reached, nothing new starts, a rule's start
            # included, even one decided on the moment that reached the last (brief, D34).
            refusal = nothing_new(case, state)
        else:
            refusal = proposal_refusal(case, name, required[name], state)
        if refusal is None:
            try:
                if (problem := expression_problem(case, catalog, name)) is not None:
                    raise StepStopped(problem)
                if isinstance(step, CallStep | PlanStep):
                    never_waits(case, catalog, state, name, step, at)
                if step.when is not None and not holds(
                    step.when, state.values, f"{name}'s condition"
                ):
                    refusal = f"{name} doesn't run now: {render(step.when)} is false"
            except StepStopped as error:
                state.history.append(f"{said}: starting {name}")
                state.started_by_rules.append(name)
                # Kept with the failed run: an operator's retry starts it on what the rule read,
                # which still counts for its inputs and its approvers (brief, D38) (brief, D39).
                proposed_by_a_rule(state, asked)
                fail(state, name, str(error))  # nothing is skipped: a person decides (brief, D17)
                started = True
                continue
        if refusal is not None:
            state.history.append(f"{said}: {name} not started: {refusal}")
            continue
        state.history.append(f"{said}: starting {name}")
        state.started_by_rules.append(name)
        proposed_by_a_rule(state, asked)
        try:
            start(case, catalog, state, name, step, commands)
        except (StepStopped, InputRefused, NotInCatalog) as error:
            fail(state, name, str(error))
        started = True
    return started


def never_waits(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: CallStep | PlanStep,
    at: int,
) -> None:
    """`StepStopped` if a fact the step needs fresh is stale: a rule's start never waits for one to
    be fetched again, since the fetch lands with no person in it, and a loop of rules could come
    round with nobody in between. An operator's retry fetches it, if anything can; the line says
    which (brief, D33) (brief, D39)."""
    for stale in stale_facts(step.max_age, state, at):
        if stale.age is None:  # fail closed: an age that can't be told is never fresh
            raise StepStopped(f"{stale.field} has no time obtained, so {name} can't tell its age")
        old = (
            f"{stale.field} was obtained {ago(stale.age)} ago, and {name} needs it at most "
            f"{as_said(stale.limit)} old"
        )
        fetched_by, why = refreshable(case, catalog, state, stale)
        if fetched_by is None:
            raise StepStopped(f"{old}: {why}")
        raise StepStopped(
            f"{old}: a rule's start doesn't wait for it to be fetched again; retry it to fetch it"
        )


def taken_up(state: CaseState, name: str) -> None:
    """A proposal that waited for a fact is taken up: the step starts, or fails, now."""
    if name in state.waiting_to_start:
        state.waiting_to_start.remove(name)


def drop_waiting(state: CaseState, name: str, why: str) -> None:
    """A proposal that waited for a fact no longer holds once it has landed: dropped, saying
    why, and its proposer with it (brief, D39)."""
    if name in state.waiting_to_start:
        state.waiting_to_start.remove(name)
        proposer = state.proposers.pop(name)
        state.history.append(f"dropped {proposer}'s proposal of {name}: {why}")


def start(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: TaskStep | CallStep | PlanStep | WaitStep,
    commands: list[Command],
) -> None:
    """Open a task's run, or a wait's; start a plan; ask for an activity's or a workflow's
    approval, or start it."""
    if isinstance(step, PlanStep):
        start_plan(case, catalog, state, name, step, commands)
        return
    if isinstance(step, WaitStep):
        # Open until the event's next arrival: pending work, listed with what it waits for
        # (brief, D10) (brief, D24) (brief, D41).
        entry = coming_run(state, name, "open").entry
        proposal_spent(state, name)  # a wait has no approval: the proposed run has started
        state.waiting[entry] = f"{step.event} {sent_by(case.events[step.event])}"
        state.history.append(f"started {entry}: waiting for {state.waiting[entry]}")
        return
    if isinstance(step, TaskStep):
        entry = coming_run(state, name, "open").entry
        proposal_spent(state, name)  # a task has no approval: the proposed run has started
        state.waiting[entry] = f"{name} by {' or '.join(step.roles)}"
        state.history.append(
            f"started {entry}: waiting for {' or '.join(step.outcomes)} by "
            f"{' or '.join(step.roles)}"
        )
        return
    given = state.given.pop(name, None)  # spent, whatever happens next
    latest = latest_run(state, name)
    if given is None and latest is not None and latest.status == "retrying":
        given = latest.approved  # a retry keeps the approval spent on its run (brief, D26)
    if given is None:
        # Read first, so a condition that can't be read stops the step; then, if it read
        # untrusted data, the approval is asked whatever it gave (brief, D11) (brief, D39).
        needed = needs_approval(state, name, step)
        anyway = asked_anyway(case, catalog, state, step)
        if needed or anyway is not None:
            ask(state, name, step, anyway)
            return
    if given is not None:
        lapsed(state, name, step, given)
    schedule(case, catalog, state, name, step, given, commands)
    # The proposed run has started. Spent here, never in `schedule`: a refresh of the step for
    # another step's fact isn't the run anyone proposed, and its proposer still may not approve
    # it (brief, D25).
    proposal_spent(state, name)


def schedule(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: CallStep,
    approved: GivenApproval | None,
    commands: list[Command],
) -> None:
    """Check the inputs against the real sources (layer 5), then schedule the activity, or start
    the workflow, with a key naming the case and the step run (brief, D17). A workflow step is
    checked exactly as an activity step is (brief, D6)."""
    contract = called(catalog, step)  # fail closed: a contract the catalog lacks stops it
    # Checked again at runtime, on nothing case validation did (learning question 34).
    if contract.risk == "high" and step.approval is None:
        raise StepStopped(f"{contract.reference} is high risk, and {name} has no approval")
    latest = latest_run(state, name)
    entry = latest.entry if latest is not None and latest.status == "retrying" else None
    entry = entry or next_entry(state, name)
    key = f"{state.case}/{entry}"
    types = {name: field.declared for name, field in case.fields.items()}
    # A retry starts the same run again, with what its first start kept (brief, D26).
    kept = latest.steered if latest is not None and latest.status == "retrying" else ()
    steered = tuple(dict.fromkeys((*kept, *steering(case, catalog, state, name, step))))
    inputs = checked_inputs(contract, step.inputs, state.values, state.sources, key, types, steered)
    if isinstance(step, WorkflowStep):
        refuse_sensitive_inputs(contract.reference, step.inputs, state.values)
    run = coming_run(state, name, "running")
    run.approved, run.steered = approved, steered
    run.excluded = may_not_approve(state, name, run)  # read before the proposal is spent
    if isinstance(step, WorkflowStep):
        # The run's name names its child workflow on Temporal, as a plan step's does.
        state.history.append(
            f"started {entry}: workflow {contract.reference} ({origins(step.inputs, state)}), "
            f"run {key}"
        )
        commands.append(StartWorkflow(entry, contract.reference, inputs, key))
        return
    keyed = f", key {key}" if contract.idempotency_key is not None else ""
    state.history.append(
        f"scheduled {entry}: {contract.reference} ({origins(step.inputs, state)}){keyed}"
    )
    commands.append(Schedule(entry, contract.reference, inputs))


def steering(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: CallStep | PlanStep,
) -> tuple[Steering, ...]:
    """What decided that the step runs, and the untrusted values it read: its own `when`, read
    now, and the `when` of the rule that started it, as it read it then (brief, D38)
    (brief, D39)."""
    steered = [
        Steering(f"{name}'s condition reads {field}", sources)
        for field, sources in untrusted_of(read_sources(case, catalog, state, step.when)).items()
    ]
    if (asked := state.proposed_by_rules.get(name)) is not None:
        steered += [
            Steering(f"{asked.entry}'s condition, which started {name}, reads {field}", sources)
            for field, sources in asked.untrusted.items()
        ]
    return tuple(steered)


def refuse_sensitive_inputs(
    reference: str, inputs: Mapping[str, Expression], values: Mapping[str, object]
) -> None:
    """A workflow step is never given a sensitive value: its worker belongs to another team and
    doesn't hold the case's key (brief, D31)."""
    for expression in inputs.values():
        for field in reads_sensitive(expression, values):
            raise InputRefused(
                f"{reference} is a workflow step and can't be given {field}, a sensitive field: "
                "its worker doesn't hold the case's key"
            )


def origins(inputs: Mapping[str, Expression], state: CaseState) -> str:
    """Where each input's value came from, as the history says it: `amount from person:ana`."""
    return "; ".join(
        f"{field} from {', '.join(sorted(provenance(expression, state.sources))) or 'the case'}"
        for field, expression in inputs.items()
    )


def start_plan(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: PlanStep,
    commands: list[Command],
) -> None:
    """Start the step's plan with its fields, each with where its value came from, so the plan's
    own checks see the real sources (brief, D28). The plan checks its fields when it starts."""
    fields: dict[str, Sourced] = {}
    for field, expression in step.inputs.items():
        try:
            value = evaluate(expression, state.values)
            fields[field] = Sourced(
                kept_sensitive(expression, state.values, value),  # wrapped into the plan too
                provenance(expression, state.sources),
            )
        except (ExpressionError, NoSources) as error:
            # Fail closed: a field that can't be read gets no default; the step fails.
            raise InputRefused(f"{field} can't be evaluated: {error}") from None
    run = coming_run(state, name, "running")
    # Who may approve nothing in the plan crosses into it, or a plan step would be a way around
    # them (brief, D25). Read before the proposal is spent: the rule's record is part of it, and
    # a retry starts the same run again, with what its first start kept (brief, D26) (brief, D39).
    excluded = may_not_approve(state, name, run)
    steered = tuple(dict.fromkeys((*run.steered, *steering(case, catalog, state, name, step))))
    run.excluded, run.steered = excluded, steered
    proposal_spent(state, name)  # the proposed run has started
    plan_run = f"{state.case}/{run.entry}"
    state.history.append(
        f"started {run.entry}: plan {step.plan} ({origins(step.inputs, state)}), run {plan_run}"
    )
    types = {field: declared.declared for field, declared in case.fields.items()}
    references = {
        field: given_as_reference(expression, types) for field, expression in step.inputs.items()
    }
    commands.append(
        StartPlan(run.entry, step.plan, fields, plan_run, excluded, references, steered)
    )


def may_not_approve(state: CaseState, name: str, run: StepRun) -> dict[str, str]:
    """Who may approve nothing in the step's run, and why: whoever its first start excluded, kept
    with the run for its retry (brief, D26); the person who opened the case (brief, D11); who
    proposed it (brief, D25); and whoever's answer the condition of the rule that started it read
    (brief, D11) (brief, D39)."""
    excluded = dict(run.excluded)
    if state.opened_by is not None:
        excluded[state.opened_by] = (
            f"{state.opened_by} opened the case, so cannot approve its steps"
        )
    if (proposer := state.proposers.get(name)) is not None:
        excluded.setdefault(proposer, f"{proposer} proposed {name}, so cannot approve it")
    if (asked := state.proposed_by_rules.get(name)) is not None:
        for person, field in asked.read_from.items():
            excluded.setdefault(person, decided_by(person, field, asked))
    return excluded


def coming_run(
    state: CaseState, name: str, status: Literal["open", "running", "failed"]
) -> StepRun:
    """The step's coming run, now `status`: the run an operator retried, which keeps its entry and
    so its key (brief, D26), or else a new one."""
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying":
        latest.status = status
        # The same run, so it starts nothing again (brief, D26) (brief, D38); but one that failed
        # before it started starts now, for the first time: `started` fires once (brief, D38, as
        # amended in 11b).
        if status != "failed" and not latest.started:
            latest.started = True
            state.moments.append(f"started {name}")
        return latest
    run = StepRun(next_entry(state, name), name, status, started=status != "failed")
    state.runs.append(run)
    if run.started:  # a run that fails before it starts never started
        state.moments.append(f"started {name}")
    return run


def coming_entry(state: CaseState, name: str) -> str:
    """The entry the step's coming run takes: the run an operator retried, or a new one."""
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying":
        return latest.entry
    return next_entry(state, name)


def next_entry(state: CaseState, name: str) -> str:
    """The step's next run: `review#1`, then `review#2`."""
    return f"{name}#{sum(1 for run in state.runs if run.step == name) + 1}"


def listed(names: list[str]) -> str:
    """`nothing`, `amount`, `amount and order_id`, `a, b and c`."""
    if len(names) <= 1:
        return names[0] if names else "nothing"
    return f"{', '.join(names[:-1])} and {names[-1]}"
