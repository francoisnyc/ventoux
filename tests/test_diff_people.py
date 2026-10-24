"""The semantic diff, layer 13b: guards on people and runs (brief, D55, as amended in 13b).

Approvals, requirements and conditions, who proposes, answers, sends and closes, freshness,
forgetting, and a plan's approval and wait states. Each judged comparison has a witness, a run
where one version refuses what the other lets through.
See docs/layers/13-diff.md (13b) and docs/guides/releases.md, "What changed: the diff".
"""

import copy
import json
from collections.abc import Callable
from typing import Any

from test_diff import (
    ROOT,
    Definition,
    lines,
    packed,
    refund,
    refund_contract,
    refund_input,
    witnessed,
)

from ventoux.case.admission import ProposalRefused
from ventoux.case.answers import AnswerRefused
from ventoux.case.closing import CloseRefused
from ventoux.case.diff import diff
from ventoux.case.memory import CaseRun
from ventoux.case.runtime import EventRefused
from ventoux.core.catalog import Catalog
from ventoux.core.policy import trusted_only
from ventoux.testing import CATALOG, close, propose, run_case, send

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


# --- Slice 1: roles, as the catalog registers them -----------------------------------------------


def roled(**changes: list[str]) -> dict[str, Any]:
    """The refund with every kind of role list: a close reason and an event sent by support, and
    `recheck`, a task proposed by support; `changes` replaces lists by kind (`answers`, `proposes`,
    `sends`, `closes`, `approves`)."""
    case = refund()
    case["steps"]["review"]["roles"] = changes.get("answers", ["support"])
    case["steps"]["recheck"] = {
        "kind": "task",
        "display": {"title": "Review it again"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": changes.get("proposes", ["support"]),
        "outcomes": {"done": {"display": {"title": "Done"}}},
    }
    case["steps"]["pay"]["approval"]["roles"] = changes.get("approves", ["support-lead"])
    case["events"] = {
        "noted": {
            "display": {"title": "A note"},
            "sent_by": {"roles": changes.get("sends", ["support"])},
            "payload": {},
        }
    }
    case["close_reasons"] = {
        "duplicate": {
            "display": {"title": "A duplicate"},
            "roles": changes.get("closes", ["support"]),
        }
    }
    return case


def judged_lines(
    before: dict[str, Any], after: dict[str, Any], catalog: Catalog = CATALOG
) -> list[str]:
    """The changes from `before` to `after`, as printed."""
    return lines(diff(packed(before), packed(after), catalog))


def test_roles_widened_are_looser() -> None:
    # support-lead is named already (it approves pay), so who sees what doesn't change.
    both = ["support", "support-lead"]
    for kind, path in (
        ("answers", "steps.review.roles"),
        ("proposes", "steps.recheck.proposed_by"),
        ("sends", "events.noted.sent_by.roles"),
        ("closes", "close_reasons.duplicate.roles"),
    ):
        assert judged_lines(roled(), roled(**{kind: both})) == [
            f"looser     {path}: support -> support, support-lead"
        ], kind


def test_roles_narrowed_are_stricter() -> None:
    both = ["support", "support-lead"]
    assert judged_lines(roled(answers=both), roled()) == [
        "stricter   steps.review.roles: support, support-lead -> support"
    ]


def test_roles_replaced_are_not_proven() -> None:
    assert judged_lines(roled(closes=["support"]), roled(closes=["support-lead"])) == [
        "not proven close_reasons.duplicate.roles: support -> support-lead"
    ]


def test_a_role_nobody_registered_counts_for_nothing() -> None:
    # A role the catalog doesn't register gives nobody anything (brief, D22).
    found = judged_lines(roled(), roled(closes=["support", "auditor"]))
    assert (
        "not proven close_reasons.duplicate.roles: support -> support, auditor (auditor isn't "
        "registered: it gives nobody anything)"
    ) in found
    # Nor does it see anything: a field without visible_to is seen by the registered roles the
    # case names (fixed in 13b: 13a counted every name).
    assert not any("visible_to" in line for line in found)


def test_a_role_that_may_not_approve_the_risk_changes_no_approver() -> None:
    # support may approve no risk, and pay is high risk: adding it changes nobody (brief, D11).
    found = judged_lines(roled(), roled(approves=["support-lead", "support"]))
    assert found == [
        (
            "not proven steps.pay.approval.roles: support-lead -> support-lead, support (the same "
            "roles may approve payments.refund@2, high risk: support may not)"
        )
    ]


def with_clerks() -> Catalog:
    """The development catalog, with clerks who may approve up to medium risk, and a refund
    contract of medium risk."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register_role("clerk", approves="medium")
    catalog.register(refund_contract(8, refund_input(trusted_only()), risk="medium"))
    return catalog


def test_a_step_moved_to_a_lower_risk_gains_approvers() -> None:
    before = roled(approves=["support-lead", "clerk"])
    after = copy.deepcopy(before)
    after["steps"]["pay"]["activity"] = "payments.refund@8"
    found = judged_lines(before, after, with_clerks())
    assert (
        "looser     steps.pay.approval.roles: approved by support-lead -> approved by clerk or "
        "support-lead (because payments.refund@8 is medium risk)"
    ) in found
    assert (
        "stricter   steps.pay.approval.roles: approved by clerk or support-lead -> approved by "
        "support-lead (because payments.refund@2 is high risk)"
    ) in judged_lines(after, before, with_clerks())


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


def attempted(
    case: dict[str, Any], catalog: Catalog = CATALOG, *script: Any, reviewed: bool = True
) -> str | CaseRun:
    """The refund reviewed by Ana (250 approved), unless not `reviewed`, then `script`: the run,
    or why it was refused."""
    people = PEOPLE | {"fin": ["finance"]}
    review = [("review", "approve", "ana", {"approved_amount": 250})] if reviewed else []
    try:
        return run_case(
            case,
            file={"order_id": "ord-1", "amount": 250},
            answers=[*review, *script],
            people=people,
            catalog=catalog,
        )
    except (AnswerRefused, CloseRefused, EventRefused, ProposalRefused) as refused:
        return str(refused)


def with_finance() -> Catalog:
    """The development catalog, with a finance role that may approve high risk."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register_role("finance", approves="high")
    return catalog


def approvers_witness() -> Witness:
    """A finance approver is refused while only team leads approve pay, and pays once finance
    may. Finance may close the case in both, so who the case names doesn't change."""
    closes = ["support", "finance"]
    before = roled(closes=closes)
    after = roled(closes=closes, approves=["support-lead", "finance"])
    approval = ("pay.approval#1", "approve", "fin")
    old, new = (
        attempted(before, with_finance(), approval),
        attempted(after, with_finance(), approval),
    )
    refused = old == "pay.approval#1 is answered by support-lead, and fin has finance"
    return before, after, with_finance(), refused, isinstance(new, CaseRun) and new.reached("pay")


def answerers_witness() -> Witness:
    """A team lead may not review while support alone answers it; then may."""
    review = ("review", "approve", "sam", {"approved_amount": 250})
    before, after = roled(), roled(answers=["support", "support-lead"])
    old = attempted(before, CATALOG, review, reviewed=False)
    new = attempted(after, CATALOG, review, reviewed=False)
    refused = old == "review#1 is answered by support, and sam has support-lead"
    return before, after, CATALOG, refused, isinstance(new, CaseRun)


def proposers_witness() -> Witness:
    """A team lead may not propose a second review while support alone proposes it; then may."""
    before, after = roled(), roled(proposes=["support", "support-lead"])
    old = attempted(before, CATALOG, propose("recheck", "sam"))
    new = attempted(after, CATALOG, propose("recheck", "sam"))
    refused = old == "recheck is proposed by support, and sam has support-lead"
    taken = isinstance(new, CaseRun) and any("recheck#1" in line for line in new.history)
    return before, after, CATALOG, refused, taken


def senders_witness() -> Witness:
    """A team lead's note is refused while support alone sends it; then arrives."""
    before, after = roled(), roled(sends=["support", "support-lead"])
    old = attempted(before, CATALOG, send("noted", {}, "sam"))
    new = attempted(after, CATALOG, send("noted", {}, "sam"))
    refused = old == "noted is sent by support, and sam has support-lead"
    return before, after, CATALOG, refused, isinstance(new, CaseRun)


def closers_witness() -> Witness:
    """A team lead may not close the case as a duplicate while support alone may; then may."""
    before, after = roled(), roled(closes=["support", "support-lead"])
    old = attempted(before, CATALOG, close("duplicate", "sam"))
    new = attempted(after, CATALOG, close("duplicate", "sam"))
    refused = old == "duplicate is closed by support, and sam has support-lead"
    return before, after, CATALOG, refused, isinstance(new, CaseRun) and new.closed


# Each of 13b's comparisons, and its witness, in the order of COMPARISONS.
WITNESSES: dict[str, Callable[[], Witness]] = {
    "approval": approval_witness,
    "approval condition": condition_witness,
    "approval count": count_witness,
    "approvers": approvers_witness,
    "answerers": answerers_witness,
    "proposers": proposers_witness,
    "senders": senders_witness,
    "closers": closers_witness,
}


def test_each_comparison_has_a_witness() -> None:
    for comparison, witness in WITNESSES.items():
        witnessed(comparison, *witness())
