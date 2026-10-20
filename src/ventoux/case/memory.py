"""Running a case in memory: the driver around `decide`, for tests (layer 8).

Each command is carried out at once by the activity passed in, and what it gave is fed back as
the next event. Pure, like all of `ventoux.case`: the activities are passed in, so every side
effect happens outside this module.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ventoux.case.called import unbound
from ventoux.case.closing import needs_attention
from ventoux.case.definition import CaseDefinition
from ventoux.case.runtime import decide
from ventoux.case.state import (
    CancelWorkflow,
    CaseState,
    Completed,
    Event,
    Failed,
    PlanCancelled,
    Schedule,
    StartPlan,
    StartWorkflow,
    StopPlan,
    WorkflowCancelled,
)
from ventoux.case.timers import next_due, set_timers
from ventoux.case.visibility import ApprovalSheet, CaseView, case_view, sheet_of
from ventoux.core.catalog import Catalog
from ventoux.core.interpreter import Outcome, failed_with
from ventoux.core.sensitive import Sensitive, unwrapped

# An activity's code, or a workflow's in memory: its inputs in, its output back.
Activity = Callable[[dict[str, Any]], dict[str, Any]]
# Runs a plan step's plan to its end: what it gave, as an event at the time given; or None while
# it waits for an answer nobody has given, and the step keeps running. Given by the caller: running
# a plan is `async` (layer 5), and `case` doesn't import `asyncio` (layer 6's boundary test).
PlanRunner = Callable[[StartPlan, int], Completed | Failed | None]


def no_plans(command: StartPlan, at: int) -> Failed:
    """A deployment that supplies no plans: a plan step fails, and a person looks at it."""
    return Failed(command.entry, f"no plan {command.plan} is available", at=at)


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
    registered: tuple[str, ...]  # the catalog's roles: only these give sight (brief, D22)
    # Each timer still set, soonest first, with its due time: pending work that waits on nobody,
    # so never in `waiting_for` (brief, D24) (brief, D44).
    timers: list[str]

    def view(self, roles: Iterable[str]) -> CaseView:
        """The case file as a person holding `roles` sees it (brief, D30)."""
        return case_view(self.definition, self.state, roles, self.registered)

    def approval_sheet(self, entry: str, roles: Iterable[str], at: int) -> ApprovalSheet:
        """The open approval `entry`'s sheet as a person holding `roles` reads it at `at`, with
        the age of each fact it depends on (brief, D18)."""
        return sheet_of(self.definition, self.state, entry, roles, at, self.registered)

    @property
    def closed(self) -> bool:
        return self.status == "closed"

    def reached(self, step: str) -> bool:
        """Whether a run of `step` is done: a task answered, an activity finished."""
        return step in self.steps_done


@dataclass(frozen=True)
class Advance:
    """Time moves on to `at`, with no event: every timer due by then fires. For the driver, not
    `decide` (brief, D44)."""

    at: int  # in seconds since the epoch


@dataclass(frozen=True)
class Finish:
    """Let a held activity's run finish now: `Finish("pay#1", at=t)`. For the driver, not
    `decide`."""

    entry: str
    at: int  # when it finishes, in seconds since the epoch: its result arrives then


def run_case_in_memory(
    case: CaseDefinition,
    catalog: Catalog,
    implementations: Mapping[str, Activity],
    events: Iterable[Event | Finish | Advance],
    name: str = "memory",
    held: Iterable[str] = (),
    plans: PlanRunner = no_plans,
    workflows: Mapping[str, Activity] | None = None,
) -> CaseRun:
    """Play `events` in order, the first opening the case; `name` names the case in its keys.
    The runs of the steps in `held` keep running until a `Finish` names them, so a test can
    close a case while an activity runs (brief, D10). `workflows` binds each workflow contract
    to the code that runs it, by reference; one it doesn't bind fails its step. Before each
    event, and at each `Advance`, every timer due by its time fires first (brief, D44)."""
    state = CaseState(name)
    driver = Driver(case, catalog, implementations, frozenset(held), plans, workflows or {})
    for event in events:
        state = driver.until(state, event.at)
        if isinstance(event, Advance):
            continue
        if isinstance(event, Finish):
            finishing = driver.held.pop(event.entry)
            state = driver.carry(state, outcome_of(finishing, driver.activity, event.at))
        else:
            state = driver.carry(state, event)
    done = frozenset(run.step for run in state.runs if run.status == "done")
    attention = needs_attention(state)
    waiting = list(state.waiting.values())
    registered = tuple(catalog.roles)
    timers = set_timers(state)
    return CaseRun(
        state.phase,
        waiting,
        attention,
        state.flags,
        state.history,
        done,
        case,
        state,
        registered,
        timers,
    )


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

    def until(self, state: CaseState, at: int) -> CaseState:
        """Fire every timer due by `at`, one at a time and in order, each stamped with its own
        due time: a firing may set or end timers, so the next is asked for afresh (brief, D44)."""
        while (due := next_due(state, at)) is not None:
            state = self.carry(state, due)
        return state

    def carry(self, state: CaseState, event: Event) -> CaseState:
        """Decide on `event`, then run each activity it asks for, feeding back what it gave. In
        memory a run is instant: what it gives arrives at the time of the event that started it."""
        at = event.at
        queue = [event]
        while queue:
            state, commands = decide(self.case, self.catalog, state, queue.pop(0))
            for command in commands:
                if isinstance(command, StopPlan):
                    # In memory a running plan step waits for an answer (its plan runs at once to
                    # its end or its first unanswered wait): nothing runs in it, so it ends now.
                    queue.append(PlanCancelled(command.entry, at=at))
                elif isinstance(command, CancelWorkflow):
                    # A held workflow step, cancelled, ends cancelled at once, as its contract
                    # promises. One that isn't held has already ended: what it gave is on its
                    # way, and the case reads it as done, as on Temporal (brief, D40).
                    if self.held.pop(command.entry, None) is not None:
                        queue.append(WorkflowCancelled(command.entry, at=at))
                elif isinstance(command, StartPlan):
                    if (ended := self.plans(command, at)) is not None:
                        queue.append(ended)  # else it waits for an answer: the step runs on
                elif isinstance(command, StartWorkflow) and command.workflow not in self.workflows:
                    # Fail closed: nothing guesses where to run an unbound workflow (brief, D29).
                    queue.append(Failed(command.entry, unbound(command.workflow), at=at))
                elif command.entry.split("#")[0] in self.holding:
                    self.held[command.entry] = command  # it keeps running until finished
                else:
                    queue.append(outcome_of(command, self.activity, at))
        return state


def outcome_of(
    command: Schedule | StartWorkflow,
    activity_for: Callable[[Schedule | StartWorkflow], Activity],
    at: int,
) -> Completed | Failed:
    """Run the activity, and say what happened as an event at `at`. In memory there are no
    retries: an error is a failure after them (Temporal retries with the contract's policy, layer
    8c)."""
    activity = activity_for(command)
    try:
        # The activity's code gets plain values, as on Temporal (brief, D31).
        return Completed(command.entry, activity(unwrapped(command.inputs)), at=at)
    except Outcome as outcome:
        # A business failure is an outcome; whether the contract declares it, `decide` checks.
        return Completed(command.entry, {}, outcome.name, at=at)
    # Any error, whatever its kind: none is ignored; a person looks at it (brief, D17).
    except Exception as error:  # noqa: BLE001 (catching every kind is the rule here)
        called = command.workflow if isinstance(command, StartWorkflow) else command.activity
        # What it said is never recorded: it may quote a sensitive value (brief, D31).
        said = Sensitive(str(error))
        return Failed(command.entry, f"{called} failed with {failed_with(error)}: {said}", at=at)


def as_json(values: Mapping[str, Any]) -> dict[str, Any]:
    """`values` as the API would pass them on from JSON, whose numbers are exact decimals
    (brief, D20): a whole number in a test is one. A float is passed on as it is, and refused by
    the type check, since it may already have lost its exact value."""
    return {
        name: Decimal(value) if isinstance(value, int) and not isinstance(value, bool) else value
        for name, value in values.items()
    }


def wrapped(case: CaseDefinition, file: Mapping[str, Any]) -> dict[str, Any]:
    """`file` as the client sends it: each sensitive field's value wrapped (brief, D31)."""
    return {
        name: Sensitive(value) if name in case.fields and case.fields[name].sensitive else value
        for name, value in file.items()
    }
