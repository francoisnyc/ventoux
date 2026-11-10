# Shows whether any expression form lets a deciding rule read untrusted data without being stopped (D20, D38, D43).
"""One rule, on a task's answer, reaches a milestone. Its condition reads the customer's note or
list through each operator that could hide a read (`exists`, `if`, `in`, `cat`, `count`, `sum`,
a short-circuited `or`), and through the ABSENCE of an output only a steered run would write
(`not exists look.status`, where `look` starts only on the customer's word, by its own `when`, by
a rule, or by a step it requires). Run with the note saying go and saying stay.
Only `ventoux.testing`, plus `parse_case` and `validate_case` to ask the check.
"""

import copy
from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, run_case

GO = {"==": [{"var": "note"}, "go"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


def case(when: Any) -> dict[str, Any]:
    untrusted = {"source": "untrusted:customer"}
    return {
        "case": "probe",
        **titled("Probe"),
        "fields": {
            "note": {"type": "string", **titled("Note"), **untrusted},
            "order": {"type": "reference", "system": "orders", **titled("Order")},
            "lines": {
                "type": "list",
                **titled("Lines"),
                **untrusted,
                "fields": {"sku": {"type": "string"}, "amount": {"type": "number"}},
            },
        },
        "milestones": {"decided": titled("Decided")},
        "steps": {
            "hold": {
                "kind": "task",
                **titled("Hold"),
                "roles": ["support"],
                "outcomes": {"ok": titled("Ok")},
            },
            "look": {
                "kind": "activity",
                **titled("Look"),
                "activity": "orders.lookup@2",  # status comes from system:orders
                "when": GO,
                "inputs": {"order_id": {"var": "order"}},
            },
        },
        "rules": {
            "decide": {
                **titled("Decide"),
                "on": {"answered": "hold"},
                "when": when,
                "then": {"reach": ["decided"]},
            }
        },
    }


def started_by_a_rule() -> dict[str, Any]:
    definition = case({"!": [{"exists": "look.status"}]})
    del definition["steps"]["look"]["when"]
    definition["steps"]["look"]["automatic"] = False
    definition["rules"]["start_look"] = {
        **titled("Start"),
        "on": "opened",
        "when": GO,
        "then": {"start": ["look"]},
    }
    return definition


def behind_a_requirement() -> dict[str, Any]:
    definition = case({"!": [{"exists": "again.status"}]})
    definition["steps"]["again"] = copy.deepcopy(definition["steps"]["look"])
    del definition["steps"]["again"]["when"]
    definition["steps"]["again"]["requires"] = ["look"]
    return definition


over = {"var": "lines"}
CASES: dict[str, dict[str, Any]] = {
    "exists note": case({"exists": "note"}),
    "if": case({"if": [GO, True, False]}),
    "in": case({"in": [{"var": "note"}, ["go", "x"]]}),
    "cat": case({"==": [{"cat": ["a", {"var": "note"}]}, "ago"]}),
    "or, short-circuited": case({"or": [True, {"==": [{"var": "note"}, "zzz"]}]}),
    "count": case({">": [{"count": {"over": over}}, 0]}),
    "count where": case(
        {"==": [{"count": {"over": over, "where": {">": [{"item": "amount"}, 1]}}}, 0]}
    ),
    "sum": case({">": [{"sum": {"over": over, "value": {"item": "amount"}}}, 0]}),
    "not exists look.status (own when)": case({"!": [{"exists": "look.status"}]}),
    "not exists look.outcome (own when)": case({"!": [{"exists": "look.outcome"}]}),
    "not exists look.status (a rule starts look)": started_by_a_rule(),
    "not exists again.status (again requires look)": behind_a_requirement(),
}

decided = []
unsaid = []
for title, definition in CASES.items():
    issues = validate_case(parse_case(copy.deepcopy(definition)), CATALOG)
    codes = sorted({i.code for i in issues if i.severity == "error"})
    reached = {}
    for note in ("go", "stay"):
        run = run_case(
            definition,
            file={"note": note, "order": "ord-1", "lines": [{"sku": "a", "amount": 2}]},
            answers=[("hold", "ok", "ana")],
            people={"ana": ["support"]},
            activities={"orders.lookup@2": lambda inputs: {"status": "delivered"}},
        )
        reached[note] = "decided" in run.state.milestones
    print(f"{title}: check errors {codes}; reached on go/stay: {reached['go']}/{reached['stay']}")
    if any(reached.values()):
        decided.append(title)
    if "UNTRUSTED_TRIGGER" not in codes:
        unsaid.append(title)

print()
if decided or unsaid:
    print(
        f"RESULT: BROKEN - the rule decided through: {decided}; the check was silent for: {unsaid}"
    )
else:
    print(
        "RESULT: HELD - through every form the rule reached nothing, whatever the note said, and "
        "the check refused each (UNTRUSTED_TRIGGER)"
    )
