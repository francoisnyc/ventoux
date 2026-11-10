# Shows whether the person whose answer to a plan step's wait decides the plan's outcome may approve the case step whose `when` reads that outcome (brief, D11, D28).
# Run: uv run python reviews/2026-11/probes/p1b_plan_wait_answerer_approves.py
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

TRIAGE = {
    "plan": "triage",
    "version": 1,
    "display": T("Triage"),
    "fields": {"order_id": {"type": "reference", "system": "orders"}},
    "initial": "decide",
    "states": {
        "decide": {
            "wait": {"outcomes": ["yes", "no"], "roles": ["support"]},
            "on": {"yes": "ok", "no": "bad"},
        },
        "ok": {"final": "succeeded"},
        "bad": {"final": "failed"},
    },
}


def with_plan() -> dict[str, Any]:
    case = refund()
    del case["steps"]["review"]
    case["steps"]["triage"] = {
        "kind": "plan",
        "display": T("Triage"),
        "plan": "triage@1",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    case["steps"]["pay"]["inputs"]["amount"] = {"var": "amount"}
    case["steps"]["pay"]["requires"] = ["triage"]
    case["steps"]["pay"]["when"] = {"==": [{"var": "triage.outcome"}, "done"]}
    return case


def with_task() -> dict[str, Any]:
    case = refund()
    case["steps"]["review"]["outcomes"]["approve"] = {"display": T("Approve")}
    case["steps"]["pay"]["inputs"]["amount"] = {"var": "amount"}
    return case


print("Control: the same decision as a task of the case. sam answers it, then approves pay.")
control = attempt(
    "  task `review` answered by sam, pay approved by sam",
    lambda: run_case(with_task(), FILE, [("review", "approve", "sam"), ("pay", "approve", "sam")], PEOPLE),
)
print("Attack: the decision is a wait inside a plan step. sam answers it, then approves pay.")
attack = attempt(
    "  plan wait `decide` answered by sam, pay approved by sam",
    lambda: run_case(
        with_plan(),
        FILE,
        [("pay", "approve", "sam")],
        PEOPLE,
        plans={"triage@1": TRIAGE},
        plan_answers={"triage": [("decide", "yes", "sam")]},
    ),
)
if attack is not None:
    tail(attack, 7)
    print("  sources of triage.outcome:", sorted(attack.state.sources["triage.outcome"]))
if control is None and attack is not None and attack.reached("pay"):
    print(
        "RESULT: BROKEN - sam's answer inside the plan decided that pay runs (pay's `when` reads "
        "triage.outcome), and sam approved pay: the outcome carries only system:triage@1"
    )
else:
    print("RESULT: HELD - the plan wait's answerer could not approve the step its answer decided")
