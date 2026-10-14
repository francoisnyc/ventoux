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
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError

# Temporal: the workflow sandbox imports a workflow's modules afresh; `case` and `core` are
# deterministic and passed through, imported once and shared (as in `cases.py`).
with workflow.unsafe.imports_passed_through():
    from ventoux.case.forgetting import approval_refusal, forgetting_role, role_refusal
    from ventoux.core.catalog import Catalog
    from ventoux.core.person import identifier_problem
    from ventoux.temporal.cases import CaseForget, CaseReport
    from ventoux.temporal.converter import keys_of

# How long one call to the key provider may take; Temporal retries it until it answers, as a
# system that is down is retried (brief, D17).
KEY_CALL = timedelta(seconds=30)
# Waiting for a case to end: as long as its running work takes, saying it is alive every few
# seconds; if a worker dies, Temporal starts the wait again on another.
CASE_WAIT = timedelta(days=30)
ALIVE = timedelta(seconds=30)


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
# Why a case without a kept key can't be forgotten, by its key's state.
NO_KEY = {
    "never made": "there is no case {case}: no key was ever made for it",
    "destroyed": "{case} was already forgotten: its key was destroyed",
}


@dataclass
class ForgetReport:
    """How a request to forget a case is going, and what it did."""

    # waiting: for an answer; refused: the proposal was; rejected; closing the case: approved,
    # waiting for the case's workflow to end; forgotten: its key was destroyed.
    status: str
    history: list[str] = field(default_factory=list[str])  # what happened, one line each


class ForgetWorkflow:
    """The code of a request to forget a case. A deployment subclasses it to name its catalog,
    whose roles registered to forget may propose and approve, and registers the subclass with
    its case worker (`case_worker(..., forget=)`), as with `CaseWorkflow`."""

    catalog: ClassVar[Catalog]  # the roles that may forget a case are registered in it

    def __init__(self) -> None:
        self.report = ForgetReport("waiting")
        self.inbox: list[ForgetAnswer] = []  # answers not yet judged, in the order they came

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
        """Check the proposal, wait for an answer someone may give, and carry it out."""
        proposer = frozenset(start.roles)
        refused = identifier_problem(start.by) or role_refusal(
            self.catalog, start.case, "proposed", start.by, proposer
        )
        if refused is not None:
            # Nothing to wait for: the request ends, saying why.
            self.report.status = "refused"
            self.report.history.append(f"refused {start.by}'s proposal: {refused}")
            return self.report
        # Before anyone answers: Temporal says the same of a case that ended and one that never
        # was, so the key provider tells which it is, and whether it was forgotten already.
        state = await workflow.execute_activity_method(
            ForgetActivities.key_state, start.case, start_to_close_timeout=KEY_CALL
        )
        if state != "kept":
            self.report.status = "refused"
            self.report.history.append(
                f"refused {start.by}'s proposal: {NO_KEY[state].format(case=start.case)}"
            )
            return self.report
        role = forgetting_role(self.catalog, proposer)
        self.report.history.append(f"{start.by} proposed forgetting {start.case}, as {role}")
        while True:
            await workflow.wait_condition(lambda: bool(self.inbox))
            sent = self.inbox.pop(0)
            refused = self.refusal(start, sent)
            if refused is not None:
                # Recorded, and the request waits on, as every refusal on Temporal (layer 8c).
                self.report.history.append(f"refused {sent.by}'s answer {sent.outcome}: {refused}")
                continue
            if sent.outcome == "reject":
                self.report.status = "rejected"
                self.report.history.append(f"rejected by {sent.by}")
                return self.report
            role = forgetting_role(self.catalog, frozenset(sent.roles))
            self.report.history.append(f"approved by {sent.by}, as {role}")
            await self.carry_out(start, sent)
            return self.report

    async def carry_out(self, start: ForgetStart, approved: ForgetAnswer) -> None:
        """Close the case as `forgotten`, wait until its workflow has ended, then destroy its
        key: work still running needs the key to read its own values (brief, D32)."""
        case = start.case
        self.report.status = "closing the case"
        sent = CaseForget(start.by, start.roles, approved.by, approved.roles)
        try:
            await workflow.get_external_workflow_handle(case).signal("forget", sent)
            self.report.history.append(f"{case} asked to close as forgotten")
        except ApplicationError:
            # Temporal found no running case: it has ended (the key says it existed).
            self.report.history.append(f"{case} was already closed")
        ended = await workflow.execute_activity_method(
            ForgetActivities.case_ended,
            case,
            start_to_close_timeout=CASE_WAIT,
            heartbeat_timeout=ALIVE,
        )
        self.report.history.append(f"{case} ended: {ended.history[-1]}")
        self.report.history += [f"{case} flagged: {flag}" for flag in ended.flags]
        await workflow.execute_activity_method(
            ForgetActivities.destroy_key, case, start_to_close_timeout=KEY_CALL
        )
        self.report.history.append(f"the key of {case} was destroyed")
        self.report.status = "forgotten"

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
    @activity.defn(name="ventoux.forget.key_state")
    async def key_state(self, case: str) -> str:
        """Whether the case's key is kept, was destroyed, or was never made."""
        return self.keys.state(case)

    @activity.defn(name="ventoux.forget.case_ended")
    async def case_ended(self, case: str) -> CaseReport:
        """The report the case returned once its workflow ended: lines and placeholders, no
        sensitive part, so it reads without a key. Waits as long as the case runs."""
        handle = self.client.get_workflow_handle(case, result_type=CaseReport)
        while True:
            try:
                return await asyncio.wait_for(handle.result(), ALIVE.total_seconds() / 3)
            except TimeoutError:
                activity.heartbeat()  # still running: the wait goes on

    @activity.defn(name="ventoux.forget.destroy_key")
    async def destroy_key(self, case: str) -> None:
        """Destroy the case's key (brief, D15)."""
        self.keys.destroy(case)

    def all(self) -> list[Any]:
        """Each activity, to register with a worker."""
        return [self.key_state, self.case_ended, self.destroy_key]


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
