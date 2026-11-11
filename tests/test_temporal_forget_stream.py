"""A case's requests to forget share one audit stream, numbered on from one to the next
(fix-forget-stream): a second request's records are kept, never refused as other content under a
number the first already used (brief, D77)."""

import asyncio
from pathlib import Path
from typing import Any

from temporalio.client import Client, WorkflowExecutionStatus, WorkflowHandle
from test_audit_export import DownAudit, QuicklyFailingExports
from test_sensitive import FILE, claim
from test_temporal_forget import QUEUE, on_temporal, reported
from test_temporal_sensitive import reported as reported_case

from ventoux.temporal.cases import CaseReport, retry_export, start_case
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import ForgetReport, answer_forget, forget_report, propose_forget
from ventoux.testing import DevelopmentCases, DevelopmentForget, as_json
from ventoux.tooling.audit import FileAudit
from ventoux.tooling.keys import KeyState


class Unreachable(DownAudit):
    """A store that, while down, answers nothing: neither an append nor a read. `DownAudit`
    alone still answers a read, and a request to forget now asks one."""

    refused = 0  # how many reads it refused while down

    def read(self, prefix: str) -> list[dict[str, Any]]:
        if self.down:
            self.refused += 1
            raise PermissionError("the audit database at db.internal refuses this worker's reads")
        return super().read(prefix)


Request = WorkflowHandle[Any, ForgetReport]


async def proposed(client: Client, case: str, by: str) -> Request:
    return await propose_forget(client, DevelopmentForget, case, by, ["privacy"], QUEUE)


async def ended(request: Request) -> ForgetReport:
    """The request's report once its workflow has ended, asked within a bound. Never its
    `result()`: asking for a result lets the test server run its clock on, and a case sitting
    idle then times out, ten years on, so a later request would find it "ended: timed out" and
    the test would pass for a reason it doesn't state (fix-flaky-temporal; the tutor's review of
    #104). A query reads the same report, and moves no clock."""
    await over(request)
    return await forget_report(request)


async def over(workflow: WorkflowHandle[Any, Any]) -> None:
    """Wait, within a bound and moving no clock, until `workflow` no longer runs."""
    for _ in range(300):
        if (await workflow.describe()).status != WorkflowExecutionStatus.RUNNING:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"{workflow.id} never ended")


async def asked(client: Client, case: str, by: str, outcome: str | None, approver: str) -> Any:
    """A request to forget `case`, proposed by `by` and, if `outcome`, answered by `approver`:
    its end."""
    request = await proposed(client, case, by)
    if outcome is not None:
        await answer_forget(request, outcome, approver, ["privacy"])
    return await ended(request)


def acts(store: FileAudit, stream: str) -> list[tuple[int, str, str | None]]:
    """Each record of `stream` in the store: its number, its act and who made it."""
    return [
        (record["number"], record["act"]["kind"], record["act"]["by"])
        for record in store.read(stream)
        if record["stream"] == stream
    ]


def test_a_second_request_to_forget_is_recorded_after_the_first(tmp_path: Path) -> None:
    # Pia's request is rejected; Quinn's, approved, forgets the case, which closes as forgotten.
    # Both are in the one stream, in order: who proposed, who answered, and the key destroyed
    # (brief, D32, D77). A third, made once the case is forgotten, is refused, ends, and is
    # recorded too.
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[list[ForgetReport], KeyState]:
        await start_case(client, DevelopmentCases, claim(), as_json(FILE), "claim-1", QUEUE)
        reports = [
            await asked(client, "claim-1", "pia", "reject", "olu"),
            await asked(client, "claim-1", "quinn", "approve", "rosa"),
            await asked(client, "claim-1", "pia", None, ""),
        ]
        return reports, keys_of(client).state("claim-1")

    reports, key = on_temporal(scenario, audit=store)
    assert [each.status for each in reports] == ["rejected", "forgotten", "refused"]
    # The case was alive when Quinn's request reached it, and closed for it.
    assert "claim-1 ended: closed: forgotten" in reports[1].history
    assert key == "destroyed"
    assert acts(store, "claim-1/forget") == [
        (1, "forget proposed", "pia"),
        (2, "answered", "olu"),
        (3, "forget proposed", "quinn"),
        (4, "answered", "rosa"),
        (5, "key destroyed", None),
        (6, "forget proposed", "pia"),
    ]


