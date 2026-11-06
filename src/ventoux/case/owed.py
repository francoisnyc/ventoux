"""What a case owes: each required step whose latest run isn't done (brief, D72).

Pending work (brief, D10) is what has started and not ended. A required step is owed even before
it starts, so a case closes by itself only once nothing is pending and nothing is owed. What is
owed is worked out from the definition and the step's runs, never stored: so it crosses
continue-as-new and follows a migration's renames with the runs themselves. How a case says
what it owes is `owing.py`'s.
"""

from ventoux.case.admission import step_done
from ventoux.case.definition import CaseDefinition
from ventoux.case.state import CaseState


def owed(case: CaseDefinition, state: CaseState) -> list[str]:
    """Each required step, in the order written, whose latest run isn't done, with any outcome:
    never run, or ended without being done (stopped, rejected)."""
    return [name for name, step in case.steps.items() if step.required and not done(state, name)]


def done(state: CaseState, step: str) -> bool:
    """Whether the step is done, as `requires` counts it: for a repeated step, every item
    (brief, D73)."""
    return step_done(state, step)
