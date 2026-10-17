"""What is surely known where a step reads a value (layer 10d): which steps have surely ended, and
how, so which values are surely set (brief, D37; design question 14).

A step starts only once its requirements are met, and reads its `when` first: whatever they say
has surely happened by then. See docs/layers/10-case-validation.md (10d).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import reduce
from typing import NamedTuple

from ventoux.case.definition import ActivityStep, CaseDefinition, PlanStep, TaskStep
from ventoux.case.sequence import requirements
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

DONE = "done"  # how a step that succeeded ends


@dataclass(frozen=True)
class Known:
    """What has surely happened at some point of a case."""

    # Each step that has surely ended, and the ways it may have ended. A step left out may not
    # have run at all.
    ended: Mapping[str, frozenset[str]] = field(default_factory=dict)
    present: frozenset[str] = frozenset()  # values an `exists` said are set


def both(a: Known, b: Known) -> Known:
    """What two facts say together: every step either says ended, the ways both allow."""
    ended = {**a.ended, **b.ended}
    for name in a.ended.keys() & b.ended.keys():
        ended[name] = a.ended[name] & b.ended[name]
    return Known(ended, a.present | b.present)


def either(a: Known, b: Known) -> Known:
    """What is known whichever of two things happened: only what they agree on."""
    ended = {name: a.ended[name] | b.ended[name] for name in a.ended.keys() & b.ended.keys()}
    return Known(ended, a.present & b.present)


@dataclass(frozen=True)
class Reading:
    """A case definition read for what its steps surely know, with the contracts and plans its
    steps call (a step whose contract or plan is missing has its own error)."""

    case: CaseDefinition
    contracts: Mapping[str, Contract]
    plans: Mapping[str, object]

    def endings(self, name: str) -> frozenset[str]:
        """Every way the step may end: a task with one of its outcomes; an activity done or with
        one its contract declares; a plan done or failed; a workflow done."""
        step = self.case.steps[name]
        if isinstance(step, TaskStep):
            return frozenset(step.outcomes)
        contract = self.contracts.get(name)
        if isinstance(step, ActivityStep) and isinstance(contract, ActivityContract):
            return frozenset({DONE, *contract.outcomes})
        if isinstance(step, PlanStep):
            return frozenset({DONE, "failed"})
        return frozenset({DONE})

    def before(self, name: str, visiting: frozenset[str] = frozenset()) -> Known:
        """What has surely happened once the step's requirements are met (`sequence` included),
        and through them, what the steps it requires waited for."""
        if name in visiting:
            return Known()  # a circle: those steps never run (DEADLOCK says so), so know nothing
        found = Known()
        for requirement in requirements(self.case)[name]:
            found = both(found, self.met(requirement, visiting | {name}))
        return found

    def met(self, requirement: str, visiting: frozenset[str]) -> Known:
        """What a requirement met says: a step required has ended, some way; a milestone
        reached says one of the things that reach it happened."""
        if requirement in self.case.steps:
            ended = Known({requirement: self.endings(requirement)})
            return both(ended, self.before(requirement, visiting))
        ways = [
            both(Known({step: endings}), self.before(step, visiting))
            for step, endings in self.reachers(requirement).items()
        ]
        # A rule may reach it too, saying nothing of what steps ended or set: a way that proves
        # nothing, so the milestone proves only what every other way agrees on (brief, D38).
        ways += [Known() for rule in self.case.rules.values() if requirement in rule.then.reach]
        # Nothing reaches it: the step can never run (NEVER_RUNS says so), so know nothing.
        return reduce(either, ways) if ways else Known()

    def reachers(self, milestone: str) -> dict[str, frozenset[str]]:
        """Each step that reaches the milestone, and how it ended to reach it: an activity, a
        workflow or a plan only when done; a task with any outcome, or the outcomes that reach it."""
        found: dict[str, frozenset[str]] = {}
        for name, step in self.case.steps.items():
            if isinstance(step, TaskStep):
                ways = {o for o, outcome in step.outcomes.items() if milestone in outcome.reaches}
                if milestone in step.reaches:
                    ways = set(step.outcomes)
                if ways:
                    found[name] = frozenset(ways)
            elif milestone in step.reaches:
                found[name] = frozenset({DONE})  # reached only when done with done
        return found

    def holds(self, condition: Expression, known: Known) -> Known:
        """What is known once `condition` was read as true: the guards it holds."""
        if isinstance(condition, And):
            return reduce(lambda now, part: self.holds(part, now), condition.args, known)
        if isinstance(condition, Or):
            # True through any one of its parts: only what they all agree on, as for a milestone
            # several steps reach.
            return reduce(either, [self.holds(part, known) for part in condition.args])
        if isinstance(condition, If) and condition.args[2] is False:
            # True only through its first branch: its condition held, and so did the branch.
            return self.holds(condition.args[1], self.holds(condition.args[0], known))
        if isinstance(condition, Exists):
            return both(known, Known(present=frozenset({condition.exists})))
        if isinstance(condition, Eq | Ne | In):
            step, ways = self.ended_as(condition)
            if step is not None:
                return both(known, Known({step: ways}))
        return known  # tells nothing the check can use: a warning errs towards saying

    def ended_as(self, condition: Eq | Ne | In) -> tuple[str | None, frozenset[str]]:
        """The step whose outcome `condition` compares, and the ways it ended if it holds."""
        if isinstance(condition, In):
            compared, ways = condition.args[0], {o for o in condition.args[1] if isinstance(o, str)}
        else:
            left, right = condition.args
            compared, other = (left, right) if isinstance(left, Var) else (right, left)
            if not isinstance(other, str):
                return None, frozenset()
            ways = {other}
        step = outcome_of(self.case, compared)
        if step is None:
            return None, frozenset()
        if isinstance(condition, Ne):
            ways = set(self.endings(step)) - ways
        return step, frozenset(ways)

    def surely_set(self, name: str, known: Known) -> bool:
        """Whether the value is surely set: given at the opening, an `exists` said so, or what
        has surely ended set it every way it may have ended."""
        if name in known.present:
            return True
        step, _, value = name.partition(".")
        if value and step in self.case.steps:
            if value == "outcome":
                return step in known.ended  # set whichever way it ended
            return known.ended.get(step) == frozenset({DONE})  # an output: written only when done
        setters = set_by_outcomes(self.case).get(name)
        if setters is None:
            return True  # given at the opening (assumed: the opener's to give)
        return any(
            task in known.ended and known.ended[task] <= ways for task, ways in setters.items()
        )


def outcome_of(case: CaseDefinition, expression: Expression) -> str | None:
    """The step whose outcome `expression` is, `{"var": "review.outcome"}`, or None."""
    if not isinstance(expression, Var):
        return None
    step, _, value = expression.var.partition(".")
    return step if value == "outcome" and step in case.steps else None


def set_by_outcomes(case: CaseDefinition) -> dict[str, dict[str, frozenset[str]]]:
    """Each field a task's form sets, and for each task setting it, the outcomes that do."""
    found: dict[str, dict[str, set[str]]] = {}
    for task, step in case.steps.items():
        if isinstance(step, TaskStep):
            for way, outcome in step.outcomes.items():
                for name in outcome.sets:
                    found.setdefault(name, {}).setdefault(task, set()).add(way)
    return {
        name: {task: frozenset(ways) for task, ways in by.items()} for name, by in found.items()
    }


