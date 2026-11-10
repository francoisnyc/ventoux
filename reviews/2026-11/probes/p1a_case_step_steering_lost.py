# Shows whether a case step (D74) keeps what steered its run (D39, D43), as a plan step does.
"""A step whose `when` reads `note`, which a customer typed (`untrusted:customer`), runs a small
letter: as a plan step (the control), then as a case step opening a child case with no person in
it. Asked of each: does its `reaches` apply, does a rule on its start act, do its outcome and
outputs carry the note's source, is a step requiring it steered, and is the letter's trusted-only
input still sent? Only `ventoux.testing`, plus `parse_case` and `validate_case` to ask the check.
"""

import copy
from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, later, run_case

LETTER = {"to_customer": {"var": "email"}, "template": "t"}  # to_customer is trusted_only()
PLAN = {
    "plan": "write",
    "version": 1,
    "display": {"title": "Write a letter"},
    "fields": {"email": {"type": "string"}},
    "initial": "letter",
    "states": {
        "letter": {"activity": "letters.draft@2", "inputs": LETTER, "on": {"done": "sent"}},
        "sent": {"final": "succeeded"},
    },
}
CHILD = {
    "case": "write",
    "display": {"title": "Write a letter"},
    "fields": {"email": {"type": "string", "display": {"title": "Email"}}},
    "steps": {
        "letter": {
            "kind": "activity",
            "display": {"title": "Letter"},
            "activity": "letters.draft@2",
            "inputs": LETTER,
        }
    },
}


def parent(kind: str) -> dict[str, Any]:
    write: dict[str, Any] = {
        "display": {"title": "Write"},
        "when": {"==": [{"var": "note"}, "go"]},  # the customer's word
        "inputs": {"email": {"var": "email"}},
        "reaches": ["written"],
    }
    write |= (
        {"kind": "plan", "plan": "write@1"}
        if kind == "plan"
        else {
            "kind": "case",
            "case": "write@1",
        }
    )
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {
            "email": {"type": "string", "display": {"title": "Email"}},
            "order": {"type": "string", "display": {"title": "Order"}},
            "seen": {"type": "boolean", "display": {"title": "Seen"}},
            "note": {
                "type": "string",
                "display": {"title": "Note"},
                "source": "untrusted:customer",
            },
        },
        "milestones": {
            "written": {"display": {"title": "Written"}},
            "began": {"display": {"title": "Began"}},
            "followed": {"display": {"title": "Followed up"}},
        },
        "steps": {
            "write": write,
            "follow_up": {
                "kind": "activity",
                "display": {"title": "Follow up"},
                "activity": "orders.lookup@1",
                "requires": ["write"],
                "inputs": {"order_id": {"var": "order"}},
                "reaches": ["followed"],
            },
        },
        "rules": {
            "begin": {
                "display": {"title": "Begin"},
                "on": {"started": "write"},
                "then": {"reach": ["began"]},
            },
            "mark": {
                "display": {"title": "Mark"},
                "on": {"started": "write"},
                "when": {"==": [{"var": "order"}, "ord-1"]},
                "then": {"set": {"seen": True}},
            },
        },
    }


FILE = {"email": "a@example.com", "order": "ord-1", "note": "go"}
seen: dict[str, dict[str, Any]] = {}
for kind in ("plan", "case"):
    definition = parent(kind)
    supplied: dict[str, Any] = {
        "plans" if kind == "plan" else "cases": {"write@1": PLAN if kind == "plan" else CHILD}
    }
    issues = validate_case(parse_case(copy.deepcopy(definition)), CATALOG, **supplied)
    run = run_case(definition, file=FILE, answers=[], people={}, **supplied)
    print(f"\n=== write is a {kind} step" + (" (control)" if kind == "plan" else ""))
    print("check:")
    for issue in issues:
        print(f"   {issue.severity} {issue.code} {issue.path}")
    print("history:")
    for line in run.history[1:]:
        print("   ", line)
    for child in run.children.values():
        print("child's history:")
        for line in child.history:
            print("      ", line)
    sources = {name: sorted(run.state.sources.get(name, ())) for name in ("write.outcome", "seen")}
    print("needs attention:", run.needs_attention)
    print("milestones:", sorted(run.state.milestones), "| sources:", sources)
    seen[kind] = {
        "milestones": set(run.state.milestones),
        "sources": sources,
        "errors": {(i.code, i.path) for i in issues if i.severity == "error"},
        "letter": any(
            "scheduled letter#1" in line for c in run.children.values() for line in c.history
        ),
    }

# A second way in: a rule starts the case step on the customer's word, the child stays open (a
# task waits in it), and a timer set on the step's start fires a day later (D39, D44).
OPEN_CHILD = copy.deepcopy(CHILD)
OPEN_CHILD["steps"]["sign"] = {
    "kind": "task",
    "display": {"title": "Sign"},
    "roles": ["support"],
    "outcomes": {"signed": {"display": {"title": "Signed"}}},
}
by_rule = parent("case")
del by_rule["steps"]["write"]["when"], by_rule["rules"]["begin"], by_rule["rules"]["mark"]
by_rule["steps"]["write"]["automatic"] = False
by_rule["rules"] = {
    "start_write": {
        "display": {"title": "Start"},
        "on": "opened",
        "when": {"==": [{"var": "note"}, "go"]},
        "then": {"start": ["write"]},
    },
    "chase": {
        "display": {"title": "Chase"},
        "on": {"after": "1d", "since": {"started": "write"}},
        "then": {"reach": ["began"]},
    },
}
issues = validate_case(parse_case(copy.deepcopy(by_rule)), CATALOG, cases={"write@1": OPEN_CHILD})
run = run_case(
    by_rule,
    file=FILE,
    answers=[later("2d")],
    people={"ana": ["support"]},
    cases={"write@1": OPEN_CHILD},
    case_answers={},
)
print("\n=== a rule starts the case step on the note; a timer is set on its start")
print("check:")
for issue in issues:
    print(f"   {issue.severity} {issue.code} {issue.path}")
print("history:")
for line in run.history[1:]:
    print("   ", line)
print("milestones:", sorted(run.state.milestones))
timer_reached = "began" in run.state.milestones

control, case = seen["plan"], seen["case"]
broken = []
if not control["milestones"] and case["milestones"]:
    broken.append(
        f"on the customer's note the case step's run and rule reached {sorted(case['milestones'])}"
    )
if case["letter"]:
    broken.append("the child sent its trusted-only input under the untrusted condition")
if "untrusted:customer" not in case["sources"]["write.outcome"]:
    broken.append("write.outcome doesn't carry untrusted:customer")
if "untrusted:customer" not in case["sources"]["seen"]:
    broken.append("a value set on its start doesn't carry untrusted:customer")
if timer_reached:
    broken.append("a timer set on a rule-started, steered case step's start reached a milestone")
missing = control["errors"] - case["errors"]
if missing:
    broken.append(f"the check is silent where it refuses the plan step: {sorted(missing)}")
print()
if broken:
    print("RESULT: BROKEN - " + "; ".join(broken))
else:
    print("RESULT: HELD - a case step's run carries what steered it, as a plan step's does")
