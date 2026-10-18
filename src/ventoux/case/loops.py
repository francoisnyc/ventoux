"""Loops of starts: rules that start tasks again on every answer, with nothing to end them, read
from the definition alone (layer 11b). See docs/layers/11-rules.md (11b, choice 17).

A rule's start never waits for anything to land, so a loop of rules comes round only through a
person answering a task (brief, D39). A loop nothing in the case ends keeps a task open for ever,
so the case never closes by itself (brief, D10). Claimed only where proven (brief, D34).
"""

from dataclasses import dataclass
from itertools import pairwise

from ventoux.case.definition import AnsweredTask, CaseDefinition, TaskStep
from ventoux.case.reach import shortest_circle
from ventoux.case.sequence import requirements


@dataclass(frozen=True)
class Loop:
    """Rules that start tasks again on every answer, in the order the loop comes round."""

    rules: tuple[str, ...]  # each rule, firing on the answer of the task before it
    steps: tuple[str, ...]  # the task each rule starts again


def endless_loops(case: CaseDefinition) -> list[Loop]:
    """Each loop of starts nothing in the case ends, entered in every case: a task in it starts by
    itself as the case opens, and each answer surely starts the next one again."""
    restarts = surely_restarts(case)
    waits = {name: [step for step, _ in restarts.get(name, [])] for name in case.steps}
    found: list[Loop] = []
    looped: set[str] = set()
    for name in case.steps:
        if name in looped or (circle := shortest_circle(name, waits)) is None:
            continue
        if not any(entered(case, task) for task in circle):
            continue
        looped |= set(circle)
        # Each hop's rule: the first written that starts the next task on this one's answer.
        hops = [
            (next(rule for step, rule in restarts[here] if step == there), there)
            for here, there in pairwise(circle)  # the circle ends where it began
        ]
        # Said from the rule written first, so the message reads as the definition does.
        first = min(range(len(hops)), key=lambda i: list(case.rules).index(hops[i][0]))
        hops = hops[first:] + hops[:first]
        found.append(Loop(tuple(rule for rule, _ in hops), tuple(step for _, step in hops)))
    return found


def surely_restarts(case: CaseDefinition) -> dict[str, list[tuple[str, str]]]:
    """Each task, and each task a rule on its answer surely starts again, with that rule: the rule
    has no condition, and the task it starts has none, may run again, and requires nothing but the
    task just answered, so admission takes the start every time. A refused start ends a loop."""
    required = requirements(case)
    found: dict[str, list[tuple[str, str]]] = {}
    for rule, written in case.rules.items():
        on = written.on
        if not isinstance(on, AnsweredTask) or written.when is not None:
            continue
        for step in written.then.start:
            task = case.steps[step]
            if (
                isinstance(task, TaskStep)
                and task.repeatable
                and task.when is None
                and set(required[step]) <= {on.answered}
            ):
                found.setdefault(on.answered, []).append((step, rule))
    return found


def entered(case: CaseDefinition, name: str) -> bool:
    """Whether the task `name` surely starts as the case opens: by itself, with no condition and
    nothing required."""
    step = case.steps[name]
    return step.automatic and step.when is None and not requirements(case)[name]
