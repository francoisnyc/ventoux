"""What each step calls, read against the catalog and the deployment's plans (layer 10b): the
contract or plan exists and is of the step's kind, the step gives it what it takes, its
expressions read only the case's values, and a high-risk step has an approval its roles may give.
See docs/layers/10-case-validation.md (10b) and docs/guides/cases.md.
"""

from collections.abc import Mapping
from typing import Any

from ventoux.case.called import called
from ventoux.case.definition import (
    ActivityStep,
    CallStep,
    CaseDefinition,
    CaseInvalid,
    CaseStep,
    PlanStep,
    WorkflowStep,
    form_fields,
    parse_case,
    rule_fields,
)
from ventoux.case.plan_step import PlanNotSupplied, supplied
from ventoux.case.types import expressions_of, set_problem, step_types, type_problem
from ventoux.core.approval import risk_refusal
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract
from ventoux.core.expressions import FieldType
from ventoux.core.plan import Plan, set_by
from ventoux.core.provenance import fields_read
from ventoux.core.roles import may_approve
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


def supplied_cases(
    case: CaseDefinition, cases: Mapping[str, Any]
) -> tuple[dict[str, CaseDefinition], list[Issue]]:
    """The child each case step opens, by step, read from `cases`, stored data by reference; and
    an issue for each step whose child isn't supplied (brief, D74). A case references its child,
    never defines it: the parent's package holds it, under `cases/`."""
    found: dict[str, CaseDefinition] = {}
    issues: list[Issue] = []
    for name, step in case.steps.items():
        if not isinstance(step, CaseStep):
            continue
        path = f"steps.{name}.case"
        if step.case not in cases:
            problem = f"{step.case} isn't supplied: add it to the package's cases/"
            issues.append(Issue(path, "UNKNOWN_CASE", problem))
            continue
        # Fail closed: a child that can't be read, or is another case, never runs in its place.
        try:
            child = parse_case(cases[step.case])
        except CaseInvalid as invalid:
            issues.append(Issue(path, "UNKNOWN_CASE", f"{step.case} can't be read: {invalid}"))
            continue
        if child.case != step.case.split("@")[0]:
            problem = f"{step.case} is supplied as {child.case}: supply the case it names"
            issues.append(Issue(path, "UNKNOWN_CASE", problem))
            continue
        # One level only: a deliberate limit, so one close reaches all it must (brief, D74).
        nested = [own for own, inner in child.steps.items() if isinstance(inner, CaseStep)]
        if nested:
            problem = (
                f"{step.case} has a case step, {', '.join(nested)}: a child case opens no case of "
                "its own"
            )
            issues.append(Issue(path, "NESTED_CASE", problem))
            continue
        found[name] = child
    return found, issues


def case_input_issues(case: CaseDefinition, children: Mapping[str, CaseDefinition]) -> list[Issue]:
    """Each case step's inputs against its child's opening: a field of the child that neither its
    forms nor its rules set, as any opening is checked (brief, D74). A field it takes and isn't
    given is simply not given."""
    issues: list[Issue] = []
    for name, child in children.items():
        step = case.steps[name]
        assert isinstance(step, CaseStep)  # only a case step opens a child
        setters = {field: f"its task {task}" for field, task in form_fields(child).items()}
        setters |= {field: f"its rule {rule}" for field, rule in rule_fields(child).items()}
        takes = ", ".join(sorted(field for field in child.fields if field not in setters))
        for given in step.inputs:
            if given in setters:
                problem = (
                    f"{step.case} takes no input {given}: {setters[given]} sets it; its inputs "
                    f"are {takes}"
                )
            elif given not in child.fields:
                problem = f"{step.case} has no input {given}: its inputs are {takes}"
            else:
                continue
            issues.append(Issue(f"steps.{name}.inputs.{given}", "UNKNOWN_INPUT", problem))
    return issues


