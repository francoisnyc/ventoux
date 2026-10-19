"""Untrusted data decides through no moment: a run carries what steered it, and passes it on
(the fix of the untrusted moment).

Tests go through `run_case` and `validate_case`, and read what a run reports.
See docs/layers/fix-untrusted-moment.md and the brief, D43.
"""

import copy
from typing import Any

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_events import PEOPLE, SMALL, cancellable

from ventoux.testing import propose, run_case, send

PLEASE = "please cancel"  # the note that steers: what a customer typed
UNTRUSTED_NOTE = {"==": [{"var": "cancelled.note"}, PLEASE]}

GOODBYE = {
    "kind": "task",
    "display": {"title": "Call to say goodbye"},
    "roles": ["support"],
    "automatic": False,
    "outcomes": {"called": {"display": {"title": "Called"}}},
}


def rule(on: dict[str, str], then: dict[str, Any], when: Any = None) -> dict[str, Any]:
    """A rule as a definition writes it, with a title."""
    written = {"display": {"title": "A rule"}, "on": on, "then": then}
    return written | ({"when": when} if when is not None else {})


def say_goodbye(
    then: dict[str, Any] | None = None, steps: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The refund a customer can cancel: on the customer's note, a rule starts the goodbye call;
    `then` is what a second rule does on that call's start. `withdrawn` closes the case."""
    definition = cancellable()
    definition["steps"]["goodbye"] = copy.deepcopy(GOODBYE)
    definition["steps"] |= steps or {}
    definition["milestones"] = {"withdrawn": {"display": {"title": "Withdrawn"}}}
    definition["closes_when"] = ["withdrawn"]
    definition["rules"] = {
        "say_goodbye": rule({"event": "cancelled"}, {"start": ["goodbye"]}, UNTRUSTED_NOTE),
        "close_it": rule({"started": "goodbye"}, then or {"reach": ["withdrawn"]}),
    }
    return definition


def cancelled(note: str = PLEASE) -> Any:
    """The portal's `cancelled` event, carrying what the customer wrote."""
    return send("cancelled", {"note": note}, "system:portal")


# --- Slice 1: a rule on a steered start doesn't decide ---


def test_a_rule_on_a_start_untrusted_data_steered_reaches_nothing() -> None:
    # The tutor review's script: on main, the customer's note closed the case.
    run = run_case(say_goodbye(), file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert run.state.phase == "open"
    assert "withdrawn" not in run.state.milestones
    assert (
        "close_it#1 on started goodbye: reaches nothing: its moment comes from untrusted data: "
        "say_goodbye#1's condition, which started goodbye, reads cancelled.note "
        "(untrusted:customer), and untrusted data can't decide"
    ) in run.history


def test_a_start_its_own_untrusted_condition_steered_passes_it_on() -> None:
    # No rule starts it: the call starts by itself once the customer's note is in and says so,
    # and the rule on its start would close the case.
    definition = say_goodbye()
    definition["steps"]["listen"] = {
        "kind": "wait",
        "display": {"title": "Listen for the customer"},
        "event": "cancelled",
        "reaches": ["heard"],
    }
    definition["milestones"]["heard"] = {"display": {"title": "Heard from the customer"}}
    definition["steps"]["goodbye"] |= {"automatic": True, "requires": ["heard"]}
    definition["steps"]["goodbye"]["when"] = UNTRUSTED_NOTE
    del definition["rules"]["say_goodbye"]
    run = run_case(definition, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert run.state.phase == "open"
    assert (
        "close_it#1 on started goodbye: reaches nothing: its moment comes from untrusted data: "
        "goodbye's condition reads cancelled.note (untrusted:customer), and untrusted data can't "
        "decide"
    ) in run.history


def test_a_rule_on_a_start_untrusted_data_steered_stops_nothing() -> None:
    definition = say_goodbye({"stop": ["review"]})
    run = run_case(definition, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert "cancelled review#1: stopped by close_it#1" not in run.history
    assert run.waiting_for == ["review by support", "goodbye by support"]
    assert (
        "close_it#1 on started goodbye: stops nothing: its moment comes from untrusted data: "
        "say_goodbye#1's condition, which started goodbye, reads cancelled.note "
        "(untrusted:customer), and untrusted data can't decide"
    ) in run.history


def test_a_start_trusted_data_chose_still_decides() -> None:
    # The fix takes nothing away from a start nothing untrusted steered: the same rules, the
    # goodbye started on the arrival alone, or by a person, close the case.
    definition = say_goodbye()
    del definition["rules"]["say_goodbye"]["when"]
    run = run_case(definition, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert run.state.phase == "closed"
    assert "close_it#1 on started goodbye: reaching withdrawn" in run.history
    proposed = say_goodbye()
    proposed["steps"]["goodbye"]["proposed_by"] = ["support"]
    run = run_case(proposed, file=SMALL, answers=[propose("goodbye", "ana")], people=PEOPLE)
    assert run.state.phase == "closed"
