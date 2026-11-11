"""Forgetting a case on Temporal: a small workflow of its own, `<case ID>/forget` (layer 9c).

One person proposes, another approves; then the case is asked to close as `forgotten`, and once
its workflow has ended, its key is destroyed (brief, D15) (brief, D32). The key is destroyed out
here, never inside the case: the case's own workflow tasks may need a replay, and replay needs
the key. None of this workflow's payloads holds a sensitive part, so it never asks for the key,
and its history stays readable once the key is gone.
See docs/layers/09-case-data.md (9c).
"""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, ClassVar

from temporalio import activity, workflow
from temporalio.client import Client, WorkflowExecutionStatus, WorkflowHandle
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.converter import WorkflowSerializationContext
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode

# Temporal: the workflow sandbox imports a workflow's modules afresh; `case` and `core` are
# deterministic and passed through, imported once and shared (as in `cases.py`).
with workflow.unsafe.imports_passed_through():
    from ventoux.case.audit import Act, ActKind, AuditRecord, Decision
    from ventoux.case.definition import parse_case
    from ventoux.case.engine import ENGINE
    from ventoux.case.forgetting import (
        approval_refusal,
        family_forgetting,
        forgetting_role,
        role_refusal,
    )
    from ventoux.core.catalog import Catalog
    from ventoux.core.person import identifier_problem
    from ventoux.temporal.audit import ExportSent
    from ventoux.temporal.carried import record_as_data
    from ventoux.temporal.cases import (
        EXPORT_CALL,
        EXPORT_REFUSALS,
        CaseForget,
        CaseReport,
        CaseStart,
    )
    from ventoux.temporal.converter import keys_of
    from ventoux.tooling.keys import KeyUnavailable

# How long one call to the key provider may take; Temporal retries it until it answers, as a
# system that is down is retried (brief, D17).
KEY_CALL = timedelta(seconds=30)
# Waiting for a case to end: as long as its running work takes, saying it is alive every few
# seconds; if a worker dies, Temporal starts the wait again on another.
CASE_WAIT = timedelta(days=30)
ALIVE = timedelta(seconds=30)
FIRST_PAUSE = timedelta(milliseconds=100)  # between two questions to Temporal, at first
LONGEST_PAUSE = timedelta(seconds=10)  # and at most, well within ALIVE
# A request writes its own audit stream behind this patch: one recorded before 19b replays as it
# was, writing nothing (brief, D51) (brief, D77).
EXPORT_PATCH = "ventoux-forget-export"
# Before it destroys a key, a request reads the case's own word as it ended, behind this patch:
# one recorded before the fix replays as it was (brief, D32) (brief, D51).
ENDING_PATCH = "ventoux-forget-ending"
# A store that is down is retried for as long as it takes, never given up on: the request's
# records hold nothing sensitive, so its key never waits for them, but none is dropped. A store
# that refuses them (a gap, other content) fails the request (brief, D77).
FORGET_EXPORTS = RetryPolicy(
    maximum_interval=timedelta(minutes=5), non_retryable_error_types=list(EXPORT_REFUSALS)
)


@dataclass
class ForgetStart:
    """A proposal to forget a case."""

    case: str  # the case's ID, such as `claim-7`
    by: str  # who proposes it, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles, stated with the proposal (brief, D22)


@dataclass
class ForgetAnswer:
    """An answer to a request to forget a case."""

    outcome: str  # approve or reject
    by: str  # who answers, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles, stated with the answer (brief, D22)


OUTCOMES = ("approve", "reject")


@dataclass
class CaseLookup:
    """What a request learns of its case before anyone answers."""

    key: str  # its key's state: kept, destroyed, or never made
    running: bool  # whether its workflow still runs
    # What its definition says (brief, D32): allowed, while_open or never; empty if its
    # definition can't be read any more.
    forgetting: str
    # Why the key service couldn't say where its key stands, if it couldn't: never read as a key
    # destroyed or never made (brief, D78). Empty in a lookup recorded before 19c.
    unavailable: str = ""


