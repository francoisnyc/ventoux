"""Teaching warnings (layer 10d): what a definition may mean, but that surprises its author when a
case runs. Each describes what the runtime really does with the definition (brief, D37).
See docs/layers/10-case-validation.md (10d) and docs/guides/cases.md, "What the check warns about".
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from decimal import Decimal

from ventoux.case.definition import ActivityStep, CaseDefinition, PlanStep
from ventoux.case.known import DONE, Known, Reading, reads, set_by_outcomes
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


def warning_issues(
    case: CaseDefinition,
    contracts: Mapping[str, Contract],
    plans: Mapping[str, Plan],
    said: Collection[str],
    missing: Collection[str],
) -> list[Issue]:
    """10d's warnings, given the paths an error already names (`said`) and the steps whose
    contract or plan is `missing`: one cause, one issue (brief, D35)."""
    reading = Reading(case, contracts, plans)
    unset = unset_reads(reading, said, missing)
    # An outcome that leaves an output another step reads is said by that read: the reading step
    # fails, and someone hears of it.
    failing = {read.value.partition(".")[0] for read in unset if read.ended_otherwise(reading)}
    return outcome_issues(case, contracts, plans, failing) + [
        unset_issue(reading, read) for read in unset
    ]


def outcome_issues(
    case: CaseDefinition,
    contracts: Mapping[str, Contract],
    plans: Mapping[str, Plan],
    failing: Collection[str] = (),
) -> list[Issue]:
    """An activity step that may end with an outcome its contract declares, or a plan step that
    may end `failed`, which no condition tells from `done`: the step is done with it, reaches
    nothing, and the case goes on, with nobody told (brief, D17) (brief, D37). Not for a step in
    `failing`, whose outcome a read already says."""
    found: list[Issue] = []
    for name, step in case.steps.items():
        if name in failing:
            continue
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


@dataclass(frozen=True)
class Unset:
    """A value a step reads, where it reads it, that may not be set by then."""

    step: str
    where: str  # `when`, `approval.when` or `inputs.<input>`
    value: str
    known: Known  # what is surely known there

    def ended_otherwise(self, reading: Reading) -> bool:
        """Whether it is an output of a step that has ended, but may have ended otherwise."""
        writer, _, part = self.value.partition(".")
        return part != "outcome" and writer in self.known.ended and writer in reading.case.steps


def unset_reads(reading: Reading, said: Collection[str], missing: Collection[str]) -> list[Unset]:
    """Each value a step reads that may not be set yet when it reads it: reading a value nobody
    set fails the step, and it needs attention (brief, D9) (brief, D37). One per value and step,
    where the runtime reads it first: its `when`, then its approval's `when` and inputs, which the
    `when` guards. Nothing is said of an expression an error already names (`said`), nor of a
    value a step whose contract or plan is `missing` would give (brief, D35)."""
    found: list[Unset] = []
    for name, step in reading.case.steps.items():
        before = reading.before(name)
        # Its `when` is read first; once true, what it says guards the rest (`admit`).
        guarded = before if step.when is None else reading.holds(step.when, before)
        warned: set[str] = set()  # one issue per value and step
        for where, expression, _ in expressions_of(step):
            if f"steps.{name}.{where}" in said:
                continue
            known = before if where == "when" else guarded
            for value, at in reads(expression, known, reading):
                if value.partition(".")[0] in missing or value in warned:
                    continue
                if not reading.surely_set(value, at):
                    warned.add(value)
                    found.append(Unset(name, where, value, at))
    return found


def unset_issue(reading: Reading, read: Unset) -> Issue:
    return Issue(
        f"steps.{read.step}.{read.where}",
        "MAY_BE_UNSET",
        unset_message(reading, read.step, read.value, read.known),
        "warning",
    )


def unset_message(reading: Reading, name: str, value: str, known: Known) -> str:
    """Why `value` may not be set where `name` reads it, what happens then, and what to do."""
    fails = f"then {name} fails and needs attention"
    step, _, part = value.partition(".")
    if part and step in reading.case.steps:
        if step not in known.ended:
            return not_waited(name, value, step, "gives it")
        others = sorted(known.ended[step] - {DONE})
        return (
            f"{name} reads {value}, which {step} gives only when done, and {step} may end "
            f"{' or '.join(others)}: {fails}: read it only when {step}.outcome is done"
        )
    setters = set_by_outcomes(reading.case)[value]
    waited = [task for task in setters if task in known.ended]
    if not waited:
        tasks = " or ".join(setters)
        return not_waited(name, value, tasks, "sets it" if len(setters) == 1 else "set it")
    sets = " or ".join(f"{task}'s {way}" for task, ways in setters.items() for way in sorted(ways))
    verb = "sets" if sum(len(ways) for ways in setters.values()) == 1 else "set"
    task = waited[0]
    return (
        f"{name} reads {value}, which only {sets} {verb}, and {name} may run after {task} is "
        f"answered otherwise: {fails}: run {name} only when {task}.outcome is "
        f"{' or '.join(sorted(setters[task]))}"
    )


def not_waited(name: str, value: str, writers: str, gives: str) -> str:
    """A value read by a step that doesn't wait for whoever sets it."""
    return (
        f"{name} reads {value}, and doesn't wait for {writers}, which {gives}: if {name} runs "
        f"first, it fails and needs attention: require {writers}"
    )
