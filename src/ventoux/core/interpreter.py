"""The interpreter: runs a plan, state by state, and records what happened (layer 5).

Pure, like all of `ventoux.core`: no clock, no randomness, no I/O. See
docs/layers/05-interpreter.md.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.expressions import evaluate
from ventoux.core.history import Ended, Entered, Event, Gave, Moved, Started, Stopped
from ventoux.core.plan import ActivityState, FinalState, Plan, Transition
from ventoux.core.provenance import CASE, Sourced

# How a run ends (docs/guides/plans.md, "Running a plan").
Status = Literal["succeeded", "failed", "waiting", "stopped"]


class RunRefused(ValueError):
    """A run that can't start: what is wrong, then what to do."""


# How the interpreter asks for an activity: its reference and inputs in, its output back. In tests a
# fake; on Temporal, `workflow.execute_activity` (layer 6). The interpreter calls nothing itself.
type Call = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class Outcome(Exception):
    """Raised by an activity for one of the outcomes its contract declares, such as `declined`."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name  # the outcome, as the contract declares it


class Stop(Exception):
    """Raised inside a step the engine won't go on with; the loop records it as `Stopped`."""


@dataclass
class PlanRun:
    """How a run ended, and what happened on the way."""

    status: Status | None = None  # None while it runs
    reason: str | None = None  # why it stopped, if it did
    history: list[Event] = field(default_factory=list[Event])  # every event, in order


async def interpret(
    plan: Plan, fields: Mapping[str, Sourced], catalog: Catalog, call: Call
) -> PlanRun:
    """Run `plan` from its `initial` state, with the `fields` the case gives it."""
    refuse_to_start(plan, fields)
    run = PlanRun(history=[Started(plan.plan, plan.version)])
    # A plan binds no new values, so its fields are the same in every state.
    values = {name: given.value for name, given in fields.items()}
    here = plan.initial
    try:
        while run.status is None:
            if here not in plan.states:
                states = ", ".join(sorted(plan.states))
                raise Stop(f"{here} is not a state of {plan.plan}: the states are {states}")
            run.history.append(Entered(here))
            state = plan.states[here]
            if isinstance(state, FinalState):
                run.history.append(Ended(state.final))
                run.status = "succeeded" if state.final == "succeeded" else "failed"
            elif isinstance(state, ActivityState):
                gave = await run_activity(state, values, catalog, call)
                run.history.append(gave)
                here = choose(here, state.on, gave.event)
                run.history.append(Moved(gave.event, here))
            else:
                # Fail closed until waits are taken (slice 5): never passed over, never spun on.
                raise Stop(f"{here} waits for an answer, which this engine can't take yet")
    except Stop as stop:
        # Fail closed: the engine never guesses past what it can't do; a person decides
        # (brief, D17).
        run.history.append(Stopped(here, str(stop)))
        run.status, run.reason = "stopped", str(stop)
    return run


async def run_activity(
    state: ActivityState, values: Mapping[str, object], catalog: Catalog, call: Call
) -> Gave:
    """Call the state's activity with its inputs, and say what it gave."""
    try:
        contract = catalog.get(state.activity)
    except NotInCatalog as missing:
        raise Stop(str(missing)) from None
    inputs = {name: evaluate(expression, values) for name, expression in state.inputs.items()}
    try:
        output = await call(contract.reference, inputs)
    except Outcome as outcome:
        # A business failure is an outcome, and only those the contract declares (brief, D17).
        if outcome.name not in contract.outcomes:
            raise Stop(
                f"{contract.reference} gave the outcome {outcome.name}, which its contract "
                f"doesn't declare: its outcomes are {', '.join(contract.outcomes) or 'none'}"
            ) from None
        return Gave(contract.reference, outcome.name, None)
    # Every other failure, whatever its kind: none is read as an outcome or ignored; a person looks
    # at it (brief, D17).
    except Exception as error:  # noqa: BLE001 (catching every kind is the rule here)
        raise Stop(f"{contract.reference} failed: {error}") from None
    try:
        # Pydantic: `model_validate` checks a dict against the model's fields, or raises.
        contract.output.model_validate(output)
    except ValidationError as error:
        raise Stop(
            f"{contract.reference} gave an output its contract doesn't declare: {one_line(error)}"
        ) from None
    return Gave(contract.reference, "done", output)


def one_line(error: ValidationError) -> str:
    """Pydantic's errors as one line: `status: Field required; amount: …`."""
    return "; ".join(
        f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in error.errors()
    )


def choose(here: str, on: Mapping[str, tuple[Transition, ...]], event: str) -> str:
    """Where `on` says to go from `here` on `event`: the first transition that holds."""
    # Fail closed: an event the plan doesn't handle is never read as "stay" or "end".
    if event not in on:
        raise Stop(f"on {event}, {here} says nowhere to go")
    for transition in on[event]:
        if transition.when is None:
            return transition.target
        # Fail closed until conditions are read (slice 4): never skipped as if false.
        raise Stop(f"on {event}, the transition to {transition.target} has a condition")
    raise Stop(f"on {event}, no transition holds")


def refuse_to_start(plan: Plan, fields: Mapping[str, Sourced]) -> None:
    """Refuse a run not given exactly the plan's fields, each saying where its value came from."""
    declared = ", ".join(sorted(plan.fields))
    problems = [
        f"{name} is missing: give every field the plan declares ({declared})"
        for name in plan.fields
        if name not in fields
    ]
    for name, given in fields.items():
        if name not in plan.fields:
            problems.append(f"{name} is not a field of {plan.plan}: its fields are {declared}")
        # Fail closed: no sources would read as a value written in the plan, which policies trust.
        elif not given.sources:
            problems.append(
                f"{name} comes with no sources: say where its value came from, such as "
                "system:opener"
            )
        # `case` is the static check's stand-in for "the case vouches for it", never an origin:
        # accepted here, it would pass `trusted_only` on the case's word
        # (docs/layers/05-interpreter.md).
        elif CASE in given.sources:
            problems.append(
                f"{name} comes from case, which only the static check uses: give the source its "
                "value really came from"
            )
    if problems:
        raise RunRefused("\n".join(problems))
