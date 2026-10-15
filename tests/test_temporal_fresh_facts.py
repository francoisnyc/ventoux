"""Layer 9d on Temporal: time from workflow time, refreshes that replay, times across
continue-as-new, and the approval sheet.

See docs/layers/09-case-data.md (9d) and docs/guides/case-data.md, "Fresh facts".
"""

import asyncio
import copy
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from temporalio import workflow
from temporalio.client import Client, WorkflowHandle, WorkflowHistory
from temporalio.converter import DataConverter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer

from ventoux.case.visibility import SheetRefused
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    CaseWorkflow,
    answer,
    approval_sheet,
    report,
    start_case,
    view,
)
from ventoux.temporal.worker import SANDBOX, case_worker
from ventoux.testing import (
    FAKES,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
    load_definition,
)

ROOT = Path(__file__).parent.parent
QUEUE = "cases"
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
GUIDE = (ROOT / "docs" / "guides" / "case-data.md").read_text()
PEOPLE = {"ana": ["support"], "sam": ["support-lead"]}
SMALL = {"order_id": "ord-1", "amount": Decimal(80)}
LARGE = {"order_id": "ord-1", "amount": Decimal(250)}
DAYS_3 = timedelta(days=3)
Case = WorkflowHandle[CaseWorkflow, CaseReport]


def refund_fresh() -> dict[str, Any]:
    """The refund with the guide's `check_order` and `pay` (as in tests/test_fresh_facts.py)."""
    section = GUIDE.split("### Saying how fresh a step needs its facts")[1]
    block = section.split("```json\n")[1].split("```")[0]
    steps: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    definition = copy.deepcopy(REFUND)
    definition["steps"] = {"check_order": steps["check_order"], **definition["steps"]}
    definition["steps"]["pay"] = steps["pay"]
    return definition


# Temporal: a case workflow that continues as new after every 2 events, so a short test crosses
# runs (as in tests/test_temporal_case.py). A deployment keeps the default (brief, D27).
@workflow.defn(name="ventoux.case")
class SwitchingCases(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    events_per_run = 2

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def skipping[T](
    scenario: Callable[[WorkflowEnvironment], Awaitable[T]],
    cases: type[CaseWorkflow] = DevelopmentCases,
    converter: DataConverter | None = None,
    activities: Any = FAKES,
) -> T:
    """Run `scenario` on Temporal's time-skipping test server, which moves workflow time on when
    the scenario sleeps: three days pass in an instant, and the case reads them from history."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(
            data_converter=converter or development_converter()
        )
        async with (
            environment,
            case_worker(environment.client, QUEUE, cases, DevelopmentPlans, activities),
        ):
            return await asyncio.wait_for(scenario(environment), timeout=30)

    return asyncio.run(go())


async def settled(case: Case, holds: Callable[[CaseReport], bool]) -> CaseReport:
    """The case's report once `holds` is true of it, asked a bounded number of times."""
    for _ in range(100):
        now = await report(case)
        if holds(now):
            return now
        await asyncio.sleep(0.05)  # real time, for the worker to take its next workflow task
    raise AssertionError(f"the case never got there: {await report(case)}")


async def reviewed_three_days_on(
    environment: WorkflowEnvironment, cases: type[CaseWorkflow], file: dict[str, Any], id: str
) -> Case:
    """A case opened now, its lookup done, then reviewed three days later."""
    client: Client = environment.client
    case = await start_case(client, cases, refund_fresh(), file, id, QUEUE)
    await settled(case, lambda now: "check_order#1 done" in " ".join(now.history))
    await environment.sleep(DAYS_3)
    form = {"approved_amount": file["amount"]}
    await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], form)
    return case


def test_a_case_left_waiting_refreshes_before_paying() -> None:
    # Three days of workflow time pass on the server; the review's signal is stamped with them,
    # so the status is stale and fetched again before `pay` runs.
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        case = await reviewed_three_days_on(environment, DevelopmentCases, SMALL, "refund-1")
        return await case.result()

    ended = skipping(scenario)
    refreshing = ended.history.index(
        "refreshing check_order.status for pay: obtained 3 days ago, at most 1 day"
    )
    assert ended.history[refreshing + 1].startswith("scheduled check_order#2")
    assert any(line.startswith("scheduled pay#1") for line in ended.history[refreshing:])
    assert ended.status == "closed"


