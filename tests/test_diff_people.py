"""The semantic diff, layer 13b: guards on people and runs (brief, D55, as amended in 13b).

Approvals, requirements and conditions, who proposes, answers, sends and closes, freshness,
forgetting, and a plan's approval and wait states. Each judged comparison has a witness, a run
where one version refuses what the other lets through.
See docs/layers/13-diff.md (13b) and docs/guides/releases.md, "What changed: the diff".
"""

import json
from collections.abc import Callable
from typing import Any

from test_diff import ROOT, Definition, lines, packed, refund, witnessed

from ventoux.case.diff import diff
from ventoux.case.memory import CaseRun
from ventoux.core.catalog import Catalog
from ventoux.testing import CATALOG, run_case

FOUR_EYES = ROOT / "examples" / "refund" / "refund-four-eyes.json"

PEOPLE = {"ana": ["support"], "sam": ["support-lead"], "lee": ["support-lead"]}

type Witness = tuple[Definition, Definition, Catalog, bool, bool]


def four_eyes() -> dict[str, Any]:
    """The four-eyes refund: a payment over 10,000 needs two team leads (brief, D47)."""
    data: dict[str, Any] = json.loads(FOUR_EYES.read_text())
    return data


def counting(count: int) -> dict[str, Any]:
    """The four-eyes refund, its payment approved by `count` team leads."""
    case = four_eyes()
    case["steps"]["pay"]["approval"]["count"] = count
    return case


def paid(case: dict[str, Any], amount: int, *answers: Any) -> CaseRun:
    """The refund reviewed, `amount` approved, then `answers`."""
    return run_case(
        case,
        file={"order_id": "ord-1", "amount": amount},
        answers=[("review", "approve", "ana", {"approved_amount": amount}), *answers],
        people=PEOPLE,
    )


# --- Slice 0: an approval, its count and its condition -------------------------------------------


def test_an_approvals_count_lowered_is_looser() -> None:
    # The curriculum's negative test for 13b: one character in the JSON, and one team lead pays
    # 20,000 where two had to (brief, D47).
    found = diff(packed(counting(2)), packed(counting(1)), CATALOG)
    assert lines(found) == [
        "looser     steps.pay.approval.count: 2 -> 1 (one person approves pay, where two had to)"
    ]
    assert found.changes[0].comparison == "approval count"


def test_an_approvals_count_raised_is_stricter() -> None:
    found = diff(packed(counting(2)), packed(counting(3)), CATALOG)
    assert lines(found) == [
        "stricter   steps.pay.approval.count: 2 -> 3 (three people approve pay, where two had to)"
    ]


def checking(approved: bool) -> dict[str, Any]:
    """A case looking an order up once support has reviewed it, the lookup approved by a team
    lead or not. A low-risk step: it may run with no approval. A team lead may also close the
    case, so removing the approval doesn't change who the case names."""
    lookup: dict[str, Any] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "requires": ["review"],
    }
    if approved:
        lookup["approval"] = {"roles": ["support-lead"], "display": {"reason": "A lead checks"}}
    return {
        "case": "checked",
        "display": {"title": "An order checked"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}}
        },
        "steps": {
            "review": {
                "kind": "task",
                "display": {"title": "Review it"},
                "roles": ["support"],
                "outcomes": {"done": {"display": {"title": "Done"}}},
            },
            "lookup": lookup,
        },
        "close_reasons": {
            "withdrawn": {"display": {"title": "Withdrawn"}, "roles": ["support-lead"]}
        },
    }


def test_an_approval_removed_is_looser() -> None:
    found = diff(packed(checking(True)), packed(checking(False)), CATALOG)
    assert lines(found) == [
        "looser     steps.lookup.approval: approved by support-lead -> approved by nobody"
    ]
    assert found.changes[0].comparison == "approval"


def test_an_approval_added_is_stricter() -> None:
    found = diff(packed(checking(False)), packed(checking(True)), CATALOG)
    assert lines(found) == [
        "stricter   steps.lookup.approval: approved by nobody -> approved by support-lead"
    ]


