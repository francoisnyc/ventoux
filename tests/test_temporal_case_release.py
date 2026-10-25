"""A case's release and engine version on Temporal (layer 12b): histories recorded before it.

Recorded under main at `b734098`, before 12b changes anything on Temporal: whatever 12b adds to a
case's start or state, a case opened before it replays as it was recorded (brief, D17, D27).
See docs/layers/12-releases.md (12b).
"""

import asyncio
import copy
import json
import shutil
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

import pytest
from temporalio import workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
    WorkflowFailureError,
    WorkflowHistory,
)
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_temporal_approvals import EveryEventCases
from test_temporal_case import (
    LARGE,
    PEOPLE,
    QUEUE,
    REFUND,
    REVIEW_FORM,
    Case,
    CasesWithPlans,
    child_waiting_at,
    on_temporal,
    replay,
    reported,
    runs_of,
    unapproved_refund_order,
)

from ventoux.case.releases import Hash, Record
from ventoux.case.state import CaseState
from ventoux.temporal import client as plans
from ventoux.temporal.activities import plan_activities
from ventoux.temporal.carried import state_as_data
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    CaseWorkflow,
    ReleaseStart,
    WordingRefused,
    answer,
    approval_sheet,
    close,
    opening,
    propose,
    report,
    start_case,
    view,
    wording_of,
)
from ventoux.temporal.converter import keys_of
from ventoux.testing import (
    CATALOG,
    FAKES,
    START,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
    fixture_converter,
)
from ventoux.tooling.releases import FolderStore, release

HERE = Path(__file__).parent / "histories"

# The quickstart's refund paid and closed; the same refund still waiting for its approval, a case
# open when 12b is deployed; the last run of one that continued as new after every event, so it
# starts from a state carried before 12b; and the cases guide's plan step, settled.
BEFORE_12B: dict[str, type[CaseWorkflow]] = {
    "before_12b_paid": DevelopmentCases,
    "before_12b_waiting": DevelopmentCases,
    "before_12b_switched": EveryEventCases,
    "before_12b_settled": CasesWithPlans,
}


def test_histories_from_before_12b_replay() -> None:
    for name, cases in BEFORE_12B.items():
        recorded = HERE / f"{name}.json"
        history = WorkflowHistory.from_json("refund-1", recorded.read_text())
        replay(history, cases, fixture_converter(recorded))


def test_an_unknown_engine_version_waits_for_its_code() -> None:
    # A run carrying a version this code doesn't know fails its workflow task, which Temporal
    # retries until code that knows it is deployed: the case waits, never decided as an older
    # version, never failed for good (brief, D17, D51).
    async def scenario(client: Client) -> tuple[list[str], bool]:
        carried = state_as_data(CaseState("refund-1/run-1")) | {"engine": 3}
        case = await client.start_workflow(
            DevelopmentCases.run,
            CaseStart(REFUND, {}, None, carried),
            id="refund-1",
            task_queue=QUEUE,
        )
        for _ in range(100):
            history = await case.fetch_history()
            kinds = [EventType.Name(event.event_type) for event in history.events]
            if "EVENT_TYPE_WORKFLOW_TASK_FAILED" in kinds:
                break
            await asyncio.sleep(0.05)
        described = await case.describe()
        await case.terminate()
        return kinds, described.status == WorkflowExecutionStatus.RUNNING

    kinds, running = on_temporal(scenario)
    assert "EVENT_TYPE_WORKFLOW_TASK_FAILED" in kinds
    assert running


# --- Slice 4: a case opens on its release ---

PACKAGE = Path(__file__).parent.parent / "examples" / "packages" / "refund"


