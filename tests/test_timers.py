"""Timers: time passing after a moment, set on it, fired as an event stamped with its own due time
(layer 11f).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md (11f), the brief, D44, and docs/guides/cases.md, "Rules on time".
"""

import copy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a helper there imports by
# its name.
from invariants import unshown
from test_fresh_facts import FILE as FRESH_FILE
from test_fresh_facts import PEOPLE as FRESH_PEOPLE
from test_fresh_facts import refund_fresh
from test_fresh_facts import run_case as run_fresh
from test_rules import endless_rework
from test_untrusted_moment import LETTER, PLEASE, cancelled, say_goodbye

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.memory import run_case_in_memory
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, Opened, Timer, TimerDue
from ventoux.case.timers import TimerRefused, next_due, utc
from ventoux.case.validate import validate_case
from ventoux.core.sensitive import Sensitive
from ventoux.core.validate import Issue
from ventoux.testing import (
    CATALOG,
    DAY,
    FAKES,
    START,
    close,
    later,
    load_definition,
    run_case,
    send,
)

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "omar": ["operations"]}
SMALL = {"order_id": "ord-1", "amount": 40}

# The guide's timer ("Rules on time"), and the step it starts.
CHASE_REVIEW = {
    "display": {"title": "Chase a review left open for two days"},
    "on": {"after": "2d", "since": {"started": "review"}},
    "then": {"start": ["chase"]},
}
CHASE = {
    "kind": "task",
    "display": {"title": "Chase the review"},
    "roles": ["support-lead"],
    "automatic": False,
    "outcomes": {"chased": {"display": {"title": "Review chased"}}},
}


def chased(on: object = None, **changes: Any) -> dict[str, Any]:
    """The quickstart's refund, with the guide's timer chasing a review left open; `on` replaces
    the timer's moment, and `changes` top-level keys."""
    definition = copy.deepcopy(REFUND) | copy.deepcopy(changes)
    definition["steps"]["chase"] = copy.deepcopy(CHASE)
    definition["rules"] = {"chase_review": copy.deepcopy(CHASE_REVIEW)}
    if on is not None:
        definition["rules"]["chase_review"]["on"] = on
    return definition


# --- Slice 1: the shape ---


@pytest.mark.parametrize(
    ("after", "message"),
    [
        ("2 days", 'an age looks like "30m", "12h" or "1d"'),
        ("-1d", 'an age looks like "30m", "12h" or "1d"'),
        ("0m", "a timer waits at least 1m: write a later age"),
    ],
)
def test_a_timer_waits_an_age_of_at_least_a_minute(after: str, message: str) -> None:
    on = {"after": after, "since": {"started": "review"}}
    with pytest.raises(CaseInvalid, match=f"^rules.chase_review.on.after: {message}$"):
        parse_case(chased(on))


def test_a_timer_is_never_set_on_another_timer() -> None:
    # `since` is one of the five other moments: a timer on a timer would be one more shape, never
    # a new reading of this one (brief, D44).
    nested = {"after": "1d", "since": {"after": "1d", "since": "opened"}}
    moments = (
        '"opened", {"started": <step>}, {"reached": <milestone>}, {"answered": <task>} or '
        '{"event": <event>}'
    )
    with pytest.raises(CaseInvalid, match=f"^rules.chase_review.on.since: a moment is {moments}$"):
        parse_case(chased(nested))


@pytest.mark.parametrize(
    ("since", "message"),
    [
        ({"started": "assess"}, "rules.chase_review.on.since.started: assess is not a step"),
        ({"reached": "paid"}, "rules.chase_review.on.since.reached: paid is not a milestone"),
        ({"answered": "pay"}, "rules.chase_review.on.since.answered: pay is not a task"),
        ({"event": "cancelled"}, "rules.chase_review.on.since.event: cancelled is not an event"),
    ],
)
def test_a_timer_since_what_the_case_doesnt_declare_is_refused(
    since: dict[str, str], message: str
) -> None:
    with pytest.raises(CaseInvalid, match=f"^{message}$"):
        parse_case(chased({"after": "2d", "since": since}))


def test_a_timer_names_its_age_and_its_moment() -> None:
    with pytest.raises(CaseInvalid, match="^rules.chase_review.on.since: required$"):
        parse_case(chased({"after": "2d"}))
    with pytest.raises(CaseInvalid, match="^rules.chase_review.on.at: not a field here$"):
        parse_case(chased({"after": "2d", "since": "opened", "at": "9am"}))


