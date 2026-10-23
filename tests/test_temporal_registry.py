"""Activation on Temporal (layer 12e): manifests, the environment registry, a case in an
environment; and the histories recorded before them.

The histories were recorded under main at `2fde255`, before 12e changes anything on Temporal:
whatever 12e adds to a case's start or commands, a case opened before it replays as it was
recorded (brief, D17) (brief, D51).
See docs/layers/12-releases.md (12e).
"""

from pathlib import Path

from temporalio.client import WorkflowHistory
from test_temporal_approvals import EveryEventCases
from test_temporal_case import replay

from ventoux.temporal.cases import CaseWorkflow
from ventoux.testing import DevelopmentCases, fixture_converter

HERE = Path(__file__).parent / "histories"

# A draft and a release, each waiting for its approval; the same release continued as new after
# every event; a case migrated to refund 2 across switches; and a case closed, its review rejected.
BEFORE_12E: dict[str, type[CaseWorkflow]] = {
    "before_12e_draft_waiting": DevelopmentCases,
    "before_12e_released_waiting": DevelopmentCases,
    "before_12e_released_switched": EveryEventCases,
    "before_12e_migrated_switched": EveryEventCases,
    "before_12e_closed": DevelopmentCases,
}


def test_histories_from_before_12e_replay() -> None:
    for name, cases in BEFORE_12E.items():
        recorded = HERE / f"{name}.json"
        history = WorkflowHistory.from_json("refund-1", recorded.read_text())
        replay(history, cases, fixture_converter(recorded))