def released(tmp_path: Path, proposed: bool = False) -> Record:
    """The example package released once, as CI would, and its record read back; `proposed`:
    with `settle` started only when a team lead proposes it."""
    folder = tmp_path / "refund"
    shutil.copytree(PACKAGE, folder)
    if proposed:
        case = json.loads((folder / "case.json").read_text())
        case["steps"]["settle"] |= {"automatic": False, "proposed_by": ["support-lead"]}
        # Open until a person closes it, so it continues as new before settle is proposed.
        case["stays_open"] = True
        case["close_reasons"] = {"settled": {"display": {"title": "Settled"}, "roles": ["support"]}}
        (folder / "case.json").write_text(json.dumps(case))
    store = FolderStore(tmp_path / "releases")
    release(folder, store, "4f2a9c1", CATALOG)
    return store.get("refund", 1)


def kinds_of(history: WorkflowHistory) -> list[str]:
    return [EventType.Name(event.event_type) for event in history.events]


def markers_of(history: WorkflowHistory) -> list[str]:
    """The patch markers `history` records, by their IDs: each engine version above 1 asked for
    and in force (brief, D51)."""
    found: list[str] = []
    for event in history.events:
        if event.event_type == EventType.EVENT_TYPE_MARKER_RECORDED:
            details = event.marker_recorded_event_attributes.details
            found.append(json.loads(details["patch-data"].payloads[0].data)["id"])
    return found


def test_a_case_opens_on_its_release(tmp_path: Path) -> None:
    refund_1 = released(tmp_path)

    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory]:
        case = await start_case(client, DevelopmentCases, refund_1, LARGE, "refund-1", QUEUE)
        now = await reported(case, lambda now: now.waiting_at == ["review#1"])
        return now, await case.fetch_history()

    now, history = on_temporal(scenario)
    assert (now.release, now.engine) == ("refund 1", 2)
    assert now.history[:2] == [
        "opened on refund 1, engine 2",
        "opened by system:opener, with amount and order_id",
    ]
    # Version 2 is a patch marker, written once at the opening (brief, D51) (brief, D52).
    assert markers_of(history) == ["ventoux-engine-2"]


def test_a_draft_is_as_before() -> None:
    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory]:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        now = await reported(case, lambda now: now.waiting_at == ["review#1"])
        return now, await case.fetch_history()

    now, history = on_temporal(scenario)
    assert (now.release, now.engine) == ("draft", 2)
    assert now.history[0] == "opened by system:opener, with amount and order_id"
    # The engine decides a draft too: its version's marker is its one difference (brief, D52).
    assert markers_of(history) == ["ventoux-engine-2"]


def test_a_start_that_isnt_its_release_is_refused(tmp_path: Path) -> None:
    # The case checks what it was given, depending on nothing the client did (brief, D34, D51):
    # a start whose case or plans aren't the release's package is refused, nothing decided.
    refund_1 = released(tmp_path)
    start = opening(refund_1, LARGE)
    assert start.release is not None
    # A valid case, but not refund 1's: settle no longer waits for the review.
    definition = copy.deepcopy(start.definition)
    definition["steps"]["settle"]["requires"] = []
    tampered = replace(start, definition=definition)

    async def scenario(client: Client) -> Any:
        keys_of(client).create("refund-1")  # as `start_case` does: its failure is sealed with it
        case = await client.start_workflow(
            DevelopmentCases.run, tampered, id="refund-1", task_queue=QUEUE
        )
        with pytest.raises(WorkflowFailureError) as failed:
            await case.result()
        return failed.value.cause

    cause = on_temporal(scenario)
    assert isinstance(cause, ApplicationError) and cause.type == "CaseRefused"
    assert cause.message == (
        "refund-1 can't open on refund 1: what it was given isn't refund 1's package"
    )


