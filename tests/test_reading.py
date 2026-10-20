"""Reading rules: each rule in plain words, worked out from the definition alone (layer 11g1).

Tests go through `parse_case` and `read_rules`, and, for each part a reading says, through
`run_case`, so a reading and the engine can't drift apart.
See docs/layers/11-rules.md (11g), the brief, D45, and docs/guides/cases.md, "Reading rules".
"""

import copy
from collections.abc import Callable
from typing import Annotated, Any, get_args, get_origin

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_timers import APPROVED, CLOSABLE, NOTED, PEOPLE, SMALL, chased, down

from ventoux.case.definition import RuleMoment, Then, parse_case
from ventoux.case.reading import CLAUSES, ReadingRefused, read_rules
from ventoux.testing import close, later, run_case, send

# --- Slice 1: the moments ---


def test_a_shape_the_reader_doesnt_know_is_refused() -> None:
    # `parse_case` refuses an unknown moment first; this is a definition that didn't come through
    # it. Fail closed: never a sentence with its moment left out, nor read as another moment.
    case = parse_case(chased())
    object.__setattr__(case.rules["chase_review"], "on", {"every": "1d"})
    with pytest.raises(ReadingRefused) as refused:
        read_rules(case)
    assert str(refused.value) == (
        "can't read chase_review's moment {'every': '1d'}: it isn't a moment Ventoux knows"
    )


# Each moment a rule may name, by the tag the definition's type picks it with, and its reading.
# A rule on it starts `chase`; the timer's row is set on a review's start.
MOMENTS = {
    "opened moment": ("opened", "When the case opens: start chase."),
    "reached moment": (
        {"reached": "checked"},
        "When checked is reached (once: a milestone is never undone): start chase.",
    ),
    "started moment": ({"started": "review"}, "Each time a run of review starts: start chase."),
    "answered moment": (
        {"answered": "review"},
        "Each time review is answered, whatever the outcome: start chase.",
    ),
    "event moment": ({"event": "noted"}, "Each time noted arrives: start chase."),
    "timer moment": (
        {"after": "2d", "since": {"started": "review"}},
        "2d after each run of review starts: start chase.",
    ),
}

# What a timer waits after, for each moment it may be set on (brief, D44).
SINCE = {
    "opened moment": ("opened", "2d after the case opens: start chase."),
    "reached moment": (
        {"reached": "checked"},
        "2d after checked is reached (once: a milestone is never undone): start chase.",
    ),
    "started moment": ({"started": "review"}, "2d after each run of review starts: start chase."),
    "answered moment": (
        {"answered": "review"},
        "2d after each answer to review, whatever the outcome: start chase.",
    ),
    "event moment": ({"event": "noted"}, "2d after each arrival of noted: start chase."),
}


def tags(alias: object) -> set[str]:
    """The tags a discriminated union picks its shapes by, nested unions included: read from the
    definition's own type, so a moment added there shows up here."""
    found: set[str] = set()
    for arg in get_args(getattr(alias, "__value__", alias)):
        if get_origin(arg) is Annotated:
            shape, *marks = get_args(arg)
            found |= {mark.tag for mark in marks if hasattr(mark, "tag")}
            found |= {tag for tag in tags(shape) if tag != "moment"}
        else:
            found |= tags(arg)
    return found - {"moment"}


def on_moment(on: object) -> dict[str, Any]:
    """The refund with the guide's chase, its rule fired `on`, and what the moments name."""
    definition = chased(on)
    definition["milestones"] = {"checked": {"display": {"title": "Checked"}}}
    definition["events"] = {
        "noted": {"display": {"title": "A note"}, "sent_by": {"system": "portal"}, "payload": {}}
    }
    return definition


def test_every_moment_the_definition_takes_is_read() -> None:
    # The closed list is the definition's own (brief, D38) (brief, D44): a new moment fails here
    # until it has a reading.
    assert tags(RuleMoment) == set(MOMENTS)
    for on, sentence in MOMENTS.values():
        [reading] = read_rules(parse_case(on_moment(on)))
        assert reading.sentence == sentence
    for since, sentence in SINCE.values():
        [reading] = read_rules(parse_case(on_moment({"after": "2d", "since": since})))
        assert reading.sentence == sentence
    assert set(SINCE) == set(MOMENTS) - {"timer moment"}


