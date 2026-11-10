# Shows whether a `max_age` refresh (D33) of a step a rule started on untrusted data keeps what steered it (D43), or hands back a clean run, value and milestone.
"""`check` reads the order's status; nothing starts it but a rule, on the customer's text
(`untrusted:customer`). So its run is steered: it reaches nothing, a rule on its start reaches
nothing, and `check.status` carries `untrusted:customer` (D43). `confirm` sends `check.status` to
a trusted-only input, once a person has reviewed, and needs it at most a day old.
Three timelines, the same definition and the same people: the review answered at once; the review
answered three days later (so `check.status` is stale and fetched again); and no text from the
customer at all. Only `ventoux.testing`, plus `parse_case` and `validate_case` to ask the check.
"""

from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, later, run_case, send

PEOPLE = {"ana": ["support"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


CASE: dict[str, Any] = {
    "case": "probe",
    **titled("Probe"),
    "fields": {"order_id": {"type": "reference", "system": "orders", **titled("Order")}},
    "events": {
        "said": {
            **titled("Said"),
            "sent_by": {"system": "portal"},
            "payload": {
                "text": {"type": "string", **titled("Text"), "source": "untrusted:customer"}
            },
        }
    },
    "milestones": {name: titled(name) for name in ("reviewed", "checked", "began", "confirmed")},
    "stays_open": True,
    "close_reasons": {"duplicate": {**titled("Duplicate"), "roles": ["support"]}},
    "steps": {
        "review": {
            "kind": "task",
            **titled("Review"),
            "roles": ["support"],
            "outcomes": {"ok": {**titled("Ok"), "reaches": ["reviewed"]}},
        },
        "check": {
            "kind": "activity",
            **titled("Check"),
            "activity": "orders.lookup@2",  # status comes from system:orders
            "automatic": False,
            "inputs": {"order_id": {"var": "order_id"}},
            "reaches": ["checked"],
        },
        "confirm": {
            "kind": "activity",
            **titled("Confirm"),
            "activity": "letters.draft@2",  # to_customer is trusted_only()
            "requires": ["reviewed"],
            "inputs": {"to_customer": {"var": "check.status"}, "template": "t"},
            "max_age": {"check.status": "1d"},
            "reaches": ["confirmed"],
        },
    },
    "rules": {
        "on_text": {
            **titled("On the customer's text"),
            "on": {"event": "said"},
            "when": {"==": [{"var": "said.text"}, "go"]},
            "then": {"start": ["check"]},
        },
        "begin": {**titled("Begin"), "on": {"started": "check"}, "then": {"reach": ["began"]}},
    },
}
print("check:")
for issue in validate_case(parse_case(CASE), CATALOG):
    if issue.severity == "error":
        print(f"   {issue.code} {issue.path}: {issue.message}")

said = send("said", {"text": "go"}, "system:portal")
answered = ("review", "ok", "ana")
TIMELINES = {
    "the text, then the review at once": [said, answered],
    "the text, then the review three days later": [said, later("3d"), answered],
    "no text; the review three days later": [later("3d"), answered],
}
reached = {}
for title, answers in TIMELINES.items():
    run = run_case(
        CASE,
        file={"order_id": "ord-1"},
        answers=answers,
        people=PEOPLE,
        activities={"orders.lookup@2": lambda inputs: {"status": "delivered"}},
    )
    reached[title] = set(run.state.milestones)
    print(f"\n=== {title}")
    for line in run.history[2:]:
        print("   ", line)
    print("    milestones:", sorted(run.state.milestones))
    print("    check.status from:", sorted(run.state.sources.get("check.status", ())) or "not set")
    print("    needs attention:", run.needs_attention)

at_once, later_on, never = reached.values()
print()
if at_once == {"reviewed"} and never == {"reviewed"} and later_on > at_once:
    print(
        "RESULT: BROKEN - a day's wait launders what the customer's text started: the refresh's "
        f"run is clean, so the case reached {sorted(later_on - at_once)} and sent the trusted-only "
        "input, which it does neither at once nor without the text, and which the check claims "
        "can never happen"
    )
else:
    print("RESULT: HELD - the refresh's run keeps what steered the run it fetches again")
