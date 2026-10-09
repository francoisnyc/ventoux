"""Admission: may a step start now? Worked out again after every event (layer 8).

A step is admitted when its `requires` are met and its `when` holds, read from the case file.
`when` is read only once `requires` are met: before the review is done, `review.outcome` has no
value, and a missing value is an error that stops the case, never "false" (fail closed).
"""

from collections.abc import Mapping

from ventoux.case.state import CaseState, StepRun
from ventoux.core.expressions import Expression, ExpressionError, evaluate, render


class StepStopped(Exception):
    """A step the engine can't decide about: a condition it can't read. Nothing runs."""


def latest_run(state: CaseState, step: str) -> StepRun | None:
    """The step's latest run, or None if it never ran."""
    runs = [run for run in state.runs if run.step == step]
    return runs[-1] if runs else None


def requirements_met(required: tuple[str, ...], state: CaseState) -> bool:
    """Whether each name is a milestone reached, or a step whose latest run is done."""
    for name in required:
        latest = latest_run(state, name)
        if name not in state.milestones and (latest is None or latest.status != "done"):
            return False
    return True


def holds(condition: Expression, values: Mapping[str, object], whose: str) -> bool:
    """Whether `condition` is true now. Fail closed: one that can't be read stops the case, and
    anything but true or false is an error, never read as false."""
    try:
        decided = evaluate(condition, values)
    except ExpressionError as error:
        raise StepStopped(f"{whose} {render(condition)} can't be evaluated: {error}") from None
    if not isinstance(decided, bool):
        raise StepStopped(
            f"{whose} {render(condition)} gives {decided!r}: a condition gives true or false"
        )
    return decided
