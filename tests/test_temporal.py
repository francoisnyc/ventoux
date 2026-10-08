"""The Temporal adapter: plans run as workflows, against Temporal's test server (layer 6).

See docs/layers/06-temporal.md and docs/guides/plans.md, "Running a plan on Temporal".
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from typing import Any

import pytest
from temporalio import workflow
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle, WorkflowHistory
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer
from temporalio.workflow import NondeterminismError
from test_interpreter import GUIDE_FIELDS, ORDER, drafting, guide_plan, looking_up, recording

from ventoux.core.catalog import NotInCatalog
from ventoux.core.interpreter import Outcome
from ventoux.core.provenance import sourced
from ventoux.temporal.client import answer, report, start_plan
from ventoux.temporal.converter import DATA_CONVERTER
from ventoux.temporal.worker import plan_worker
from ventoux.temporal.workflow import PlanStart, PlanWorkflow, RunReport
from ventoux.testing import CATALOG, FAKES, Activity, DevelopmentPlans, fake_refund, run_plan

QUEUE = "plans"


def on_temporal[T](
    scenario: Callable[[Client], Awaitable[T]], activities: Mapping[str, Activity] = FAKES
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a worker serving the
    development plans and `activities`: timers fire at once, and nothing outside is reached."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(data_converter=DATA_CONVERTER)
        async with (
            environment,
            plan_worker(environment.client, QUEUE, DevelopmentPlans, activities),
        ):
            return await scenario(environment.client)

    return asyncio.run(go())


async def settled(run: WorkflowHandle[PlanWorkflow, RunReport]) -> RunReport:
    """The run's report once it has settled (ended, or waiting): while it runs, its status is
    None. Asked a bounded number of times, so a run that never settles fails the test."""
    for _ in range(100):
        now = await report(run)
        if now.status is not None:
            return now
        await asyncio.sleep(0.05)  # real time, for the worker to take its next workflow task
    raise AssertionError("the run never settled")


def ending_at_once() -> dict[str, Any]:
    """The smallest plan: one field, and a start that is already the end."""
    return {
        "plan": "at-once",
        "version": 1,
        "display": {"title": "Ends at once"},
        "fields": {"amount": {"type": "number"}},
        "initial": "done",
        "states": {"done": {"final": "succeeded"}},
    }


def round_trip(value: Any) -> Any:
    """`value` written as Temporal writes a payload, and read back."""

    async def both_ways() -> Any:
        payloads = await DATA_CONVERTER.encode([value])
        return (await DATA_CONVERTER.decode(payloads, [Any]))[0]

    return asyncio.run(both_ways())


def test_a_float_is_refused() -> None:
    # A binary float may already have lost its exact value: 0.1 is 0.1000000000000000055…
    with pytest.raises(TypeError, match="0.1 is a binary float"):
        round_trip({"amount": 0.1})


def test_a_decimal_comes_back_exactly() -> None:
    back = round_trip({"amount": Decimal("0.1"), "count": 3})
    assert back == {"amount": Decimal("0.1"), "count": 3}
    assert isinstance(back["amount"], Decimal)  # never the text "0.1", never a float


def test_a_whole_decimal_stays_a_decimal_and_an_int_an_int() -> None:
    # Found in slice 5: `Decimal("250")` crossed as `250` and came back an int, which an expression
    # refuses. Each comes back as what it was, so a run decides on Temporal as it does in memory.
    back = round_trip({"amount": Decimal(250), "version": 1})
    assert back == {"amount": Decimal(250), "version": 1}
    assert isinstance(back["amount"], Decimal)
    assert str(back["amount"]) == "250"  # the same digits, not 250.0
    assert type(back["version"]) is int


def test_a_run_missing_a_field_is_refused_to_start() -> None:
    async def scenario(client: Client) -> None:
        run = await start_plan(
            client, DevelopmentPlans, ending_at_once(), fields={}, id="refund-1", task_queue=QUEUE
        )
        with pytest.raises(WorkflowFailureError) as failed:
            await run.result()
        assert "amount is missing" in str(failed.value.cause)

    on_temporal(scenario)


def test_a_malformed_plan_is_refused_to_start() -> None:
    malformed = ending_at_once()
    malformed["initial"] = 7  # not a state's name

    async def scenario(client: Client) -> None:
        run = await start_plan(
            client,
            DevelopmentPlans,
            malformed,
            fields={"amount": sourced(Decimal(250), "system:opener")},
            id="refund-1",
            task_queue=QUEUE,
        )
        with pytest.raises(WorkflowFailureError) as failed:
            await run.result()
        assert "initial" in str(failed.value.cause)

    on_temporal(scenario)


def test_a_client_without_exact_numbers_is_refused() -> None:
    # With another converter an amount could arrive as the text "250" (Pydantic's) and a contract
    # would read it back as a number: exact numbers are checked where a client is used, never
    # assumed (brief, D20).
    async def go() -> None:
        async with await WorkflowEnvironment.start_time_skipping() as environment:
            with pytest.raises(ValueError, match="exact numbers"):
                plan_worker(environment.client, QUEUE, DevelopmentPlans, FAKES)
            with pytest.raises(ValueError, match="exact numbers"):
                await start_plan(
                    environment.client,
                    DevelopmentPlans,
                    ending_at_once(),
                    fields={"amount": sourced(Decimal(250), "system:opener")},
                    id="refund-1",
                    task_queue=QUEUE,
                )

    asyncio.run(go())


def test_a_plan_runs_as_a_workflow() -> None:
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client,
            DevelopmentPlans,
            ending_at_once(),
            fields={"amount": sourced(Decimal(250), "system:opener")},
            id="refund-1",
            task_queue=QUEUE,
        )
        return await run.result()

    report = on_temporal(scenario)
    assert report.status == "succeeded"
    assert report.history == ["started at-once@1", "entered done", "ended succeeded"]


def test_the_runtime_check_blocks_the_injection_on_temporal() -> None:
    # Layer 5's injection, unchanged: the value's real source is the model, and the check before an
    # activity runs inside the workflow, before anything is scheduled.
    calls: list[dict[str, Any]] = []

    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client,
            DevelopmentPlans,
            drafting(),
            fields={
                "customer_email": sourced("ana@example.com", "system:crm"),
                "suggested_recipient": sourced("attacker@evil.example", "untrusted:llm"),
            },
            id="reply-1",
            task_queue=QUEUE,
        )
        return await run.result()

    report = on_temporal(scenario, activities={"letters.draft@2": recording(calls)})
    assert report.status == "stopped"
    assert report.reason is not None
    assert report.reason.startswith("letters.draft@2 takes to_customer only from")
    assert calls == []  # never called


def test_an_implementation_the_catalog_does_not_hold_is_refused() -> None:
    # A typo would register an activity no plan can call, and leave the real one unserved.
    async def go() -> None:
        environment = await WorkflowEnvironment.start_time_skipping(data_converter=DATA_CONVERTER)
        async with environment:
            with pytest.raises(NotInCatalog, match="payments.refnd@2"):
                plan_worker(
                    environment.client, QUEUE, DevelopmentPlans, {"payments.refnd@2": fake_refund}
                )

    asyncio.run(go())


TRUSTED_REPLY = {
    "customer_email": sourced("ana@example.com", "system:crm"),
    "suggested_recipient": sourced("ana@example.com", "person:sam"),
}


def drafts_on_the_second_attempt(keys: list[str]) -> Activity:
    """A fake `letters.draft@2` whose system is down on the first attempt."""

    def draft(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        if len(keys) == 1:
            raise ConnectionError("letters system unavailable")
        return {"draft_id": "draft-1"}

    return draft


def test_a_retried_activity_reuses_the_same_key() -> None:
    # A retry repeats the same step run, so the letters system sees the same key and can return
    # the draft it already made; the key is never the attempt number (brief, D17).
    keys: list[str] = []

    async def scenario(client: Client) -> tuple[RunReport, str]:
        run = await start_plan(
            client, DevelopmentPlans, drafting(), TRUSTED_REPLY, id="reply-1", task_queue=QUEUE
        )
        return await run.result(), run.result_run_id or ""

    report, run_id = on_temporal(
        scenario, activities={"letters.draft@2": drafts_on_the_second_attempt(keys)}
    )
    assert report.status == "succeeded"
    assert keys == [f"reply-1/{run_id}/draft#1"] * 2


def test_an_activity_failing_past_its_retries_stops_the_step() -> None:
    keys: list[str] = []

    def always_down(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        raise ConnectionError("letters system unavailable")

    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, drafting(), TRUSTED_REPLY, id="reply-1", task_queue=QUEUE
        )
        return await run.result()

    report = on_temporal(scenario, activities={"letters.draft@2": always_down})
    assert len(keys) == 5  # the contract's maximum_attempts, then a person looks (brief, D17)
    assert report.status == "stopped"
    assert report.reason == "letters.draft@2 failed: letters system unavailable"


def test_a_declared_outcome_is_never_retried_and_moves_the_plan_on() -> None:
    # "Not found" is an answer, not an outage: retrying it would ask the same question again
    # (brief, D17).
    calls: list[dict[str, Any]] = []

    def not_found(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs)
        raise Outcome("not_found")

    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, looking_up(), ORDER, id="look-1", task_queue=QUEUE
        )
        return await run.result()

    report = on_temporal(scenario, activities={"orders.lookup@1": not_found})
    assert len(calls) == 1  # its contract allows 3 attempts; an outcome uses one
    assert report.status == "failed"  # the plan's own way to fail: `not_found` goes to `missing`
    assert "orders.lookup@1 gave not_found" in report.history


def test_an_answer_the_wait_does_not_offer_is_refused_and_the_wait_goes_on() -> None:
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await answer(run, "approve_refund", "edit", by="ana")
        await answer(run, "approve_refund", "approve", by="sam")
        return await run.result()

    report = on_temporal(scenario)
    assert report.status == "succeeded"
    assert "refused ana's answer edit: approve_refund offers approve or reject" in report.history
    assert "sam answered approve" in report.history


def test_a_run_without_its_answer_reports_waiting() -> None:
    # On Temporal a wait just waits: nothing returns, so the run is asked how it is going.
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        return await settled(run)

    assert on_temporal(scenario).status == "waiting"


def test_a_timeout_sent_by_a_person_is_refused() -> None:
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await answer(run, "approve_refund", "timeout", by="mallory")
        await answer(run, "approve_refund", "approve", by="sam")
        return await run.result()

    report = on_temporal(scenario)
    assert report.status == "succeeded"
    assert (
        "refused mallory's answer timeout: a timeout comes from the wait's timer, never from a "
        "person" in report.history
    )


def test_a_wait_times_out_on_a_temporal_timer() -> None:
    # No answer comes: the test server skips the 48 hours at once, and history records the timer.
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        return await asyncio.wait_for(run.result(), timeout=20)  # real seconds

    report = on_temporal(scenario)
    assert report.status == "failed"
    assert report.history[-4:] == [
        "the wait timed out",
        "moved on timeout to failed",
        "entered failed",
        "ended failed",
    ]


def test_the_guides_run_gives_the_same_history_as_in_memory() -> None:
    # The same plan, fields and answers make the same decisions in memory and on Temporal: only
    # the idempotency keys differ, by the run's name.
    in_memory = run_plan(guide_plan(), GUIDE_FIELDS, answers=[("approve_refund", "approve", "sam")])

    async def scenario(client: Client) -> tuple[RunReport, str]:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await answer(run, "approve_refund", "approve", by="sam")
        return await run.result(), run.result_run_id or ""

    report, run_id = on_temporal(scenario)
    assert report.status == in_memory.status == "succeeded"
    assert report.history == [
        str(event).replace("memory/", f"refund-1/{run_id}/") for event in in_memory.history
    ]


# Temporal: replay runs a workflow's code again against a recorded history, as a new worker does
# after a crash. This version was changed to ask for a timer before the plan starts.
@workflow.defn(name="ventoux.plan")
class ChangedPlans(PlanWorkflow):
    catalog = CATALOG

    @workflow.run
    async def run(self, start: PlanStart) -> RunReport:
        await workflow.sleep(1)  # a command the recorded history never saw
        return await self.interpret(start)


def finished_history() -> WorkflowHistory:
    """The history of the guide's run, answered and finished."""

    async def scenario(client: Client) -> WorkflowHistory:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await answer(run, "approve_refund", "approve", by="sam")
        await run.result()
        return await run.fetch_history()

    return on_temporal(scenario)


