"""Approvals: who may give one, and what it is tied to (brief, D11, layer 7).

An approval is its own state (brief, D23). This module holds what only an approval checks, after
the checks every answer passes: the role may approve the activity's risk, and the person is
someone else; and the digest of the inputs it saw.
"""

import hashlib
import json
from collections.abc import Mapping

from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import ActivityContract
from ventoux.core.expressions import Expression, evaluate
from ventoux.core.plan import APPROVE, ActivityState, ApprovalState, Plan
from ventoux.core.provenance import fields_read
from ventoux.core.roles import may_approve, what_it_approves


class Unapprovable(Exception):
    """An approval of something that isn't an activity the catalog holds: it approves nothing."""


def approved(state: ApprovalState, plan: Plan, catalog: Catalog) -> ActivityContract:
    """The contract of the activity `state` approves, or `Unapprovable`."""
    target = plan.states.get(state.approval.of)
    if not isinstance(target, ActivityState):
        raise Unapprovable(f"{state.approval.of} is not an activity state")
    try:
        return catalog.get(target.activity)
    except NotInCatalog as missing:
        raise Unapprovable(str(missing)) from None


def approver_role(
    roles: tuple[str, ...], stated: frozenset[str], contract: ActivityContract, catalog: Catalog
) -> str | None:
    """The role that lets a person approve `contract`'s activity: the first, in order, of their
    roles that the approval lists and that may approve its risk. None: no role of theirs may."""
    able = sorted(
        role
        for role in stated
        if role in roles
        and role in catalog.roles
        and may_approve(catalog.roles[role], contract.risk)
    )
    return able[0] if able else None


def risk_refusal(role: str, catalog: Catalog, contract: ActivityContract) -> str:
    """Why `role` may not approve `contract`'s activity: `support may approve no risk, …`."""
    return (
        f"{role} may approve {what_it_approves(catalog.roles.get(role))}, and "
        f"{contract.reference} is {contract.risk} risk"
    )


def used_by(state: ApprovalState, plan: Plan) -> list[Expression]:
    """What decides the approved run: its activity's inputs, and the conditions on the
    approval's `approve` (brief, D11)."""
    target = plan.states[state.approval.of]
    inputs = list(target.inputs.values()) if isinstance(target, ActivityState) else []
    conditions = [t.when for t in state.on.get(APPROVE, ()) if t.when is not None]
    return inputs + conditions


def set_by_them(
    person: str, expressions: list[Expression], sources: Mapping[str, frozenset[str]]
) -> str | None:
    """The first field `expressions` read that `person`'s answer set, or None. "Someone else" is
    computed from where values came from, never listed by hand (brief, D11)."""
    for expression in expressions:
        for field in fields_read(expression):
            # A field nobody has set yet has no sources: nobody's answer is in it.
            if f"person:{person}" in sources.get(field, frozenset()):
                return field
    return None


def inputs_digest(state: ActivityState, values: Mapping[str, object]) -> str:
    """The digest of the values `state`'s activity would be given now: what an approval saw, so
    a change, up or down, is noticed before the activity runs (brief, D11). Evaluating an input
    that can't be read raises `ExpressionError`."""
    seen = {name: evaluate(expression, values) for name, expression in state.inputs.items()}
    # Canonical JSON: keys sorted, a number written as its exact text, marked apart from a text,
    # so `250` and `"250"` never share a digest.
    canonical = json.dumps(seen, sort_keys=True, default=lambda number: {"number": str(number)})
    return hashlib.sha256(canonical.encode()).hexdigest()
