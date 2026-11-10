# Shows whether a child case's reported field named `outcome` can replace `<step>.outcome` in the parent with a person's free text, and whether that text reaches the step advisor (brief, D74, D61).
# Run: uv run python reviews/2026-11/probes/p1b_child_report_named_outcome.py
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

from ventoux.authoring.advisor import shown_to_advisor
from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case

CANARY = "CANARY-typed-by-a-person"


def repair() -> dict[str, Any]:
    return {
        "case": "repair",
        "display": T("Repair"),
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": T("Order")},
            "outcome": {"type": "string", "display": T("Notes on how it went")},
        },
        "steps": {
            "fix": {
                "kind": "task",
                "display": T("Fix"),
                "roles": ["support"],
                "outcomes": {"fixed": {"display": T("Fixed"), "sets": ["outcome"]}},
            },
        },
        "reports": ["outcome"],
        "close_reasons": {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}},
    }


def claim() -> dict[str, Any]:
    case = refund()
    case["steps"]["repair"] = {
        "kind": "case",
        "display": T("Repair"),
        "case": "repair@3",
        "requires": ["review"],
        "inputs": {"order_id": {"var": "order_id"}},
    }
    # The payment runs only if the repair closed by itself, never if a person closed it.
    case["steps"]["pay"]["requires"] = ["repair"]
    case["steps"]["pay"]["when"] = {"==": [{"var": "repair.outcome"}, "done"]}
    case["steps"]["note"] = {
        "kind": "task",
        "display": T("Note"),
        "roles": ["support"],
        "requires": ["repair"],
        "outcomes": {"noted": {"display": T("Noted")}},
    }
    return case


broken = []
try:
    issues = validate_case(parse_case(claim()), CATALOG, None, {"repair@3": repair()})
    said = [f"{issue.code}: {issue.message[:90]}" for issue in issues]
    print("validation of the parent with this child says:", said or "nothing")
    if not any("outcome" in issue.message and "repair" in issue.message and issue.code != "OUTCOME_UNREAD" for issue in issues):
        broken.append("validation accepts a child that reports a field named outcome")
except Exception as refused:  # noqa: BLE001
    print("the definition is refused:", str(refused)[:200])
run = attempt(
    "the child's task sets its field `outcome` to free text, and the child closes by itself",
    lambda: run_case(
        claim(),
        FILE,
        [("review", "approve", "ana", {"approved_amount": 900})],
        PEOPLE,
        cases={"repair@3": repair()},
        case_answers={"repair": [("fix", "fixed", "sam", {"outcome": CANARY})]},
    ),
)
if run is not None:
    tail(run, 4)
    held = run.state.values.get("repair.outcome")
    print("  the child's own ending:", run.children["repair#1"].history[-1])
    print("  repair.outcome in the parent is the canary:", held == CANARY)
    print("  its sources:", sorted(run.state.sources.get("repair.outcome", ())))
    print("  pay (when repair.outcome == 'done') waits or ran:", run.waiting_for, run.reached("pay"))
    if held == CANARY:
        broken.append("repair.outcome holds the field's text, not `done`, so pay never starts")
    shown = shown_to_advisor(run.definition, CATALOG, run.state, "ana", frozenset(["support"]), START)
    request = shown.request.messages[0].content
    print("  the request the step advisor's model would read holds the canary:", CANARY in request)
    if CANARY in request:
        broken.append("the step advisor is sent the person's text as the run's outcome")
if broken:
    print("RESULT: BROKEN - " + "; ".join(broken))
else:
    print("RESULT: HELD - a reported field never replaces the step's outcome")
