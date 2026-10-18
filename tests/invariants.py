"""What a case must show after every decision: nothing pending is silent (brief, D17, D24).

An open case that doesn't stay open has nothing pending, or shows each pending item: an open run
or approval in `waiting_for`; a failed run or rule in `needs_attention` (which lists every one);
a running run as running work; and a run an operator retried, an approval given, or a proposal
waiting to start, by what it waits for. See docs/layers/fix-retry-rejected.md, "The invariant".
"""

from ventoux.case.definition import CaseDefinition, TaskStep
from ventoux.case.state import CaseState


def unshown(case: CaseDefinition, state: CaseState) -> list[str]:
    """Each pending item of an open case that nothing shows, said in a line; empty if none."""
    if state.phase != "open" or case.stays_open:
        return []
    silent: list[str] = []
    for run in state.runs:
        if run.status == "open" and run.entry not in state.waiting:
            silent.append(f"{run.entry} is open, and waiting_for doesn't list it")
        if run.status == "retrying" and not waits_for_its_own(case, state, run.step):
            silent.append(f"{run.entry} is retried, and waits for no approval or fact of its own")
    for name, approval in state.approvals.items():
        if approval.entry not in state.waiting:
            silent.append(f"{approval.entry} is open, and waiting_for doesn't list it")
    for name, given in state.given.items():
        if not fact_on_its_way(case, state, name):
            silent.append(f"{given.entry} is given, and {name} waits for no fact")
    for name in state.waiting_to_start:
        if not fact_on_its_way(case, state, name):
            silent.append(f"{name}'s proposal waits to start, for no fact")
    return silent


def waits_for_its_own(case: CaseDefinition, state: CaseState, name: str) -> bool:
    """Whether the step's retried run waits for its approval, asked and listed, or its fact."""
    approval = state.approvals.get(name)
    asked = approval is not None and approval.entry in state.waiting
    return asked or fact_on_its_way(case, state, name)


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
