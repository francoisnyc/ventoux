"""The interpreter: runs a plan, state by state, and records what happened (layer 5).

Pure, like all of `ventoux.core`: no clock, no randomness, no I/O. See
docs/layers/05-interpreter.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from ventoux.core.history import Ended, Entered, Event, Started
from ventoux.core.plan import FinalState, Plan
from ventoux.core.provenance import CASE, Sourced

# How a run ends (docs/guides/plans.md, "Running a plan").
Status = Literal["succeeded", "failed", "waiting", "stopped"]


class RunRefused(ValueError):
    """A run that can't start: what is wrong, then what to do."""


@dataclass
class PlanRun:
    """How a run ended, and what happened on the way."""

    status: Status | None = None  # None while it runs
    history: list[Event] = field(default_factory=list[Event])  # every event, in order


async def interpret(plan: Plan, fields: Mapping[str, Sourced]) -> PlanRun:
    """Run `plan` from its `initial` state, with the `fields` the case gives it."""
    refuse_to_start(plan, fields)
    run = PlanRun(history=[Started(plan.plan, plan.version)])
    run.history.append(Entered(plan.initial))
    state = plan.states[plan.initial]
    if isinstance(state, FinalState):
        run.history.append(Ended(state.final))
        run.status = "succeeded" if state.final == "succeeded" else "failed"
    return run


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
