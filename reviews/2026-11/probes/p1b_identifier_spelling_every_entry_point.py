# Shows whether every act a person sends (open, answer, propose, claim, assign, give back, unassign, close, event, edit, skip, migrate, retry, shown, forget) refuses an identifier not written the one way (brief, D22).
# Run: uv run python reviews/2026-11/probes/p1b_identifier_spelling_every_entry_point.py
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

from ventoux.testing import (
    assign, claim, close, edit, forget, give_back, migrate, propose, release_of, retry, send, shown, skip, unassign,
)

case = refund()
case["close_reasons"] = {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}}
case["events"] = {"called": {"display": T("Called"), "sent_by": {"roles": ["support"]}, "payload": {}}}
case["steps"]["extra"] = {
    "kind": "task", "display": T("Extra"), "roles": ["support"], "automatic": False,
    "proposed_by": ["support"], "outcomes": {"ok": {"display": T("OK")}},
}
case["forgetting"] = "allowed"
RELEASE = release_of(case, 1)
REVIEWED = ("review", "approve", "ana", {"approved_amount": 900})
BAD = ["Sam", "sam ", " sam", "sаm", "sam\n", "send_back#1", "case:x", "person:sam", "system:opener", "", "-sam", "sam,lee"]
# "sаm" above holds a Cyrillic letter that looks like a Latin one.


def acts(bad: str) -> dict[str, tuple[list[Any], dict[str, Any]]]:
    people = PEOPLE | {bad: ["support", "support-lead", "operations", "platform", "privacy"]}
    with_roles = {"people": people}
    return {
        "open": ([], with_roles | {"opened_by": bad}),
        "answer a task": ([("review", "approve", bad, {"approved_amount": 9})], with_roles),
        "answer an approval": ([REVIEWED, ("pay", "approve", bad)], with_roles),
        "propose": ([propose("extra", bad)], with_roles),
        "claim": ([claim("review#1", bad)], with_roles),
        "give back": ([claim("review#1", "ana"), give_back("review#1", bad)], with_roles),
        "assign (by)": ([assign("review#1", "ana", by=bad)], with_roles),
        "assign (to)": ([assign("review#1", bad, by="lee")], with_roles),
        "unassign": ([claim("review#1", "ana"), unassign("review#1", by=bad)], with_roles),
        "close": ([close("duplicate", bad)], with_roles),
        "send an event": ([send("called", {}, bad)], with_roles),
        "propose an edit": ([REVIEWED, edit("approved_amount", 5, bad)], with_roles),
        "approve an edit": ([REVIEWED, edit("approved_amount", 5, "kim"), ("case.change#1", "approve", bad)], with_roles),
        "propose a skip": ([REVIEWED, ("pay", "approve", "lee"), skip("pay#1", bad)], with_roles | {"activities": {"payments.refund@2": down}}),
        "retry": ([REVIEWED, ("pay", "approve", "lee"), retry("pay#1", bad)], with_roles | {"activities": {"payments.refund@2": down}}),
        "propose a migration": ([migrate(RELEASE, {}, bad, engine=99)], with_roles | {"release": RELEASE}),
        "shown a record": ([shown("order_id", bad)], with_roles),
        "forget (proposer)": ([forget(bad, "olga")], with_roles),
        "forget (approver)": ([forget("olga", bad)], with_roles),
    }


accepted, wrong_reason = [], []
for bad in BAD:
    for name, (script, options) in acts(bad).items():
        if bad == "system:opener" and name == "send an event":
            continue  # a system's name is how a system's event is sent: refused as the wrong sender
        try:
            run_case(case, FILE, script, **options)
            accepted.append(f"{name} by {bad!r}")
        except Exception as refused:  # noqa: BLE001
            if "is not written as a person's identifier" not in str(refused):
                wrong_reason.append(f"{name} by {bad!r}: {type(refused).__name__}: {str(refused)[:90]}")
# Control: the same scripts with a well-written identifier reach their act (none says "not written").
control = []
for name, (script, options) in acts("zed").items():
    try:
        run_case(case, FILE, script, **options)
        control.append(f"{name}: taken")
    except Exception as refused:  # noqa: BLE001
        assert "is not written as" not in str(refused), name
        control.append(f"{name}: {str(refused)[:60]}")
print("control, by 'zed':", "; ".join(control))
print(f"{len(BAD)} misspelt identifiers x {len(acts('x'))} acts")
print("accepted:", accepted or "none")
print("refused for another reason first:")
for line in wrong_reason:
    print("   ", line)
if accepted:
    print("RESULT: BROKEN - an act was taken from a misspelt identifier: " + "; ".join(accepted[:6]))
elif wrong_reason:
    print("RESULT: HELD - no act is taken from a misspelt identifier; some are refused by another check first (listed above)")
else:
    print("RESULT: HELD - every act refuses a misspelt identifier, saying so, before any other check")
