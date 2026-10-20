"""Stories: a timeline in simulated time, played on the in-memory engine (layer 11g2).

Tests go through `parse_story` and `simulate`, and read what a simulation prints.
See docs/layers/11-rules.md (11g), the brief, D45, and docs/guides/cases.md, "Simulating a story".
"""

import copy
from pathlib import Path
from typing import Any

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_case import guide_refund_with_plan
from test_timers import chased

from ventoux.case.definition import parse_case
from ventoux.case.simulate import StoryRefused, simulate
from ventoux.case.story import StoryInvalid, parse_story
from ventoux.testing import CATALOG, load_definition

EXAMPLES = Path(__file__).parent.parent / "examples"
REFUND = load_definition(EXAMPLES / "refund" / "refund.json")

# --- Slice 1: the format ---


def story(**changes: object) -> dict[str, object]:
    """A story of the refund with nothing on its timeline, changed by `changes`."""
    return {
        "title": "Nobody reviews the refund",
        "definition": "../refund.json",
        "file": {"order_id": "ord-1", "amount": 40},
        "people": {"ana": ["support"]},
        "fakes": {"payments.refund@2": {"gives": {"refund_id": "refund-1"}}},
        "timeline": [],
    } | changes


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"timelien": []}, "timelien: not a field here"),
        (
            {
                "timeline": [
                    {
                        "at": "day 1",
                        "answer": {"step": "review", "outcome": "approve", "by": "ana"},
                        "propose": {"step": "pay", "by": "ana"},
                    }
                ]
            },
            (
                "timeline.0: an entry does one thing, and this one does answer and propose: "
                "split it in two entries"
            ),
        ),
        (
            {"timeline": [{"at": "Tuesday"}]},
            'timeline.0.at: a time looks like "day 3" or "day 3 14:30", counted from the opening',
        ),
        (
            {"timeline": [{"at": "day 1 25:00"}]},
            'timeline.0.at: a time looks like "day 3" or "day 3 14:30", counted from the opening',
        ),
        (
            {"timeline": [{"at": "day 2"}, {"at": "day 1"}]},
            (
                "timeline.1.at: day 1 00:00 comes before day 2 00:00, the entry before it: time "
                "only moves forward"
            ),
        ),
        (
            {"until": "day 0 12:00", "timeline": [{"at": "day 1"}]},
            "until: day 0 12:00 comes before day 1 00:00, the last entry: time only moves forward",
        ),
        (
            {"fakes": {"payments.refund@2": {"gives": {}, "fails": "down"}}},
            (
                "fakes.payments.refund@2: a fake gives, gives an outcome or fails, and this one "
                "does gives and fails: keep one"
            ),
        ),
    ],
)
def test_a_story_that_cant_be_read_is_refused(changes: dict[str, object], problem: str) -> None:
    # Fail closed: a story is data, and one that can't be read whole plays nothing.
    with pytest.raises(StoryInvalid) as refused:
        parse_story(story(**changes))
    assert str(refused.value) == problem


def refused(data: dict[str, Any], definition: dict[str, Any]) -> list[str]:
    """Why `data`, a story, can't run against `definition`: one line per problem."""
    with pytest.raises(StoryRefused) as refusal:
        simulate(parse_story(data), parse_case(definition), CATALOG)
    return str(refusal.value).splitlines()


def test_a_story_without_a_fake_for_what_its_definition_calls_is_refused() -> None:
    # Nothing real is ever reached for: every contract the definition calls has a fake, and a
    # fake for nothing it calls is a typo (brief, D45).
    assert refused(story(fakes={}), REFUND) == [
        "fakes: no fake for payments.refund@2, which pay calls: add one, so nothing real is called"
    ]
    extra = story()
    extra["fakes"] = {**extra["fakes"], "orders.lookup@1": {"gives": {}}}  # type: ignore[dict-item]
    assert refused(extra, REFUND) == [
        (
            "fakes.orders.lookup@1: the definition calls no orders.lookup@1: remove it, or name a "
            "contract a step calls"
        )
    ]


def test_a_story_with_a_plan_step_is_refused() -> None:
    assert "steps.settle: a story can't run a plan step yet: plans in stories come later" in (
        refused(story(), guide_refund_with_plan())
    )


# --- Slice 2: playing a story ---


def played(data: dict[str, Any], definition: dict[str, Any] = REFUND) -> Any:
    """`data`, a story, simulated on `definition`."""
    return simulate(parse_story(data), parse_case(definition), CATALOG)


APPROVE = {"step": "review", "outcome": "approve", "by": "ana", "form": {"approved_amount": 40}}


def test_a_story_names_times_from_the_opening() -> None:
    # Day 0 00:00 is the opening; each entry's time is its event's time (brief, D33).
    simulation = played(story(timeline=[{"at": "day 1 09:30", "answer": APPROVE}]))
    assert simulation.timeline_lines() == {
        "day 0 00:00": [
            "the case opens",
            "opened by system:opener, with amount and order_id",
            "started review#1: waiting for approve or reject by support",
        ],
        "day 1 09:30": [
            "ana answers review: approve, with approved_amount",
            "ana answered review#1 approve as support, setting approved_amount",
            "review#1 done",
            (
                "scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from "
                "person:ana), key story/pay#1"
            ),
            "pay#1 done, giving refund_id from untrusted:undeclared",
            "closed: nothing left to do",
        ],
    }


def test_time_passing_fires_timers_at_their_due_time() -> None:
    # Nobody answers: the chase fires on day 2, stamped with its due time, though the story
    # only says it ends on day 3 (brief, D44).
    simulation = played(story(until="day 3"), chased())
    lines = simulation.timeline_lines()
    assert (
        "set chase_review: 2d after started review#1, due 2026-01-03T00:00:00Z"
        in (lines["day 0 00:00"])
    )
    assert lines["day 2 00:00"] == [
        "chase_review#1 on 2d after started review#1: starting chase",
        "started chase#1: waiting for chased by support-lead",
    ]
    assert simulation.end_at == "day 3 00:00"


def test_a_refused_entry_is_a_line_and_the_story_goes_on() -> None:
    # Eve has no role: the engine refuses her answer, which changes nothing, and Ana's goes on.
    eve = APPROVE | {"by": "eve"}
    simulation = played(
        story(
            people={"ana": ["support"], "eve": []},
            timeline=[{"at": "day 1", "answer": eve}, {"at": "day 2", "answer": APPROVE}],
        )
    )
    lines = simulation.timeline_lines()
    assert lines["day 1 00:00"] == [
        "eve answers review: approve, with approved_amount",
        "refused: review#1 is answered by support, and eve has no role",
    ]
    assert lines["day 2 00:00"][1] == (
        "ana answered review#1 approve as support, setting approved_amount"
    )


def unused(*_: object) -> None:
    """Keeps the imports used while the file grows slice by slice."""


unused(copy)
