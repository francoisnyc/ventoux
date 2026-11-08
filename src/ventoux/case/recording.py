"""Making audit records: one per act the case decides, from engine version 3 (layer 19a).

See `ventoux.case.audit` for what a record holds, and docs/layers/19-audit-keys.md (19a).
"""

import copy

from ventoux.case.audit import Act, AuditRecord, Decision, Fact
from ventoux.case.definition import CallStep, CaseDefinition, CaseStep, PlanStep, Step
from ventoux.case.keeping import kept
from ventoux.case.state import (
    Answered,
    Assigned,
    CaseEnded,
    CaseState,
    ChangeProposed,
    ChildNotEnded,
    ChildRang,
    Claimed,
    CloseAsked,
    ClosedByParent,
    Completed,
    Event,
    Failed,
    ForgetApproved,
    GivenBack,
    Opened,
    PlanCancelled,
    Proposed,
    Retried,
    Sent,
    Shown,
    TimerDue,
    Unassigned,
    WorkflowCancelled,
)
from ventoux.core.expressions import Expression
from ventoux.core.provenance import fields_read

# The first engine version that makes audit records (brief, D51) (brief, D76).
RECORDS_FROM = 3


def recorded(case: CaseDefinition, state: CaseState, act: Event, since: int) -> None:
    """Record `act`, once `decide` has decided it: the decisions it caused, and the lines it
    added to the history from line `since` on. From engine version 3 only (brief, D76)."""
    if state.engine >= RECORDS_FROM:
        state.audit.append(record(case, state, act, state.deciding, state.history[since:]))
    state.deciding = []  # a collector for one decision: always empty between events


def decided_start(state: CaseState, name: str, step: Step, entry: str) -> None:
    """Say that `name`'s run `entry` started, under which rule, on which facts."""
    rule = f"steps.{name}.when" if step.when is not None else f"steps.{name}"
    if (asked := state.proposed_by_rules.get(name)) is not None:
        [firing] = [each for each in state.firings if each.entry == asked.entry]
        rule = f"rules.{firing.rule}"
    # What let it start: its condition, and, for a call, its approval's, which decided whether a
    # person had to approve; then what it was given.
    approval = step.approval.when if isinstance(step, CallStep) and step.approval else None
    read = facts(state, [step.when, approval, *inputs_of(step)])
    state.deciding.append(Decision("started", step=name, entry=entry, rule=rule, read=read))


def decided_failure(state: CaseState, step: str, entry: str, reason: str) -> None:
    """Say that `step`'s run `entry` failed, and why: the run's own reason, which names what
    failed and the type of what it raised, never what it said (brief, D31) (brief, D76)."""
    decision = Decision("failed", step=step, entry=entry, rule=f"steps.{step}", reason=reason)
    state.deciding.append(decision)


def inputs_of(step: Step) -> list[Expression]:
    """What a step gives what it runs: an activity's or workflow's inputs, a plan's fields, a
    child case's opening. A task and a wait give nothing."""
    if isinstance(step, CallStep | PlanStep | CaseStep):
        return list(step.inputs.values())
    return []


def facts(state: CaseState, expressions: list[Expression | None]) -> tuple[Fact, ...]:
    """Each field of the case file `expressions` read, once, in the order read: with its sources,
    and its value as the state holds it, sensitive ones wrapped. A field not set has no fact:
    nothing was read from it."""
    names = [name for each in expressions if each is not None for name in fields_read(each)]
    return tuple(
        Fact(name, tuple(sorted(state.sources.get(name, ()))), state.values[name])
        for name in dict.fromkeys(names)
        if name in state.values
    )


def record_refused(
    case: CaseDefinition, state: CaseState, act: Event, refusal: Exception
) -> CaseState:
    """`state` with the refused `act` recorded: its history line, and from engine version 3 its
    record, whose one decision is `refused`. Nothing else changes: `decide` raised, so the case
    waits on as if the act hadn't come (brief, D76)."""
    state = copy.deepcopy(state)  # the state passed in is never changed
    line = f"refused {asked(act)}: {refusal}"
    state.history.append(line)
    if state.engine >= RECORDS_FROM:
        # The entry as it was asked, never a step guessed from it: it may name none.
        step = act.step if isinstance(act, Proposed) else None
        entry = getattr(act, "entry", None)
        refused = Decision("refused", step=step, entry=entry, reason=str(refusal))
        state.audit.append(record(case, state, act, [refused], [line]))
    return state


def record(
    case: CaseDefinition,
    state: CaseState,
    act: Event,
    decisions: list[Decision],
    lines: list[str],
) -> AuditRecord:
    """The next record of `state`, for `act`, the `decisions` it caused and the `lines` it
    wrote: numbered after the last, from 1 (brief, D76)."""
    return AuditRecord(
        number=len(state.audit) + 1,
        at=act.at,
        release=state.release,
        engine=state.engine,
        act=act_of(case, act),
        decisions=decisions,
        lines=lines,
    )


