"""Layer 8c: cases run as Temporal workflows, against Temporal's test server.

See docs/layers/08-case.md (8c) and docs/guides/cases.md, "Running a case on Temporal".
"""

import asyncio
import copy
import dataclasses
import json
import threading
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from activity_threads import activity_threads
from skipping_server import time_skipping
from temporalio import workflow
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle, WorkflowHistory
from temporalio.converter import DataConverter
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer
from temporalio.workflow import NondeterminismError

from ventoux.case.definition import parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import (
    Answered,
    CaseState,
    Completed,
    Event,
    Obtained,
    Opened,
    Proposed,
    StepRun,
)
from ventoux.case.validate import validate_case
from ventoux.core.before_activity import Steering
from ventoux.temporal import client as plans
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    CaseWorkflow,
    answer,
    close,
    propose,
    report,
    retry,
    signal_stop,
    start_case,
)
from ventoux.temporal.converter import ExactPayloadConverter
from ventoux.temporal.worker import SANDBOX, case_worker
from ventoux.temporal.workflow import PlanWorkflow, RunReport
from ventoux.testing import CATALOG, DAY, START
from ventoux.tooling.keys import KeyRefused

# Temporal: this module defines a workflow (`CasesWithPlans`, below), so the workflow sandbox
# imports it afresh. The development catalog is passed through, imported once and shared:
# rebuilt in the sandbox, it would hold contract classes the shared `core` doesn't know.
with workflow.unsafe.imports_passed_through():
    from ventoux.testing import (
        CATALOG,
        FAKES,
        Activity,
        DevelopmentCases,
        DevelopmentPlans,
        Outcome,
        development_converter,
        fixture_converter,
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
    queue: str = QUEUE,
    converter: DataConverter | None = None,
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a worker serving the
    development cases, their plans and `activities`: nothing outside is reached. `converter`
    holds the keys, for a test that replays what it recorded; else fresh ones."""

    async def go() -> T:
        async with (
            time_skipping(converter or development_converter()) as environment,
            activity_threads() as threads,
            case_worker(
                environment.client,
                queue,
                cases,
                DevelopmentPlans,
                activities,
                activity_executor=threads,
            ),
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
        now = await answered_report(case)
        if now is not None and holds(now):
            return now
        await asyncio.sleep(0.05)  # real time, for the worker to take its next workflow task
    raise AssertionError(f"the case never got there: {await answered_report(case)}")


async def answered_report(case: Case) -> CaseReport | None:
    """The case's report, or None if the query isn't answered in time. A query sent as the case
    continues as new can reach the run that is ending, which no longer answers it; asked again,
    it reaches the new run (brief, D27)."""
    try:
        return await asyncio.wait_for(report(case), timeout=1)
    except TimeoutError:
        return None


async def first_run(client: Client, id: str) -> str:
    """The run ID of the case's first run, which its keys carry (brief, D27)."""
    described = await client.get_workflow_handle(id).describe()
    return described.raw_description.workflow_execution_info.first_run_id


def skipping[T](
    scenario: Callable[[WorkflowEnvironment], Awaitable[T]],
    activities: Mapping[str, Activity] = FAKES,
    cases: type[CaseWorkflow] = DevelopmentCases,
    converter: DataConverter | None = None,
) -> T:
    """As `on_temporal`, for a scenario that moves time on itself: the server skips time only
    while a client waits on a workflow's result, and a case waiting for a person never ends.
    `converter` holds the keys, for a test that replays what it recorded; else fresh ones."""

    async def go() -> T:
        async with (
            time_skipping(converter or development_converter()) as environment,
            activity_threads() as threads,
            case_worker(
                environment.client,
                QUEUE,
                cases,
                DevelopmentPlans,
                activities,
                activity_executor=threads,
            ),
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
        # Refused before Temporal is asked: the ID's key was made, and is never made again
        # (brief, D31). Temporal would refuse it too (`REJECT_DUPLICATE`).
        with pytest.raises(KeyRefused, match="^a key was already made for refund-1"):
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
        await reported(
            case,
            lambda now: (
                "check_order#1 done, giving status from untrusted:undeclared" in now.history
            ),
        )
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
    assert now.needs_attention == [
        "pay#1: payments.refund@2 failed with ConnectionError: ‹sensitive›"
    ]
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
        # The quickstart reacts to the decline: support calls the customer, then it closes.
        await reported(case, lambda now: now.waiting_at == ["call_customer#1"])
        await answer(case, "call_customer#1", "called", "ana", PEOPLE["ana"])
        return await case.result()

    ended = on_temporal(scenario, {**FAKES, "payments.refund@2": declines})
    assert len(attempts) == 1
    assert "pay#1 gave declined" in ended.history
    assert "started call_customer#1: waiting for called by support" in ended.history
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
# A lookup, then straight on to a letter, with no wait between: what starts after a close.
LOOKUP_AND_DRAFT = {
    "plan": "lookup-and-draft",
    "version": 1,
    "display": {"title": "Look the order up, then draft a letter"},
    "fields": {"order_id": {"type": "reference", "system": "orders"}},
    "initial": "check_order",
    "states": {
        "check_order": {
            "activity": "orders.lookup@1",
            "inputs": {"order_id": {"var": "order_id"}},
            "on": {"done": "draft", "not_found": "failed"},
        },
        "draft": {
            "activity": "letters.draft@2",
            "inputs": {"to_customer": {"var": "order_id"}, "template": "refund"},
            "on": {"done": "drafted"},
        },
        "drafted": {"final": "succeeded"},
        "failed": {"final": "failed"},
    },
}

TEST_PLANS = {
    "lookup-and-draft@1": LOOKUP_AND_DRAFT,
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
    """The refund, `pay` and `call_customer` replaced by the guide's plan step running `plan`."""
    definition = copy.deepcopy(REFUND)
    del definition["steps"]["pay"], definition["steps"]["call_customer"], definition["sequence"]
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


def test_case_validation_says_what_the_driver_does_with_its_plans() -> None:
    # The driver reads its deployment's plans itself: given the same plans, validation refuses
    # exactly what fails the step on Temporal (brief, D35).
    async def scenario(client: Client, plan: str) -> CaseReport:
        definition = refund_with_plan(plan)
        case = await start_case(client, CasesWithPlans, definition, LARGE, f"check-{plan}", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        return await reported(case, lambda now: now.needs_attention != [])

    for plan in ("refund-order@3", "refund-order@9"):

        def ran(client: Client, plan: str = plan) -> Awaitable[CaseReport]:
            return scenario(client, plan)

        run = on_temporal(ran, cases=CasesWithPlans)
        [issue] = validate_case(parse_case(refund_with_plan(plan)), CATALOG, plans=TEST_PLANS)
        assert issue.code == "UNKNOWN_PLAN"
        assert run.needs_attention == [f"settle#1: {issue.message.split(': supply it with')[0]}"]


def test_a_plan_field_takes_only_a_reference_of_its_system_on_temporal() -> None:
    # G7, as in memory: the driver refuses a made-up order ID before the child starts, and case
    # validation says the same (brief, D30) (brief, D36).
    made_up = {"cat": ["ord-", {"string": [{"var": "amount"}]}]}
    inputs = {"order_id": made_up, "amount": {"var": "approved_amount"}}

    async def scenario(client: Client) -> CaseReport:
        definition = refund_with_plan(inputs=inputs)
        case = await start_case(client, CasesWithPlans, definition, LARGE, "made-up", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        return await reported(case, lambda now: now.needs_attention != [])

    run = on_temporal(scenario, cases=CasesWithPlans)
    found = validate_case(parse_case(refund_with_plan(inputs=inputs)), CATALOG, plans=TEST_PLANS)
    # The error the driver meets; nothing here reacts to the plan failing, which only warns.
    [issue] = [issue for issue in found if issue.severity == "error"]
    assert issue.code == "REFERENCE"
    assert run.needs_attention == [f"settle#1: {issue.message.split(': give it')[0]}"]


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
        "settle#1: refund-order@1 stopped: payments.refund@2 failed with ConnectionError: ‹sensitive›"
    ]
    assert keys == [f"refund-1/{run_id}/settle#1/pay#1"] * 6  # five attempts, then the retry's
    assert "omar retried settle#1 as operations" in ended.history
    assert ended.history[-2:] == ["settle#1 done", "closed: nothing left to do"]


# --- Slice 6: continue-as-new (brief, D27) ---


def test_a_carried_state_reads_back_as_it_was() -> None:
    # The whole state crosses to the new run as data, through the same converter as everything
    # else: an amount stays an exact Decimal, every value keeps its sources, and the order of
    # what waits on people, and of the history, is kept (brief, D27).
    state = case_state(REFUND, LARGE, [("review#1", REVIEW_FORM)])
    payload = ExactPayloadConverter().to_payload(state_as_data(state))
    assert payload is not None
    back = state_from_data(ExactPayloadConverter().from_payload(payload, dict))
    assert back == state
    assert back.values["approved_amount"] == Decimal(250)
    assert isinstance(back.values["approved_amount"], Decimal)
    assert back.sources["approved_amount"] == frozenset({"person:ana"})
    assert list(back.approvals) == ["pay"]
    # A time crosses as the same whole number, not the exact decimal JSON numbers are read as
    # (brief, D33).
    assert back.obtained["approved_amount"] == Obtained(START, None)
    assert type(back.obtained["approved_amount"].at) is int
    # Every field of the state crosses: one added later and forgotten here would vanish at every
    # switch, unnoticed.
    assert set(state_as_data(state)) == {field.name for field in dataclasses.fields(CaseState)}


def test_a_carried_time_that_isnt_whole_is_refused() -> None:
    # Fail closed: a damaged time is never rounded into one the case would decide on.
    data = state_as_data(case_state(REFUND, LARGE, [("review#1", REVIEW_FORM)]))
    data["obtained"]["amount"]["at"] = Decimal("1767225600.5")
    with pytest.raises(ValueError, match="a carried time is a whole number of seconds"):
        state_from_data(data)


def case_state(definition: dict[str, Any], file: dict[str, Any], reviews: list[Any]) -> CaseState:
    """The state `decide` reaches after opening `definition` with `file` and Ana's `reviews`."""
    case = parse_case(definition)
    state, _ = decide(case, CATALOG, CaseState("refund-1/run"), Opened(file, None, at=START))
    for entry, form in reviews:
        answered = Answered(entry, "approve", "ana", frozenset({"support"}), form, at=START)
        state, _ = decide(case, CATALOG, state, answered)
    return state


# Temporal: a case workflow that continues as new after every 2 events, so a short test crosses
# several runs. A deployment keeps the default (brief, D27).
@workflow.defn(name="ventoux.case")
class SwitchingCases(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    events_per_run = 2

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


REWORKABLE = copy.deepcopy(REFUND)
REWORKABLE["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}


async def runs_of(client: Client, id: str) -> tuple[str, str]:
    """The case's first run ID, and its current one."""
    described = await client.get_workflow_handle(id).describe()
    info = described.raw_description.workflow_execution_info
    return info.first_run_id, info.execution.run_id


def test_entry_counts_cross_continue_as_new() -> None:
    # Reviewed, sent back, reworked to 900 and approved, over three runs of the case: every count
    # carries on, so the rework is review#2 and its approval pay.approval#2, and the payment's
    # key names the case's first run, as every key of the case does (brief, D27).
    async def scenario(client: Client) -> tuple[CaseReport, tuple[str, str], list[str]]:
        case = await start_case(client, SwitchingCases, REWORKABLE, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await propose(case, "review", "ana", PEOPLE["ana"])
        await reported(case, lambda now: now.waiting_at == ["review#2"])
        rework = {"approved_amount": Decimal(900)}
        await answer(case, "review#2", "approve", "ana", PEOPLE["ana"], rework)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#2"])
        await answer(case, "pay.approval#2", "approve", "sam", PEOPLE["sam"])
        ended = await case.result()
        return ended, await runs_of(client, "refund-1"), keys

    keys: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    ended, (first, last), paid = on_temporal(
        scenario, {**FAKES, "payments.refund@2": refund}, cases=SwitchingCases
    )
    assert last != first  # the case continued as new at least once
    assert "started review#2: waiting for approve or reject by support" in ended.history
    assert "asked pay.approval#2: approval of pay by support-lead" in ended.history
    assert paid == [f"refund-1/{first}/pay#1"]
    assert ended.history[0] == "opened by system:opener, with amount and order_id"  # as one
    assert ended.status == "closed"


def test_an_open_entry_survives_the_switch() -> None:
    # Ana's review makes the second event, and the case switches with pay.approval#1 open: Sam
    # answers it after the switch, by the same name, and his double click is refused as closed.
    # Then the same answers sent at once, landing wherever the switch falls: whichever run
    # decides them, the approval counts once and the refund is paid once (brief, D27).
    paid: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paid.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    async def after_the_switch(client: Client) -> tuple[CaseReport, str]:
        case = await start_case(client, SwitchingCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        for _ in range(100):  # until the case has continued as new
            first, last = await runs_of(client, "refund-1")
            if last != first:
                break
            await asyncio.sleep(0.05)
        assert (await reported(case, lambda now: True)).waiting_at == ["pay.approval#1"]
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        return await case.result(), first

    async def at_once(client: Client) -> CaseReport:
        case = await start_case(client, SwitchingCases, REFUND, LARGE, "refund-2", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        return await case.result()

    activities = {**FAKES, "payments.refund@2": refund}
    ended, first = on_temporal(after_the_switch, activities, cases=SwitchingCases)
    assert ended.history.count("sam answered pay.approval#1 approve as support-lead") == 1
    assert "refused sam's answer approve to pay.approval#1: pay.approval#1 is closed" in (
        ended.history
    )
    assert paid == [f"refund-1/{first}/pay#1"]
    assert ended.status == "closed"
    paid.clear()
    ended = on_temporal(at_once, activities, cases=SwitchingCases)
    assert ended.history.count("sam answered pay.approval#1 approve as support-lead") == 1
    assert len(paid) == 1
    assert ended.status == "closed"


def test_a_switch_waits_while_an_activity_runs() -> None:
    # The case reaches its count with pay#1 running. It must not switch until the payment is back:
    # its result would come back to a run that has ended, and be lost (brief, D27).
    release = threading.Event()
    calls: list[str] = []

    def held(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs["idempotency_key"])
        release.wait(timeout=10)
        return {"refund_id": "refund-ord-1"}

    staying = {**REFUND, "stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}

    async def scenario(client: Client) -> tuple[tuple[str, str], CaseReport, tuple[str, str]]:
        case = await start_case(client, SwitchingCases, staying, SMALL, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], SMALL_FORM)
        await reported(
            case, lambda now: any(line.startswith("scheduled pay#1") for line in now.history)
        )
        await asyncio.sleep(0.5)  # time enough to switch, were it allowed
        while_running = await runs_of(client, "refund-1")
        release.set()
        paid = await reported(
            case,
            lambda now: "pay#1 done, giving refund_id from untrusted:undeclared" in now.history,
        )
        await close(case, "duplicate", "ana", PEOPLE["ana"])
        await case.result()
        return while_running, paid, await runs_of(client, "refund-1")

    (first, during), paid, (_, last) = on_temporal(
        scenario, {**FAKES, "payments.refund@2": held}, cases=SwitchingCases
    )
    assert during == first  # no switch while the payment ran
    assert last != first  # and one once it was back
    assert len(calls) == 1
    assert paid.history.count("pay#1 done, giving refund_id from untrusted:undeclared") == 1


# --- Slice 7: replay ---


# Temporal: replay runs a workflow's code again against a recorded history, as a new worker does
# after a crash. This version was changed to ask for a timer before the case opens.
@workflow.defn(name="ventoux.case")
class ChangedCases(CaseWorkflow):
    catalog = DevelopmentCases.catalog

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        await workflow.sleep(1)  # a command the recorded history never saw
        return await self.drive(start)


def finished_case(converter: DataConverter) -> WorkflowHistory:
    """The history of the guide's refund, reviewed, approved after a double click, and paid, its
    parts sealed by `converter`."""

    async def scenario(client: Client) -> WorkflowHistory:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await case.result()
        return await case.fetch_history()

    return on_temporal(scenario, converter=converter)


def replay(
    history: WorkflowHistory, workflow_class: type[CaseWorkflow], converter: DataConverter
) -> None:
    """Replay `history` against `workflow_class`, as a worker would after a restart, with the
    converter that recorded it: its sealed parts open only with their keys (brief, D31)."""
    replayer = Replayer(
        workflows=[workflow_class], data_converter=converter, workflow_runner=SANDBOX
    )
    asyncio.run(replayer.replay_workflow(history))


def test_a_case_history_replayed_with_changed_code_fails() -> None:
    # Temporal refuses rather than let the case go another way than it went: the case waits
    # until the code is fixed (brief, D17).
    with pytest.raises(NondeterminismError):
        converter = development_converter()
        replay(finished_case(converter), ChangedCases, converter)


def test_a_case_history_replays() -> None:
    # `decide` reads no clock, randomness or I/O, and the inbox decides events in the order
    # history records them: the same code asks for the same things, and the recorded answers,
    # refusals and results are read back, nothing done again.
    converter = development_converter()
    replay(finished_case(converter), DevelopmentCases, converter)

    # A case that continued as new: its last run starts from the carried state, and replays.
    async def switched(client: Client) -> WorkflowHistory:
        case = await start_case(client, SwitchingCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await case.result()
        first, last = await runs_of(client, "refund-1")
        assert last != first
        return await case.fetch_history()  # the latest run's

    converter = development_converter()
    replay(
        on_temporal(switched, cases=SwitchingCases, converter=converter), SwitchingCases, converter
    )

    # A case whose plan step ran as a child workflow: the case's history records the child's
    # start and result, and replays.
    async def with_child(client: Client) -> WorkflowHistory:
        case = await start_case(
            client, CasesWithPlans, refund_with_plan(), LARGE, "refund-1", QUEUE
        )
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        await plans.answer(plan, "approve_refund#1", "approve", "sam", PEOPLE["sam"])
        await case.result()
        return await case.fetch_history()

    converter = development_converter()
    replay(
        on_temporal(with_child, cases=CasesWithPlans, converter=converter),
        CasesWithPlans,
        converter,
    )


# --- Layer 11a: rules on Temporal (brief, D27, D38) ---

FLAGGING = copy.deepcopy(REWORKABLE)
FLAGGING["milestones"] = {"reviewing": {"display": {"title": "Under review"}}}
FLAGGING["rules"] = {
    "flag_review": {
        "display": {"title": "Mark the case under review"},
        "on": {"started": "review"},
        "then": {"reach": ["reviewing"]},
    }
}


def test_rule_firings_cross_continue_as_new_and_replay() -> None:
    # A rule fires on each start of the review; the review is reworked over several runs of the
    # case. Its firings cross with the rest of the state, so the second is flag_review#2, never a
    # second #1; and the last run, started from the carried state, replays.
    async def scenario(client: Client) -> tuple[CaseReport, tuple[str, str], WorkflowHistory]:
        case = await start_case(client, SwitchingCases, FLAGGING, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await propose(case, "review", "ana", PEOPLE["ana"])
        await reported(case, lambda now: now.waiting_at == ["review#2"])
        await answer(case, "review#2", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#2"])
        await answer(case, "pay.approval#2", "approve", "sam", PEOPLE["sam"])
        ended = await case.result()
        return ended, await runs_of(client, "refund-1"), await case.fetch_history()

    converter = development_converter()
    ended, (first, last), history = on_temporal(scenario, cases=SwitchingCases, converter=converter)
    assert last != first  # the case continued as new at least once
    assert [line for line in ended.history if line.startswith("flag_review#")] == [
        "flag_review#1 on started review: reaching reviewing",
        "flag_review#2 on started review: reaching reviewing",
    ]
    assert ended.history.count("reached reviewing") == 1
    replay(history, SwitchingCases, converter)


# --- Layer 11b: a history recorded before 11b still replays (brief, D17) ---

BEFORE_11B = Path(__file__).parent / "histories" / "before_11b_proposal.json"


def test_a_history_from_before_11b_replays() -> None:
    # Recorded under 11a's code: a case where a person proposed check_order, which ran, and the
    # case was closed as a duplicate. 11b decides this path the same way, so the new worker
    # replays it: its new state fields read back empty from an old run. It shows no more: on a path
    # 11b decides differently (a proposal on a stale fact, beside a failed run, a condition
    # reading untrusted data), Temporal refuses the history, and the case waits until the code is
    # fixed (brief, D17); see the note, 11b, "From the second review". No part of it is sealed
    # (no form, no sensitive field), so it replays with no key.
    history = WorkflowHistory.from_json("refund-1", BEFORE_11B.read_text())
    replay(history, DevelopmentCases, development_converter())


# --- Layer 11c: a history recorded before 11c still replays (brief, D17) ---

BEFORE_11C = Path(__file__).parent / "histories" / "before_11c_plan_closed.json"


def test_a_history_from_before_11c_replays() -> None:
    # Recorded under 11b's driver: the refund's plan step waits for a team lead when Ana closes the
    # case as a duplicate, so the case signals its child `stop` with no reason, and the plan ends
    # cancelled. 11c gives the signal a reason whose default keeps that text, so the new worker
    # replays it (brief, D28, D40). Ana's review is sealed with the case's key, so the
    # fixture's development key is kept beside it, as a test server's would be.
    history = WorkflowHistory.from_json("refund-1", BEFORE_11C.read_text())
    replay(history, CasesWithPlans, fixture_converter(BEFORE_11C))


# --- The fix of a rejected retry: a history recorded before it still replays (brief, D26) ---

RETRY_REJECTED = Path(__file__).parent / "histories" / "before_fix_retry_rejected.json"


def test_a_history_with_a_rejected_retry_replays() -> None:
    # Recorded under main, before the fix: pay#1 fails, the review is answered again for more,
    # an operator retries pay#1, its approval is rejected (recorded then as `pay#2 won't run`),
    # and Ana closes the case as a duplicate. The fix sends the rejected retry back to failed,
    # which schedules nothing either, so the new worker replays it. A history that went on to
    # retry pay#1 again replays while that retry asks an approval, and not once it would start
    # unasked (the next two tests; the fix's note, decision 4).
    history = WorkflowHistory.from_json("refund-1", RETRY_REJECTED.read_text())
    replay(history, DevelopmentCases, fixture_converter(RETRY_REJECTED))


RETRIED_AGAIN = Path(__file__).parent / "histories" / "before_fix_retry_rejected_retried.json"
UNAPPROVED = Path(__file__).parent / "histories" / "before_fix_retry_rejected_unapproved.json"


def test_a_history_that_retried_a_rejected_retry_again_replays_if_it_asks_again() -> None:
    # Recorded under main: the same case, but an operator retries pay#1 again after the
    # rejection, which main refused ("has not failed"), before Ana closes it. The fix takes
    # that retry, and pay#1 asks a new approval: state, not a command, so the history replays.
    history = WorkflowHistory.from_json("refund-1", RETRIED_AGAIN.read_text())
    replay(history, DevelopmentCases, fixture_converter(RETRIED_AGAIN))


def test_a_history_whose_retry_again_would_start_unasked_doesnt_replay() -> None:
    # The known limit (the fix's note, decision 4). Recorded under main: after the rejection
    # the review is answered again for 80, which needs no approval, then pay#1 is retried again,
    # refused by main. The fix takes the retry and schedules pay#1 at once, so Temporal refuses
    # the history rather than let the case go another way than it went, and the case waits
    # until the code is fixed (brief, D17).
    history = WorkflowHistory.from_json("refund-1", UNAPPROVED.read_text())
    with pytest.raises(NondeterminismError):
        replay(history, DevelopmentCases, fixture_converter(UNAPPROVED))


# The refund whose review may be answered again, and a close reason: the fix's path.
RESCUABLE = copy.deepcopy(REFUND)
RESCUABLE["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
RESCUABLE["close_reasons"] = {"duplicate": DUPLICATE}


def test_a_rejected_retry_on_temporal() -> None:
    # pay#1 fails past its retries; the review is answered again for 250, so the operator's
    # retry asks for an approval, which Sam rejects: pay#1 needs attention again, with no new
    # run. Retried again once the provider is back, it asks again and pays once, every attempt
    # with the first run's key (brief, D17, D26) (the fix's note, decision 1).
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
        file = {"order_id": "ord-1", "amount": Decimal(300)}
        case = await start_case(client, DevelopmentCases, RESCUABLE, file, "refund-1", QUEUE)
        await answer(
            case, "review#1", "approve", "ana", PEOPLE["ana"], {"approved_amount": Decimal(80)}
        )
        await past_the_retries(environment, case)
        await propose(case, "review", "ana", PEOPLE["ana"])
        await reported(case, lambda now: now.waiting_at == ["review#2"])
        await answer(case, "review#2", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await retry(case, "pay#1", "omar", ["operations"])
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await answer(case, "pay.approval#1", "reject", "sam", PEOPLE["sam"])
        rejected = await reported(case, lambda now: now.needs_attention != [])
        back = True
        await retry(case, "pay#1", "omar", ["operations"])
        await reported(case, lambda now: now.waiting_at == ["pay.approval#2"])
        await answer(case, "pay.approval#2", "approve", "sam", PEOPLE["sam"])
        return rejected, await case.result(), await first_run(client, "refund-1")

    rejected, ended, run_id = skipping(scenario, {**FAKES, "payments.refund@2": flaky})
    assert rejected.needs_attention == [
        (
            "pay#1: sam rejected pay.approval#1, the approval of its retry: retry it to ask "
            "again, or close the case"
        )
    ]
    assert "pay#1 won't run: sam rejected pay.approval#1, so it needs attention again" in (
        rejected.history
    )
    assert keys == [f"refund-1/{run_id}/pay#1"] * 6  # five attempts, then the second retry's
    assert ended.status == "closed"


# --- Layer 11b: a waiting start and a rule's record cross continue-as-new (brief, D27, D39) ---

# The refund with the order looked up, and `pay` proposed by support only on a status at most a
# day old.
PROPOSED_FRESH = copy.deepcopy(REFUND)
PROPOSED_FRESH["steps"]["check_order"] = {
    "kind": "activity",
    "display": {"title": "Look the order up"},
    "activity": "orders.lookup@2",
    "inputs": {"order_id": {"var": "order_id"}},
}
PROPOSED_FRESH["steps"]["pay"] |= {
    "automatic": False,
    "proposed_by": ["support"],
    "requires": ["check_order"],
    "when": {
        "and": [
            {"==": [{"var": "review.outcome"}, "approve"]},
            {"==": [{"var": "check_order.status"}, "delivered"]},
        ]
    },
    "max_age": {"check_order.status": "1d"},
}
PROPOSED_FRESH |= {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}

# The refund with `pay` started by a rule once the review is approved, and by nothing else.
PAID_BY_A_RULE = copy.deepcopy(REFUND)
PAID_BY_A_RULE["steps"]["pay"]["automatic"] = False
PAID_BY_A_RULE["rules"] = {
    "pay_approved": {
        "display": {"title": "Pay an approved refund"},
        "on": {"answered": "review"},
        "when": {"==": [{"var": "review.outcome"}, "approve"]},
        "then": {"start": ["pay"]},
    }
}


def test_a_waiting_start_crosses_continue_as_new() -> None:
    # A proposal waiting for its fact to be fetched again, and what a rule read for the run it
    # started, are state like the rest: they cross to the next run as data (brief, D27)
    # (brief, D39).
    case = parse_case(PROPOSED_FRESH)
    events: list[Event] = [
        Opened(SMALL, None, at=START),
        Completed("check_order#1", {"status": "delivered"}, at=START),
        Answered("review#1", "approve", "ana", frozenset({"support"}), SMALL_FORM, at=START),
        Proposed("pay", "ana", frozenset({"support"}), at=START + 3 * DAY),
    ]
    state = CaseState("refund-1/run")
    for event in events:
        state, _ = decide(case, CATALOG, state, event)
    assert state.waiting_to_start == ["pay"] and state.proposers == {"pay": "ana"}
    # What a run keeps for its retry crosses too: who may approve nothing in it, the untrusted
    # values that chose it ran, and whether it has started.
    kept = state.runs[0]
    kept.excluded = {"sam": "sam set lead_check.outcome, which decided that settle_on#1 started it"}
    kept.steered = (Steering("settle's condition reads note", frozenset({"untrusted:customer"})),)
    kept.started = False  # failed before it started: its retry will be its first start
    payload = ExactPayloadConverter().to_payload(state_as_data(state))
    assert payload is not None
    assert state_from_data(ExactPayloadConverter().from_payload(payload, dict)) == state

    # On Temporal the switch waits while the refresh runs (layer 8c), so what crosses a live
    # switch is a rule's record: Sam's answer decided that pay runs, so after the switch he still
    # can't approve it; Lee does. The last run, started from the carried state, replays.
    async def scenario(client: Client) -> tuple[CaseReport, tuple[str, str], WorkflowHistory]:
        case = await start_case(client, SwitchingCases, PAID_BY_A_RULE, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "sam", PEOPLE["sam"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await answer(case, "pay.approval#1", "approve", "sam", PEOPLE["sam"])
        await answer(case, "pay.approval#1", "approve", "lee", PEOPLE["lee"])
        ended = await case.result()
        return ended, await runs_of(client, "refund-1"), await case.fetch_history()

    converter = development_converter()
    ended, (first, last), history = on_temporal(scenario, cases=SwitchingCases, converter=converter)
    assert last != first  # the case continued as new with the approval open
    assert "pay_approved#1 on answered review: starting pay" in ended.history
    assert (
        "refused sam's answer approve to pay.approval#1: sam set review.outcome, which decided "
        "that pay_approved#1 started pay, so cannot approve it"
    ) in ended.history
    assert "lee answered pay.approval#1 approve as support-lead" in ended.history
    assert ended.status == "closed"
    replay(history, SwitchingCases, converter)


# --- Slice 8: the guide, as the engine does it ---

CASES_GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "cases.md").read_text()
ON_TEMPORAL = CASES_GUIDE.split("## Running a case on Temporal\n")[1]


def test_the_guides_refusals_on_temporal_are_what_the_engine_records() -> None:
    # Every refusal line the guide shows, from one case: the review answered by step, then twice;
    # a proposal by someone with no role; a retry of the failed payment by someone who doesn't
    # operate; a close by someone the reason doesn't name. The case waits on through them all.
    shown = [line.strip() for line in ON_TEMPORAL.splitlines() if line.startswith("  refused ")]
    assert len(shown) == 5

    def down(inputs: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("provider unreachable")

    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        client = environment.client
        case = await start_case(client, DevelopmentCases, WITH_REQUESTS, SMALL, "refund-1", QUEUE)
        await answer(case, "review", "approve", "ana", PEOPLE["ana"], SMALL_FORM)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], SMALL_FORM)
        await answer(case, "review#1", "approve", "sam", PEOPLE["sam"], SMALL_FORM)
        await propose(case, "check_order", "eve", [])
        await past_the_retries(environment, case)
        await retry(case, "pay#1", "ana", PEOPLE["ana"])
        await close(case, "duplicate", "eve", [])
        return await reported(case, lambda now: now.history[-1].startswith("refused eve's close"))

    now = skipping(scenario, {**FAKES, "payments.refund@2": down})
    for line in shown:
        assert line in now.history
    assert now.status == "open"
    assert now.needs_attention == [
        "pay#1: payments.refund@2 failed with ConnectionError: ‹sensitive›"
    ]


def test_the_guides_client_example_runs_as_written() -> None:
    # Our own documentation, run so it can't drift from the code; never a definition (data).
    # The guide's top-level `await`s run inside a coroutine, against the development workflow.
    example = ON_TEMPORAL.split("```python\n")[3].split("```")[0]
    body = "".join(f"    {line}\n" for line in example.splitlines())
    namespace: dict[str, Any] = {"RefundCases": DevelopmentCases, "refund": REFUND}
    exec(f"async def guide(client):\n{body}", namespace)  # noqa: S102 -- our guide, as in layer 7

    async def scenario(client: Client) -> None:
        await namespace["guide"](client)

    on_temporal(scenario, queue="refunds")  # the guide's task queue


# --- Tutor review: closing a case stops its plan steps ---


def test_closing_a_case_stops_its_child_plan() -> None:
    # The tutor's probe: the child refund-1/settle#1 waits for a team lead's approval when Ana
    # closes the case as a duplicate. Lee's approval on the child, after the close, can't approve
    # the refund: refused, or no longer given (the child has ended). Nothing is paid, and the case
    # closes as a duplicate (brief, D10, D28).
    paid: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paid.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    definition = refund_with_plan() | {"close_reasons": {"duplicate": DUPLICATE}}

    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, CasesWithPlans, definition, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        await close(case, "duplicate", "ana", PEOPLE["ana"])
        await reported(case, lambda now: now.status != "open")
        try:
            await plans.answer(plan, "approve_refund#1", "approve", "lee", PEOPLE["lee"])
        except RPCError:
            pass  # the child has ended: the answer can no longer be given
        return await case.result()

    ended = on_temporal(scenario, {**FAKES, "payments.refund@2": refund}, cases=CasesWithPlans)
    assert paid == []
    assert "settle#1 cancelled: the case is closing" in ended.history
    assert ended.history[-1] == "closed: duplicate, by ana"
    assert ended.flags == []


def test_an_activity_running_in_a_stopped_plan_finishes() -> None:
    # Ana closes the case while the plan's lookup runs. It finishes, once: it may already have
    # acted (brief, D10). Then the plan goes on to its approval, which is cancelled at once:
    # nothing is paid, its step run is cancelled, and the case closes.
    release = threading.Event()
    looked_up: list[str] = []
    paid: list[str] = []

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        looked_up.append(inputs["order_id"])
        release.wait(timeout=10)
        return {"status": "delivered"}

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paid.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    definition = refund_with_plan() | {"close_reasons": {"duplicate": DUPLICATE}}

    async def scenario(client: Client) -> tuple[CaseReport, RunReport]:
        case = await start_case(client, CasesWithPlans, definition, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        for _ in range(100):  # until the lookup runs inside the child
            if looked_up:
                break
            await asyncio.sleep(0.05)
        await close(case, "duplicate", "ana", PEOPLE["ana"])
        await reported(case, lambda now: now.status != "open")
        release.set()
        child: PlanRun = client.get_workflow_handle("refund-1/settle#1", result_type=RunReport)
        return await case.result(), await child.result()

    activities = {**FAKES, "orders.lookup@1": lookup, "payments.refund@2": refund}
    ended, plan = on_temporal(scenario, activities, cases=CasesWithPlans)
    assert looked_up == ["ord-1"]  # finished, never cut off or run again
    assert "orders.lookup@1 gave done" in plan.history
    # Its approval was reached and cancelled at once: the plan ends there, no answer taken.
    assert plan.history[-1].startswith("waiting at approve_refund#1")
    assert "entered pay" not in plan.history
    assert plan.status == "cancelled"
    assert paid == []
    assert "settle#1 cancelled: the case is closing" in ended.history
    assert ended.history[-1] == "closed: duplicate, by ana"


def test_a_stopped_plan_starts_nothing_new() -> None:
    # Ana closes the case while the plan's lookup runs, and the plan's next state is a letter.
    # The lookup finishes; the letter is never scheduled: nothing new starts while a case closes
    # (brief, D10, D28).
    release = threading.Event()
    looked_up: list[str] = []
    drafted: list[str] = []

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        looked_up.append(inputs["order_id"])
        release.wait(timeout=10)
        return {"status": "delivered"}

    def draft(inputs: dict[str, Any]) -> dict[str, Any]:
        drafted.append(inputs["idempotency_key"])
        return {"draft_id": "draft-1"}

    inputs = {"order_id": {"var": "order_id"}}
    definition = refund_with_plan("lookup-and-draft@1", inputs=inputs) | {
        "close_reasons": {"duplicate": DUPLICATE}
    }

    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, CasesWithPlans, definition, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        for _ in range(100):  # until the lookup runs inside the child
            if looked_up:
                break
            await asyncio.sleep(0.05)
        await close(case, "duplicate", "ana", PEOPLE["ana"])
        await reported(case, lambda now: now.status != "open")
        release.set()
        return await case.result()

    activities = {**FAKES, "orders.lookup@1": lookup, "letters.draft@2": draft}
    ended = on_temporal(scenario, activities, cases=CasesWithPlans)
    assert looked_up == ["ord-1"]
    assert drafted == []
    assert "settle#1 cancelled: the case is closing" in ended.history
    assert ended.history[-1] == "closed: duplicate, by ana"


# --- Tutor review, second pass: a stopped plan reports what finished after the close ---


def refund_then_letter() -> dict[str, Any]:
    """The guide's `refund-order`, drafting a letter after the payment before it ends `paid`."""
    plan = refund_order(version=4)
    plan["states"]["pay"]["on"]["done"] = "draft"
    plan["states"]["draft"] = {
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "order_id"}, "template": "refund"},
        "on": {"done": "paid"},
    }
    return plan


LETTER_PLANS = {**TEST_PLANS, "refund-order@4": refund_then_letter()}


@workflow.defn(name="ventoux.case")
class CasesWithLetters(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    plans = LETTER_PLANS

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


async def close_while_paying(
    client: Client, paying: list[str], release: threading.Event
) -> tuple[Case, PlanRun]:
    """Open the refund settled by `refund-order@4`; Lee approves inside the child; Ana closes the
    case as a duplicate while the payment runs; then the payment is released."""
    definition = refund_with_plan("refund-order@4") | {"close_reasons": {"duplicate": DUPLICATE}}
    case = await start_case(client, CasesWithLetters, definition, LARGE, "refund-1", QUEUE)
    await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
    plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
    await plans.answer(plan, "approve_refund#1", "approve", "lee", PEOPLE["lee"])
    for _ in range(100):  # until the payment runs inside the child
        if paying:
            break
        await asyncio.sleep(0.05)
    await close(case, "duplicate", "ana", PEOPLE["ana"])
    await reported(case, lambda now: now.status != "open")
    release.set()
    return case, plan


def test_a_payment_finishing_in_a_stopped_plan_flags_the_case() -> None:
    # The tutor's probe: a duplicate refund paid after the close must never disappear into
    # "cancelled". The case closes as a duplicate, flagged with the payment, as 8b flags a
    # payment step (brief, D10, D28); the letter after it never starts.
    release = threading.Event()
    paying: list[str] = []
    drafted: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paying.append(inputs["idempotency_key"])
        release.wait(timeout=10)
        return {"refund_id": "refund-ord-1"}

    def draft(inputs: dict[str, Any]) -> dict[str, Any]:
        drafted.append(inputs["idempotency_key"])
        return {"draft_id": "draft-1"}

    async def scenario(client: Client) -> CaseReport:
        case, _ = await close_while_paying(client, paying, release)
        return await case.result()

    activities = {**FAKES, "payments.refund@2": refund, "letters.draft@2": draft}
    ended = on_temporal(scenario, activities, cases=CasesWithLetters)
    assert len(paying) == 1 and drafted == []
    assert ended.flags == ["settle#1: payments.refund@2 completed after the close was requested"]
    assert "flagged: settle#1: payments.refund@2 completed after the close was requested" in (
        ended.history
    )
    assert ended.history[-1] == "closed: duplicate, by ana"


def test_an_activity_failing_in_a_stopped_plan_flags_the_case() -> None:
    # The payment running at the close fails past its retries: the case closes, flagged with the
    # failure, never just "cancelled" (brief, D10, D28).
    release = threading.Event()
    paying: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paying.append(inputs["idempotency_key"])
        release.wait(timeout=10)
        raise ConnectionError("provider unreachable")

    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        case, _ = await close_while_paying(environment.client, paying, release)
        for _ in range(100):  # past the backoff between attempts, until the case closes
            now = await report(case)
            if now.status == "closed":
                return now
            await environment.sleep(timedelta(seconds=10))
        raise AssertionError(f"the case never closed: {await report(case)}")

    ended = skipping(scenario, {**FAKES, "payments.refund@2": refund}, cases=CasesWithLetters)
    assert ended.flags == [
        "settle#1: payments.refund@2 failed with ConnectionError after the close was requested: ‹sensitive›"
    ]
    assert ended.needs_attention == []
    assert ended.history[-1] == "closed: duplicate, by ana"


# --- Layer 11c: a rule stops a child plan (brief, D28, D40) ---

WITHDRAWAL = {
    "kind": "task",
    "display": {"title": "Log the customer's withdrawal"},
    "roles": ["support"],
    "automatic": False,
    "proposed_by": ["support"],
    "outcomes": {"logged": {"display": {"title": "Withdrawn"}, "reaches": ["withdrawn"]}},
}
WITHDRAW = {
    "display": {"title": "Stop the refund when the customer withdraws"},
    "on": {"reached": "withdrawn"},
    "then": {"stop": ["settle"]},
}


def withdrawn_plan(plan: str = "refund-order@1") -> dict[str, Any]:
    """The refund settled by `plan`, with a support task logging a withdrawal and a rule that
    stops the settlement once it is logged."""
    definition = refund_with_plan(plan)
    definition["milestones"] = {"withdrawn": {"display": {"title": "Withdrawn"}}}
    definition["steps"]["log_withdrawal"] = copy.deepcopy(WITHDRAWAL)
    definition["rules"] = {"withdraw": copy.deepcopy(WITHDRAW)}
    return definition


async def withdraw(case: Case) -> None:
    """Ana logs the customer's withdrawal."""
    await propose(case, "log_withdrawal", "ana", PEOPLE["ana"])
    await reported(case, lambda now: "log_withdrawal#1" in now.waiting_at)
    await answer(case, "log_withdrawal#1", "logged", "ana", PEOPLE["ana"])


def test_a_rule_stops_a_child_plan() -> None:
    # The child waits for a team lead when the customer withdraws: the rule's stop signals it,
    # with the rule's entry as the reason; the plan ends cancelled saying so, Lee's approval after
    # it pays nothing, and the case closes. The signal's default, the close's text, is what a
    # history from before 11c replays with (test_a_history_from_before_11c_replays).
    paid: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paid.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    async def scenario(client: Client) -> tuple[CaseReport, RunReport]:
        case = await start_case(client, CasesWithPlans, withdrawn_plan(), LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        await withdraw(case)
        ended = await case.result()
        try:
            await plans.answer(plan, "approve_refund#1", "approve", "lee", PEOPLE["lee"])
        except RPCError:
            pass  # the child has ended: the answer can no longer be given
        return ended, await plan.result()

    ended, child = on_temporal(
        scenario, {**FAKES, "payments.refund@2": refund}, cases=CasesWithPlans
    )
    assert paid == []
    assert ended.history[-4:] == [
        "withdraw#1 on reached withdrawn: stopping settle",
        "settle#1: stop requested by withdraw#1",
        "settle#1 cancelled: stopped by withdraw#1",
        "closed: nothing left to do",
    ]
    assert (child.status, child.reason) == ("cancelled", "stopped by withdraw#1")


async def withdraw_while_paying(
    client: Client, paying: list[str], release: threading.Event
) -> Case:
    """Open the refund settled by `refund-order@4`; Lee approves inside the child; Ana logs the
    customer's withdrawal while the payment runs; then the payment is released."""
    case = await start_case(
        client, CasesWithLetters, withdrawn_plan("refund-order@4"), LARGE, "refund-1", QUEUE
    )
    await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
    plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
    await plans.answer(plan, "approve_refund#1", "approve", "lee", PEOPLE["lee"])
    for _ in range(100):  # until the payment runs inside the child
        if paying:
            break
        await asyncio.sleep(0.05)
    await withdraw(case)
    await reported(case, lambda now: "settle#1: stop requested by withdraw#1" in now.history)
    release.set()
    return case


def test_a_payment_in_a_plan_a_rule_stopped_completes_flagged_or_fails_for_a_person() -> None:
    # The payment runs inside the child when the rule stops it: it finishes, since it may have
    # moved money. Completed, the case is flagged and nothing after it starts in the plan; failed
    # past its retries, the case goes on, so the step needs attention, never cancelled
    # (brief, D10, D17, D40).
    release = threading.Event()
    paying: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paying.append(inputs["idempotency_key"])
        release.wait(timeout=10)
        return {"refund_id": "refund-ord-1"}

    async def completing(client: Client) -> CaseReport:
        return await (await withdraw_while_paying(client, paying, release)).result()

    ended = on_temporal(completing, {**FAKES, "payments.refund@2": refund}, cases=CasesWithLetters)
    assert ended.flags == ["settle#1: payments.refund@2 completed after the stop was requested"]
    assert "settle#1 cancelled: stopped by withdraw#1" in ended.history
    assert ended.history[-1] == "closed: nothing left to do"

    release.clear()
    paying.clear()

    def unreachable(inputs: dict[str, Any]) -> dict[str, Any]:
        paying.append(inputs["idempotency_key"])
        release.wait(timeout=10)
        raise ConnectionError("provider unreachable")

    async def failing(environment: WorkflowEnvironment) -> CaseReport:
        case = await withdraw_while_paying(environment.client, paying, release)
        for _ in range(100):  # past the backoff between attempts, until the step fails
            now = await report(case)
            if now.needs_attention:
                return now
            await environment.sleep(timedelta(seconds=10))
        raise AssertionError(f"the step never failed: {await report(case)}")

    failed = skipping(failing, {**FAKES, "payments.refund@2": unreachable}, cases=CasesWithLetters)
    assert failed.status == "open" and failed.flags == []
    [line] = [line for line in failed.history if line.startswith("settle#1 failed")]
    assert line.startswith("settle#1 failed after its stop was requested by withdraw#1: ")
    assert [entry.split(":")[0] for entry in failed.needs_attention] == ["settle#1"]


def test_a_stop_request_crosses_continue_as_new() -> None:
    # A run whose stop a rule asked for runs on, and is never asked twice: that mark is state
    # like the rest, so it crosses to the next run as data (brief, D27, D40). A state from before
    # 11c reads every run as asked nothing.
    definition = copy.deepcopy(REFUND)
    definition["milestones"] = {"withdrawn": {"display": {"title": "Withdrawn"}}}
    definition["steps"]["log_withdrawal"] = copy.deepcopy(WITHDRAWAL)
    definition["rules"] = {"withdraw": copy.deepcopy(WITHDRAW) | {"then": {"stop": ["pay"]}}}
    case = parse_case(definition)
    roles = frozenset({"support"})
    state = case_state(definition, SMALL, [("review#1", SMALL_FORM)])
    for event in (
        Proposed("log_withdrawal", "ana", roles, at=START),
        Answered("log_withdrawal#1", "logged", "ana", roles, at=START),
    ):
        state, _ = decide(case, CATALOG, state, event)
    [paying] = [run for run in state.runs if run.entry == "pay#1"]
    assert (paying.status, paying.stop_requested) == ("running", "withdraw#1")
    data = state_as_data(state)
    back = state_from_data(data)
    assert back == state
    # Every field of a run crosses: one added later and forgotten would vanish at every switch.
    assert set(data["runs"][0]) == {field.name for field in dataclasses.fields(StepRun)}
    for run in data["runs"]:
        del run["stop_requested"]
    assert all(run.stop_requested == "" for run in state_from_data(data).runs)


def test_a_retry_after_a_stop_runs_on_temporal() -> None:
    # From the review: the payment in the plan a rule stopped fails, and an operator retries the
    # step. The retry is a person's decision, so the driver forgets the stop: the retried child
    # runs, and waits for a team lead again. Until the fix, it was stopped as it started, recorded
    # as the case closing, and the case closed with nothing paid (brief, D26, D40).
    release = threading.Event()
    paying: list[str] = []
    down = [True]

    def flaky(inputs: dict[str, Any]) -> dict[str, Any]:
        paying.append(inputs["idempotency_key"])
        release.wait(timeout=10)
        if down[0]:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-ord-1"}

    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        client = environment.client
        case = await withdraw_while_paying(client, paying, release)
        for _ in range(100):  # past the backoff between attempts, until the step fails
            if (await report(case)).needs_attention:
                break
            await environment.sleep(timedelta(seconds=10))
        down[0] = False
        await retry(case, "settle#1", "omar", ["operations"])
        await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        return await report(case)

    now = skipping(scenario, {**FAKES, "payments.refund@2": flaky}, cases=CasesWithLetters)
    assert now.status == "open" and now.needs_attention == []
    assert "settle#1 cancelled: the case is closing" not in now.history


def with_a_rule_on_its_start(definition: dict[str, Any], step: str) -> dict[str, Any]:
    """`definition` with a rule that stops `step` as each of its runs starts."""
    definition["rules"] = {
        "hold_back": {
            "display": {"title": "Hold the step back"},
            "on": {"started": step},
            "then": {"stop": [step]},
        }
    }
    return definition


def test_a_plan_stopped_as_it_starts_is_stopped_on_temporal() -> None:
    # From the review: a rule on the plan step's own start stops it in the decision that starts
    # it, before the child exists. The driver keeps the stop, and signals the child once it has
    # started; untested, its loss would leave the case waiting for ever (brief, D40).
    async def scenario(client: Client) -> CaseReport:
        definition = with_a_rule_on_its_start(refund_with_plan(), "settle")
        case = await start_case(client, CasesWithPlans, definition, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        return await case.result()

    ended = on_temporal(scenario, cases=CasesWithPlans)
    assert "settle#1 cancelled: stopped by hold_back#1" in ended.history
    assert ended.history[-1] == "closed: nothing left to do"


class EndedChild:
    """A child plan's handle whose signal fails as Temporal fails one to a workflow that has
    ended, or with another failure."""

    def __init__(self, failure: str) -> None:
        self.failure = failure

    async def signal(self, name: str, reason: str) -> None:
        raise ApplicationError("the workflow has ended", type=self.failure)


def test_a_stop_to_a_child_that_has_just_ended_is_dropped() -> None:
    # From the review: a rule stops the plan step as its child ends, and the stop signal finds
    # the child gone. Its result is already on its way, so nothing is left to stop. Until the fix
    # the failed signal failed the whole case workflow; a race a close could hit before 11c, which
    # every rule's stop of a plan now can (brief, D17, D40). Any other failure still raises: an
    # engine bug is never lost.
    ended = EndedChild("ExternalWorkflowExecutionNotFound")
    asyncio.run(signal_stop(ended, "stopped by withdraw#1"))  # type: ignore[arg-type]
    with pytest.raises(ApplicationError):
        asyncio.run(signal_stop(EndedChild("Unexpected"), "stopped by withdraw#1"))  # type: ignore[arg-type]