def test_a_high_risk_steps_approval_removed_is_not_proven() -> None:
    # A high-risk step with no approval never runs: the runtime refuses it (brief, D11). So
    # removing its approval lets nothing more through, and "looser" would be a false claim.
    after = refund()
    del after["steps"]["pay"]["approval"]
    found = diff(packed(refund()), packed(after), CATALOG)
    assert (
        "not proven steps.pay.approval: approved by support-lead -> approved by nobody "
        "(payments.refund@2 is high risk: without an approval, pay never runs)"
    ) in lines(found)
    assert all(c.comparison != "approval" for c in found.changes)


def always_asked() -> dict[str, Any]:
    """The refund, its payment's approval asked on every run."""
    case = refund()
    del case["steps"]["pay"]["approval"]["when"]
    return case


def test_an_approvals_condition_added_is_looser() -> None:
    # Its condition isn't compared, its presence is: asked on no more runs than before, and on
    # fewer wherever it is false (choice 19).
    found = diff(packed(always_asked()), packed(refund()), CATALOG)
    assert lines(found) == [
        (
            "looser     steps.pay.approval.when: asked on every run -> asked only if "
            "approved_amount > 100 (on no more runs, and on fewer wherever that is false)"
        )
    ]
    assert found.changes[0].comparison == "approval condition"


def test_an_approvals_condition_removed_is_stricter() -> None:
    found = diff(packed(refund()), packed(always_asked()), CATALOG)
    assert lines(found) == [
        (
            "stricter   steps.pay.approval.when: asked only if approved_amount > 100 -> asked on "
            "every run"
        )
    ]


def test_an_approvals_condition_changed_is_not_proven() -> None:
    after = refund()
    after["steps"]["pay"]["approval"]["when"] = {">": [{"var": "approved_amount"}, 150]}
    found = diff(packed(refund()), packed(after), CATALOG)
    assert lines(found) == [
        "not proven steps.pay.approval.when: approved_amount > 100 -> approved_amount > 150"
    ]


# --- Witnesses -----------------------------------------------------------------------------------


def waits_for_approval(run: CaseRun, waiting: str = "approval of pay by support-lead") -> bool:
    """Whether the payment hasn't run, waiting for its approval."""
    return not run.reached("pay") and run.waiting_for == [waiting]


def count_witness() -> Witness:
    """With two to approve, one team lead's approval leaves 20,000 waiting; with one, it pays."""
    approved = ("pay.approval#1", "approve", "sam")
    refused = waits_for_approval(
        paid(counting(2), 20000, approved), "approval of pay by support-lead: 1 of 2 given"
    )
    return (
        counting(2),
        counting(1),
        CATALOG,
        refused,
        paid(counting(1), 20000, approved).reached("pay"),
    )


def checked(case: dict[str, Any], *answers: Any) -> CaseRun:
    """The order reviewed, then `answers`."""
    return run_case(
        case,
        file={"order_id": "ord-1"},
        answers=[("review", "done", "ana"), *answers],
        people=PEOPLE,
    )


def approval_witness() -> Witness:
    """The lookup waits for a team lead; with no approval, it runs."""
    old = checked(checking(True))
    refused = not old.reached("lookup") and old.waiting_for == [
        "approval of lookup by support-lead"
    ]
    taken = checked(checking(False)).reached("lookup")
    return checking(True), checking(False), CATALOG, refused, taken


def condition_witness() -> Witness:
    """50 waits for a team lead while every run is asked; asked only over 100, it pays."""
    refused = waits_for_approval(paid(always_asked(), 50))
    return always_asked(), refund(), CATALOG, refused, paid(refund(), 50).reached("pay")


# Each of 13b's comparisons, and its witness, in the order of COMPARISONS.
WITNESSES: dict[str, Callable[[], Witness]] = {
    "approval": approval_witness,
    "approval condition": condition_witness,
    "approval count": count_witness,
}


def test_each_comparison_has_a_witness() -> None:
    for comparison, witness in WITNESSES.items():
        witnessed(comparison, *witness())
