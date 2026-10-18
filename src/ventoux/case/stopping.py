"""Stopping a step: what a close does to the whole case, done to one step (layer 11c).

A rule's `stop` ends the run going on now: an open task is cancelled, an approval withdrawn, and
a running activity finishes, since a side effect can't be cut off halfway (brief, D10). A failed
run is never stopped (brief, D17) (brief, D26). See docs/layers/11-rules.md (11c).
"""

from ventoux.case.admission import latest_run
from ventoux.case.definition import CaseDefinition
from ventoux.case.state import CaseState, Command, StepRun
from ventoux.core.catalog import Catalog


def stop_step(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    by: str,
    said: str,
    commands: list[Command],
) -> None:
    """Stop the run of `name` going on now, for the rule's firing `by`; `said` begins the line
    the history writes when there is nothing to stop. The step may start again later
    (brief, D40)."""
    latest = latest_run(state, name)
    if latest is not None and latest.status in ("failed", "retrying"):
        # Nothing is skipped automatically: an operator retries it, or closes the case
        # (brief, D17) (brief, D26).
        state.history.append(
            f"{said}: {name} not stopped: {latest.entry} needs attention, and a failed run is "
            "never stopped"
        )
        return
    if latest is not None and latest.status == "running":
        stop_running(case, catalog, state, latest, by, said, commands)
        return
    if latest is not None and latest.status == "open":
        # A task waiting for a person: cancelled, as a close cancels it (brief, D10). An answer
        # to it is refused as closed.
        latest.status = "cancelled"
        del state.waiting[latest.entry]
        state.history.append(f"cancelled {latest.entry}: stopped by {by}")
        return
    if not stop_coming_run(state, name, by):
        state.history.append(f"{said}: {name} not stopped: no run of {name} is going on")


def stop_coming_run(state: CaseState, name: str, by: str) -> bool:
    """Stop the run about to start, if there is one: its approval asked is withdrawn, or the
    approval given lapses, and the run is recorded `cancelled`, so the step doesn't start by
    itself again (brief, D25) (brief, D40). Whether there was one."""
    why = f"stopped by {by}"
    if (approval := state.approvals.pop(name, None)) is not None:
        del state.waiting[approval.entry]
        state.withdrawn[approval.entry] = why  # an answer to it is refused, saying why
        state.history.append(f"cancelled {approval.entry}: {why}")
    elif state.given.pop(name, None) is None:
        return False
    entry = f"{name}#{sum(1 for run in state.runs if run.step == name) + 1}"
    state.runs.append(StepRun(entry, name, "cancelled", started=False))
    # Whoever proposed it, a person or a rule, proposed a run that is over (brief, D25).
    state.proposers.pop(name, None)
    state.proposed_by_rules.pop(name, None)
    state.history.append(f"{entry} cancelled: {why}")
    return True


def stop_running(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    run: StepRun,
    by: str,
    said: str,
    commands: list[Command],
) -> None:
    """Ask a running run to stop, by the mechanism its kind declares. An activity does nothing
    but finish: a side effect can't be cut off halfway (brief, D10). Asked once, never twice."""
    if run.stop_requested:
        state.history.append(f"{said}: {run.step} not stopped: its stop is already requested")
        return
    run.stop_requested = by
    state.history.append(f"{run.entry}: stop requested by {by}")
