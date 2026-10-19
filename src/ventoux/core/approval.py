"""Approvals: who may give one, and what it is tied to (brief, D11, layer 7).

An approval is its own state (brief, D23). This module holds what only an approval checks, after
the checks every answer passes: the role may approve the activity's risk, and the person is
someone else; and the digest of the inputs it saw.
"""

import hashlib
import json
from collections.abc import Collection, Mapping

from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import ActivityContract, Contract
from ventoux.core.expressions import Expression, evaluate
from ventoux.core.plan import APPROVE, ActivityState, ApprovalState, Plan
from ventoux.core.provenance import fields_read
from ventoux.core.roles import may_approve, what_it_approves
from ventoux.core.sensitive import Sensitive
from ventoux.core.sensitive_inputs import reads_sensitive


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
    roles: tuple[str, ...], stated: frozenset[str], contract: Contract, catalog: Catalog
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


def risk_refusal(role: str, catalog: Catalog, contract: Contract) -> str:
    """Why `role` may not approve `contract`'s activity: `support may approve no risk, …`."""
    return (
        f"{role} may approve {what_it_approves(catalog.roles.get(role))}, and "
        f"{contract.reference} is {contract.risk} risk"
    )


def inputs_of(state: ApprovalState, plan: Plan) -> list[Expression]:
    """What the approved activity is given: its inputs."""
    target = plan.states[state.approval.of]
    return list(target.inputs.values()) if isinstance(target, ActivityState) else []


def conditions_of(state: ApprovalState) -> list[Expression]:
    """What decides whether the approved activity runs: the conditions on `approve`."""
    return [t.when for t in state.on.get(APPROVE, ()) if t.when is not None]


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


def not_someone_else(
    person: str,
    step: str,
    inputs: list[Expression],
    conditions: list[Expression],
    sources: Mapping[str, frozenset[str]],
    computed: Collection[str] = (),
) -> str | None:
    """Why `person` may not approve `step`: their answer is in a value it uses, or one that decides
    whether it runs (brief, D11). None: they are someone else. A field in `computed` was set by a
    case's rule from what it read, so their answer is in it without their having set it
    (brief, D42)."""
    for read, does in ((inputs, f"{step} uses"), (conditions, f"decides whether {step} runs")):
        if (field := set_by_them(person, read, sources)) is None:
            continue
        if field in computed:
            return (
                f"{person}'s answer is in {field}, which a rule computes and {does}, so cannot "
                "approve it"
            )
        return f"{person} set {field}, which {does}, so cannot approve it"
    return None


def inputs_digest(
    inputs: Mapping[str, Expression], values: Mapping[str, object]
) -> str | Sensitive:
    """The digest of the values an activity would be given now from `inputs`: what an approval
    saw, so a change, up or down, is noticed before the activity runs (brief, D11). Evaluating an
    input that can't be read raises `ExpressionError`. A plan's activity state and a case's step
    both pass their `inputs`. A digest of a sensitive value is sensitive too: a national ID's is
    reversed by trying every one (brief, D31)."""
    seen = {name: evaluate(expression, values) for name, expression in inputs.items()}
    # Canonical JSON: keys sorted, a number written as its exact text, marked apart from a text,
    # so `250` and `"250"` never share a digest.
    canonical = json.dumps(seen, sort_keys=True, default=lambda number: {"number": str(number)})
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    read = any(reads_sensitive(expression, values) for expression in inputs.values())
    return Sensitive(digest) if read else digest