def child_refusal(case: str) -> str | None:
    """Why `case` can't be forgotten alone: its ID names a case before its `/`, whose key it is
    under. Forgetting it would destroy that case's key, so only that case is forgotten, with
    its children (brief, D75). None if `case` is a case of its own."""
    if "/" not in case:
        return None
    parent, child = case.split("/", 1)
    return f"{child} is a child of {parent}: forget {parent}, which forgets it too"


def lookup_refusal(case: str, found: CaseLookup) -> str | None:
    """Why a request to forget `case` is refused before anyone answers; None if it may go on."""
    if found.unavailable:
        # Nothing was decided, so nothing waits: proposed again, it is asked again (brief, D78).
        return f"{found.unavailable}: propose again once it answers"
    if found.key == "never made":
        return f"there is no case {case}: no key was ever made for it"
    if found.key == "destroyed":
        return f"{case} was already forgotten: its key was destroyed"
    if found.forgetting == "":
        # Fail closed: a case whose definition can't be read might keep its records.
        return (
            f"{case}'s definition can't be read: Temporal holds no history of it, so whether "
            "it keeps its records is unknown"
        )
    if found.forgetting == "never":
        return f"{case} keeps its records (forgetting: never): it can't be forgotten"
    if found.forgetting == "while_open" and not found.running:
        return f"{case} is closed, and its definition keeps closed cases (forgetting: while_open)"
    return None


@dataclass
class CaseOpener:
    """Who opened a case, as its start says, asked when someone approves forgetting it."""

    by: str | None  # the person who opened it; None: a system did
    known: bool = True  # False: Temporal holds no history of it, so who opened it is unknown


def opener_refusal(case: str, by: str, found: CaseOpener) -> str | None:
    """Why `by` may not approve forgetting `case`: they opened it, and approve no change to it
    (brief, D25) (brief, D52); or whoever opened it can't be told. None if they may."""
    if not found.known:
        # Fail closed: an approval is never taken from someone who might have opened the case.
        return f"who opened {case} can't be told: Temporal holds no history of it"
    if by == found.by:
        return f"{by} opened {case}, so cannot approve forgetting it"
    return None


@dataclass
class CaseEnded:
    """How a case ended, as the request records it."""

    # Its closing line (`closed: forgotten`) if it completed; else how it ended: `failed`,
    # `terminated`, `timed out`, `canceled`.
    last: str
    flags: list[str]  # what completed after its close was requested, if it completed
    # The case's own word, from the report it returned: what its family's definitions say of
    # forgetting as it ended, and whether it took this request (brief, D32). Empty if it returned
    # no report, or its worker predates the fix: the request then goes on as it did.
    forgetting: str = ""
    took: bool = False


@dataclass
class ForgetReport:
    """How a request to forget a case is going, and what it did."""

    # waiting: for an answer; refused: the proposal was; rejected; closing the case: approved,
    # waiting for the case's workflow to end; forgotten: its key was destroyed.
    status: str
    history: list[str] = field(default_factory=list[str])  # what happened, one line each


def ending_refusal(case: str, ended: CaseEnded) -> str | None:
    """Why the key of `case` is kept though its forgetting was approved, read from the case's own
    word as it ended; None if the key may go. A case that took the request is forgotten. One
    that didn't was closed already when it was asked: a closed case can be forgotten unless its
    definition keeps its records (brief, D32). Temporal saying "running" never meant "open": a
    closed case runs on until its records are written (brief, D77)."""
    if ended.took:
        return None
    if ended.forgetting == "never":
        return f"{case} keeps its records (forgetting: never): it can't be forgotten"
    if ended.forgetting == "while_open":
        return closed_first(case)
    return None


def closed_first(case: str) -> str:
    """Why a case that keeps closed cases, and closed before the approval reached it, isn't
    forgotten (brief, D32)."""
    return (
        f"{case} closed before forgetting was approved, and its definition keeps closed cases "
        "(forgetting: while_open)"
    )


