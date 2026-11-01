"""The values a case's expressions may read, each with its type, and the check of a step's
expressions against them (layer 10b). Used by case validation and by the runtime alike, each on its
own: the runtime depends on nothing validation did (brief, D34). See
docs/layers/10-case-validation.md (10b).
"""

from datetime import date
from decimal import Decimal

from pydantic.fields import FieldInfo

from ventoux.case.called import called
from ventoux.case.definition import CallStep, CaseDefinition, PlanStep, TaskStep, WaitStep
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import ActivityContract
from ventoux.core.expressions import (
    BooleanType,
    DateType,
    Expression,
    ExpressionInvalid,
    FieldType,
    NumberType,
    OutcomeType,
    ReferenceType,
    StringType,
    check,
)
from ventoux.core.expressions.check import a_type
from ventoux.core.references import references

DONE = "done"  # how every run that succeeds ends
FAILED = "failed"  # how a plan ending in a failed final state ends (brief, D28)


def case_types(case: CaseDefinition, catalog: Catalog) -> dict[str, FieldType]:
    """Every value `case` holds, by the name an expression reads it with, and its type: each field;
    each step's outcome, a closed list (brief, D9); each output its contract declares (brief, D29);
    each value an event carries (brief, D41).
    A step whose contract the catalog can't give has no values here, so reading one is an error
    (fail closed)."""
    types: dict[str, FieldType] = {name: field.declared for name, field in case.fields.items()}
    # Each value an event from outside carries, as its payload declares it (brief, D41).
    for name, event in case.events.items():
        for field, carried in event.payload.items():
            types[f"{name}.{field}"] = carried.declared
    for name, step in case.steps.items():
        if isinstance(step, WaitStep):
            continue  # a wait gives no value: its event's payload is the event's
        if isinstance(step, TaskStep):
            types[f"{name}.outcome"] = OutcomeType(outcomes=tuple(step.outcomes))
        elif isinstance(step, PlanStep):
            types[f"{name}.outcome"] = OutcomeType(outcomes=(DONE, FAILED))
        else:
            try:
                contract = called(catalog, step)
            except NotInCatalog:
                continue
            # An activity may end with a business outcome its contract declares; a workflow
            # declares none (brief, D17) (brief, D29).
            declared = contract.outcomes if isinstance(contract, ActivityContract) else ()
            types[f"{name}.outcome"] = OutcomeType(outcomes=(DONE, *declared))
            systems = references(contract.output)
            for field, info in contract.output.model_fields.items():
                found = output_type(info, systems.get(field))
                if found is not None:
                    types[f"{name}.{field}"] = found
    return types


def output_type(info: FieldInfo, system: str | None) -> FieldType | None:
    """An output's type as an expression reads it: a decimal is a number, a text a string (a reference
    to `system` if it names one), a bool a boolean, a date a date (brief, D66). None for any other:
    registration refuses those (brief, D29), so one that got through is left out, and reading it is
    an error."""
    if info.annotation is Decimal:
        return NumberType()
    if info.annotation is str:
        return StringType() if system is None else ReferenceType(system=system)
    if info.annotation is bool:
        return BooleanType()
    if info.annotation is date:  # exactly: a `datetime` output is refused at registration
        return DateType()
    return None


def fits_type(given: FieldType, wanted: FieldType) -> bool | None:
    """Whether a value of the type `given` always fits `wanted` (True), never does (False), or
    only depends on the value (None), as the runtime's `fits` and strict validation read it."""
    if isinstance(wanted, StringType):
        # A string, an outcome and a reference are all texts.
        return isinstance(given, StringType | OutcomeType | ReferenceType)
    if isinstance(wanted, OutcomeType):
        if isinstance(given, OutcomeType):
            # Every outcome it may give is one the field takes, or some aren't.
            return True if set(given.outcomes) <= set(wanted.outcomes) else None
        # A text, or a reference, may be one of them or not: that depends on the value.
        return None if isinstance(given, StringType | ReferenceType) else False
    if isinstance(wanted, NumberType | BooleanType):
        return type(given) is type(wanted)
    # Fail closed: a type the runtime's `fits` doesn't know (a list, for now) fits nothing.
    return False


def expressions_of(
    step: TaskStep | CallStep | PlanStep | WaitStep,
) -> list[tuple[str, Expression, bool]]:
    """Each expression the step reads, where it is in the step, and whether it is a condition:
    its `when`, its approval's `when`, its inputs."""
    found: list[tuple[str, Expression, bool]] = []
    if step.when is not None:
        found.append(("when", step.when, True))
    if isinstance(step, CallStep) and step.approval is not None and step.approval.when is not None:
        found.append(("approval.when", step.approval.when, True))
    if isinstance(step, CallStep | PlanStep):  # a task and a wait take no inputs
        found += [(f"inputs.{name}", expression, False) for name, expression in step.inputs.items()]
    return found


def type_problem(
    expression: Expression, types: dict[str, FieldType], condition: bool
) -> str | None:
    """Why `expression` can't be read over `types`, or None: layer 2's check, and a condition gives
    a boolean (brief, D20)."""
    try:
        found = check(expression, types)
    except ExpressionInvalid as refused:
        return str(refused)  # starts with where it is inside the expression: `==[1]: …`
    if condition and not isinstance(found, BooleanType):
        # Nothing is truthy: a condition gives true or false, never a number read as one.
        return (
            f"a condition gives a boolean, and this gives {a_type(found)}: write a comparison, "
            "such as amount > 100"
        )
    return None


def expression_problem(case: CaseDefinition, catalog: Catalog, name: str) -> str | None:
    """Why the step `name` can't read its expressions, or None: the first that doesn't check,
    said as `pay.when can't be read: …`. The runtime asks before reading them, so a misspelt
    outcome fails the step instead of reading as false (brief, D35)."""
    types = case_types(case, catalog)
    for where, expression, condition in expressions_of(case.steps[name]):
        problem = type_problem(expression, types, condition)
        if problem is not None:
            return f"{name}.{where} can't be read: {problem}"
    return None


def rule_problem(case: CaseDefinition, catalog: Catalog, name: str) -> str | None:
    """Why the rule `name` can't read its condition, or None, said as `flag_large.when can't be
    read: …`: asked before it is read, as for a step (brief, D35) (brief, D38)."""
    rule = case.rules[name]
    types = case_types(case, catalog)
    problem = None if rule.when is None else type_problem(rule.when, types, True)
    if problem is not None:
        return f"{name}.when can't be read: {problem}"
    for field, expression in rule.then.set.items():
        problem = set_problem(expression, types, case.fields[field].declared, field)
        if problem is not None:
            return f"{name}.then.set.{field} can't be read: {problem}"
    return None


def set_problem(
    expression: Expression, types: dict[str, FieldType], wanted: FieldType, field: str
) -> str | None:
    """Why `expression` can't set `field`, of the type `wanted`, or None: it doesn't check, or it
    never gives a value of the field's type (brief, D42). One that may, depending on the value
    (a text for an outcome field), is checked when it is written."""
    try:
        found = check(expression, types)
    except ExpressionInvalid as refused:
        return str(refused)
    if fits_type(found, wanted) is False:
        return f"{field} is {a_type(wanted)}, and this gives {a_type(found)}: set it from {a_type(wanted)}"
    return None
