"""Admission: may a step start now? Worked out again after every event (layer 8).

A step is admitted when its `requires` are met and its `when` holds, read from the case file.
`when` is read only once `requires` are met: before the review is done, `review.outcome` has no
value, and a missing value is an error that stops the case, never "false" (fail closed).
"""

from collections.abc import Mapping

from ventoux.case.definition import CaseDefinition
from ventoux.case.state import CaseState, StepRun
from ventoux.core.expressions import Expression, ExpressionError, a_kind, evaluate, render


class ProposalRefused(Exception):
    """A proposed step the engine won't start, with the reason."""


class RetryRefused(Exception):
    """A retry the engine won't make, with the reason."""


class StepStopped(Exception):
    """A step the engine can't decide about: a condition it can't read. Nothing runs."""


def latest_run(state: CaseState, step: str) -> StepRun | None:
    """The step's latest run, or None if it never ran."""
    runs = [run for run in state.runs if run.step == step]
    return runs[-1] if runs else None


def requirements_met(required: tuple[str, ...], state: CaseState) -> bool:
    """Whether each name is a milestone reached, or a step whose latest run is done."""
    for name in required:
        latest = latest_counted(state, name)
        if name not in state.milestones and (latest is None or latest.status != "done"):
            return False
    return True


def latest_counted(state: CaseState, step: str) -> StepRun | None:
    """The step's latest run that counts for `requires`: a refresh still running doesn't undo
    the run before it, so only what it changes counts once it lands (brief, D33)."""
    runs = [run for run in state.runs if run.step == step]
    while runs and runs[-1].refresh and runs[-1].status == "running":
        runs.pop()
    return runs[-1] if runs else None


def holds(condition: Expression, values: Mapping[str, object], whose: str) -> bool:
    """Whether `condition` is true now. Fail closed: one that can't be read stops the case, and
    anything but true or false is an error, never read as false."""
    try:
        decided = evaluate(condition, values)
    except ExpressionError as error:
        raise StepStopped(f"{whose} {render(condition)} can't be evaluated: {error}") from None
    if not isinstance(decided, bool):
        raise StepStopped(
            f"{whose} {render(condition)} gives {a_kind(decided)}: a condition gives true or false"
        )
    return decided


def proposal_refusal(
    case: CaseDefinition, name: str, required: tuple[str, ...], state: CaseState
) -> str | None:
    """Why the proposed step can't start now, or None if it can: admission, asked by a person.
    Who may propose it is checked before this; its `when`, after."""
    step = case.steps[name]
    latest = latest_run(state, name)
    if name in state.approvals:
        return f"{name} is waiting for its approval: {state.approvals[name].entry}"
    # Approved, and waiting for a fact fetched again: it starts on that approval, once (brief, D33).
    if name in state.given:
        return f"{name} is approved, and waits to start: {state.given[name].entry}"
    # Proposed already, and waiting for a fact: a second proposal would replace the first
    # proposer, who could then approve the run (brief, D25) (brief, D39).
    if name in state.waiting_to_start:
        return f"{name} is already proposed, and waits for its facts to be fetched again"
    if latest is not None and latest.status in ("open", "running"):
        return f"{name} is already running: {latest.entry}"
    # Nothing starts beside a failed run: a new run would skip it by another name, and with a new
    # key a side effect could happen twice; an operator retries it, or closes the case
    # (brief, D17) (brief, D26) (brief, D39).
    if latest is not None and latest.status in ("failed", "retrying"):
        return f"{latest.entry} needs attention: retry it, or close the case"
    if latest is not None and not step.repeatable:
        return f"{name} has run, and is not repeatable"
    for requirement in required:
        if not requirements_met((requirement,), state):
            missing = "completed" if requirement in case.steps else "been reached"
            return f"{name} requires {requirement}, which hasn't {missing}"
    return None