# --- Slice 2: conditions and actions ---


class Closing(Then):
    """An action the engine doesn't have: a rule that closes the case."""

    close: tuple[str, ...] = ("done",)


def test_an_action_the_reader_doesnt_know_is_refused() -> None:
    case = parse_case(chased())
    rule = case.rules["chase_review"]
    object.__setattr__(rule, "then", Closing(start=("chase",)))
    with pytest.raises(ReadingRefused) as refused:
        read_rules(case)
    assert str(refused.value) == (
        "can't read chase_review's then.close: it isn't an action Ventoux knows"
    )


def test_an_expression_the_reader_doesnt_know_is_refused() -> None:
    # The expression renderer refuses it (layer 2); the reader says which rule.
    case = parse_case(chased())
    object.__setattr__(case.rules["chase_review"], "when", {"now": []})
    with pytest.raises(ReadingRefused) as refused:
        read_rules(case)
    assert str(refused.value) == (
        "can't read chase_review's condition: can't render {'now': []}: it isn't a parsed "
        "expression"
    )


def every_action() -> dict[str, Any]:
    """The refund with a rule doing all four actions, written in another order than the engine
    takes them."""
    definition = on_moment({"answered": "review"})
    definition["fields"]["owed"] = {"type": "number", "display": {"title": "What is owed"}}
    definition["milestones"]["owed_known"] = {"display": {"title": "What is owed is known"}}
    definition["steps"]["pay"]["automatic"] = False
    definition["steps"]["pay"]["proposed_by"] = ["support"]
    definition["rules"]["chase_review"] |= {
        "when": {"==": [{"var": "review.outcome"}, "approve"]},
        "then": {
            "start": ["chase", "pay"],
            "reach": ["owed_known"],
            "set": {"owed": {"-": [{"var": "approved_amount"}, 1]}},
            "stop": ["call_customer"],
        },
    }
    return definition


# Each action the definition takes, and how it reads.
ACTIONS = {
    "stop": "stop call_customer",
    "set": "set owed to approved_amount - 1",
    "reach": "reach owed_known",
    "start": "start chase and pay",
}


def test_every_action_the_definition_takes_is_read_in_the_engines_order() -> None:
    # The closed list is the definition's own (brief, D38, D39, D40, D42), and the order is the
    # engine's: stop, set, reach, start, whatever order the JSON is written in.
    assert set(Then.model_fields) == set(ACTIONS)
    [reading] = read_rules(parse_case(every_action()))
    assert reading.sentence == (
        'Each time review is answered, whatever the outcome, if review.outcome = "approve" (read '
        "when it fires): stop call_customer, then set owed to approved_amount - 1, then reach "
        "owed_known, then start chase and pay."
    )


def test_a_condition_reads_as_rendered_and_when_it_is_read() -> None:
    # A timer's condition is read when it fires, not when it is set (brief, D44).
    definition = chased()
    definition["rules"]["chase_review"]["when"] = {"!=": [{"var": "review.outcome"}, "approve"]}
    [reading] = read_rules(parse_case(definition))
    assert reading.sentence == (
        '2d after each run of review starts, if review.outcome != "approve" (read when the timer '
        "fires, not when it is set): start chase."
    )


# --- Slices 3 and 4: the fine print, each clause with its witness ---

# Each clause a reading may say, with the test that shows the engine doing what it says.
WITNESSED: set[str] = set()


def witness(clause: str) -> Callable[[Callable[[], None]], Callable[[], None]]:
    """Mark a test as `clause`'s witness: it reads a rule saying it, and runs a case where the
    engine does what it says (brief, D45)."""

    def marked(test: Callable[[], None]) -> Callable[[], None]:
        WITNESSED.add(clause)
        return test

    return marked


def reading_of(definition: dict[str, Any], rule: str = "chase_review") -> Any:
    """The reading of `rule` in `definition`."""
    return next(r for r in read_rules(parse_case(definition)) if r.name == rule)


