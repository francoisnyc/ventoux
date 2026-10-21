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
from ventoux.testing import load_definition

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
