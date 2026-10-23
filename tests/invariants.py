"""What a case must show after every decision: nothing pending is silent (brief, D17, D24).

An open case, whether or not it stays open, has nothing pending, or shows each pending item: an
open run, approval or change request in `waiting_for`; a failed run or rule in `needs_attention` (which lists
every one); a running run as running work; a run an operator retried, an approval given, or a
proposal waiting to start, by what it waits for; and a timer set, in `timers`, while its purpose
lasts (brief, D44). See docs/layers/fix-retry-rejected.md, "The invariant".
"""

from typing import assert_never

from ventoux.case.admission import latest_counted, requirements_met
from ventoux.case.closing import close_held
from ventoux.case.definition import CallStep, CaseDefinition, PlanStep
from ventoux.case.sequence import requirements
from ventoux.case.state import CaseState, StepRun
from ventoux.case.timers import named


class Silent(AssertionError):
    """A decision left a pending item that nothing shows: the invariant's failure, and no other."""


def unshown(case: CaseDefinition, state: CaseState) -> list[str]:
    """Each pending item of an open case that nothing shows, said in a line; empty if none."""
    if state.phase != "open":
        return []
    silent: list[str] = []
    for run in state.runs:
        # Python: `match` compares the status with each case in turn; `assert_never` makes mypy
        # refuse a status this list doesn't name, so a new one fails closed.
        match run.status:
            case "open":
                if run.entry not in state.waiting:
                    silent.append(f"{run.entry} is open, and waiting_for doesn't list it")
            case "retrying":
                if not retry_waits_for_its_own(case, state, run.step):
                    silent.append(
                        f"{run.entry} is retried, and waits for no approval or fact of its own"
                    )
            case "failed":
                pass  # in needs_attention, which lists every failed run
            case "running":
                pass  # running work
            case "done" | "rejected" | "cancelled" | "skipped":
                pass  # ended: nothing pending
            case _:
                assert_never(run.status)
    for approval in state.approvals.values():
        if approval.entry not in state.waiting:
            silent.append(f"{approval.entry} is open, and waiting_for doesn't list it")
    for request in state.changes:  # a change request waits for its approver (brief, D52)
        if request not in state.waiting:
            silent.append(f"{request} is proposed, and waiting_for doesn't list it")
    for name, given in state.given.items():
        if not waits_for_what_can_let_it_start(case, state, name):
            silent.append(f"{given.entry} is given, and {name} waits for no fact or requirement")
    for name in state.waiting_to_start:
        if not fact_on_its_way(case, state, name):
            silent.append(f"{name}'s proposal waits to start, for no fact")
    return silent + outlived(case, state)


def outlived(case: CaseDefinition, state: CaseState) -> list[str]:
    """Each timer set that has outlived its purpose: its run has ended, or the close is held, so
    it could never act (brief, D44). A set timer is shown by `timers`, which lists every one, so
    one that lives on past its purpose is pending work nobody can explain."""
    runs = {run.entry: run.status for run in state.runs}
    found: list[str] = []
    for timer in state.timers:
        said = f"{named(timer)} is set, and"
        if runs.get(timer.run) in ("done", "rejected", "cancelled", "skipped"):
            found.append(f"{said} {timer.run} has ended")
        elif close_held(case, state):
            found.append(f"{said} the close is held: it can never act")
    return found


def retry_waits_for_its_own(case: CaseDefinition, state: CaseState, name: str) -> bool:
    """Whether the step's retried run waits for what can still let it start: its approval, asked
    and listed; its fact, fetched again; or its requirements, on their way (the note, decision
    2). Admission reads `requires` before freshness, so a refresh helps a retry only once its
    requirements are met."""
    approval = state.approvals.get(name)
    if approval is not None and approval.entry in state.waiting:
        return True
    return waits_for_what_can_let_it_start(case, state, name)


def waits_for_what_can_let_it_start(
    case: CaseDefinition, state: CaseState, name: str, followed: frozenset[str] = frozenset()
) -> bool:
    """Its requirements met, whether a fact it needs fresh is on its way; otherwise whether each
    requirement that hasn't completed is. Admission reads `requires` before freshness, so a
    refresh helps only once the requirements are met (the note, decisions 2 and 5). `followed`:
    the steps already followed through a retried refresh."""
    if requirements_met(requirements(case)[name], state):
        return fact_on_its_way(case, state, name, followed)
    return requirements_on_their_way(case, state, name)


def fact_on_its_way(
    case: CaseDefinition, state: CaseState, name: str, followed: frozenset[str] = frozenset()
) -> bool:
    """Whether a fact the step needs fresh is being fetched again: its refresh is running, or an
    operator retried it and it waits, in turn, for what can let it start, as admission counts it
    (`refresh_stale`). Never back through a step already followed: two refreshes waiting for each
    other wait for nothing."""
    step = case.steps[name]
    if not isinstance(step, CallStep | PlanStep):
        return False  # a task or a wait needs no fact fresh
    runs = {run.entry: run for run in state.runs}
    for field, entry in state.refreshing.items():
        if field not in step.max_age or entry not in runs:
            continue
        refresh = runs[entry]
        if refresh.status == "running":
            return True
        retried = refresh.status == "retrying" and refresh.step not in followed | {name}
        if retried and waits_for_what_can_let_it_start(
            case, state, refresh.step, followed | {name}
        ):
            return True
    return False


def requirements_on_their_way(case: CaseDefinition, state: CaseState, name: str) -> bool:
    """Whether some step the step requires hasn't completed, and each that hasn't has a run still
    on its way, which the case shows itself: open, running, failed or retried. One that ended
    without completing (cancelled, rejected) leaves nothing to wait for (the note, decisions 2
    and 5)."""
    unmet = [r for r in requirements(case)[name] if not requirements_met((r,), state)]
    return bool(unmet) and all(on_its_way(latest_counted(state, r)) for r in unmet)


def on_its_way(run: StepRun | None) -> bool:
    """Whether a run is still on its way to completing, and shown: open in `waiting_for`, running,
    failed in `needs_attention`, or retried by an operator."""
    return run is not None and run.status in ("open", "running", "failed", "retrying")
