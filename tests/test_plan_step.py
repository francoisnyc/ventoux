"""Layer 8c, slice 1: a plan step runs a plan as one step of a case, in memory (brief, D28).

Tests go through `parse_case` and `run_case`, and read what a run reports.
See docs/layers/08-case.md (8c) and docs/guides/cases.md, "Plan steps".
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import load_definition, propose, run_case

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")

PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"]}
LARGE = {"order_id": "ord-1", "amount": 250}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 250})

PLANS_GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "plans.md"


def refund_order() -> dict[str, Any]:
    """The plans guide's `refund-order` plan, its first JSON block, as stored data."""
    example = PLANS_GUIDE.read_text().split("```json\n")[1].split("```")[0]
    plan: dict[str, Any] = json.loads(example, parse_float=Decimal)
    return plan


# The guide's plan step: the refund paid through the plans guide's `refund-order` plan.
SETTLE: dict[str, Any] = {
    "kind": "plan",
    "display": {"title": "Settle the refund"},
    "plan": "refund-order@1",
    "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
    "requires": ["review"],
    "when": {"==": [{"var": "review.outcome"}, "approve"]},
}


def refund_with_plan(**settle: Any) -> dict[str, Any]:
    """The quickstart's refund, `pay` replaced by the guide's plan step, with `settle` changed."""
    definition = copy.deepcopy(REFUND)
    del definition["steps"]["pay"], definition["sequence"]
    definition["steps"]["settle"] = {**copy.deepcopy(SETTLE), **settle}
    return definition


def test_a_plan_step_is_read_with_its_shape_checked() -> None:
    # The plan carries its own approvals, checked when it is read (layer 3): no second kind here.
    approval = {"roles": ["support-lead"], "display": {"reason": "Refunds need a team lead"}}
    with pytest.raises(
        CaseInvalid,
        match="^steps.settle: a plan step has no approval: its plan asks for its own$",
    ):
        parse_case(refund_with_plan(approval=approval))
    unnamed = refund_with_plan()
    del unnamed["steps"]["settle"]["plan"]
    with pytest.raises(CaseInvalid, match="^steps.settle.plan: required$"):
        parse_case(unnamed)
    with pytest.raises(
        CaseInvalid,
        match='^steps.settle.plan: a plan reference looks like "refund-order@1"$',
    ):
        parse_case(refund_with_plan(plan="refund-order"))
    assert "settle" in parse_case(refund_with_plan()).steps


def test_a_plan_the_deployment_lacks_fails_the_step() -> None:
    # Fail closed: a plan nobody supplied never runs as something else; a person looks at it.
    run = run_case(refund_with_plan(), file=LARGE, answers=[REVIEWED], people=PEOPLE, plans={})
    assert run.needs_attention == ["settle#1: no plan refund-order@1 is available"]
    assert not run.closed


def test_a_plan_that_stops_fails_the_step() -> None:
    # The plan pays straight after its lookup: no approval, so the engine stops it before the
    # refund, and the case's step fails, waiting for a person (brief, D17).
    unapproved = refund_order()
    unapproved["states"]["check_order"]["on"]["done"] = "pay"
    run = run_case(
        refund_with_plan(),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        plans={"refund-order@1": unapproved},
    )
    assert run.needs_attention == [
        (
            "settle#1: refund-order@1 stopped: payments.refund@2 is high risk, and nobody "
            "approved this run of pay"
        )
    ]
    assert not run.closed


def proposed_settle() -> dict[str, Any]:
    """The refund with the plan step, which a team lead proposes; it stays open until closed."""
    definition = refund_with_plan(automatic=False, proposed_by=["support-lead"])
    reason = {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    return definition | {"stays_open": True, "close_reasons": {"duplicate": reason}}


def test_who_may_not_approve_crosses_into_the_plan() -> None:
    # Sam proposes settling the refund; nothing he gave flows into it (Ana's review set the
    # amount), so only D25's rule keeps him from approving his own proposal inside the plan. A
    # plan step is no way around it: his approval is refused, and nothing is paid.
    paid: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paid.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    def settled(approver: str, opened_by: str | None = None) -> bool:
        paid.clear()
        run = run_case(
            proposed_settle(),
            file=LARGE,
            answers=[REVIEWED, propose("settle", "sam")],
            people=PEOPLE,
            opened_by=opened_by,
            activities={"payments.refund@2": refund},
            plans={"refund-order@1": refund_order()},
            plan_answers={"settle": [("approve_refund", "approve", approver)]},
        )
        return run.reached("settle") and paid == ["memory/settle#1/pay#1"]

    assert not settled("sam")
    assert paid == []
    assert settled("lee")  # someone else approves it
    # The opener too (brief, D25): Lee opened the case, so Lee approves nothing in it.
    assert not settled("lee", opened_by="lee")
