"""Migrations on Temporal (layer 12d), and the histories recorded before them.

The histories were recorded under main at `66e2cff`, before 12d changes anything on Temporal:
whatever 12d adds to a case's state, its commands or its start, a case opened before it replays as
it was recorded (brief, D17) (brief, D51).
See docs/layers/12-releases.md (12d).
"""

from pathlib import Path

from temporalio.client import WorkflowHistory
from test_temporal_approvals import EveryEventCases
from test_temporal_case import replay

from ventoux.temporal.cases import CaseWorkflow
from ventoux.testing import DevelopmentCases, fixture_converter

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
