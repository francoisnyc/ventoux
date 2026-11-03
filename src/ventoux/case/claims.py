"""Claiming an open entry: the holder is the one asked to answer it, never allowed to (layer 17a).

A task's roles, and an approval's exclusions, say who may answer an entry; its holder says who is
asked. Holding grants nothing, and while someone holds an entry only they answer it (brief, D69).
See docs/layers/17-assignment.md (17a).
"""

from ventoux.case.definition import CaseDefinition, TaskStep
from ventoux.case.state import CaseState, Claimed, OpenApproval, StepRun
from ventoux.core.catalog import Catalog
from ventoux.core.roles import no_role, role_that_counts


class ClaimRefused(Exception):
    """A claim the engine will not take, with the reason, naming no value (brief, D30)."""


def claim(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    found: StepRun | OpenApproval,
    event: Claimed,
) -> None:
    """Make `event.by` the holder of `found`, the open entry they claim; or `ClaimRefused`."""
    # Holding grants nothing: a claim is checked as an answer to the entry would be, so nobody is
    # asked what they couldn't answer (brief, D69).
    assert isinstance(found, StepRun)
    step = case.steps[found.step]
    assert isinstance(step, TaskStep)
    if role_that_counts(step.roles, event.roles, catalog.roles) is None:
        why = no_role(found.entry, step.roles, event.by, event.roles, catalog.roles)
        raise ClaimRefused(f"{event.by} may not claim {found.entry}: {why}")