class Read(NamedTuple):
    """One value an expression reads, what is known where it reads it, and whether it is read
    every time the expression is: not inside an `if`'s branch, nor an element `count` or `sum`
    reads (an empty list reads none)."""

    value: str
    known: Known
    always: bool


def reads(
    expression: Expression, known: Known, reading: Reading, always: bool = True
) -> list[Read]:
    """Each value `expression` reads, with what is known where it reads it: inside an `if`, its
    first branch is read only once its condition held. `and` and `or` read every part
    (brief, D20), so a part guards nothing."""
    if isinstance(expression, Decimal | str | bool | Item | Exists):
        return []  # `exists` asks whether a value is set: it never fails for one that isn't
    if isinstance(expression, Var):
        return [Read(expression.var, known, always)]
    if isinstance(expression, If):
        condition, then, otherwise = expression.args
        held = reading.holds(condition, known)
        return (
            reads(condition, known, reading, always)
            + reads(then, held, reading, always=False)
            + reads(otherwise, known, reading, always=False)
        )
    if isinstance(expression, Count | Sum):
        found = reads(expression.args.over, known, reading, always)
        each = [expression.args.where]  # read for each element
        if isinstance(expression, Sum):
            each.append(expression.args.value)
        return found + [
            read for part in each if part is not None for read in reads(part, known, reading, False)
        ]
    if isinstance(expression, In):
        # The list after it holds only literals.
        return reads(expression.args[0], known, reading, always)
    if isinstance(expression, Comparison | And | Or | Not | Add | Sub | Mul | Div | Cat | String):
        return [
            read for argument in expression.args for read in reads(argument, known, reading, always)
        ]
    # Fail closed: an operator this walk doesn't know is an error, never "reads nothing"
    # (brief, D20).
    raise TypeError(f"not an expression: {type(expression).__name__}")
