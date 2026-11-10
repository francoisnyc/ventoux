# Shows whether what steered a run, a rule's pending start, a failed firing and a timer survives the state's trip through continue-as-new (D27, D43), and still stops a decision after it.
"""Pure: no Temporal worker. The case's state is written as data and read back with the two
functions the case workflow uses to continue as new (`ventoux.temporal.carried`, reached past the
public names: there is no public door to the carried state), through the exact payload converter.
Then the script goes on from the state read back, and from the original, and the two are compared.
"""

import dataclasses
from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.memory import run_case_in_memory
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.converter import ExactPayloadConverter
from ventoux.testing import (
    CATALOG,
    FAKES,
    START,
    finish,
    later,
    retry,
    run_case,
    script_events,
    send,
)

GO = {"==": [{"var": "note"}, "go"]}
PEOPLE = {"ana": ["support"], "lee": ["support-lead"], "omar": ["operations"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


CASE: dict[str, Any] = {
    "case": "probe",
    **titled("Probe"),
    "fields": {
        "note": {"type": "string", **titled("Note"), "source": "untrusted:customer"},
        "order_id": {"type": "reference", "system": "orders", **titled("Order")},
        "amount": {"type": "number", **titled("Amount")},
        "seen": {"type": "boolean", **titled("Seen")},
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
    "milestones": {name: titled(name) for name in ("looked", "late", "began", "paid")},
    "steps": {
        # Steered by its own condition, and held running across the switch.
        "look": {
            "kind": "activity",
            **titled("Look"),
            "activity": "orders.lookup@1",
            "when": GO,
            "inputs": {"order_id": {"var": "order_id"}},
            "reaches": ["looked"],
        },
        # Started by a rule on the customer's word, and waiting for its approval at the switch.
        "pay": {
            "kind": "activity",
            **titled("Pay"),
            "activity": "payments.refund@2",
            "automatic": False,
            "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
            "approval": {"roles": ["support-lead"], "display": {"reason": "why"}},
            "reaches": ["paid"],
        },
    },
    "rules": {
        "start_pay": {
            **titled("Start pay"),
            "on": {"event": "said"},
            "when": {"==": [{"var": "said.text"}, "pay"]},
            "then": {"start": ["pay"]},
        },
        "begin": {**titled("Begin"), "on": {"started": "pay"}, "then": {"reach": ["began"]}},
        "chase": {
            **titled("Chase"),
            "on": {"after": "1d", "since": {"started": "look"}},
            "then": {"reach": ["late"]},
        },
        "mark": {
            **titled("Mark"),
            "on": {"started": "look"},
            "when": {"==": [{"var": "order_id"}, {"var": "order_id"}]},
            "then": {"set": {"seen": True}},
        },
    },
}
FILE = {"note": "go", "order_id": "ord-1", "amount": 5}
BEFORE = [send("said", {"text": "pay"}, "system:portal")]
# The approval is given, the timer falls due, an operator retries the refused payment, and at
# last the held lookup finishes (only in the reference run: the driver that held it is gone).
AFTER = [
    ("pay.approval#1", "approve", "lee"),
    later("2d"),
    retry("pay#1", "omar"),
    ("pay.approval#2", "approve", "lee"),
    finish("look#1"),
]

before = run_case(CASE, file=FILE, answers=BEFORE, people=PEOPLE, held=["look"])
print("=== before the switch")
for line in before.history:
    print("   ", line)
print("    timers:", before.timers)

converter = ExactPayloadConverter()
payload = converter.to_payload(state_as_data(before.state))
assert payload is not None
types = {name: field.declared for name, field in parse_case(CASE).fields.items()}
back = state_from_data(converter.from_payload(payload, dict), types)
same = back == before.state
print("\nstate read back equals the state written:", same)
if not same:
    for each in dataclasses.fields(back):
        if getattr(back, each.name) != getattr(before.state, each.name):
            print("    differs:", each.name)

# Go on from the state read back: the whole script from the start gives the reference.
whole = run_case(CASE, file=FILE, answers=[*BEFORE, *AFTER], people=PEOPLE, held=["look"])
print("\n=== the whole script with no switch: milestones", sorted(whole.state.milestones))
for line in whole.history[len(before.history) :]:
    print("   ", line)

events = script_events(AFTER[:4], PEOPLE, START)
resumed = run_case_in_memory(parse_case(CASE), CATALOG, FAKES, events, state=back)
print(
    "\n=== after the switch, from the state read back: milestones", sorted(resumed.state.milestones)
)
for line in resumed.history[len(before.history) :]:
    print("   ", line)

look = next(run for run in resumed.state.runs if run.entry == "look#1")
print("\nlook#1 still carries:", [s.said for s in look.steered])
print("seen's sources:", sorted(resumed.state.sources["seen"]))
expected = [
    line for line in whole.history[len(before.history) :] if "look#1" not in line or "chase" in line
]
got = resumed.history[len(before.history) :]
ok = (
    same
    and not resumed.state.milestones
    and look.steered
    and sum(line.startswith("pay#1 failed") for line in got) == 2  # refused again on its retry
    and "untrusted:customer" in resumed.state.sources["seen"]
    and got == expected
)
print()
if ok:
    print(
        "RESULT: HELD - the state reads back equal; after the switch the steered runs, the rule's "
        "start (retried by an operator and approved again too), the timer and the set value still "
        "carry untrusted:customer, and nothing is reached"
    )
else:
    print("RESULT: BROKEN - something steered was lost across continue-as-new (see above)")
