"""Untrusted data decides through no moment: a run carries what steered it, and passes it on
(the fix of the untrusted moment).

Tests go through `run_case` and `validate_case`, and read what a run reports.
See docs/layers/fix-untrusted-moment.md and the brief, D43.
"""

import copy
from typing import Any

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_events import PEOPLE, SMALL, cancellable

from ventoux.testing import later, propose, retry, run_case, send

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


# --- Slice 2: what a steered start passes on ---


def test_a_value_set_on_a_steered_start_carries_what_steered_it() -> None:
    # On main, `leaving` read as from the opener only, and a rule reading it closed the case.
    definition = say_goodbye({"set": {"leaving": {">": [{"var": "amount"}, 0]}}})
    definition["fields"]["leaving"] = {"type": "boolean", "display": {"title": "Leaving"}}
    definition["rules"]["close_on_review"] = rule(
        {"answered": "review"}, {"reach": ["withdrawn"]}, {"var": "leaving"}
    )
    answers = [cancelled(), ("review", "reject", "ana")]
    run = run_case(definition, file=SMALL, answers=answers, people=PEOPLE)
    assert run.state.sources["leaving"] == {"system:opener", "untrusted:customer"}
    assert (
        "close_it#1 on started goodbye: setting leaving, from system:opener, untrusted:customer"
    ) in run.history
    assert run.state.phase == "open"
    assert (
        "close_on_review#1 on answered review: reaches nothing: its condition reads leaving, from "
        "untrusted:customer, and untrusted data can't decide"
    ) in run.history


LETTER = {
    "kind": "activity",
    "display": {"title": "Draft a goodbye letter"},
    "activity": "letters.draft@2",
    "automatic": False,
    "inputs": {"to_customer": {"var": "order_id"}, "template": "goodbye"},
}


