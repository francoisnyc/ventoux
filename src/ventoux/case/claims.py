"""Claiming an open entry: the holder is the one asked to answer it, never allowed to (layer 17a).

A task's roles, and an approval's exclusions, say who may answer an entry; its holder says who is
asked. Holding grants nothing, and while someone holds an entry only they answer it (brief, D69).
See docs/layers/17-assignment.md (17a).
"""

from ventoux.case.answers import AnswerRefused, judge_approval
from ventoux.case.definition import CallStep, CaseDefinition, TaskStep
from ventoux.case.state import Answered, CaseState, Claimed, GivenBack, OpenApproval, StepRun
from ventoux.core.catalog import Catalog
from ventoux.core.plan import APPROVE
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
    # One entry collecting several people's approvals can't be one person's (brief, D47, D69).
    if isinstance(found, OpenApproval) and found.count > 1:
        raise ClaimRefused(f"{found.entry} needs {found.count} people, so nobody can hold it")
    # One holder at a time: a claim never takes the work from someone (brief, D69).
    holder = state.holders.get(found.entry)
    if holder == event.by:
        raise ClaimRefused(f"{event.by} already holds {found.entry}")
    if holder is not None:
        raise ClaimRefused(f"{holder} holds {found.entry}; ask someone who assigns to reassign it")
    # Holding grants nothing: a claim is checked as an answer to the entry would be, so nobody is
    # asked what they couldn't answer (brief, D69).
    role = role_to_hold(case, catalog, state, found, event)
    state.holders[found.entry] = event.by
    state.history.append(f"{event.by} claimed {found.entry} as {role}")


def role_to_hold(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    found: StepRun | OpenApproval,
    event: Claimed,
) -> str:
    """The role that would let `event.by` answer `found`, or `ClaimRefused` saying why not."""
    step = case.steps[found.step]
    if isinstance(found, OpenApproval):
        assert isinstance(step, CallStep)  # only an activity or a workflow is asked for one
        # Judged as their approval would be, by the same checks, so the two can't drift apart.
        approving = Answered(found.entry, APPROVE, event.by, event.roles, at=event.at)
        try:
            return judge_approval(case, catalog, state, found.entry, found.step, step, approving)
        except AnswerRefused as refused:
            raise ClaimRefused(f"{event.by} may not claim {found.entry}: {refused}") from None
    assert isinstance(step, TaskStep)  # only a task's run is answered by a person
    role = role_that_counts(step.roles, event.roles, catalog.roles)
    if role is None:
        why = no_role(found.entry, step.roles, event.by, event.roles, catalog.roles)
        raise ClaimRefused(f"{event.by} may not claim {found.entry}: {why}")
    return role


def give_back(state: CaseState, found: StepRun | OpenApproval, event: GivenBack) -> None:
    """Return `found` to its queue, given back by its holder; or `ClaimRefused`."""
    # Only the holder gives an entry back: anyone else would free work that isn't theirs
    # (brief, D69).
    holder = state.holders.get(found.entry)
    if holder is None:
        raise ClaimRefused(f"nobody holds {found.entry}")
    if holder != event.by:
        raise ClaimRefused(f"{event.by} doesn't hold {found.entry}; {holder} does")
    del state.holders[found.entry]
    state.history.append(f"{event.by} gave back {found.entry}")


def held_by_another(state: CaseState, entry: str, by: str) -> str | None:
    """Why `by` may not answer `entry`, held by someone else; None if nobody else holds it."""
    holder = state.holders.get(entry)
    if holder is None or holder == by:
        return None
    return f"{holder} holds {entry}: ask {holder} to give it back, or someone who assigns to reassign it"


def let_go_of_ended(state: CaseState) -> None:
    """End the assignment of every entry no longer open: answered, withdrawn, stopped or cancelled,
    an entry's holder goes with it. Done once, after every decision, so no route that ends an entry
    can leave its holder behind (brief, D69)."""
    state.holders = {entry: by for entry, by in state.holders.items() if entry in state.waiting}
