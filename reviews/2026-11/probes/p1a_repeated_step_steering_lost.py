# Shows whether a repeated step (for_each, D73) keeps what steered its runs (D39, D43), as a plain step does.
"""Four definitions, each run twice: once with a plain step (the control) and once with the same
step repeated over a list. In each the step's `when` reads `note`, which a customer typed
(`untrusted:customer`). Only public names and `ventoux.testing` are used, plus
`ventoux.case.definition.parse_case` and `ventoux.case.validate.validate_case` to ask the check.
"""

import copy
from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, run_case, send

NOTE_SAYS_GO = {"==": [{"var": "note"}, "go"]}
FILE = {
    "email": "a@example.com",
    "note": "go",
    "order": "ord-1",
    "lines": [{"sku": "A"}, {"sku": "B"}],
}


def case(repeated: bool) -> dict[str, Any]:
    """A letter drafted (once, or once per line) only when the customer's note says go."""
    draft: dict[str, Any] = {
        "kind": "activity",
        "display": {"title": "Draft a letter"},
        "activity": "letters.draft@2",  # to_customer is trusted_only()
        "when": NOTE_SAYS_GO,
        "inputs": {"to_customer": {"var": "email"}, "template": "t"},
    }
    if repeated:
        draft["for_each"] = {"over": "lines", "key": "sku"}
    return {
        "case": "probe",
        "display": {"title": "Probe"},
        "fields": {
            "email": {"type": "string", "display": {"title": "Email"}},
            "order": {"type": "string", "display": {"title": "Order"}},
            "note": {
                "type": "string",
                "display": {"title": "Note"},
                "source": "untrusted:customer",
            },
            "lines": {
                "type": "list",
                "display": {"title": "Lines"},
                "fields": {"sku": {"type": "string"}},
            },
        },
        "milestones": {"settled": {"display": {"title": "Settled"}}},
        "closes_when": ["settled"],
        "steps": {"draft": draft},
    }


def with_rule(repeated: bool) -> dict[str, Any]:
    """A rule on the draft's start reaches the milestone that closes the case."""
    definition = case(repeated)
    definition["rules"] = {
        "close_it": {
            "display": {"title": "Close"},
            "on": {"started": "draft"},
            "then": {"reach": ["settled"]},
        }
    }
    return definition


def with_requiring_step(repeated: bool) -> dict[str, Any]:
    """A second activity requires the draft and reaches the milestone that closes the case."""
    definition = case(repeated)
    definition["steps"]["settle"] = {
        "kind": "activity",
        "display": {"title": "Settle"},
        "activity": "letters.draft@2",
        "requires": ["draft"],
        "inputs": {"to_customer": {"var": "email"}, "template": "s"},
        "reaches": ["settled"],
    }
    return definition


def required_by_repeated(repeated: bool) -> dict[str, Any]:
    """A wait step the note steers; the draft (plain or repeated, no condition of its own)
    requires it, and sends a trusted-only input."""
    definition = case(repeated)
    del definition["steps"]["draft"]["when"]
    definition["events"] = {
        "ping": {"display": {"title": "Ping"}, "sent_by": {"system": "portal"}, "payload": {}}
    }
    definition["steps"]["listen"] = {
        "kind": "wait",
        "display": {"title": "Listen"},
        "event": "ping",
        "when": NOTE_SAYS_GO,
    }
    definition["steps"]["draft"]["requires"] = ["listen"]
    return definition


def show(title: str, build: Any, answers: list[Any]) -> dict[bool, Any]:
    print(f"\n=== {title}")
    runs = {}
    for repeated in (False, True):
        definition = build(repeated)
        issues = validate_case(parse_case(copy.deepcopy(definition)), CATALOG)
        run = run_case(definition, file=FILE, answers=answers, people={})
        runs[repeated] = run
        print(f"--- {'repeated over lines' if repeated else 'plain step (control)'}")
        print("    check:", [(i.severity, i.code, i.path) for i in issues] or "no issue")
        print("    status:", run.status, "| milestones:", sorted(run.state.milestones))
        for line in run.history[1:]:
            print("     ", line)
    return runs


broken = []
runs = show("1. the step's own untrusted `when` and a trusted-only input (D39)", case, [])
plain_refused = any("untrusted" in line for line in runs[False].needs_attention)
repeated_sent = any(line.startswith("scheduled draft.1#1") for line in runs[True].history)
print("plain refused:", plain_refused, "| repeated scheduled:", repeated_sent)
if plain_refused and repeated_sent:
    broken.append("an untrusted `when` chooses what a repeated step sends to a trusted-only input")

runs = show("2. a rule on the steered start reaches a closes_when milestone (D43)", with_rule, [])
if "settled" not in runs[False].state.milestones and "settled" in runs[True].state.milestones:
    broken.append("a rule on a repeated step's steered start reaches a milestone")


# The control's draft is refused by its input policy before it runs, so for 3 the control drafts
# through a step whose input policy takes anything: swap to compare like with like.
def requiring_loose(repeated: bool) -> dict[str, Any]:
    definition = with_requiring_step(repeated)
    definition["steps"]["draft"]["activity"] = "orders.lookup@1"
    definition["steps"]["draft"]["inputs"] = {"order_id": {"var": "order"}}
    return definition


runs = show("3. a step requiring the steered run reaches a milestone (D43)", requiring_loose, [])
if "settled" not in runs[False].state.milestones and "settled" in runs[True].state.milestones:
    broken.append("a step requiring a repeated step's steered runs reaches a milestone")

runs = show(
    "4. a repeated step requiring a steered run sends a trusted-only input (D43)",
    required_by_repeated,
    [send("ping", {}, "system:portal")],
)
plain_refused = any("untrusted" in line for line in runs[False].needs_attention)
repeated_sent = any(line.startswith("scheduled draft.1#1") for line in runs[True].history)
print("plain refused:", plain_refused, "| repeated scheduled:", repeated_sent)
if plain_refused and repeated_sent:
    broken.append("a repeated step requiring a steered run sends what a plain step is refused")

print()
if broken:
    print("RESULT: BROKEN - " + "; ".join(broken))
else:
    print("RESULT: HELD - a repeated step's runs carry what steered them, as a plain step's do")
