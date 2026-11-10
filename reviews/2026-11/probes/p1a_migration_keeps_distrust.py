# Shows whether migrating an open case to a release that drops `untrusted` marks (and renames the field) launders values the case already holds (D53, D12, D43).
"""Release 1 marks the opening's `note` and the event's `text` as `untrusted:customer`; a rule
copies `note` into `copy`; an activity steered by `note` is held running. Release 2 removes both
marks, removes the steered step's condition and gives it a milestone, adds rules that decide on
each value, a letter that sends `note` to a trusted-only input, and (second run) renames `note`
to `memo`. Release 2 also ADDS a mark to `email`, which was trusted. The case migrates while
open, then everything fires. Only `ventoux.testing`.
"""

import json
from typing import Any

from ventoux.testing import finish, migrate, release_of, run_case, send

PEOPLE = {"ana": ["support"], "lee": ["support-lead", "platform"], "pia": ["platform"]}


def titled(title: str) -> dict[str, Any]:
    return {"display": {"title": title}}


def release_1() -> dict[str, Any]:
    untrusted = {"source": "untrusted:customer"}
    return {
        "case": "probe",
        **titled("Probe"),
        "fields": {
            "note": {"type": "string", **titled("Note"), **untrusted},
            "email": {"type": "string", **titled("Email")},
            "order": {"type": "string", **titled("Order")},
            "copy": {"type": "string", **titled("Copy")},
        },
        "events": {
            "said": {
                **titled("Said"),
                "sent_by": {"system": "portal"},
                "payload": {"text": {"type": "string", **titled("Text"), **untrusted}},
            }
        },
        "milestones": {name: titled(name) for name in ("by_note", "by_text", "by_copy", "looked")},
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
                "activity": "orders.lookup@1",
                "when": {"==": [{"var": "note"}, "go"]},
                "inputs": {"order_id": {"var": "order"}},
            },
        },
        "rules": {
            "copy_it": {
                **titled("Copy"),
                "on": "opened",
                "then": {"set": {"copy": {"var": "note"}}},
            }
        },
    }


def release_2(rename: bool) -> dict[str, Any]:
    definition = release_1()
    del definition["fields"]["note"]["source"]
    del definition["events"]["said"]["payload"]["text"]["source"]
    del definition["steps"]["look"]["when"]
    definition["steps"]["look"]["reaches"] = ["looked"]
    definition["fields"]["email"]["source"] = "untrusted:customer"  # a mark the target adds
    for milestone, field in (("by_note", "note"), ("by_text", "said.text"), ("by_copy", "copy")):
        definition["rules"][f"on_{milestone}"] = {
            **titled(milestone),
            "on": {"answered": "hold"},
            "when": {"==": [{"var": field}, "go"]},
            "then": {"reach": [milestone]},
        }
    for name, field in (("letter", "note"), ("letter_2", "email")):
        definition["steps"][name] = {
            "kind": "activity",
            **titled(name),
            "activity": "letters.draft@2",
            "requires": ["hold"],
            "inputs": {"to_customer": {"var": field}, "template": "t"},
        }
    if rename:
        definition = json.loads(json.dumps(definition).replace('"note"', '"memo"'))
    return definition


broken = []
for rename in (False, True):
    target = release_of(release_2(rename), 2)
    mapping = {"fields": {"note": "memo"}} if rename else {}
    run = run_case(
        release_1(),
        file={"note": "go", "email": "a@example.com", "order": "ord-1"},
        answers=[
            send("said", {"text": "go"}, "system:portal"),
            migrate(target, mapping, "pia"),
            ("case.change#1", "approve", "lee"),
            finish("look#1"),
            ("hold", "ok", "ana"),
        ],
        people=PEOPLE,
        release=release_of(release_1(), 1),
        held=["look"],
    )
    print(f"\n=== migrated to release 2{', note renamed to memo' if rename else ''}")
    for line in run.history[6:]:
        print("   ", line)
    print("    milestones:", sorted(run.state.milestones))
    print("    sources:", {name: sorted(found) for name, found in run.state.sources.items()})
    if run.state.release != "probe 2":
        broken.append("the migration wasn't applied, so nothing was tested")
    if run.state.milestones:
        broken.append(f"reached {sorted(run.state.milestones)} after the migration")
    if any(line.startswith("scheduled letter") for line in run.history):
        broken.append("a letter was sent from a value that was untrusted, or newly marked")
    name = "memo" if rename else "note"
    for field in (name, "copy", "said.text", "email"):
        if "untrusted:customer" not in run.state.sources[field]:
            broken.append(f"{field} lost or never got untrusted:customer")

print()
if broken:
    print("RESULT: BROKEN - " + "; ".join(dict.fromkeys(broken)))
else:
    print(
        "RESULT: HELD - after the migration every value keeps its sources (under its new name "
        "too), the steered run still reaches nothing, the rules reach nothing, both letters are "
        "refused, and the mark release 2 adds to email is added to the value already held"
    )
