"""A step needs a fact fresh: the run that obtained it is run again, if that is safe, before the
step starts (brief, D33).
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from typing import Literal

from ventoux.case.admission import (
    StepStopped,
    holds,
    requirements_met,
)
from ventoux.case.approvals import (
    asked_anyway,
    needs_approval,
)
from ventoux.case.called import called
from ventoux.case.definition import (
    ActivityStep,
    CallStep,
    CaseDefinition,
    PlanStep,
    WorkflowStep,
)
from ventoux.case.freshness import Stale, ago, as_said, stale_facts
from ventoux.case.runtime.runs import coming_entry
from ventoux.case.runtime.starting import required_steering, schedule
from ventoux.case.sequence import requirements
from ventoux.case.state import (
    CaseState,
    Command,
)
from ventoux.core.catalog import Catalog


class StoppedRefresh(StepStopped):
    """A step needs a fact whose refresh a rule stopped: it fails, and an operator's retry of
    its run fetches the fact again; a person's proposal of it is refused (brief, D40)."""

    def __init__(self, stopped: str, entry: str, refresh: str) -> None:
        super().__init__(f"{stopped}; retry {entry} to fetch it again")
        self.stopped = stopped  # what is wrong, without what to do
        self.refresh = refresh  # the stopped refresh's run, such as `check_order#2`

    def to_proposer(self, step: str) -> str:
        """The refusal a person proposing `step` reads: nothing failed, so nothing is retried."""
        return f"{self.stopped}; propose {step} again once {self.refresh} has landed"


def refresh_stale(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: CallStep | PlanStep,
    at: int,
    commands: list[Command],
) -> Literal["fresh", "refreshing", "waiting"]:
    """Whether every fact the step needs fresh is: `fresh`; or one is being fetched again,
    `refreshing` (scheduled now) or `waiting` (on its way). A stale fact is refreshed, never
    trusted: only one a read-only activity step obtained can be fetched again, and only once for
    the same need; any other stops the step, and a person decides (brief, D17) (brief, D33)."""
    for stale in stale_facts(step.max_age, state, at):
        if stale.age is None:  # fail closed: an age that can't be told is never fresh
            raise StepStopped(f"{stale.field} has no time obtained, so {name} can't tell its age")
        said = f"{stale.field} was obtained {ago(stale.age)} ago"
        needed = f"{name} needs it at most {as_said(stale.limit)} old"
        prior = state.refreshing.get(stale.field)
        if prior is not None and prior != stale.run:  # fetched again, and still the old value
            run = next(run for run in state.runs if run.entry == prior)
            if run.stop_requested and run.status == "running":
                # A stopped refresh counts for nothing: what needed it fails, never waits and
                # asks again, which could loop in one decision (brief, D39) (brief, D40).
                stopped = (
                    f"{said}, and {needed}: its refresh {prior} was stopped by "
                    f"{run.stop_requested}, so it counts for nothing"
                )
                raise StoppedRefresh(stopped, coming_entry(state, name), prior)
            if run.status not in ("done", "failed"):
                return "waiting"  # on its way: running, or retried by an operator
            gave = (
                f"gave {state.values[f'{run.step}.outcome']}" if run.status == "done" else "failed"
            )
            raise StepStopped(
                f"{prior} {gave}, so {stale.field} is still {ago(stale.age)} old, and {needed}"
            )
        source, why_not = refreshable(case, catalog, state, stale)
        if source is None:
            raise StepStopped(f"{said}, and {needed}: {why_not}")
        state.history.append(
            f"refreshing {stale.field} for {name}: obtained {ago(stale.age)} ago, at most "
            f"{as_said(stale.limit)}"
        )
        refreshing = case.steps[source]
        assert isinstance(refreshing, ActivityStep)  # only a read-only activity is refreshed
        # A new run, with its own key; what steered the step it fetches for steers it too, as
        # its start is a moment (brief, D43).
        needing = required_steering(case, state, name)
        schedule(case, catalog, state, source, refreshing, None, commands, needing)
        run = state.runs[-1]
        run.refresh = True
        state.refreshing[stale.field] = run.entry
        return "refreshing"
    return "fresh"