ON_A_RUN = (
    "The timer is set as each run of review starts, and ends when that run does: done, rejected "
    "or cancelled, a stop included. A failed run keeps it: a retry is the same run."
)


@witness("timer on a run")
def test_a_timer_on_a_run_reads_as_ending_with_it() -> None:
    reading = reading_of(chased())
    assert "timer on a run" in reading.clauses
    assert ON_A_RUN in reading.fine_print
    # Done: the run's timer goes with it (brief, D44).
    done = run_case(chased(), file=SMALL, answers=[APPROVED, later("3d")], people=PEOPLE)
    assert "cancelled chase_review, 2d after started review#1: review#1 is done" in done.history
    # Stopped: cancelled, and its timer with it (brief, D40).
    definition = chased(events=NOTED)
    definition["rules"]["withdraw"] = {
        "display": {"title": "Withdraw"},
        "on": {"event": "noted"},
        "then": {"stop": ["review"]},
    }
    stopped = run_case(
        definition, file=SMALL, answers=[send("noted", {}, "system:portal")], people=PEOPLE
    )
    assert (
        "cancelled chase_review, 2d after started review#1: review#1 is cancelled"
    ) in stopped.history
    # Failed: kept, and the rule acts (brief, D40, as amended by D44).
    failing = chased({"after": "1h", "since": {"started": "look_up"}})
    failing["steps"]["look_up"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    failed = run_case(
        failing,
        file=SMALL,
        answers=[later("2h")],
        people=PEOPLE,
        activities={"orders.lookup@1": down},
    )
    assert failed.needs_attention[0].startswith("look_up#1: orders.lookup@1 failed")
    assert "chase_review#1 on 1h after started look_up#1: starting chase" in failed.history


def after_the_answer() -> dict[str, Any]:
    """The guide's chase, set 30 days after the review is answered: on an instant."""
    return chased({"after": "30d", "since": {"answered": "review"}}, close_reasons=CLOSABLE)


@witness("timer on an instant")
def test_a_timer_on_an_instant_reads_as_living_until_it_fires() -> None:
    reading = reading_of(after_the_answer())
    assert "timer on an instant" in reading.clauses
    assert "The timer is set at each answer to review, and lives until it fires." in (
        reading.fine_print
    )
    # The review is done and the refund paid: the timer lives on, and fires on day 30.
    run = run_case(after_the_answer(), file=SMALL, answers=[APPROVED, later("30d")], people=PEOPLE)
    assert "review#1 done" in run.history and run.reached("pay")
    assert "chase_review#1 on 30d after answered review#1: starting chase" in run.history


@witness("timer holds the case")
def test_a_set_timer_reads_as_keeping_the_case_open() -> None:
    reading = reading_of(after_the_answer())
    assert "timer holds the case" in reading.clauses
    assert "While it is set, the timer keeps the case open; a close cancels it." in (
        reading.fine_print
    )
    # Nothing waits on anyone, and the case is open: the timer holds it (brief, D10).
    paid = run_case(after_the_answer(), file=SMALL, answers=[APPROVED], people=PEOPLE)
    assert paid.waiting_for == [] and not paid.closed
    assert paid.timers == ["chase_review: 30d after answered review#1, due 2026-01-31T00:00:00Z"]
    closed = run_case(
        after_the_answer(),
        file=SMALL,
        answers=[APPROVED, close("duplicate", "ana")],
        people=PEOPLE,
    )
    assert (
        "cancelled chase_review, 30d after answered review#1: closed as duplicate by ana"
    ) in closed.history
    assert closed.closed


@witness("listening")
def test_a_rule_on_an_event_reads_as_listening() -> None:
    definition = chased({"event": "noted"}, events=NOTED)
    reading = reading_of(definition)
    assert "listening" in reading.clauses
    assert "Listening for noted doesn't keep the case open." in reading.fine_print
    # The refund is paid, and the rule still listens: the case closes (brief, D41).
    run = run_case(definition, file=SMALL, answers=[APPROVED], people=PEOPLE)
    assert run.closed


def unused(*_: Any) -> None:
    """Keeps the imports used while the file grows slice by slice."""


unused(copy, PEOPLE, SMALL)
