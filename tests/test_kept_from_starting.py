"""Untrusted data may keep something from happening, and the history says so (brief, D48).

Tests go through `run_case`, and read the history. See docs/layers/checkpoint-doors.md, row 33,
choice 6.
"""

from pathlib import Path
from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.validate import Issue
from ventoux.testing import CATALOG, load_definition, run_case, send

WITNESS = Path(__file__).parent.parent / "examples" / "witnesses"


def checked(source: str | None = "untrusted:customer") -> dict[str, Any]:
    """A case whose one task, `check`, starts by itself unless the opening's `note` says "skip";
    `note` is declared from `source`."""
    note: dict[str, Any] = {"type": "string", "display": {"title": "What the customer wrote"}}
    if source is not None:
        note["source"] = source
    return {
        "case": "checked",
        "display": {"title": "Checked"},
        "fields": {"note": note},
        "steps": {
            "check": {
                "kind": "task",
                "display": {"title": "Check the request"},
                "roles": ["support"],
                "when": {"!=": [{"var": "note"}, "skip"]},
                "outcomes": {"ok": {"display": {"title": "Checked"}}},
            }
        },
    }


def test_a_step_its_own_untrusted_condition_kept_from_starting_is_said() -> None:
    # The customer's note kept the check from starting: allowed (brief, D48), never silent. The
    # line names the step, the field and its source, never the value (brief, D30).
    run = run_case(checked(), file={"note": "skip"}, answers=[], people={})
    assert run.history[-2:] == [
        "check not started: its condition reads note, from untrusted:customer, and is false",
        "closed: nothing left to do",
    ]
    assert not any("skip" in line for line in run.history)


def test_a_step_that_starts_or_a_trusted_condition_says_nothing_new() -> None:
    started = run_case(checked(), file={"note": "go on"}, answers=[], people={})
    assert started.history[-1] == "started check#1: waiting for ok by support"
    trusted = run_case(checked(source=None), file={"note": "skip"}, answers=[], people={})
    assert trusted.history[-1:] == ["closed: nothing left to do"]
    assert not any("not started" in line for line in trusted.history)


def test_a_rule_its_untrusted_condition_kept_from_acting_is_said() -> None:
    # 11h's probe B6: a rule whose condition reads the customer's note, false, starts nothing.
    definition = load_definition(WITNESS / "untrusted-data-decides-nothing.json")
    del definition["rules"]["close_it"]
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 40},
        answers=[send("cancelled", {"note": "never mind"}, "system:portal")],
        people={},
    )
    # It names what the rule would have done, the step it would have started (brief, D48).
    assert run.history[-1] == (
        "say_goodbye#1 on event cancelled: its condition reads cancelled.note, from "
        "untrusted:customer, and is false: goodbye not started"
    )
    assert not any("never mind" in line for line in run.history)


def test_only_what_the_condition_kept_from_starting_is_said() -> None:
    # A step a person must propose, or one whose requirement never came, wasn't kept from
    # starting by its condition: no line claims it was.
    proposed = checked()
    proposed["steps"]["check"] |= {"automatic": False, "proposed_by": ["support"]}
    waiting = checked()
    waiting["milestones"] = {"asked": {"display": {"title": "Asked"}}}
    waiting["steps"]["check"]["requires"] = ["asked"]
    for definition in (proposed, waiting):
        run = run_case(definition, file={"note": "skip"}, answers=[], people={})
        assert run.history[-1] == "closed: nothing left to do"
        assert not any("not started" in line for line in run.history)


def test_a_rule_that_only_sets_names_the_field_it_kept_from_being_set() -> None:
    definition = load_definition(WITNESS / "untrusted-data-decides-nothing.json")
    del definition["rules"]["close_it"]
    definition["fields"]["cancel_note"] = {"type": "string", "display": {"title": "Cancel note"}}
    definition["rules"]["say_goodbye"]["then"] = {"set": {"cancel_note": {"var": "cancelled.note"}}}
    del definition["steps"]["goodbye"]  # nothing starts it now
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 40},
        answers=[send("cancelled", {"note": "never mind"}, "system:portal")],
        people={},
    )
    assert run.history[-1] == (
        "say_goodbye#1 on event cancelled: its condition reads cancelled.note, from "
        "untrusted:customer, and is false: cancel_note not set"
    )


# --- Layer 14c: said before any case runs, as a warning -----------------------------------------


def warnings_of(definition: dict[str, Any]) -> list[Issue]:
    """The `KEPT_FROM_STARTING` warnings validation gives `definition`, against the development
    catalog."""
    issues = validate_case(parse_case(definition), CATALOG)
    return [issue for issue in issues if issue.code == "KEPT_FROM_STARTING"]


def test_a_step_untrusted_data_may_keep_from_starting_is_warned_about() -> None:
    # Before any case runs, as the history says it once one closes (layer 14c, choice 37).
    [warning] = warnings_of(checked())
    assert warning.path == "steps.check.when"
    assert warning.severity == "warning"
    assert "note (untrusted:customer)" in warning.message
    assert "the case may close without it" in warning.message
    assert "skip" not in warning.message  # a definition's literal is shown, never a case's value


def test_a_trusted_condition_is_no_warning() -> None:
    assert warnings_of(checked(source=None)) == []


def test_a_step_the_case_cant_close_without_is_no_warning() -> None:
    # It reaches a milestone the case closes on: false keeps it from starting, and the case waits.
    definition = checked()
    definition["milestones"] = {"checked": {"display": {"title": "Checked"}}}
    definition["steps"]["check"]["reaches"] = ["checked"]
    definition["closes_when"] = ["checked"]
    assert warnings_of(definition) == []


def test_a_step_that_doesnt_start_by_itself_is_no_warning() -> None:
    # A step that waits to be proposed is a person's to start: its condition keeps nothing alone.
    definition = checked()
    definition["steps"]["check"]["automatic"] = False
    definition["steps"]["check"]["proposed_by"] = ["support"]
    assert warnings_of(definition) == []
