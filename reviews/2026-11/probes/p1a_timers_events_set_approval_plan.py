# Shows whether untrusted data decides when timers, events, `set`, an approval's `when` and a plan's transition are combined in one case (D38, D39, D42, D43, D44, D49).
"""One case, one run. A task `review` starts only on the customer's note. An event from the portal
carries the customer's text. A rule sets `flag` and `copy` under a condition on that text. Then:
- a timer on the steered task's start, and one on a condition reading the text, try to reach;
- a timer on the event's arrival alone, and one on the task's answer, try to reach (both may:
  an arrival is a fact, an answer is a person's);
- the payment's approval reads `flag` in its `when` (false: "no approval needed");
- a plan step is given `flag`, and its transition reads it, with a person's wait before it.
Also asked: an approval whose `when` is `exists flag`, while `flag` isn't set at all.
Only `ventoux.testing`.
"""

import copy
from typing import Any

from ventoux.testing import later, run_case, send

PEOPLE = {"ana": ["support"], "lee": ["support-lead"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


PLAN = {
    "plan": "branch",
    "version": 1,
    **titled("Branch"),
    "fields": {"flag": {"type": "boolean"}},
    "initial": "ask",
    "states": {
        "ask": {
            "wait": {"roles": ["support"], "outcomes": ["ok"]},
            "on": {"ok": [{"when": {"var": "flag"}, "target": "good"}, {"target": "bad"}]},
        },
        "good": {"final": "succeeded"},
        "bad": {"final": "failed"},
    },
}


def timer(since: dict[str, str], milestone: str, when: Any = None) -> dict[str, Any]:
    rule = {
        **titled(milestone),
        "on": {"after": "1d", "since": since},
        "then": {"reach": [milestone]},
    }
    return rule | ({"when": when} if when is not None else {})


CASE: dict[str, Any] = {
    "case": "probe",
    **titled("Probe"),
    "fields": {
        "note": {"type": "string", **titled("Note"), "source": "untrusted:customer"},
        "order_id": {"type": "reference", "system": "orders", **titled("Order")},
        "amount": {"type": "number", **titled("Amount")},
        "flag": {"type": "boolean", **titled("Flag")},
    },
    "events": {
        "said": {
            **titled("Said"),
            "sent_by": {"system": "portal"},
            "payload": {
                "text": {"type": "string", **titled("Text"), "source": "untrusted:customer"}
            },
        }
    },
    "milestones": {
        name: titled(name)
        for name in ("steered_start", "untrusted_when", "arrival", "answer", "reviewed", "branched")
    },
    "steps": {
        "review": {
            "kind": "task",
            **titled("Review"),
            "roles": ["support"],
            "when": {"==": [{"var": "note"}, "go"]},
            "outcomes": {"ok": {**titled("Ok"), "reaches": ["reviewed"]}},
        },
        "pay": {
            "kind": "activity",
            **titled("Pay"),
            "activity": "payments.refund@2",
            "requires": ["reviewed"],
            "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
            "approval": {
                "roles": ["support-lead"],
                "when": {"var": "flag"},
                "display": {"reason": "Refunds need a lead"},
            },
        },
        "branch": {
            "kind": "plan",
            **titled("Branch"),
            "plan": "branch@1",
            "requires": ["reviewed"],
            "inputs": {"flag": {"var": "flag"}},
            "reaches": ["branched"],
        },
    },
    "rules": {
        "on_start": timer({"started": "review"}, "steered_start"),
        "on_text": timer({"event": "said"}, "untrusted_when", {"==": [{"var": "said.text"}, "no"]}),
        "on_arrival": timer({"event": "said"}, "arrival"),
        "on_answer": timer({"answered": "review"}, "answer"),
        "mark": {
            **titled("Mark"),
            "on": {"event": "said"},
            "when": {"==": [{"var": "said.text"}, "no"]},
            "then": {"set": {"flag": False}},
        },
    },
}
run = run_case(
    CASE,
    file={"note": "go", "order_id": "ord-1", "amount": 5},
    answers=[
        send("said", {"text": "no"}, "system:portal"),
        later("2d"),
        ("review", "ok", "ana"),
        later("2d"),
    ],
    people=PEOPLE,
    plans={"branch@1": PLAN},
    plan_answers={"branch": [("ask", "ok", "ana")]},
)
for line in run.history:
    print("   ", line)
print("milestones:", sorted(run.state.milestones))
print("waiting for:", run.waiting_for)
print("needs attention:", run.needs_attention)

# `exists flag` while flag is not set: its only writer, the rule, would give an untrusted value.
unset = copy.deepcopy(CASE)
unset["steps"]["pay"]["approval"]["when"] = {"exists": "flag"}
del unset["steps"]["pay"]["requires"], unset["steps"]["branch"]
quiet = run_case(
    unset, file={"note": "stay", "order_id": "ord-1", "amount": 5}, answers=[], people=PEOPLE
)
print("\nwith `exists flag` as the approval's condition and flag never set:")
for line in quiet.history:
    print("   ", line)

held = (
    set(run.state.milestones) == {"arrival", "answer", "reviewed"}
    and run.waiting_for == ["approval of pay by support-lead"]
    and any("can't choose a plan's path" in line for line in run.needs_attention)
    and not any(line.startswith("scheduled pay") for line in run.history + quiet.history)
    and quiet.waiting_for == ["approval of pay by support-lead"]
)
print()
if held:
    print(
        "RESULT: HELD - only the arrival's timer, the person's answer and its timer reached; the "
        "steered start's timer and the untrusted condition reached nothing; the approval was "
        "asked whatever flag said, and when flag wasn't set; the plan stopped at its transition"
    )
else:
    print("RESULT: BROKEN - untrusted data decided somewhere above")
