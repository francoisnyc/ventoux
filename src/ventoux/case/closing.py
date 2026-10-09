"""Closing a case: by itself when nothing is left to do, or by a person with a declared reason
(brief, D10, layer 8b).

A close puts the case in **closing**: what waits for people is cancelled, saying why; nothing new
starts; activities already running finish, since a side effect can't be cut off halfway. Then the
case is **closed**. Something that completes while closing flags the case for a person.
"""

from ventoux.case.definition import CaseDefinition
from ventoux.case.state import CaseState, CloseAsked
from ventoux.core.catalog import Catalog
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
    """Put the case in closing: cancel every open task, approval and failed run, saying why, so
    the people they were assigned to see it; running activities finish (brief, D10)."""
    state.phase = "closing"
    state.closed_because = closed_because
    for run in state.runs:
        if run.status in ("open", "failed", "retrying"):
            run.status = "cancelled"
            state.waiting.pop(run.entry, None)
            state.history.append(f"cancelled {run.entry}: {cancelled_because}")
    for approval in list(state.approvals.values()):
        del state.approvals[approval.step]
        del state.waiting[approval.entry]
        state.history.append(f"cancelled {approval.entry}: {cancelled_because}")
    state.given.clear()  # an approval not yet spent starts nothing now
    state.proposers.clear()


def settle(case: CaseDefinition, state: CaseState) -> None:
    """Close the case if it is done: open with nothing left to do (unless it stays open), or
    closing with nothing still running (brief, D10)."""
    if state.phase == "open" and not case.stays_open and not pending(state):
        state.phase = "closed"
        state.history.append("closed: nothing left to do")
    elif state.phase == "closing" and not any(run.status == "running" for run in state.runs):
        state.phase = "closed"
        state.history.append(f"closed: {state.closed_because}")


def close_when_reached(case: CaseDefinition, state: CaseState) -> None:
    """Begin closing once every milestone in `closes_when` is reached (brief, D10), unless a step
    needs attention: a failed run waits for a person, never cancelled by a milestone (brief, D26).
    The case closes once it is retried to completion, or a person closes it with a reason."""
    if state.phase != "open" or not case.closes_when:
        return
    if any(run.status in ("failed", "retrying") for run in state.runs):
        return  # nothing is skipped automatically (brief, D17)
    if all(milestone in state.milestones for milestone in case.closes_when):
        names = " and ".join(case.closes_when)
        verb = "are" if len(case.closes_when) > 1 else "is"
        begin_closing(state, f"the case closes when {names} {verb} reached", f"{names} reached")


def pending(state: CaseState) -> bool:
    """Whether anything is left to do (brief, D10): a task open, an activity running, an approval
    asked or given and not yet spent, or a step failed, which waits for a person (brief, D17)."""
    unfinished = any(run.status in ("open", "running", "failed", "retrying") for run in state.runs)
    return unfinished or bool(state.approvals) or bool(state.given)
