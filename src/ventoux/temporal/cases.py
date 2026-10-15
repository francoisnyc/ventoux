"""A case as a Temporal workflow, one per case for as long as it lives; and its client (layer 8c).

The workflow is a driver around `decide`, as `case/memory.py` is in tests: every event (the opening,
a person's signal, an activity's result) goes into one inbox, and the loop decides them one at a
time, in the order history records them, then starts what `decide` asks for. `decide` reads no
clock, randomness or I/O, so replay rebuilds the same case. See docs/layers/08-case.md (8c).
"""

import asyncio
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from temporalio import workflow
from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
    WorkflowHandle,
    WorkflowQueryFailedError,
)
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import (
    ActivityError,
    ApplicationError,
    ChildWorkflowError,
    FailureError,
)
from temporalio.exceptions import TimeoutError as TemporalTimeout  # not Python's own TimeoutError
from temporalio.service import RPCError, RPCStatusCode

# Temporal: the workflow sandbox imports a workflow's modules afresh for every run; modules passed
# through are imported once and shared. `core` and `case` are deterministic (the boundary test
# holds them to that), so they are shared.
with workflow.unsafe.imports_passed_through():
    from ventoux.case.admission import ProposalRefused, RetryRefused
    from ventoux.case.answers import AnswerRefused
    from ventoux.case.called import unbound
    from ventoux.case.closing import CloseRefused
    from ventoux.case.definition import CaseInvalid, parse_case
    from ventoux.case.forgetting import ForgetRefused
    from ventoux.case.freshness import TimeRefused
    from ventoux.case.plan_step import PlanNotSupplied, supplied
    from ventoux.case.runtime import CaseRefused, ShownRefused, decide
    from ventoux.case.state import (
        Answered,
        CaseState,
        CloseAsked,
        Command,
        Completed,
        Event,
        Failed,
        ForgetApproved,
        Opened,
        PlanCancelled,
        Proposed,
        Retried,
        Schedule,
        Shown,
        StartPlan,
        StartWorkflow,
        StopPlan,
    )
    from ventoux.case.visibility import ApprovalSheet, CaseView, SheetRefused, case_view, sheet_of
    from ventoux.core.catalog import Catalog
    from ventoux.core.sensitive import Sensitive
    from ventoux.core.workflow_contract import WorkflowContract
    from ventoux.temporal.activities import OUTCOME
    from ventoux.temporal.bindings import Binding
    from ventoux.temporal.carried import state_as_data, state_from_data
    from ventoux.temporal.converter import keys_of
    from ventoux.temporal.options import activity_options
    from ventoux.temporal.workflow import Given, PlanStart, RunReport, raised
    from ventoux.tooling.keys import FORGOTTEN


class CaseForgotten(Exception):
    """A forgotten case read for what it held: its key is gone (brief, D32)."""


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
class CaseForget:
    """An approved request to forget the case, from `<case ID>/forget` (brief, D32)."""

    proposed_by: str  # who proposed it
    proposer_roles: list[str]  # their roles, stated with the proposal (brief, D22)
    approved_by: str  # who approved it
    approver_roles: list[str]  # their roles, stated with the approval


@dataclass
class CaseRequest:
    """A person's request to a case: propose a step, retry a failed run, or close it."""

    what: str  # the step proposed, the run retried (`pay#1`), or the close reason
    by: str  # who asks, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles, stated with the request (brief, D22)


@dataclass
class SheetAsked:
    """A person reading an open approval's sheet: which, with which roles, at what time."""

    entry: str  # the open approval, such as `pay.approval#1`
    roles: list[str]  # the reader's roles, as the trusted caller states them (brief, D22)
    at: int  # the reader's time, in seconds since the epoch, against which ages are told


@dataclass
class SheetAnswer:
    """What a sheet query answers: the sheet, or why it can't be read."""

    sheet: ApprovalSheet | None
    refused: str = ""  # why not, naming the entry, never a value


