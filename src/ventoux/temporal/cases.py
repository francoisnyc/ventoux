"""A case as a Temporal workflow, one per case for as long as it lives; and its client (layer 8c).

The workflow is a driver around `decide`, as `case/memory.py` is in tests: every event (the opening,
a person's signal, an activity's result) goes into one inbox, and the loop decides them one at a
time, in the order history records them, then starts what `decide` asks for. `decide` reads no
clock, randomness or I/O, so replay rebuilds the same case. See docs/layers/08-case.md (8c).
"""

import asyncio
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from temporalio import workflow
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import (
    ActivityError,
    ApplicationError,
    ChildWorkflowError,
    FailureError,
)

# Temporal: the workflow sandbox imports a workflow's modules afresh for every run; modules passed
# through are imported once and shared. `core` and `case` are deterministic (the boundary test
# holds them to that), so they are shared.
with workflow.unsafe.imports_passed_through():
    from ventoux.case.admission import ProposalRefused, RetryRefused
    from ventoux.case.answers import AnswerRefused
    from ventoux.case.closing import CloseRefused
    from ventoux.case.definition import CaseInvalid, parse_case
    from ventoux.case.plan_step import PlanNotSupplied, supplied
    from ventoux.case.runtime import CaseRefused, decide
    from ventoux.case.state import (
        Answered,
        CaseState,
        CloseAsked,
        Command,
        Completed,
        Event,
        Failed,
        Opened,
        PlanCancelled,
        Proposed,
        Retried,
        Schedule,
        StartPlan,
        StopPlan,
    )
    from ventoux.core.catalog import Catalog
    from ventoux.temporal.activities import OUTCOME
    from ventoux.temporal.carried import state_as_data, state_from_data
    from ventoux.temporal.converter import require_exact_numbers
    from ventoux.temporal.options import activity_options
    from ventoux.temporal.workflow import Given, PlanStart, RunReport


@dataclass
class CaseStart:
    """What a case opens with."""

    definition: dict[str, Any]  # the case definition, as stored data
    file: dict[str, Any]  # the case file's first values, each of its field's type
    opened_by: str | None = None  # the person who opened it, as the API states; None: a system
    # The state of the case, when it continues as new: the new run decides from it alone
    # (brief, D27). None: the case opens now.
    carried: dict[str, Any] | None = None


@dataclass
class CaseReport:
    """How a case is going: what `run_case` reports in memory, and the entries open."""

    status: str  # open; closing: nothing new starts; closed (brief, D10)
    waiting_for: list[str]  # open tasks and approvals, in the order they opened (brief, D24)
    waiting_at: list[str]  # their entries, in the same order, to answer: `review#1`
    needs_attention: list[str]  # failed step runs, each with its reason (brief, D17)
    flags: list[str]  # what completed after the close was requested
    history: list[str]  # what happened, one line each


@dataclass
class CaseAnswer:
    """An answer, as a person sends it to a case."""

    entry: str  # the entry it answers: `review#1` or `pay.approval#1`
    outcome: str  # one of the entry's outcomes, such as `approve`
    by: str  # who answered
    # Their roles, as the Ventoux API states them; recorded in history with the signal, so a
    # replay decides as the first run did, whatever their roles are now (brief, D22).
    roles: list[str]
    form: dict[str, Any] | None = None  # the values the outcome sets, if any


@dataclass
class CaseRequest:
    """A person's request to a case: propose a step, retry a failed run, or close it."""

    what: str  # the step proposed, the run retried (`pay#1`), or the close reason
    by: str  # who asks, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles, stated with the request (brief, D22)


