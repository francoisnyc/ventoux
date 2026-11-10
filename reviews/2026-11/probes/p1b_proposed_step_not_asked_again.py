# Shows what happens to a person's proposal when the approval it waits for is withdrawn by an edit: whether it is "asked again" (brief, D25, D52), and whether the history says what became of the proposal.
# Run: uv run python reviews/2026-11/probes/p1b_proposed_step_not_asked_again.py
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

from ventoux.testing import edit, propose

REVIEWED = ("review", "approve", "ana", {"approved_amount": 900})
EDITED = [edit("approved_amount", 5, "lee"), ("case.change#1", "approve", "sam")]
by_itself = refund()
proposed = refund()
proposed["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support-lead"]}
proposed |= {"stays_open": True, "close_reasons": {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}}}
auto = run_case(by_itself, FILE, [REVIEWED, *EDITED], PEOPLE)
print("Control: pay starts by itself; its open approval saw the old amount; an edit is applied:")
tail(auto, 3)
asked = run_case(proposed, FILE, [REVIEWED, propose("pay", "kim"), *EDITED], PEOPLE)
print("The same, where kim proposed pay:")
tail(asked, 4)
print("  waiting_for:", asked.waiting_for, "| needs_attention:", asked.needs_attention, "| status:", asked.status)
print("  the case still keeps kim as pay's proposer:", asked.state.proposers)
again = any(line.startswith("asked pay.approval#2") for line in asked.history)
told = any("propos" in line and "kim" not in line.split(" proposed ")[0] and ("over" in line or "dropped" in line or "again" in line) for line in asked.history[-3:])
if any(line.startswith("asked pay.approval#2") for line in auto.history) and not again and not told:
    print(
        "RESULT: BROKEN - (misleads) the edit withdrew the approval kim's proposal waited for and "
        "nothing asks again, as D52 says each is; the case waits for nothing, and no line says the "
        "proposal is over or that pay must be proposed again"
    )
else:
    print("RESULT: HELD - the proposed step's approval is asked again, or the history says the proposal is over")