class ForgetWorkflow:
    """The code of a request to forget a case. A deployment subclasses it to name its catalog,
    whose roles registered to forget may propose and approve, and registers the subclass with
    its case worker (`case_worker(..., forget=)`), as with `CaseWorkflow`."""

    catalog: ClassVar[Catalog]  # the roles that may forget a case are registered in it

    def __init__(self) -> None:
        self.report = ForgetReport("waiting")
        self.found = CaseLookup("never made", False, "")  # the case, once looked up
        self.inbox: list[ForgetAnswer] = []  # answers not yet judged, in the order they came
        self.exports = False  # whether it writes its own audit stream (from 19b)
        self.recorded = 0  # how many records it made: the next is numbered after them
        self.unwritten: list[AuditRecord] = []  # made, not yet written, oldest first
        self.since = 0  # the first history line no record holds yet
        self.ended = False  # it decides nothing more: the writer stops once all is written

    # Temporal: a signal is a message into a running workflow, recorded in its history.
    @workflow.signal(name="answer")
    def answer(self, sent: ForgetAnswer) -> None:
        self.inbox.append(sent)

    # Temporal: a query reads a workflow's state without changing it, and isn't recorded.
    @workflow.query(name="report")
    def current(self) -> ForgetReport:
        return self.report

    async def run(self, start: ForgetStart) -> ForgetReport:
        return await self.drive(start)

    async def drive(self, start: ForgetStart) -> ForgetReport:
        """Carry the request through, writing its own audit stream beside it (from 19b)."""
        self.exports = workflow.patched(EXPORT_PATCH)
        if not self.exports:
            return await self.decide(start)
        # Temporal: a task inside a workflow runs in step with it, and replays the same way. The
        # writer runs beside the request: a store that is down never keeps an answer waiting.
        writer = asyncio.create_task(self.write())
        report = await self.decide(start)
        self.ended = True
        await writer  # it ends once each record is written, and fails if one is refused
        return report

    def record(self, kind: ActKind, by: str | None, roles: list[str], *decided: Decision) -> None:
        """Record an act of the request: who, the `decided` it caused, and the history lines added
        since its last record, so each line is in exactly one record (brief, D77)."""
        if not self.exports:
            return
        self.recorded += 1
        lines = self.report.history[self.since :]
        self.since = len(self.report.history)
        act = Act(kind, by=by, roles=tuple(sorted(roles)))
        at = int(workflow.now().timestamp())  # workflow time, recorded in history (brief, D33)
        made = AuditRecord(self.recorded, at, None, ENGINE, act, list(decided), lines)
        self.unwritten.append(made)

    async def write(self) -> None:
        """Write the request's records to the store as they are made, until it has ended and
        each is written."""
        while True:
            await workflow.wait_condition(lambda: bool(self.unwritten) or self.ended)
            if not self.unwritten:
                return
            sending = list(self.unwritten)
            sent = ExportSent(
                workflow.info().workflow_id, [record_as_data(each) for each in sending], {}, {}
            )
            await workflow.execute_activity(
                "ventoux.audit.append",
                sent,
                start_to_close_timeout=EXPORT_CALL,
                retry_policy=FORGET_EXPORTS,
            )
            self.unwritten = self.unwritten[len(sending) :]

    async def decide(self, start: ForgetStart) -> ForgetReport:
        """Check the proposal, wait for an answer someone may give, and carry it out."""
        proposer = frozenset(start.roles)
        refused = (
            identifier_problem(start.by)
            or role_refusal(self.catalog, start.case, "proposed", start.by, proposer)
            or child_refusal(start.case)
        )
        if refused is not None:
            # Nothing to wait for: the request ends, saying why.
            self.report.status = "refused"
            self.report.history.append(f"refused {start.by}'s proposal: {refused}")
            self.record("forget proposed", start.by, start.roles, self.refused(start, refused))
            return self.report
        # Before anyone answers: Temporal says the same of a case that ended and one that never
        # was, so the key provider tells which it is; the case's definition says whether it
        # keeps its records (brief, D32).
        self.found = await workflow.execute_activity_method(
            ForgetActivities.look_up, start.case, start_to_close_timeout=KEY_CALL
        )
        if (refused := lookup_refusal(start.case, self.found)) is not None:
            self.report.status = "refused"
            self.report.history.append(f"refused {start.by}'s proposal: {refused}")
            self.record("forget proposed", start.by, start.roles, self.refused(start, refused))
            return self.report
        role = forgetting_role(self.catalog, proposer)
        self.report.history.append(f"{start.by} proposed forgetting {start.case}, as {role}")
        self.record(
            "forget proposed", start.by, start.roles, Decision("admitted", target=start.case)
        )
        while True:
            await workflow.wait_condition(lambda: bool(self.inbox))
            sent = self.inbox.pop(0)
            refused = self.refusal(start, sent)
            if refused is not None:
                # Recorded, and the request waits on, as every refusal on Temporal (layer 8c).
                self.report.history.append(f"refused {sent.by}'s answer {sent.outcome}: {refused}")
                self.record("answered", sent.by, sent.roles, self.refused(start, refused))
                continue
            # Its opener approves no change to the case. Asked of the case's start, behind a patch:
            # a request recorded before 12c replays as it was (brief, D51) (brief, D52).
            if sent.outcome == "approve" and workflow.patched("ventoux-forget-opener"):
                found = await workflow.execute_activity_method(
                    ForgetActivities.opener, start.case, start_to_close_timeout=KEY_CALL
                )
                if (refused := opener_refusal(start.case, sent.by, found)) is not None:
                    self.report.history.append(f"refused {sent.by}'s answer approve: {refused}")
                    self.record("answered", sent.by, sent.roles, self.refused(start, refused))
                    continue
            if sent.outcome == "reject":
                self.report.status = "rejected"
                self.report.history.append(f"rejected by {sent.by}")
                self.record(
                    "answered", sent.by, sent.roles, Decision("rejected", target=start.case)
                )
                return self.report
            role = forgetting_role(self.catalog, frozenset(sent.roles))
            self.report.history.append(f"approved by {sent.by}, as {role}")
            approved = Decision("approved", target=start.case)
            # The approval's record holds what it did to the case: asked it to close, or found it
            # closed; or, refused, why.
            if (refused := await self.ask_to_close(start, sent)) is not None:
                self.record("answered", sent.by, sent.roles, approved, self.refused(start, refused))
                return self.report
            self.record("answered", sent.by, sent.roles, approved)
            if (refused := await self.destroy_once_ended(start.case)) is not None:
                self.record("key kept", None, [], self.refused(start, refused))
                return self.report
            # Its last record, written after the key is gone: it holds no sensitive value.
            self.record("key destroyed", None, [], Decision("forgotten", target=start.case))
            return self.report

    @staticmethod
    def refused(start: ForgetStart, reason: str) -> Decision:
        """The decision of a refusal: what was refused, and why, in the line's own words."""
        return Decision("refused", target=start.case, reason=reason)

    async def ask_to_close(self, start: ForgetStart, approved: ForgetAnswer) -> str | None:
        """Ask the case to close as `forgotten`. Why it can't be forgotten if it closed first and
        keeps closed cases; None if it may go on (brief, D32)."""
        case = start.case
        sent = CaseForget(start.by, start.roles, approved.by, approved.roles)
        try:
            await workflow.get_external_workflow_handle(case).signal("forget", sent)
            self.report.history.append(f"{case} asked to close as forgotten")
        except ApplicationError:
            # Temporal found no running case: it has ended (the key says it existed).
            if self.found.forgetting == "while_open":
                # It closed before the approval reached it, and keeps closed cases (brief, D32).
                self.report.status = "refused"
                self.report.history.append(f"refused: {closed_first(case)}")
                return closed_first(case)
            self.report.history.append(f"{case} was already closed")
        # The status changes with its line, after the signal: a query between workflow tasks
        # reads the report as it is, so set before the signal it said `closing the case` with
        # no line saying the case was asked (fix-flaky-temporal).
        self.report.status = "closing the case"
        return None

    async def destroy_once_ended(self, case: str) -> str | None:
        """Wait until the case's workflow has ended, then destroy its key: work still running
        needs the key to read its own values (brief, D32). Why the key is kept, if the case's own
        word as it ended says so; None once it is destroyed."""
        ended = await workflow.execute_activity_method(
            ForgetActivities.case_ended,
            case,
            start_to_close_timeout=CASE_WAIT,
            heartbeat_timeout=ALIVE,
        )
        self.report.history.append(f"{case} ended: {ended.last}")
        self.report.history += [f"{case} flagged: {flag}" for flag in ended.flags]
        # Behind a patch: a request recorded before the fix replays as it was (brief, D51).
        if workflow.patched(ENDING_PATCH) and (kept := ending_refusal(case, ended)) is not None:
            self.report.status = "refused"
            self.report.history.append(f"refused: {kept}")
            return kept
        await workflow.execute_activity_method(
            ForgetActivities.destroy_key, case, start_to_close_timeout=KEY_CALL
        )
        self.report.history.append(f"the key of {case} was destroyed")
        self.report.status = "forgotten"
        return None

    def refusal(self, start: ForgetStart, sent: ForgetAnswer) -> str | None:
        """Why `sent` can't answer the request; None if it may."""
        if (wrong := identifier_problem(sent.by)) is not None:
            return wrong
        if sent.outcome not in OUTCOMES:
            return "a request to forget is answered approve or reject"
        roles = frozenset(sent.roles)
        if sent.outcome == "reject":
            return role_refusal(self.catalog, start.case, "rejected", sent.by, roles)
        return approval_refusal(self.catalog, start.case, start.by, sent.by, roles)