def settled_on(
    client: Client, cases: type[CaseWorkflow], refund_1: Record, proposing: bool = False
) -> Awaitable[tuple[CaseReport, str | None]]:
    """Open a case of `cases` on refund 1, review it, and answer its plan's approval: its report
    once settled, and where the plan waited."""

    async def scenario() -> tuple[CaseReport, str | None]:
        case = await start_case(client, cases, refund_1, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        if proposing:
            for _ in range(100):  # until the case has continued as new since it opened
                first, current = await runs_of(client, "refund-1")
                if current != first:
                    break
                await asyncio.sleep(0.05)
            assert current != first
            await propose(case, "settle", "lee", PEOPLE["lee"])
        plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        waited = (await plans.report(plan)).waiting_at
        await plans.answer(plan, "approve_refund#1", "approve", "sam", PEOPLE["sam"])
        await plan.result()
        if proposing:
            await reported(case, lambda now: "settle#1 done" in now.history)
            await close(case, "settled", "ana", PEOPLE["ana"])
        return await case.result(), waited

    return scenario()


def test_the_release_and_engine_cross_continue_as_new(tmp_path: Path) -> None:
    # A case switching after every event keeps its release and engine version, and its plan,
    # proposed after a switch, comes from the release it carries: this worker supplies no plans at
    # all (brief, D27, D51).
    refund_1 = released(tmp_path, proposed=True)
    ended, waited = on_temporal(
        lambda client: settled_on(client, EveryEventCases, refund_1, proposing=True),
        cases=EveryEventCases,
    )
    assert waited == "approve_refund#1"
    assert (ended.status, ended.release, ended.engine) == ("closed", "refund 1", 2)
    assert "settle#1 done" in ended.history


# Temporal: a deployment whose own `refund-order@1` was changed under the same reference: it pays
# straight after the lookup, with no approval, so the engine stops it.
@workflow.defn(name="ventoux.case")
class ChangedPlans(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    plans: ClassVar[Mapping[str, Any]] = {
        "refund-order@1": unapproved_refund_order() | {"version": 1}
    }

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def test_a_released_case_runs_its_releases_plans(tmp_path: Path) -> None:
    # The deployment's changed plan never reaches a case opened on refund 1: it runs refund 1's,
    # which waits for a team lead (brief, D28, D51).
    refund_1 = released(tmp_path)
    ended, waited = on_temporal(
        lambda client: settled_on(client, ChangedPlans, refund_1), cases=ChangedPlans
    )
    assert waited == "approve_refund#1"
    assert ended.status == "closed" and ended.needs_attention == []


# --- Slice 6: wording, read when it is shown ---

QUICKSTART = Path(__file__).parent.parent / "examples" / "refund" / "refund.json"


def retitle_amount(title: str) -> Callable[[dict[str, Any]], None]:
    def change(case: dict[str, Any]) -> None:
        case["fields"]["approved_amount"]["display"]["title"] = title

    return change


def quickstart_released(tmp_path: Path, *changes: Callable[[dict[str, Any]], None]) -> FolderStore:
    """The quickstart's refund as a package, released, then each change released in turn."""
    folder = tmp_path / "quickstart"
    folder.mkdir()
    shutil.copy(QUICKSTART, folder / "case.json")
    store = FolderStore(tmp_path / "releases")
    release(folder, store, "a0", CATALOG)
    for number, change in enumerate(changes, start=1):
        case = json.loads((folder / "case.json").read_text())
        change(case)
        (folder / "case.json").write_text(json.dumps(case))
        release(folder, store, f"a{number}", CATALOG)
    return store


async def waiting_for_approval(client: Client, opening_on: Any) -> Case:
    case = await start_case(client, DevelopmentCases, opening_on, LARGE, "refund-1", QUEUE)
    await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
    await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
    return case


def test_new_wording_is_read_when_shown(tmp_path: Path) -> None:
    # Reworded after the case opened: the view and the sheet show the new title when given the
    # revision, the old one without it, and nothing the case decided or recorded changes
    # (brief, D51).
    store = quickstart_released(tmp_path, retitle_amount("Amount the team agreed"))
    refund_1, reworded = store.get("refund", 1), store.get("refund", 1, wording=2)

    async def scenario(client: Client) -> tuple[list[str], list[str], list[str], CaseReport]:
        case = await waiting_for_approval(client, refund_1)
        before = await report(case)
        new = (await view(case, ["support"], wording_of(reworded))).lines
        old = (await view(case, ["support"])).lines
        sheet = await approval_sheet(
            case, "pay.approval#1", ["support-lead"], START, wording_of(reworded)
        )
        after = await report(case)
        assert after.history == before.history
        return new, old, sheet.lines, after

    new, old, sheet, now = on_temporal(scenario)
    assert any(line.startswith("Amount the team agreed: 250") for line in new)
    assert any(line.startswith("Amount approved: 250") for line in old)
    assert any(line.startswith("Amount the team agreed: 250") for line in sheet)
    assert now.waiting_at == ["pay.approval#1"]


def test_wording_of_another_release_is_refused(tmp_path: Path) -> None:
    # Fail closed: a revision of another release, or any revision for a draft, is refused,
    # never read in its place (brief, D51).
    store = quickstart_released(
        tmp_path,
        lambda case: case["steps"]["pay"]["approval"].update(
            when={">": [{"var": "approved_amount"}, 200]}
        ),
    )
    refund_1, refund_2 = store.get("refund", 1), store.get("refund", 2)

    async def scenario(client: Client) -> tuple[str, str]:
        case = await waiting_for_approval(client, refund_1)
        with pytest.raises(WordingRefused) as other:
            await view(case, ["support"], wording_of(refund_2))
        # Claiming to be refund 1, with refund 2's behaviour: its digest isn't refund 1's.
        claiming = replace(wording_of(refund_2), release=1)
        with pytest.raises(WordingRefused) as claimed:
            await approval_sheet(case, "pay.approval#1", ["support-lead"], START, claiming)
        assert str(claimed.value) == (
            "refund 1, wording 1 isn't a wording of refund 1, which this case runs"
        )
        draft = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-2", QUEUE)
        with pytest.raises(WordingRefused) as drafted:
            await view(draft, ["support"], wording_of(refund_1))
        return str(other.value), str(drafted.value)

    other, drafted = on_temporal(scenario)
    assert other == "refund 2, wording 1 isn't a wording of refund 1, which this case runs"
    assert drafted == "refund 1, wording 1 isn't a wording of this case: it is a draft"


def test_an_answer_says_which_wording_it_saw(tmp_path: Path) -> None:
    store = quickstart_released(tmp_path, retitle_amount("Amount the team agreed"))

    async def scenario(client: Client) -> CaseReport:
        case = await start_case(
            client, DevelopmentCases, store.get("refund", 1), LARGE, "refund-1", QUEUE
        )
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM, wording=2)
        # A draft has no wording revisions: an answer naming one is refused, and recorded.
        draft = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-2", QUEUE)
        await answer(draft, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM, wording=2)
        drafted = await reported(draft, lambda now: now.history[-1].startswith("refused"))
        assert drafted.history[-1] == (
            "refused ana's answer approve to review#1: wording 2 names no wording of this case: "
            "it is a draft"
        )
        return await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])

    now = on_temporal(scenario)
    assert (
        "ana answered review#1 approve as support, setting approved_amount, as worded in "
        "refund 1, wording 2"
    ) in now.history


