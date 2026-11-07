"""Layer 18d: child cases on Temporal. A child is its own workflow under its parent's ID and key,
started with `ABANDON`; its end is a doorbell, and the parent reads the report itself (brief,
D75).

See docs/layers/18-lifecycle.md (18d) and docs/guides/cases.md, "Child cases".
"""

from decimal import Decimal

from temporalio.client import Client
from test_child_cases import claim
from test_temporal_case import QUEUE, on_temporal, reported

from ventoux.temporal.cases import CaseReport, answer, case_handle, start_case
from ventoux.testing import DevelopmentCases

FILE = {"order_id": "ord-1", "vehicle": "veh-9"}


def test_a_doorbell_for_no_open_child_is_recorded_and_changes_nothing() -> None:
    # A signal says nothing of who sent it: anyone with the namespace may ring. One for an entry
    # that is no open child of the case finds nothing to read (brief, D75).
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, claim(), FILE, "claim-1", QUEUE)
        await answer(case, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await case_handle(client, DevelopmentCases, "claim-1").signal("child_ended", "repair#2")
        return await reported(case, lambda now: any("child_ended" in line for line in now.history))

    report = on_temporal(scenario)
    assert "child_ended for repair#2, which is no open child: nothing read" in report.history
    assert "repair.outcome" not in "\n".join(report.history)