class CaseWorkflow:
    """The code of a case workflow. A deployment subclasses it to name its catalog and plans, and
    registers the subclass (Temporal's SDK wants `@workflow.run` on the class it registers), as
    the cases guide shows."""

    catalog: ClassVar[Catalog]  # the contracts this deployment's cases may call
    plans: ClassVar[Mapping[str, Any]] = {}  # the plans its plan steps may run, by reference
    # The plan workflow a plan step runs as, by the name its worker registers it under.
    plan_workflow: ClassVar[str] = "ventoux.plan"
    # How many events one run decides before the case continues as new: a count, never a clock,
    # so replay switches at the same place (brief, D27). Temporal warns at about 10,000 history
    # events; a case's event makes a few.
    events_per_run: ClassVar[int] = 1000

    def __init__(self) -> None:
        self.state = CaseState("")  # named when the case opens
        self.inbox: list[Event] = []  # events not yet decided, in the order they came
        self.decided = 0  # events this run has decided
        self.running = 0  # activities and child plans started and not yet back
        # Each child plan running, by its step run, to stop it if the case closes (brief, D28).
        self.children: dict[str, workflow.ChildWorkflowHandle[Any, RunReport]] = {}
        self.stopping: set[str] = set()  # step runs whose plans the case has stopped

    # Temporal: a signal is a message into a running workflow, recorded in its history, so replay
    # delivers it again at the same point.
    @workflow.signal(name="answer")
    def answer(self, sent: CaseAnswer) -> None:
        form = None if sent.form is None else dict(sent.form)
        self.inbox.append(Answered(sent.entry, sent.outcome, sent.by, frozenset(sent.roles), form))

    @workflow.signal(name="propose")
    def propose(self, sent: CaseRequest) -> None:
        self.inbox.append(Proposed(sent.what, sent.by, frozenset(sent.roles)))

    @workflow.signal(name="retry")
    def retry(self, sent: CaseRequest) -> None:
        self.inbox.append(Retried(sent.what, sent.by, frozenset(sent.roles)))

    @workflow.signal(name="close")
    def close(self, sent: CaseRequest) -> None:
        self.inbox.append(CloseAsked(sent.what, sent.by, frozenset(sent.roles)))

    # Temporal: a query reads a workflow's state without changing it, and isn't recorded.
    @workflow.query(name="report")
    def report(self) -> CaseReport:
        state = self.state
        attention = [f"{run.entry}: {run.reason}" for run in state.runs if run.status == "failed"]
        return CaseReport(
            state.phase,
            list(state.waiting.values()),
            list(state.waiting),
            attention,
            list(state.flags),
            list(state.history),
        )

    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)

    async def drive(self, start: CaseStart) -> CaseReport:
        """Open the case, then decide each event as it comes, until the case is closed."""
        info = workflow.info()  # recorded in history, so the same on replay
        # The case's name in its keys: its ID and its first run's, the same in every run of it
        # (brief, D27).
        self.state = CaseState(f"{info.workflow_id}/{info.first_execution_run_id}")
        try:
            case = parse_case(start.definition)
            if start.carried is None:
                self.decide(case, Opened(start.file, start.opened_by))
            else:
                self.state = state_from_data(start.carried)  # a case continued as new
        except (CaseInvalid, CaseRefused) as refused:
            # A case that can't open fails at once, saying why. Any other exception fails only the
            # workflow task, which Temporal retries until fixed code is deployed (brief, D17).
            kind = type(refused).__name__
            raise ApplicationError(str(refused), type=kind, non_retryable=True) from None
        while self.state.phase != "closed":
            await workflow.wait_condition(lambda: bool(self.inbox) or self.time_to_switch())
            if not self.inbox:
                self.switch(start)
            event = self.inbox.pop(0)
            try:
                names_its_entry(event, self.state)
                self.decide(case, event)
            except (AnswerRefused, ProposalRefused, RetryRefused, CloseRefused) as refused:
                # In memory a refusal raises to the test; here nobody is there to catch it. It is
                # recorded, and the case waits on as if it hadn't come: `decide` changed nothing
                # (8b, slice 0). Never queued for later (layer 6).
                self.state.history.append(f"refused {asked(event)}: {refused}")
        return self.report()

    def time_to_switch(self) -> bool:
        """Whether the case should continue as new now: enough events in this run, or Temporal
        suggests it (its history is getting large); and nothing is running, whose result would
        come back to a run that has ended (brief, D27)."""
        enough = self.decided >= self.events_per_run
        return self.running == 0 and (enough or workflow.info().is_continue_as_new_suggested())

    def switch(self, start: CaseStart) -> None:
        """Continue as new, carrying the whole state. Only at a quiet point: no event waiting to
        be decided, nothing running, no signal handler part-way. A signal that arrives while the
        switch is committed fails it, and this run decides that signal first: no answer is ever
        carried as a queue (brief, D27)."""
        assert not self.inbox and self.running == 0 and workflow.all_handlers_finished()
        carried = CaseStart(start.definition, {}, start.opened_by, state_as_data(self.state))
        # Temporal: ends this run and starts the next one of the same workflow, with `carried`.
        workflow.continue_as_new(carried)

    def decide(self, case: Any, event: Event) -> None:
        """Decide `event`, then start what the case asks for."""
        self.decided += 1
        self.state, commands = decide(case, self.catalog, self.state, event)
        for command in commands:
            self.carry(command)

    def carry(self, command: Command) -> None:
        """Start the command; what it gives comes back to the inbox when it arrives."""
        # asyncio: a task runs alongside the loop; Temporal's event loop runs it deterministically.
        if isinstance(command, StopPlan):
            asyncio.create_task(self.stop_plan(command))
            return
        self.running += 1
        if isinstance(command, StartPlan):
            asyncio.create_task(self.until_back(self.run_plan(command)))
        else:
            asyncio.create_task(self.until_back(self.run_activity(command)))

    async def until_back(self, carried: Coroutine[Any, Any, None]) -> None:
        """Run `carried`, which puts what happened in the inbox; then it no longer runs."""
        try:
            await carried
        finally:
            self.running -= 1

    async def run_plan(self, command: StartPlan) -> None:
        """Run the step's plan as a child workflow, `<case ID>/<entry>`, and put how it ended in
        the inbox (brief, D28): succeeded is done, a failed final state the outcome `failed`, a
        plan that stops or can't start fails the step."""
        try:
            plan = supplied(self.plans, command.plan)
        except PlanNotSupplied as missing:
            self.inbox.append(Failed(command.entry, str(missing)))  # fail closed
            return
        fields = {
            name: Given(given.value, sorted(given.sources))
            for name, given in command.fields.items()
        }
        start = PlanStart(self.plans[command.plan], fields, command.run, dict(command.excluded))
        try:
            # Temporal: a child workflow is a workflow the case starts and waits for; its own
            # history holds its waits and activities. Its ID names the step run; a retry starts it
            # again under the same ID, with the same keys (brief, D26).
            child = await workflow.start_child_workflow(
                self.plan_workflow,
                start,
                id=f"{workflow.info().workflow_id}/{command.entry}",
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                result_type=RunReport,
            )
            self.children[command.entry] = child
            if command.entry in self.stopping:
                await child.signal("stop")  # the case closed while the child was starting
            ran: RunReport = await child
        except ChildWorkflowError as error:
            cause = error.cause
            said = cause.message if isinstance(cause, FailureError) else str(error)
            self.inbox.append(
                Failed(command.entry, f"{plan.plan}@{plan.version} can't start: {said}")
            )
            return
        finally:
            self.children.pop(command.entry, None)
        if ran.status == "cancelled":
            self.inbox.append(PlanCancelled(command.entry))  # ended by the close
        elif ran.status == "succeeded":
            self.inbox.append(Completed(command.entry, {}))
        elif ran.status == "failed":
            self.inbox.append(Completed(command.entry, {}, "failed"))  # a failed final state
        else:
            self.inbox.append(Failed(command.entry, f"{command.plan} stopped: {ran.reason}"))

    async def stop_plan(self, command: StopPlan) -> None:
        """Stop a child plan because the case is closing (brief, D28). A signal, not Temporal's
        cancellation: cancellation would cut short the await on an activity running in the
        plan, which must finish (brief, D10); the signal lets the plan's driver cancel its open
        wait and start nothing new, and the plan ends `cancelled`."""
        self.stopping.add(command.entry)
        child = self.children.get(command.entry)
        if child is not None:  # else it is starting: `run_plan` signals it once started
            await child.signal("stop")

    async def run_activity(self, command: Schedule) -> None:
        """Run the activity, retried and timed out as its contract says (brief, D17), and put
        what happened in the inbox: its output, a declared outcome, or a failure."""
        contract = self.catalog.get(command.activity)
        try:
            # Temporal: the result is recorded in history; on replay it is read back, never
            # called again.
            output: dict[str, Any] = await workflow.execute_activity(
                command.activity, command.inputs, **activity_options(contract), result_type=dict
            )
        except ActivityError as error:
            cause = error.cause
            if isinstance(cause, ApplicationError) and cause.type == OUTCOME:
                self.inbox.append(Completed(command.entry, {}, cause.message))
                return
            said = cause.message if isinstance(cause, FailureError) else str(error)
            self.inbox.append(Failed(command.entry, f"{command.activity} failed: {said}"))
            return
        self.inbox.append(Completed(command.entry, output))