def replay(history: WorkflowHistory, workflow_class: type[PlanWorkflow]) -> None:
    """Replay `history` against `workflow_class`, as a worker would after a restart."""
    replayer = Replayer(workflows=[workflow_class], data_converter=DATA_CONVERTER)
    asyncio.run(replayer.replay_workflow(history))


def test_a_history_replayed_with_changed_code_fails() -> None:
    # Temporal refuses rather than let the run go another way than it went: the run waits until
    # the code is fixed (brief, D17).
    with pytest.raises(NondeterminismError):
        replay(finished_history(), ChangedPlans)


def test_a_history_replays_with_the_same_code() -> None:
    # The interpreter reads no clock, randomness or I/O, so it asks for the same things in the
    # same order: the recorded results, answer and timer are read back, nothing is called again.
    replay(finished_history(), DevelopmentPlans)


def test_the_bound_on_a_loop_holds_on_temporal_and_replays() -> None:
    # Layer 5's loop on activities alone. The bound is a count inside the interpreter, never a
    # clock or the history's length, so replay counts the same states and stops at the same place.
    looping = looking_up(on={"done": "look", "not_found": "missing"})

    async def scenario(client: Client) -> tuple[RunReport, WorkflowHistory]:
        run = await start_plan(
            client, DevelopmentPlans, looping, ORDER, id="look-1", task_queue=QUEUE
        )
        return await run.result(), await run.fetch_history()

    report, history = on_temporal(scenario)
    assert report.status == "stopped"
    assert report.reason == (
        "entered 1,000 states without waiting for anyone: a plan that loops needs a wait or an end"
    )
    # Under Temporal's warning (about 10,000 events), far under its limit (51,200): no
    # continue-as-new is needed for a plan (design question 18).
    assert len(history.events) < 10_000
    replay(history, DevelopmentPlans)
