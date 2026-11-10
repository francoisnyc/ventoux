# Shows that a migration never lets a field lose `sensitive`, widen `visible_to` or change type, renamed or not, and that a pending edit, a proposer and an answerer follow a rename with their exclusions (brief, D52, D53, D69, D71).
# Run: uv run python reviews/2026-11/probes/p1b_migration_never_loosens.py
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

from ventoux.testing import edit, migrate, propose, release_of

P = PEOPLE | {"lee": ["support-lead", "platform"]}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 900})
wrong = []


def claimish() -> dict[str, Any]:
    case = refund()
    case["fields"]["fraud_score"] = {"type": "number", "display": T("Fraud score"), "visible_to": ["fraud"]}
    case["fields"]["national_id"] = {"type": "string", "display": T("National ID"), "sensitive": True, "visible_to": ["claims-sensitive"]}
    case["steps"]["screen"] = {"kind": "task", "display": T("Screen"), "roles": ["fraud", "claims-sensitive"], "outcomes": {"ok": {"display": T("OK")}}}
    return case


def renamed(case: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    return json.loads(json.dumps(case).replace(old, new))


def moved(target: dict[str, Any], mapping: dict[str, Any] | None = None) -> Any:
    start = claimish()
    script = [migrate(release_of(target, 2), mapping or {}, "pia"), ("case.change#1", "approve", "pat")]
    return run_case(start, FILE | {"fraud_score": 77, "national_id": "AB123456C"}, script, P, release=release_of(start, 1))


def loosened(label: str, change: Any, mapping: dict[str, Any] | None = None, rename: tuple[str, str] | None = None) -> None:
    target = claimish()
    if rename:
        target = renamed(target, *rename)
    change(target)
    try:
        moved(target, mapping)
        wrong.append(label)
        print(f"{label}: TAKEN")
    except Exception as refused:  # noqa: BLE001
        print(f"{label}: refused\n       | {str(refused)[:150]}")


loosened("1. the target drops fraud_score's visible_to", lambda t: t["fields"]["fraud_score"].pop("visible_to"))
loosened("2. the target adds a role to fraud_score's visible_to", lambda t: t["fields"]["fraud_score"].update(visible_to=["fraud", "support"]))
loosened("3. the target replaces fraud by support in visible_to", lambda t: t["fields"]["fraud_score"].update(visible_to=["support"]))
loosened("4. the target adds a role to a sensitive field's visible_to", lambda t: t["fields"]["national_id"].update(visible_to=["claims-sensitive", "support"]))
loosened("5. the target's national_id is no longer sensitive", lambda t: t["fields"]["national_id"].pop("sensitive"))
loosened("6. the target's fraud_score is a string", lambda t: t["fields"]["fraud_score"].update(type="string"))
loosened("7. fraud_score renamed to score, which declares no visible_to", lambda t: t["fields"]["score"].pop("visible_to"), {"fields": {"fraud_score": "score"}}, ("fraud_score", "score"))
loosened("8. national_id renamed to nid, which isn't sensitive", lambda t: t["fields"]["nid"].pop("sensitive"), {"fields": {"national_id": "nid"}}, ("national_id", "nid"))

# A pending edit follows the field's new name, and whoever gave the value still can't approve it.
start = refund()
target = renamed(start, "approved_amount", "amount_ok")
script = [REVIEWED, edit("approved_amount", 5, "kim"), migrate(release_of(target, 2), {"fields": {"approved_amount": "amount_ok"}}, "pia"), ("case.change#2", "approve", "pat")]
try:
    run_case(start, FILE, [*script, ("case.change#1", "approve", "ana")], P, release=release_of(start, 1))
    wrong.append("9")
    print("9. ana, who set the renamed field, approves the pending edit of it: TAKEN")
except Exception as refused:  # noqa: BLE001
    print(f"9. ana, who set the renamed field, approves the pending edit of it: refused\n       | {refused}")
run = run_case(start, FILE, [*script, ("case.change#1", "approve", "sam")], P, release=release_of(start, 1))
ok = "applied case.change#1: amount_ok edited by kim, approved by sam" in run.history
print(f"10. someone else approves it: applied under the new name = {ok}")
if not ok:
    wrong.append("10")

# The proposer of a step follows its rename.
proposed = refund()
proposed["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support-lead"]}
proposed |= {"stays_open": True, "close_reasons": {"duplicate": {"display": T("Duplicate"), "roles": ["support"]}}}
target = renamed(proposed, '"pay"', '"settle"')
run = run_case(proposed, FILE, [REVIEWED, propose("pay", "kim"), migrate(release_of(target, 2), {"steps": {"pay": "settle"}}, "pia"), ("case.change#1", "approve", "pat")], P, release=release_of(proposed, 1))
print("11. kim proposed pay, renamed settle: the case remembers the proposer as", run.state.proposers)
if run.state.proposers != {"settle": "kim"}:
    wrong.append("11")

# An assignment rule naming a task's new name finds who answered it under its old name.
ruled = refund()
ruled["steps"]["follow_up"] = {"kind": "task", "display": T("Follow up"), "roles": ["support"], "requires": ["pay"], "outcomes": {"done": {"display": T("Done")}}, "assign": {"to": "answered", "step": "review"}}
target = renamed(ruled, '"review"', '"assess"').copy()
target = json.loads(json.dumps(target).replace("review.outcome", "assess.outcome"))
run = run_case(ruled, FILE, [REVIEWED, migrate(release_of(target, 2), {"steps": {"review": "assess"}}, "pia"), ("case.change#1", "approve", "pat"), ("pay.approval#2", "approve", "kim")], P, release=release_of(ruled, 1))
print("12. review renamed assess; follow_up asks whoever answered assess:", run.assignees, "|", run.history[-1])
if run.assignees != {"follow_up#1": "ana"}:
    wrong.append("12")
if wrong:
    print("RESULT: BROKEN - " + "; ".join(wrong))
else:
    print("RESULT: HELD - all 8 loosening targets are refused, and the edit, the proposer and the answerer followed their renames")
