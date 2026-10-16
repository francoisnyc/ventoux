"""Teaching warnings (layer 10d): what a definition may mean, but that surprises its author when a
case runs. Each describes what the runtime really does with the definition (brief, D37).
See docs/layers/10-case-validation.md (10d) and docs/guides/cases.md, "What the check warns about".
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from decimal import Decimal

from ventoux.case.definition import (
    ActivityStep,
    CallStep,
    CaseDefinition,
    PlanStep,
    TaskStep,
    WorkflowStep,
)
from ventoux.case.known import DONE, Known, Read, Reading, reads, set_by_outcomes
from ventoux.case.runtime import listed
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
from ventoux.core.provenance import fields_read
from ventoux.core.validate import Issue


def warning_issues(
    case: CaseDefinition,
    contracts: Mapping[str, Contract],
    plans: Mapping[str, Plan],
    said: Collection[str],
    missing: Collection[str],
) -> list[Issue]:
    """10d's issues, given the paths an issue already names (`said`) and the steps that are
    `missing` their contract or plan, or refused by an error: one cause, one issue (brief, D35).
    Such a step gets none of these, and nor does what it would give."""
    reading = Reading(case, contracts, plans)
    unset = unset_reads(reading, said, missing)
    # An outcome that leaves an output another step reads is said by that read: the reading step
    # fails, and someone hears of it.
    failing = {read.value.partition(".")[0] for read in unset if read.ended_otherwise(reading)}
    found = outcome_issues(case, contracts, plans, failing)
    found += [unset_issue(reading, read) for read in unset]
    return found + refresh_issues(case, contracts, missing) + elsewhere_issues(case, missing)


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
    always: bool  # read every time the step starts: not inside an `if`'s branch

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
        if name in missing:
            continue  # refused already: one cause, one issue
        before = reading.before(name)
        # Its `when` is read first; once true, what it says guards the rest (`admit`).
        guarded = before if step.when is None else reading.holds(step.when, before)
        warned: set[str] = set()  # one issue per value and step
        for where, expression, _ in expressions_of(step):
            if f"steps.{name}.{where}" in said:
                continue
            known = before if where == "when" else guarded
            for value, at, always in step_reads(where, expression, known, reading):
                if value.partition(".")[0] in missing or value in warned:
                    continue
                if not reading.surely_set(value, at):
                    warned.add(value)
                    found.append(Unset(name, where, value, at, always))
    return found


def step_reads(where: str, expression: Expression, known: Known, reading: Reading) -> list[Read]:
    """What a step's expression reads, as the runtime reads it. A condition is evaluated: an
    `if` reads only the branch it takes. An input also needs where its value comes from, which
    is worked out from every value it names, both branches of an `if` and an `exists` included
    (brief, D36): so each is read every time, and only the step's `when` guards them."""
    if where.startswith("inputs."):
        return [Read(value, known, True) for value in fields_read(expression)]
    return reads(expression, known, reading)


def unset_issue(reading: Reading, read: Unset) -> Issue:
    """The read's issue: an error when it fails every time (`SET_AFTER`), a warning otherwise."""
    writers = writers_of(reading, read.value)
    if set_after(reading, read, writers):
        gives = "gives" if read.value.partition(".")[0] in reading.case.steps else "sets"
        who, run = (writers[0], "runs") if len(writers) == 1 else (" or ".join(writers), "run")
        return Issue(
            f"steps.{read.step}.{read.where}",
            "SET_AFTER",
            f"{read.step} reads {read.value}, which only {who} {gives}, and {who} {run} only "
            f"after {read.step}: {read.step} fails every time it starts: read it in a step that "
            f"comes after {who}, or run {read.step} after {who}",
        )
    if writers and all(read.step in reading.before(writer).ended for writer in writers):
        # Read only on some runs, and set only after: requiring the writer would be a circle.
        gives = "gives" if read.value.partition(".")[0] in reading.case.steps else "sets"
        who, run = (writers[0], "runs") if len(writers) == 1 else (" or ".join(writers), "run")
        message = (
            f"{read.step} reads {read.value}, which only {who} {gives}, and {who} {run} only "
            f"after {read.step}: when {read.step} reads it, it fails and needs attention: read "
            f"it in a step that comes after {who}"
        )
    else:
        message = unset_message(reading, read.step, read.value, read.known)
    return Issue(f"steps.{read.step}.{read.where}", "MAY_BE_UNSET", message, "warning")


