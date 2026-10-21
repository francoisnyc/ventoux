"""Approvals by several people: `count` on a step's approval (layer 11h2).

Tests go through `parse_case`, `run_case` and what a run reports.
See docs/layers/11-rules.md, 11h2, docs/guides/cases.md, "Several approvers", and brief D47.
"""

import copy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import load_definition, run_case

ROOT = Path(__file__).parent.parent
FOUR_EYES = load_definition(ROOT / "examples" / "refund" / "refund-four-eyes.json")


def four_eyes(**approval: Any) -> dict[str, Any]:
    """A copy of the four-eyes refund, its approval changed by `approval`."""
    definition = copy.deepcopy(FOUR_EYES)
    definition["steps"]["pay"]["approval"].update(approval)
    return definition


# --- Slice 1: the shape ---


@pytest.mark.parametrize("count", [0, -1, "2", Decimal("2.0"), 2.0, True, None])
def test_a_count_that_isnt_a_whole_number_of_at_least_one_is_refused(count: object) -> None:
    # Pydantic would read "2" and 2.0 as 2, and `true` as 1: refused instead, never guessed
    # (brief, D47).
    with pytest.raises(
        CaseInvalid,
        match=(
            r"^steps\.pay\.approval\.count: how many people must approve: a whole number of at "
            r"least 1, such as 2$"
        ),
    ):
        parse_case(four_eyes(count=count))


def test_a_count_is_read() -> None:
    assert parse_case(four_eyes()).steps["pay"].approval.count == 2  # type: ignore[union-attr]
    one = four_eyes()
    del one["steps"]["pay"]["approval"]["count"]
    assert parse_case(one).steps["pay"].approval.count == 1  # type: ignore[union-attr]


# --- Slice 2: one entry collects the answers ---

PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "kim": ["support-lead"],
}
LARGE = {"order_id": "ord-1", "amount": 12000}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 12000})


def test_one_approval_of_two_starts_nothing() -> None:
    run = run_case(FOUR_EYES, file=LARGE, answers=[REVIEWED, ("pay", "approve", "sam")], people=PEOPLE)
    # The warm-up's three assertions, with the count (learning question 14) (brief, D24).
    assert run.waiting_for == ["approval of pay by support-lead: 1 of 2 given"]
    assert not run.reached("pay")
    assert not run.closed
    assert run.history[-2:] == [
        "asked pay.approval#1: approval of pay by support-lead, from 2 people",
        "sam answered pay.approval#1 approve as support-lead: 1 of 2 given",
    ]


def test_the_second_approval_starts_the_step() -> None:
    run = run_case(
        FOUR_EYES,
        file=LARGE,
        answers=[REVIEWED, ("pay", "approve", "sam"), ("pay.approval#1", "approve", "lee")],
        people=PEOPLE,
    )
    asked = run.history.index("asked pay.approval#1: approval of pay by support-lead, from 2 people")
    assert run.history[asked : asked + 4] == [
        "asked pay.approval#1: approval of pay by support-lead, from 2 people",
        "sam answered pay.approval#1 approve as support-lead: 1 of 2 given",
        "lee answered pay.approval#1 approve as support-lead: 2 of 2 given",
        (
            "scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from "
            "person:ana), key memory/pay#1"
        ),
    ]
    assert run.reached("pay")
    assert run.closed


def test_waiting_for_says_how_many_are_given() -> None:
    run = run_case(FOUR_EYES, file=LARGE, answers=[REVIEWED], people=PEOPLE)
    assert run.waiting_for == ["approval of pay by support-lead: 0 of 2 given"]
    three = four_eyes(count=3)
    run = run_case(
        three,
        file=LARGE,
        answers=[REVIEWED, ("pay", "approve", "sam"), ("pay", "approve", "lee")],
        people=PEOPLE,
    )
    assert run.waiting_for == ["approval of pay by support-lead: 2 of 3 given"]
    assert run.history[-2:] == [
        "sam answered pay.approval#1 approve as support-lead: 1 of 3 given",
        "lee answered pay.approval#1 approve as support-lead: 2 of 3 given",
    ]


def test_a_count_of_one_changes_nothing() -> None:
    # Written or left out, a count of 1 decides, records and reports exactly as before 11h2:
    # every earlier test runs the refund without it (brief, D47).
    plain = load_definition(ROOT / "examples" / "refund" / "refund.json")
    written = copy.deepcopy(plain)
    written["steps"]["pay"]["approval"]["count"] = 1
    small = {"order_id": "ord-1", "amount": 250}
    review = ("review", "approve", "ana", {"approved_amount": 250})
    for definition in (plain, written):
        waiting = run_case(definition, file=small, answers=[review], people=PEOPLE)
        assert waiting.waiting_for == ["approval of pay by support-lead"]
        assert waiting.history[-1] == "asked pay.approval#1: approval of pay by support-lead"
        paid = run_case(
            definition, file=small, answers=[review, ("pay", "approve", "sam")], people=PEOPLE
        )
        assert "sam answered pay.approval#1 approve as support-lead" in paid.history
        assert paid.reached("pay")