@pytest.mark.parametrize(
    "since",
    [
        "opened",
        {"started": "review"},
        {"answered": "review"},
        {"reached": "paid"},
        {"event": "cancelled"},
    ],
)
def test_a_timer_is_set_on_any_of_the_five_moments(since: object) -> None:
    definition = chased({"after": "30m", "since": since})
    definition["milestones"] = {"paid": {"display": {"title": "Paid"}}}
    definition["events"] = {
        "cancelled": {
            "display": {"title": "The customer cancels"},
            "sent_by": {"system": "portal"},
            "payload": {},
        }
    }
    parse_case(definition)


# --- Slice 2: setting and firing, in memory, in order ---


def opened(definition: dict[str, Any]) -> Any:
    """The case just opened at START: its state, with the review started and its timer set."""
    return run_case(definition, file=SMALL, answers=[], people=PEOPLE).state


def test_a_firing_for_a_timer_that_isnt_set_is_refused() -> None:
    # Only a driver makes a firing, from the state: one for no timer set is refused, and changes
    # nothing, never read as a moment that came (fail closed).
    case, state = parse_case(chased()), opened(chased())
    nowhere = TimerDue("chase_review", "started review#2", at=START + 2 * DAY)
    with pytest.raises(
        TimerRefused, match="^chase_review has no timer set on started review#2: nothing fires$"
    ):
        decide(case, CATALOG, state, nowhere)


def test_a_firing_stamped_with_another_time_is_refused() -> None:
    # A timer fires as an event stamped with its own due time, never "now" (brief, D44).
    case, state = parse_case(chased()), opened(chased())
    late = TimerDue("chase_review", "started review#1", at=START + 3 * DAY)
    with pytest.raises(
        TimerRefused,
        match="^chase_review, 2d after started review#1 is due at 2026-01-03T00:00:00Z, and this "
        "firing is stamped 2026-01-04T00:00:00Z: a timer fires at its due time$",
    ):
        decide(case, CATALOG, state, late)


def test_a_timer_is_set_when_its_moment_comes() -> None:
    run = run_case(chased(), file=SMALL, answers=[], people=PEOPLE)
    assert run.history[-2:] == [
        "started review#1: waiting for approve or reject by support",
        "set chase_review: 2d after started review#1, due 2026-01-03T00:00:00Z",
    ]
    assert not run.closed


def test_a_timer_fires_once_its_time_has_passed_and_its_rule_acts() -> None:
    run = run_case(chased(), file=SMALL, answers=[later("2d")], people=PEOPLE)
    assert run.history[-2:] == [
        "chase_review#1 on 2d after started review#1: starting chase",
        "started chase#1: waiting for chased by support-lead",
    ]
    # The review stays open: nothing is cancelled because time passed (brief, D17).
    assert run.waiting_for == ["review by support", "chase by support-lead"]


def test_a_timer_doesnt_fire_before_its_time() -> None:
    run = run_case(chased(), file=SMALL, answers=[later("47h")], people=PEOPLE)
    assert not any(line.startswith("chase_review#") for line in run.history)


def test_the_firing_is_stamped_with_its_due_time() -> None:
    # Time moves on three days; the timer, due on the second, fires stamped then, never "now"
    # (brief, D33) (brief, D44). The driver asks for the firings due by a time, one at a time.
    state = opened(chased())
    assert next_due(state, START + 3 * DAY) == TimerDue(
        "chase_review", "started review#1", at=START + 2 * DAY
    )
    assert next_due(state, START + 2 * DAY - 1) is None


def test_a_timer_due_with_an_event_fires_before_it() -> None:
    # Due on the second at midnight, with Ana's answer stamped that same second: the timer fires
    # first, since the answer came during that second and the timer was due at its start.
    case = parse_case(chased())
    answered = Answered(
        "review",
        "approve",
        "ana",
        frozenset({"support"}),
        {"approved_amount": Sensitive(Decimal(40))},  # sealed, as the client sends every value
        at=START + 2 * DAY,
    )
    opening = Opened({"order_id": "ord-1", "amount": Decimal(40)}, None, at=START)
    run = run_case_in_memory(case, CATALOG, FAKES, [opening, answered])
    fired = run.history.index("chase_review#1 on 2d after started review#1: starting chase")
    assert fired < run.history.index(
        "ana answered review#1 approve as support, setting approved_amount"
    )


