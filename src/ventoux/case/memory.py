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
from ventoux.case.state import CaseState, Completed, Event
from ventoux.core.catalog import Catalog

Activity = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class CaseRun:
    """Where a case ended: closed or not, what it waits for, and what happened."""

    closed: bool
    waiting_for: list[str]  # open tasks and approvals, in the order they opened (brief, D24)
    history: list[str]
    steps_done: frozenset[str]

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
    return CaseRun(state.closed, list(state.waiting.values()), state.history, done)


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
            output = implementations[command.activity](command.inputs)
            queue.append(Completed(command.entry, output))
    return state