def recorded(cases: type[CaseWorkflow], converter: DataConverter) -> WorkflowHistory:
    """The history of a refund reviewed three days on, refreshed and paid."""

    async def scenario(environment: WorkflowEnvironment) -> WorkflowHistory:
        case = await reviewed_three_days_on(environment, cases, SMALL, "refund-1")
        await case.result()
        return await case.fetch_history()

    return skipping(scenario, cases=cases, converter=converter)


def test_a_case_with_a_refresh_replays() -> None:
    # Time is only ever event data: replayed, the review is stamped with the time history
    # recorded, so the same refresh is asked for at the same point, and nothing differs.
    converter = development_converter()
    history = recorded(DevelopmentCases, converter)
    replayer = Replayer(
        workflows=[DevelopmentCases], data_converter=converter, workflow_runner=SANDBOX
    )
    asyncio.run(replayer.replay_workflow(history))


def test_times_cross_continue_as_new_exactly() -> None:
    # The case switches runs every two events; each value's time comes through every switch
    # exactly, so the refresh three days on is decided as it would be in one run.
    async def scenario(environment: WorkflowEnvironment) -> tuple[Any, Any, CaseReport]:
        case = await start_case(
            environment.client, SwitchingCases, refund_fresh(), SMALL, "refund-1", QUEUE
        )
        await settled(case, lambda now: "check_order#1 done" in " ".join(now.history))
        before = await view(case, ["support"])
        await environment.sleep(DAYS_3)
        await answer(
            case, "review#1", "approve", "ana", PEOPLE["ana"], {"approved_amount": Decimal(80)}
        )
        ended = await case.result()
        described = await environment.client.get_workflow_handle("refund-1").describe()
        info = described.raw_description.workflow_execution_info
        return before, (info.first_run_id, described.run_id), ended

    before, (first, last), ended = skipping(scenario, cases=SwitchingCases)
    assert last != first  # it continued as new at least once
    assert all(type(at) is int for at in before.obtained.values())
    assert "refreshing check_order.status for pay: obtained 3 days ago, at most 1 day" in (
        ended.history
    )
    assert ended.status == "closed"


def test_a_stale_answer_on_temporal_needs_attention() -> None:
    # Sam approves three days after Ana's answer, which `pay` needs at most a day old: it came
    # from a person, so the case records why and waits for one. Sam's sheet, read then, says how
    # old each fact is; a sheet for an approval that isn't open is refused.
    definition = refund_fresh()
    definition["steps"]["pay"]["max_age"] = {"approved_amount": "1d"}

    async def scenario(environment: WorkflowEnvironment) -> tuple[Any, CaseReport, str]:
        client = environment.client
        case = await start_case(client, DevelopmentCases, definition, LARGE, "refund-1", QUEUE)
        await answer(
            case, "review#1", "approve", "ana", PEOPLE["ana"], {"approved_amount": Decimal(250)}
        )
        await settled(case, lambda now: now.waiting_at == ["pay.approval#1"])
        # The sheet is read exactly three days after the approved amount was obtained, by the
        # times the case recorded: an age is rounded down, so a few seconds short of three days
        # would read "2 days" (the tutor review found it 1 run in 14).
        asked_at = (await view(case, ["support-lead"])).obtained["approved_amount"]
        await environment.sleep(DAYS_3)
        sheet = await approval_sheet(
            case, "pay.approval#1", ["support-lead"], at=asked_at + 3 * 86400
        )
        with pytest.raises(SheetRefused) as refused:
            await approval_sheet(case, "pay.approval#2", ["support-lead"], at=asked_at)
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        now = await settled(case, lambda now: bool(now.needs_attention))
        return sheet, now, str(refused.value)

    sheet, now, refused = skipping(scenario)
    assert "Amount approved: 250, obtained 3 days ago" in sheet.lines
    assert refused == "pay.approval#2 is not open: there is no sheet to read"
    assert now.needs_attention == [
        (
            "pay#1: approved_amount was obtained 3 days ago, and pay needs it at most 1 day old: "
            "it came from a person, so it can't be fetched again"
        )
    ]
    assert now.status == "open"  # it waits for a person (brief, D17)