class CaseWorkflow:
    """The code of a case workflow. A deployment subclasses it to name its catalog and plans, and
    registers the subclass (Temporal's SDK wants `@workflow.run` on the class it registers), as
    the cases guide shows."""

    catalog: ClassVar[Catalog]  # the contracts this deployment's cases may call
    plans: ClassVar[Mapping[str, Any]] = {}  # the plans its plan steps may run, by reference
    # The plan workflow a plan step runs as, by the name its worker registers it under.
    plan_workflow: ClassVar[str] = "ventoux.plan"
    # Where each workflow contract runs, in this deployment (brief, D5): its workflow type and
    # task queue. A workflow step whose contract isn't bound here fails (brief, D29).
    workflows: ClassVar[Mapping[str, Binding]] = {}
    # How many events one run decides before the case continues as new: a count, never a clock,
    # so replay switches at the same place (brief, D27). Temporal warns at about 10,000 history
    # events; a case's event makes a few.
    events_per_run: ClassVar[int] = 1000

    def __init__(self) -> None:
        self.state = CaseState("")  # named when the case opens
        self.case: Any = None  # the case definition, once read
        self.inbox: list[Event] = []  # events not yet decided, in the order they came
        self.decided = 0  # events this run has decided
        self.running = 0  # activities and child plans started and not yet back
        # Each child plan running, by its step run, to stop it if the case closes (brief, D28).
        self.children: dict[str, workflow.ChildWorkflowHandle[Any, RunReport]] = {}
        self.stopping: set[str] = set()  # step runs whose plans the case has stopped
        # An engine bug raised in a task beside the loop, which the loop raises in its turn.
        self.broken: Exception | None = None

    # Temporal: a signal is a message into a running workflow, recorded in its history, so replay
    # delivers it again at the same point.
    @workflow.signal(name="answer")
    def answer(self, sent: CaseAnswer) -> None:
        form = None if sent.form is None else dict(sent.form)
        self.inbox.append(
            Answered(sent.entry, sent.outcome, sent.by, frozenset(sent.roles), form, at=now())
        )

    @workflow.signal(name="propose")
    def propose(self, sent: CaseRequest) -> None:
        self.inbox.append(Proposed(sent.what, sent.by, frozenset(sent.roles), at=now()))

    @workflow.signal(name="retry")
    def retry(self, sent: CaseRequest) -> None:
        self.inbox.append(Retried(sent.what, sent.by, frozenset(sent.roles), at=now()))

    @workflow.signal(name="close")
    def close(self, sent: CaseRequest) -> None:
        self.inbox.append(CloseAsked(sent.what, sent.by, frozenset(sent.roles), at=now()))

    @workflow.signal(name="forget")
    def forget(self, sent: CaseForget) -> None:
        self.inbox.append(
            ForgetApproved(
                sent.proposed_by,
                frozenset(sent.proposer_roles),
                sent.approved_by,
                frozenset(sent.approver_roles),
                at=now(),
            )
        )

    @workflow.signal(name="shown")
    def shown(self, sent: CaseRequest) -> None:
        self.inbox.append(Shown(sent.what, sent.by, frozenset(sent.roles), at=now()))

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

    @workflow.query(name="view")
    def view(self, roles: list[str]) -> CaseView:
        """The case file as a person holding `roles` sees it, filtered here, in the worker, so
        nothing hidden from them leaves it (brief, D30)."""
        return case_view(self.case, self.state, roles, self.catalog.roles)

    @workflow.query(name="approval_sheet")
    def approval_sheet(self, asked: SheetAsked) -> SheetAnswer:
        """An open approval's sheet, with each fact's age at the reader's time, filtered here as
        the view is (brief, D18). A query changes nothing, so the time it is given decides
        nothing. A refusal comes back as data: a failure's message is sealed whoever raised it
        (brief, D31), and the reader must learn why; it names the entry, never a value."""
        try:
            sheet = sheet_of(
                self.case, self.state, asked.entry, asked.roles, asked.at, self.catalog.roles
            )
            return SheetAnswer(sheet)
        except (SheetRefused, TimeRefused) as refused:
            return SheetAnswer(None, str(refused))

    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)

    async def drive(self, start: CaseStart) -> CaseReport:
        """Open the case, then decide each event as it comes, until the case is closed."""
        info = workflow.info()  # recorded in history, so the same on replay
        # The case's name in its keys: its ID and its first run's, the same in every run of it
        # (brief, D27).
        self.state = CaseState(f"{info.workflow_id}/{info.first_execution_run_id}")
        try:
            case = self.case = parse_case(start.definition)
            if start.carried is None:
                self.decide(case, Opened(start.file, start.opened_by, at=now()))
            else:
                self.state = state_from_data(start.carried)  # a case continued as new
        except (CaseInvalid, CaseRefused) as refused:
            # A case that can't open fails at once, saying why. Any other exception fails only the
            # workflow task, which Temporal retries until fixed code is deployed (brief, D17).
            kind = type(refused).__name__
            raise ApplicationError(str(refused), type=kind, non_retryable=True) from None
        while self.state.phase != "closed":
            await workflow.wait_condition(
                lambda: bool(self.inbox) or self.time_to_switch() or self.broken is not None
            )
            if self.broken is not None:
                # An engine bug is never lost: it fails the workflow task, which Temporal retries
                # until fixed code is deployed (brief, D17); the log keeps its type (brief, D31).
                raise self.broken
            if not self.inbox:
                self.switch(start)
            event = self.inbox.pop(0)
            try:
                names_its_entry(event, self.state)
                self.decide(case, event)
            except (
                AnswerRefused,
                ProposalRefused,
                RetryRefused,
                CloseRefused,
                ShownRefused,
                ForgetRefused,
            ) as refused:
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
        if isinstance(command, StopPlan):
            self.beside(self.stop_plan(command))
            return
        self.running += 1
        if isinstance(command, StartPlan):
            self.beside(self.until_back(self.run_plan(command)))
        elif isinstance(command, StartWorkflow):
            self.beside(self.until_back(self.run_workflow(command)))
        else:
            self.beside(self.until_back(self.run_activity(command)))

    def beside(self, work: Coroutine[Any, Any, None]) -> None:
        """Run `work` in a task beside the loop. An exception it raises is an engine bug: kept
        for the loop to raise, never left in the task, where nobody would retrieve it and
        Temporal's SDK would log the task's description, quoting it (layer 9c)."""
        # asyncio: a task runs alongside the loop; Temporal's event loop runs it deterministically.
        asyncio.create_task(self.watched(work))

    async def watched(self, work: Coroutine[Any, Any, None]) -> None:
        try:
            await work
        except Exception as bug:  # noqa: BLE001 (every kind of bug: none may vanish)
            self.broken = bug

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
            self.inbox.append(Failed(command.entry, str(missing), at=now()))  # fail closed
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
                Failed(command.entry, f"{plan.plan}@{plan.version} can't start: {said}", at=now())
            )
            return
        finally:
            self.children.pop(command.entry, None)
        if ran.status == "cancelled":
            # Ended by the close, with what finished or failed in it after the close (brief, D28).
            self.inbox.append(PlanCancelled(command.entry, tuple(ran.after_stop), at=now()))
        elif ran.status == "succeeded":
            self.inbox.append(Completed(command.entry, {}, at=now()))
        elif ran.status == "failed":
            self.inbox.append(
                Completed(command.entry, {}, "failed", at=now())
            )  # a failed final state
        else:
            self.inbox.append(
                Failed(command.entry, f"{command.plan} stopped: {ran.reason}", at=now())
            )

    async def run_workflow(self, command: StartWorkflow) -> None:
        """Run the workflow step as a child workflow, `<case ID>/<entry>`, of the type and on the
        task queue its binding names, for at most its contract's timeout; put what it gave in the
        inbox (brief, D6). Its output is checked and tagged by `decide`, from the contract."""
        binding = self.workflows.get(command.workflow)
        if binding is None:
            self.inbox.append(
                Failed(command.entry, unbound(command.workflow), at=now())
            )  # fail closed
            return
        contract = self.catalog.workflow(command.workflow)
        try:
            # Temporal: the team's workflow runs on their worker; the case waits for its result,
            # recorded in its history. A retry starts it again under the same ID (brief, D26).
            output: dict[str, Any] = await workflow.execute_child_workflow(
                binding.workflow,
                command.inputs,
                id=f"{workflow.info().workflow_id}/{command.entry}",
                task_queue=binding.task_queue,
                execution_timeout=timedelta(seconds=contract.timeout),
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                result_type=dict,
            )
        except ChildWorkflowError as error:
            self.inbox.append(
                Failed(command.entry, workflow_failure(command.workflow, contract, error), at=now())
            )
            return
        self.inbox.append(Completed(command.entry, output, at=now()))

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
                self.inbox.append(Completed(command.entry, {}, cause.message, at=now()))
                return
            said = cause.message if isinstance(cause, FailureError) else str(error)
            # Never recorded: it may quote a sensitive value (brief, D31).
            self.inbox.append(
                Failed(
                    command.entry,
                    f"{command.activity} failed with {raised(error)}: {Sensitive(said)}",
                    at=now(),
                )
            )
            return
        self.inbox.append(Completed(command.entry, output, at=now()))