def names_its_entry(event: Event, state: CaseState) -> None:
    """On Temporal an answer names the entry it answers (`review#1`), never a step: after a
    rework, an answer to `review` would answer `review#2`, which its sender never saw (layer 6).
    The in-memory script may answer by step: it runs in order, with no one clicking."""
    if isinstance(event, Answered) and "#" not in event.entry:
        step = event.entry
        open_now = [
            entry for entry in state.waiting if entry.split("#")[0] in (step, f"{step}.approval")
        ]
        example = open_now[0] if open_now else f"{step}#1"
        raise AnswerRefused(f"name the entry it answers, such as {example}")


def asked(event: Event) -> str:
    """What a person asked, as a refusal names it: `sam's answer approve to review#1`."""
    if isinstance(event, Answered):
        return f"{event.by}'s answer {event.outcome} to {event.entry}"
    if isinstance(event, Proposed):
        return f"{event.by}'s proposal of {event.step}"
    if isinstance(event, Retried):
        return f"{event.by}'s retry of {event.entry}"
    if isinstance(event, CloseAsked):
        return f"{event.by}'s close as {event.reason}"
    return type(event).__name__  # only people's requests are refused; anything else is a bug


async def start_case(
    client: Client,
    workflow: type[CaseWorkflow],
    definition: dict[str, Any],
    file: Mapping[str, Any],
    id: str,
    task_queue: str,
    opened_by: str | None = None,
) -> WorkflowHandle[CaseWorkflow, CaseReport]:
    """Open a case of `definition` with `file`, as a run of `workflow`. `id` is the case
    (`refund-A-1001`): a second case with the same ID is refused (brief, D27)."""
    require_exact_numbers(client)
    start = CaseStart(definition, dict(file), opened_by)
    await client.start_workflow(
        workflow.run,
        start,
        id=id,
        task_queue=task_queue,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
    return case_handle(client, workflow, id)


def case_handle(
    client: Client, workflow: type[CaseWorkflow], id: str
) -> WorkflowHandle[CaseWorkflow, CaseReport]:
    """The case `id`, by its ID alone, so it always reaches its latest run (brief, D27)."""
    return client.get_workflow_handle_for(workflow.run, id)


async def answer(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    entry: str,
    outcome: str,
    by: str,
    roles: list[str],
    form: Mapping[str, Any] | None = None,
) -> None:
    """Answer the open `entry` (`review#1`, as `report` shows it in `waiting_at`) with `outcome`,
    as the person `by`, who has `roles`. The caller vouches for who `by` is and their roles: only
    the Ventoux API may send answers (brief, D19)."""
    sent = CaseAnswer(entry, outcome, by, sorted(roles), None if form is None else dict(form))
    await case.signal(CaseWorkflow.answer, sent)


async def propose(
    case: WorkflowHandle[CaseWorkflow, CaseReport], step: str, by: str, roles: list[str]
) -> None:
    """Propose starting `step`, as the person `by`, who has `roles`; admission decides."""
    await case.signal(CaseWorkflow.propose, CaseRequest(step, by, sorted(roles)))


async def retry(
    case: WorkflowHandle[CaseWorkflow, CaseReport], entry: str, by: str, roles: list[str]
) -> None:
    """Retry the failed run `entry` (`pay#1`), as an operator: the same run, the same key
    (brief, D26)."""
    await case.signal(CaseWorkflow.retry, CaseRequest(entry, by, sorted(roles)))


async def close(
    case: WorkflowHandle[CaseWorkflow, CaseReport], reason: str, by: str, roles: list[str]
) -> None:
    """Close the case with the declared `reason`, as the person `by` (brief, D10)."""
    await case.signal(CaseWorkflow.close, CaseRequest(reason, by, sorted(roles)))


async def report(case: WorkflowHandle[CaseWorkflow, CaseReport]) -> CaseReport:
    """How the case is going: what it waits for, and its history so far."""
    return await case.query(CaseWorkflow.report)
