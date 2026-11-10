# Shows that "someone else" follows a person's answer through an event they send, a chain of rules' `set`, a child case's report, a child's close reason, an edit, a holder kept, and assigning (brief, D11, D42, D52, D70, D71, D74).
# Run: uv run python reviews/2026-11/probes/p1b_someone_else_across_joins.py
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

from ventoux.testing import assign, claim, close, edit, propose, send, unassign

REVIEWED = ("review", "approve", "ana", {"approved_amount": 900})
BY_SAM = ("review", "approve", "sam", {"approved_amount": 900})
taken = []


def expect_refused(label: str, play: Any) -> None:
    if attempt(label, play) is not None:
        taken.append(label)


# 1. An event a person sends, whose payload is the payment's amount.
by_event = refund()
del by_event["steps"]["review"]
by_event["events"] = {"noted": {"display": T("Noted"), "sent_by": {"roles": ["support"]}, "payload": {"sum": {"type": "number", "display": T("Sum")}}}}
by_event["steps"]["wait"] = {"kind": "wait", "display": T("Wait"), "event": "noted"}
by_event["steps"]["pay"] |= {"requires": ["wait"], "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "noted.sum"}}}
del by_event["steps"]["pay"]["when"]
expect_refused("1. sam sends the event whose payload pay is given; sam approves pay",
               lambda: run_case(by_event, FILE, [send("noted", {"sum": 5}, "sam"), ("pay", "approve", "sam")], PEOPLE))

# 2. Two rules: owed from approved_amount, then owed_again from owed; pay is given owed_again.
chained = refund()
chained["fields"] |= {"owed": {"type": "number", "display": T("Owed")}, "owed_again": {"type": "number", "display": T("Owed again")}}
chained["milestones"] = {"one": {"display": T("One")}, "two": {"display": T("Two")}}
chained["steps"]["review"]["outcomes"]["approve"]["reaches"] = ["one"]
chained["rules"] = {
    "first": {"display": T("First"), "on": {"reached": "one"}, "then": {"set": {"owed": {"-": [{"var": "approved_amount"}, 1]}}, "reach": ["two"]}},
    "second": {"display": T("Second"), "on": {"reached": "two"}, "then": {"set": {"owed_again": {"+": [{"var": "owed"}, 1]}}}},
}
chained["steps"]["pay"] = chained["steps"]["pay"] | {"requires": ["two"], "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "owed_again"}}}
del chained["steps"]["pay"]["when"]
expect_refused("2. sam's amount goes through two rules' set into pay's input; sam approves pay",
               lambda: run_case(chained, FILE, [BY_SAM, ("pay", "approve", "sam")], PEOPLE))

# 3 and 4. A child reports a value its answerer set; a person closes a child with a reason.
REPAIR = {
    "case": "repair", "display": T("Repair"),
    "fields": {"order_id": {"type": "reference", "system": "orders", "display": T("Order")}, "cost": {"type": "number", "display": T("Cost")}},
    "steps": {"fix": {"kind": "task", "display": T("Fix"), "roles": ["support"], "outcomes": {"fixed": {"display": T("Fixed"), "sets": ["cost"]}}}},
    "reports": ["cost"],
    "close_reasons": {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}},
}
claim_case = refund()
claim_case["steps"]["repair"] = {"kind": "case", "display": T("Repair"), "case": "repair@3", "requires": ["review"], "inputs": {"order_id": {"var": "order_id"}}}
claim_case["steps"]["pay"] = claim_case["steps"]["pay"] | {"requires": ["repair"], "when": {"==": [{"var": "repair.outcome"}, "done"]}, "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "repair.cost"}}}
expect_refused("3. sam sets cost inside the child; the parent's pay is given repair.cost; sam approves pay",
               lambda: run_case(claim_case, FILE, [REVIEWED, ("pay", "approve", "sam")], PEOPLE, cases={"repair@3": REPAIR}, case_answers={"repair": [("fix", "fixed", "sam", {"cost": 600})]}))
closed_by = refund()
closed_by["steps"]["repair"] = claim_case["steps"]["repair"]
closed_by["steps"]["pay"] = closed_by["steps"]["pay"] | {"requires": ["repair"], "when": {"==": [{"var": "repair.outcome"}, "duplicate"]}, "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}}}
expect_refused("4. sam closes the child as duplicate; the parent's pay runs when repair.outcome is duplicate; sam approves pay",
               lambda: run_case(closed_by, FILE, [REVIEWED, ("pay", "approve", "sam")], PEOPLE, cases={"repair@3": REPAIR}, case_answers={"repair": [close("duplicate", "sam")]}))

# 5. An edit: its proposer and its approver decided the value.
plain = refund()
expect_refused("5a. lee proposes an edit of the amount, sam approves it; lee approves pay",
               lambda: run_case(plain, FILE, [REVIEWED, edit("approved_amount", 5, "lee"), ("case.change#1", "approve", "sam"), ("pay", "approve", "lee")], PEOPLE))
expect_refused("5b. the edit's approver kim approves pay",
               lambda: run_case(plain, FILE, [REVIEWED, edit("approved_amount", 5, "lee"), ("case.change#1", "approve", "kim"), ("pay", "approve", "kim")], PEOPLE))
expect_refused("5c. ana, whose answer gave the value, approves an edit of it",
               lambda: run_case(plain, FILE, [REVIEWED, edit("approved_amount", 5, "lee"), ("case.change#1", "approve", "ana")], PEOPLE))
kept = run_case(plain, FILE, [REVIEWED, claim("pay.approval#1", "lee"), edit("approved_amount", 5, "lee"), ("case.change#1", "approve", "sam")], PEOPLE)
print("5d. lee held pay's approval, then edited the amount:", kept.history[-1], "| holders:", kept.assignees)
if kept.assignees:
    taken.append("5d. a holder who edited the value kept the approval")

# 6. Nobody chooses their own judge.
expect_refused("6a. sam set the amount; sam unassigns pay's approval from lee", lambda: run_case(plain, FILE, [BY_SAM, claim("pay.approval#1", "lee"), unassign("pay.approval#1", by="sam")], PEOPLE))
expect_refused("6b. sam set the amount; sam reassigns pay's approval to kim", lambda: run_case(plain, FILE, [BY_SAM, claim("pay.approval#1", "lee"), assign("pay.approval#1", "kim", by="sam")], PEOPLE))
expect_refused("6c. lee opened the case; lee assigns pay's approval to kim", lambda: run_case(plain, FILE, [REVIEWED, assign("pay.approval#1", "kim", by="lee")], PEOPLE, opened_by="lee"))
expect_refused("6d. lee assigns pay's approval to sam, who set the amount", lambda: run_case(plain, FILE, [BY_SAM, assign("pay.approval#1", "sam", by="lee")], PEOPLE))
expect_refused("6e. kim answers the approval lee holds", lambda: run_case(plain, FILE, [REVIEWED, claim("pay.approval#1", "lee"), ("pay", "approve", "kim")], PEOPLE))
proposed = refund()
proposed["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support-lead"]}
proposed |= {"stays_open": True, "close_reasons": {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}}}
expect_refused("6f. kim proposed pay; kim assigns its approval to lee", lambda: run_case(proposed, FILE, [REVIEWED, propose("pay", "kim"), assign("pay.approval#1", "lee", by="kim")], PEOPLE))
ruled = refund()
ruled["steps"]["pay"]["approval"]["assign"] = {"to": "answered", "step": "review"}
picked = run_case(ruled, FILE, [BY_SAM], PEOPLE)
print("6g. an assignment rule picks the reviewer for pay's approval:", picked.history[-1], "| holders:", picked.assignees)
if picked.assignees:
    taken.append("6g. an assignment rule made an excluded person the holder")
if taken:
    print("RESULT: BROKEN - taken where it should be refused: " + "; ".join(taken))
else:
    print("RESULT: HELD - in each of the 14 joins the person whose answer is in the decision approves, assigns and holds nothing")
