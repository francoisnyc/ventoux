"""Whether what a run gave can be taken, and where it lands in the case file.
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from pydantic import ValidationError

from ventoux.case.definition import (
    PlanStep,
)
from ventoux.case.runtime.runs import DONE, FAILED
from ventoux.case.state import (
    CaseState,
    Completed,
    Obtained,
)
from ventoux.core.before_activity import (
    one_line,
)
from ventoux.core.contract import ActivityContract, Contract
from ventoux.core.dates import date_fields, given_day
from ventoux.core.expressions import (
    a_kind,
)
from ventoux.core.output_sources import is_held, output_sources


def write_outputs(
    state: CaseState,
    step: str,
    contract: Contract,
    event: Completed,
    steered: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Each field the contract declares lands in the case file as `<step>.<field>`, tagged with
    the source the contract declares for it, never one the activity sends back (brief, D29), and
    what steered the run, if anything did (brief, D43). Gives each field's sources, for the
    history."""
    # Pydantic: `model_validate` checks a dict against the model's fields and builds the model; a
    # field the model doesn't declare is left out, so it never reaches the case file.
    given = contract.output.model_validate(event.output)
    said: dict[str, str] = {}
    for name, source in output_sources(contract.output).items():
        state.values[f"{step}.{name}"] = getattr(given, name)
        state.sources[f"{step}.{name}"] = frozenset({source}) | steered
        state.obtained[f"{step}.{name}"] = Obtained(event.at, event.entry)  # by this run
        said[name] = ", ".join(sorted(state.sources[f"{step}.{name}"]))
    return said


def plan_outcome_problem(step: PlanStep, event: Completed) -> str | None:
    """Why how the plan ended can't be taken, or None: a plan ends done (it succeeded) or
    `failed` (a failed final state), and gives no output to the case (brief, D28)."""
    if event.outcome not in (DONE, FAILED):
        return f"{step.plan} ended with {event.outcome}: a plan ends done or failed"
    return None


def outcome_problem(contract: Contract, event: Completed) -> str | None:
    """Why what the activity gave can't be taken, or None: an outcome its contract doesn't
    declare, or an output its contract doesn't describe. Fail closed: neither is read as done."""
    if event.outcome != DONE:
        # A workflow declares no outcomes: its business result is in its output (brief, D29).
        outcomes = contract.outcomes if isinstance(contract, ActivityContract) else ()
        if event.outcome in outcomes:
            return None
        declared = ", ".join(outcomes) or "none"
        return (
            f"{contract.reference} gave the outcome {event.outcome}, which its contract doesn't "
            f"declare: its outcomes are {declared}"
        )
    # A date is read as a day, by its exact shape, before Pydantic's lax reading, which would pick
    # a day for a timestamp or a moment: Ventoux never turns a moment into a day (brief, D66).
    for name in date_fields(contract.output):
        value = event.output.get(name)
        if value is not None and given_day(value) is None:
            return (
                f"{contract.reference} gave {name} as {a_kind(value)}, which isn't a day: an "
                f"output date is a date, or a text written YYYY-MM-DD, never a moment (brief, D66)"
            )
    try:
        # Pydantic: `model_validate` checks a dict against the model's fields, or raises.
        given = contract.output.model_validate(event.output)
    except ValidationError as error:
        return (
            f"{contract.reference} gave an output its contract doesn't declare: {one_line(error)}"
        )
    # Checked again here, on nothing registration did: the case file holds values exactly, so a
    # value it can't hold fails the step, and nothing the step gave lands (brief, D20).
    for name in contract.output.model_fields:
        value = getattr(given, name)
        if not is_held(value):
            return (
                f"{contract.reference} gave {name} as {a_kind(value)}, which the case file "
                "can't hold exactly (brief, D20)"
            )
    return None
