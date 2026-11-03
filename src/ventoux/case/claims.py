"""Claiming an open entry: the holder is the one asked to answer it, never allowed to (layer 17a).

A task's roles, and an approval's exclusions, say who may answer an entry; its holder says who is
asked. Holding grants nothing, and while someone holds an entry only they answer it (brief, D69).
See docs/layers/17-assignment.md (17a).
"""

from ventoux.case.answers import AnswerRefused, judge_approval
from ventoux.case.definition import CallStep, CaseDefinition, TaskStep
from ventoux.case.state import (
    Answered,
    CaseState,
    Claimed,
    GivenBack,
    Holder,
    OpenApproval,
    StepRun,
)
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
    # One holder at a time: a claim never takes the work from someone (brief, D69).
    holder = state.holders.get(found.entry)
    if holder is not None and holder.by == event.by:
        raise ClaimRefused(f"{event.by} already holds {found.entry}")
    if holder is not None:
        raise ClaimRefused(
            f"{holder.by} holds {found.entry}; ask someone who assigns to reassign it"
        )
    claiming = Holder(event.by, event.roles, at=event.at)
    # Holding grants nothing: a claim is checked as an answer to the entry would be, so nobody is
    # asked what they couldn't answer (brief, D69).
    try:
        role = role_to_hold(case, catalog, state, found, claiming)
    except AnswerRefused as refused:
        raise ClaimRefused(f"{event.by} may not claim {found.entry}: {refused}") from None
    state.holders[found.entry] = claiming
    state.history.append(f"{event.by} claimed {found.entry} as {role}")


def role_to_hold(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    found: StepRun | OpenApproval,
    holder: Holder,
) -> str:
    """The role that would let `holder` answer `found`; or `AnswerRefused`, saying why their
    answer would be refused, or `ClaimRefused` if nobody can hold it."""
    # One entry collecting several people's approvals can't be one person's (brief, D47) (brief, D69).
    if isinstance(found, OpenApproval) and found.count > 1:
        raise ClaimRefused(f"{found.entry} needs {found.count} people, so nobody can hold it")
    step = case.steps[found.step]
    if isinstance(found, OpenApproval):
        assert isinstance(step, CallStep)  # only an activity or a workflow is asked for one
        # Judged as their approval would be, by the same checks, so the two can't drift apart.
        approving = Answered(found.entry, APPROVE, holder.by, holder.roles, at=holder.at)
        return judge_approval(case, catalog, state, found.entry, found.step, step, approving)
    assert isinstance(step, TaskStep)  # only a task's run is answered by a person
    role = role_that_counts(step.roles, holder.roles, catalog.roles)
    if role is None:
        raise AnswerRefused(
            no_role(found.entry, step.roles, holder.by, holder.roles, catalog.roles)
        )
    return role


def keep_holder(
    case: CaseDefinition, catalog: Catalog, state: CaseState, approval: OpenApproval
) -> None:
    """Give the approval just asked to whoever held the one withdrawn before it, if they could
    still answer it; otherwise leave it in its queue, saying why (brief, D25) (brief, D69)."""
    holder = state.kept.pop(approval.step, None)
    if holder is None:
        return
    try:
        role_to_hold(case, catalog, state, approval, holder)
    except (AnswerRefused, ClaimRefused) as refused:
        state.history.append(f"{approval.entry} back in its queue: {refused}")
        return
    state.holders[approval.entry] = holder
    state.history.append(f"{approval.entry} kept for {holder.by}")


def keep_holders_who_can_answer(case: CaseDefinition, catalog: Catalog, state: CaseState) -> None:
    """After a migration to `case`, send back to its queue every held entry whose holder couldn't
    answer it there, saying why: the new release may name other roles (brief, D53) (brief, D69)."""
    for entry, holder in list(state.holders.items()):
        found = held_entry(state, entry)
        if found is None:
            continue  # no longer open: its holder goes with it once the decision ends
        try:
            role_to_hold(case, catalog, state, found, holder)
        except (AnswerRefused, ClaimRefused) as refused:
            del state.holders[entry]
            state.history.append(f"{entry} back in its queue: {refused}")


def held_entry(state: CaseState, entry: str) -> StepRun | OpenApproval | None:
    """The open task run or approval named `entry`, or None if it is no longer open."""
    for run in state.runs:
        if run.status == "open" and run.entry == entry:
            return run
    for approval in state.approvals.values():
        if approval.entry == entry:
            return approval
    return None


def give_back(state: CaseState, found: StepRun | OpenApproval, event: GivenBack) -> None:
    """Return `found` to its queue, given back by its holder; or `ClaimRefused`."""
    # Only the holder gives an entry back: anyone else would free work that isn't theirs
    # (brief, D69).
    holder = state.holders.get(found.entry)
    if holder is None:
        raise ClaimRefused(f"nobody holds {found.entry}")
    if holder.by != event.by:
        raise ClaimRefused(f"{event.by} doesn't hold {found.entry}; {holder.by} does")
    del state.holders[found.entry]
    state.history.append(f"{event.by} gave back {found.entry}")


def held_by_another(state: CaseState, entry: str, by: str) -> str | None:
    """Why `by` may not answer `entry`, held by someone else; None if nobody else holds it."""
    holder = state.holders.get(entry)
    if holder is None or holder.by == by:
        return None
    return (
        f"{holder.by} holds {entry}: ask {holder.by} to give it back, or someone who assigns to "
        "reassign it"
    )


def assignees(state: CaseState) -> dict[str, str]:
    """Each held open entry and its holder, in the order the entries opened; an entry in its
    queue is absent (brief, D69). Every holder is listed, so one left on an entry no longer open
    would show."""
    held = state.holders
    opened = [entry for entry in state.waiting if entry in held]
    left = [entry for entry in held if entry not in state.waiting]
    return {entry: held[entry].by for entry in opened + left}


def let_go_of_ended(state: CaseState) -> None:
    """End the assignment of every entry no longer open: answered, withdrawn, stopped or cancelled,
    an entry's holder goes with it. Done once, after every decision, so no route that ends an entry
    can leave its holder behind (brief, D69). A withdrawn approval's holder was kept for the step's
    next entry when it was withdrawn."""
    state.holders = {entry: held for entry, held in state.holders.items() if entry in state.waiting}
