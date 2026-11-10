# Shows whether the parent's opener, or the proposer of the case step, may approve a change request (an edit, a skip) inside the child case (brief, D52, D74).
# Run: uv run python reviews/2026-11/probes/p1b_child_change_request_by_parents_opener.py
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

from ventoux.testing import edit, propose, skip


def repair() -> dict[str, Any]:
    return {
        "case": "repair",
        "display": T("Repair"),
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": T("Order")},
            "budget": {"type": "number", "display": T("Budget")},
            "cost": {"type": "number", "display": T("Cost")},
            "email": {"type": "string", "display": T("Email")},
        },
        "steps": {
            "fix": {
                "kind": "task",
                "display": T("Fix"),
                "roles": ["support"],
                "outcomes": {"fixed": {"display": T("Fixed"), "sets": ["cost", "email"]}},
            },
            "tell": {
                "kind": "activity",
                "display": T("Draft a letter"),
                "activity": "letters.draft@2",
                "inputs": {"to_customer": {"var": "email"}, "template": "repaired"},
                "requires": ["fix"],
            },
            "check": {
                "kind": "task",
                "display": T("Check"),
                "roles": ["support", "support-lead"],
                "requires": ["fix"],
                "outcomes": {"ok": {"display": T("OK")}},
            },
        },
        "reports": ["cost"],
    }


def claim(proposed: bool) -> dict[str, Any]:
    case = refund()
    del case["steps"]["pay"]
    case["steps"]["repair"] = {
        "kind": "case",
        "display": T("Repair"),
        "case": "repair@3",
        "requires": ["review"],
        "inputs": {"order_id": {"var": "order_id"}, "budget": {"var": "approved_amount"}},
    }
    if proposed:
        case["steps"]["repair"] |= {"automatic": False, "proposed_by": ["support-lead", "operations"]}
        case["stays_open"] = True
        case["close_reasons"] = {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}}
    return case


REVIEWED = ("review", "approve", "ana", {"approved_amount": 900})
FIXED = ("fix", "fixed", "ana", {"cost": 600, "email": "a@example.com"})


def play(child_script: list[Any], opened_by: str | None, proposer: str | None, **more: Any) -> Any:
    answers: list[Any] = [REVIEWED] + ([propose("repair", proposer)] if proposer else [])
    return run_case(
        claim(proposer is not None),
        FILE,
        answers,
        PEOPLE,
        opened_by=opened_by,
        cases={"repair@3": repair()},
        case_answers={"repair": child_script},
        **more,
    )


print("Control, in one case: its opener approves an edit, and a skip.")
solo = refund()
c1 = attempt(
    "  lee opened the refund; kim proposes an edit, lee approves it",
    lambda: run_case(solo, FILE, [REVIEWED, edit("approved_amount", 5, "kim"), ("case.change#1", "approve", "lee")], PEOPLE, opened_by="lee"),
)
print("Attack, in the child: the same people, where the parent's exclusions should cross.")
broken = []
a1 = attempt(
    "  lee opened the PARENT; in the child kim proposes an edit of cost, lee approves it",
    lambda: play([FIXED, edit("cost", 700, "kim"), ("case.change#1", "approve", "lee")], "lee", None),
)
a2 = attempt(
    "  olga opened the PARENT; in the child tell#1 failed, omar proposes its skip, olga approves it",
    lambda: play([FIXED, skip("tell#1", "omar"), ("case.change#1", "approve", "olga")], "olga", None, activities={"letters.draft@2": down}),
)
a3 = attempt(
    "  kim PROPOSED the case step; in the child lee proposes an edit of cost, kim approves it",
    lambda: play([FIXED, edit("cost", 700, "lee"), ("case.change#1", "approve", "kim")], None, "kim"),
)
a4 = attempt(
    "  olga PROPOSED the case step; in the child tell#1 failed, omar proposes its skip, olga approves it",
    lambda: play([FIXED, skip("tell#1", "omar"), ("case.change#1", "approve", "olga")], None, "olga", activities={"letters.draft@2": down}),
)
for label, run in (("edit by parent's opener", a1), ("skip by parent's opener", a2), ("edit by step's proposer", a3), ("skip by step's proposer", a4)):
    if run is not None and any(line.startswith("applied case.change#1") for line in run.children["repair#1"].history):
        broken.append(label)
        tail(run.children["repair#1"], 3)
if c1 is None and broken:
    print(f"RESULT: BROKEN - approved and applied inside the child: {'; '.join(broken)}")
else:
    print("RESULT: HELD - the parent's opener and the step's proposer approved no change in the child")