def workflow_failure(reference: str, contract: WorkflowContract, error: ChildWorkflowError) -> str:
    """Why a workflow step failed, as the history says it: past its timeout, or what it said."""
    cause = error.cause
    if isinstance(cause, TemporalTimeout):
        return f"{reference} didn't finish within its timeout of {contract.timeout}s"
    said = cause.message if isinstance(cause, FailureError) else str(error)
    # Its type, never what it said (brief, D31).
    return f"{reference} failed with {raised(error)}: {Sensitive(said)}"


def now() -> int:
    """The workflow's time as each event reaches the case, in whole seconds since the epoch.
    Temporal's workflow time is recorded in history, so a replay stamps the same times; the case
    itself reads no clock (brief, D33)."""
    return int(workflow.now().timestamp())  # whole seconds, rounded down


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
    if isinstance(event, Shown):
        return f"the record of {event.field} shown to {event.by}"
    if isinstance(event, ForgetApproved):
        return f"forgetting the case, approved by {event.approved_by}"
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
    (`refund-A-1001`): a second case with the same ID is refused (brief, D27). The case's key is
    made first, and never again: if starting then fails, the ID is spent (brief, D31)."""
    keys = keys_of(client)
    # The codec finds a key from the part of a workflow ID before its first `/` (brief, D31).
    if "/" in id:
        raise ValueError(f'{id} can\'t name a case: a case ID has no "/"')
    keys.create(id)
    # Each sensitive field's value wrapped: it crosses Temporal in its own part, sealed with the
    # case's key (brief, D31). The workflow checks the definition; here a field marked anything
    # but `false` counts as sensitive, so a malformed mark never sends a value in plain text.
    fields = definition.get("fields", {})
    sensitive = {
        name for name, field in fields.items() if dict(field).get("sensitive", False) is not False
    }
    sealed = {
        name: Sensitive(value) if name in sensitive else value for name, value in file.items()
    }
    start = CaseStart(definition, sealed, opened_by)
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
    the Ventoux API may send answers (brief, D19). Every value of `form` crosses sealed: the
    client can't tell which fields are sensitive, and the case keeps sealed only those
    (brief, D31)."""
    sealed = None if form is None else {name: Sensitive(value) for name, value in form.items()}
    sent = CaseAnswer(entry, outcome, by, sorted(roles), sealed)
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


