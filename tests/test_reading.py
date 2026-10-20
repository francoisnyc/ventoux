"""Reading rules: each rule in plain words, worked out from the definition alone (layer 11g1).

Tests go through `parse_case` and `read_rules`, and, for each part a reading says, through
`run_case`, so a reading and the engine can't drift apart.
See docs/layers/11-rules.md (11g), the brief, D45, and docs/guides/cases.md, "Reading rules".
"""

import copy
from typing import Annotated, Any, get_args, get_origin

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_timers import PEOPLE, SMALL, chased

from ventoux.case.definition import RuleMoment, Then, parse_case
from ventoux.case.reading import ReadingRefused, read_rules

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


def unused(*_: Any) -> None:
    """Keeps the imports used while the file grows slice by slice."""


unused(copy, PEOPLE, SMALL)
