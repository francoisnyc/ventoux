"""Change requests on Temporal (layer 12c), and the histories recorded before them.

The histories were recorded under main at `5801ca0`, before 12c changes anything on Temporal:
whatever 12c adds to a case's state, its signals or the rule of forgetting, a case or a request
opened before it replays as it was recorded (brief, D17) (brief, D51).
See docs/layers/12-releases.md (12c).
"""

import asyncio
from pathlib import Path

from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer
from test_temporal_approvals import EveryEventCases
from test_temporal_case import replay

from ventoux.temporal.cases import CaseWorkflow
from ventoux.temporal.worker import SANDBOX
from ventoux.testing import DevelopmentCases, DevelopmentForget, fixture_converter

HERE = Path(__file__).parent / "histories"

# The refund waiting for its approval, a case open when 12c is deployed; one that continued as new
# after every event, so it starts from states carried before 12c; and a claim its opener, olu,
# approved forgetting, as 9c allowed.
BEFORE_12C: dict[str, tuple[str, type[CaseWorkflow]]] = {
    "before_12c_waiting": ("refund-1", DevelopmentCases),
    "before_12c_switched": ("refund-1", EveryEventCases),
    "before_12c_forgotten_by_its_opener": ("claim-7", DevelopmentCases),
}


def test_histories_from_before_12c_replay() -> None:
    for name, (id, cases) in BEFORE_12C.items():
        recorded = HERE / f"{name}.json"
        history = WorkflowHistory.from_json(id, recorded.read_text())
        replay(history, cases, fixture_converter(recorded))
    # The request that olu approved, recorded with the case's: its approval stands on replay.
    recorded = HERE / "before_12c_forget_request.json"
    request = WorkflowHistory.from_json("claim-7/forget", recorded.read_text())
    replayer = Replayer(
        workflows=[DevelopmentForget],
        data_converter=fixture_converter(recorded),
        workflow_runner=SANDBOX,
    )
    asyncio.run(replayer.replay_workflow(request))
