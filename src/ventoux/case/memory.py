"""Running a case in memory: the driver around `decide`, for tests (layer 8).

Each command is carried out at once by the activity passed in, and what it gave is fed back as
the next event. Pure, like all of `ventoux.case`: the activities are passed in, so every side
effect happens outside this module.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ventoux.case.called import unbound
from ventoux.case.definition import CaseDefinition
from ventoux.case.runtime import decide
from ventoux.case.state import (
    CaseState,
    Completed,
    Event,
    Failed,
    PlanCancelled,
    Schedule,
    StartPlan,
    StartWorkflow,
    StopPlan,
)
from ventoux.case.visibility import CaseView, case_view
from ventoux.core.catalog import Catalog
from ventoux.core.interpreter import Outcome
from ventoux.core.sensitive import Sensitive, unwrapped

# An activity's code, or a workflow's in memory: its inputs in, its output back.
Activity = Callable[[dict[str, Any]], dict[str, Any]]
# Runs a plan step's plan to its end: what it gave, as an event; or None while it waits for an
# answer nobody has given, and the step keeps running. Given by the caller: running a plan is
# `async` (layer 5), and `case` doesn't import `asyncio` (layer 6's boundary test).
PlanRunner = Callable[[StartPlan], Completed | Failed | None]


def no_plans(command: StartPlan) -> Failed:
    """A deployment that supplies no plans: a plan step fails, and a person looks at it."""
    return Failed(command.entry, f"no plan {command.plan} is available")


@dataclass(frozen=True)
class CaseRun:
    """Where a case ended: closed or not, what it waits for, and what happened."""

    status: str  # open; closing: nothing new starts; closed (brief, D10)
    waiting_for: list[str]  # open tasks and approvals, in the order they opened (brief, D24)
    needs_attention: list[str]  # failed step runs, each with its reason (brief, D17)
    flags: list[str]  # what completed after the close was requested, for a person to look at
    history: list[str]
    steps_done: frozenset[str]
    definition: CaseDefinition  # what ran, so a view can be filtered by it
    state: CaseState  # where it ended

    def view(self, roles: Iterable[str]) -> CaseView:
        """The case file as a person holding `roles` sees it (brief, D30)."""
        return case_view(self.definition, self.state, roles)

    @property
    def closed(self) -> bool:
        return self.status == "closed"

    def reached(self, step: str) -> bool:
        """Whether a run of `step` is done: a task answered, an activity finished."""
        return step in self.steps_done


@dataclass(frozen=True)
class Finish:
    """Let a held activity's run finish now: `Finish("pay#1")`. For the driver, not `decide`."""

    entry: str


def run_case_in_memory(
    case: CaseDefinition,
    catalog: Catalog,
    implementations: Mapping[str, Activity],
    events: Iterable[Event | Finish],
    name: str = "memory",
    held: Iterable[str] = (),
    plans: PlanRunner = no_plans,
    workflows: Mapping[str, Activity] | None = None,
) -> CaseRun:
    """Play `events` in order, the first opening the case; `name` names the case in its keys.
    The runs of the steps in `held` keep running until a `Finish` names them, so a test can
    close a case while an activity runs (brief, D10). `workflows` binds each workflow contract
    to the code that runs it, by reference; one it doesn't bind fails its step."""
    state = CaseState(name)
    driver = Driver(case, catalog, implementations, frozenset(held), plans, workflows or {})
    for event in events:
        if isinstance(event, Finish):
            state = driver.carry(state, outcome_of(driver.held.pop(event.entry), driver.activity))
        else:
            state = driver.carry(state, event)
    done = frozenset(run.step for run in state.runs if run.status == "done")
    attention = [f"{run.entry}: {run.reason}" for run in state.runs if run.status == "failed"]
    waiting = list(state.waiting.values())
    return CaseRun(state.phase, waiting, attention, state.flags, state.history, done, case, state)


@dataclass
class Driver:
    """Carries out what `decide` asks for, at once, unless the step is held."""

    case: CaseDefinition
    catalog: Catalog
    implementations: Mapping[str, Activity]
    holding: frozenset[str]  # steps whose runs wait for a `Finish`
    plans: PlanRunner  # runs a plan step's plan
    workflows: Mapping[str, Activity]  # the workflows bound here, by contract
    held: dict[str, Schedule | StartWorkflow] = field(
        default_factory=dict[str, Schedule | StartWorkflow]
    )  # by entry

    def activity(self, command: Schedule | StartWorkflow) -> Activity:
        if isinstance(command, StartWorkflow):
            return self.workflows[command.workflow]
        if command.activity not in self.implementations:
            raise LookupError(f"no implementation of {command.activity} is available")
        return self.implementations[command.activity]

    def carry(self, state: CaseState, event: Event) -> CaseState:
        """Decide on `event`, then run each activity it asks for, feeding back what it gave."""
        queue = [event]
        while queue:
            state, commands = decide(self.case, self.catalog, state, queue.pop(0))
            for command in commands:
                if isinstance(command, StopPlan):
                    # In memory a running plan step waits for an answer (its plan runs at once to
                    # its end or its first unanswered wait): nothing runs in it, so it ends now.
                    queue.append(PlanCancelled(command.entry))
                elif isinstance(command, StartPlan):
                    if (ended := self.plans(command)) is not None:
                        queue.append(ended)  # else it waits for an answer: the step runs on
                elif isinstance(command, StartWorkflow) and command.workflow not in self.workflows:
                    # Fail closed: nothing guesses where to run an unbound workflow (brief, D29).
                    queue.append(Failed(command.entry, unbound(command.workflow)))
                elif command.entry.split("#")[0] in self.holding:
                    self.held[command.entry] = command  # it keeps running until finished
                else:
                    queue.append(outcome_of(command, self.activity))
        return state


def outcome_of(
    command: Schedule | StartWorkflow, activity_for: Callable[[Schedule | StartWorkflow], Activity]
) -> Completed | Failed:
    """Run the activity, and say what happened as an event. In memory there are no retries: an
    error is a failure after them (Temporal retries with the contract's policy, layer 8c)."""
    activity = activity_for(command)
    try:
        # The activity's code gets plain values, as on Temporal (brief, D31).
        return Completed(command.entry, activity(unwrapped(command.inputs)))
    except Outcome as outcome:
        # A business failure is an outcome; whether the contract declares it, `decide` checks.
        return Completed(command.entry, {}, outcome.name)
    # Any error, whatever its kind: none is ignored; a person looks at it (brief, D17).
    except Exception as error:  # noqa: BLE001 (catching every kind is the rule here)
        called = command.workflow if isinstance(command, StartWorkflow) else command.activity
        # What it said is never recorded: it may quote a sensitive value (brief, D31).
        return Failed(command.entry, f"{called} failed: {Sensitive(str(error))}")