def test_a_step_started_on_a_steered_start_cant_send_what_its_policy_refuses() -> None:
    # On main, the letter was drafted: its address came from the opener, and the rule that
    # started it read nothing untrusted.
    definition = say_goodbye({"start": ["letter"]}, steps={"letter": LETTER})
    run = run_case(definition, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert run.needs_attention == [
        (
            "letter#1: letters.draft@2 takes to_customer only from a system or a person, never "
            "from untrusted data, and say_goodbye#1's condition, which started goodbye, reads "
            "cancelled.note (untrusted:customer)"
        )
    ]


def test_a_retried_rule_keeps_what_its_moment_carried() -> None:
    # The rule can't be read when goodbye starts (the review isn't answered yet), so it waits
    # for an operator; once it can be, its retry still doesn't act on that start.
    definition = say_goodbye()
    definition["rules"]["close_it"]["when"] = {"==": [{"var": "review.outcome"}, "reject"]}
    answers = [cancelled(), ("review", "reject", "ana"), retry("close_it#1", "omar")]
    run = run_case(definition, file=SMALL, answers=answers, people=PEOPLE)
    assert (
        "close_it#1 failed: close_it's condition review.outcome = \"reject\" can't be evaluated: "
        "review.outcome has no value"
    ) in run.history
    assert run.state.phase == "open"
    assert (
        "close_it#1 on started goodbye: reaches nothing: its moment comes from untrusted data: "
        "say_goodbye#1's condition, which started goodbye, reads cancelled.note "
        "(untrusted:customer), and untrusted data can't decide"
    ) in run.history


# --- Slice 3: a steered run ---

LOOKUP = {
    "kind": "activity",
    "display": {"title": "Look the order up again"},
    "activity": "orders.lookup@1",
    "automatic": False,
    "inputs": {"order_id": {"var": "order_id"}},
}


def starting(step: str, steps: dict[str, Any], rules: dict[str, Any] | None = None) -> Any:
    """The cancellable refund where the customer's note starts `step`, one of `steps`, and
    `rules` (none but that one, unless given) react; `withdrawn` closes the case."""
    definition = say_goodbye(steps=steps)
    del definition["steps"]["goodbye"]
    definition["rules"] = {
        "say_goodbye": rule({"event": "cancelled"}, {"start": [step]}, UNTRUSTED_NOTE),
        **(rules or {}),
    }
    return definition


STEERED_LOOKUP = (
    "say_goodbye#1's condition, which started lookup, reads cancelled.note (untrusted:customer)"
)


def test_a_steered_run_reaches_nothing() -> None:
    # On main, the lookup the customer's note started reached `withdrawn`, and the case closed.
    definition = starting("lookup", {"lookup": LOOKUP | {"reaches": ["withdrawn"]}})
    run = run_case(definition, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert run.state.phase == "open"
    assert "lookup#1 done, giving status from untrusted:customer, untrusted:undeclared" in (
        run.history
    )
    assert (
        f"lookup#1 reaches nothing: {STEERED_LOOKUP}, and untrusted data can't decide"
    ) in run.history


def test_a_steered_wait_reaches_nothing() -> None:
    # The wait ends on the next arrival, whatever it says; it started only on the first note.
    listen = {
        "kind": "wait",
        "display": {"title": "Listen for the customer again"},
        "event": "cancelled",
        "automatic": False,
        "reaches": ["withdrawn"],
    }
    definition = starting("listen", {"listen": listen})
    answers = [cancelled(), cancelled("anything")]
    run = run_case(definition, file=SMALL, answers=answers, people=PEOPLE)
    assert "listen#1 done: cancelled#2 arrived" in run.history
    assert run.state.phase == "open"
    assert (
        "listen#1 reaches nothing: say_goodbye#1's condition, which started listen, reads "
        "cancelled.note (untrusted:customer), and untrusted data can't decide"
    ) in run.history


def test_a_steered_runs_outcome_and_outputs_carry_what_steered_it() -> None:
    # On main, lookup.outcome read as from the contract only, and the rule reading it after a
    # person's answer closed the case.
    close_on_review = rule(
        {"answered": "review"},
        {"reach": ["withdrawn"]},
        {"==": [{"var": "lookup.outcome"}, "done"]},
    )
    definition = starting("lookup", {"lookup": LOOKUP}, {"close_on_review": close_on_review})
    answers = [cancelled(), ("review", "reject", "ana")]
    run = run_case(definition, file=SMALL, answers=answers, people=PEOPLE)
    assert run.state.sources["lookup.outcome"] == {"system:orders.lookup@1", "untrusted:customer"}
    assert run.state.sources["lookup.status"] == {"untrusted:customer", "untrusted:undeclared"}
    assert "withdrawn" not in run.state.milestones  # it closes with nothing left to do instead
    assert (
        "close_on_review#1 on answered review: reaches nothing: its condition reads "
        "lookup.outcome, from untrusted:customer, and untrusted data can't decide"
    ) in run.history


def test_a_step_requiring_a_steered_run_is_steered_by_it() -> None:
    # `after` starts by itself once the lookup is done; on main, a rule on its start closed the
    # case.
    after = {
        "kind": "task",
        "display": {"title": "Follow up"},
        "roles": ["support"],
        "requires": ["lookup"],
        "outcomes": {"done": {"display": {"title": "Done"}}},
    }
    close_on_after = rule({"started": "after"}, {"reach": ["withdrawn"]})
    definition = starting("lookup", {"lookup": LOOKUP, "after": after}, {"close": close_on_after})
    run = run_case(definition, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert "started after#1: waiting for done by support" in run.history
    assert run.state.phase == "open"
    assert (
        "close#1 on started after: reaches nothing: its moment comes from untrusted data: after "
        f"requires lookup, and {STEERED_LOOKUP}, and untrusted data can't decide"
    ) in run.history


def test_a_person_answering_a_steered_task_decides() -> None:
    # The person is where the influence ends (brief, D43): Ana's answer reaches `withdrawn`
    # through the task's outcome, and through a rule on her answer.
    on_answer = say_goodbye({"reach": ["withdrawn"]})
    on_answer["rules"]["close_it"]["on"] = {"answered": "goodbye"}
    answers = [cancelled(), ("goodbye", "called", "ana")]
    run = run_case(on_answer, file=SMALL, answers=answers, people=PEOPLE)
    assert "close_it#1 on answered goodbye: reaching withdrawn" in run.history
    assert run.state.phase == "closed"
    by_outcome = say_goodbye()
    del by_outcome["rules"]["close_it"]
    by_outcome["steps"]["goodbye"]["outcomes"]["called"]["reaches"] = ["withdrawn"]
    run = run_case(by_outcome, file=SMALL, answers=answers, people=PEOPLE)
    assert run.state.phase == "closed"
    assert run.state.sources["goodbye.outcome"] == {"person:ana"}


def test_an_approval_doesnt_end_what_steered_a_run() -> None:
    # Sam approves the lookup the customer's note started: he approves what it is sent, not what
    # other rules do once it starts, so the rule on its start still doesn't act.
    approved = LOOKUP | {"approval": {"roles": ["support-lead"], "display": {"reason": "Check"}}}
    close_on_start = rule({"started": "lookup"}, {"reach": ["withdrawn"]})
    definition = starting("lookup", {"lookup": approved}, {"close_it": close_on_start})
    answers = [cancelled(), ("lookup.approval#1", "approve", "sam")]
    run = run_case(definition, file=SMALL, answers=answers, people=PEOPLE)
    assert "sam answered lookup.approval#1 approve as support-lead" in run.history
    assert run.state.phase == "open"
    assert (
        f"close_it#1 on started lookup: reaches nothing: its moment comes from untrusted data: "
        f"{STEERED_LOOKUP}, and untrusted data can't decide"
    ) in run.history


def test_a_refresh_for_a_step_a_steered_run_admits_is_steered_by_it() -> None:
    # `confirm` needs `check.status` at most a day old and requires the lookup the note started.
    # Three days on, the note comes; once the lookup is done, `check` is fetched again for
    # `confirm`. On main, that refresh's start was a clean moment, and the rule on it closed the
    # case once Ana had answered the review.
    check = LOOKUP | {"automatic": True, "display": {"title": "Check the order"}}
    confirm = LOOKUP | {
        "automatic": True,
        "display": {"title": "Confirm the order"},
        "requires": ["lookup"],
        "inputs": {"order_id": {"var": "check.status"}},
        "max_age": {"check.status": "1d"},
    }
    close_on_check = rule(
        {"started": "check"}, {"reach": ["withdrawn"]}, {"exists": "review.outcome"}
    )
    steps = {"lookup": LOOKUP, "check": check, "confirm": confirm}
    definition = starting("lookup", steps, {"close_it": close_on_check})
    definition["stays_open"] = True  # so it waits, with nothing open, for the note
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "A duplicate"}, "roles": ["support"]}
    }
    answers = [later("3d"), ("review", "reject", "ana"), cancelled()]
    run = run_case(definition, file=SMALL, answers=answers, people=PEOPLE)
    assert "refreshing check.status for confirm: obtained 3 days ago, at most 1 day" in (
        run.history
    )
    assert run.state.phase == "open"
    assert (
        "close_it#2 on started check: reaches nothing: its moment comes from untrusted data: "
        f"confirm requires lookup, and {STEERED_LOOKUP}, and untrusted data can't decide"
    ) in run.history
