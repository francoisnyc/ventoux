"""Timers: time passing after a moment, set on it, fired as an event stamped with its own due time
(layer 11f).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md (11f), the brief, D44, and docs/guides/cases.md, "Rules on time".
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import load_definition

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


def chased(on: object = None) -> dict[str, Any]:
    """The quickstart's refund, with the guide's timer chasing a review left open; `on` replaces
    the timer's moment."""
    definition = copy.deepcopy(REFUND)
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
