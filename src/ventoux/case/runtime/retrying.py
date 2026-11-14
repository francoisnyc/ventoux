"""An operator retries a failed run: it runs again as the same run (brief, D26).
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from ventoux.case.admission import (
    RetryRefused,
    StepStopped,
    holds,
    latest_of_item,
    latest_run,
    requirements_met,
)
from ventoux.case.audit import Decision
from ventoux.case.closing import (
    close_held,
)
from ventoux.case.definition import (
    ActivityStep,
    CallStep,
    CaseDefinition,
    CaseStep,
    PlanStep,
    TaskStep,
    WaitStep,
    is_repeated,
)
from ventoux.case.freshness import stale_facts
from ventoux.case.rules import retry_rule
from ventoux.case.runtime.items import item_of, with_item
from ventoux.case.runtime.runs import listed
from ventoux.case.sequence import requirements
from ventoux.case.state import (
    CaseState,
    Command,
    Retried,
)
from ventoux.case.types import expression_problem
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import (
    render,
)
from ventoux.core.person import identifier_problem
from ventoux.core.provenance import fields_read


def operating_role(catalog: Catalog, event: Retried) -> str:
    """The role that lets `event`'s person retry: one the catalog marks as operating
    (brief, D26); or `RetryRefused`."""
    counted = sorted(role for role in event.roles if role in catalog.operators)
    if not counted:
        registered = sorted(role for role in event.roles if role in catalog.roles)
        known = listed(registered) if registered else ""
        raise RetryRefused(
            f"{event.entry} is retried by an operating role "
            f"({', '.join(catalog.operators) or 'none registered'}), and {event.by} has "
            f"{known or 'no role'}"
        )
    return counted[0]


def retry(  # noqa: C901
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    event: Retried,
    commands: list[Command],
) -> None:
    """An operator retries a failed run: it runs again as the same run, with the same key, once
    the step is checked again (brief, D26). Or `RetryRefused`."""
    # Who retried is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise RetryRefused(wrong)
    if state.phase != "open":
        raise RetryRefused(f"the case is {state.phase}: nothing starts")
    firing = next((f for f in state.firings if f.entry == event.entry), None)
    if firing is not None and firing.status == "failed":
        role = operating_role(catalog, event)
        try:
            retried = f"{event.by} retried {event.entry} as {role}"
            retry_rule(case, catalog, state, firing, retried, commands, event.at)
        except StepStopped as unreadable:
            raise RetryRefused(f"{event.entry} can't be retried: {unreadable}") from None
        return
    run = next((run for run in state.runs if run.entry == event.entry), None)
    if run is None or run.status != "failed":
        raise RetryRefused(f"{event.entry} has not failed: nothing to retry")
    if run.item is None and is_repeated(case.steps[run.step]):
        # Its items couldn't be told apart, and the list is never edited: it would fail again.
        raise RetryRefused(
            f"{event.entry} can't be retried: its list can't change, so it would fail again: "
            "close the case"
        )
    # For a repeated step, the latest run of the same item (brief, D73).
    latest = (
        latest_run(state, run.step)
        if run.item is None
        else latest_of_item(state, run.step, run.item)
    )
    if latest is not None and latest is not run:
        # Only a step's latest run runs again, so a retry of an earlier one could never start:
        # refused, rather than left waiting for nothing (brief, D26).
        failed_too = latest.status == "failed"
        then = f"retry {latest.entry}, or close the case" if failed_too else "close the case"
        raise RetryRefused(
            f"{event.entry} can't be retried: {latest.entry} has run since, and only a step's "
            f"latest run runs again: {then}"
        )
    counted = [operating_role(catalog, event)]
    step = case.steps[run.step]
    # The step is checked again: what made it fail may still hold. Fail closed: nothing starts.
    for requirement in requirements(case)[run.step]:
        if not requirements_met((requirement,), state):
            raise RetryRefused(
                f"{event.entry} can't be retried: {run.step} requires {requirement}, which "
                "hasn't completed"
            )
    if (problem := expression_problem(case, catalog, run.step, state.cases)) is not None:
        raise RetryRefused(f"{event.entry} can't be retried: {problem}")
    values = state.values
    if run.item is not None:  # a repeated run reads its item (brief, D73)
        assert isinstance(step, TaskStep | ActivityStep)
        values, _ = with_item(case, state, step, item_of(state, run.step, step, run.item))
    if step.when is not None:
        try:
            decided = holds(step.when, values, f"{run.step}'s condition")
        except StepStopped as unreadable:
            raise RetryRefused(f"{event.entry} can't be retried: {unreadable}") from None
        # A stale fact is fetched again, never trusted to refuse: the retry is taken, and
        # admission fetches the fact, if anything can, before it reads the condition again; if
        # nothing can, the run fails at once on its age (brief, D18) (brief, D33).
        if not decided and not reads_a_stale_fact(step, state, event.at):
            raise RetryRefused(f"{event.entry} can't be retried: {render(step.when)} is false now")
    # A person decided to try again: no longer a run whose stop was asked (brief, D40).
    run.status, run.reason, run.stop_requested = "retrying", "", ""
    if close_held(case, state):
        # The close waits for this retry: if it completes, its flag says so, never that it ran on
        # after a close (brief, D28) (brief, D34).
        names = " and ".join(case.closes_when)
        verb = "were" if len(case.closes_when) > 1 else "was"
        run.held_retry = f"{event.by}'s retry, after {names} {verb} reached"
    state.history.append(f"{event.by} retried {event.entry} as {counted[0]}")
    state.deciding.append(Decision("retried", step=run.step, entry=run.entry))
    # A person decided to try again: a fact the step needs fresh may be fetched again, unless a
    # refresh of it is still on its way (brief, D33). A stopped refresh counts for nothing, even
    # while it runs on (brief, D40).
    for field in step.max_age if isinstance(step, CallStep | PlanStep) else {}:
        prior = state.refreshing.get(field)
        if prior is None:
            continue
        refresh = next(r for r in state.runs if r.entry == prior)
        if refresh.status in ("done", "failed") or refresh.stop_requested:
            del state.refreshing[field]


def reads_a_stale_fact(
    step: TaskStep | CallStep | PlanStep | CaseStep | WaitStep, state: CaseState, at: int
) -> bool:
    """Whether the step's condition reads a fact the step needs fresh that is too old at `at`."""
    if not isinstance(step, CallStep | PlanStep) or step.when is None:
        return False
    read = fields_read(step.when)
    return any(stale.field in read for stale in stale_facts(step.max_age, state, at))
