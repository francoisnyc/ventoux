"""What a case can ever reach: the steps that can complete and the milestones that can be reached,
read from the definition alone (layer 10). See docs/layers/10-case-validation.md.

Every `when` is taken as possibly true, and every outcome as possible, so whatever is left out can
never happen on any path (brief, D34).
"""

from collections.abc import Collection, Mapping
from typing import Literal

from ventoux.case.definition import (
    ActivityStep,
    After,
    AnsweredTask,
    CaseDefinition,
    EventArrived,
    Reached,
    Started,
    TaskStep,
    WorkflowStep,
    anchor,
)
from ventoux.case.rules import said, unknown_moment
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

    A rule whose moment can come adds itself and the milestones it reaches, its condition taken as
    possibly true (brief, D38). Rule names are unlike step and milestone names, so they share the
    set; there are finitely many rules too, so it still ends. A rule in the set may start a step
    too, unless its start is refused every time (brief, D39).
    """
    can: set[str] = set()
    required = requirements(case)
    while True:
        before = len(can)
        for name, rule in case.rules.items():
            if (
                name not in can
                and moment_can_come(rule.on, can)
                and not acts_after_close(case, name)
            ):
                can |= {name, *rule.then.reach}
        for name, step in case.steps.items():
            if not can_start(case, catalog, name, can) or after_the_close(case, catalog, name):
                continue
            if name not in can and all(requirement in can for requirement in required[name]):
                can |= {name, *step.reaches}
                if isinstance(step, TaskStep):  # any of its outcomes may be the answer
                    for outcome in step.outcomes.values():
                        can |= set(outcome.reaches)
        if len(can) == before:  # a round added nothing: nothing more can ever happen
            return can


def moment_can_come(moment: object, can: set[str]) -> bool:
    """Whether a rule's moment can come, given what can happen so far: the opening always; a
    milestone, a step's start or a task's answer, once it is in `can`; an event from outside
    whenever the case is open, since nothing in the case decides when it comes (brief, D41); a
    timer, once the moment it is set on can come (brief, D44)."""
    if isinstance(moment, After):
        return moment_can_come(moment.since, can)
    if isinstance(moment, Reached):
        return moment.reached in can
    if isinstance(moment, Started):
        return moment.started in can
    if isinstance(moment, AnsweredTask):
        return moment.answered in can
    if moment == "opened" or isinstance(moment, EventArrived):
        return True
    unknown_moment(moment)  # fail closed: never one that can come


def acts_after_close(case: CaseDefinition, name: str) -> bool:
    """Whether the rule `name` can act only once every `closes_when` milestone is reached: its
    moment is reaching the only one, or its timer is set on that (a timer isn't set once nothing
    new is decided). Nothing new is decided then (brief, D38) (brief, D44). Only this form is
    claimed: the check says less, never more."""
    on = anchor(case.rules[name].on)
    return (
        isinstance(on, Reached) and bool(case.closes_when) and set(case.closes_when) == {on.reached}
    )


def rules_reaching(case: CaseDefinition, milestone: str) -> list[str]:
    """The rules that may reach `milestone`, in order."""
    return [name for name, rule in case.rules.items() if milestone in rule.then.reach]


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


def can_start(case: CaseDefinition, catalog: Catalog, name: str, can: Collection[str]) -> bool:
    """Whether anyone can start the step `name`, given what can happen so far: it starts by
    itself, a registered role may propose it, or a rule in `can` starts it, its start not refused
    every time (brief, D39). The one answer every check asks. A role nobody registered counts for
    nothing, as when the case runs (brief, D22)."""
    step = case.steps[name]
    return (
        step.automatic
        or any(role in catalog.roles for role in step.proposed_by)
        or any(
            rule in can and start_refused(case, rule, name) is None for rule in starters(case, name)
        )
    )


def starters(case: CaseDefinition, name: str) -> list[str]:
    """The rules that start the step `name`, in order."""
    return [rule for rule, written in case.rules.items() if name in written.then.start]


def start_refused(case: CaseDefinition, rule: str, name: str) -> str | None:
    """Why the rule's start of the step `name` is refused every time it fires, as the check says
    it, or None if it may be taken. Claimed only where proven (brief, D34): a failed firing is
    retried later, on the case file as it is then, so a condition that may fail proves nothing
    that later could change."""
    written, may_fail = case.rules[rule].on, case.rules[rule].when is not None
    repeatable = case.steps[name].repeatable
    fires = f"{rule} can never start {name}: it fires on {said(written)}"
    # A timer on the opening fires later, when more may have happened: only the opening itself.
    if written == "opened" and not may_fail and (unmet := unmet_at_opening(case, name)) is not None:
        return f"{fires}, and {unmet}"
    # A timer set on the step's start or answer fires later, and on a start only while that run
    # lasts, so it is read as its moment is (brief, D44).
    on = anchor(written)
    # On its own moment: a step's start comes while it runs, its answer once it has run. Unless
    # a rule may stop it first and it is a task: a stopped task is cancelled at once, and the
    # start is taken; anything else runs on through the decision (brief, D40).
    stopped = isinstance(case.steps[name], TaskStep) and any(
        name in written.then.stop for written in case.rules.values()
    )
    if (
        isinstance(on, Started)
        and on.started == name
        and not (may_fail and repeatable)
        and not stopped
    ):
        return f"{fires}, while {name} is running: start it on another moment"
    if isinstance(on, AnsweredTask) and on.answered == name and not repeatable:
        return (
            f"{fires}, once {name} has run, and {name} is not repeatable: make {name} "
            "repeatable, or start it on another moment"
        )
    return None


def unmet_at_opening(case: CaseDefinition, name: str) -> str | None:
    """The first requirement of the step `name` that can't be met as the case opens, with the
    fix, or None. Nothing has completed then, and only what rules on the opening reach is reached."""
    reached = opening_reaches(case)
    for requirement in requirements(case)[name]:
        if requirement in case.steps and requirement not in case.steps[name].requires:
            return (
                f"{name} comes after {requirement} in sequence, and {requirement} can't have "
                "completed by then: start it on a later moment"
            )
        if requirement in case.steps:
            why = "which can't have completed by then"
        elif requirement not in reached:
            why = "which nothing can reach by then"
        else:
            continue
        return (
            f"{name} requires {requirement}, {why}: start it on a later moment, or remove the "
            "requirement"
        )
    return None


def on_own_moment(case: CaseDefinition, rule: str, name: str) -> bool:
    """Whether the rule fires on the step `name` starting or being answered: a moment that comes
    only once the step runs; a timer set on one of them, too (brief, D44)."""
    on = anchor(case.rules[rule].on)
    return (isinstance(on, Started) and on.started == name) or (
        isinstance(on, AnsweredTask) and on.answered == name
    )


def opening_fired(case: CaseDefinition) -> list[str]:
    """The rules that may fire as the case opens: those on the opening, then those on a milestone
    one of them may reach, and so on, every `when` taken as possibly true (brief, D38)."""
    fired: list[str] = []
    reached: set[str] = set()
    while True:
        more = [
            name
            for name, rule in case.rules.items()
            if name not in fired
            and (
                rule.on == "opened" or (isinstance(rule.on, Reached) and rule.on.reached in reached)
            )
        ]
        if not more:  # a round added nothing: it ends, over finitely many rules
            return fired
        fired += more
        reached |= {m for name in more for m in case.rules[name].then.reach}


def opening_reaches(case: CaseDefinition) -> set[str]:
    """Every milestone a rule may reach as the case opens."""
    return {m for name in opening_fired(case) for m in case.rules[name].then.reach}


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
