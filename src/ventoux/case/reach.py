"""What a case can ever reach: the steps that can complete and the milestones that can be reached,
read from the definition alone (layer 10). See docs/layers/10-case-validation.md.

Every `when` is taken as possibly true, and every outcome as possible, so whatever is left out can
never happen on any path (brief, D34).
"""

from collections.abc import Mapping

from ventoux.case.definition import CaseDefinition, TaskStep
from ventoux.case.sequence import requirements


def can_happen(case: CaseDefinition) -> set[str]:
    """Every step that can complete and every milestone that can be reached in `case`.

    A fixpoint: start from nothing, add every step whose requirements are all in the set, with what
    it reaches, and repeat until a round adds nothing. Steps have no order (a case has no
    position), so one pass in the written order would miss what a later step makes possible. It
    ends: a round only adds, and there are finitely many steps and milestones to add (learning
    question 33). Starting from nothing matters: steps that wait on each other never get in.
    """
    can: set[str] = set()
    required = requirements(case)
    while True:
        before = len(can)
        for name, step in case.steps.items():
            if name not in can and all(requirement in can for requirement in required[name]):
                can |= {name, *step.reaches}
                if isinstance(step, TaskStep):  # any of its outcomes may be the answer
                    for outcome in step.outcomes.values():
                        can |= set(outcome.reaches)
        if len(can) == before:  # a round added nothing: nothing more can ever happen
            return can


def reached_by(case: CaseDefinition, milestone: str) -> list[str]:
    """The steps that reach `milestone`, on completing or by one of their outcomes, in order."""
    return [
        name
        for name, step in case.steps.items()
        if milestone in step.reaches
        or (
            isinstance(step, TaskStep)
            and any(milestone in outcome.reaches for outcome in step.outcomes.values())
        )
    ]


def waited_on(case: CaseDefinition, requirement: str) -> list[str]:
    """The steps a requirement waits on: the step it names, or the steps reaching its milestone."""
    return [requirement] if requirement in case.steps else reached_by(case, requirement)


def reachable(start: str, waits: Mapping[str, list[str]]) -> set[str]:
    """Every step `start` waits on, directly or through others (not `start`, unless in a circle)."""
    found: set[str] = set()
    waiting = list(waits[start])
    while waiting:
        here = waiting.pop()
        if here not in found:
            found.add(here)
            waiting += waits[here]
    return found


def shortest_circle(start: str, waits: Mapping[str, list[str]]) -> list[str] | None:
    """The fewest steps from `start` back to itself along `waits`, `start` at both ends, or None
    if it waits on no circle through itself. Searched breadth first: nearer steps first."""
    came_from: dict[str, str] = {}
    waiting = [start]
    while waiting:
        here = waiting.pop(0)
        for there in waits[here]:
            if there == start:
                path = [here]
                while path[-1] != start:
                    path.append(came_from[path[-1]])
                return [*reversed(path), start]
            if there not in came_from:
                came_from[there] = here
                waiting.append(there)
    return None
