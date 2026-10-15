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
from ventoux.core.plan import Plan, set_by
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


def contract_input_issues(case: CaseDefinition, contracts: Mapping[str, Contract]) -> list[Issue]:
    """Each activity and workflow step's inputs against its contract's: none it doesn't take, every
    one it needs, and never the idempotency key."""
    issues: list[Issue] = []
    for name, contract in contracts.items():
        step = case.steps[name]
        assert isinstance(step, CallStep)  # only a call step has a contract
        path = f"steps.{name}.inputs"
        key = contract.idempotency_key
        # The engine fills the key, from the case, the step and its run, so a retry reuses it and
        # two runs never share it (brief, D17). A definition neither sets it nor is asked for it.
        takes = {field: info for field, info in contract.input.model_fields.items() if field != key}
        for given in step.inputs:
            if given == key:
                message = f"{given} is filled by the engine, never by a definition: remove it"
                issues.append(Issue(f"{path}.{given}", "ENGINE_INPUT", message))
            elif given not in takes:
                issues.append(
                    Issue(
                        f"{path}.{given}",
                        "UNKNOWN_INPUT",
                        f"{contract.reference} has no input {given}: its inputs are "
                        f"{', '.join(sorted(takes))}",
                    )
                )
        for field, info in takes.items():
            # Pydantic: `is_required()` is true for a field declared with no default.
            if info.is_required() and field not in step.inputs:
                issues.append(
                    Issue(
                        path,
                        "MISSING_INPUT",
                        f"{contract.reference} needs the input {field}: add it to inputs",
                    )
                )
    return issues


def plan_input_issues(case: CaseDefinition, plans: Mapping[str, Plan]) -> list[Issue]:
    """Each plan step's inputs against its plan's fields: the plan is given exactly the fields it
    takes at its start, never one a person's form in it sets (brief, D9) (brief, D28)."""
    issues: list[Issue] = []
    for name, plan in plans.items():
        step = case.steps[name]
        assert isinstance(step, PlanStep)  # only a plan step runs a plan
        path = f"steps.{name}.inputs"
        setters = set_by(plan)
        takes = sorted(field for field in plan.fields if field not in setters)
        for given in step.inputs:
            if given in setters:
                problem = (
                    f"{step.plan} takes no input {given}: its wait {setters[given]} sets it; its "
                    f"inputs are {', '.join(takes)}"
                )
            elif given not in plan.fields:
                problem = f"{step.plan} has no input {given}: its inputs are {', '.join(takes)}"
            else:
                continue
            issues.append(Issue(f"{path}.{given}", "UNKNOWN_INPUT", problem))
        issues += [
            Issue(path, "MISSING_INPUT", f"{step.plan} needs the input {field}: add it to inputs")
            for field in takes
            if field not in step.inputs
        ]
    return issues