def refreshable(  # noqa: C901
    case: CaseDefinition, catalog: Catalog, state: CaseState, stale: Stale
) -> tuple[str | None, str]:
    """The step whose run obtained the stale fact, if running it again is safe: an activity whose
    contract only reads (brief, D33). Otherwise None, and why it can't be fetched again."""
    if stale.run is not None and stale.run.partition("#")[0] in case.events:
        # Sent from outside: nothing in the case can ask its sender again (brief, D41).
        return (
            None,
            f"it came from the event {stale.run}, sent from outside, so it can't be fetched again",
        )
    if stale.run is not None and stale.run.partition("#")[0] in case.rules:
        # Computed by a rule, which doesn't fire again because a fact was refreshed (brief, D42).
        return None, f"it was computed by {stale.run}, so it can't be fetched again"
    run = next((run for run in state.runs if run.entry == stale.run), None)
    if run is None:
        # Not from a run: from a person (their answer, or the opening a person made), or from the
        # system that opened the case. Nothing can ask either again.
        came = "a person" if is_from_a_person(state, stale.field) else "the opening"
        return None, f"it came from {came}, so it can't be fetched again"
    step = case.steps[run.step]
    if isinstance(step, PlanStep):
        return None, f"{run.step} is a plan step, so it isn't run again unasked"
    if isinstance(step, WorkflowStep):
        # Another team's workflow, which may run for minutes: never re-run unasked (brief, D33).
        return None, f"{run.step} is a workflow step, so it isn't run again unasked"
    assert isinstance(step, ActivityStep)  # only a task has no contract, and it gives no run's fact
    effect = called(catalog, step).effect
    if effect == "compute":
        # The same inputs give the same answer: its age is its inputs' age (brief, D33).
        return None, (
            f"{run.step} computes it from its inputs (compute), so running it again gives "
            "nothing new"
        )
    if effect != "read":
        return None, f"{run.step} has side effects ({effect}), so it can't be run again"
    # A refresh is a run like any other: it passes the same gate as a start, or doesn't run.
    # Fail closed: it never asks for an approval itself, so a step that needs one now isn't run
    # again, and a person decides (brief, D33).
    for requirement in requirements(case)[run.step]:
        if not requirements_met((requirement,), state):
            return None, (
                f"{run.step} requires {requirement}, which hasn't completed, so it isn't run again"
            )
    if step.when is not None and not holds(step.when, state.values, f"{run.step}'s condition"):
        return None, f"{run.step}'s condition is false now, so it isn't run again"
    needed = needs_approval(state, run.step, step)
    if needed or asked_anyway(case, catalog, state, step) is not None:
        return None, f"{run.step} needs an approval to run, so it isn't run again unasked"
    return run.step, ""


def is_from_a_person(state: CaseState, field: str) -> bool:
    """Whether a person gave the field's value: their answer, or the case they opened."""
    return any(source.startswith("person:") for source in state.sources.get(field, ()))


def never_waits(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: CallStep | PlanStep,
    at: int,
) -> None:
    """`StepStopped` if a fact the step needs fresh is stale: a rule's start never waits for one to
    be fetched again, since the fetch lands with no person in it, and a loop of rules could come
    round with nobody in between. An operator's retry fetches it, if anything can; the line says
    which (brief, D33) (brief, D39)."""
    for stale in stale_facts(step.max_age, state, at):
        if stale.age is None:  # fail closed: an age that can't be told is never fresh
            raise StepStopped(f"{stale.field} has no time obtained, so {name} can't tell its age")
        old = (
            f"{stale.field} was obtained {ago(stale.age)} ago, and {name} needs it at most "
            f"{as_said(stale.limit)} old"
        )
        fetched_by, why = refreshable(case, catalog, state, stale)
        if fetched_by is None:
            raise StepStopped(f"{old}: {why}")
        raise StepStopped(
            f"{old}: a rule's start doesn't wait for it to be fetched again; retry it to fetch it"
        )