async def shown(
    case: WorkflowHandle[CaseWorkflow, CaseReport], field: str, by: str, roles: list[str]
) -> None:
    """Record that the person `by` was shown the record behind the reference `field`, as the API
    does after asking its system's resolver (brief, D16)."""
    await case.signal(CaseWorkflow.shown, CaseRequest(field, by, sorted(roles)))


async def view(case: WorkflowHandle[CaseWorkflow, CaseReport], roles: list[str]) -> CaseView:
    """The case file as a person holding `roles` sees it, filtered in the worker (brief, D30).
    A forgotten case has no case file left to read: refused, saying so (brief, D32)."""
    try:
        return await case.query(CaseWorkflow.view, sorted(roles))
    except WorkflowQueryFailedError as failed:
        # The worker replays the case to answer, and its key provider refuses a destroyed key.
        if FORGOTTEN in str(failed):
            raise CaseForgotten(f"{case.id} was forgotten: its case file can't be read") from None
        raise


# A report asked at the moment the case continues as new can reach the run that is ending, which
# no longer answers; asked again, it reaches the new run (layer 8c). So each question waits a
# little, and is asked again a few times.
ASK = timedelta(seconds=2)
ASKS = 10
UNANSWERED = (RPCStatusCode.CANCELLED, RPCStatusCode.DEADLINE_EXCEEDED)


class CaseUnanswered(Exception):
    """A case that didn't answer, however many times it was asked."""


async def report(case: WorkflowHandle[CaseWorkflow, CaseReport]) -> CaseReport:
    """How the case is going: what it waits for, and its history so far. A case that has closed
    gives the report it returned then: lines and placeholders, no sensitive part, so it reads
    without a key, even once the case is forgotten (brief, D32). Asked with a short timeout, and
    again a bounded number of times, so it never hangs while the case continues as new
    (brief, D27)."""
    for _ in range(ASKS):
        try:
            described = await case.describe(rpc_timeout=ASK)
            if described.status == WorkflowExecutionStatus.COMPLETED:
                return await case.result(rpc_timeout=ASK)
            return await case.query(CaseWorkflow.report, rpc_timeout=ASK)
        except RPCError as error:
            # Temporal: no answer in time, as when the query reached a run that was ending. The
            # SDK says so as `CANCELLED` ("Timeout expired") when the client's own timeout ends
            # the call, and as `DEADLINE_EXCEEDED` when the server's does.
            if error.status not in UNANSWERED:
                raise
    raise CaseUnanswered(
        f"{case.id} didn't answer in {ASKS} tries of {ASK.total_seconds():g}s: ask again later"
    )


async def approval_sheet(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    entry: str,
    roles: list[str],
    at: int | None = None,
) -> ApprovalSheet:
    """The open approval `entry`'s sheet as a person holding `roles` reads it at `at`, seconds
    since the epoch: by default the API's own clock, now. A sheet is a query, read and never
    decided on, so the reader's time is safe here, outside the case (brief, D33). An approval
    that isn't open is refused, saying so."""
    if at is None:
        at = int(datetime.now(UTC).timestamp())  # whole seconds, rounded down
    try:
        answered = await case.query(
            CaseWorkflow.approval_sheet, SheetAsked(entry, sorted(roles), at)
        )
    except WorkflowQueryFailedError as failed:
        # The worker replays the case to answer, and its key provider refuses a destroyed key.
        if FORGOTTEN in str(failed):
            raise CaseForgotten(f"{case.id} was forgotten: its case file can't be read") from None
        raise
    if answered.sheet is None:
        raise SheetRefused(answered.refused)
    return answered.sheet
