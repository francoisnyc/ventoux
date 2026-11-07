"""Layer 18d: child cases on Temporal. A child is its own workflow under its parent's ID and key,
started with `ABANDON`; its end is a doorbell, and the parent reads the report itself (brief,
D75).

See docs/layers/18-lifecycle.md (18d) and docs/guides/cases.md, "Child cases".
"""

import asyncio
import copy
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from dev_server import cli_binary, cli_folder, dev_server
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.workflow import ParentClosePolicy
from test_child_cases import claim, repair
from test_temporal_case import QUEUE, SwitchingCases, on_temporal, reported, runs_of, skipping
from worker_threads import worker_threads

from ventoux.case.definition import parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseEnded, CaseState, Opened
from ventoux.core.provenance import Sourced
from ventoux.temporal.cases import CaseReport, answer, case_handle, start_case
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    CATALOG,
    FAKES,
    START,
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
    # The new run asked how its open child stood as it started: still open, so nothing recorded.
    assert not [line for line in done.history if line.startswith("child_ended")]
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


def test_a_child_terminated_after_a_switch_is_noticed_when_the_next_run_starts() -> None:
    # A run after a switch holds no handle on the child: it can't watch it. So every run that
    # starts with an open child asks how it stands, and one ended without reporting fails its
    # step there, never waited for in silence (brief, D17) (brief, D75). The test server never
    # tells the run either way, so only that question can notice.
    async def scenario(client: Client) -> tuple[CaseReport, list[str]]:
        parent = await start_case(client, SwitchingCases, RELEASE, FILE, "claim-11", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        first, _ = await runs_of(client, "claim-11")
        _, second = await until_switched(client, "claim-11", first)
        child = case_handle(client, SwitchingCases, "claim-11/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await child.terminate("from outside")
        for entry in ("repair#8", "repair#9"):  # two events: the case switches again
            await case_handle(client, SwitchingCases, "claim-11").signal("child_ended", entry)
        _, third = await until_switched(client, "claim-11", second)
        noticed = await reported(parent, lambda now: bool(now.needs_attention))
        return noticed, [first, second, third]

    report, runs = on_temporal(scenario, cases=SwitchingCases)
    assert len(set(runs)) == 3
    assert report.needs_attention == [ENDED_WITHOUT]
    assert report.waiting_for == []


def test_a_childs_end_read_twice_lands_once() -> None:
    # Its doorbell and a new run's question can both read the same end: the second finds no
    # open child, is recorded, and changes nothing; the report never lands twice (brief, D75).
    case = parse_case(claim())
    opened = Opened(FILE, None, at=START, cases={"repair@3": repair()})
    state, _ = decide(case, CATALOG, CaseState("claim-12/run"), opened)
    accepted = Answered(
        "assess#1", "accept", "ana", frozenset({"support"}), {"payout": Decimal(900)}, at=START
    )
    state, _ = decide(case, CATALOG, state, accepted)
    cost = Sourced(Decimal(640), frozenset({"person:lee"}))
    ended = CaseEnded(
        "repair#1", "done", None, "nothing left to do", ("fixed",), {"cost": cost}, at=START
    )
    state, _ = decide(case, CATALOG, state, ended)
    once = copy.deepcopy(state)
    state, commands = decide(case, CATALOG, state, replace(ended, at=START + 1))
    assert state.history == [*once.history, "repair#1 ended again: nothing read"]
    assert (state.values, state.sources, state.runs) == (once.values, once.sources, once.runs)
    assert commands == []


def test_a_child_terminated_unheard_is_noticed_within_a_day() -> None:
    # A run that never hears its child end (the test server never tells it; a server may lose
    # it) asks each open child how it stands once a day, on a durable timer: a child lost goes
    # unnoticed a day at most, never for ever (brief, D17) (brief, D75).
    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, CaseReport]:
        client = environment.client
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-13", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        child = case_handle(client, DevelopmentCases, "claim-13/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await child.terminate("from outside")
        await environment.sleep(timedelta(hours=23))
        unheard = await reported(parent, lambda now: True)
        await environment.sleep(timedelta(hours=2))
        return unheard, await reported(parent, lambda now: bool(now.needs_attention))

    unheard, noticed = skipping(scenario, cases=DevelopmentCases)
    assert unheard.needs_attention == []  # not yet a day
    assert noticed.needs_attention == [ENDED_WITHOUT]
    assert noticed.waiting_for == []


def test_after_a_switch_a_child_terminated_unheard_is_noticed_within_a_day() -> None:
    # A run after a switch sets its own daily check: the starting run's timer ended with it
    # (brief, D75).
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        client = environment.client
        parent = await start_case(client, SwitchingCases, RELEASE, FILE, "claim-14", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        first, _ = await runs_of(client, "claim-14")
        await until_switched(client, "claim-14", first)
        child = case_handle(client, SwitchingCases, "claim-14/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await child.terminate("from outside")
        await environment.sleep(timedelta(hours=25))
        return await reported(parent, lambda now: bool(now.needs_attention))

    noticed = skipping(scenario, cases=SwitchingCases)
    assert noticed.needs_attention == [ENDED_WITHOUT]
