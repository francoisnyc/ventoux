"""How a closed child case reports to its parent: one function, for every driver (brief, D74).

The parent reads this, never what a doorbell said: in memory the runner hands it over; on
Temporal the child's workflow returns it, and the parent's read activity fetches it (brief, D75).
"""

from ventoux.case.definition import CaseDefinition
from ventoux.case.state import CaseEnded, CaseState
from ventoux.case.types import DONE
from ventoux.core.provenance import Sourced


def ending_of(entry: str, child: CaseDefinition, state: CaseState, at: int) -> CaseEnded:
    """The closed child's report for the run `entry` of its parent: its outcome and who chose it,
    its closed line, the milestones it reached, and each field it reports that is set, with its
    sources (brief, D74)."""
    closed = next(line for line in reversed(state.history) if line.startswith("closed: "))
    return CaseEnded(
        entry,
        state.closed_as or DONE,
        state.closed_by if state.closed_as is not None else None,
        closed.removeprefix("closed: "),
        tuple(state.milestones),
        {
            name: Sourced(state.values[name], state.sources[name])
            for name in child.reports
            if name in state.values
        },
        at=at,
    )
