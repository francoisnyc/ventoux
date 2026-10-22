"""A case's release and engine version on Temporal (layer 12b): histories recorded before it.

Recorded under main at `b734098`, before 12b changes anything on Temporal: whatever 12b adds to a
case's start or state, a case opened before it replays as it was recorded (brief, D17, D27).
See docs/layers/12-releases.md (12b).
"""

import asyncio
from pathlib import Path

from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowExecutionStatus, WorkflowHistory

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_temporal_approvals import EveryEventCases
from test_temporal_case import QUEUE, REFUND, CasesWithPlans, on_temporal, replay

from ventoux.case.state import CaseState
from ventoux.temporal.carried import state_as_data
from ventoux.temporal.cases import CaseStart, CaseWorkflow
from ventoux.testing import DevelopmentCases, fixture_converter

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
        carried = state_as_data(CaseState("refund-1/run-1")) | {"engine": 2}
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
