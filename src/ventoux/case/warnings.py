"""Teaching warnings (layer 10d): what a definition may mean, but that surprises its author when a
case runs. Each describes what the runtime really does with the definition (brief, D37).
See docs/layers/10-case-validation.md (10d) and docs/guides/cases.md, "What the check warns about".
"""

from collections.abc import Mapping
from decimal import Decimal

from ventoux.case.definition import ActivityStep, CaseDefinition, PlanStep
from ventoux.case.types import expressions_of
from ventoux.core.contract import ActivityContract, Contract
from ventoux.core.expressions.model import (
    Add,
    And,
    Cat,
    Comparison,
    Count,
    Div,
    Eq,
    Exists,
    Expression,
    If,
    In,
    Item,
    Mul,
    Ne,
    Not,
    Or,
    String,
    Sub,
    Sum,
    Var,
)
from ventoux.core.plan import Plan
from ventoux.core.validate import Issue

DONE = "done"  # how a step that succeeded ends


def outcome_issues(
    case: CaseDefinition, contracts: Mapping[str, Contract], plans: Mapping[str, Plan]
) -> list[Issue]:
    """An activity step that may end with an outcome its contract declares, or a plan step that
    may end `failed`, which no condition tells from `done`: the step is done with it, reaches
    nothing, and the case goes on, with nobody told (brief, D17) (brief, D37)."""
    found: list[Issue] = []
    for name, step in case.steps.items():
        contract = contracts.get(name)
        if isinstance(step, ActivityStep) and isinstance(contract, ActivityContract):
            declared = list(contract.outcomes)
        elif isinstance(step, PlanStep) and name in plans:
            declared = ["failed"]  # a plan ends done or failed (brief, D28)
        else:
            continue  # a task's answer was chosen by a person; a workflow ends only done
        read = read_outcomes(case, f"{name}.outcome")
        if DONE in read:
            continue  # told from done, every one of them
        unread = [outcome for outcome in declared if outcome not in read]
        if unread:
            found.append(unread_issue(name, unread))
    return found


def unread_issue(name: str, unread: list[str]) -> Issue:
    """One issue for the step, naming every outcome nobody reads."""
    if len(unread) == 1:
        which, told, fix = unread[0], "that", unread[0]
    else:
        which, told, fix = f"{', '.join(unread[:-1])} or {unread[-1]}", "them", "one of them"
    return Issue(
        f"steps.{name}",
        "OUTCOME_UNREAD",
        f"{name} may end {which}, and no condition tells {told} from done, so the case goes on "
        f"and nobody is told: add a step that runs when {name}.outcome is {fix}",
        "warning",
    )


def read_outcomes(case: CaseDefinition, field: str) -> set[str]:
    """Every outcome of `field` (`pay.outcome`) some expression of the case tells apart."""
    return {
        outcome
        for step in case.steps.values()
        for _, expression, _ in expressions_of(step)
        for outcome in told_apart(expression, field)
    }


def told_apart(expression: Expression, field: str) -> set[str]:
    """The outcomes of `field` that `expression` tells from the others: those it compares the
    field with (`==`, `!=`, `in`). Comparing it with `done` tells every outcome from `done`, and so
    does reading it any other way, since the check never guesses: `done` then stands for all."""
    if isinstance(expression, Decimal | str | bool | Item | Exists):
        return set()  # `exists` asks whether the step ended, not how
    if isinstance(expression, Var):
        return {DONE} if expression.var == field else set()  # read as a value: all of them
    if isinstance(expression, Eq | Ne):
        left, right = expression.args
        for named, other in ((left, right), (right, left)):
            if named == Var(var=field) and isinstance(other, str):
                return {other}
    if isinstance(expression, In) and expression.args[0] == Var(var=field):
        return {option for option in expression.args[1] if isinstance(option, str)}
    if isinstance(expression, Count | Sum):
        parts = [expression.args.over, expression.args.where]
        if isinstance(expression, Sum):
            parts.append(expression.args.value)
        return {o for part in parts if part is not None for o in told_apart(part, field)}
    if isinstance(expression, In):
        return told_apart(expression.args[0], field)  # the list after it holds only literals
    if isinstance(
        expression, Comparison | And | Or | Not | Add | Sub | Mul | Div | If | Cat | String
    ):
        return {o for argument in expression.args for o in told_apart(argument, field)}
    # Fail closed: an operator this walk doesn't know is an error, never "reads nothing"
    # (brief, D20).
    raise TypeError(f"not an expression: {type(expression).__name__}")