def act_of(case: CaseDefinition, event: Event) -> Act:
    """`event` as an act: who, with which roles, what it names, giving what. A value given for a
    field of the case file is as the case file keeps it: the client wraps every value of a form,
    since it can't tell which are sensitive; the record keeps wrapped only the sensitive ones
    (brief, D31) (brief, D76)."""
    roles = tuple(sorted(getattr(event, "roles", ())))  # as the trusted caller stated them
    match event:
        case Opened():
            values = {name: kept(case, name, value) for name, value in event.file.items()}
            return Act("opened", by=event.by, roles=roles, values=values)
        case Answered():
            values = {name: kept(case, name, value) for name, value in (event.form or {}).items()}
            return Act(
                "answered",
                by=event.by,
                roles=roles,
                entry=event.entry,
                outcome=event.outcome,
                values=values,
            )
        case Proposed():
            return Act("proposed", by=event.by, roles=roles, entry=event.step)
        case Completed():
            # What the run gave, as it gave it: its contract says where each value came from.
            return Act("completed", entry=event.entry, outcome=event.outcome, values=event.output)
        case Failed():
            # Its reason is the failed decision's: the act itself gives nothing.
            return Act("failed", entry=event.entry)
        case Retried():
            return Act("retried", by=event.by, roles=roles, entry=event.entry)
        case CloseAsked():
            return Act("closed", by=event.by, roles=roles, outcome=event.reason)
        case PlanCancelled():
            return Act("plan cancelled", entry=event.entry)
        case CaseEnded():
            # What the child reported, each value as it holds it, sensitive ones wrapped.
            values = {name: sourced.value for name, sourced in event.report.items()}
            return Act(
                "child ended",
                by=event.closed_by,
                entry=event.entry,
                outcome=event.outcome,
                values=values,
            )
        case ChildRang():
            return Act("child rang", entry=event.entry)
        case ChildNotEnded():
            return Act("child not ended", entry=event.entry, outcome=event.how)
        case ClosedByParent():
            return Act("closed by parent", outcome=event.reason)
        case WorkflowCancelled():
            return Act("workflow cancelled", entry=event.entry)
        case Shown():
            return Act("shown", by=event.by, roles=roles, entry=event.field)
        case ForgetApproved():
            # Who approved it is the act's; who proposed it, the forgotten decision's.
            return Act("forget approved", by=event.approved_by, roles=roles_of(event))
        case ChangeProposed():
            given = {event.target: kept(case, event.target, event.value)}
            values = given if event.kind == "edit" else {}  # a skip or a migration gives none
            return Act(
                "change proposed",
                by=event.by,
                roles=roles,
                entry=event.target,
                outcome=event.kind,
                values=values,
            )
        case Sent():
            # What the event carries, as it carried it: its sender is its source (brief, D41).
            return Act("event", by=event.by, roles=roles, entry=event.event, values=event.payload)
        case TimerDue():
            return Act("timer", entry=event.rule)
        case Claimed():
            return Act("claimed", by=event.by, roles=roles, entry=event.entry)
        case GivenBack():
            return Act("given back", by=event.by, roles=roles, entry=event.entry)
        case Assigned():
            return Act(
                "assigned", by=event.by, roles=roles, entry=event.entry, values={"to": event.to}
            )
        case Unassigned():
            return Act("unassigned", by=event.by, roles=roles, entry=event.entry)


def roles_of(event: ForgetApproved) -> tuple[str, ...]:
    """The approver's roles, sorted: the proposer's are the forgotten decision's."""
    return tuple(sorted(event.approver_roles))


def asked(event: Event) -> str:
    """What a person asked, as a refusal names it: `sam's answer approve to review#1`."""
    if isinstance(event, Answered):
        return f"{event.by}'s answer {event.outcome} to {event.entry}"
    if isinstance(event, Proposed):
        return f"{event.by}'s proposal of {event.step}"
    if isinstance(event, Retried):
        return f"{event.by}'s retry of {event.entry}"
    if isinstance(event, Claimed):
        return f"{event.by}'s claim of {event.entry}"
    if isinstance(event, GivenBack):
        return f"{event.by}'s give-back of {event.entry}"
    if isinstance(event, Assigned):
        return f"{event.by}'s assignment of {event.entry}"
    if isinstance(event, Unassigned):
        return f"{event.by}'s return of {event.entry}"
    if isinstance(event, CloseAsked):
        return f"{event.by}'s close as {event.reason}"
    if isinstance(event, Shown):
        return f"the record of {event.field} shown to {event.by}"
    if isinstance(event, ForgetApproved):
        return f"forgetting the case, approved by {event.approved_by}"
    if isinstance(event, ChangeProposed):
        return f"{event.by}'s proposal to {event.kind} {event.target}"  # never the value
    if isinstance(event, Sent):
        return f"{event.event} from {event.by}"  # who sent it, never what it carries
    return type(event).__name__  # only people's requests are refused; anything else is a bug