def sensitive_to_child_issues(
    case: CaseDefinition, children: Mapping[str, CaseDefinition]
) -> list[Issue]:
    """Each case step's input that reads a sensitive field into a field its child doesn't keep
    sensitive: a view can hide more than its source, never less (brief, D74)."""
    issues: list[Issue] = []
    for name, child in children.items():
        step = case.steps[name]
        assert isinstance(step, CaseStep)  # only a case step opens a child
        for given, expression in step.inputs.items():
            opening = child.fields.get(given)
            if opening is None or opening.sensitive:
                continue  # an unknown input is UNKNOWN_INPUT's (one cause, one issue)
            for read in sorted(fields_read(expression)):
                if read in case.fields and case.fields[read].sensitive:
                    issues.append(
                        Issue(
                            f"steps.{name}.inputs.{given}",
                            "SENSITIVE_TO_CHILD",
                            f"{read} is sensitive, and {step.case}'s {given} isn't: a child "
                            "keeps a sensitive value sensitive",
                        )
                    )
    return issues


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


def expression_issues(  # noqa: C901
    case: CaseDefinition, types: dict[str, FieldType], missing: set[str]
) -> list[Issue]:
    """Each expression a step or a rule reads, type-checked over the case's values. One that reads what a
    step in `missing` would give (its contract or plan can't be found) isn't said again, nor are
    such a step's own inputs: that step's issue says it (one cause, one issue)."""
    issues: list[Issue] = []
    for name, step in case.steps.items():
        for where, expression, condition in expressions_of(step):
            if name in missing and where.startswith("inputs."):
                continue
            read = fields_read(expression)
            if any(field.split(".")[0] in missing and "." in field for field in read):
                continue
            problem = type_problem(expression, step_types(case, types, name), condition)
            if problem is not None:
                issues.append(Issue(f"steps.{name}.{where}", "EXPRESSION_INVALID", problem))
    # A rule's condition too, as the runtime checks it before reading it (brief, D38).
    for name, rule in case.rules.items():
        if rule.when is None:
            continue
        if any(field.split(".")[0] in missing and "." in field for field in fields_read(rule.when)):
            continue
        if (problem := type_problem(rule.when, types, True)) is not None:
            issues.append(Issue(f"rules.{name}.when", "EXPRESSION_INVALID", problem))
    # And each value a rule sets, against its field's type (brief, D42).
    for name, rule in case.rules.items():
        for field, expression in rule.then.set.items():
            if any(
                read.split(".")[0] in missing and "." in read for read in fields_read(expression)
            ):
                continue
            declared = case.fields[field].declared
            if (problem := set_problem(expression, types, declared, field)) is not None:
                issues.append(
                    Issue(f"rules.{name}.then.set.{field}", "EXPRESSION_INVALID", problem)
                )
    return issues


def approval_issues(
    case: CaseDefinition, catalog: Catalog, contracts: Mapping[str, Contract]
) -> list[Issue]:
    """A high-risk step has an approval, and every registered role on an approval may approve its
    step's risk (brief, D11) (brief, D22). An approval with a `when` is enough: whether it is
    asked depends on values, which the runtime reads. A role nobody registered is UNKNOWN_ROLE's."""
    issues: list[Issue] = []
    for name, contract in contracts.items():
        step = case.steps[name]
        assert isinstance(step, CallStep)  # only a call step has a contract
        if step.approval is None:
            if contract.risk == "high":
                # A repeated step can have no approval yet, so "add one" can't be done
                # (brief, D48) (brief, D73).
                repeated = isinstance(step, ActivityStep) and step.for_each is not None
                needs = (
                    f"{name} is repeated, so it can have no approval: repeat a low-risk step, "
                    "or pay once"
                    if repeated
                    else f"{name} has no approval: add one"
                )
                issues.append(
                    Issue(
                        f"steps.{name}",
                        "APPROVAL_REQUIRED",
                        f"{contract.reference} is high risk, and {needs}",
                    )
                )
            continue
        issues += [
            Issue(
                f"steps.{name}.approval.roles",
                "APPROVAL_ROLE",
                f"{risk_refusal(role, catalog, contract)}: name a role that may approve "
                f"{contract.risk} risk",
            )
            for role in step.approval.roles
            if role in catalog.roles and not may_approve(catalog.roles[role], contract.risk)
        ]
    return issues