class ForgetActivities:
    """What a request to forget a case asks of the world: the key provider, and the case's
    workflow. Activities, so each answer is recorded in the request's history, and replayed."""

    def __init__(self, client: Client) -> None:
        self.client = client
        self.keys = keys_of(client)  # the key provider the client's codec seals with

    # Temporal: an activity runs outside the workflow, and its result is recorded in history.
    @activity.defn(name="ventoux.forget.look_up")
    async def look_up(self, case: str) -> CaseLookup:
        """The case's key state, whether its workflow runs, and what its definition says."""
        # Off the event loop, as every call to the key service (brief, D78).
        try:
            key = await asyncio.to_thread(self.keys.state, case)
        except KeyUnavailable as down:
            return CaseLookup("", False, "", unavailable=str(down))
        if key != "kept":
            return CaseLookup(key, False, "")
        return CaseLookup(key, await self.still_running(case), await self.forgetting(case))

    async def forgetting(self, case: str) -> str:
        """What the case's family says about forgetting, read from the start of its latest run
        (each run carries the definition, and its release the children it pins): the strictest
        of the case's and its children's (brief, D75); empty if Temporal holds no history of
        it."""
        opening = await self.start_of(case)
        if opening is None:
            return ""
        pinned = {} if opening.release is None else opening.release.cases
        children = [parse_case(definition) for definition in pinned.values()]
        return family_forgetting(parse_case(opening.definition), children)

    @activity.defn(name="ventoux.forget.opener")
    async def opener(self, case: str) -> CaseOpener:
        """Who opened the case, read from the start of its latest run, which carries it."""
        opening = await self.start_of(case)
        return CaseOpener(None, known=False) if opening is None else CaseOpener(opening.opened_by)

    async def start_of(self, case: str) -> CaseStart | None:
        """The start of the case's latest run; None if Temporal holds no history of it."""
        try:
            history = await self.client.get_workflow_handle(case).fetch_history()
        except RPCError as error:
            if error.status == RPCStatusCode.NOT_FOUND:
                return None
            raise
        started = history.events[0].workflow_execution_started_event_attributes
        # Temporal: the start's payloads are decoded as the case's, with its key.
        converter = self.client.data_converter.with_context(
            WorkflowSerializationContext(self.client.namespace, case)
        )
        [opening] = await converter.decode(started.input.payloads, [CaseStart])
        assert isinstance(opening, CaseStart)
        return opening

    @activity.defn(name="ventoux.forget.case_ended")
    async def case_ended(self, case: str) -> CaseEnded:
        """How the case ended, once its latest run no longer runs, however it ended. Only a
        case that completed returned a report (lines and placeholders, no sensitive part, so it
        reads without a key); one refused at its opening, terminated by an operator, failed or
        timed out returned none, and its key goes all the same (tutor review). Waits as long
        as the case runs, asking Temporal again a little less often each time."""
        pause = FIRST_PAUSE
        while (status := await self.ended_as(case)) == WorkflowExecutionStatus.RUNNING:
            activity.heartbeat()  # still running: the wait goes on
            await asyncio.sleep(pause.total_seconds())
            pause = min(pause * 2, LONGEST_PAUSE)
        if status == WorkflowExecutionStatus.COMPLETED:
            handle = self.client.get_workflow_handle(case, result_type=CaseReport)
            returned = await handle.result()
            return CaseEnded(
                returned.history[-1],
                list(returned.flags),
                returned.forgetting,
                returned.forget_taken,
            )
        how = "no longer held by Temporal" if status is None else status.name.lower()
        return CaseEnded(how.replace("_", " "), [])

    async def ended_as(self, case: str) -> WorkflowExecutionStatus | None:
        """The status of the case's latest run; None if Temporal no longer remembers it."""
        try:
            described = await self.client.get_workflow_handle(case).describe()
        except RPCError as error:
            if error.status == RPCStatusCode.NOT_FOUND:
                return None  # nothing of it runs
            raise
        return described.status

    @activity.defn(name="ventoux.forget.destroy_key")
    async def destroy_key(self, case: str) -> None:
        """Destroy the case's key (brief, D15), never while its workflow runs: work in flight
        would no longer read its own values. Refused then, and Temporal retries (brief, D32)."""
        if await self.still_running(case):
            raise ApplicationError(
                f"{case} is still running: its key is destroyed once its workflow has ended"
            )
        await asyncio.to_thread(self.keys.destroy, case)  # off the event loop (brief, D78)

    async def still_running(self, case: str) -> bool:
        """Whether the case's workflow (its latest run) is still running."""
        return await self.ended_as(case) == WorkflowExecutionStatus.RUNNING

    def all(self) -> list[Any]:
        """Each activity, to register with a worker."""
        return [self.look_up, self.case_ended, self.destroy_key, self.opener]


async def propose_forget(
    client: Client,
    workflow: type[ForgetWorkflow],
    case: str,
    by: str,
    roles: list[str],
    task_queue: str,
) -> WorkflowHandle[ForgetWorkflow, ForgetReport]:
    """Propose forgetting the case `case`, as the person `by`, who has `roles`. The request is
    the workflow `<case ID>/forget`; one that ended (refused, rejected, forgotten) leaves room for
    a new one, which the key provider's record keeps from forgetting a case twice."""
    return await client.start_workflow(
        workflow.run,
        ForgetStart(case, by, sorted(roles)),
        id=f"{case}/forget",
        task_queue=task_queue,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )


async def answer_forget(
    request: WorkflowHandle[ForgetWorkflow, ForgetReport],
    outcome: str,
    by: str,
    roles: list[str],
) -> None:
    """Answer the request `approve` or `reject`, as the person `by`, who has `roles`."""
    await request.signal(ForgetWorkflow.answer, ForgetAnswer(outcome, by, sorted(roles)))


async def forget_report(request: WorkflowHandle[ForgetWorkflow, ForgetReport]) -> ForgetReport:
    """How the request is going: its status, and what happened so far."""
    return await request.query(ForgetWorkflow.current)
