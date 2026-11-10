# Shows whether a person whose answer decides that a step runs, through a milestone the step requires, may approve that step: by an outcome's `reaches`, and by a rule that reaches on their answer (brief, D11, D39).
# Run: uv run python reviews/2026-11/probes/p1b_milestone_route_around_someone_else.py
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

def routed(how: str) -> dict[str, Any]:
    case = refund()
    case["steps"]["review"]["outcomes"]["approve"] = {"display": T("Approve")}
    case["steps"]["pay"]["inputs"]["amount"] = {"var": "amount"}  # the opener's, nobody's answer
    pay = case["steps"]["pay"]
    if how == "when":  # the control: pay's own `when` reads the answer
        return case
    del pay["when"]
    case["milestones"] = {"approved": {"display": T("Approved")}}
    if how == "outcome reaches":
        case["steps"]["review"]["outcomes"]["approve"]["reaches"] = ["approved"]
        pay["requires"] = ["approved"]
    elif how == "rule reaches":
        case["rules"] = {
            "mark": {
                "display": T("Mark approved"),
                "on": {"answered": "review"},
                "when": {"==": [{"var": "review.outcome"}, "approve"]},
                "then": {"reach": ["approved"]},
            }
        }
        pay["requires"] = ["approved"]
    elif how == "rule starts":  # the second control: the rule starts pay itself
        pay["automatic"] = False
        pay["requires"] = []
        case["rules"] = {
            "go": {
                "display": T("Start the payment"),
                "on": {"answered": "review"},
                "when": {"==": [{"var": "review.outcome"}, "approve"]},
                "then": {"start": ["pay"]},
            }
        }
    return case


SCRIPT = [("review", "approve", "sam"), ("pay", "approve", "sam")]
results = {}
for how in ("when", "rule starts", "outcome reaches", "rule reaches"):
    run = attempt(
        f"sam answers review `approve`, which alone decides that pay runs ({how}); sam approves pay",
        lambda how=how: run_case(routed(how), FILE, SCRIPT, PEOPLE),
    )
    results[how] = run is not None and run.reached("pay")
# In each variant a `reject` pays nothing: sam's answer is what decides.
for how in ("outcome reaches", "rule reaches"):
    rejected = run_case(routed(how), FILE, [("review", "reject", "sam")], PEOPLE)
    print(f"  ({how}) had sam answered `reject`: pay reached = {rejected.reached('pay')}, waiting = {rejected.waiting_for}")
if not results["when"] and not results["rule starts"] and (results["outcome reaches"] or results["rule reaches"]):
    routes = [how for how in ("outcome reaches", "rule reaches") if results[how]]
    print(
        "RESULT: BROKEN - sam is refused when pay's `when`, or a rule that starts pay, reads the "
        f"answer, and approves the payment sam's own answer released when the route is: {', '.join(routes)}"
    )
else:
    print("RESULT: HELD - whoever's answer reaches the milestone a step requires does not approve it")
