"""Layer 8c: cases run as Temporal workflows, against Temporal's test server.

See docs/layers/08-case.md (8c) and docs/guides/cases.md, "Running a case on Temporal".
"""

import asyncio
import copy
import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from temporalio import workflow
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from temporalio.testing import WorkflowEnvironment

from ventoux.temporal import client as plans
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    CaseWorkflow,
    answer,
    close,
    propose,
    report,
    retry,
    start_case,
)
from ventoux.temporal.converter import DATA_CONVERTER
from ventoux.temporal.worker import case_worker
from ventoux.temporal.workflow import PlanWorkflow, RunReport

# Temporal: this module defines a workflow (`CasesWithPlans`, below), so the workflow sandbox
# imports it afresh. The development catalog is passed through, imported once and shared:
# rebuilt in the sandbox, it would hold contract classes the shared `core` doesn't know.
with workflow.unsafe.imports_passed_through():
    from ventoux.testing import (
        FAKES,
        Activity,
        DevelopmentCases,
        DevelopmentPlans,
        Outcome,
        load_definition,
        run_case,
    )

QUEUE = "cases"
REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
LARGE = {"order_id": "ord-1", "amount": Decimal(250)}
SMALL = {"order_id": "ord-1", "amount": Decimal(40)}


def on_temporal[T](
    scenario: Callable[[Client], Awaitable[T]],
    activities: Mapping[str, Activity] = FAKES,
    cases: type[CaseWorkflow] = DevelopmentCases,
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a worker serving the
    development cases, their plans and `activities`: nothing outside is reached."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(data_converter=DATA_CONVERTER)
        async with (
            environment,
            case_worker(environment.client, QUEUE, cases, DevelopmentPlans, activities),
        ):
            # Bounded: a case that hangs (a workflow task retried forever) fails the test.
            return await asyncio.wait_for(scenario(environment.client), timeout=20)

    return asyncio.run(go())


PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"]}
Case = WorkflowHandle[CaseWorkflow, CaseReport]
PlanRun = WorkflowHandle[PlanWorkflow, RunReport]


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


def skipping[T](
    scenario: Callable[[WorkflowEnvironment], Awaitable[T]],
    activities: Mapping[str, Activity] = FAKES,
    cases: type[CaseWorkflow] = DevelopmentCases,
) -> T:
    """As `on_temporal`, for a scenario that moves time on itself: the server skips time only
    while a client waits on a workflow's result, and a case waiting for a person never ends."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(data_converter=DATA_CONVERTER)
        async with (
            environment,
            case_worker(environment.client, QUEUE, cases, DevelopmentPlans, activities),
        ):
            return await asyncio.wait_for(scenario(environment), timeout=20)

    return asyncio.run(go())


async def past_the_retries(environment: WorkflowEnvironment, case: Case) -> CaseReport:
    """The case's report once a step needs attention, moving time on past the backoff between
    attempts (payments.refund@2: 1 s, then doubling)."""
    for _ in range(100):
        now = await report(case)
        if now.needs_attention:
            return now
        await environment.sleep(timedelta(seconds=10))
    raise AssertionError(f"no step needs attention: {await report(case)}")


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


# --- Slice 3: signals and refusals ---

REVIEW_FORM = {"approved_amount": Decimal(250)}


def test_a_double_click_is_refused_and_recorded() -> None:
    # Ana's second click reaches review#1 after it closed. On Temporal nobody is there to catch
    # a refusal: it is recorded, and the case waits on for what it waited for (layer 6).
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        return await reported(case, lambda now: "refused" in "\n".join(now.history))

    now = on_temporal(scenario)
    assert "refused ana's answer approve to review#1: review#1 is closed" in now.history
    assert now.status == "open"
    assert now.waiting_at == ["pay.approval#1"]


def test_an_answer_before_its_entry_opens_is_refused() -> None:
    # Sam approves the payment before anyone has reviewed the refund: he can't have seen the
    # amount he approves. Refused and recorded; once the review sets it, the approval still waits.
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        return await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])

    now = on_temporal(scenario)
    assert "refused sam's answer approve to pay.approval#1: pay.approval#1 isn't open" in (
        now.history
    )
    assert "sam answered" not in "\n".join(now.history)


def test_an_answer_names_its_entry() -> None:
    # On Temporal an answer names the entry it answers, never a step: after a rework, a late
    # click on "review" would answer review#2, which its sender never saw (layer 6).
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        return await reported(case, lambda now: "refused" in "\n".join(now.history))

    now = on_temporal(scenario)
    assert (
        "refused ana's answer approve to review: name the entry it answers, such as review#1"
    ) in now.history
    assert now.waiting_at == ["review#1"]


# The cases guide's proposed step and close reason, beside the refund (docs/guides/cases.md).
CHECK_ORDER = {
    "kind": "activity",
    "display": {"title": "Look the order up again"},
    "activity": "orders.lookup@1",
    "inputs": {"order_id": {"var": "order_id"}},
    "automatic": False,
    "proposed_by": ["support"],
    "requires": ["review"],
}
DUPLICATE = {"display": {"title": "Duplicate request"}, "roles": ["support"]}
WITH_REQUESTS = {
    **REFUND,
    "steps": {**REFUND["steps"], "check_order": CHECK_ORDER},
    "close_reasons": {"duplicate": DUPLICATE},
}


def test_a_refused_request_is_recorded_and_the_case_waits_on() -> None:
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, WITH_REQUESTS, LARGE, "refund-1", QUEUE)
        await propose(case, "check_order", "eve", [])
        await retry(case, "pay#1", "ana", PEOPLE["ana"])
        await close(case, "duplicate", "eve", [])
        return await reported(case, lambda now: "\n".join(now.history).count("refused") == 3)

    now = on_temporal(scenario)
    assert now.history[-3:] == [
        (
            "refused eve's proposal of check_order: check_order is proposed by support, and eve "
            "has no role"
        ),
        "refused ana's retry of pay#1: pay#1 has not failed: nothing to retry",
        "refused eve's close as duplicate: duplicate is closed by support, and eve has no role",
    ]
    assert now.status == "open"
    assert now.waiting_at == ["review#1"]


def test_a_proposal_and_a_close_by_reason_are_decided_as_in_memory() -> None:
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, WITH_REQUESTS, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await propose(case, "check_order", "ana", PEOPLE["ana"])
        await reported(case, lambda now: "check_order#1 done, giving status" in now.history)
        await close(case, "duplicate", "ana", PEOPLE["ana"])
        return await case.result()

    ended = on_temporal(scenario)
    assert "ana proposed check_order as support" in ended.history
    assert ended.history[-1] == "closed: duplicate, by ana"
    assert ended.status == "closed"


# --- Slice 4: activities, retried as their contracts say ---

SMALL_FORM = {"approved_amount": Decimal(40)}  # under 100: paid with no approval


def test_an_activity_failing_past_its_retries_needs_attention() -> None:
    # payments.refund@2 allows 5 attempts (its contract); past them, the step fails and waits for
    # a person, nothing skipped (brief, D17). The time-skipping server skips the backoff.
    attempts: list[str] = []

    def down(inputs: dict[str, Any]) -> dict[str, Any]:
        attempts.append(inputs["idempotency_key"])
        raise ConnectionError("provider unreachable")

    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        client = environment.client
        case = await start_case(client, DevelopmentCases, REFUND, SMALL, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], SMALL_FORM)
        return await past_the_retries(environment, case)

    now = skipping(scenario, {**FAKES, "payments.refund@2": down})
    assert len(attempts) == 5
    assert now.needs_attention == ["pay#1: payments.refund@2 failed: provider unreachable"]
    assert now.status == "open"


def test_a_declared_outcome_is_never_retried() -> None:
    # A business failure is an answer, not an outage (brief, D17): one attempt, and the step
    # is done with its outcome.
    attempts: list[str] = []

    def declines(inputs: dict[str, Any]) -> dict[str, Any]:
        attempts.append(inputs["idempotency_key"])
        raise Outcome("declined")

    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, REFUND, SMALL, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], SMALL_FORM)
        return await case.result()

    ended = on_temporal(scenario, {**FAKES, "payments.refund@2": declines})
    assert len(attempts) == 1
    assert "pay#1 gave declined" in ended.history
    assert ended.needs_attention == []


def test_every_attempt_and_a_retry_send_the_same_key() -> None:
    # The provider is down for the first attempts of pay#1 and every retry Temporal makes; an
    # operator retries once it is back. Every attempt names the same step run, so a payment that
    # went through before a failure is never made twice (brief, D17, D26).
    keys: list[str] = []
    back = False

    def flaky(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        if not back:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-ord-1"}

    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, str]:
        nonlocal back
        client = environment.client
        case = await start_case(client, DevelopmentCases, REFUND, SMALL, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], SMALL_FORM)
        await past_the_retries(environment, case)
        back = True
        await retry(case, "pay#1", "omar", ["operations"])
        return await case.result(), await first_run(client, "refund-1")

    ended, run_id = skipping(scenario, {**FAKES, "payments.refund@2": flaky})
    assert keys == [f"refund-1/{run_id}/pay#1"] * 6  # five attempts, then the retry's first
    assert "omar retried pay#1 as operations" in ended.history
    assert ended.status == "closed"


# --- Slice 5: plan steps as child workflows ---

PLANS_GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "plans.md"


def refund_order(version: int = 1) -> dict[str, Any]:
    """The plans guide's `refund-order` plan, as stored data, numbered `version`."""
    example = PLANS_GUIDE.read_text().split("```json\n")[1].split("```")[0]
    plan: dict[str, Any] = load_json(example)
    return plan | {"version": version}


def load_json(text: str) -> Any:
    """`text` as JSON, its numbers exact decimals (brief, D20)."""
    return json.loads(text, parse_float=Decimal)


def unapproved_refund_order() -> dict[str, Any]:
    """The plan paying straight after its lookup, with no approval: the engine stops it."""
    plan = refund_order(version=2)
    plan["states"]["check_order"]["on"]["done"] = "pay"
    return plan


# The plans the test deployment supplies: the guide's, one that stops, and one supplied under a
# reference that isn't its own.
TEST_PLANS = {
    "refund-order@1": refund_order(),
    "refund-order@2": unapproved_refund_order(),
    "refund-order@3": refund_order(version=1),
}


# Temporal: a deployment's case workflow names its catalog and plans (the cases guide).
@workflow.defn(name="ventoux.case")
class CasesWithPlans(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    plans = TEST_PLANS

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


SETTLE: dict[str, Any] = {
    "kind": "plan",
    "display": {"title": "Settle the refund"},
    "plan": "refund-order@1",
    "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
    "requires": ["review"],
    "when": {"==": [{"var": "review.outcome"}, "approve"]},
}


def refund_with_plan(plan: str = "refund-order@1", **settle: Any) -> dict[str, Any]:
    """The refund, `pay` replaced by the guide's plan step running `plan`."""
    definition = copy.deepcopy(REFUND)
    del definition["steps"]["pay"], definition["sequence"]
    definition["steps"]["settle"] = {**SETTLE, "plan": plan, **settle}
    return definition


def test_a_plan_that_cannot_run_fails_its_step() -> None:
    # Fail closed, as in memory: a plan that stops in its child workflow, and a plan supplied
    # under another reference, each fail the step, which waits for a person (brief, D17, D28).
    async def scenario(client: Client, plan: str) -> CaseReport:
        definition = refund_with_plan(plan)
        case = await start_case(client, CasesWithPlans, definition, LARGE, f"refund-{plan}", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        return await reported(case, lambda now: now.needs_attention != [])

    stopped = on_temporal(lambda client: scenario(client, "refund-order@2"), cases=CasesWithPlans)
    assert stopped.needs_attention == [
        (
            "settle#1: refund-order@2 stopped: payments.refund@2 is high risk, and nobody "
            "approved this run of pay"
        )
    ]
    misnamed = on_temporal(lambda client: scenario(client, "refund-order@3"), cases=CasesWithPlans)
    assert misnamed.needs_attention == [
        "settle#1: refund-order@3 is supplied as refund-order@1: supply the plan it names"
    ]


async def child_waiting_at(client: Client, id: str, entry: str) -> PlanRun:
    """The child plan `id` once it waits at `entry`. The case starts it in its own time: until
    then, Temporal says it is not found. Asked a bounded number of times."""
    plan: PlanRun = client.get_workflow_handle(id, result_type=RunReport)
    for _ in range(100):
        try:
            if (await plans.report(plan)).waiting_at == entry:
                return plan
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
        await asyncio.sleep(0.05)
    raise AssertionError(f"{id} never waited at {entry}")


def proposed_settle() -> dict[str, Any]:
    """The refund with the plan step, which a team lead proposes; it stays open until closed."""
    definition = refund_with_plan(automatic=False, proposed_by=["support-lead"])
    return definition | {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}


def test_a_plan_step_runs_as_a_child_workflow() -> None:
    # Sam proposes settling the refund. Its plan runs as the child refund-1/settle#1, whose wait
    # is answered on the child. Sam approves nothing he proposed, inside the plan too (brief,
    # D25): refused, and the child waits on; Lee's approval pays, keyed by the case's step run.
    keys: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    async def scenario(client: Client) -> tuple[CaseReport, list[str], str]:
        case = await start_case(client, CasesWithPlans, proposed_settle(), LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await propose(case, "settle", "sam", PEOPLE["sam"])
        plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        await plans.answer(plan, "approve_refund#1", "approve", "sam", PEOPLE["sam"])
        await plans.answer(plan, "approve_refund#1", "approve", "lee", PEOPLE["lee"])
        ended = await plan.result()
        now = await reported(case, lambda now: "settle#1 done" in now.history)
        return now, ended.history, await first_run(client, "refund-1")

    now, plan_history, run_id = on_temporal(
        scenario, {**FAKES, "payments.refund@2": refund}, cases=CasesWithPlans
    )
    assert "refused sam's answer approve: sam proposed settle, so cannot approve it" in (
        plan_history
    )
    assert keys == [f"refund-1/{run_id}/settle#1/pay#1"]
    assert (
        "started settle#1: plan refund-order@1 (order_id from system:opener; amount from "
        f"person:ana), run refund-1/{run_id}/settle#1"
    ) in now.history
    assert now.status == "open"  # it stays open until a person closes it


def test_a_stopped_child_plan_is_retried_with_the_same_keys() -> None:
    # The provider is down: inside the plan, pay fails past its retries, the plan stops, and the
    # step needs attention. Once it is back, an operator retries settle#1: the same step run, so
    # the child starts again under the same ID, and pays with the same key (brief, D26, D28).
    keys: list[str] = []
    back = False

    def flaky(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        if not back:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-ord-1"}

    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, CaseReport, str]:
        nonlocal back
        client = environment.client
        case = await start_case(
            client, CasesWithPlans, refund_with_plan(), LARGE, "refund-1", QUEUE
        )
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        await plans.answer(plan, "approve_refund#1", "approve", "sam", PEOPLE["sam"])
        failed = await past_the_retries(environment, case)
        back = True
        await retry(case, "settle#1", "omar", ["operations"])
        again = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        await plans.answer(again, "approve_refund#1", "approve", "sam", PEOPLE["sam"])
        return failed, await case.result(), await first_run(client, "refund-1")

    failed, ended, run_id = skipping(
        scenario, {**FAKES, "payments.refund@2": flaky}, cases=CasesWithPlans
    )
    assert failed.needs_attention == [
        "settle#1: refund-order@1 stopped: payments.refund@2 failed: provider unreachable"
    ]
    assert keys == [f"refund-1/{run_id}/settle#1/pay#1"] * 6  # five attempts, then the retry's
    assert "omar retried settle#1 as operations" in ended.history
    assert ended.history[-2:] == ["settle#1 done", "closed: nothing left to do"]
