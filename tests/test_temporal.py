"""The Temporal adapter: plans run as workflows, against Temporal's test server (layer 6).

See docs/layers/06-temporal.md and docs/guides/plans.md, "Running a plan on Temporal".
"""

import asyncio
import threading
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from typing import Any

import pytest
from replaying import replay_history
from skipping_server import time_skipping
from temporalio import workflow
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle, WorkflowHistory
from temporalio.converter import DataConverter
from temporalio.workflow import NondeterminismError
from test_interpreter import (
    GUIDE_FIELDS,
    ORDER,
    PEOPLE,
    drafting,
    guide_plan,
    looking_up,
    recording,
)
from test_validate import guide_review_with
from worker_threads import worker_threads

from ventoux.core.catalog import NotInCatalog
from ventoux.core.interpreter import Outcome
from ventoux.core.provenance import sourced
from ventoux.temporal.client import answer, report, start_plan
from ventoux.temporal.worker import plan_worker
from ventoux.temporal.workflow import PlanStart, PlanWorkflow, RunReport
from ventoux.testing import (
    CATALOG,
    FAKES,
    Activity,
    DevelopmentPlans,
    development_converter,
    fake_draft,
    fake_refund,
    run_plan,
)

QUEUE = "plans"


def on_temporal[T](
    scenario: Callable[[Client], Awaitable[T]],
    activities: Mapping[str, Activity] = FAKES,
    converter: DataConverter | None = None,
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a worker serving the
    development plans and `activities`: timers fire at once, and nothing outside is reached.
    `converter` holds the keys, for a test that replays what it recorded; else fresh ones."""

    async def go() -> T:
        async with (
            time_skipping(converter or development_converter()) as environment,
            worker_threads() as threads,
            plan_worker(
                environment.client, QUEUE, DevelopmentPlans, activities, activity_executor=threads
            ),
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


async def reported(
    run: WorkflowHandle[PlanWorkflow, RunReport], holds: Callable[[RunReport], bool]
) -> RunReport:
    """The run's report once `holds` is true of it: the worker takes signals and runs on in its
    own time. Asked a bounded number of times, so a run that never gets there fails the test."""
    for _ in range(100):
        now = await report(run)
        if holds(now):
            return now
        await asyncio.sleep(0.05)  # real time, for the worker to take its next workflow task
    raise AssertionError(f"the run never got there: {await report(run)}")


def refusals(report: RunReport) -> int:
    """How many answers the run has refused so far."""
    return sum(line.startswith("refused ") for line in report.history)


async def waiting_at(run: WorkflowHandle[PlanWorkflow, RunReport], entry: str) -> RunReport:
    """The run's report once its wait `entry` (`approve_refund#1`) is open for an answer."""
    return await reported(run, lambda now: now.waiting_at == entry)


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
        converter = development_converter()
        payloads = await converter.encode([value])
        return (await converter.decode(payloads, [Any]))[0]

    return asyncio.run(both_ways())


def test_a_float_is_refused() -> None:
    # A binary float may already have lost its exact value: 0.1 is 0.1000000000000000055…
    with pytest.raises(TypeError, match="0.1 is a binary float"):
        round_trip({"amount": 0.1})


@pytest.mark.parametrize(
    ("value", "refusal"),
    [
        (Decimal("NaN"), "NaN is not a number JSON can hold"),
        ({1: "one"}, "a key must be a text"),  # JSON keys are texts: 1 would come back as "1"
        ({"sources": {"system:orders"}}, "set can't be written exactly as JSON"),
    ],
)
def test_what_json_cannot_hold_exactly_is_refused(value: Any, refusal: str) -> None:
    with pytest.raises(TypeError, match=refusal):
        round_trip(value)


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
        async with time_skipping() as environment, worker_threads() as threads:
            with pytest.raises(ValueError, match="exact numbers"):
                plan_worker(
                    environment.client, QUEUE, DevelopmentPlans, FAKES, activity_executor=threads
                )
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
        async with (
            time_skipping(development_converter()) as environment,
            worker_threads() as threads,
        ):
            with pytest.raises(NotInCatalog, match="payments.refnd@2"):
                plan_worker(
                    environment.client,
                    QUEUE,
                    DevelopmentPlans,
                    {"payments.refnd@2": fake_refund},
                    activity_executor=threads,
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


def test_the_thread_an_activity_ran_on_has_ended_once_its_worker_stops() -> None:
    # Whoever starts a worker owns its activity threads, and shuts them down once it stops:
    # none is left for the garbage collector to end at some later test (fix-worker-executors,
    # choices 1, 5 and 6). No collection is forced here.
    ran_on: list[threading.Thread] = []

    def drafting_here(inputs: dict[str, Any]) -> dict[str, Any]:
        ran_on.append(threading.current_thread())
        return fake_draft(inputs)

    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, drafting(), TRUSTED_REPLY, id="reply-1", task_queue=QUEUE
        )
        return await run.result()

    assert on_temporal(scenario, activities={"letters.draft@2": drafting_here}).status == (
        "succeeded"
    )
    assert ran_on and threading.main_thread() not in ran_on  # a plain function, on a pool thread
    assert [thread.name for thread in ran_on if thread.is_alive()] == []


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
    assert report.reason == "letters.draft@2 failed with ConnectionError: ‹sensitive›"


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
        await waiting_at(run, "approve_refund#1")
        await answer(run, "approve_refund#1", "edit", by="ana", roles=PEOPLE["ana"])
        await answer(run, "approve_refund#1", "approve", by="sam", roles=PEOPLE["sam"])
        return await run.result()

    report = on_temporal(scenario)
    assert report.status == "succeeded"
    assert "refused ana's answer edit: approve_refund offers approve or reject" in report.history
    assert "sam answered approve as support-lead" in report.history


def test_an_answer_is_taken_only_by_the_wait_it_names() -> None:
    # An answer sent to another entry is never read as an answer to this wait: it is refused, and
    # recorded.
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await waiting_at(run, "approve_refund#1")
        await answer(run, "check_order#1", "approve", by="sam", roles=PEOPLE["sam"])  # not a wait
        await answer(
            run, "approve_refund#2", "approve", by="sam", roles=PEOPLE["sam"]
        )  # not open yet
        return await reported(run, lambda now: refusals(now) == 2)

    report = on_temporal(scenario)
    assert report.status == "waiting"
    assert report.waiting_at == "approve_refund#1"
    assert "refused sam's answer approve: check_order#1 isn't open" in report.history
    assert "refused sam's answer approve: approve_refund#2 isn't open" in report.history


def test_a_run_without_its_answer_reports_waiting() -> None:
    # On Temporal a wait just waits: nothing returns, so the run is asked how it is going.
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        return await settled(run)

    report = on_temporal(scenario)
    assert report.status == "waiting"
    assert report.waiting_at == "approve_refund#1"  # the entry an answer must name


def test_a_timeout_sent_by_a_person_is_refused() -> None:
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await waiting_at(run, "approve_refund#1")
        await answer(run, "approve_refund#1", "timeout", by="mallory", roles=[])
        await answer(run, "approve_refund#1", "approve", by="sam", roles=PEOPLE["sam"])
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
    in_memory = run_plan(
        guide_plan(),
        GUIDE_FIELDS,
        answers=[("approve_refund", "approve", "sam")],
        people=PEOPLE,
    )

    async def scenario(client: Client) -> tuple[RunReport, str]:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await waiting_at(run, "approve_refund#1")
        await answer(run, "approve_refund#1", "approve", by="sam", roles=PEOPLE["sam"])
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


def finished_history(converter: DataConverter) -> WorkflowHistory:
    """The history of the guide's run, answered and finished, its parts sealed by `converter`."""

    async def scenario(client: Client) -> WorkflowHistory:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await waiting_at(run, "approve_refund#1")
        await answer(run, "approve_refund#1", "approve", by="sam", roles=PEOPLE["sam"])
        await run.result()
        return await run.fetch_history()

    return on_temporal(scenario, converter=converter)


def replay(
    history: WorkflowHistory, workflow_class: type[PlanWorkflow], converter: DataConverter
) -> None:
    """Replay `history` against `workflow_class`, as a worker would after a restart, with the
    converter that recorded it: its sealed parts open only with their keys (brief, D31)."""
    asyncio.run(replay_history(history, [workflow_class], converter))


def test_a_history_replayed_with_changed_code_fails() -> None:
    # Temporal refuses rather than let the run go another way than it went: the run waits until
    # the code is fixed (brief, D17).
    with pytest.raises(NondeterminismError):
        converter = development_converter()
        replay(finished_history(converter), ChangedPlans, converter)


def test_a_history_replays_with_the_same_code() -> None:
    # The interpreter reads no clock, randomness or I/O, so it asks for the same things in the
    # same order: the recorded results, answer and timer are read back, nothing is called again.
    converter = development_converter()
    replay(finished_history(converter), DevelopmentPlans, converter)


def test_the_threads_a_failed_replay_ran_on_have_ended_once_it_raises() -> None:
    # Whoever makes a replayer owns its workflow-task threads, and shuts them down once the
    # replay is done, failed or not: none is left for the garbage collector to end at some later
    # test (fix-replayer-threads). No collection is forced here. A failed replay is the sure
    # case: its error's traceback keeps the replayer, and any pool it made, alive.
    converter = development_converter()
    history = finished_history(converter)
    before = set(threading.enumerate())
    with pytest.raises(NondeterminismError):
        replay(history, ChangedPlans, converter)
    assert [thread.name for thread in threading.enumerate() if thread not in before] == []


def test_the_bound_on_a_loop_holds_on_temporal_and_replays() -> None:
    # Layer 5's loop on activities alone. The bound is a count inside the interpreter, never a
    # clock or the history's length, so replay counts the same states and stops at the same place.
    looping = looking_up(on={"done": "look", "not_found": "missing"})

    async def scenario(client: Client) -> tuple[RunReport, WorkflowHistory]:
        run = await start_plan(
            client, DevelopmentPlans, looping, ORDER, id="look-1", task_queue=QUEUE
        )
        return await run.result(), await run.fetch_history()

    converter = development_converter()
    report, history = on_temporal(scenario, converter=converter)
    assert report.status == "stopped"
    assert report.reason == (
        "entered 1,000 states without waiting for anyone: a plan that loops needs a wait or an end"
    )
    # Under Temporal's warning (about 10,000 events), far under its limit (51,200): no
    # continue-as-new is needed for a plan (design question 18).
    assert len(history.events) < 10_000
    replay(history, DevelopmentPlans, converter)


def declines_once(keys: list[str]) -> Activity:
    """A fake `payments.refund@2` that declines the first refund, and pays the next."""

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        if len(keys) == 1:
            raise Outcome("declined")
        return {"refund_id": "refund-1"}

    return refund


def retrying_after_a_decline() -> dict[str, Any]:
    """The guide's plan, where a declined refund goes back to the approval for a new decision."""
    plan = guide_plan()
    plan["states"]["pay"]["on"]["declined"] = "approve_refund"
    return plan


def test_a_double_click_does_not_approve_the_retry() -> None:
    # From the tutor review: Sam clicks "approve" twice. The second click was meant for the first
    # approval; left queued, it approved the retry, which was paid with nobody deciding again
    # (brief, D11: one approval unlocks one run of one step). Each answer names the entry it
    # answers, and one for an entry that isn't open is refused, and recorded.
    keys: list[str] = []

    async def scenario(client: Client) -> tuple[RunReport, RunReport]:
        run = await start_plan(
            client,
            DevelopmentPlans,
            retrying_after_a_decline(),
            GUIDE_FIELDS,
            id="refund-1",
            task_queue=QUEUE,
        )
        await waiting_at(run, "approve_refund#1")
        await answer(run, "approve_refund#1", "approve", by="sam", roles=PEOPLE["sam"])
        await answer(
            run, "approve_refund#1", "approve", by="sam", roles=PEOPLE["sam"]
        )  # the double click
        retry = await waiting_at(run, "approve_refund#2")  # the retry waits for a new decision
        await answer(run, "approve_refund#2", "approve", by="lee", roles=["support-lead"])
        return retry, await run.result()

    retry, ended = on_temporal(
        scenario, activities={**FAKES, "payments.refund@2": declines_once(keys)}
    )
    assert "refused sam's answer approve: approve_refund#1 is closed" in retry.history
    assert retry.history.count("sam answered approve as support-lead") == 1
    assert ended.status == "succeeded"
    assert len(keys) == 2  # the first refund, declined, and the retry lee approved


def test_an_answer_sent_before_the_wait_opens_is_refused() -> None:
    # From the tutor review: an answer queued while `check_order` ran approved the wait the moment
    # it opened, so a person could approve what they never saw.
    looked_up = threading.Event()  # set by the test once its answer is sent

    def slow_lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        looked_up.wait(timeout=10)
        return {"status": "delivered"}

    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await answer(
            run, "approve_refund#1", "approve", by="sam", roles=PEOPLE["sam"]
        )  # check_order still runs
        looked_up.set()
        return await waiting_at(run, "approve_refund#1")

    report = on_temporal(scenario, activities={**FAKES, "orders.lookup@1": slow_lookup})
    assert report.status == "waiting"  # still waiting for an answer given while it waits
    assert "refused sam's answer approve: approve_refund#1 isn't open" in report.history
    assert "sam answered approve" not in report.history


def test_an_answer_without_the_role_is_refused_on_temporal_as_in_memory() -> None:
    # The roles come with the signal, as the Ventoux API states them (brief, D22), and the same
    # check runs: Ana is in support, and approving a refund needs a team lead.
    async def scenario(client: Client) -> RunReport:
        run = await start_plan(
            client, DevelopmentPlans, guide_plan(), GUIDE_FIELDS, id="refund-1", task_queue=QUEUE
        )
        await waiting_at(run, "approve_refund#1")
        await answer(run, "approve_refund#1", "approve", by="ana", roles=PEOPLE["ana"])
        await answer(run, "approve_refund#1", "approve", by="sam", roles=[])  # no role stated
        return await reported(run, lambda now: refusals(now) == 2)

    report = on_temporal(scenario)
    assert report.status == "waiting"
    assert [line for line in report.history if line.startswith("refused")] == [
        (
            "refused ana's answer approve: approve_refund#1 is answered by support-lead, and ana "
            "has support"
        ),
        (
            "refused sam's answer approve: approve_refund#1 is answered by support-lead, and sam "
            "has no role"
        ),
    ]


def test_a_form_crosses_in_the_signal_and_the_history_replays() -> None:
    # The guide's review then approval: Ana's form sets the amount, exactly, and Sam approves it.
    plan = guide_review_with()
    order = {"order_id": sourced("A-1001", "system:orders")}
    answers: list[tuple[Any, ...]] = [
        ("review", "accept", "ana", {"approved_amount": Decimal("250.50")}),
        ("approve_refund", "approve", "sam"),
    ]
    in_memory = run_plan(plan, order, answers=answers, people=PEOPLE)

    async def scenario(client: Client) -> tuple[RunReport, str, WorkflowHistory]:
        run = await start_plan(
            client, DevelopmentPlans, plan, order, id="refund-1", task_queue=QUEUE
        )
        await waiting_at(run, "review#1")
        await answer(
            run,
            "review#1",
            "accept",
            by="ana",
            roles=PEOPLE["ana"],
            form={"approved_amount": Decimal("250.50")},
        )
        await waiting_at(run, "approve_refund#1")
        await answer(run, "approve_refund#1", "approve", by="sam", roles=PEOPLE["sam"])
        return await run.result(), run.result_run_id or "", await run.fetch_history()

    converter = development_converter()
    report, run_id, history = on_temporal(scenario, converter=converter)
    assert report.status == in_memory.status == "succeeded"
    assert report.history == [
        str(event).replace("memory/", f"refund-1/{run_id}/") for event in in_memory.history
    ]
    assert "ana answered accept as support, setting approved_amount" in report.history
    replay(history, DevelopmentPlans, converter)
