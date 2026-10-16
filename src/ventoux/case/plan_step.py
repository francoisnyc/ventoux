"""The plan a plan step runs, from the plans a deployment supplies (layer 8c).

A case references a plan, never defines one (brief, D28). Shared by every driver, in memory and
on Temporal, so a plan is looked up the same way in both.
"""

from collections.abc import Mapping
from typing import Any

from ventoux.case.state import StartPlan
from ventoux.core.expressions import ReferenceType
from ventoux.core.plan import Plan, PlanInvalid, parse_plan


class PlanNotSupplied(Exception):
    """A plan step whose plan the deployment can't give it: what is wrong."""


def supplied(plans: Mapping[str, Any], reference: str) -> Plan:
    """The plan `reference` names (`refund-order@1`), read from `plans`; or `PlanNotSupplied`.
    Fail closed: a plan nobody supplied, one that can't be read, or one supplied under another
    reference never runs in its place."""
    if reference not in plans:
        raise PlanNotSupplied(f"no plan {reference} is available")
    try:
        plan = parse_plan(plans[reference])
    except PlanInvalid as invalid:
        raise PlanNotSupplied(f"{reference} can't be read: {invalid}") from None
    if (named := f"{plan.plan}@{plan.version}") != reference:
        raise PlanNotSupplied(f"{reference} is supplied as {named}: supply the plan it names")
    return plan


def wrong_references(plan: Plan, command: StartPlan) -> str | None:
    """Why the case can't start `plan` with what it gives, or None: a reference field takes only a
    reference field of its system, read as it is, never another system's, a text or a computed
    value, as a contract's reference input does (brief, D30) (brief, D36)."""
    problems = [
        f"{command.plan} takes {name} as a reference to {declared.system}, and is given {said}"
        for name, declared in plan.fields.items()
        if isinstance(declared, ReferenceType) and name in command.references
        for system, said in [command.references[name]]
        if system != declared.system
    ]
    return "\n".join(problems) or None
