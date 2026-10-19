"""The fix of the untrusted moment on Temporal: what steered a run crosses continue-as-new, and
histories recorded before the fix replay, or don't, as the note says.

See docs/layers/fix-untrusted-moment.md and the brief, D43.
"""

from pathlib import Path
from typing import Any

import pytest
from temporalio.client import Client, WorkflowHistory
from temporalio.workflow import NondeterminismError

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_temporal_case import QUEUE, SMALL, SwitchingCases, on_temporal, replay, reported, runs_of
from test_untrusted_moment import LETTER, say_goodbye

from ventoux.case.state import CaseState, Moment, RuleFiring, RuleStart, StepRun
from ventoux.core.before_activity import Steering
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.cases import CaseReport, answer, retry, send_event, start_case
from ventoux.testing import DevelopmentCases, development_converter, fixture_converter

HERE = Path(__file__).parent / "histories"
STEERED = Steering(
    "say_goodbye#1's condition, which started goodbye, reads cancelled.note",
    frozenset({"untrusted:customer"}),
)


async def opened(client: Client, definition: dict[str, Any], id: str) -> Any:
    return await start_case(client, SwitchingCases, definition, SMALL, id=id, task_queue=QUEUE)


def test_a_failed_firing_keeps_what_steered_its_start_across_continue_as_new() -> None:
    # The rule can't be read when goodbye starts, the case continues as new, and an operator
    # retries it once it can be: it still doesn't act on that start.
    definition = say_goodbye()
    definition["rules"]["close_it"]["when"] = {"==": [{"var": "review.outcome"}, "reject"]}

    async def scenario(client: Client) -> tuple[CaseReport, tuple[str, str]]:
        case = await opened(client, definition, "refund-U-1")
        await send_event(case, "cancelled", {"note": "please cancel"}, by="system:portal")
        await reported(case, lambda now: now.needs_attention != [])
        await answer(case, "review#1", "reject", by="ana", roles=["support"])
        await retry(case, "close_it#1", by="omar", roles=["operations"])
        now = await reported(case, lambda now: now.needs_attention == [])
        return now, await runs_of(client, "refund-U-1")

    now, (first, last) = on_temporal(scenario, cases=SwitchingCases)
    assert last != first  # the case continued as new in between
    assert now.status == "open"
    assert (
        "close_it#1 on started goodbye: reaches nothing: its moment comes from untrusted data: "
        "say_goodbye#1's condition, which started goodbye, reads cancelled.note "
        "(untrusted:customer), and untrusted data can't decide"
    ) in now.history


def test_a_rules_start_keeps_what_steered_its_moment_across_continue_as_new() -> None:
    # A rule on goodbye's start starts a letter that needs a team lead's approval; the case
    # continues as new while it waits. Approved, the letter is still refused on its address.
    letter = LETTER | {"approval": {"roles": ["support-lead"], "display": {"reason": "Check"}}}
    definition = say_goodbye({"start": ["letter"]}, steps={"letter": letter})

    async def scenario(client: Client) -> tuple[CaseReport, tuple[str, str]]:
        case = await opened(client, definition, "refund-U-2")
        await send_event(case, "cancelled", {"note": "please cancel"}, by="system:portal")
        await reported(case, lambda now: "letter.approval#1" in now.waiting_at)
        await answer(case, "letter.approval#1", "approve", by="sam", roles=["support-lead"])
        now = await reported(case, lambda now: now.needs_attention != [])
        return now, await runs_of(client, "refund-U-2")

    now, (first, last) = on_temporal(scenario, cases=SwitchingCases)
    assert last != first
    assert now.needs_attention == [
        (
            "letter#1: letters.draft@2 takes to_customer only from a system or a person, never "
            "from untrusted data, and say_goodbye#1's condition, which started goodbye, reads "
            "cancelled.note (untrusted:customer)"
        )
    ]


def test_what_steered_a_run_reads_back_as_it_was() -> None:
    # Every part of the state that keeps it: a run, a firing, a rule's start waiting for its
    # run, and a moment (always empty between events, but written as data all the same).
    state = CaseState("refund-1/run")
    state.runs.append(StepRun("goodbye#1", "goodbye", "open", steered=(STEERED,)))
    state.firings.append(RuleFiring("close_it#1", "close_it", "started goodbye", "failed"))
    state.firings[0].steered = (STEERED,)
    asked = RuleStart("write#1", "started goodbye", "letter", steered=(STEERED,))
    state.proposed_by_rules["letter"] = asked
    state.rule_starts.append(asked)
    state.moments.append(Moment("started goodbye", "goodbye#1"))
    assert state_from_data(state_as_data(state)) == state


def test_a_state_carried_from_before_the_fix_reads_as_steered_by_nothing() -> None:
    # A run from before the fix wrote no `steered` on a firing or a rule's start: read back as
    # nothing, as a run from before 11b read its own.
    state = CaseState("refund-1/run")
    state.firings.append(RuleFiring("close_it#1", "close_it", "started goodbye", "failed"))
    state.proposed_by_rules["letter"] = RuleStart("write#1", "started goodbye", "letter")
    data = state_as_data(state)
    del data["firings"][0]["steered"]
    del data["proposed_by_rules"]["letter"]["steered"]
    assert state_from_data(data) == state


# --- Histories recorded under main, before the fix (brief, D17) ---

SET_ON_A_STEERED_START = HERE / "before_fix_untrusted_moment_set.json"
CLOSED_ON_A_STEERED_START = HERE / "before_fix_untrusted_moment_closed.json"


def test_a_history_the_fix_decides_the_same_replays() -> None:
    # Recorded under main: the note starts goodbye, a rule on its start sets `leaving` from the
    # amount, Ana answers both tasks, and the case closes. The fix changes only where `leaving`
    # comes from, which no command carries, so the new worker replays it.
    history = WorkflowHistory.from_json("refund-1", SET_ON_A_STEERED_START.read_text())
    replay(history, DevelopmentCases, fixture_converter(SET_ON_A_STEERED_START))


def test_a_history_the_fix_decides_differently_doesnt_replay() -> None:
    # The known limit (the note, decision 7). Recorded under main: the tutor review's case,
    # closed by the rule on goodbye's start. The fix keeps it open, so Temporal refuses the
    # history rather than let the case go another way than it went, and it waits until the code
    # is fixed (brief, D17). Carried to layer 12.
    history = WorkflowHistory.from_json("refund-1", CLOSED_ON_A_STEERED_START.read_text())
    with pytest.raises(NondeterminismError):
        replay(history, DevelopmentCases, fixture_converter(CLOSED_ON_A_STEERED_START))


def test_a_steered_start_on_temporal_is_decided_as_in_memory() -> None:
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(
            client, DevelopmentCases, say_goodbye(), SMALL, id="refund-U-3", task_queue=QUEUE
        )
        await send_event(case, "cancelled", {"note": "please cancel"}, by="system:portal")
        return await reported(case, lambda now: "close_it#1" in " ".join(now.history))

    now = on_temporal(scenario, converter=development_converter())
    assert now.status == "open"
    assert now.waiting_for == ["review by support", "goodbye by support"]
