"""Forgetting a case: proposed by one person, approved by another, then the case closes as
`forgotten` and its key is destroyed outside it (brief, D15) (brief, D32). Layer 9c.

The request checks who proposes and who approves before it asks the case; the case checks them
again here, depending on nothing the request did.
See docs/layers/09-case-data.md (9c).
"""

from ventoux.case.closing import begin_closing
from ventoux.case.definition import CaseDefinition
from ventoux.case.state import CaseState, ForgetApproved
from ventoux.core.catalog import Catalog
from ventoux.core.person import identifier_problem
from ventoux.core.roles import role_that_counts


class ForgetRefused(Exception):
    """A request to forget a case that the engine won't carry out, with the reason."""


def role_refusal(
    catalog: Catalog, case_id: str, act: str, by: str, roles: frozenset[str]
) -> str | None:
    """Why `by`, holding `roles`, may not `act` (propose or approve) forgetting `case_id`; None
    if one of their roles is registered to forget (brief, D32)."""
    # Fail closed: a role the catalog didn't register to forget counts for nothing.
    if role_that_counts(tuple(catalog.forgetters), roles, catalog.roles) is not None:
        return None
    allowed = " or ".join(catalog.forgetters) or "a role registered to forget"
    known = ", ".join(sorted(role for role in roles if role in catalog.roles)) or "no role"
    return f"forgetting {case_id} is {act} by {allowed}, and {by} has {known}"


def approval_refusal(
    catalog: Catalog, case_id: str, proposed_by: str, approved_by: str, roles: frozenset[str]
) -> str | None:
    """Why `approved_by` may not approve forgetting `case_id`, proposed by `proposed_by`; None
    if they may."""
    if (wrong := role_refusal(catalog, case_id, "approved", approved_by, roles)) is not None:
        return wrong
    # Erasure is a decision two people make (brief, D15): the proposer approves nothing of it.
    if approved_by == proposed_by:
        return f"{proposed_by} proposed forgetting {case_id}, so cannot approve it"
    return None


def forget(case: CaseDefinition, catalog: Catalog, state: CaseState, event: ForgetApproved) -> None:
    """Begin closing the case as `forgotten`, once the request is checked again here."""
    case_id = state.case.split("/")[0]  # the case's ID, before its first run's
    # Who proposed and who approved are each written one way, before they are compared
    # (brief, D22): `Pia` and `pia` would otherwise be two people.
    for by in (event.proposed_by, event.approved_by):
        if (wrong := identifier_problem(by)) is not None:
            raise ForgetRefused(wrong)
    if state.phase == "closed":
        raise ForgetRefused("the case is closed: nothing records it any more")
    if case.forgetting == "never":
        raise ForgetRefused(
            f"{case_id} keeps its records (forgetting: never): it can't be forgotten"
        )
    proposed = role_refusal(catalog, case_id, "proposed", event.proposed_by, event.proposer_roles)
    if proposed is not None:
        raise ForgetRefused(proposed)
    approved = approval_refusal(
        catalog, case_id, event.proposed_by, event.approved_by, event.approver_roles
    )
    if approved is not None:
        raise ForgetRefused(approved)
    approver = forgetting_role(catalog, event.approver_roles)
    proposer = forgetting_role(catalog, event.proposer_roles)
    state.history.append(
        f"forgetting approved by {event.approved_by} as {approver}, "
        f"proposed by {event.proposed_by} as {proposer}"
    )
    if state.phase == "closing":
        return  # already closing, with its own reason: it closes, then the key goes
    begin_closing(state, "the case is being forgotten", "forgotten")


def forgetting_role(catalog: Catalog, roles: frozenset[str]) -> str:
    """The role that let a person propose or approve forgetting, as the history names it."""
    role = role_that_counts(tuple(catalog.forgetters), roles, catalog.roles)
    assert role is not None  # checked just before: `role_refusal` said it counts
    return role
