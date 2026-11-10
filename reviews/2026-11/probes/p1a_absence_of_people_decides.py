# Shows whether untrusted data can decide by making a person's work NOT exist: a task kept from starting, or an empty customer-typed list (D38, D43, D48, D73).
"""Part 1. `review` is a task that starts only when the customer's note says go (D48 lets
untrusted data keep it from starting). A rule on another task's answer reaches the milestone that
closes the case when `review.outcome` doesn't exist. The same rule over an ACTIVITY the note keeps
from starting is refused (see p1a_expression_forms_never_decide.py): what about a task?

Part 2. `inspect` is a task repeated over `lines`, a list the customer typed. `settle` requires
it and reaches the milestone that closes the case. With lines, a person inspects each before
`settle` runs. With an empty list, the requirement is met at once (D73).
Only `ventoux.testing`, plus `parse_case` and `validate_case` to ask the check.
"""

from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, run_case

PEOPLE = {"ana": ["support"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


def task(**more: Any) -> dict[str, Any]:
    return {
        "kind": "task",
        **titled("A task"),
        "roles": ["support"],
        "outcomes": {"ok": titled("Ok")},
    } | more


ABSENT: dict[str, Any] = {
    "case": "probe",
    **titled("Probe"),
    "fields": {"note": {"type": "string", **titled("Note"), "source": "untrusted:customer"}},
    "milestones": {"settled": titled("Settled")},
    "closes_when": ["settled"],
    "steps": {"hold": task(), "review": task(when={"==": [{"var": "note"}, "go"]})},
    "rules": {
        "unreviewed": {
            **titled("Settle what nobody reviewed"),
            "on": {"answered": "hold"},
            "when": {"!": [{"exists": "review.outcome"}]},
            "then": {"reach": ["settled"]},
        }
    },
}
print("=== 1. a rule on the absence of a task's answer, the task kept from starting by the note")
issues = validate_case(parse_case(ABSENT), CATALOG)
print("check:", [(i.severity, i.code, i.path) for i in issues])
outcome = {}
for note, answers in (
    ("go", [("review", "ok", "ana"), ("hold", "ok", "ana")]),
    ("stay", [("hold", "ok", "ana")]),
):
    run = run_case(ABSENT, file={"note": note}, answers=answers, people=PEOPLE)
    outcome[note] = "settled" in run.state.milestones
    print(f"--- the note says {note}")
    for line in run.history[1:]:
        print("   ", line)
part_1 = outcome["stay"] and not outcome["go"]

LINES: dict[str, Any] = {
    "case": "probe",
    **titled("Probe"),
    "fields": {
        "email": {"type": "string", **titled("Email")},
        "lines": {
            "type": "list",
            **titled("Lines"),
            "source": "untrusted:customer",
            "fields": {"sku": {"type": "string"}},
        },
    },
    "milestones": {"settled": titled("Settled")},
    "closes_when": ["settled"],
    "steps": {
        "inspect": task(for_each={"over": "lines", "key": "sku"}),
        "settle": {
            "kind": "activity",
            **titled("Settle"),
            "activity": "letters.draft@2",
            "requires": ["inspect"],
            "inputs": {"to_customer": {"var": "email"}, "template": "settled"},
            "reaches": ["settled"],
        },
    },
}
print("\n=== 2. a step requiring a task repeated over a list the customer typed")
issues = validate_case(parse_case(LINES), CATALOG)
print("check:", [(i.severity, i.code, i.path) for i in issues])
closed = {}
for title, lines in (("two lines", [{"sku": "A"}, {"sku": "B"}]), ("no lines", [])):
    run = run_case(
        LINES, file={"email": "a@example.com", "lines": lines}, answers=[], people=PEOPLE
    )
    closed[title] = run.closed
    print(f"--- {title}: {run.status}; waiting for {run.waiting_for}")
    for line in run.history[1:]:
        print("   ", line)
part_2 = closed["no lines"] and not closed["two lines"]

print()
if part_1 or part_2:
    found = []
    if part_1:
        found.append(
            "the note alone (stay) made the rule reach the closing milestone, by keeping the "
            "review from existing, and the absent answer read as a person's"
        )
    if part_2:
        found.append(
            "an empty customer-typed list closed the case with no person, where any line waits "
            "for one"
        )
    print("RESULT: BROKEN - " + "; ".join(found) + "; the check said nothing of either")
else:
    print("RESULT: HELD - the absence of a person's work never decided")
