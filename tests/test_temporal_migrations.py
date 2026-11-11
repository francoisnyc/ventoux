"""Migrations on Temporal (layer 12d), and the histories recorded before them.

The histories were recorded under main at `66e2cff`, before 12d changes anything on Temporal:
whatever 12d adds to a case's state, its commands or its start, a case opened before it replays as
it was recorded (brief, D17) (brief, D51).
See docs/layers/12-releases.md (12d).
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from temporalio import workflow
from temporalio.client import Client, WorkflowHistory
from test_migrations import PEOPLE, REFUND_1, REFUND_2, REFUND_3, RENAMES
from test_temporal_approvals import EveryEventCases
from test_temporal_case import LARGE, QUEUE, continued_as_new, on_temporal, replay, reported

from ventoux.case import engine as engine_module
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    CaseWorkflow,
    PreviewAnswer,
    answer,
    case_handle,
    preview_migrations,
    propose_migration,
    report,
    shown,
    start_case,
)
from ventoux.testing import (
    DevelopmentCases,
    development_converter,
    fixture_converter,
)
from ventoux.tooling.audit import FileAudit

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
    assert (ended.status, ended.release, ended.engine) == ("closed", "refund 2", 3)
    assert (
        "applied case.change#1: migrated from refund 1, engine 3 to refund 2, engine 3, "
        "proposed by pia, approved by lee"
    ) in ended.history
    assert "pay#1 done, giving refund_id from untrusted:undeclared" in ended.history
    replay(history, EveryEventCases, converter)


# Temporal: a case workflow that continues as new after five events decided: the opening, the
# review, Lee's answer, the proposal to engine 4, and the record shown. A proposal the driver
# refuses before deciding it (to engine 3) isn't one.
@workflow.defn(name="ventoux.case")
class SwitchingAfterFive(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    events_per_run = 5

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def test_a_case_moves_on_temporal_only_to_an_engine_it_opens_cases_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # As 19a left it, this code knew engine 3 but opened no case at it: a migration there was
    # refused when proposed, saying so (from the tutor's review of #90). Once 19b's code runs the
    # case, it opens cases at 3, so the case moves there, and its export starts with the
    # migration's record, saying what came before was not recorded (brief, D51) (brief, D76)
    # (brief, D77).
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[CaseReport, CaseReport]:
        # Python's `monkeypatch`: each run of the workflow imports its module afresh in the
        # sandbox, reading `OPENING` from `ventoux.case.engine`, which the sandbox passes through:
        # this run, as 19a's code, opens cases at 2 at most.
        monkeypatch.setattr(engine_module, "OPENING", (2, 1))
        case = await start_case(client, SwitchingAfterFive, REFUND_1, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await propose_migration(case, REFUND_2, {}, "pia", PEOPLE["pia"], engine=3)
        await answer(case, "case.change#1", "approve", "lee", PEOPLE["lee"])
        # A version this code doesn't know at all is the case's own refusal, as in memory.
        await propose_migration(case, REFUND_2, {}, "pia", PEOPLE["pia"], engine=4)
        refused = await reported(case, lambda now: "engine 4" in now.history[-1])
        # The next run imports 19b's code: a fifth event, and the case continues as new.
        monkeypatch.setattr(engine_module, "OPENING", (3, 2, 1))
        await shown(case, "order_id", "ana", PEOPLE["ana"])
        await continued_as_new(client, "refund-1")
        await propose_migration(case, REFUND_2, {}, "pia", PEOPLE["pia"], engine=3)
        # The first request numbered: the refused proposals never were.
        await reported(case, lambda now: "case.change#1" in now.waiting_at)
        await answer(case, "case.change#1", "approve", "lee", PEOPLE["lee"])
        moved = await reported(case, lambda now: now.engine == 3 and now.unwritten == 0)
        return refused, moved

    refused, moved = on_temporal(scenario, cases=SwitchingAfterFive, audit=store)
    assert refused.history[-3:] == [
        (
            "refused pia's proposal to migrate refund 2: engine 3 is one this code knows but "
            "doesn't run cases at yet (it runs them at 2, 1)"
        ),
        "refused lee's answer approve to case.change#1: case.change#1 isn't open",
        (
            "refused pia's proposal to migrate refund 2: engine 4 is one this code doesn't know "
            "(it knows 3, 2, 1)"
        ),
    ]
    assert (refused.release, refused.engine) == ("refund 1", 2)
    assert (moved.release, moved.engine) == ("refund 2", 3)
    [first, *_] = store.read("refund-1")
    assert first["number"] == 1
    assert first["decisions"][0]["kind"] == "migrated"
    assert first["decisions"][0]["reason"] == "what came before engine 3 was not recorded"


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
        "from refund 1, engine 3 to refund 3, engine 3",
        "withdrew pay.approval#1: refund 3 changed pay",
        "renamed step pay to payment",
        "renamed field approved_amount to amount_approved",
    ]
    assert seen["refund-2"] == PreviewAnswer(["the case is closed: nothing changes it"], [])
    assert seen["refund-9"] == PreviewAnswer(["refund-9 is not a case: no workflow has its ID"], [])
    assert after == before


# --- Slice 10: the guide ---

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "releases.md").read_text()
SNIPPET = (
    GUIDE.split("## Moving open cases to a later release\n")[1]
    .split("\n## ")[0]
    .split("```python\n")[3]
    .split("```")[0]
)


def test_the_guides_cohort_example_runs_as_written() -> None:
    # The releases guide's preview and proposals on Temporal, run as written inside a coroutine,
    # as a client would (our own documentation, never a definition).
    code = "async def snippet():\n" + "".join(f"    {line}\n" for line in SNIPPET.splitlines())

    async def scenario(client: Client) -> list[list[str]]:
        cohort = ["refund-A-1001", "refund-A-1002"]
        for id in cohort:
            case = await start_case(client, DevelopmentCases, REFUND_1, LARGE, id, QUEUE)
            await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
            await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        namespace: dict[str, Any] = {
            "client": client,
            "RefundCases": DevelopmentCases,
            "refund_3": REFUND_3,
            "renames": RENAMES,
            "preview_migrations": preview_migrations,
            "propose_migration": propose_migration,
            "case_handle": case_handle,
        }
        exec(code, namespace)  # noqa: S102
        await namespace["snippet"]()
        waiting = []
        for id in cohort:
            case = case_handle(client, DevelopmentCases, id)
            now = await reported(case, lambda now: "case.change#1" in now.waiting_at)
            waiting.append(now.waiting_at)
        return waiting

    assert on_temporal(scenario) == [["pay.approval#1", "case.change#1"]] * 2
