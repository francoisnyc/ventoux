# Shows whether the person whose answer a step's `when` read is still excluded when that step is a plan step or a case step, inside the plan or the child (brief, D11, D25, D28, D74).
# Run: uv run python reviews/2026-11/probes/p1b_when_decider_crosses_into_plan_and_child.py
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

PLAN = {
    "plan": "refund-order",
    "version": 1,
    "display": T("Refund an order"),
    "fields": {"order_id": {"type": "reference", "system": "orders"}, "amount": {"type": "number"}},
    "initial": "approve_refund",
    "states": {
        "approve_refund": {
            "approval": {"of": "pay", "roles": ["support-lead"]},
            "on": {"approve": "pay", "reject": "failed"},
        },
        "pay": {
            "activity": "payments.refund@2",
            "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
            "on": {"done": "paid", "declined": "failed"},
        },
        "paid": {"final": "succeeded"},
        "failed": {"final": "failed"},
    },
}
CHILD = {
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
WHEN = {"==": [{"var": "review.outcome"}, "approve"]}


def base() -> dict[str, Any]:
    case = refund()
    case["steps"]["review"]["outcomes"]["approve"] = {"display": T("Approve")}
    return case


call = base()
call["steps"]["pay"]["inputs"]["amount"] = {"var": "amount"}
plan = base()
del plan["steps"]["pay"]
plan["steps"]["settle"] = {
    "kind": "plan", "display": T("Settle"), "plan": "refund-order@1", "requires": ["review"], "when": WHEN,
    "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
}
child = base()
del child["steps"]["pay"]
child["steps"]["repair"] = {
    "kind": "case", "display": T("Repair"), "case": "repair@3", "requires": ["review"], "when": WHEN,
    "inputs": {"order_id": {"var": "order_id"}, "budget": {"var": "amount"}},
}
REVIEW = ("review", "approve", "sam")
a = attempt("Control, a call step: sam's answer is read by pay's `when`; sam approves pay",
            lambda: run_case(call, FILE, [REVIEW, ("pay", "approve", "sam")], PEOPLE))
b = attempt("A plan step with the same `when`: sam approves the payment inside the plan",
            lambda: run_case(plan, FILE, [REVIEW], PEOPLE, plans={"refund-order@1": PLAN},
                             plan_answers={"settle": [("approve_refund", "approve", "sam")]}))
c = attempt("A case step with the same `when`: sam approves the payment inside the child",
            lambda: run_case(child, FILE, [REVIEW], PEOPLE, cases={"repair@3": CHILD},
                             case_answers={"repair": [("parts", "approve", "sam")]}))
paid_in_plan = b is not None and b.reached("settle")
paid_in_child = c is not None and c.children["repair#1"].reached("parts")
if c is not None:
    tail(c.children["repair#1"], 3)
if a is None and (paid_in_plan or paid_in_child):
    where = [w for w, yes in (("a plan step", paid_in_plan), ("a case step", paid_in_child)) if yes]
    print(
        "RESULT: BROKEN - sam, whose answer decided that the payment runs, may not approve it as a "
        f"call step, and approves it once it is wrapped in {' or '.join(where)}"
    )
else:
    print("RESULT: HELD - whoever a step's `when` read approves nothing inside its plan or child")
