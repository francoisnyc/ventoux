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

from ventoux.case.definition import RuleMoment, parse_case
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


def unused(*_: Any) -> None:
    """Keeps the imports used while the file grows slice by slice."""


unused(copy, PEOPLE, SMALL)
