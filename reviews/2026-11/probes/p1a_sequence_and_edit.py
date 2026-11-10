# Shows whether steering crosses a `sequence` (an implied requirement), and whether an edit (D52) can re-stamp an untrusted value as people's by giving it again, as a number written another way.
"""Part 1: `look` runs only on the customer's note; `confirm` follows it by `sequence` alone (no
`requires`), reaches a milestone and sends a trusted-only input.
Part 2: `amount` is declared `untrusted:customer` and holds 250. Edits to 250, to 250.00 and to
"250" are proposed; then a real edit to 251, approved by someone else.
Only `ventoux.testing`.
"""

from decimal import Decimal
from typing import Any

from ventoux.testing import ChangeRefused, edit, run_case

PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


def case() -> dict[str, Any]:
    untrusted = {"source": "untrusted:customer"}
    return {
        "case": "probe",
        **titled("Probe"),
        "fields": {
            "order_id": {"type": "reference", "system": "orders", **titled("Order")},
            "email": {"type": "string", **titled("Email")},
            "note": {"type": "string", **titled("Note"), **untrusted},
            "amount": {"type": "number", **titled("Amount"), **untrusted},
        },
        "milestones": {"confirmed": titled("Confirmed")},
        "stays_open": True,
        "close_reasons": {"duplicate": {**titled("Duplicate"), "roles": ["support"]}},
        "steps": {
            "look": {
                "kind": "activity",
                **titled("Look"),
                "activity": "orders.lookup@1",
                "when": {"==": [{"var": "note"}, "go"]},
                "inputs": {"order_id": {"var": "order_id"}},
            },
            "confirm": {
                "kind": "activity",
                **titled("Confirm"),
                "activity": "letters.draft@2",
                "inputs": {"to_customer": {"var": "email"}, "template": "t"},
                "reaches": ["confirmed"],
            },
        },
        "sequence": ["look", "confirm"],
    }


FILE = {"order_id": "ord-1", "email": "a@example.com", "note": "go", "amount": 250}
broken = []
print("=== 1. steering across a sequence")
run = run_case(case(), file=FILE, answers=[], people=PEOPLE)
for line in run.history[1:]:
    print("   ", line)
if run.state.milestones or any(line.startswith("scheduled confirm") for line in run.history):
    broken.append("confirm ran or reached after a steered look, by sequence")

print("\n=== 2. an edit to the value already held")
for value in (250, Decimal("250.00"), "250"):
    try:
        run_case(case(), file=FILE, answers=[edit("amount", value, "ana")], people=PEOPLE)
        print(f"    edit to {value!r}: PROPOSED")
        broken.append(f"an edit to {value!r} was taken")
    except ChangeRefused as refused:
        print(f"    edit to {value!r}: refused: {refused}")
changed = run_case(
    case(),
    file=FILE,
    answers=[edit("amount", 251, "ana"), ("case.change#1", "approve", "sam")],
    people=PEOPLE,
)
print("    after a real edit to 251, amount comes from:", sorted(changed.state.sources["amount"]))
if "untrusted:customer" not in changed.state.sources["amount"]:
    broken.append("an edit removed the field's declared mark")

print()
if broken:
    print("RESULT: BROKEN - " + "; ".join(broken))
else:
    print(
        "RESULT: HELD - a step after a steered one in a sequence is steered by it; an edit to the "
        "same number, however written, is refused; a real edit keeps the field's declared mark"
    )
