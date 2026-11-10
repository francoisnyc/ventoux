# Shows that an approval is tied to what it saw across an edit, a half-given count, a migration, a sensitive value's edit, a failed run's retry, and that one approval unlocks one run (brief, D11, D25, D47, D52, D53).
# Run: uv run python reviews/2026-11/probes/p1b_approval_lapses_across_joins.py
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

from ventoux.testing import edit, migrate, propose, release_of, retry

P = PEOPLE | {"lee": ["support-lead", "platform"], "cy": ["claims-sensitive", "support"], "cz": ["claims-sensitive", "support"]}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 900})
wrong = []


def expect(label: str, run: Any, *lines: str) -> None:
    missing = [line for line in lines if line not in run.history]
    print(f"{label}: {'as promised' if not missing else 'MISSING ' + str(missing)}")
    for line in lines:
        print("       |", line)
    if missing:
        wrong.append(label)
        tail(run, 5)


two = refund()
two["steps"]["pay"]["approval"]["count"] = 2
run = run_case(two, FILE, [REVIEWED, ("pay", "approve", "kim"), edit("approved_amount", 5, "lee"), ("case.change#1", "approve", "sam")], P)
expect("1. count=2, one given, then an edit", run,
       "withdrew pay.approval#1: approved_amount changed, with 1 of 2 approvals given",
       "asked pay.approval#2: approval of pay by support-lead, from 2 people")

one = refund()
run = run_case(two, FILE, [REVIEWED, ("pay", "approve", "kim"), migrate(release_of(one, 2), {}, "pia"), ("case.change#1", "approve", "pat")], P, release=release_of(two, 1))
expect("2. count=2, one given, then a migration to a release asking one person", run,
       "withdrew pay.approval#1: refund 2 changed pay, with 1 of 2 approvals given",
       "asked pay.approval#2: approval of pay by support-lead")
print("       pay ran on the half-given approval:", run.reached("pay"))
if run.reached("pay"):
    wrong.append("2. pay ran")

calls: list[Any] = []


def down_once(inputs: dict[str, Any]) -> dict[str, Any]:
    calls.append(inputs["amount"])
    if len(calls) == 1:
        raise ConnectionError("down")
    return {"refund_id": "r-1"}


run = run_case(one, FILE, [REVIEWED, ("pay", "approve", "kim"), edit("approved_amount", 5000, "lee"), ("case.change#1", "approve", "sam"), retry("pay#1", "omar")], P, activities={"payments.refund@2": down_once})
expect("3. an approval spent on a failed run, then an edit, then the retry", run,
       "lapsed pay.approval#1: approved_amount changed", "asked pay.approval#2: approval of pay by support-lead")
print("       amounts the provider was called with:", calls)
if len(calls) != 1:
    wrong.append("3. the retry ran without a new approval")

calls.clear()
other = refund()
other["steps"]["pay"]["inputs"]["amount"] = {"var": "amount"}
run = run_case(one, {"order_id": "ord-1", "amount": 99999}, [REVIEWED, ("pay", "approve", "kim"), migrate(release_of(other, 2), {}, "pia"), ("case.change#1", "approve", "pat"), retry("pay#1", "omar")], P, release=release_of(one, 1), activities={"payments.refund@2": down_once})
expect("4. an approval spent on a failed run, then a migration that changes what pay is given, then the retry", run,
       "lapsed pay.approval#1: refund 2 changed pay", "asked pay.approval#2: approval of pay by support-lead")
print("       amounts the provider was called with:", calls)
if len(calls) != 1:
    wrong.append("4. the retry ran without a new approval")

secret = refund()
del secret["steps"]["pay"]
secret["fields"]["national_id"] = {"type": "string", "display": T("National ID"), "sensitive": True, "visible_to": ["claims-sensitive"]}
secret["steps"]["tell"] = {"kind": "activity", "display": T("Draft"), "activity": "letters.draft@2", "inputs": {"to_customer": {"var": "national_id"}, "template": "t"},
                           "approval": {"roles": ["support-lead"], "display": {"reason": "A lead"}}}
run = run_case(secret, FILE | {"national_id": "AB123456C"}, [edit("national_id", "ZZ999999Z", "cy"), ("case.change#1", "approve", "cz")], P)
expect("5. an open approval that reads a sensitive value, then an edit of it", run,
       "withdrew tell.approval#1: national_id changed", "asked tell.approval#2: approval of tell by support-lead")
leak = [line for line in run.history + run.waiting_for if "AB123456C" in line or "ZZ999999Z" in line]
print("       history or waiting_for lines quoting either value:", leak or "none")
if leak:
    wrong.append("5. a value is quoted")

again = refund()
again["steps"]["pay"] |= {"repeatable": True, "proposed_by": ["support"]}
again |= {"stays_open": True, "close_reasons": {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}}}
run = run_case(again, FILE, [REVIEWED, ("pay", "approve", "kim"), propose("pay", "ana")], P)
expect("6. pay approved and run once, then proposed again", run, "asked pay.approval#2: approval of pay by support-lead")
runs = [line for line in run.history if line.startswith("scheduled pay#")]
print("       runs scheduled:", len(runs))
if len(runs) != 1:
    wrong.append("6. a second run on one approval")
if wrong:
    print("RESULT: BROKEN - " + "; ".join(wrong))
else:
    print("RESULT: HELD - in each of the 6 joins the approval was withdrawn or lapsed and asked again, and nothing ran on what it had not seen")
