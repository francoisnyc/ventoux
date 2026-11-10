# Shows whether an expression the runtime can't read (missing field, wrong type, division by zero) is ever taken as false or as "no approval" at any place a case reads one (D20, D34, D38, fail closed).
"""Each bad expression is put, in turn, in every place a case reads a condition or a value: a
step's `when`, a rule's `when`, an approval's `when`, a rule's `set` value, a child case's input,
and a repeated step's `when` (reading its item). The runtime runs alone: validation isn't called
(D34). For each, the step guarded must not run, nothing must be decided, and the case must say it
needs attention. Unknown operators, floats and bare `each` are tried at the reader.
Only `ventoux.testing`, plus `parse_case` for the reader.
"""

import copy
from typing import Any

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import run_case

PEOPLE = {"ana": ["support"], "lee": ["support-lead"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


BAD = {
    "a missing field": {"==": [{"var": "pay.outcome"}, "done"]},  # pay has not run
    "a number compared with a text": {">": [{"var": "amount"}, {"var": "name"}]},
    "a division by zero": {">": [{"/": [{"var": "amount"}, {"var": "zero"}]}, 1]},
    "a text added to a number": {">": [{"+": [{"var": "amount"}, {"var": "name"}]}, 1]},
    # D20: `and` and `or` evaluate every operand, so an error is never hidden.
    "false and <a missing field>": {
        "and": [{"<": [{"var": "amount"}, 0]}, {"==": [{"var": "pay.outcome"}, "done"]}]
    },
    "true or <a missing field>": {
        "or": [{">": [{"var": "amount"}, 0]}, {"==": [{"var": "pay.outcome"}, "done"]}]
    },
}
CHILD = {
    "case": "sub",
    **titled("Sub"),
    "fields": {"flag": {"type": "boolean", **titled("Flag")}},
    "steps": {
        "wait": {
            "kind": "task",
            **titled("Wait"),
            "roles": ["support"],
            "outcomes": {"ok": titled("Ok")},
        }
    },
}


def base() -> dict[str, Any]:
    return {
        "case": "probe",
        **titled("Probe"),
        "fields": {
            "order_id": {"type": "reference", "system": "orders", **titled("Order")},
            "amount": {"type": "number", **titled("Amount")},
            "zero": {"type": "number", **titled("Zero")},
            "name": {"type": "string", **titled("Name")},
            "flag": {"type": "boolean", **titled("Flag")},
            "lines": {"type": "list", **titled("Lines"), "fields": {"sku": {"type": "string"}}},
        },
        "milestones": {"decided": titled("Decided")},
        "steps": {
            "pay": {
                "kind": "activity",
                **titled("Pay"),
                "activity": "payments.refund@2",  # high risk
                "automatic": False,
                "proposed_by": ["support"],
                "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
                "approval": {
                    "roles": ["support-lead"],
                    "display": {"reason": "Refunds need a lead"},
                },
            }
        },
        "rules": {},
    }


LOOK = {
    "kind": "activity",
    **titled("Look"),
    "activity": "orders.lookup@1",
    "inputs": {"order_id": {"var": "order_id"}},
}


def placed(place: str, bad: Any) -> tuple[dict[str, Any], list[Any]]:
    """The base case with `bad` at `place`, and the script that brings it to be read."""
    definition = base()
    answers: list[Any] = []
    if place == "a step's when":
        definition["steps"]["look"] = LOOK | {"when": bad, "reaches": ["decided"]}
    elif place == "a rule's when":
        definition["rules"]["decide"] = {
            **titled("Decide"),
            "on": "opened",
            "when": bad,
            "then": {"reach": ["decided"]},
        }
    elif place == "an approval's when":
        # A high-risk step with an approval that is "needed only when": unreadable must not mean "not needed".
        definition["steps"]["look"] = LOOK | {
            "activity": "payments.refund@2",
            "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
            "approval": {"roles": ["support-lead"], "when": bad, "display": {"reason": "why"}},
        }
    elif place == "a rule's set value":
        definition["rules"]["mark"] = {
            **titled("Mark"),
            "on": "opened",
            "then": {"set": {"flag": bad}, "reach": ["decided"]},
        }
    elif place == "a child case's input":
        definition["steps"]["sub"] = {
            "kind": "case",
            **titled("Sub"),
            "case": "sub@1",
            "inputs": {"flag": bad},
            "reaches": ["decided"],
        }
    elif place == "a repeated step's when":
        definition["steps"]["look"] = LOOK | {
            "for_each": {"over": "lines", "key": "sku"},
            "when": {"and": [{"==": [{"var": "each.sku"}, "A"]}, bad]},
        }
    return definition, answers


FILE = {"order_id": "ord-1", "amount": 5, "zero": 0, "name": "x", "lines": [{"sku": "A"}]}
wrong = []
for place in (
    "a step's when",
    "a rule's when",
    "an approval's when",
    "a rule's set value",
    "a child case's input",
    "a repeated step's when",
):
    for title, bad in BAD.items():
        definition, answers = placed(place, copy.deepcopy(bad))
        run = run_case(
            definition, file=FILE, answers=answers, people=PEOPLE, cases={"sub@1": CHILD}
        )
        ran = [
            line for line in run.history if line.startswith(("scheduled", "started sub", "reached"))
        ]
        ok = (
            bool(run.needs_attention)
            and not ran
            and not run.closed
            and "flag" not in run.state.values
        )
        said = run.needs_attention[0][:110] if run.needs_attention else "NOTHING NEEDS ATTENTION"
        print(f"{place}, {title}: {'refused' if ok else 'TAKEN'}: {said}")
        if not ok:
            wrong.append(f"{place} with {title}")

print("\nat the reader:")
for title, bad in {
    "an unknown operator": {"matches": [{"var": "name"}, ".*"]},
    "a binary float": {">": [{"var": "amount"}, 0.1]},
    "`each` outside a repeated step": {"==": [{"var": "each.sku"}, "A"]},
    "a Python-looking text": "__import__('os')",
    "now": {">": [{"var": "amount"}, {"now": []}]},
}.items():
    definition, _ = placed("a rule's when", bad)
    try:
        parse_case(definition)
    except CaseInvalid as refused:
        print(f"  {title}: refused: {str(refused)[:100]}")
    else:
        run = run_case(definition, file=FILE, answers=[], people=PEOPLE)
        decided = "decided" in run.state.milestones
        print(f"  {title}: READ; decided: {decided}; needs attention: {run.needs_attention}")
        if decided or not run.needs_attention:
            wrong.append(f"the reader took {title}")

print()
if wrong:
    print("RESULT: BROKEN - read as false, or acted on: " + "; ".join(wrong))
else:
    print("RESULT: HELD - every unreadable expression stopped what it guarded and needs attention")