def writers_of(reading: Reading, value: str) -> list[str]:
    """The steps that set `value`: the step whose outcome or output it is, or the tasks whose
    form sets it. None for a value given at the opening."""
    step = value.partition(".")[0]
    if step in reading.case.steps:
        return [step]
    return list(set_by_outcomes(reading.case).get(value, {}))


def set_after(reading: Reading, read: Unset, writers: list[str]) -> bool:
    """Whether the read fails every time its step starts: it is read on every start, and every
    writer of the value waits for the step to be done. The value can be set only once the step
    is done, and the step is done only after a run that read it: so no run of it, retried or
    proposed, ever succeeds (brief, D34) (brief, D37)."""
    if not read.always:
        return False  # inside an `if`'s branch: a run that doesn't take it may succeed
    return bool(writers) and all(read.step in reading.before(writer).ended for writer in writers)


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


def refresh_issues(
    case: CaseDefinition, contracts: Mapping[str, Contract], refused: Collection[str]
) -> list[Issue]:
    """A `max_age` on a fact that can never be fetched again: each time it is stale, the step
    needs attention and a person decides (brief, D33) (brief, D37). Only a read is fetched
    again, and only if it needs no approval: a refresh never asks for one. Not for a step, or a
    fact from a step, that an error already refuses."""
    found: list[Issue] = []
    for name, step in case.steps.items():
        if name in refused or isinstance(step, TaskStep):
            continue
        for value in step.max_age:
            writer = value.partition(".")[0]
            if writer in refused:
                continue
            why = never_fetched(case, contracts, value)
            if why is not None:
                found.append(
                    Issue(
                        f"steps.{name}.max_age.{value}",
                        "NEVER_REFRESHED",
                        f"{value} comes from {why}: whenever it is older than {name}'s max_age "
                        f"allows, {name} needs attention: keep it only if a person should decide "
                        "each time",
                        "warning",
                    )
                )
    return found


def never_fetched(
    case: CaseDefinition, contracts: Mapping[str, Contract], value: str
) -> str | None:
    """Why `value` can never be fetched again, as the runtime's `refreshable` says; None if it
    is a read that can be."""
    writer = value.partition(".")[0]
    step = case.steps.get(writer)
    if step is None:
        setters = set_by_outcomes(case).get(value)
        if setters is not None:
            return f"a person, in {' or '.join(setters)}, and can't be fetched again"
        return "the opening, and can't be fetched again"
    if isinstance(step, TaskStep):
        return f"a person, in {writer}, and can't be fetched again"
    if isinstance(step, PlanStep):
        return f"{writer}, a plan step, which isn't run again unasked"
    if isinstance(step, WorkflowStep):
        return f"{writer}, a workflow step, which isn't run again unasked"
    contract = contracts[writer]
    if contract.effect == "compute":
        return f"{writer}, which computes it (compute), so running it again gives nothing new"
    if contract.effect != "read":
        return f"{writer}, which has side effects ({contract.effect}), and can't be run again"
    if step.approval is not None and step.approval.when is None:
        # A refresh passes the same gate as any start, and never asks for an approval.
        return f"{writer}, a read that always needs an approval, which a refresh never asks for"
    return None


def elsewhere_issues(case: CaseDefinition, refused: Collection[str]) -> list[Issue]:
    """An approval whose `when` reads none of the fields its step's inputs read: it guards a
    neighbouring value, not the one the step sends (brief, D9) (brief, D37). An approval with no
    `when` guards every run; a step given nothing has nothing to guard."""
    found: list[Issue] = []
    for name, step in case.steps.items():
        if name in refused or not isinstance(step, CallStep) or step.approval is None:
            continue
        if step.approval.when is None:
            continue
        given = list(dict.fromkeys(f for e in step.inputs.values() for f in fields_read(e)))
        read = list(dict.fromkeys(fields_read(step.approval.when)))
        if given and not set(read) & set(given):
            found.append(
                Issue(
                    f"steps.{name}.approval.when",
                    "APPROVAL_ELSEWHERE",
                    f"{name}'s approval reads {listed(read)}, and {name} is given only "
                    f"{listed(given)}: it guards a value {name} doesn't use: read one of those in "
                    "its when",
                    "warning",
                )
            )
    return found
