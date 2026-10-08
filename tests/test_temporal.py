"""The Temporal adapter: plans run as workflows, against Temporal's test server (layer 6).

See docs/layers/06-temporal.md and docs/guides/plans.md, "Running a plan on Temporal".
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from typing import Any

import pytest
from temporalio.client import Client, WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from test_interpreter import drafting, recording

from ventoux.core.provenance import sourced
from ventoux.temporal.client import start_plan
from ventoux.temporal.converter import DATA_CONVERTER
from ventoux.temporal.worker import plan_worker
from ventoux.temporal.workflow import RunReport
from ventoux.testing import FAKES, Activity, DevelopmentPlans

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