def test_timers_fire_soonest_first_and_in_the_order_set_at_one_second() -> None:
    definition = chased()
    definition["steps"]["note"] = {
        "kind": "task",
        "display": {"title": "Note the wait"},
        "roles": ["support"],
        "automatic": False,
        "repeatable": True,
        "outcomes": {"noted": {"display": {"title": "Noted"}}},
    }
    definition["rules"] = {
        "late": {
            "display": {"title": "Late"},
            "on": {"after": "3d", "since": "opened"},
            "then": {"start": ["chase"]},
        },
        "first": {
            "display": {"title": "First"},
            "on": {"after": "1d", "since": "opened"},
            "then": {"start": ["note"]},
        },
        "second": {
            "display": {"title": "Second"},
            "on": {"after": "24h", "since": "opened"},
            "then": {"stop": ["note"]},
        },
    }
    run = run_case(definition, file=SMALL, answers=[later("5d")], people=PEOPLE)
    # `late` was set first and is due last; `first` and `second` are due the same second, and fire
    # in the order they were set, which is the order they are written.
    fired = [
        line.split(" on ")[0]
        for line in run.history
        if line.startswith(("late#", "first#", "second#"))
    ]
    assert fired == ["first#1", "second#1", "late#1"]


def test_a_timer_falling_due_at_the_end_of_the_script_fires() -> None:
    # `later` moves time on even with nothing after it: what falls due by then fires.
    run = run_case(chased(), file=SMALL, answers=[later("3d")], people=PEOPLE)
    assert "started chase#1: waiting for chased by support-lead" in run.history


def test_a_timer_set_while_time_moves_on_fires_in_turn() -> None:
    # The first timer starts the chase; a timer on the chase's start falls due before time stops
    # moving, so it fires too, in its turn.
    definition = chased()
    definition["rules"]["remind_lead"] = {
        "display": {"title": "Remind the team lead"},
        "on": {"after": "1h", "since": {"started": "chase"}},
        "then": {"stop": ["chase"]},
    }
    run = run_case(definition, file=SMALL, answers=[later("3d")], people=PEOPLE)
    assert run.history.index(
        "set remind_lead: 1h after started chase#1, due 2026-01-03T01:00:00Z"
    ) < (run.history.index("remind_lead#1 on 1h after started chase#1: stopping chase"))


def test_a_timers_condition_is_read_when_it_fires() -> None:
    # Set as the review starts, when nothing is approved; read two days later, on the case file
    # then: Ana approved 250 on the first day (brief, D38) (brief, D44).
    definition = chased()
    definition["rules"]["chase_review"]["on"] = {"after": "2d", "since": "opened"}
    definition["rules"]["chase_review"]["when"] = {">": [{"var": "approved_amount"}, 100]}
    definition["steps"]["pay"]["approval"]["roles"] = ["support-lead"]
    big = ("review", "approve", "ana", {"approved_amount": 250})
    run = run_case(definition, file=SMALL, answers=[later("1d"), big, later("1d")], people=PEOPLE)
    assert "chase_review#1 on 2d after opened: starting chase" in run.history


def test_due_times_read_as_dates_in_utc() -> None:
    # Worked out by hand in `case`, which imports no `datetime` (layer 0's boundary): checked here
    # against Python's own, over leap years and centuries.
    from datetime import UTC, datetime

    for seconds in (0, START, 951_782_400, 4_107_542_399, 1_709_164_800, 253_402_300_799, 86_399):
        assert utc(seconds) == datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Slice 3: a timer ends with its purpose, and with any close ---

