# Shows whether an untrusted value sent into a child case and reported back (D74) can decide or reach a guarded input on either side, directly or through a value the child's rule set.
"""The parent gives the customer's `note` to the child's `memo` (which the child doesn't mark).
In the child: a rule tries to reach a milestone on `memo`, a rule sets `flag` under a condition
on `memo`, and a letter sends `memo` to a trusted-only input. A person closes the child with a
reason. The child reports `memo` and `flag`. Back in the parent: a step whose `when` reads
`sub.memo` reaches a milestone; a step whose `when` reads `sub.flag` sends a trusted-only input;
a rule decides on `sub.outcome` (a person's choice of reason, D74).
Only `ventoux.testing`.
"""

from typing import Any

from ventoux.testing import close, run_case

PEOPLE = {"ana": ["support"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


CHILD: dict[str, Any] = {
    "case": "sub",
    **titled("Sub"),
    "fields": {
        "memo": {"type": "string", **titled("Memo")},
        "flag": {"type": "boolean", **titled("Flag")},
    },
    "milestones": {"went": titled("Went")},
    "close_reasons": {"duplicate": {**titled("Duplicate"), "roles": ["support"]}},
    "steps": {
        "letter": {
            "kind": "activity",
            **titled("Letter"),
            "activity": "letters.draft@2",
            "inputs": {"to_customer": {"var": "memo"}, "template": "t"},
        },
        "fix": {
            "kind": "task",
            **titled("Fix"),
            "roles": ["support"],
            "outcomes": {"ok": titled("Ok")},
        },
    },
    "rules": {
        "go": {
            **titled("Go"),
            "on": "opened",
            "when": {"==": [{"var": "memo"}, "go"]},
            "then": {"reach": ["went"]},
        },
        "mark": {
            **titled("Mark"),
            "on": "opened",
            "when": {"==": [{"var": "memo"}, "go"]},
            "then": {"set": {"flag": True}},
        },
    },
    "reports": ["memo", "flag"],
}
PARENT: dict[str, Any] = {
    "case": "claim",
    **titled("Claim"),
    "fields": {
        "email": {"type": "string", **titled("Email")},
        "order": {"type": "string", **titled("Order")},
        "note": {"type": "string", **titled("Note"), "source": "untrusted:customer"},
    },
    "milestones": {name: titled(name) for name in ("by_memo", "by_flag", "by_reason")},
    "steps": {
        "sub": {
            "kind": "case",
            **titled("Sub"),
            "case": "sub@1",
            "inputs": {"memo": {"var": "note"}},
        },
        "on_memo": {
            "kind": "activity",
            **titled("On memo"),
            "activity": "orders.lookup@1",
            "requires": ["sub"],
            "when": {"==": [{"var": "sub.memo"}, "go"]},
            "inputs": {"order_id": {"var": "order"}},
            "reaches": ["by_memo"],
        },
        "on_flag": {
            "kind": "activity",
            **titled("On flag"),
            "activity": "letters.draft@2",
            "requires": ["sub"],
            "when": {"var": "sub.flag"},
            "inputs": {"to_customer": {"var": "email"}, "template": "t"},
            "reaches": ["by_flag"],
        },
    },
    "rules": {
        "reason": {
            **titled("Reason"),
            "on": {"started": "on_memo"},
            "when": {"==": [{"var": "sub.outcome"}, "duplicate"]},
            "then": {"reach": ["by_reason"]},
        }
    },
}
run = run_case(
    PARENT,
    file={"email": "a@example.com", "order": "ord-1", "note": "go"},
    answers=[],
    people=PEOPLE,
    cases={"sub@1": CHILD},
    case_answers={"sub": [close("duplicate", "ana")]},
)
child = run.children["sub#1"]
print("child:")
for line in child.history:
    print("   ", line)
print("    sources:", {name: sorted(found) for name, found in child.state.sources.items()})
print("parent:")
for line in run.history:
    print("   ", line)
sub = {name: sorted(found) for name, found in run.state.sources.items() if name.startswith("sub.")}
print("    sources:", sub)

held = (
    not child.state.milestones
    and not any(line.startswith("scheduled letter") for line in child.history)
    and "untrusted:customer" in child.state.sources["flag"]
    and "untrusted:customer" in run.state.sources["sub.memo"]
    and "untrusted:customer" in run.state.sources["sub.flag"]
    and "case:sub" in run.state.sources["sub.memo"]
    and set(run.state.sources["sub.outcome"]) == {"case:sub", "person:ana"}
    and "by_memo" not in run.state.milestones
    and "by_flag" not in run.state.milestones
    and not any(line.startswith("scheduled on_flag") for line in run.history)
)
print("\nmilestones in the parent:", sorted(run.state.milestones))
print()
if held:
    print(
        "RESULT: HELD - the note stays untrusted:customer into the child, through the child's "
        "rule, and back (with case:sub); it reaches nothing and no trusted-only input on either "
        "side; sub.outcome, the reason a person chose, comes from person:ana and case:sub (D74)"
    )
else:
    print("RESULT: BROKEN - the untrusted value decided or was sent somewhere above")
