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
from pathlib import Path
from typing import Any

import pytest
from dev_server import cli_binary, cli_folder, dev_server
from replaying import replay_history
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowHistory
from temporalio.service import RPCError, RPCStatusCode
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.workflow import ParentClosePolicy
from test_activation import NEEDS, SERVED, SERVES, production, worker
from test_child_cases import CLOSABLE, claim, repair, written_off_repair
from test_temporal_case import QUEUE, Case, SwitchingCases, on_temporal, reported, runs_of, skipping
from test_temporal_forget import on_temporal as forgetting_on_temporal
from test_temporal_forget import reported as forget_reported
from test_temporal_registry import QUEUE as REFUNDS
from test_temporal_registry import ProductionCases, in_production, production_worker
from test_temporal_sensitive import as_stored, every_run
from worker_threads import worker_threads

from ventoux.case.definition import parse_case
from ventoux.case.forgetting import ForgetRefused
from ventoux.case.registry import (
    Activating,
    Answer,
    Opening,
    Registry,
    Released,
    Retiring,
    activate,
    closed,
    open_on,
    opened,
    retire,
)
from ventoux.case.releases import Hash, Record, digest, package
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseEnded, CaseState, ForgetApproved, Opened
from ventoux.case.visibility import CaseView
from ventoux.core.provenance import Sourced
from ventoux.core.sensitive import Sensitive
from ventoux.temporal.cases import (
    CaseReport,
    CaseWorkflow,
    answer,
    case_handle,
    close,
    propose_migration,
    retry,
    send_event,
    start_case,
    view,
)
from ventoux.temporal.children import SETTLE, ChildActivities, ChildAsked, ChildRead
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import ForgetReport, answer_forget, propose_forget
from ventoux.temporal.registry import (
    RegistryWorkflow,
    Retire,
    activation_of,
    ask,
    registry_id,
    released,
)
from ventoux.temporal.worker import case_worker
from ventoux.temporal.workflow import RunReport
from ventoux.testing import (
    CATALOG,
    FAKES,
    START,
    DevelopmentCases,
    DevelopmentForget,
    DevelopmentPlans,
    as_text,
    development_converter,
    fixture_converter,
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
        child = await started(client, DevelopmentCases, "claim-7/repair#1")
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
        child = await started(client, SwitchingCases, "claim-9/repair#1")
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
        child = await started(client, DevelopmentCases, "claim-10/repair#1")
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
        child = await started(client, SwitchingCases, "claim-11/repair#1")
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
        child = await started(client, DevelopmentCases, "claim-13/repair#1")
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
        child = await started(client, SwitchingCases, "claim-14/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await child.terminate("from outside")
        await environment.sleep(timedelta(hours=25))
        return await reported(parent, lambda now: bool(now.needs_attention))

    noticed = skipping(scenario, cases=SwitchingCases)
    assert noticed.needs_attention == [ENDED_WITHOUT]


CLOSING = release_of(claim() | {"close_reasons": CLOSABLE}, 1, cases={"repair@3": repair()})


def test_a_parent_closed_after_a_switch_closes_its_child_saying_why() -> None:
    # A close asked across a switch is asked again, once, by the new run: the child is closed
    # by its parent, saying why, and the parent closes once the child has ended (brief, D40)
    # (brief, D75).
    async def scenario(client: Client) -> tuple[CaseReport, CaseReport]:
        parent = await start_case(client, SwitchingCases, CLOSING, FILE, "claim-15", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        first, _ = await runs_of(client, "claim-15")
        await until_switched(client, "claim-15", first)
        child = await started(client, SwitchingCases, "claim-15/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await close(parent, "duplicate", "ana", ["support"])
        done = await reported(parent, lambda now: now.status == "closed")
        return done, await reported(child, lambda now: now.status == "closed")

    parent, child = on_temporal(scenario, cases=SwitchingCases)
    assert child.history[-2:] == [
        "cancelled fix#1: closed by its parent: duplicate, by ana",
        "closed: by its parent: duplicate, by ana",
    ]
    assert "repair#1 cancelled: the case is closing" in parent.history


async def started(client: Client, cases: type[CaseWorkflow], id: str) -> Case:
    """The child case `id`, once Temporal has recorded its start: its parent says it is open as
    it decides to open it, before the start is recorded. Asked a bounded number of times."""
    for _ in range(100):
        try:
            await client.get_workflow_handle(id).describe()
            return case_handle(client, cases, id)
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
        await asyncio.sleep(0.05)
    raise AssertionError(f"{id} never started")


def test_a_parent_that_closes_closes_its_child_saying_why() -> None:
    # In the run that started it: the child is closed by its parent, its tasks cancelled, and
    # the parent closes once the child has ended; the child's report changes nothing there
    # (brief, D40) (brief, D75).
    async def scenario(client: Client) -> tuple[CaseReport, CaseReport]:
        parent = await start_case(client, DevelopmentCases, CLOSING, FILE, "claim-16", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, DevelopmentCases, "claim-16/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await close(parent, "duplicate", "ana", ["support"])
        done = await reported(parent, lambda now: now.status == "closed")
        return done, await reported(child, lambda now: now.status == "closed")

    parent, child = on_temporal(scenario)
    assert child.history[-2:] == [
        "cancelled fix#1: closed by its parent: duplicate, by ana",
        "closed: by its parent: duplicate, by ana",
    ]
    assert "repair#1 cancelled: the case is closing" in parent.history
    assert not [line for line in parent.history if line.startswith("reached repair")]


def withdrawable() -> dict[str, Any]:
    """The claim, whose rule stops the repair when the customer withdraws."""
    definition = claim()
    definition["events"] = {
        "withdrawn": {
            "display": {"title": "The customer withdraws"},
            "sent_by": {"system": "portal"},
        }
    }
    definition["rules"] = {
        "withdraw": {
            "display": {"title": "Stop the repair when the customer withdraws"},
            "on": {"event": "withdrawn"},
            "then": {"stop": ["repair"]},
        }
    }
    return definition


def test_a_rule_that_stops_the_step_closes_its_child_and_the_parent_goes_on() -> None:
    # The child is closed by its parent, saying which rule stopped it; also across a switch: the
    # new run asks the child to close, once (brief, D40) (brief, D75).
    released = release_of(withdrawable(), 1, cases={"repair@3": repair()})

    async def scenario(client: Client) -> tuple[CaseReport, CaseReport]:
        parent = await start_case(client, SwitchingCases, released, FILE, "claim-17", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, SwitchingCases, "claim-17/repair#1")
        first, _ = await runs_of(client, "claim-17")
        await until_switched(client, "claim-17", first)
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await send_event(parent, "withdrawn", {}, "system:portal")
        child_closed = await reported(child, lambda now: now.status == "closed")
        stopped = await reported(parent, lambda now: now.status == "closed")
        return stopped, child_closed

    parent, child = on_temporal(scenario, cases=SwitchingCases)
    assert child.history[-1] == "closed: by its parent: stopped by withdraw#1"
    # As in memory: the repair stopped, the claim has nothing left to do, so it closes.
    assert parent.history[-2:] == [
        "repair#1 cancelled: stopped by withdraw#1",
        "closed: nothing left to do",
    ]


def test_a_doorbell_read_waits_for_the_child_ringing_it_to_end() -> None:
    # A child rings as its last act, then ends in its next workflow task: a parent quick to
    # read finds it still running. So a doorbell's read waits for it to end, a few seconds at
    # most, and reads the report; it never says `open` of a child about to end (brief, D75).
    async def scenario(client: Client) -> ChildRead:
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-20", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, DevelopmentCases, "claim-20/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        reads = ActivityEnvironment().run(
            ChildActivities(client).read, ChildAsked("claim-20/repair#1", SETTLE)
        )
        reading = asyncio.ensure_future(reads)
        await asyncio.sleep(0.3)  # the read has found the child running
        await answer(child, "fix#1", "fixed", "lee", ["support-lead"], {"cost": Decimal(640)})
        return await reading

    read = on_temporal(scenario)
    assert read.how == ""
    assert read.ending is not None
    assert read.ending.closed == "nothing left to do"


# --- Slice 6: forgetting (brief, D75) ---


def test_a_child_is_never_forgotten_alone() -> None:
    # A child is under its parent's key: forgetting it alone would destroy its parent's key. So
    # the request is refused before anyone answers, naming the case to forget instead.
    async def scenario(client: Client) -> tuple[ForgetReport, str, CaseReport]:
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-21", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, DevelopmentCases, "claim-21/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        request = await propose_forget(
            client, DevelopmentForget, "claim-21/repair#1", "pia", ["privacy"], QUEUE
        )
        ended = await request.result()
        return ended, keys_of(client).state("claim-21"), await reported(child, lambda now: True)

    ended, key, child = forgetting_on_temporal(scenario)
    assert ended.status == "refused"
    assert ended.history == [
        (
            "refused pia's proposal: repair#1 is a child of claim-21: forget claim-21, which "
            "forgets it too"
        )
    ]
    assert key == "kept"
    assert child.status == "open"


def test_forgetting_the_parent_forgets_its_children() -> None:
    # One key for the family: the parent, asked to close as forgotten, closes its child, ends
    # once the child has ended, and only then is the key destroyed, with no workflow of the
    # family still running (brief, D32) (brief, D75).
    async def scenario(client: Client) -> tuple[ForgetReport, CaseReport, list[str]]:
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-22", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, DevelopmentCases, "claim-22/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        request = await propose_forget(
            client, DevelopmentForget, "claim-22", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        ended = await request.result()
        statuses = [
            getattr((await client.get_workflow_handle(id).describe()).status, "name", "")
            for id in ("claim-22", "claim-22/repair#1")
        ]
        return ended, await child.result(), statuses

    ended, child, statuses = forgetting_on_temporal(scenario)
    assert ended.status == "forgotten"
    assert ended.history[-3:] == [
        "claim-22 asked to close as forgotten",
        "claim-22 ended: closed: forgotten",
        "the key of claim-22 was destroyed",
    ]
    assert child.history[-2:] == [
        "cancelled fix#1: closed by its parent: forgotten",
        "closed: by its parent: forgotten",
    ]
    assert statuses == ["COMPLETED", "COMPLETED"]


def test_the_familys_forgetting_is_the_strictest_of_its_cases() -> None:
    # Forgetting the parent forgets its children: so a child that keeps its records keeps the
    # family's, worked out from the cases the parent's release pins, said as the parent's own
    # refusal is (brief, D32) (brief, D75).
    never = release_of(claim(), 1, cases={"repair@3": repair() | {"forgetting": "never"}})
    closable = claim() | {"close_reasons": CLOSABLE}
    while_open = release_of(
        closable, 1, cases={"repair@3": repair() | {"forgetting": "while_open"}}
    )

    async def scenario(client: Client) -> list[ForgetReport]:
        await start_case(client, DevelopmentCases, never, FILE, "claim-23", QUEUE)
        closed = await start_case(client, DevelopmentCases, while_open, FILE, "claim-24", QUEUE)
        await close(closed, "duplicate", "ana", ["support"])
        await closed.result()
        ended = []
        for case in ("claim-23", "claim-24"):
            request = await propose_forget(
                client, DevelopmentForget, case, "pia", ["privacy"], QUEUE
            )
            # Polled, never awaited: a request that wasn't refused waits for an answer, and the
            # test server would skip time to its end.
            decided = lambda now: now.status == "refused" or len(now.history) > 0
            ended.append(await forget_reported(request, decided))
        return ended

    ended = forgetting_on_temporal(scenario)
    assert [each.history[-1] for each in ended] == [
        (
            "refused pia's proposal: claim-23 keeps its records (forgetting: never): it can't be "
            "forgotten"
        ),
        (
            "refused pia's proposal: claim-24 is closed, and its definition keeps closed cases "
            "(forgetting: while_open)"
        ),
    ]


def test_the_case_itself_refuses_forgetting_a_family_that_keeps_its_records() -> None:
    # The case checks a request again, depending on nothing the request did: a child pinned to
    # keep its records keeps the family's (brief, D32) (brief, D75).
    case = parse_case(claim())
    kept = {"repair@3": repair() | {"forgetting": "never"}}
    state, _ = decide(
        case, CATALOG, CaseState("claim-25/run"), Opened(FILE, None, at=START, cases=kept)
    )
    approved = ForgetApproved(
        "pia", frozenset({"privacy"}), "olu", frozenset({"privacy"}), at=START
    )
    with pytest.raises(ForgetRefused) as refused:
        decide(case, CATALOG, state, approved)
    assert str(refused.value) == (
        "claim-25 keeps its records (forgetting: never): it can't be forgotten"
    )


# --- Slice 7: the registry (brief, D75) ---

REPAIR_3 = Released("repair", 3, Hash(1, "33" * 32))
CLAIM_1 = Released("claim", 1, Hash(1, "c1" * 32))
REPAIRING = worker("repairs-a", SERVES, queue="repairs")  # a case worker on another queue


def pinning(released: Released, pins: tuple[Released, ...], queue: str = "refunds") -> Activating:
    """Pia's activation of `released`, which pins the child releases `pins`, on `queue`."""
    seen = {queue: [f"{queue}-a"]}
    return Activating(released, dict(NEEDS), queue, seen, "pia", pins=pins)


def with_repair(queue: str = "refunds") -> Registry:
    """Production with repair 3 activated on `queue`."""
    registry, answer = activate(production(SERVED, REPAIRING), pinning(REPAIR_3, (), queue))
    assert answer.done, answer.said
    return registry


def test_activating_a_parent_checks_each_child_it_pins() -> None:
    # A parent's case opens the child on its pinned release, on the parent's queue: activating
    # the parent checks that release here first, activated, not retired, with the digest the
    # parent's package gives it, on that queue; refused, saying so (brief, D54) (brief, D75).
    retired, _ = activate(with_repair(), pinning(Released("repair", 4, Hash(1, "44" * 32)), ()))
    retired, answer = retire(retired, Retiring(REPAIR_3, "pia"), {})
    assert answer.done, answer.said
    other = Released("repair", 3, Hash(1, "99" * 32))
    refused = [
        (production(SERVED, REPAIRING), REPAIR_3),
        (retired, REPAIR_3),
        (with_repair(), other),
        (with_repair("repairs"), REPAIR_3),
    ]
    said = [activate(registry, pinning(CLAIM_1, (child,)))[1].said for registry, child in refused]
    assert said == [
        [
            "claim 1 not activated in production:",
            "claim 1 pins repair 3, which production never activated",
        ],
        [
            "claim 1 not activated in production:",
            "claim 1 pins repair 3, which is retired in production",
        ],
        [
            "claim 1 not activated in production:",
            "claim 1 pins repair 3, whose digest in production is another",
        ],
        [
            "claim 1 not activated in production:",
            "claim 1 pins repair 3, which production activated on repairs, not refunds",
        ],
    ]
    after, done = activate(with_repair(), pinning(CLAIM_1, (REPAIR_3,)))
    assert done.said == ["pia activated claim 1 in production"]
    assert after.active["claim"] == 1


def test_a_release_a_release_in_use_pins_is_not_retired() -> None:
    # Fail closed early: a parent active here, or with a case open on it, still opens children on
    # the release it pins; retiring it would fail their steps (brief, D54) (brief, D75).
    registry, _ = activate(with_repair(), pinning(CLAIM_1, (REPAIR_3,)))
    registry, _ = activate(registry, pinning(Released("repair", 4, Hash(1, "44" * 32)), ()))
    _, active = retire(registry, Retiring(REPAIR_3, "pia"), {})
    registry, _ = opened(registry, Opening("claim-7", "refunds", CLAIM_1))
    registry, _ = activate(registry, pinning(Released("claim", 2, Hash(1, "c2" * 32)), ()))
    _, open_case = retire(registry, Retiring(REPAIR_3, "pia"), {})
    registry, _ = closed(registry, "claim-7")
    _, done = retire(registry, Retiring(REPAIR_3, "pia"), {})
    assert [active.said, open_case.said, done.said] == [
        ["repair 3 not retired: claim 1, active in production, pins it"],
        ["repair 3 not retired: claim 1, with 1 open case in production, pins it"],
        ["pia retired repair 3 in production"],
    ]


def test_a_child_opens_on_its_pinned_release_never_the_active_one() -> None:
    # Activating repair 4 breaks no claim pinning repair 3: a child asks for its pinned release,
    # as a migration's target is asked, activated here, not retired, with its digest, on its
    # queue (brief, D54) (brief, D75). A case of its own still opens only on the active one.
    registry, _ = activate(with_repair(), pinning(CLAIM_1, (REPAIR_3,)))
    registry, _ = activate(registry, pinning(Released("repair", 4, Hash(1, "44" * 32)), ()))
    child = Opening("claim-7/repair#1", "refunds", REPAIR_3, pinned=True)
    after, allowed = opened(registry, child)
    _, alone = opened(registry, Opening("repair-9", "refunds", REPAIR_3))
    other = Released("repair", 3, Hash(1, "99" * 32))
    _, digest = opened(registry, replace(child, released=other))
    _, queue = opened(registry, replace(child, task_queue="repairs"))
    assert [allowed.said, alone.said, digest.said, queue.said] == [
        ["claim-7/repair#1 is open on repair 3 in production"],
        ["repair-9 can't open on repair 3: repair 4 is active in production"],
        ["claim-7/repair#1 can't open on repair 3: production's repair 3 has another digest"],
        ["claim-7/repair#1 can't open on repair 3 on repairs: production activated it on refunds"],
    ]
    assert open_on(after, REPAIR_3) == ["claim-7/repair#1"]


async def activated_here(client: Client, record: Record) -> None:
    """Pia activates `record` in production on the parent's queue, pins included, the registry
    given the pollers a command would see (the test server can't list them)."""
    asked = activation_of(record, REFUNDS, {REFUNDS: ["refunds-a"]}, "pia")
    answer = await ask(client, "production", "activate", asked)
    assert answer.done, answer.said


def test_on_temporal_a_child_opens_on_its_pinned_release() -> None:
    # Production activates repair 3, claim 1 pinning it, then repair 4: claim-30's child opens
    # on repair 3 all the same, asking for it, never the active one (brief, D75).
    async def scenario(client: Client) -> CaseReport:
        async with production_worker(client):
            for record in (release_of(repair(), 3), RELEASE, release_of(repair(), 4)):
                await activated_here(client, record)
            case = await start_case(client, ProductionCases, RELEASE, FILE, "claim-30", REFUNDS)
            await answer(case, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
            child = await started(client, ProductionCases, "claim-30/repair#1")
            return await reported(child, lambda now: now.waiting_at == ["fix#1"])

    child = in_production(scenario)
    assert child.release == "repair 3"


def test_on_temporal_activating_a_parent_before_its_child_is_refused() -> None:
    # The request a command builds from the record carries the children it pins (brief, D75).
    async def scenario(client: Client) -> Answer:
        async with production_worker(client):
            asked = activation_of(RELEASE, REFUNDS, {REFUNDS: ["refunds-a"]}, "pia")
            return await ask(client, "production", "activate", asked)

    refused = in_production(scenario)
    assert refused.said == [
        "claim 1 not activated in production:",
        "claim 1 pins repair 3, which production never activated",
    ]


def test_on_temporal_a_child_refused_as_it_opens_fails_its_step() -> None:
    # Should a pinned release go anyway (here, retired before a parent was activated by a
    # request that didn't say its pins), the child's own ask refuses it: the parent's step
    # fails, needing attention, never waited for in silence (brief, D17) (brief, D75).
    async def scenario(client: Client) -> CaseReport:
        async with production_worker(client):
            for record in (release_of(repair(), 3), release_of(repair(), 4)):
                await activated_here(client, record)
            gone = Retiring(Released("repair", 3, release_of(repair(), 3).digest), "pia")
            assert (await ask(client, "production", "retire", Retire(gone))).done
            unpinned = Activating(released(RELEASE), {}, REFUNDS, {REFUNDS: ["refunds-a"]}, "pia")
            assert (await ask(client, "production", "activate", unpinned)).done
            case = await start_case(client, ProductionCases, RELEASE, FILE, "claim-31", REFUNDS)
            await answer(case, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
            return await reported(case, lambda now: bool(now.needs_attention))

    report = in_production(scenario)
    assert report.needs_attention == [
        (
            "repair#1: repair@3 refused its opening: claim-31/repair#1 can't open on repair 3: "
            "repair 3 is retired in production"
        )
    ]


def test_on_temporal_a_retry_starts_the_refused_child_again_under_its_id() -> None:
    # An operator retries the failed step: the same entry, so the same child workflow ID, which
    # Temporal lets start again only because the earlier attempt failed (brief, D26) (brief,
    # D75). Refused again here, since its release is still retired.
    async def scenario(client: Client) -> CaseReport:
        async with production_worker(client):
            for record in (release_of(repair(), 3), release_of(repair(), 4)):
                await activated_here(client, record)
            gone = Retiring(Released("repair", 3, release_of(repair(), 3).digest), "pia")
            assert (await ask(client, "production", "retire", Retire(gone))).done
            unpinned = Activating(released(RELEASE), {}, REFUNDS, {REFUNDS: ["refunds-a"]}, "pia")
            assert (await ask(client, "production", "activate", unpinned)).done
            case = await start_case(client, ProductionCases, RELEASE, FILE, "claim-32", REFUNDS)
            await answer(case, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
            await reported(case, lambda now: bool(now.needs_attention))
            await retry(case, "repair#1", "omar", ["operations"])

            def again(now: CaseReport) -> bool:
                opened = [line for line in now.history if line.startswith("started repair#1")]
                return len(opened) == 2 and bool(now.needs_attention)

            return await reported(case, again)

    report = in_production(scenario)
    assert report.needs_attention == [
        (
            "repair#1: repair@3 refused its opening: claim-32/repair#1 can't open on repair 3: "
            "repair 3 is retired in production"
        )
    ]


# --- Slice 8: sensitive values cross sealed (brief, D31) (brief, D75) ---

VIN = "WP0ZZZ99ZTS392124"


def sensitive(definition: dict[str, Any], seen_by: str) -> dict[str, Any]:
    """`definition` with its vehicle sensitive, seen only by `seen_by`."""
    vehicle = definition["fields"]["vehicle"] | {"sensitive": True, "visible_to": [seen_by]}
    return definition | {"fields": definition["fields"] | {"vehicle": vehicle}}


def test_a_sensitive_value_crosses_into_the_child_sealed() -> None:
    # The child is under its parent's key: a sensitive value it is given crosses sealed into its
    # start, and is in plain text nowhere, in any run of either history; inside the worker the
    # child reads it, and shows it only to whom may see it (brief, D31) (brief, D75).
    released = release_of(
        sensitive(claim(), "support"), 1, cases={"repair@3": sensitive(repair(), "support-lead")}
    )

    async def scenario(client: Client) -> tuple[list[WorkflowHistory], CaseView, CaseView]:
        file = FILE | {"vehicle": VIN}
        parent = await start_case(client, SwitchingCases, released, file, "claim-40", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, SwitchingCases, "claim-40/repair#1")
        # Its start, as soon as it exists: a value given in plain text would be there.
        [opening] = (await every_run(client, "claim-40/repair#1"))[:1]
        assert VIN.encode() not in as_stored(opening)[0], "the child's start holds it in plain text"
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        seen, unseen = await view(child, ["support-lead"]), await view(child, ["support"])
        await answer(child, "fix#1", "fixed", "lee", ["support-lead"], {"cost": Decimal(640)})
        await reported(parent, lambda now: now.waiting_at == ["pay_garage.approval#1"])
        roles = ["support", "support-lead"]
        await answer(parent, "pay_garage.approval#1", "approve", "sam", roles, None)
        await reported(parent, lambda now: now.status == "closed")
        runs = await every_run(client, "claim-40") + await every_run(client, "claim-40/repair#1")
        return runs, seen, unseen

    histories, seen, unseen = on_temporal(scenario, cases=SwitchingCases)
    # It reached the child, opened by the client, which holds the keys, still wrapped.
    assert seen.values["vehicle"] == Sensitive(VIN)
    assert "vehicle" not in unseen.values
    assert {history.workflow_id for history in histories} == {"claim-40", "claim-40/repair#1"}
    assert len(histories) > 2  # the parent, at least, continued as new
    for history in histories:
        raw, exported = as_stored(history)
        assert VIN.encode() not in raw, history.workflow_id
        assert VIN not in exported, history.workflow_id


def test_a_migration_renaming_the_case_step_keeps_its_open_child_on_temporal() -> None:
    # A run keeps its entry across a migration's rename, so its child's workflow ID, its
    # doorbell and its read: the report lands under the renamed step, across a switch
    # (brief, D53) (brief, D75).
    before = claim()
    after = claim()
    after["steps"]["fix_vehicle"] = after["steps"].pop("repair")
    after["steps"]["pay_garage"]["requires"] = ["fix_vehicle"]
    after["steps"]["pay_garage"]["inputs"]["amount"] = {"var": "fix_vehicle.cost"}
    one = release_of(before, 1, cases={"repair@3": repair()})
    two = release_of(after, 2, cases={"repair@3": repair()})

    async def scenario(client: Client) -> CaseReport:
        parent = await start_case(client, SwitchingCases, one, FILE, "claim-60", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, SwitchingCases, "claim-60/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        renamed = {"steps": {"repair": "fix_vehicle"}}
        await propose_migration(parent, two, renamed, "pia", ["platform"])
        await reported(parent, lambda now: "case.change#1" in now.waiting_at)
        await answer(parent, "case.change#1", "approve", "lee", ["support-lead", "platform"])
        await reported(parent, lambda now: now.release == "claim 2")
        await answer(child, "fix#1", "fixed", "lee", ["support-lead"], {"cost": Decimal(640)})
        await reported(parent, lambda now: now.waiting_at == ["pay_garage.approval#1"])
        roles = ["support", "support-lead"]
        await answer(parent, "pay_garage.approval#1", "approve", "sam", roles, None)
        return await reported(parent, lambda now: now.status == "closed")

    report = on_temporal(scenario, cases=SwitchingCases)
    assert "repair#1 done: repair closed, nothing left to do, reaching fixed; reporting cost" in (
        report.history
    )
    assert "amount from case:repair, person:lee" in "\n".join(
        report.history
    )  # read as fix_vehicle.cost


def test_a_childs_plan_step_runs_on_temporal() -> None:
    # A child's plan comes from its parent's release, which holds its children's plans too: one
    # reference is one plan (brief, D74). Its plan runs as the child's own child workflow, under
    # the family's key, and asks its people as any plan does (brief, D75).
    from test_case import refund_order  # here: that module imports the guide's tests

    child = repair()
    child["fields"]["order_id"] = {
        "type": "reference",
        "system": "orders",
        "display": {"title": "Order"},
    }
    child["steps"]["settle"] = {
        "kind": "plan",
        "display": {"title": "Settle the parts"},
        "plan": "refund-order@1",
        "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "budget"}},
    }
    parent = claim()
    parent["steps"]["repair"]["inputs"]["order_id"] = {"var": "order_id"}
    children = {"repair@3": package(as_text(child), [as_text(refund_order())])}
    packaged = package(as_text(parent), [], children)
    released = Record("claim", 1, 1, digest(packaged), "memory", {}, packaged.written)

    async def scenario(client: Client) -> RunReport:
        case = await start_case(client, DevelopmentCases, released, FILE, "claim-61", QUEUE)
        await answer(case, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await started(client, DevelopmentCases, "claim-61/repair#1")
        plan = client.get_workflow_handle("claim-61/repair#1/settle#1", result_type=RunReport)
        for _ in range(100):
            try:
                now: RunReport = await plan.query("report", result_type=RunReport)
                if now.waiting_at == "approve_refund#1":
                    return now
            except RPCError:
                pass  # not started yet
            await asyncio.sleep(0.05)
        raise AssertionError("the child's plan never waited")

    waiting = on_temporal(scenario)
    assert waiting.waiting_at == "approve_refund#1"


def test_on_temporal_who_closed_the_child_approves_nothing_its_outcome_decides() -> None:
    # Who closed the child crosses in its report, so its outcome is that person's act on
    # Temporal too: lee closes the repair as written off, which decides that pay_garage runs, so
    # lee approves nothing of it (brief, D11) (brief, D74) (brief, D75).
    definition = claim()
    definition["steps"]["pay_garage"]["when"] = {"==": [{"var": "repair.outcome"}, "written_off"]}
    definition["steps"]["pay_garage"]["inputs"]["amount"] = {"var": "payout"}
    released = release_of(definition, 1, cases={"repair@3": written_off_repair()})

    async def scenario(client: Client) -> CaseReport:
        parent = await start_case(client, DevelopmentCases, released, FILE, "claim-62", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, DevelopmentCases, "claim-62/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await close(child, "written_off", "lee", ["support-lead"])
        await reported(parent, lambda now: now.waiting_at == ["pay_garage.approval#1"])
        await answer(parent, "pay_garage.approval#1", "approve", "lee", ["support-lead"], None)
        await reported(parent, lambda now: any("refused lee" in line for line in now.history))
        roles = ["support", "support-lead"]
        await answer(parent, "pay_garage.approval#1", "approve", "sam", roles, None)
        return await reported(parent, lambda now: now.status == "closed")

    report = on_temporal(scenario)
    assert (
        "refused lee's answer approve to pay_garage.approval#1: lee set repair.outcome, which "
        "decides whether pay_garage runs, so cannot approve it"
    ) in report.history
    assert any(line.startswith("scheduled pay_garage#1") for line in report.history)


# --- Slice 9: replay (brief, D17) (brief, D75, choice 49) ---

HERE = Path(__file__).parent / "histories"

# Recorded under main at `dc2407e`, before 18d changes anything on Temporal: a case whose case
# step failed closed, continuing as new; a case in production, closed; and production's registry,
# activating, opening, closing and retiring. No new engine version: each replays as recorded.
BEFORE_18D: dict[str, tuple[str, type[Any]]] = {
    "before_18d_case_step_failed_switched": ("claim-2", SwitchingCases),
    "before_18d_production_case": ("claim-3", ProductionCases),
    "before_18d_registry": (registry_id("production"), RegistryWorkflow),
}


def test_histories_from_before_18d_replay() -> None:
    for name, (id, workflow_class) in BEFORE_18D.items():
        recorded = HERE / f"{name}.json"
        history = WorkflowHistory.from_json(id, recorded.read_text())
        asyncio.run(replay_history(history, [workflow_class], fixture_converter(recorded)))


def test_a_history_with_a_child_replays() -> None:
    # Everything 18d adds is recorded in the histories, never read from the world on replay: the
    # child's start, its watch, the doorbell and its read, the question asked as a run starts,
    # the daily timer, and the close, across switches on both sides (brief, D17) (brief, D75).
    converter = development_converter()  # holds the keys the replay needs

    async def scenario(environment: WorkflowEnvironment) -> list[WorkflowHistory]:
        client = environment.client
        parent = await start_case(client, SwitchingCases, CLOSING, FILE, "claim-50", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, SwitchingCases, "claim-50/repair#1")
        first, _ = await runs_of(client, "claim-50")
        await until_switched(client, "claim-50", first)
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await environment.sleep(timedelta(hours=25))  # a daily check: the child still open
        opened, _ = await runs_of(client, "claim-50/repair#1")
        for entry in ("fix#8", "fix#9"):  # two events, recorded and ignored: the child switches
            await child.signal("child_ended", entry)
        await until_switched(client, "claim-50/repair#1", opened)
        await close(parent, "duplicate", "ana", ["support"])
        await reported(parent, lambda now: now.status == "closed")
        await reported(child, lambda now: now.status == "closed")
        return await every_run(client, "claim-50") + await every_run(client, "claim-50/repair#1")

    histories = skipping(scenario, cases=SwitchingCases, converter=converter)
    ids = [history.workflow_id for history in histories]
    assert ids.count("claim-50") > 1 and ids.count("claim-50/repair#1") > 1  # both switched
    # What 18d records, each there to replay: the child's start, the daily timer, the read, and
    # the doorbell and the close, each a signal to another workflow.
    recorded = {
        (history.workflow_id, EventType.Name(event.event_type))
        for history in histories
        for event in history.events
    } | {
        ("activity", event.activity_task_scheduled_event_attributes.activity_type.name)
        for history in histories
        for event in history.events
        if event.HasField("activity_task_scheduled_event_attributes")
    }
    assert {
        ("claim-50", "EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED"),
        ("claim-50", "EVENT_TYPE_TIMER_STARTED"),
        ("claim-50", "EVENT_TYPE_SIGNAL_EXTERNAL_WORKFLOW_EXECUTION_INITIATED"),
        ("claim-50/repair#1", "EVENT_TYPE_SIGNAL_EXTERNAL_WORKFLOW_EXECUTION_INITIATED"),
        ("activity", "ventoux.child.read"),
    } <= recorded
    for history in histories:
        asyncio.run(replay_history(history, [SwitchingCases], converter))
