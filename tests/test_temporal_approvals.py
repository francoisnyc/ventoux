"""Approvals by several people on Temporal (layer 11h2): each answer a signal, decided one at a
time; a half-given approval crossing continue-as-new; and what main recorded still replaying.

See docs/layers/11-rules.md (11h2) and the brief, D47.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from skipping_server import time_skipping
from temporalio import workflow
from temporalio.client import Client, WorkflowHistory

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_approvals import FOUR_EYES, PEOPLE
from test_temporal_case import QUEUE, Case, on_temporal, replay, reported, runs_of
from test_temporal_timers import HERE
from worker_threads import worker_threads

from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow, answer, close, start_case
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    FAKES,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
    fixture_converter,
)

LARGE = {"order_id": "ord-1", "amount": Decimal(12000)}
REVIEW_FORM = {"approved_amount": Decimal(12000)}
CLOSABLE = FOUR_EYES | {
    "close_reasons": {"duplicate": {"display": {"title": "Duplicate"}, "roles": ["support"]}}
}

# --- Histories and a carried state recorded under main, before 11h2 (slice 7) ---

# The quickstart's refund: reviewed, approved by Sam and paid. One run, and one that continued as
# new with the approval open, so its last run starts from a state carried before 11h2.
APPROVED_BEFORE = HERE / "before_11h2_approved.json"
SWITCHED_BEFORE = HERE / "before_11h2_switched.json"
# What main carried: a case waiting for its approval, and one paid on an approval its run keeps.
CARRIED_BEFORE = HERE / "before_11h2_carried.json"


def test_histories_from_before_11h2_replay() -> None:
    # With no count, an approval is one person's: every decision schedules what it did, so the
    # new worker replays what the old one recorded (brief, D47).
    for recorded in (APPROVED_BEFORE, SWITCHED_BEFORE):
        history = WorkflowHistory.from_json("refund-1", recorded.read_text())
        replay(history, DevelopmentCases, fixture_converter(recorded))


def test_a_state_from_before_11h2_reads_back() -> None:
    # A state main carried has no approvals collected and no other approvers: it reads as an
    # entry with none given yet, of one person, and an approval given by its one person, exactly
    # as it was (brief, D27, D47).
    carried: dict[str, Any] = json.loads(CARRIED_BEFORE.read_text())
    asked = state_from_data(carried["asked"])
    open_approval = asked.approvals["pay"]
    assert (open_approval.entry, open_approval.count, open_approval.approved) == (
        "pay.approval#1",
        1,
        {},
    )
    paid = state_from_data(carried["paid"])
    kept = paid.runs[-1].approved
    assert kept is not None and kept.approvers == ("sam",)
    # Written again, it is what main wrote, with the new keys at their defaults.
    again = state_as_data(asked)
    assert again["approvals"]["pay"] == carried["asked"]["approvals"]["pay"] | {
        "count": 1,
        "approved": {},
    }
    again = state_as_data(paid)
    assert again["runs"][-1]["approved"] == carried["paid"]["runs"][-1]["approved"] | {"also": []}


# --- Slice 7: answers as signals, and continue-as-new ---


# Temporal: continues as new after every event, so an approval half given crosses a switch.
# A deployment keeps the default (brief, D27).
@workflow.defn(name="ventoux.case")
class EveryEventCases(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    events_per_run = 1

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def test_a_half_given_approval_crosses_continue_as_new() -> None:
    # Sam approves, the case switches with his approval on the open entry, and Lee's approval in
    # the next run makes the count: the refund is paid once (brief, D27, D47).
    paid: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paid.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    async def scenario(client: Client) -> tuple[CaseReport, str, str]:
        case = await start_case(client, EveryEventCases, FOUR_EYES, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        _, before = await runs_of(client, "refund-1")
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        half = "approval of pay by support-lead: 1 of 2 given"
        await reported(case, lambda now: now.waiting_for == [half])
        for _ in range(100):  # until the run holding Sam's approval has continued as new
            _, after = await runs_of(client, "refund-1")
            if after != before:
                break
            await asyncio.sleep(0.05)
        await answer(case, "pay.approval#1", "approve", "lee", PEOPLE["lee"])
        ended = await case.result()
        _, last = await runs_of(client, "refund-1")
        return ended, before, last

    ended, before, last = on_temporal(
        scenario, {**FAKES, "payments.refund@2": refund}, cases=EveryEventCases
    )
    assert last != before
    assert "sam answered pay.approval#1 approve as support-lead: 1 of 2 given" in ended.history
    assert "lee answered pay.approval#1 approve as support-lead: 2 of 2 given" in ended.history
    assert len(paid) == 1
    assert ended.status == "closed"


def before_the_worker(id: str, signals: Callable[[Case], Awaitable[None]]) -> CaseReport:
    """Open the four-eyes case and send it `signals` before any worker runs, then start one: every
    signal sent before then lands in the case's first workflow task, with its opening."""

    async def go() -> CaseReport:
        async with time_skipping(development_converter()) as environment:
            client = environment.client
            case = await start_case(client, DevelopmentCases, CLOSABLE, LARGE, id, QUEUE)
            await signals(case)
            async with (
                worker_threads() as threads,
                case_worker(
                    client,
                    QUEUE,
                    DevelopmentCases,
                    DevelopmentPlans,
                    FAKES,
                    activity_executor=threads,
                ),
            ):
                return await asyncio.wait_for(case.result(), timeout=20)

    return asyncio.run(go())


def test_two_approvals_in_one_task() -> None:
    # The inbox decides one signal at a time, in the order history records them: Sam's double
    # click is refused between his approval and Lee's, which makes the count (brief, D47).
    async def signals(case: Case) -> None:
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await answer(case, "pay.approval#1", "approve", "lee", PEOPLE["lee"])

    ended = before_the_worker("refund-11h2-1", signals)
    asked = ended.history.index(
        "asked pay.approval#1: approval of pay by support-lead, from 2 people"
    )
    assert ended.history[asked + 1 : asked + 4] == [
        "sam answered pay.approval#1 approve as support-lead: 1 of 2 given",
        (
            "refused sam's answer approve to pay.approval#1: sam has already approved "
            "pay.approval#1: it needs 1 more person"
        ),
        "lee answered pay.approval#1 approve as support-lead: 2 of 2 given",
    ]
    assert sum(line.startswith("scheduled pay#") for line in ended.history) == 1
    assert ended.status == "closed"


def test_an_approval_with_the_close_is_refused() -> None:
    # The close is decided first: the entry is cancelled with Sam's approval on it, and Lee's,
    # still in the inbox, is refused and recorded, never counted (brief, D10, D41, D47).
    async def signals(case: Case) -> None:
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await close(case, "duplicate", "ana", PEOPLE["ana"])
        await answer(case, "pay.approval#1", "approve", "lee", PEOPLE["lee"])

    ended = before_the_worker("refund-11h2-2", signals)
    assert (
        "cancelled pay.approval#1: closed as duplicate by ana, with 1 of 2 approvals given"
    ) in ended.history
    assert ended.history[-2:] == [
        "closed: duplicate, by ana",
        "refused lee's answer approve to pay.approval#1: the case is closed",
    ]
    assert not any(line.startswith("scheduled pay#") for line in ended.history)
