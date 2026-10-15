"""What each step calls, read against the catalog and the deployment's plans (layer 10b): the
contract or plan exists, and each step gives it what it takes. See docs/layers/10-case-validation.md (10b) and docs/guides/cases.md.
"""

from collections.abc import Mapping
from typing import Any

from ventoux.case.called import called
from ventoux.case.definition import CallStep, CaseDefinition, PlanStep, WorkflowStep
from ventoux.case.plan_step import PlanNotSupplied, supplied
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract
from ventoux.core.plan import Plan
from ventoux.core.validate import Issue


def called_contracts(
    case: CaseDefinition, catalog: Catalog
) -> tuple[dict[str, Contract], list[Issue]]:
    """The contract each activity and workflow step calls, by step; and an issue for each step
    whose contract can't be found. A step left out has its one issue: nothing else is said of it
    (one cause, one issue)."""
    found: dict[str, Contract] = {}
    issues: list[Issue] = []
    for name, step in case.steps.items():
        if not isinstance(step, CallStep):
            continue
        path = f"steps.{name}.{'workflow' if isinstance(step, WorkflowStep) else 'activity'}"
        try:
            catalog.lookup(step.called)
        except NotInCatalog as missing:
            # The catalog's own message, which names the versions it does hold.
            issues.append(Issue(path, "UNKNOWN_CONTRACT", str(missing)))
            continue
        try:
            # Read as the runtime reads it, so the two can't disagree: an activity step takes only
            # an activity contract, a workflow step only a workflow contract (brief, D29).
            found[name] = called(catalog, step)
        except NotInCatalog as other_kind:
            issues.append(Issue(path, "WRONG_KIND", str(other_kind)))
    return found, issues


def supplied_plans(
    case: CaseDefinition, plans: Mapping[str, Any]
) -> tuple[dict[str, Plan], list[Issue]]:
    """The plan each plan step runs, by step, read from `plans` as the runtime reads them; and an
    issue for each step whose plan isn't supplied or can't be read (brief, D28). A case references
    a plan, never defines one: the deployment supplies its plans, as it supplies its catalog."""
    found: dict[str, Plan] = {}
    issues: list[Issue] = []
    for name, step in case.steps.items():
        if not isinstance(step, PlanStep):
            continue
        try:
            # The runtime's own reader: a plan supplied under another reference, or one that
            # can't be read, is refused here as it is when the step starts.
            found[name] = supplied(plans, step.plan)
        except PlanNotSupplied as missing:
            fix = "" if step.plan in plans else ": supply it with the deployment's plans"
            issues.append(Issue(f"steps.{name}.plan", "UNKNOWN_PLAN", f"{missing}{fix}"))
    return found, issues
