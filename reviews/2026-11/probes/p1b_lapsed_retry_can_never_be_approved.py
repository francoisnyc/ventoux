# Shows what a failed run's retry does once a task answered again changed the run's inputs: it stops saying "a new approval is needed", and whether anything can then ask for that approval (brief, D23, D25, D26).
# Run: uv run python reviews/2026-11/probes/p1b_lapsed_retry_can_never_be_approved.py
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

from ventoux.testing import propose, retry

calls: list[Any] = []


def down_once(inputs: dict[str, Any]) -> dict[str, Any]:
    calls.append(inputs["amount"])
    if len(calls) == 1:
        raise ConnectionError("down")
    return {"refund_id": "r-1"}


case = refund()
case["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
script = [
    ("review", "approve", "ana", {"approved_amount": 900}),
    ("pay", "approve", "kim"),  # kim approves 900; pay#1 fails
    propose("review", "ana"),
    ("review#2", "approve", "ana", {"approved_amount": 5000}),  # reworked to 5000
    retry("pay#1", "omar"),
    retry("pay#1", "omar"),
    retry("pay#1", "olga"),
]
run = run_case(case, FILE, script, PEOPLE, activities={"payments.refund@2": down_once})
tail(run, 7)
print("  amounts the provider was called with:", calls)
print("  waiting_for:", run.waiting_for, "| needs_attention:", run.needs_attention)
never_paid_5000 = calls == [900]
asked_again = any(line.startswith("asked pay.approval#2") for line in run.history)
if not never_paid_5000:
    print("RESULT: BROKEN - the retry paid an amount kim never approved")
elif not asked_again:
    print(
        "RESULT: HELD - the retry never pays the 5000 kim did not see (D11, D23). Noted (minor): its "
        "reason says `a new approval is needed`, and no retry asks for one: every retry stops the "
        "same way, where the same change made by an edit asks again (D25 as amended by D52)"
    )
else:
    print("RESULT: HELD - the retry asked for a new approval")
