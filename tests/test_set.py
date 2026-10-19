"""Rules that update the case file: a value comes from everything its rule read (layer 11e).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md (11e) and docs/guides/cases.md, "Rules that update the case file".
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import load_definition

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "omar": ["operations"]}

# What is owed once the review is approved: the approved amount less a fee given at the opening.
WORK_OUT_OWED = {
    "display": {"title": "Work out what is owed"},
    "on": {"answered": "review"},
    "when": {"==": [{"var": "review.outcome"}, "approve"]},
    "then": {"set": {"owed": {"-": [{"var": "approved_amount"}, {"var": "fee"}]}}},
}


def with_owed(**changes: Any) -> dict[str, Any]:
    """The quickstart's refund, with a `fee` given at the opening and `owed`, which only the rule
    `work_out_owed` sets; `changes` replaces top-level keys."""
    definition = copy.deepcopy(REFUND)
    definition["fields"]["fee"] = {"type": "number", "display": {"title": "Handling fee"}}
    definition["fields"]["owed"] = {"type": "number", "display": {"title": "What is owed"}}
    definition["rules"] = {"work_out_owed": copy.deepcopy(WORK_OUT_OWED)}
    return definition | changes


# --- Slice 1: the shape ---


def test_set_names_a_field_of_the_case_file() -> None:
    definition = with_owed()
    definition["rules"]["work_out_owed"]["then"]["set"] = {"owing": {"var": "fee"}}
    with pytest.raises(CaseInvalid, match="^rules.work_out_owed.then.set: owing is not a field$"):
        parse_case(definition)


def test_a_list_field_is_never_set() -> None:
    # `fits` can't check a list value yet, so a list is never set, nor packed into a text
    # meanwhile (brief, D42).
    definition = with_owed()
    definition["fields"]["lines"] = {
        "type": "list",
        "fields": {"sku": {"type": "string"}},
        "display": {"title": "Order lines"},
    }
    definition["rules"]["work_out_owed"]["then"]["set"] = {"lines": {"var": "lines"}}
    with pytest.raises(
        CaseInvalid,
        match="^rules.work_out_owed.then.set.lines: lines is a list, and a rule never sets a list "
        "yet: a list comes once a list value can be checked$",
    ):
        parse_case(definition)


def test_a_field_has_one_kind_of_writer() -> None:
    # A field is given at the opening, set by people's forms, or set by rules, never two of these:
    # a rule overwriting a person's answer would silently undo what they confirmed (brief, D42).
    definition = with_owed()
    definition["rules"]["work_out_owed"]["then"]["set"] = {"approved_amount": {"var": "fee"}}
    with pytest.raises(
        CaseInvalid,
        match="^rules.work_out_owed.then.set.approved_amount: approved_amount is set by a person "
        "in review, so a rule never sets it: set another field, and read approved_amount there$",
    ):
        parse_case(definition)


@pytest.mark.parametrize(
    "value",
    [{"cat": ["ord-", {"var": "order_id"}]}, {"var": "customer_id"}, {"var": "note"}],
    ids=["computed", "another system", "a text"],
)
def test_a_reference_is_set_only_from_its_systems_reference(value: dict[str, Any]) -> None:
    # A reference goes only where its system is expected, read as it is: a rule never makes one
    # up (brief, D30, D42).
    definition = with_owed()
    definition["fields"] |= {
        "customer_id": {"type": "reference", "system": "crm", "display": {"title": "Customer"}},
        "note": {"type": "string", "display": {"title": "Note"}},
        "refunded_order": {"type": "reference", "system": "orders", "display": {"title": "Order"}},
    }
    definition["rules"]["work_out_owed"]["then"]["set"] = {"refunded_order": value}
    with pytest.raises(
        CaseInvalid,
        match="^rules.work_out_owed.then.set.refunded_order: refunded_order is a reference to "
        "orders, and is set only from a reference field of orders, read as it is$",
    ):
        parse_case(definition)


def test_a_reference_is_set_from_its_systems_reference_read_as_it_is() -> None:
    definition = with_owed()
    definition["fields"]["refunded_order"] = {
        "type": "reference",
        "system": "orders",
        "display": {"title": "Order"},
    }
    definition["rules"]["work_out_owed"]["then"]["set"] = {"refunded_order": {"var": "order_id"}}
    parse_case(definition)


def test_a_set_reading_nothing_is_refused() -> None:
    # Its value would come from nobody, which no value of a case file does (brief, D36, D42).
    definition = with_owed()
    rule = definition["rules"]["work_out_owed"]
    del rule["when"]
    rule["then"]["set"] = {"owed": 0}
    with pytest.raises(
        CaseInvalid,
        match="^rules.work_out_owed.then.set: work_out_owed reads no field, so what it sets would "
        "come from nobody: read a field in its when or its values, or reach a milestone instead$",
    ):
        parse_case(definition)


def test_a_constant_set_under_a_condition_comes_from_what_the_condition_read() -> None:
    definition = with_owed()
    definition["rules"]["work_out_owed"]["then"]["set"] = {"owed": 0}
    parse_case(definition)
