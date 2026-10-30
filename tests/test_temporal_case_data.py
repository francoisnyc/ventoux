"""Layer 9a on Temporal: the view filtered in the worker, records shown, refusals recorded.

See docs/layers/09-case-data.md (9a) and docs/guides/cases.md, "Running a case on Temporal".
"""

import asyncio
import dataclasses
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from activity_threads import activity_threads
from replaying import replay_history
from skipping_server import time_skipping
from temporalio.client import Client, WorkflowHandle, WorkflowHistory
from temporalio.converter import DataConverter

from ventoux.temporal.cases import CaseReport, CaseWorkflow, answer, report, shown, start_case, view
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    FAKES,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
    load_definition,
    run_case,
)

ROOT = Path(__file__).parent.parent
QUEUE = "cases"
PEOPLE = {"ana": ["adjuster"], "fay": ["fraud"], "eve": ["support"]}


def guide_claim() -> dict[str, Any]:
    """The case data guide's claim, its first JSON block, as stored data."""
    guide = (ROOT / "docs" / "guides" / "case-data.md").read_text()
    block = guide.split("```json\n")[1].split("```")[0]
    claim: dict[str, Any] = json.loads(block, parse_float=Decimal)
    return claim


def refund_seen_by_support() -> dict[str, Any]:
    """The quickstart's refund, its approved amount seen only by support."""
    refund = load_definition(ROOT / "examples" / "refund" / "refund.json")
    refund["fields"]["approved_amount"]["visible_to"] = ["support"]
    return refund


FILE = {"customer_id": "cus-7", "policy_id": "pol-3", "estimated_damage": 1200, "fraud_score": 12}
EXACT_FILE = {
    name: Decimal(value) if isinstance(value, int) else value for name, value in FILE.items()
}
Case = WorkflowHandle[CaseWorkflow, CaseReport]


def on_temporal[T](
    scenario: Callable[[Client], Awaitable[T]], converter: DataConverter | None = None
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a worker serving the
    development cases: nothing outside is reached. `converter` holds the keys, for a test that
    replays what it recorded; else fresh ones."""

    async def go() -> T:
        async with (
            time_skipping(converter or development_converter()) as environment,
            activity_threads() as threads,
            case_worker(
                environment.client,
                QUEUE,
                DevelopmentCases,
                DevelopmentPlans,
                FAKES,
                activity_executor=threads,
            ),
        ):
            return await asyncio.wait_for(scenario(environment.client), timeout=20)

    return asyncio.run(go())


async def reported(case: Case, holds: Callable[[CaseReport], bool]) -> CaseReport:
    """The case's report once `holds` is true of it: the worker runs on in its own time."""
    for _ in range(100):
        now = await report(case)
        if holds(now):
            return now
        await asyncio.sleep(0.05)
    raise AssertionError(f"the case never got there: {await report(case)}")


def test_the_view_on_temporal_is_the_view_in_memory() -> None:
    async def scenario(client: Client) -> list[Any]:
        case = await start_case(
            client, DevelopmentCases, guide_claim(), EXACT_FILE, "claim-1", QUEUE
        )
        return [await view(case, roles) for roles in (["adjuster"], ["fraud"], ["support"])]

    in_memory = run_case(guide_claim(), file=FILE, answers=[], people=PEOPLE)
    expected = [in_memory.view(roles) for roles in (["adjuster"], ["fraud"], ["support"])]
    seen = on_temporal(scenario)
    # The same view, but for the times: on Temporal they are the workflow's, in memory the
    # test's own (layer 9d). Each value has one, the same for all: they came with the opening.
    assert [dataclasses.replace(v, obtained={}) for v in seen] == [
        dataclasses.replace(v, obtained={}) for v in expected
    ]
    for got, wanted in zip(seen, expected, strict=True):
        assert set(got.obtained) == set(wanted.obtained) == set(wanted.values)
        assert len(set(got.obtained.values())) <= 1  # none for a role that sees nothing


def test_refusals_are_recorded_and_the_case_waits() -> None:
    async def scenario(client: Client) -> list[str]:
        claimed = await start_case(
            client, DevelopmentCases, guide_claim(), EXACT_FILE, "claim-1", QUEUE
        )
        await shown(claimed, "customer_id", "eve", ["support"])
        await shown(claimed, "customer_id", "ana", ["adjuster"])
        claimed_now = await reported(claimed, lambda now: len(now.history) >= 4)
        refund = await start_case(
            client,
            DevelopmentCases,
            refund_seen_by_support(),
            {"order_id": "ord-1", "amount": Decimal(250)},
            "refund-1",
            QUEUE,
        )
        await answer(
            refund, "review#1", "approve", "ana", ["support"], {"approved_amount": Decimal(250)}
        )
        await reported(refund, lambda now: now.waiting_at == ["pay.approval#1"])
        await answer(refund, "pay.approval#1", "approve", "lee", ["support-lead"])
        refund_now = await reported(refund, lambda now: now.history[-1].startswith("refused"))
        assert refund_now.waiting_at == ["pay.approval#1"]  # the case waits on
        return [*claimed_now.history[-2:], refund_now.history[-1]]

    eve_refused = (
        "refused the record of customer_id shown to eve: eve can't see customer_id: it needs "
        "adjuster or fraud"
    )
    lee_refused = (
        "refused lee's answer approve to pay.approval#1: lee can't see approved_amount, which pay "
        "reads: it needs support"
    )
    assert on_temporal(scenario) == [
        eve_refused,
        "ana was shown customer_id (crm cus-7)",
        lee_refused,
    ]


def test_a_case_history_with_shown_replays() -> None:
    async def scenario(client: Client) -> WorkflowHistory:
        case = await start_case(
            client, DevelopmentCases, guide_claim(), EXACT_FILE, "claim-1", QUEUE
        )
        await shown(case, "customer_id", "ana", ["adjuster"])
        await shown(case, "fraud_score", "ana", ["adjuster"])  # refused, and recorded
        await answer(case, "assess#1", "deny", "ana", ["adjuster"])
        await case.result()
        return await case.fetch_history()

    converter = development_converter()
    history = on_temporal(scenario, converter)
    asyncio.run(replay_history(history, [DevelopmentCases], converter))
