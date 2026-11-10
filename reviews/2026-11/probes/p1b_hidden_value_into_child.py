# Shows whether a value hidden by `visible_to` in a parent stays hidden once it is given to a child case's opening field, or reported back from a child's hidden field (brief, D30, D42, D74; CLAUDE.md "a view hiding more than its source").
# Run: uv run python reviews/2026-11/probes/p1b_hidden_value_into_child.py
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

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case


def repair() -> dict[str, Any]:
    return {
        "case": "repair",
        "display": T("Repair"),
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": T("Order")},
            "score": {"type": "number", "display": T("Score given by the parent")},
            "margin": {"type": "number", "display": T("Our margin"), "visible_to": ["fraud"]},
        },
        "steps": {
            "price": {
                "kind": "task",
                "display": T("Price"),
                "roles": ["fraud"],
                "outcomes": {"priced": {"display": T("Priced"), "sets": ["margin"]}},
            },
            "look": {
                "kind": "task",
                "display": T("Look"),
                "roles": ["support"],
                "outcomes": {"ok": {"display": T("OK")}},
            },
        },
        "reports": ["margin"],
    }


def claim() -> dict[str, Any]:
    case = refund()
    del case["steps"]["pay"]
    case["fields"]["fraud_score"] = {"type": "number", "display": T("Fraud score"), "visible_to": ["fraud"]}
    case["steps"]["screen"] = {
        "kind": "task",
        "display": T("Screen"),
        "roles": ["fraud"],
        "requires": ["repair"],
        "outcomes": {"ok": {"display": T("OK")}},
    }
    case["steps"]["repair"] = {
        "kind": "case",
        "display": T("Repair"),
        "case": "repair@3",
        "requires": ["review"],
        "inputs": {"order_id": {"var": "order_id"}, "score": {"var": "fraud_score"}},
    }
    return case


# Control: inside one case, copying a hidden field into an open one is refused when read.
copied = claim()
copied["fields"]["flag"] = {"type": "number", "display": T("Flag")}
copied["rules"] = {"copy": {"display": T("Copy"), "on": "opened", "then": {"set": {"flag": {"var": "fraud_score"}}}}}
control = attempt("Control: a rule sets an open field from fraud_score (seen only by fraud)", lambda: parse_case(copied))
issues = validate_case(parse_case(claim()), CATALOG, None, {"repair@3": repair()})
about = [f"{i.code}: {i.message[:110]}" for i in issues if "fraud_score" in i.message or "margin" in i.message or "visible" in i.message]
print("Attack: the same value given to the child's open field `score`. Validation says of it:", about or "nothing")
run = run_case(
    claim(),
    FILE | {"fraud_score": 77},
    [("review", "approve", "ana", {"approved_amount": 900})],
    PEOPLE,
    cases={"repair@3": repair()},
    case_answers={"repair": [("price", "priced", "fay", {"margin": 41}), ("look", "ok", "ana")]},
)
child = run.children["repair#1"]
parent_view, child_view = run.view(["support"]), child.view(["support"])
print("  parent, as support sees it:", [line for line in parent_view.lines if "score" in line.lower()])
print("  child, as support sees it: ", [line for line in child_view.lines if "score" in line.lower()])
print("  child, as support sees it: ", [line for line in child_view.lines if "margin" in line.lower()])
print("  parent's values for support include repair.margin:", parent_view.values.get("repair.margin"))
broken = []
if "fraud_score" not in parent_view.values and child_view.values.get("score") == 77:
    broken.append("support, who may not see fraud_score, reads its value 77 as the child's `score`")
if "margin" not in child_view.values and parent_view.values.get("repair.margin") == 41:
    broken.append("support, who may not see the child's margin, reads 41 as the parent's repair.margin")
if control is None and broken and not about:
    print("RESULT: BROKEN - " + "; ".join(broken) + "; validation says nothing")
else:
    print("RESULT: HELD - a hidden value stays hidden across a child case")
