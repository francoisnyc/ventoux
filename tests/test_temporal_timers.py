"""Layer 11f on Temporal: a timer is a workflow timer whose firing is decided stamped with its due
time; it crosses continue-as-new exactly; and histories recorded before 11f replay.

See docs/layers/11-rules.md (11f) and the brief, D44.
"""

import asyncio
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from activity_threads import activity_threads
from skipping_server import time_skipping
from temporalio.client import Client, WorkflowHistory
from temporalio.testing import WorkflowEnvironment

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_temporal_case import (
    QUEUE,
    SMALL,
    SwitchingCases,
    on_temporal,
    replay,
    reported,
    runs_of,
    skipping,
)
from test_timers import CLOSABLE, PEOPLE, chased
from test_timers import SMALL as SMALL_IN_MEMORY

from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    answer,
    case_handle,
    close,
    send_event,
    start_case,
)
from ventoux.temporal.converter import keys_of
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    DAY,
    FAKES,
    START,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
    fixture_converter,
    later,
)
from ventoux.testing import run_case as run_in_memory

HERE = Path(__file__).parent / "histories"

# --- Histories recorded under main, before 11f (slice 0) ---

# The refund taking the cancelled event: reviewed, an event arriving while the approval is open,
# approved and paid. One run, and one that continued as new (every 2 events): its last run starts
# from a state carried before timers existed.
REFUND_BEFORE = HERE / "before_11f_refund.json"
SWITCHED_BEFORE = HERE / "before_11f_switched.json"


def test_a_history_from_before_11f_replays() -> None:
    # A case with no timer asks Temporal for nothing new: no workflow timer, so the new worker
    # replays what the old one recorded (brief, D44).
    for recorded in (REFUND_BEFORE, SWITCHED_BEFORE):
        history = WorkflowHistory.from_json("refund-1", recorded.read_text())
        replay(history, DevelopmentCases, fixture_converter(recorded))


# --- Slice 7: a timer on Temporal ---

FIRED = "chase_review#1 on 2d after started review#1: starting chase"


def test_a_timer_fires_on_temporal_as_in_memory() -> None:
    # A workflow timer wakes the case at the due time; the firing is decided stamped then, and
    # the case says what the in-memory run says (brief, D44).
    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, CaseReport]:
        case = await start_case(
            environment.client, DevelopmentCases, chased(), SMALL, "refund-1", QUEUE
        )
        set_ = await reported(case, lambda now: bool(now.timers))
        await environment.sleep(timedelta(days=2, seconds=1))
        fired = await reported(case, lambda now: FIRED in now.history)
        return set_, fired

    set_, fired = skipping(scenario)
    assert set_.waiting_for == ["review by support"]
    assert len(set_.timers) == 1 and set_.timers[0].startswith(
        "chase_review: 2d after started review#1, due "
    )
    assert fired.timers == []
    assert fired.waiting_for == ["review by support", "chase by support-lead"]
    memory = run_in_memory(chased(), file=SMALL_IN_MEMORY, answers=[later("2d")], people=PEOPLE)
    # The same lines, but for the due date: the test server's clock starts today.
    assert [line.split(", due")[0] for line in fired.history] == [
        line.split(", due")[0] for line in memory.history
    ]


def noted() -> dict[str, Any]:
    """The guide's chased refund, taking a `noted` event no rule reads: something to send that
    makes the case continue as new while its timer is set."""
    definition = chased()
    definition["events"] = {
        "noted": {"display": {"title": "A note"}, "sent_by": {"system": "portal"}, "payload": {}}
    }
    return definition


def test_a_timer_crosses_continue_as_new_and_fires_once() -> None:
    # The opening and the note make two events: the case continues as new with its timer set,
    # which is state, not running work. The new run fires it once, at its time (brief, D27)
    # (brief, D44).
    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, tuple[str, str]]:
        client = environment.client
        case = await start_case(client, SwitchingCases, noted(), SMALL, "refund-1", QUEUE)
        await reported(case, lambda now: bool(now.timers))
        await send_event(case, "noted", {}, "system:portal")
        for _ in range(100):  # until the case has continued as new
            first, last = await runs_of(client, "refund-1")
            if last != first:
                break
            await environment.sleep(timedelta(seconds=0))
        crossed = await reported(case, lambda now: bool(now.timers))
        assert crossed.timers[0].startswith("chase_review: 2d after started review#1, due ")
        await environment.sleep(timedelta(days=2, seconds=1))
        fired = await reported(case, lambda now: FIRED in now.history)
        return fired, await runs_of(client, "refund-1")

    fired, (first, last) = skipping(scenario, cases=SwitchingCases)
    assert last != first
    assert fired.history.count(FIRED) == 1 and fired.timers == []


