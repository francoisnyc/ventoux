"""Assigning an open entry: an assigner moves work between people, or back to its queue, without
its holder, and never answers it (layer 17b).

Who may answer an entry is the task's roles and an approval's exclusions; who is asked is its
holder (brief, D69). Assigning is a role the catalog registers, so no case names its assigners
(brief, D70). See docs/layers/17-assignment.md (17b).
"""

from ventoux.case.answers import AnswerRefused
from ventoux.case.claims import ClaimRefused, role_to_hold
from ventoux.case.definition import CaseDefinition
from ventoux.case.state import Assigned, CaseState, Holder, OpenApproval, StepRun
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
    before = state.holders.get(found.entry)
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
