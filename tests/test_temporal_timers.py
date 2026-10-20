"""Layer 11f on Temporal: a timer is a workflow timer whose firing is decided stamped with its due
time; it crosses continue-as-new exactly; and histories recorded before 11f replay.

See docs/layers/11-rules.md (11f) and the brief, D44.
"""

from pathlib import Path

from temporalio.client import WorkflowHistory

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_temporal_case import replay

from ventoux.testing import DevelopmentCases, fixture_converter

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
