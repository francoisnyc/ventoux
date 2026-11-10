# Shows whether a child case's failed run (a payment that may or may not have happened) still waits for a person when its parent closes by itself (`closes_when`) or a parent's rule stops the case step (brief, D17, D34, D40, D74).
# Run: uv run python reviews/2026-11/probes/p1b_parent_auto_close_cancels_childs_failed_run.py
import copy
import json
from typing import Any

from ventoux.testing import CATALOG, START, run_case

# Fictional people and their roles, as the trusted caller would state them (brief, D22).
PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "kim": ["support-lead"],
    "omar": ["operations"],
    "olga": ["operations"],
    "pia": ["platform"],
    "pat": ["platform"],
    "fay": ["fraud", "support-lead"],
}
FILE = {"order_id": "ord-1", "amount": 250}


def T(title: str) -> dict[str, str]:
    return {"title": title}


def refund() -> dict[str, Any]:
    """A small refund: a review that sets the amount, then a high-risk payment a lead approves."""
    return copy.deepcopy(
        {
            "case": "refund",
            "display": T("Refund"),
            "fields": {
                "order_id": {"type": "reference", "system": "orders", "display": T("Order")},
                "amount": {"type": "number", "display": T("Amount")},
                "approved_amount": {"type": "number", "display": T("Approved")},
            },
            "steps": {
                "review": {
                    "kind": "task",
                    "display": T("Review"),
                    "roles": ["support"],
                    "outcomes": {
                        "approve": {"display": T("Approve"), "sets": ["approved_amount"]},
                        "reject": {"display": T("Reject")},
                    },
                },
                "pay": {
                    "kind": "activity",
                    "display": T("Pay"),
                    "activity": "payments.refund@2",
                    "inputs": {
                        "order_id": {"var": "order_id"},
                        "amount": {"var": "approved_amount"},
                    },
                    "requires": ["review"],
                    "when": {"==": [{"var": "review.outcome"}, "approve"]},
                    "approval": {"roles": ["support-lead"], "display": {"reason": "A lead"}},
                },
            },
        }
    )


def attempt(label: str, play: Any) -> Any:
    """Play a script; say whether the engine took it or refused it, and return the run or None."""
    try:
        run = play()
    except Exception as refused:  # noqa: BLE001 (a probe reports every refusal)
        print(f"{label}\n    -> REFUSED ({type(refused).__name__}): {str(refused)[:260]}")
        return None
    print(f"{label}\n    -> ACCEPTED")
    return run


def tail(run: Any, lines: int = 6) -> None:
    for line in run.history[-lines:]:
        print(f"       | {line}")


def down(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("provider unreachable")


_ = (CATALOG, START, json, run_case)  # used by some probes only

from ventoux.testing import send


def repair() -> dict[str, Any]:
    return {
        "case": "repair",
        "display": T("Repair"),
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": T("Order")},
            "budget": {"type": "number", "display": T("Budget")},
        },
        "steps": {
            "parts": {
                "kind": "activity",
                "display": T("Pay for parts"),
                "activity": "payments.refund@2",
                "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "budget"}},
                "approval": {"roles": ["support-lead"], "display": {"reason": "A lead"}},
            },
        },
    }


def claim() -> dict[str, Any]:
    case = refund()
    del case["steps"]["pay"]
    case["milestones"] = {"reviewed": {"display": T("Reviewed")}}
    case["steps"]["review"]["reaches"] = ["reviewed"]
    case["steps"]["repair"] = {
        "kind": "case",
        "display": T("Repair"),
        "case": "repair@3",
        "inputs": {"order_id": {"var": "order_id"}, "budget": {"var": "amount"}},
    }
    return case


REVIEWED = ("review", "approve", "ana", {"approved_amount": 900})
CHILD = {"repair": [("parts", "approve", "lee")]}

# Control: in ONE case, `closes_when` waits for a failed run.
solo = refund()
solo["milestones"] = {"reviewed": {"display": T("Reviewed")}}
solo["closes_when"] = ["reviewed"]
solo["steps"]["review"]["reaches"] = ["reviewed"]
solo["steps"]["pay"] = {
    "kind": "activity",
    "display": T("Pay"),
    "activity": "payments.refund@2",
    "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
    "approval": {"roles": ["support-lead"], "display": {"reason": "A lead"}},
}
one = run_case(solo, FILE, [("pay", "approve", "lee"), REVIEWED], PEOPLE, activities={"payments.refund@2": down})
print("Control, one case: pay#1 failed, then `reviewed` (closes_when) is reached:")
print("    status:", one.status, "| needs attention:", one.needs_attention)

by_itself = claim()
by_itself["closes_when"] = ["reviewed"]
auto = run_case(by_itself, FILE, [REVIEWED], PEOPLE, cases={"repair@3": repair()}, case_answers=CHILD, activities={"payments.refund@2": down})
print("Attack 1: the failed payment is in the child; the parent reaches `reviewed` (closes_when):")
tail(auto, 3)
tail(auto.children["repair#1"], 4)

by_rule = claim()
by_rule["events"] = {"cancelled": {"display": T("Cancelled"), "sent_by": {"system": "portal"}, "payload": {}}}
by_rule["rules"] = {"withdraw": {"display": T("Withdraw"), "on": {"event": "cancelled"}, "then": {"stop": ["repair"]}}}
ruled = run_case(by_rule, FILE, [send("cancelled", {}, "system:portal")], PEOPLE, cases={"repair@3": repair()}, case_answers=CHILD, activities={"payments.refund@2": down})
print("Attack 2: a parent's rule stops the case step when the portal's event arrives:")
tail(ruled, 3)
tail(ruled.children["repair#1"], 3)

broken = []
for label, run in (("the parent's closes_when", auto), ("a parent's rule's stop", ruled)):
    child = run.children["repair#1"]
    if child.closed and any(line.startswith("cancelled parts#1") for line in child.history) and not child.needs_attention:
        flags = run.flags + child.flags
        broken.append(f"{label} cancelled the child's failed parts#1 with no person (flags: {flags or 'none'})")
if one.status != "closed" and one.needs_attention and broken:
    print("RESULT: BROKEN - " + "; ".join(broken))
else:
    print("RESULT: HELD - a child's failed run waits for a person whatever its parent does by itself")
