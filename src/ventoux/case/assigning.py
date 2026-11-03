"""Assigning an open entry: an assigner moves work between people, or back to its queue, without
its holder, and never answers it (layer 17b).

Who may answer an entry is the task's roles and an approval's exclusions; who is asked is its
holder (brief, D69). Assigning is a role the catalog registers, so no case names its assigners
(brief, D70). See docs/layers/17-assignment.md (17b).
"""

from ventoux.case.answers import AnswerRefused, why_excluded
from ventoux.case.claims import ClaimRefused, role_to_hold
from ventoux.case.definition import CallStep, CaseDefinition
from ventoux.case.state import Assigned, CaseState, Holder, OpenApproval, StepRun, Unassigned
from ventoux.core.catalog import Catalog
from ventoux.core.roles import role_that_counts


def assign(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    found: StepRun | OpenApproval,
    event: Assigned,
) -> None:
    """Give `found` to `event.to`, as `event.by` asks; or `ClaimRefused`."""
    role = refuse_unless_assigner(catalog, found.entry, event.by, event.roles)
    refuse_if_a_party(case, state, found, event.by)
    before = state.holders.get(found.entry)
    if before is not None and before.by == event.to:
        raise ClaimRefused(f"{event.to} already holds {found.entry}")  # it would change nothing
    asked = Holder(event.to, event.to_roles, at=event.at)
    # Being assigned grants nothing: the assignee is judged as their claim would be, with the
    # roles the API states for them (brief, D69) (brief, D70).
    try:
        role_to_hold(case, catalog, state, found, asked)
    except AnswerRefused as refused:
        raise ClaimRefused(
            f"{event.by} may not assign {found.entry} to {event.to}: {refused}"
        ) from None
    state.holders[found.entry] = asked
    from_whom = f", from {before.by}" if before is not None else ""
    state.history.append(f"{event.by} assigned {found.entry} to {event.to} as {role}{from_whom}")


def refuse_unless_assigner(catalog: Catalog, entry: str, by: str, roles: frozenset[str]) -> str:
    """The role that lets `by` move `entry`; or `ClaimRefused`. Fail closed: a role the catalog
    didn't register to assign counts for nothing (brief, D70)."""
    role = role_that_counts(tuple(catalog.assigners), roles, catalog.roles)
    if role is None:
        allowed = " or ".join(catalog.assigners) or "a role registered to assign"
        known = ", ".join(sorted(r for r in roles if r in catalog.roles)) or "no role"
        raise ClaimRefused(
            f"{by} may not assign {entry}: assigning is done by {allowed}, and {by} has {known}"
        )
    return role


def unassign(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    found: StepRun | OpenApproval,
    event: Unassigned,
) -> None:
    """Return `found` to its queue, without its holder, as `event.by` asks; or `ClaimRefused`. So
    an entry whose holder never acts can always be freed (brief, D70)."""
    role = refuse_unless_assigner(catalog, found.entry, event.by, event.roles)
    refuse_if_a_party(case, state, found, event.by)
    before = state.holders.get(found.entry)
    if before is None:
        raise ClaimRefused(f"nobody holds {found.entry}")
    del state.holders[found.entry]
    state.history.append(
        f"{event.by} returned {found.entry} to its queue as {role}, from {before.by}"
    )


def refuse_if_a_party(
    case: CaseDefinition, state: CaseState, found: StepRun | OpenApproval, by: str
) -> None:
    """`ClaimRefused` if `found` is an approval `by` may not give: nobody chooses their own judge.
    Whoever may not approve a step moves none of its approvals, judged by the exclusions alone,
    never by the approval's role, risk or sight (brief, D11) (brief, D70). A task is no one's
    judgement of a decision, so its runs are moved by any assigner."""
    if not isinstance(found, OpenApproval):
        return
    step = case.steps[found.step]
    assert isinstance(step, CallStep)  # only an activity or a workflow is asked for an approval
    if (why := why_excluded(case, state, found.step, step, by)) is not None:
        raise ClaimRefused(f"{by} may not assign {found.entry}: {why}")