APPROVED = ("review", "approve", "ana", {"approved_amount": 40})
CLOSABLE = {"duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}}


def down(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("orders unreachable")


def test_a_timer_set_on_a_run_ends_with_it() -> None:
    # Ana answers on the first day: the review is done, and the chase has no purpose left. It
    # needs no `when` saying "if the review is still open" (brief, D44).
    run = run_case(
        chased(), file=SMALL, answers=[later("1d"), APPROVED, later("2d")], people=PEOPLE
    )
    assert "cancelled chase_review, 2d after started review#1: review#1 is done" in run.history
    assert not any(line.startswith("chase_review#") for line in run.history)
    assert run.closed and run.timers == []


def test_a_stopped_runs_timers_end_with_it() -> None:
    # A rule stops the review: the run is cancelled, and its timer with it (brief, D40).
    definition = chased()
    definition["events"] = {
        "cancelled": {
            "display": {"title": "Cancelled"},
            "sent_by": {"system": "portal"},
            "payload": {},
        }
    }
    definition["rules"]["withdraw"] = {
        "display": {"title": "Withdraw"},
        "on": {"event": "cancelled"},
        "then": {"stop": ["review"]},
    }
    run = run_case(
        definition, file=SMALL, answers=[send("cancelled", {}, "system:portal")], people=PEOPLE
    )
    assert "cancelled chase_review, 2d after started review#1: review#1 is cancelled" in run.history
    assert run.closed


def test_a_failed_runs_timer_stays_set() -> None:
    # A failed run waits for a person, and an operator's retry runs it again as the same run, so
    # it hasn't ended for its timers: the lead is still told (brief, D17) (D40, as amended).
    definition = chased({"after": "1h", "since": {"started": "look_up"}})
    definition["steps"]["look_up"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    run = run_case(
        definition,
        file=SMALL,
        answers=[later("2h")],
        people=PEOPLE,
        activities={"orders.lookup@1": down},
    )
    assert run.needs_attention[0].startswith("look_up#1: orders.lookup@1 failed")
    assert "chase_review#1 on 1h after started look_up#1: starting chase" in run.history


def test_a_timer_set_on_an_instant_keeps_the_case_open_until_it_fires() -> None:
    # Set on the review's answer, it lives until it fires: the paid refund stays open, and the
    # case map would say so (brief, D10: "a rule that fires 30 days after payment keeps the case
    # open 30 days").
    definition = chased({"after": "30d", "since": {"answered": "review"}})
    paid = run_case(definition, file=SMALL, answers=[APPROVED, later("29d")], people=PEOPLE)
    assert paid.reached("pay") and not paid.closed
    assert paid.timers == ["chase_review: 30d after answered review#1, due 2026-01-31T00:00:00Z"]
    fired = run_case(definition, file=SMALL, answers=[APPROVED, later("30d")], people=PEOPLE)
    assert "chase_review#1 on 30d after answered review#1: starting chase" in fired.history


def test_a_close_cancels_every_timer() -> None:
    run = run_case(
        chased(close_reasons=CLOSABLE),
        file=SMALL,
        answers=[close("duplicate", "ana"), later("3d")],
        people=PEOPLE,
    )
    assert (
        "cancelled chase_review, 2d after started review#1: closed as duplicate by ana"
    ) in run.history
    assert run.closed and not any(line.startswith("chase_review#") for line in run.history)


def test_a_timer_due_as_the_case_closes_fires_first() -> None:
    # Due the very second Ana closes the case: it fires first, and its chase is then cancelled
    # by the close, each said; never lost (brief, D44).
    run = run_case(
        chased(close_reasons=CLOSABLE),
        file=SMALL,
        answers=[later("2d"), close("duplicate", "ana")],
        people=PEOPLE,
    )
    assert run.history.index("chase_review#1 on 2d after started review#1: starting chase") < (
        run.history.index("ana closed the case as duplicate, as support")
    )
    assert "cancelled chase#1: closed as duplicate by ana" in run.history


def holding(**changes: Any) -> dict[str, Any]:
    """The refund with a lookup beside the review that fails, closing once paid: paid reached,
    the failed lookup holds the close (brief, D34)."""
    definition = chased(on={"after": "5d", "since": "opened"}) | changes
    definition["steps"]["look_up"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    definition["milestones"] = {"paid": {"display": {"title": "Paid"}}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["closes_when"] = ["paid"]
    return definition


def test_a_held_close_cancels_every_timer() -> None:
    # Nothing new is decided while a failed run holds the close, and the hold never goes back to
    # deciding: the timer could never act, so it is cancelled, once (brief, D34) (brief, D44).
    run = run_case(
        holding(),
        file=SMALL,
        answers=[APPROVED, later("6d")],
        people=PEOPLE,
        activities={"orders.lookup@1": down},
    )
    assert run.status == "open" and "reached paid" in run.history
    assert (
        "cancelled chase_review, 5d after opened: paid is reached, so the case closes and "
        "nothing new is decided"
    ) in run.history
    assert run.timers == [] and not any(line.startswith("chase_review#") for line in run.history)


def test_a_timer_isnt_set_once_nothing_new_is_decided() -> None:
    # Its moment is the very one that completes closes_when: a timer set then could never act.
    definition = holding()
    definition["rules"]["chase_review"]["on"] = {"after": "1d", "since": {"reached": "paid"}}
    run = run_case(definition, file=SMALL, answers=[APPROVED], people=PEOPLE)
    assert (
        "chase_review on reached paid: not set: paid is reached, so the case closes and nothing "
        "new is decided"
    ) in run.history
    assert run.closed


# --- Slice 4: what a report shows, and nothing pending is silent ---


def test_a_report_lists_set_timers_soonest_first_never_in_waiting_for() -> None:
    # A timer waits on nobody, so it is not in `waiting_for` (brief, D24); `timers` lists each
    # one set, soonest first, with its due time: the view a due date reads (brief, D44).
    definition = chased()
    definition["rules"]["early"] = {
        "display": {"title": "Early"},
        "on": {"after": "12h", "since": "opened"},
        "then": {"start": ["chase"]},
    }
    run = run_case(definition, file=SMALL, answers=[], people=PEOPLE)
    assert run.waiting_for == ["review by support"]
    assert run.timers == [
        "early: 12h after opened, due 2026-01-01T12:00:00Z",
        "chase_review: 2d after started review#1, due 2026-01-03T00:00:00Z",
    ]


def test_the_invariant_finds_a_timer_that_outlived_its_purpose() -> None:
    # Read on states the runtime never leaves, so the invariant can't pass them either: a timer
    # set on a run that has ended, and one set while the close is held.
    case = parse_case(chased())
    run = run_case(chased(), file=SMALL, answers=[], people=PEOPLE)
    assert unshown(case, run.state) == []
    next(r for r in run.state.runs if r.entry == "review#1").status = "done"
    assert unshown(case, run.state) == [
        "chase_review, 2d after started review#1 is set, and review#1 has ended"
    ]
    held = run_case(
        holding(),
        file=SMALL,
        answers=[APPROVED],
        people=PEOPLE,
        activities={"orders.lookup@1": down},
    )
    held.state.timers.append(Timer("chase_review", "5d", "opened", START + 5 * DAY))
    assert unshown(parse_case(holding()), held.state) == [
        "chase_review, 5d after opened is set, and the close is held: it can never act"
    ]


# --- Slice 5: trust ---


def test_a_timer_on_a_start_untrusted_data_steered_reaches_nothing() -> None:
    # The goodbye call starts on what the customer typed; a day later, a timer on its start
    # would close the case. Time passing doesn't clean what steered the run (brief, D43) (brief,
    # D44): the rule on it reaches nothing, saying what steered, never the note.
    definition = say_goodbye()
    definition["rules"]["close_it"]["on"] = {"after": "1d", "since": {"started": "goodbye"}}
    run = run_case(definition, file=SMALL, answers=[cancelled(), later("1d")], people=PEOPLE)
    assert run.state.phase == "open" and "withdrawn" not in run.state.milestones
    assert (
        "close_it#1 on 1d after started goodbye#1: reaches nothing: its moment comes from "
        "untrusted data: say_goodbye#1's condition, which started goodbye, reads cancelled.note "
        "(untrusted:customer), and untrusted data can't decide"
    ) in run.history
    assert PLEASE not in "\n".join(run.history)


def test_a_timer_on_a_steered_start_sets_a_value_that_carries_it() -> None:
    definition = say_goodbye({"set": {"leaving": {"var": "amount"}}})
    definition["fields"]["leaving"] = {"type": "number", "display": {"title": "Leaving with"}}
    definition["rules"]["close_it"]["on"] = {"after": "1d", "since": {"started": "goodbye"}}
    run = run_case(definition, file=SMALL, answers=[cancelled(), later("1d")], people=PEOPLE)
    assert "untrusted:customer" in run.state.sources["leaving"]


def test_time_passing_after_an_arrival_is_a_fact() -> None:
    # The event's arrival is a fact, whatever it carries (brief, D41): a timer set on it carries
    # nothing, so its rule decides, the note unread.
    definition = say_goodbye()
    definition["rules"]["close_it"]["on"] = {"after": "1d", "since": {"event": "cancelled"}}
    run = run_case(definition, file=SMALL, answers=[cancelled(), later("1d")], people=PEOPLE)
    assert "close_it#1 on 1d after event cancelled#1: reaching withdrawn" in run.history
    assert run.closed


# --- Slice 6: validation stays a proof ---


def issues(definition: dict[str, Any], *codes: str) -> list[Issue]:
    """What `ventoux check` says of a definition, only the issues with `codes` if any are given."""
    found = validate_case(parse_case(definition), CATALOG)
    return [issue for issue in found if not codes or issue.code in codes]


def test_check_reads_the_guides_timer() -> None:
    # Before 11f a moment the check didn't know was refused, never read as the opening (fail
    # closed); a timer is known now, and the guide's gets no issue.
    assert issues(chased()) == []


def test_a_timer_whose_moment_never_comes_never_fires() -> None:
    definition = chased({"after": "1d", "since": {"reached": "escalated"}})
    definition["milestones"] = {"escalated": {"display": {"title": "Escalated"}}}
    assert issues(definition, "NEVER_FIRES") == [
        Issue(
            "rules.chase_review.on",
            "NEVER_FIRES",
            "chase_review can never fire: it fires on 1d after reached escalated, which no step "
            "or rule reaches: reach escalated from a step or a rule, or fire it on another moment",
        )
    ]


def test_a_timer_on_the_last_closes_when_milestone_never_acts() -> None:
    # Shown with a run in slice 3: its moment comes as the case closes, and it isn't set.
    definition = holding()
    definition["rules"]["chase_review"]["on"] = {"after": "1d", "since": {"reached": "paid"}}
    assert issues(definition, "NEVER_FIRES") == [
        Issue(
            "rules.chase_review.on",
            "NEVER_FIRES",
            "chase_review can never act: it fires on 1d after reached paid, and refund closes "
            "once paid is reached, when nothing new is decided: fire it on an earlier moment, or "
            "remove paid from closes_when",
        )
    ]


def waiting_a_day() -> dict[str, Any]:
    """The refund whose review nobody starts as it opens: a timer on the opening starts it a day
    later."""
    definition = chased()
    definition["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    definition["rules"] = {
        "open_review": {
            "display": {"title": "Open the review a day later"},
            "on": {"after": "1d", "since": "opened"},
            "then": {"start": ["review"]},
        }
    }
    del definition["steps"]["chase"]
    return definition


def test_a_timer_set_as_the_case_opens_keeps_it_open() -> None:
    # Nothing starts by itself, but the timer is set as the case opens: pending work, so the case
    # doesn't close at once, and the check doesn't say it does (brief, D10) (brief, D44).
    assert issues(waiting_a_day(), "CLOSES_AT_OPENING") == []
    opened_only = run_case(waiting_a_day(), file=SMALL, answers=[], people=PEOPLE)
    assert not opened_only.closed
    a_day_on = run_case(waiting_a_day(), file=SMALL, answers=[later("1d")], people=PEOPLE)
    assert a_day_on.waiting_for == ["review by support"]
    # The same set on a milestone a rule on the opening reaches: set as it opens, too.
    triaged = waiting_a_day()
    triaged["milestones"] = {"triaged": {"display": {"title": "Triaged"}}}
    triaged["rules"]["triage"] = {
        "display": {"title": "Triage"},
        "on": "opened",
        "then": {"reach": ["triaged"]},
    }
    triaged["rules"]["open_review"]["on"] = {"after": "1d", "since": {"reached": "triaged"}}
    assert issues(triaged, "CLOSES_AT_OPENING") == []
    assert not run_case(triaged, file=SMALL, answers=[], people=PEOPLE).closed
    # Without the timer it would close at once, and the check says so, as before.
    definition = waiting_a_day()
    del definition["rules"]
    assert [i.code for i in issues(definition, "CLOSES_AT_OPENING")] == ["CLOSES_AT_OPENING"]


def test_a_timer_reads_what_may_be_set_by_then() -> None:
    # On the opening itself, a rule reading what only a person sets fails every time
    # (`SET_AFTER`). Two days later the person may have answered: shown with a run in slice 2,
    # so the check only warns (brief, D37).
    definition = chased({"after": "2d", "since": "opened"})
    definition["rules"]["chase_review"]["when"] = {">": [{"var": "approved_amount"}, 100]}
    assert issues(definition, "SET_AFTER", "MAY_BE_UNSET") == [
        Issue(
            "rules.chase_review.when",
            "MAY_BE_UNSET",
            "chase_review reads approved_amount, which may not be set when 2d after opened "
            "comes: then chase_review fails and needs attention: read it only when it is set, or "
            "fire it on another moment",
            "warning",
        )
    ]
    # Set on the answer, what the answer gives is set when it fires.
    answered = chased({"after": "2d", "since": {"answered": "review"}})
    answered["rules"]["chase_review"]["when"] = {"==": [{"var": "review.outcome"}, "approve"]}
    assert issues(answered) == []


def test_a_step_reading_what_only_a_timer_after_it_sets_fails_every_time() -> None:
    # `flagged` is set only by a timer on the follow-up's answer, and the follow-up reads it as it
    # starts: it fails every time (`SET_AFTER`), as the run shows.
    definition = copy.deepcopy(REFUND)
    definition["fields"]["flagged"] = {"type": "boolean", "display": {"title": "Flagged"}}
    definition["steps"]["follow_up"] = {
        "kind": "task",
        "display": {"title": "Follow up"},
        "roles": ["support"],
        "when": {"var": "flagged"},
        "outcomes": {"done": {"display": {"title": "Done"}}},
    }
    definition["rules"] = {
        "flag": {
            "display": {"title": "Flag it"},
            "on": {"after": "1h", "since": {"answered": "follow_up"}},
            "then": {"set": {"flagged": {"var": "amount"}}},
        }
    }
    definition["rules"]["flag"]["then"]["set"]["flagged"] = {">": [{"var": "amount"}, 0]}
    assert [(i.path, i.code) for i in issues(definition, "SET_AFTER")] == [
        ("steps.follow_up.when", "SET_AFTER")
    ]
    run = run_case(definition, file=SMALL, answers=[], people=PEOPLE)
    assert run.needs_attention[0].startswith("follow_up#1: ")


def test_check_follows_what_steered_a_timers_start() -> None:
    definition = say_goodbye()
    definition["rules"]["close_it"]["on"] = {"after": "1d", "since": {"started": "goodbye"}}
    assert issues(definition, "UNTRUSTED_TRIGGER", "WRITER_DECIDES") == [
        Issue(
            "rules.close_it.on",
            "UNTRUSTED_TRIGGER",
            "close_it fires on 1d after started goodbye, which untrusted data steers however "
            "goodbye starts (untrusted:customer), and untrusted data can't decide, so it never "
            "reaches withdrawn: start goodbye only on trusted data, or let a person decide in a "
            "task",
        )
    ]
    # A person may propose the call too: then only some of its starts are steered, a warning.
    definition["steps"]["goodbye"]["proposed_by"] = ["support"]
    assert [
        (i.code, i.severity) for i in issues(definition, "UNTRUSTED_TRIGGER", "WRITER_DECIDES")
    ] == [("WRITER_DECIDES", "warning")]


def test_check_refuses_an_input_a_timer_on_a_steered_start_would_send() -> None:
    definition = say_goodbye({"start": ["letter"]}, steps={"letter": LETTER})
    definition["rules"]["close_it"]["on"] = {"after": "1d", "since": {"started": "goodbye"}}
    assert issues(definition, "INPUT_POLICY") == [
        Issue(
            "rules.close_it.then.start",
            "INPUT_POLICY",
            "letter fails on its inputs every time close_it starts it: letters.draft@2 takes "
            "to_customer only from a system or a person, never from untrusted data, and close_it "
            "fires on 1d after started goodbye, which untrusted data steers (untrusted:customer): "
            "start goodbye only on trusted data, or let a person decide in a task",
        )
    ]
    run = run_case(definition, file=SMALL, answers=[cancelled(), later("1d")], people=PEOPLE)
    assert run.needs_attention[0].startswith("letter#1: letters.draft@2 takes to_customer")


def test_a_timer_on_its_steps_start_can_never_start_it() -> None:
    # Set on the review's start, it lives only while that run does: the review is running
    # whenever it fires, so its start is refused every time (`NEVER_STARTS`).
    definition = chased()
    definition["rules"]["chase_review"]["then"] = {"start": ["review"]}
    definition["steps"]["review"]["repeatable"] = True
    del definition["steps"]["chase"]
    assert issues(definition, "NEVER_STARTS") == [
        Issue(
            "rules.chase_review.then.start",
            "NEVER_STARTS",
            "chase_review can never start review: it fires on 2d after started review, while "
            "review is running: start it on another moment",
        )
    ]
    run = run_case(definition, file=SMALL, answers=[later("2d")], people=PEOPLE)
    assert any(
        line.startswith("chase_review#1 on 2d after started review#1: review not started")
        for line in run.history
    )


def test_a_timer_cant_re_arm_itself() -> None:
    # The would-be loop: a lookup that starts again an hour after it starts. Its timer lives only
    # while its run does, and the run is done first, so it ends: nothing to claim (brief, D44).
    definition = copy.deepcopy(REFUND)
    definition["steps"]["look_up"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "repeatable": True,
        "proposed_by": ["support"],
    }
    definition["rules"] = {
        "again": {
            "display": {"title": "Look it up again"},
            "on": {"after": "1h", "since": {"started": "look_up"}},
            "then": {"start": ["look_up"]},
        }
    }
    assert issues(definition, "NEVER_CLOSES", "LOOPS_UNTIL_CLOSED") == []
    run = run_case(definition, file=SMALL, answers=[APPROVED, later("1d")], people=PEOPLE)
    assert "cancelled again, 1h after started look_up#1: look_up#1 is done" in run.history
    assert run.closed


def test_a_timer_that_may_stop_a_loop_lets_it_end() -> None:
    # The endless rework never closes; a timer that may stop the review lets the loop end, as any
    # rule that may stop does (brief, D40): the check claims no NEVER_CLOSES.
    definition = endless_rework()
    assert [i.code for i in issues(definition, "NEVER_CLOSES")] == ["NEVER_CLOSES"]
    definition["rules"]["give_up"] = {
        "display": {"title": "Give up on a slow review"},
        "on": {"after": "5d", "since": {"started": "review"}},
        "then": {"stop": ["review"]},
    }
    assert issues(definition, "NEVER_CLOSES", "LOOPS_UNTIL_CLOSED") == []
    run = run_case(definition, file=SMALL, answers=[later("5d")], people=PEOPLE)
    assert run.closed


# --- Slice 8: staleness noticed sooner, by a timer an author writes ---


def looked_up_again() -> dict[str, Any]:
    """The case data guide's fresh refund, whose payment needs the order's status at most a day
    old, with a timer looking the order up again a day after the review is answered: the guide's
    "Noticing a stale fact sooner"."""
    definition = refund_fresh()
    definition["steps"]["check_order"]["repeatable"] = True
    definition["rules"] = {
        "look_again": {
            "display": {"title": "Look the order up again a day after the review"},
            "on": {"after": "1d", "since": {"answered": "review"}},
            "then": {"start": ["check_order"]},
        }
    }
    return definition


BIG = ("review", "approve", "ana", {"approved_amount": 250})


def test_a_timer_an_author_writes_fetches_a_read_again_before_anyone_acts() -> None:
    # The engine sets no timer for a fact's age (brief, D44). Without one, the stale status is
    # noticed only when Sam approves on the second day, and fetched again then (brief, D33).
    plain = run_fresh(
        refund_fresh(), FRESH_FILE, [BIG, later("2d"), ("pay", "approve", "sam")], FRESH_PEOPLE
    )
    assert plain.history.index("sam answered pay.approval#1 approve as support-lead") < (
        plain.history.index(
            "refreshing check_order.status for pay: obtained 2 days ago, at most 1 day"
        )
    )
    # With the author's timer the order is looked up again on the first day: the approval asked
    # on the old status is withdrawn as its requirement starts again, and asked again on the
    # fresh one, so Sam approves on a fact a day old, and nothing is fetched as he acts.
    run = run_fresh(
        looked_up_again(),
        FRESH_FILE,
        [BIG, later("1d"), later("1d"), ("pay", "approve", "sam")],
        FRESH_PEOPLE,
    )
    assert appears_in_order(
        [
            "look_again#1 on 1d after answered review#1: starting check_order",
            "scheduled check_order#2: orders.lookup@2 (order_id from system:opener)",
            "withdrew pay.approval#1: check_order started again",
            "check_order#2 done, giving status from system:orders",
            "asked pay.approval#2: approval of pay by support-lead",
            "sam answered pay.approval#2 approve as support-lead",
        ],
        run.history,
    )
    assert not any(line.startswith("refreshing") for line in run.history)
    assert run.reached("pay")


def appears_in_order(lines: list[str], history: list[str]) -> bool:
    """Whether each of `lines` is in `history`, in the same order (others may come between)."""
    rest = iter(history)
    return all(line in rest for line in lines)


def test_an_open_approval_follows_what_the_timers_read_gives() -> None:
    # The second look-up finds the order lost: the approval asked on what the first one said is
    # withdrawn before Sam acts on it, and the payment's condition is false now (brief, D25).
    statuses = iter(["delivered", "lost"])
    lookup = {"orders.lookup@2": lambda inputs: {"status": next(statuses)}}
    run = run_fresh(
        looked_up_again(), FRESH_FILE, [BIG, later("1d")], FRESH_PEOPLE, activities=lookup
    )
    assert "withdrew pay.approval#1: check_order started again" in run.history
    assert "asked pay.approval#2: approval of pay by support-lead" not in run.history
    assert run.closed  # the order is lost: nothing is paid, and nothing is left to do
