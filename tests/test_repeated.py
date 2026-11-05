"""Layer 18b: repeated steps. A step runs once per item of a list in the case file, each run named
by a number the engine gives its item's key, and given its item (brief, D73).

See docs/layers/18-lifecycle.md (18b) and docs/guides/cases.md, "Repeated steps: one run per item".
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.memory import CaseRun
from ventoux.testing import CaseRefused, load_definition, run_case

ROOT = Path(__file__).parent.parent
GUIDE = ROOT / "docs" / "guides" / "cases.md"
SECTION = "## Repeated steps: one run per item"
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")  # the quickstart's


def guide_block() -> dict[str, Any]:
    """The guide's fields and steps for a returned order, as stored data, read from the guide."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[1].split("```")[0]
    loaded: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    return loaded


def order_return() -> dict[str, Any]:
    """The guide's returned order: its fields and its two repeated steps, as a case of its own."""
    block = guide_block()
    return {
        "case": "order-return",
        "display": {"title": "A returned order"},
        "fields": block["fields"],
        "steps": block["steps"],
    }


def test_a_step_repeated_over_a_field_that_isnt_a_list_is_refused() -> None:
    # The curriculum's negative test (brief, D73).
    definition = order_return()
    definition["steps"]["draft_line"]["for_each"]["over"] = "order_id"
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == (
        "steps.draft_line.for_each: order_id is a reference to orders, not a list: a step "
        "repeats over a list field"
    )


# --- Slice 1: a list value, given at the opening (brief, D73) ---

LINES = [{"sku": "A12", "amount": 40}, {"sku": "B7", "amount": 25}]
FILE = {"order_id": "ord-1", "email": "ana@example.com", "lines": LINES}
PEOPLE = {"ana": ["support"], "omar": ["operations"]}
SHAPE = "lines is a list of records with sku (a string) and amount (a number)"


def opened(lines: object) -> CaseRun:
    """The returned order opened with `lines`, nothing answered."""
    return run_case(order_return(), file=FILE | {"lines": lines}, answers=[], people=PEOPLE)


def test_a_list_that_fits_is_given_at_the_opening() -> None:
    assert opened(LINES).status == "open"


@pytest.mark.parametrize(
    ("lines", "refusal"),
    [
        ("A12, B7", f"{SHAPE}, and the opening gives a string"),
        ([{"sku": "A12"}], f"{SHAPE}, and the opening gives an item without amount"),
        (
            [{"sku": "A12", "amount": 40, "note": "x"}],
            f"{SHAPE}, and the opening gives an item with a field lines doesn't declare",
        ),
        (
            [{"sku": "A12", "amount": "40"}],
            f"{SHAPE}, and the opening gives an item whose amount is a string",
        ),
        (["A12"], f"{SHAPE}, and the opening gives an item that is a string"),
        (
            [{"sku": f"s{n}", "amount": 1} for n in range(101)],
            "lines holds at most 100 items, and the opening gives 101",
        ),
    ],
)
def test_a_list_that_doesnt_fit_is_refused_at_the_opening(lines: object, refusal: str) -> None:
    # The type and the shape, never a value: refusals reach people who may not see it (brief,
    # D30) (brief, D73).
    with pytest.raises(CaseRefused) as refused:
        opened(lines)
    assert str(refused.value) == refusal