def test_a_store_that_is_down_keeps_no_answer_waiting_and_the_key_until_it_is_back(
    tmp_path: Path,
) -> None:
    # The request asks the store where its stream stands beside its work, never before it. With
    # the store down, for reads as for appends, the proposal and the approval are still taken,
    # and the case is asked to close. The key is kept: the case's own records can't be written,
    # so the case doesn't end (brief, D77). Once the store is back and an operator retries the
    # case's export, the case ends, the key goes, and the request's records are written,
    # numbered after the first request's.
    store = Unreachable(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[ForgetReport, KeyState, CaseReport, ForgetReport]:
        case = await start_case(
            client, QuicklyFailingExports, claim(), as_json(FILE), "claim-1", QUEUE
        )
        await asked(client, "claim-1", "pia", "reject", "olu")
        store.down = True
        request = await proposed(client, "claim-1", "quinn")
        await answer_forget(request, "approve", "rosa", ["privacy"])
        # Taken, the store still down: nothing waited for it.
        waiting = await reported(request, lambda now: now.status == "closing the case")
        await reported_case(case, lambda now: bool(now.needs_attention))
        kept = keys_of(client).state("claim-1")
        store.down = False
        await retry_export(case, "omar", ["operations"])
        told = await ended(request)
        # Last, once nothing is left to time out: the report the case returned.
        return waiting, kept, await asyncio.wait_for(case.result(), timeout=15), told

    waiting, kept, closed, told = on_temporal(scenario, cases=QuicklyFailingExports, audit=store)
    assert store.refused > 0  # the worker did ask where the stream stands, and was refused
    assert waiting.history == [
        "quinn proposed forgetting claim-1, as privacy",
        "approved by rosa, as privacy",
        "claim-1 asked to close as forgotten",
    ]
    assert kept == "kept"
    assert "closed: forgotten" in closed.history and closed.forget_taken
    assert told.status == "forgotten"
    assert not any("timed out" in line for line in told.history)
    assert [number for number, _, _ in acts(store, "claim-1/forget")] == [1, 2, 3, 4, 5]


class AppendOnly(FileAudit):
    """A store that keeps what it is given and, while `refusing`, lets the worker read nothing:
    a credential that may only append."""

    refusing = True
    refused = 0  # how many reads it refused

    def read(self, prefix: str) -> list[dict[str, Any]]:
        if self.refusing:
            self.refused += 1
            raise PermissionError("the audit database at db.internal refuses this worker's reads")
        return super().read(prefix)


def test_a_read_the_store_refuses_is_retried_as_an_outage_is(tmp_path: Path) -> None:
    # Appends are taken, so the case writes its records, closes and ends, and the key goes. The
    # request's own records wait: its report says `forgotten`, its workflow runs on, and the
    # store holds nothing of its stream. Once the worker may read, they are written, in order.
    # On purpose: the worker can't tell a credential that may not read from a store that is
    # away, and neither may lose a record (the deployment guide, "The audit store").
    store = AppendOnly(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[ForgetReport, bool, int, ForgetReport]:
        await start_case(client, DevelopmentCases, claim(), as_json(FILE), "claim-1", QUEUE)
        request = await proposed(client, "claim-1", "quinn")
        await answer_forget(request, "approve", "rosa", ["privacy"])
        decided = await reported(request, lambda now: now.status == "forgotten")
        running = (await request.describe()).status == WorkflowExecutionStatus.RUNNING
        written = len(list((tmp_path / "audit").rglob("forget.jsonl")))
        store.refusing = False
        return decided, running, written, await ended(request)

    decided, running, written, told = on_temporal(scenario, audit=store)
    assert store.refused > 0
    assert "claim-1 ended: closed: forgotten" in decided.history
    assert decided.history[-1] == "the key of claim-1 was destroyed"
    assert running and written == 0  # decided, and nothing of it in the store yet
    assert told.status == "forgotten"
    assert [kind for _, kind, _ in acts(store, "claim-1/forget")] == [
        "forget proposed",
        "answered",
        "key destroyed",
    ]