CASES_GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "cases.md"


def test_the_guides_release_example_runs_as_written(tmp_path: Path) -> None:
    # The cases guide's "A case runs its release": the history it shows is the one a case opened
    # on the example package's first release begins with.
    section = CASES_GUIDE.read_text().split("### A case runs its release")[1].split("\n## ")[0]
    shown = section.split("Its history begins")[1].split("```\n")[1].split("```")[0].splitlines()
    refund_1 = released(tmp_path)

    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, refund_1, LARGE, "refund-1", QUEUE)
        return await reported(case, lambda now: now.waiting_at == ["review#1"])

    now = on_temporal(scenario)
    assert now.history[: len(shown)] == shown
    assert (now.release, now.engine) == ("refund 1", 2)


# --- From the tutor review: a continued run that can't read its start waits for its code ---


# Temporal: a worker whose code no longer gives the release's digest, as a later change to method
# 1 would: it reads every release's digest as all zeros. Same workflow name, so it picks up the
# case's next workflow task.
@workflow.defn(name="ventoux.case")
class DigestChanged(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    events_per_run = 1

    def released_on(self, case: Any, release: ReleaseStart) -> str:
        return super().released_on(case, replace(release, digest=Hash(1, "0" * 64)))

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def test_a_continued_run_whose_digest_changed_waits_for_its_code(tmp_path: Path) -> None:
    # The case opened and continued as new on code that gave its release's digest; the code then
    # changes and no longer gives it. The next run's workflow task fails, and the case waits,
    # running, never failed for good; code that gives it again lets the case go on (brief, D17,
    # D51).
    refund_1 = released(tmp_path, proposed=True)

    async def scenario() -> tuple[list[str], bool, CaseReport]:
        environment = await WorkflowEnvironment.start_time_skipping(
            data_converter=development_converter()
        )
        async with environment:
            client = environment.client

            def serving(cases: type[CaseWorkflow]) -> Worker:
                # Temporal: with no workflow cached, each task goes to the queue every worker
                # polls, never to a stopped worker's own, so the next worker takes it at once.
                # The price: every task, each `report` asked included, replays the case from its
                # start. The sandbox re-imports the workflow's module for each replay: this test
                # module, and the sixteen it imports, through pytest's assertion rewriting, 2 s
                # on an idle Intel Mac, over the 1 s each ask of `reported` waits; and once one
                # ask is late, the next comes while the worker still replays for the last, so
                # every ask is late. Unsandboxed, a replay takes 10 ms
                # (docs/layers/fix-flaky-temporal.md).
                return Worker(
                    client,
                    task_queue=QUEUE,
                    workflows=[cases, DevelopmentPlans],
                    activities=plan_activities(cases.catalog, FAKES),
                    activity_executor=ThreadPoolExecutor(),
                    workflow_runner=UnsandboxedWorkflowRunner(),
                    max_cached_workflows=0,
                )

            async with serving(EveryEventCases):
                case = await start_case(client, EveryEventCases, refund_1, LARGE, "refund-1", QUEUE)
                await reported(case, lambda now: now.waiting_at == ["review#1"])
                first, current = await runs_of(client, "refund-1")
                assert current != first  # it has continued as new since it opened
            async with serving(DigestChanged):
                await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
                for _ in range(100):
                    kinds = kinds_of(await case.fetch_history())
                    if "EVENT_TYPE_WORKFLOW_TASK_FAILED" in kinds:
                        break
                    await asyncio.sleep(0.05)
                running = (await case.describe()).status == WorkflowExecutionStatus.RUNNING
            async with serving(EveryEventCases):
                now = await reported(case, lambda now: "review#1 done" in now.history)
            return kinds, running, now

    kinds, running, now = asyncio.run(asyncio.wait_for(scenario(), timeout=60))
    assert "EVENT_TYPE_WORKFLOW_TASK_FAILED" in kinds
    assert running
    assert (now.status, now.release) == ("open", "refund 1")


def test_a_continued_run_whose_definition_no_longer_reads_waits_for_its_code() -> None:
    # The same for a definition that read when the case opened and no longer does on a later
    # run: a change of code, never a reason to fail the case for good (brief, D17, D51).
    async def scenario(client: Client) -> tuple[list[str], bool]:
        carried = state_as_data(CaseState("refund-1/run-1"))
        unreadable = REFUND | {"stays_open": "yes"}
        keys_of(client).create("refund-1")
        case = await client.start_workflow(
            DevelopmentCases.run,
            CaseStart(unreadable, {}, None, carried),
            id="refund-1",
            task_queue=QUEUE,
        )
        for _ in range(100):
            kinds = kinds_of(await case.fetch_history())
            if "EVENT_TYPE_WORKFLOW_TASK_FAILED" in kinds:
                break
            await asyncio.sleep(0.05)
        running = (await case.describe()).status == WorkflowExecutionStatus.RUNNING
        await case.terminate()
        return kinds, running

    kinds, running = on_temporal(scenario)
    assert "EVENT_TYPE_WORKFLOW_TASK_FAILED" in kinds
    assert running
