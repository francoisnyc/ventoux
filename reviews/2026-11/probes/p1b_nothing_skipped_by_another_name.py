# Shows that, inside one case, a failed run is never ended by anything but a person's retry, a two-person skip or a person's close: a rule's stop (failed or being retried), a new proposal, `closes_when`, a migration, a required step's skip, and requests that race (brief, D17, D26, D34, D40, D52, D53, D72).
# Run: uv run python reviews/2026-11/probes/p1b_nothing_skipped_by_another_name.py
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

from ventoux.testing import close, edit, migrate, propose, release_of, retry, send, skip

P = PEOPLE | {"lee": ["support-lead", "platform"]}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 900})
APPROVED = ("pay", "approve", "kim")
FAIL = {"activities": {"payments.refund@2": down}}
wrong = []


def still_failed(label: str, run: Any, said: str = "") -> None:
    held = bool(run.needs_attention) and not run.closed
    ok = held and (not said or any(said in line for line in run.history))
    print(f"{label}: pay#1 still needs attention = {held}; said = {ok}")
    for line in run.history[-2:]:
        print("       |", line)
    if not ok:
        wrong.append(label)


def refused(label: str, play: Any, said: str) -> None:
    try:
        play()
        wrong.append(label)
        print(f"{label}: TAKEN")
    except Exception as error:  # noqa: BLE001
        ok = said in str(error)
        print(f"{label}: refused = True; for the reason expected = {ok}\n       | {str(error)[:170]}")
        if not ok:
            wrong.append(label)


stopped = refund()
stopped["events"] = {"cancelled": {"display": T("Cancelled"), "sent_by": {"system": "portal"}, "payload": {}}}
stopped["rules"] = {"withdraw": {"display": T("Withdraw"), "on": {"event": "cancelled"}, "then": {"stop": ["pay"]}}}
CANCEL = send("cancelled", {}, "system:portal")
still_failed("1. a rule stops pay while pay#1 is failed", run_case(stopped, FILE, [REVIEWED, APPROVED, CANCEL], P, **FAIL), "a failed run is never stopped")
# The retry waits for a new approval (an edit lapsed the spent one): the run is `retrying`.
script = [REVIEWED, APPROVED, edit("approved_amount", 5, "lee"), ("case.change#1", "approve", "sam"), retry("pay#1", "omar"), CANCEL]
run = run_case(stopped, FILE, script, P, **FAIL)
ok = not run.closed and "approval of pay by support-lead" in run.waiting_for and any("a failed run is never stopped" in line for line in run.history)
print(f"2. a rule stops pay while pay#1's retry waits for its approval: the retry still waits = {ok}\n       | {run.history[-1]}")
if not ok:
    wrong.append("2")

again = refund()
again["steps"]["pay"] |= {"repeatable": True, "proposed_by": ["support"]}
refused("3. pay proposed again beside its failed run", lambda: run_case(again, FILE, [REVIEWED, APPROVED, propose("pay", "ana")], P, **FAIL), "pay#1 needs attention")

closing = refund()
closing["milestones"] = {"reviewed": {"display": T("Reviewed")}}
closing["closes_when"] = ["reviewed"]
closing["steps"]["extra"] = {"kind": "task", "display": T("Extra"), "roles": ["support"], "requires": ["pay"], "outcomes": {"ok": {"display": T("OK"), "reaches": ["reviewed"]}}}
late = refund()
late["milestones"] = closing["milestones"]
late["closes_when"] = ["reviewed"]
late["steps"]["mark"] = {"kind": "task", "display": T("Mark"), "roles": ["support"], "requires": ["review"], "outcomes": {"ok": {"display": T("OK"), "reaches": ["reviewed"]}}}
still_failed("4. every closes_when milestone is reached while pay#1 is failed", run_case(late, FILE, [REVIEWED, APPROVED, ("mark", "ok", "ana")], P, **FAIL))

without = refund()
del without["steps"]["pay"]
refused("5. a migration to a release that has no step pay", lambda: run_case(refund(), FILE, [REVIEWED, APPROVED, migrate(release_of(without, 2), {}, "pia"), ("case.change#1", "approve", "pat")], P, release=release_of(refund(), 1), **FAIL), "pay#1 failed, and refund 2 has no step pay")

owed = refund()
owed["steps"]["pay"]["required"] = True
del owed["steps"]["pay"]["when"]
refused("6. a skip of a required step's failed run", lambda: run_case(owed, FILE, [REVIEWED, APPROVED, skip("pay#1", "omar")], P, **FAIL), "pay is required, so its run is never skipped")
refused("7. a skip approved by the person who approved the run", lambda: run_case(refund(), FILE, [REVIEWED, APPROVED, skip("pay#1", "omar"), ("case.change#1", "approve", "kim")], PEOPLE | {"kim": ["support-lead", "operations"]}, **FAIL), "kim approved pay.approval#1")
refused("8. a skip approved by the reviewer whose amount the run was given", lambda: run_case(refund(), FILE, [("review", "approve", "sam", {"approved_amount": 9}), APPROVED, skip("pay#1", "omar"), ("case.change#1", "approve", "sam")], PEOPLE | {"sam": ["support", "operations"]}, **FAIL), "sam set")

calls: list[int] = []


def down_once(inputs: dict[str, Any]) -> dict[str, Any]:
    calls.append(1)
    if len(calls) == 1:
        raise ConnectionError("down")
    return {"refund_id": "r-1"}


stay = refund() | {"stays_open": True, "close_reasons": {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}}}
run = run_case(stay, FILE, [REVIEWED, APPROVED, skip("pay#1", "omar"), retry("pay#1", "olga"), ("case.change#1", "approve", "olga")], P, activities={"payments.refund@2": down_once})
ok = "case.change#1 not applied: pay#1 can't be skipped: it hasn't failed" in run.history and run.reached("pay")
print(f"9. a skip pending while the run is retried and succeeds, then approved: not applied = {ok}\n       | {run.history[-1]}")
if not ok:
    wrong.append("9")
run = run_case(stay, FILE, [REVIEWED, edit("approved_amount", 5, "lee"), edit("approved_amount", 7, "kim"), ("case.change#1", "approve", "sam"), ("case.change#2", "approve", "fay")], P)
ok = "case.change#2 not applied: approved_amount changed since it was proposed: propose it again" in run.history
print(f"10. two edits pending on one field, both approved: the second not applied = {ok}\n       | {run.history[-1]}")
if not ok:
    wrong.append("10")
refused("11. an edit proposed once the case is closed", lambda: run_case(stay, FILE, [REVIEWED, close("duplicate", "ana"), edit("approved_amount", 5, "lee")], P), "the case is closed")
run = run_case(stay, FILE, [REVIEWED, edit("approved_amount", 5, "lee"), close("duplicate", "ana")], P)
ok = any(line.startswith("cancelled case.change#1") for line in run.history)
print(f"12. a request pending when a person closes the case: cancelled, saying so = {ok}")
if not ok:
    wrong.append("12")
if wrong:
    print("RESULT: BROKEN - " + "; ".join(wrong))
else:
    print("RESULT: HELD - in each of the 12 attempts the failed run waited for a person, and no request applied to a case that had moved on")
