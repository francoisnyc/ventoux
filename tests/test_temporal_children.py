"""Layer 18d: child cases on Temporal. A child is its own workflow under its parent's ID and key,
started with `ABANDON`; its end is a doorbell, and the parent reads the report itself (brief,
D75).

See docs/layers/18-lifecycle.md (18d) and docs/guides/cases.md, "Child cases".
"""

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal

from dev_server import cli_binary, cli_folder, dev_server
from temporalio.client import Client
from temporalio.workflow import ParentClosePolicy
from test_child_cases import claim, repair
from test_temporal_case import QUEUE, SwitchingCases, on_temporal, reported, runs_of
from worker_threads import worker_threads

from ventoux.temporal.cases import CaseReport, answer, case_handle, start_case
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    FAKES,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
    release_of,
)

FILE = {"order_id": "ord-1", "vehicle": "veh-9"}


def test_a_doorbell_for_no_open_child_is_recorded_and_changes_nothing() -> None:
    # A signal says nothing of who sent it: anyone with the namespace may ring. One for an entry
    # that is no open child of the case finds nothing to read (brief, D75).
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, claim(), FILE, "claim-1", QUEUE)
        await answer(case, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await case_handle(client, DevelopmentCases, "claim-1").signal("child_ended", "repair#2")
        return await reported(case, lambda now: any("child_ended" in line for line in now.history))

    report = on_temporal(scenario)
    assert "child_ended for repair#2, which is no open child: nothing read" in report.history
    assert "repair.outcome" not in "\n".join(report.history)


RELEASE = release_of(claim(), 1, cases={"repair@3": repair()})


def test_the_guides_child_case_runs_on_temporal() -> None:
    # The child is its own workflow under its parent's ID; it rings as its last act, and the
    # parent reads its report itself, with its sources and the route it came by (brief, D75).
    async def scenario(client: Client) -> tuple[CaseReport, CaseReport]:
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-7", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        child = case_handle(client, DevelopmentCases, "claim-7/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await answer(child, "fix#1", "fixed", "lee", ["support-lead"], {"cost": Decimal(640)})
        await reported(parent, lambda now: now.waiting_at == ["pay_garage.approval#1"])
        roles = ["support", "support-lead"]
        await answer(parent, "pay_garage.approval#1", "approve", "sam", roles, None)
        done = await reported(parent, lambda now: now.status == "closed")
        return done, await reported(child, lambda now: now.status == "closed")

    parent, child = on_temporal(scenario)
    assert (
        "started repair#1: case repair@3 (vehicle from system:opener; budget from person:ana), "
        "run claim-7/repair#1"
    ) in parent.history
    assert "repair#1 done: repair closed, nothing left to do, reaching fixed; reporting cost" in (
        parent.history
    )
    # The report's sources crossed the doorbell's read intact, and gained the route.
    assert (
        "scheduled pay_garage#1: payments.refund@2 (order_id from system:opener; amount from "
        "case:repair, person:lee), key claim-7/"
    ) in "\n".join(parent.history)
    # A released case says its release first; then who opened it: its parent, never a person.
    assert child.history[:2] == [
        "opened on repair 3, engine 2",
        "opened by claim-7, from repair#1, with budget and vehicle",
    ]


def test_a_doorbell_for_a_child_still_open_reads_and_changes_nothing() -> None:
    # Rung by anyone while the child's case is open: the parent reads the child's own run, finds
    # it open, records so, and waits on (brief, D75).
    async def scenario(client: Client) -> CaseReport:
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-8", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        await case_handle(client, DevelopmentCases, "claim-8").signal("child_ended", "repair#1")
        return await reported(parent, lambda now: any("child_ended" in l for l in now.history))

    report = on_temporal(scenario)
    assert "child_ended for repair#1, whose case is still open: nothing read" in report.history
    assert report.waiting_for == ["repair#1: case repair, open"]


def test_the_child_outlives_its_parents_switch() -> None:
    # The parent starts its child with ABANDON, which its history records: no server ends the
    # child when the parent continues as new, and the switch waits for no child. The child's
    # doorbell goes to the parent's workflow ID, never a run, so the new run hears it (brief, D75).
    async def scenario(client: Client) -> tuple[CaseReport, list[str], list[ParentClosePolicy]]:
        parent = await start_case(client, SwitchingCases, RELEASE, FILE, "claim-9", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        first, _ = await runs_of(client, "claim-9")
        child = case_handle(client, SwitchingCases, "claim-9/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await reported(parent, lambda now: now.history[-1].startswith("started repair#1"))
        switched = await until_switched(client, "claim-9", first)
        await answer(child, "fix#1", "fixed", "lee", ["support-lead"], {"cost": Decimal(640)})
        done = await reported(parent, lambda now: now.waiting_at == ["pay_garage.approval#1"])
        history = await client.get_workflow_handle("claim-9", run_id=first).fetch_history()
        # Temporal: the event that starts a child records the policy it was started with.
        policies = [
            ParentClosePolicy(
                event.start_child_workflow_execution_initiated_event_attributes.parent_close_policy
            )
            for event in history.events
            if event.HasField("start_child_workflow_execution_initiated_event_attributes")
        ]
        return done, switched, policies

    done, runs, policies = on_temporal(scenario, cases=SwitchingCases)
    assert policies == [ParentClosePolicy.ABANDON]  # one child started, and abandoned
    assert runs[0] != runs[1]  # the parent switched while its child was open
    # ... and the child, answered after the switch, rang the new run, which read its report.
    assert "repair#1 done: repair closed, nothing left to do, reaching fixed; reporting cost" in (
        done.history
    )


async def until_switched(client: Client, id: str, first: str) -> list[str]:
    """The case's first run and its current one, once it has continued as new; asked a bounded
    number of times."""
    for _ in range(100):
        _, current = await runs_of(client, id)
        if current != first:
            return [first, current]
        await asyncio.sleep(0.05)
    raise AssertionError(f"{id} never continued as new")


ENDED_WITHOUT = (
    "repair#1: repair@3 ended without reporting: it was terminated: look at the child, then retry "
    "or close"
)


def on_dev_server[T](scenario: Callable[[Client], Awaitable[T]]) -> T:
    """Run `scenario` against a case worker on the development server. Only it tells a parent
    that its child was terminated: the time-skipping test server never does, under any parent
    close policy (18d, slice 4, run on both)."""

    async def go() -> T:
        binary = await cli_binary(cli_folder())
        async with (
            dev_server(binary, data_converter=development_converter()) as environment,
            worker_threads() as threads,
            case_worker(
                environment.client,
                QUEUE,
                DevelopmentCases,
                DevelopmentPlans,
                FAKES,
                activity_executor=threads,
            ),
        ):
            # Bounded: a case that hangs fails the test.
            return await asyncio.wait_for(scenario(environment.client), timeout=60)

    return asyncio.run(go())


def test_a_child_terminated_in_the_run_that_started_it_fails_the_step_at_once() -> None:
    # Anyone with the namespace may terminate a child, which then never rings: the run that
    # started it watches it, so its step fails at once and waits for a person, never waited for
    # in silence (brief, D17) (brief, D75).
    async def scenario(client: Client) -> CaseReport:
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-10", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        child = case_handle(client, DevelopmentCases, "claim-10/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await child.terminate("from outside")
        return await reported(parent, lambda now: bool(now.needs_attention))

    report = on_dev_server(scenario)
    assert report.needs_attention == [ENDED_WITHOUT]
    assert report.waiting_for == []
