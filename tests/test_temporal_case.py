"""Layer 8c: cases run as Temporal workflows, against Temporal's test server.

See docs/layers/08-case.md (8c) and docs/guides/cases.md, "Running a case on Temporal".
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.testing import WorkflowEnvironment

from ventoux.temporal.cases import CaseReport, CaseWorkflow, answer, report, start_case
from ventoux.temporal.converter import DATA_CONVERTER
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    FAKES,
    Activity,
    DevelopmentCases,
    DevelopmentPlans,
    load_definition,
    run_case,
)

QUEUE = "cases"
REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
LARGE = {"order_id": "ord-1", "amount": Decimal(250)}
SMALL = {"order_id": "ord-1", "amount": Decimal(40)}


def on_temporal[T](
    scenario: Callable[[Client], Awaitable[T]], activities: Mapping[str, Activity] = FAKES
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a worker serving the
    development cases, their plans and `activities`: nothing outside is reached."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(data_converter=DATA_CONVERTER)
        async with (
            environment,
            case_worker(environment.client, QUEUE, DevelopmentCases, DevelopmentPlans, activities),
        ):
            # Bounded: a case that hangs (a workflow task retried forever) fails the test.
            return await asyncio.wait_for(scenario(environment.client), timeout=20)

    return asyncio.run(go())


PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"]}
Case = WorkflowHandle[CaseWorkflow, CaseReport]


async def reported(case: Case, holds: Callable[[CaseReport], bool]) -> CaseReport:
    """The case's report once `holds` is true of it: the worker takes signals and runs on in its
    own time. Asked a bounded number of times, so a case that never gets there fails the test."""
    for _ in range(100):
        now = await report(case)
        if holds(now):
            return now
        await asyncio.sleep(0.05)  # real time, for the worker to take its next workflow task
    raise AssertionError(f"the case never got there: {await report(case)}")


async def first_run(client: Client, id: str) -> str:
    """The run ID of the case's first run, which its keys carry (brief, D27)."""
    described = await client.get_workflow_handle(id).describe()
    return described.raw_description.workflow_execution_info.first_run_id


def test_a_refused_opening_fails_at_once() -> None:
    # The opening gives a field a person sets: the case never opens, and says why, at once;
    # it doesn't hang retrying a workflow task (layer 6, decided while building).
    async def scenario(client: Client) -> None:
        opening = {**LARGE, "approved_amount": Decimal(250)}
        case = await start_case(
            client, DevelopmentCases, REFUND, opening, id="refund-1", task_queue=QUEUE
        )
        with pytest.raises(WorkflowFailureError) as failed:
            await case.result()
        cause: Any = failed.value.cause
        assert isinstance(cause, ApplicationError)
        assert cause.type == "CaseRefused"
        assert cause.message == (
            "approved_amount is set by a person in review, never given at the opening"
        )

    on_temporal(scenario)


def test_a_case_id_opens_one_case() -> None:
    # The case is its ID (brief, D27): its keys name it, so a second case under the same ID,
    # even once the first has closed, would share them. It is refused.
    async def scenario(client: Client) -> None:
        case = await start_case(client, DevelopmentCases, REFUND, SMALL, "refund-1", QUEUE)
        await answer(
            case, "review#1", "approve", "ana", ["support"], {"approved_amount": Decimal(40)}
        )
        assert (await case.result()).status == "closed"
        with pytest.raises(WorkflowAlreadyStartedError):
            await start_case(client, DevelopmentCases, REFUND, SMALL, "refund-1", QUEUE)

    on_temporal(scenario)


def test_a_waiting_case_reports_its_open_entries() -> None:
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        return await reported(case, lambda now: now.waiting_at != [])

    waiting = on_temporal(scenario)
    assert waiting.status == "open"
    assert waiting.waiting_for == ["review by support"]
    assert waiting.waiting_at == ["review#1"]  # what a person's answer names


def test_the_guides_case_gives_the_same_history_as_in_memory() -> None:
    # The quickstart's refund, answered by entry: the same decisions, line for line, the keys
    # naming the case and its first run instead of `memory` (brief, D27).
    async def scenario(client: Client) -> tuple[CaseReport, str]:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(
            case, "review#1", "approve", "ana", PEOPLE["ana"], {"approved_amount": Decimal(250)}
        )
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        return await case.result(), await first_run(client, "refund-1")

    ended, run_id = on_temporal(scenario)
    in_memory = run_case(
        REFUND,
        file={"order_id": "ord-1", "amount": 250},
        answers=[("review", "approve", "ana", {"approved_amount": 250}), ("pay", "approve", "sam")],
        people=PEOPLE,
    )
    assert ended.status == "closed"
    assert [line.replace(f"refund-1/{run_id}/", "memory/") for line in ended.history] == (
        in_memory.history
    )
    assert f"key refund-1/{run_id}/pay#1" in "\n".join(ended.history)
