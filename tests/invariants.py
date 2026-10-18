"""What a case must show after every decision: nothing pending is silent (brief, D17, D24).

An open case, whether or not it stays open, has nothing pending, or shows each pending item: an
open run or approval in `waiting_for`; a failed run or rule in `needs_attention` (which lists
every one); a running run as running work; and a run an operator retried, an approval given, or
a proposal waiting to start, by what it waits for. See docs/layers/fix-retry-rejected.md, "The
invariant".
"""

from typing import assert_never

from ventoux.case.admission import latest_counted, requirements_met
from ventoux.case.definition import CaseDefinition, TaskStep
from ventoux.case.sequence import requirements
from ventoux.case.state import CaseState


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
            case "done" | "rejected" | "cancelled":
                pass  # ended: nothing pending
            case _:
                assert_never(run.status)
    for approval in state.approvals.values():
        if approval.entry not in state.waiting:
            silent.append(f"{approval.entry} is open, and waiting_for doesn't list it")
    for name, given in state.given.items():
        if not fact_on_its_way(case, state, name) and not requirement_on_its_way(case, state, name):
            silent.append(f"{given.entry} is given, and {name} waits for no fact or requirement")
    for name in state.waiting_to_start:
        if not fact_on_its_way(case, state, name):
            silent.append(f"{name}'s proposal waits to start, for no fact")
    return silent


def retry_waits_for_its_own(case: CaseDefinition, state: CaseState, name: str) -> bool:
    """Whether the step's retried run waits for its approval, asked and listed, or for its fact.
    Admission reads `requires` before freshness, so a refresh helps a retry only once its
    requirements are met (the note, decision 2)."""
    approval = state.approvals.get(name)
    if approval is not None and approval.entry in state.waiting:
        return True
    return requirements_met(requirements(case)[name], state) and fact_on_its_way(case, state, name)


def fact_on_its_way(case: CaseDefinition, state: CaseState, name: str) -> bool:
    """Whether a fact the step needs fresh is being fetched again: its refresh is running."""
    step = case.steps[name]
    if isinstance(step, TaskStep):
        return False  # a task needs no fact fresh
    runs = {run.entry: run for run in state.runs}
    return any(
        runs[entry].status == "running"
        for field, entry in state.refreshing.items()
        if field in step.max_age and entry in runs
    )


def requirement_on_its_way(case: CaseDefinition, state: CaseState, name: str) -> bool:
    """Whether a step the step requires, not completed, has a run still on its way, which the
    case shows itself: open, running, failed or retried (the note, decision 5)."""
    for required in requirements(case)[name]:
        latest = latest_counted(state, required)
        if latest is not None and latest.status in ("open", "running", "failed", "retrying"):
            return True
    return False
