"""What a case owes: each required step whose latest run isn't done (brief, D72).

Pending work (brief, D10) is what has started and not ended. A required step is owed even before
it starts, so a case closes by itself only once nothing is pending and nothing is owed. What is
owed is worked out from the definition and the step's runs, never stored: so it crosses
continue-as-new and follows a migration's renames with the runs themselves.
"""

from ventoux.case.admission import latest_counted
from ventoux.case.definition import CaseDefinition
from ventoux.case.state import CaseState


def owed(case: CaseDefinition, state: CaseState) -> list[str]:
    """Each required step, in the order written, whose latest run isn't done, with any outcome:
    never run, or ended without being done (stopped, rejected)."""
    return [name for name, step in case.steps.items() if step.required and not done(state, name)]


def done(state: CaseState, step: str) -> bool:
    """Whether the step's latest run, as `requires` counts it, is done."""
    latest = latest_counted(state, step)
    return latest is not None and latest.status == "done"


def waiting_for(case: CaseDefinition, state: CaseState) -> list[str]:
    """What the case waits for from people (brief, D24): each open entry, in the order it
    opened, then each owed step nothing is running for, with who may start it (brief, D72)."""
    return list(state.waiting.values()) + [
        owed_line(case, name) for name in owed(case, state) if not under_way(state, name)
    ]


def under_way(state: CaseState, step: str) -> bool:
    """Whether the step's latest run is already shown as pending work: open (in `waiting`),
    running, or failed and waiting for an operator."""
    latest = latest_counted(state, step)
    return latest is not None and latest.status in ("open", "running", "failed", "retrying")


def owed_line(case: CaseDefinition, step: str) -> str:
    """How an owed step reads in `waiting_for`: `confirm, required, proposed by support`."""
    roles = " or ".join(case.steps[step].proposed_by)
    return f"{step}, required, proposed by {roles}"