def test_a_timer_that_fell_due_during_the_switch_fires_at_once_stamped_with_its_due_time() -> None:
    # The carried state holds a timer whose time has already come (it fell due while the case
    # switched runs): the new run fires it at once, stamped with its due time, never "now". The
    # timer its rule's start sets is due an hour after that stamp, and fires at once in turn.
    definition = chased()
    definition["rules"]["remind_lead"] = {
        "display": {"title": "Remind the team lead"},
        "on": {"after": "1h", "since": {"started": "chase"}},
        "then": {"stop": ["chase"]},
    }
    carried = run_in_memory(definition, file=SMALL_IN_MEMORY, answers=[], people=PEOPLE).state
    assert carried.timers[0].due == START + 2 * DAY  # long past on the test server

    async def scenario(client: Client) -> CaseReport:
        keys_of(client).create("refund-1")
        start = CaseStart(definition, {}, None, state_as_data(carried))
        await client.start_workflow(DevelopmentCases.run, start, id="refund-1", task_queue=QUEUE)
        case = case_handle(client, DevelopmentCases, "refund-1")
        return await reported(case, lambda now: "remind_lead#1" in "\n".join(now.history))

    ended = on_temporal(scenario)
    assert FIRED in ended.history
    assert "set remind_lead: 1h after started chase#1, due 2026-01-03T01:00:00Z" in ended.history
    assert "remind_lead#1 on 1h after started chase#1: stopping chase" in ended.history


def test_a_timer_crosses_in_the_carried_state() -> None:
    state = run_in_memory(chased(), file=SMALL_IN_MEMORY, answers=[], people=PEOPLE).state
    assert state.timers  # one is set
    assert state_from_data(state_as_data(state)) == state
    # A state carried from before 11f has no timers: none could be set then.
    before = state_as_data(state)
    del before["timers"]
    assert state_from_data(before).timers == []


def test_a_case_whose_timer_fired_replays() -> None:
    # The workflow timer and its firing are in history: a new worker replays them, the same
    # commands at the same places, the firing stamped as it was (brief, D44).
    async def scenario(environment: WorkflowEnvironment) -> WorkflowHistory:
        case = await start_case(
            environment.client, DevelopmentCases, chased(), SMALL, "refund-1", QUEUE
        )
        await reported(case, lambda now: bool(now.timers))
        await environment.sleep(timedelta(days=2, seconds=1))
        await reported(case, lambda now: FIRED in now.history)
        return await case.fetch_history()

    converter = development_converter()
    replay(skipping(scenario, converter=converter), DevelopmentCases, converter)


def test_a_close_cancels_a_timer_on_temporal_and_the_case_ends() -> None:
    # Closed as a duplicate before the chase is due: the timer is cancelled, said, and the
    # workflow ends without waiting for it (brief, D10) (brief, D44).
    async def scenario(client: Client) -> CaseReport:
        definition = chased(close_reasons=CLOSABLE)
        case = await start_case(client, DevelopmentCases, definition, SMALL, "refund-1", QUEUE)
        await reported(case, lambda now: bool(now.timers))
        await close(case, "duplicate", "ana", PEOPLE["ana"])
        return await case.result()

    ended = on_temporal(scenario)
    assert ended.status == "closed" and ended.timers == []
    assert (
        "cancelled chase_review, 2d after started review#1: closed as duplicate by ana"
    ) in ended.history


def test_a_timer_already_due_and_an_answer_in_one_workflow_task_fire_timer_first() -> None:
    # The carried state holds a review open and its chase long due. Ana's answer is signalled
    # before any worker runs, so the timer and the answer are decided in the same workflow task:
    # the timer fires first, stamped with its due time, before the answer stamped now (brief,
    # D44). Answered first, review#1 would be done and its timer cancelled, never fired.
    carried = run_in_memory(chased(), file=SMALL_IN_MEMORY, answers=[], people=PEOPLE).state
    assert carried.timers[0].due == START + 2 * DAY  # long past on the test server

    async def go() -> CaseReport:
        async with time_skipping(development_converter()) as environment:
            client = environment.client
            keys_of(client).create("refund-1")
            start = CaseStart(chased(), {}, None, state_as_data(carried))
            await client.start_workflow(
                DevelopmentCases.run, start, id="refund-1", task_queue=QUEUE
            )
            case = case_handle(client, DevelopmentCases, "refund-1")
            form = {"approved_amount": Decimal(40)}
            await answer(case, "review#1", "approve", "ana", ["support"], form)
            async with (
                activity_threads() as threads,
                case_worker(
                    client,
                    QUEUE,
                    DevelopmentCases,
                    DevelopmentPlans,
                    FAKES,
                    activity_executor=threads,
                ),
            ):
                answered = "ana answered review#1 approve as support, setting approved_amount"
                return await asyncio.wait_for(
                    reported(case, lambda now: answered in now.history), timeout=20
                )

    ended = asyncio.run(go())
    fired = ended.history.index(FIRED)
    assert fired < ended.history.index(
        "ana answered review#1 approve as support, setting approved_amount"
    )
    assert ended.timers == []
