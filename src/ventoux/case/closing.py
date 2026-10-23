"""Closing a case: by itself when nothing is left to do, or by a person with a declared reason
(brief, D10, layer 8b).

A close puts the case in **closing**: what waits for people is cancelled, saying why; nothing new
starts; activities already running finish, since a side effect can't be cut off halfway. Then the
case is **closed**. Something that completes while closing flags the case for a person.
"""

from ventoux.case.admission import latest_run, requirements_met
from ventoux.case.approvals import with_given
from ventoux.case.definition import CaseDefinition
from ventoux.case.state import CaseState, CloseAsked
from ventoux.case.timers import cancel_timers
from ventoux.case.writers import read_sources, untrusted_of
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import ExpressionError, evaluate
from ventoux.core.person import identifier_problem
from ventoux.core.roles import role_that_counts


class CloseRefused(Exception):
    """A close the engine won't make, with the reason."""


def refuse_to_close(
    case: CaseDefinition, catalog: Catalog, state: CaseState, event: CloseAsked
) -> str:
    """The role that lets `event`'s person close the case with its reason; or `CloseRefused`.
    Undeclared reasons and roles are refused (brief, D10)."""
    # Who closes is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise CloseRefused(wrong)
    if state.phase != "open":
        raise CloseRefused(f"the case is {state.phase}: it can't be closed again")
    reason = case.close_reasons.get(event.reason)
    if reason is None:
        declared = ", ".join(sorted(case.close_reasons)) or "none"
        raise CloseRefused(
            f"{case.case} has no close reason {event.reason!r}: its reasons are {declared}"
        )
    role = role_that_counts(reason.roles, event.roles, catalog.roles)
    if role is None:
        registered = sorted(r for r in event.roles if r in catalog.roles)
        known = ", ".join(registered) if registered else "no role"
        raise CloseRefused(
            f"{event.reason} is closed by {' or '.join(reason.roles)}, and {event.by} has {known}"
        )
    return role


def begin_closing(state: CaseState, cancelled_because: str, closed_because: str) -> None:
    """Put the case in closing: cancel every open task, approval, failed run, failed rule and
    timer, saying why, so the people they were assigned to see it; running activities finish
    (brief, D10)."""
    state.phase = "closing"
    state.closed_because = closed_because
    for run in state.runs:
        if run.status in ("open", "failed", "retrying"):
            run.status = "cancelled"
            state.waiting.pop(run.entry, None)
            state.history.append(f"cancelled {run.entry}: {cancelled_because}")
    for firing in state.firings:
        if firing.status == "failed":  # a rule waiting for a person, as a failed run does
            firing.status = "cancelled"
            state.history.append(f"cancelled {firing.entry}: {cancelled_because}")
    for approval in list(state.approvals.values()):
        del state.approvals[approval.step]
        del state.waiting[approval.entry]
        state.history.append(
            f"cancelled {approval.entry}: {cancelled_because}{with_given(approval)}"
        )
    state.given.clear()  # an approval not yet spent starts nothing now
    state.proposers.clear()
    state.proposed_by_rules.clear()
    state.waiting_to_start.clear()  # nor does a proposal waiting for a fact (brief, D39)
    cancel_timers(state, cancelled_because)  # nor can a timer act (brief, D10) (brief, D44)
    cancel_changes(state, cancelled_because)  # nor is any change applied (brief, D52)


def cancel_changes(state: CaseState, because: str) -> None:
    """Cancel every change request still waiting for its approver, saying why: a request is not
    pending work, so it keeps no case open, and nothing changes a case that stopped deciding
    (brief, D52)."""
    for entry in list(state.changes):
        del state.changes[entry]
        del state.waiting[entry]
        state.history.append(f"cancelled {entry}: {because}")


def settle(case: CaseDefinition, catalog: Catalog, state: CaseState) -> None:
    """Close the case if it is done: open with nothing left to do (unless it stays open), or
    closing with nothing still running (brief, D10)."""
    if state.phase == "open" and not case.stays_open and not pending(state):
        state.phase = "closed"
        cancel_changes(state, "nothing left to do")
        say_kept_from_starting(case, catalog, state)
        state.history.append("closed: nothing left to do")
    elif state.phase == "closing" and not any(run.status == "running" for run in state.runs):
        state.phase = "closed"
        say_kept_from_starting(case, catalog, state)
        state.history.append(f"closed: {state.closed_because}")


def say_kept_from_starting(case: CaseDefinition, catalog: Catalog, state: CaseState) -> None:
    """As the case closes, say each step that would have started by itself but for its own
    condition, read false on untrusted data. Untrusted data may keep something from happening,
    but never silently (brief, D17) (brief, D48): the line names the field and its source, never
    the value (brief, D30)."""
    for name, step in case.steps.items():
        if step.when is None or not step.automatic or latest_run(state, name) is not None:
            continue
        if not requirements_met(step.requires, state):
            continue  # what kept it is a requirement, not its condition
        untrusted = untrusted_of(read_sources(case, catalog, state, step.when))
        try:
            kept = evaluate(step.when, state.values) is False
        except ExpressionError:
            continue  # a condition that can't be read is admission's to stop on, not this line's
        if not untrusted or not kept:
            continue
        reads = "; ".join(f"{field}, from {', '.join(sorted(s))}" for field, s in untrusted.items())
        state.history.append(f"{name} not started: its condition reads {reads}, and is false")


def close_when_reached(case: CaseDefinition, state: CaseState) -> None:
    """Begin closing once every milestone in `closes_when` is reached (brief, D10), unless a step
    or a rule needs attention: a failed run waits for a person, never cancelled by a milestone (brief, D26).
    The case closes once it is retried to completion, or a person closes it with a reason."""
    if state.phase != "open" or not case.closes_when:
        return
    if any(run.status in ("failed", "retrying") for run in state.runs):
        return  # nothing is skipped automatically (brief, D17)
    if any(firing.status == "failed" for firing in state.firings):
        return  # nor is a rule that couldn't be read (brief, D38)
    if all(milestone in state.milestones for milestone in case.closes_when):
        names = " and ".join(case.closes_when)
        verb = "are" if len(case.closes_when) > 1 else "is"
        begin_closing(state, f"the case closes when {names} {verb} reached", f"{names} reached")


def close_held(case: CaseDefinition, state: CaseState) -> bool:
    """Whether every `closes_when` milestone is reached while the case is still open: a failed
    run holds the close until it is retried or a person closes the case (brief, D26). Nothing new
    starts meanwhile, as in any close (brief, D10) (brief, D34)."""
    return (
        state.phase == "open"
        and bool(case.closes_when)
        and all(milestone in state.milestones for milestone in case.closes_when)
    )


def pending(state: CaseState) -> bool:
    """Whether anything is left to do (brief, D10): a task open, an activity running, an approval
    asked or given and not yet spent, a step or a rule failed, which waits for a person
    (brief, D17) (brief, D38), or a timer set (brief, D44)."""
    unfinished = any(run.status in ("open", "running", "failed", "retrying") for run in state.runs)
    failed_rule = any(firing.status == "failed" for firing in state.firings)
    waiting = bool(state.approvals) or bool(state.given) or bool(state.timers)
    return unfinished or failed_rule or waiting


def needs_attention(state: CaseState) -> list[str]:
    """What waits for an operator, each with why: every failed step run, then every failed rule
    (brief, D17) (brief, D38)."""
    runs = [f"{run.entry}: {run.reason}" for run in state.runs if run.status == "failed"]
    rules = [f"{f.entry}: {f.reason}" for f in state.firings if f.status == "failed"]
    return runs + rules
