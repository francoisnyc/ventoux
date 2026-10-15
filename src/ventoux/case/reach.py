"""What a case can ever reach: the steps that can complete and the milestones that can be reached,
read from the definition alone (layer 10). See docs/layers/10-case-validation.md.

Every `when` is taken as possibly true, and every outcome as possible, so whatever is left out can
never happen on any path (brief, D34).
"""

from collections.abc import Collection, Mapping
from typing import Literal

from ventoux.case.definition import (
    ActivityStep,
    CallStep,
    CaseDefinition,
    PlanStep,
    TaskStep,
    WorkflowStep,
)
from ventoux.case.sequence import requirements
from ventoux.core.catalog import Catalog, NotInCatalog


def can_happen(case: CaseDefinition, catalog: Catalog) -> set[str]:
    """Every step that can complete and every milestone that can be reached in `case`, read
    against `catalog` (its roles, and what each contract may give).

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
            if not can_start(step, catalog.roles) or after_the_close(case, catalog, name):
                continue
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


def after_the_close(case: CaseDefinition, catalog: Catalog, name: str) -> bool:
    """Whether the step `name` waits for every milestone `closes_when` names. The case is closing
    once they are all reached, and nothing new starts once they are (layer 8b) (brief, D34): such
    a step can never run."""
    before = reached_before(case, catalog, name)
    return bool(case.closes_when) and set(case.closes_when) <= set(before)


# A step `name` waits for, and how it makes a milestone sure: it `requires` it, or `reaches` it.
type Through = tuple[str, Literal["requires", "reaches"]]


def reached_before(case: CaseDefinition, catalog: Catalog, name: str) -> dict[str, Through | None]:
    """Each milestone surely reached before the step `name` can start, and the step it waits for
    that requires or reaches it, or None for a milestone it requires itself. A required step is
    done before, and so are the steps it required in turn; milestones are never undone."""
    required = requirements(case)
    found: dict[str, Through | None] = {}
    seen: set[str] = set()
    waiting = [name]
    while waiting:
        here = waiting.pop(0)
        for requirement in required[here]:
            if requirement in case.milestones:
                found.setdefault(requirement, None if here == name else (here, "requires"))
            elif requirement not in seen:
                seen.add(requirement)
                waiting.append(requirement)
                for milestone in surely_reached(case, catalog, requirement):
                    found.setdefault(milestone, (requirement, "reaches"))
    return found


def can_start(step: TaskStep | CallStep | PlanStep, roles: Collection[str]) -> bool:
    """Whether anyone can start the step: it starts by itself, or a registered role may propose
    it. A role nobody registered counts for nothing, as when the case runs (brief, D22)."""
    return step.automatic or any(role in roles for role in step.proposed_by)


def surely_reached(case: CaseDefinition, catalog: Catalog, name: str) -> tuple[str, ...]:
    """The milestones every completion of the step `name` reaches. A run done with a declared
    outcome (`declined`) is done for `requires` but reaches nothing (layer 8b), and a plan may end
    `failed`, so only a task's own `reaches`, a workflow step's (its contract declares no
    outcomes), and an activity's whose contract declares none count. Anything the catalog can't
    say counts for nothing: the check then claims less, never more."""
    step = case.steps[name]
    if isinstance(step, TaskStep | WorkflowStep):
        return step.reaches
    if isinstance(step, ActivityStep):
        try:
            contract = catalog.get(step.activity)
        except NotInCatalog:
            return ()
        return () if contract.outcomes else step.reaches
    return ()
