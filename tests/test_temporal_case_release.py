"""A case's release and engine version on Temporal (layer 12b): histories recorded before it.

Recorded under main at `b734098`, before 12b changes anything on Temporal: whatever 12b adds to a
case's start or state, a case opened before it replays as it was recorded (brief, D17, D27).
See docs/layers/12-releases.md (12b).
"""

from pathlib import Path

from temporalio.client import WorkflowHistory

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_temporal_approvals import EveryEventCases
from test_temporal_case import CasesWithPlans, replay

from ventoux.temporal.cases import CaseWorkflow
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
