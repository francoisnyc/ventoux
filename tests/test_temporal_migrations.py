"""Migrations on Temporal (layer 12d), and the histories recorded before them.

The histories were recorded under main at `66e2cff`, before 12d changes anything on Temporal:
whatever 12d adds to a case's state, its commands or its start, a case opened before it replays as
it was recorded (brief, D17) (brief, D51).
See docs/layers/12-releases.md (12d).
"""

from decimal import Decimal
from pathlib import Path

from temporalio.client import Client, WorkflowHistory
from test_migrations import PEOPLE, REFUND_1, REFUND_2, REFUND_3, RENAMES
from test_temporal_approvals import EveryEventCases
from test_temporal_case import LARGE, QUEUE, on_temporal, replay, reported

from ventoux.temporal.cases import (
    CaseReport,
    CaseWorkflow,
    PreviewAnswer,
    answer,
    preview_migrations,
    propose_migration,
    report,
    start_case,
)
from ventoux.testing import DevelopmentCases, development_converter, fixture_converter

HERE = Path(__file__).parent / "histories"

# The example package's first release reviewed, its plan step waiting for a team lead; the same
# release waiting for its review, a case open when 12d is deployed; and a draft refund that
# continued as new after every event, an edit pending across the switches.
BEFORE_12D: dict[str, type[CaseWorkflow]] = {
    "before_12d_released_waiting": DevelopmentCases,
    "before_12d_released_open": DevelopmentCases,
    "before_12d_pending_edit_switched": EveryEventCases,
}


def test_histories_from_before_12d_replay() -> None:
    for name, cases in BEFORE_12D.items():
        recorded = HERE / f"{name}.json"
        history = WorkflowHistory.from_json("refund-1", recorded.read_text())
        replay(history, cases, fixture_converter(recorded))


# --- Slice 7: on Temporal ---

REVIEW_FORM = {"approved_amount": Decimal(250)}


def test_a_migrated_case_runs_its_new_release() -> None:
    # Every event in a run of its own: the migration is proposed in one, approved in a later one;
    # the case then decides as refund 2 in every run after, carried in its start, and its history
    # replays (brief, D27) (brief, D53).
    converter = development_converter()

    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory]:
        case = await start_case(client, EveryEventCases, REFUND_1, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await propose_migration(case, REFUND_2, {}, "pia", PEOPLE["pia"])
        await reported(case, lambda now: "case.change#1" in now.waiting_at)
        await answer(case, "case.change#1", "approve", "lee", PEOPLE["lee"])
        await reported(case, lambda now: now.waiting_at == ["fraud_check#1"])
        await answer(case, "fraud_check#1", "clear", "fay", PEOPLE["fay"])
        await reported(case, lambda now: now.waiting_at == ["pay.approval#2"])
        await answer(case, "pay.approval#2", "approve", "sam", PEOPLE["sam"])
        return await case.result(), await case.fetch_history()

    ended, history = on_temporal(scenario, cases=EveryEventCases, converter=converter)
    assert (ended.status, ended.release, ended.engine) == ("closed", "refund 2", 2)
    assert (
        "applied case.change#1: migrated from refund 1, engine 2 to refund 2, engine 2, "
        "proposed by pia, approved by lee"
    ) in ended.history
    assert "pay#1 done, giving refund_id from untrusted:undeclared" in ended.history
    replay(history, EveryEventCases, converter)


def test_a_cohort_preview_names_every_case() -> None:
    # The cohort is the case IDs given: each in the result, with what it would get or why not,
    # none skipped silently; and a preview is a query, so no case's history changes
    # (brief, D53). Finding the open cases of a release comes with 12e's registry.
    async def scenario(client: Client) -> tuple[dict[str, PreviewAnswer], list[str], list[str]]:
        waiting = await start_case(client, DevelopmentCases, REFUND_1, LARGE, "refund-1", QUEUE)
        await answer(waiting, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(waiting, lambda now: now.waiting_at == ["pay.approval#1"])
        rejected = await start_case(client, DevelopmentCases, REFUND_1, LARGE, "refund-2", QUEUE)
        await answer(rejected, "review#1", "reject", "ana", PEOPLE["ana"])
        await rejected.result()
        before = (await report(waiting)).history
        cohort = ["refund-1", "refund-2", "refund-9"]
        seen = await preview_migrations(client, DevelopmentCases, cohort, REFUND_3, RENAMES)
        return seen, before, (await report(waiting)).history

    seen, before, after = on_temporal(scenario)
    assert list(seen) == ["refund-1", "refund-2", "refund-9"]
    assert seen["refund-1"].refused == []
    assert seen["refund-1"].lines[:4] == [
        "from refund 1, engine 2 to refund 3, engine 2",
        "withdrew pay.approval#1: refund 3 changed pay",
        "renamed step pay to payment",
        "renamed field approved_amount to amount_approved",
    ]
    assert seen["refund-2"] == PreviewAnswer(["the case is closed: nothing changes it"], [])
    assert seen["refund-9"] == PreviewAnswer(["refund-9 is not a case: no workflow has its ID"], [])
    assert after == before
