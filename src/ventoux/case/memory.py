"""Running a case in memory: the driver around `decide`, for tests (layer 8).

Each command is carried out at once by the activity passed in, and what it gave is fed back as
the next event. Pure, like all of `ventoux.case`: the activities are passed in, so every side
effect happens outside this module.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ventoux.case.definition import CaseDefinition
from ventoux.case.runtime import decide
from ventoux.case.state import CaseState, Completed, Event, Failed, Schedule
from ventoux.core.catalog import Catalog

Activity = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class CaseRun:
    """Where a case ended: closed or not, what it waits for, and what happened."""

    closed: bool
    waiting_for: list[str]  # open tasks and approvals, in the order they opened (brief, D24)
    needs_attention: list[str]  # failed step runs, each with its reason (brief, D17)
    history: list[str]
    steps_done: frozenset[str]

    @property
    def status(self) -> str:
        """`open` or `closed`."""
        return "closed" if self.closed else "open"

    def reached(self, step: str) -> bool:
        """Whether a run of `step` is done: a task answered, an activity finished."""
        return step in self.steps_done


def run_case_in_memory(
    case: CaseDefinition,
    catalog: Catalog,
    implementations: Mapping[str, Activity],
    events: Iterable[Event],
    name: str = "memory",
) -> CaseRun:
    """Play `events` in order, the first opening the case; `name` names the case in its keys."""
    state = CaseState(name)
    for event in events:
        state = carry(case, catalog, implementations, state, event)
    done = frozenset(run.step for run in state.runs if run.status == "done")
    attention = [f"{run.entry}: {run.reason}" for run in state.runs if run.status == "failed"]
    return CaseRun(state.closed, list(state.waiting.values()), attention, state.history, done)


def carry(
    case: CaseDefinition,
    catalog: Catalog,
    implementations: Mapping[str, Activity],
    state: CaseState,
    event: Event,
) -> CaseState:
    """Decide on `event`, then run each activity it asks for, feeding back what it gave."""
    queue = [event]
    while queue:
        state, commands = decide(case, catalog, state, queue.pop(0))
        for command in commands:
            if command.activity not in implementations:
                raise LookupError(f"no implementation of {command.activity} is available")
            queue.append(outcome_of(command, implementations[command.activity]))
    return state


def outcome_of(command: Schedule, activity: Activity) -> Completed | Failed:
    """Run the activity, and say what happened as an event. In memory there are no retries: an
    error is a failure after them (Temporal retries with the contract's policy, layer 8c)."""
    try:
        return Completed(command.entry, activity(command.inputs))
    # Any error, whatever its kind: none is ignored; a person looks at it (brief, D17).
    except Exception as error:  # noqa: BLE001 (catching every kind is the rule here)
        return Failed(command.entry, f"{command.activity} failed: {error}")
