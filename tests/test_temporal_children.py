"""Layer 18d: child cases on Temporal. A child is its own workflow under its parent's ID and key,
started with `ABANDON`; its end is a doorbell, and the parent reads the report itself (brief,
D75).

See docs/layers/18-lifecycle.md (18d) and docs/guides/cases.md, "Child cases".
"""

from decimal import Decimal

from temporalio.client import Client
from test_child_cases import claim, repair
from test_temporal_case import QUEUE, on_temporal, reported

from ventoux.temporal.cases import CaseReport, answer, case_handle, start_case
from ventoux.testing import DevelopmentCases, release_of

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


RELEASE = release_of(claim(), 1, cases={"repair@3": repair()})


def test_the_guides_child_case_runs_on_temporal() -> None:
    # The child is its own workflow under its parent's ID; it rings as its last act, and the
    # parent reads its report itself, with its sources and the route it came by (brief, D75).
    async def scenario(client: Client) -> tuple[CaseReport, CaseReport]:
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-7", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        child = case_handle(client, DevelopmentCases, "claim-7/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"])
        await answer(child, "fix#1", "fixed", "lee", ["support-lead"], {"cost": Decimal(640)})
        await reported(parent, lambda now: now.waiting_at == ["pay_garage.approval#1"])
        roles = ["support", "support-lead"]
        await answer(parent, "pay_garage.approval#1", "approve", "sam", roles, None)
        done = await reported(parent, lambda now: now.status == "closed")
        return done, await reported(child, lambda now: now.status == "closed")

    parent, child = on_temporal(scenario)
    assert (
        "started repair#1: case repair@3 (vehicle from system:opener; budget from person:ana), "
        "run claim-7/repair#1"
    ) in parent.history
    assert "repair#1 done: repair closed, nothing left to do, reaching fixed; reporting cost" in (
        parent.history
    )
    # The report's sources crossed the doorbell's read intact, and gained the route.
    assert (
        "scheduled pay_garage#1: payments.refund@2 (order_id from system:opener; amount from "
        "case:repair, person:lee), key claim-7/"
    ) in "\n".join(parent.history)
    # A released case says its release first; then who opened it: its parent, never a person.
    assert child.history[:2] == [
        "opened on repair 3, engine 2",
        "opened by claim-7, from repair#1, with budget and vehicle",
    ]


def test_a_doorbell_for_a_child_still_open_reads_and_changes_nothing() -> None:
    # Rung by anyone while the child's case is open: the parent reads the child's own run, finds
    # it open, records so, and waits on (brief, D75).
    async def scenario(client: Client) -> CaseReport:
        parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-8", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
        await case_handle(client, DevelopmentCases, "claim-8").signal("child_ended", "repair#1")
        return await reported(parent, lambda now: any("child_ended" in l for l in now.history))

    report = on_temporal(scenario)
    assert "child_ended for repair#1, whose case is still open: nothing read" in report.history
    assert report.waiting_for == ["repair#1: case repair, open"]
