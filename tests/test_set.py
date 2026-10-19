"""Rules that update the case file: a value comes from everything its rule read (layer 11e).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md (11e) and docs/guides/cases.md, "Rules that update the case file".
"""

import copy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.state import Obtained
from ventoux.testing import (
    START,
    AnswerRefused,
    CaseRefused,
    load_definition,
    retry,
    run_case,
    send,
)

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "omar": ["operations"]}
FILE = {"order_id": "ord-1", "amount": 40, "fee": 5}
APPROVED = ("review", "approve", "ana", {"approved_amount": 40})

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


# --- Slice 2: writing, in memory ---


def test_a_set_that_cant_be_read_fails_the_whole_rule() -> None:
    # A rule acts whole or not at all: a value it can't compute fails it, and it reaches nothing
    # either (brief, D42).
    definition = with_owed()
    definition["milestones"] = {"owed_known": {"display": {"title": "What is owed is known"}}}
    definition["rules"]["work_out_owed"]["then"]["reach"] = ["owed_known"]
    run = run_case(
        definition, file={"order_id": "ord-1", "amount": 40}, answers=[APPROVED], people=PEOPLE
    )
    assert run.needs_attention == [
        (
            "work_out_owed#1: work_out_owed's owed approved_amount - fee can't be evaluated: fee has "
            "no value"
        ),
    ]
    assert "owed" not in run.state.values
    assert "owed_known" not in run.state.milestones


def test_a_set_value_comes_from_everything_its_rule_read() -> None:
    # Its expression reads approved_amount (Ana's) and fee (the opener's); its condition reads
    # review.outcome (Ana's): the value comes from all of them (brief, D42).
    run = run_case(with_owed(), file=FILE, answers=[APPROVED], people=PEOPLE)
    assert run.state.values["owed"] == Decimal(35)
    assert run.state.sources["owed"] == {"person:ana", "system:opener"}
    assert run.state.obtained["owed"] == Obtained(START, "work_out_owed#1")
    assert (
        "work_out_owed#1 on answered review: setting owed, from person:ana, system:opener"
        in run.history
    )


def test_a_set_of_another_type_fails_the_rule() -> None:
    # Checked over the case's types before the rule reads anything, so the rule fails and writes
    # nothing; the message names the types, never a value (brief, D35, D42).
    definition = with_owed()
    definition["rules"]["work_out_owed"]["then"]["set"] = {"owed": {"string": [{"var": "fee"}]}}
    run = run_case(definition, file=FILE, answers=[APPROVED], people=PEOPLE)
    assert run.needs_attention == [
        (
            "work_out_owed#1: work_out_owed.then.set.owed can't be read: owed is a number, and this "
            "gives a string"
        ),
    ]
    assert "owed" not in run.state.values


def test_a_text_set_on_an_outcome_field_is_checked_when_written() -> None:
    # A text may be one of the field's outcomes or not: that depends on the value, so it is
    # checked as it is written (brief, D42).
    definition = with_owed()
    definition["fields"]["verdict"] = {
        "type": "outcome",
        "outcomes": ["approve", "reject"],
        "display": {"title": "Verdict"},
    }
    definition["fields"]["said"] = {"type": "string", "display": {"title": "What was said"}}
    definition["rules"]["work_out_owed"]["then"]["set"] = {"verdict": {"var": "said"}}
    run = run_case(definition, file=FILE | {"said": "maybe"}, answers=[APPROVED], people=PEOPLE)
    assert run.needs_attention == [
        (
            "work_out_owed#1: work_out_owed's verdict gives a text that is none of its outcomes: "
            "approve or reject"
        ),
    ]


def test_set_values_are_read_together() -> None:
    # Each value is read on the case file as the condition saw it: `doubled` reads what was owed
    # before this rule set it, though `owed` is written first (brief, D42).
    definition = with_owed()
    definition["fields"]["doubled"] = {"type": "number", "display": {"title": "Twice the fee"}}
    definition["rules"]["work_out_owed"]["then"]["set"] = {
        "owed": {"-": [{"var": "approved_amount"}, {"var": "fee"}]},
        "doubled": {"*": [{"var": "owed"}, 2]},
    }
    definition["rules"]["first"] = {
        "display": {"title": "Owe nothing at first"},
        "on": "opened",
        "then": {"set": {"owed": {"-": [{"var": "fee"}, {"var": "fee"}]}}},
    }
    run = run_case(definition, file=FILE, answers=[APPROVED], people=PEOPLE)
    assert run.state.values["owed"] == Decimal(35)
    assert run.state.values["doubled"] == Decimal(0)  # twice the owed as the condition saw it


def test_a_milestone_a_rule_reaches_sees_what_it_set() -> None:
    # Set comes before reach, so a step the milestone lets start reads the new value (brief, D42).
    definition = with_owed()
    definition["milestones"] = {"owed_known": {"display": {"title": "What is owed is known"}}}
    definition["rules"]["work_out_owed"]["then"]["reach"] = ["owed_known"]
    definition["steps"]["pay"]["requires"] = ["owed_known"]
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    run = run_case(definition, file=FILE, answers=[APPROVED], people=PEOPLE)
    assert run.reached("pay")
    assert run.history.index(
        "work_out_owed#1 on answered review: setting owed, from person:ana, system:opener"
    ) < run.history.index("work_out_owed#1 on answered review: reaching owed_known")


def test_the_opening_never_gives_a_rules_field() -> None:
    # One kind of writer per field: what rules set is never given at the opening (brief, D42).
    with pytest.raises(
        CaseRefused, match="^owed is set by rules, in work_out_owed, never given at the opening$"
    ):
        run_case(with_owed(), file=FILE | {"owed": 1}, answers=[], people=PEOPLE)


def test_the_latest_write_stands() -> None:
    # Two rules setting one field in one decision set it in order, and both are recorded; the
    # latest stands, as with an answer or an output (brief, D42).
    definition = with_owed()
    definition["rules"]["owe_all"] = {
        "display": {"title": "Owe all of it"},
        "on": {"answered": "review"},
        "when": {"==": [{"var": "review.outcome"}, "approve"]},
        "then": {"set": {"owed": {"var": "approved_amount"}}},
    }
    run = run_case(definition, file=FILE, answers=[APPROVED], people=PEOPLE)
    assert run.state.values["owed"] == Decimal(40)
    assert run.state.obtained["owed"].run == "owe_all#1"
    setting = [line for line in run.history if "setting owed" in line]
    assert setting == [
        "work_out_owed#1 on answered review: setting owed, from person:ana, system:opener",
        "owe_all#1 on answered review: setting owed, from person:ana",
    ]


def test_a_retried_set_reads_again() -> None:
    # A rule that failed reads its condition and its values again on retry, on the case file as
    # it is then (brief, D26, D42).
    definition = with_owed()
    definition["rules"]["work_out_owed"]["on"] = "opened"
    del definition["rules"]["work_out_owed"]["when"]
    definition["rules"]["work_out_owed"]["then"]["set"] = {
        "owed": {"-": [{"var": "approved_amount"}, {"var": "fee"}]}
    }
    run = run_case(
        definition,
        file=FILE,
        answers=[APPROVED, retry("work_out_owed#1", "omar")],
        people=PEOPLE,
    )
    assert run.needs_attention == []
    assert run.state.values["owed"] == Decimal(35)


# --- Slice 3: provenance at work ---


def with_large_claim() -> dict[str, Any]:
    """The refund, with the customer's own estimate (untrusted), `large_claim` set from it on the
    opening, and a milestone a second rule reaches on `large_claim`."""
    definition = with_owed()
    definition["fields"] |= {
        "estimate": {
            "type": "number",
            "source": "untrusted:customer",
            "display": {"title": "Customer's own estimate"},
        },
        "large_claim": {"type": "boolean", "display": {"title": "A large claim"}},
    }
    definition["milestones"] = {"large": {"display": {"title": "A large claim"}}}
    definition["rules"] |= {
        "size_up": {
            "display": {"title": "Mark a large claim"},
            "on": "opened",
            "when": {">": [{"var": "estimate"}, 5000]},
            "then": {"set": {"large_claim": True}},
        },
        "flag_large": {
            "display": {"title": "Flag a large claim"},
            "on": "opened",
            "when": {"==": [{"var": "large_claim"}, True]},
            "then": {"reach": ["large"]},
        },
    }
    return definition


def test_a_constant_under_an_untrusted_condition_is_untrusted() -> None:
    # `true` is written by the definition, but the customer's estimate chose it: the value comes
    # from what the condition read. Setting informs, so the rule acts (brief, D42).
    run = run_case(with_large_claim(), file=FILE | {"estimate": 9000}, answers=[], people=PEOPLE)
    assert run.state.values["large_claim"] is True
    assert run.state.sources["large_claim"] == {"system:opener", "untrusted:customer"}
    assert (
        "size_up#1 on opened: setting large_claim, from system:opener, untrusted:customer"
        in run.history
    )


def test_untrusted_data_cant_decide_through_a_set_field() -> None:
    # Without the condition's sources, `large_claim` would launder the estimate into a trusted
    # milestone (brief, D38, D42).
    run = run_case(with_large_claim(), file=FILE | {"estimate": 9000}, answers=[], people=PEOPLE)
    assert "large" not in run.state.milestones
    assert (
        "flag_large#1 on opened: reaches nothing: its condition reads large_claim, from "
        "untrusted:customer, and untrusted data can't decide"
    ) in run.history


def test_a_rule_that_sets_and_reaches_on_untrusted_data_doesnt_act() -> None:
    definition = with_large_claim()
    definition["rules"]["size_up"]["then"]["reach"] = ["large"]
    run = run_case(definition, file=FILE | {"estimate": 9000}, answers=[], people=PEOPLE)
    assert "large_claim" not in run.state.values
    assert "large" not in run.state.milestones
    assert (
        "size_up#1 on opened: reaches and sets nothing: its condition reads estimate, from "
        "untrusted:customer, and untrusted data can't decide"
    ) in run.history


def test_an_input_policy_refuses_a_value_computed_from_untrusted_data() -> None:
    # payments.refund@2 takes amount only from a system or a person: a value computed from the
    # customer's estimate is refused, as the estimate itself is (brief, D36, D42).
    definition = with_owed()
    definition["fields"]["estimate"] = with_large_claim()["fields"]["estimate"]
    definition["rules"]["work_out_owed"]["then"]["set"] = {
        "owed": {"-": [{"var": "estimate"}, {"var": "fee"}]}
    }
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    run = run_case(definition, file=FILE | {"estimate": 50}, answers=[APPROVED], people=PEOPLE)
    assert not run.reached("pay")
    assert run.needs_attention == [
        (
            "pay#1: payments.refund@2 takes amount only from a system or a person, never from "
            "untrusted data, and this value comes from owed (person:ana, system:opener, "
            "untrusted:customer)"
        )
    ]


def test_whose_answer_a_set_value_carries_cant_approve() -> None:
    # Sam's answer is in what is owed, so Sam can't approve paying it: four eyes hold through the
    # computation (brief, D11, D42).
    definition = with_owed()
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    big = ("review", "approve", "sam", {"approved_amount": 500})
    with pytest.raises(
        AnswerRefused,
        match="^sam's answer is in owed, which a rule computes and pay uses, so cannot approve it$",
    ):
        run_case(definition, file=FILE, answers=[big, ("pay", "approve", "sam")], people=PEOPLE)


def test_a_set_changing_what_an_approval_saw_withdraws_it() -> None:
    # Nobody approves values they didn't see: a rule changing what is owed while its approval is
    # open withdraws it, and a new one is asked (brief, D25, D42).
    definition = with_owed()
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    definition["events"] = {
        "fee_changed": {
            "display": {"title": "The fee changes"},
            "sent_by": {"system": "portal"},
            "payload": {"fee": {"type": "number", "display": {"title": "The new fee"}}},
        }
    }
    definition["rules"]["refigure"] = {
        "display": {"title": "Work out what is owed again"},
        "on": {"event": "fee_changed"},
        "then": {"set": {"owed": {"-": [{"var": "approved_amount"}, {"var": "fee_changed.fee"}]}}},
    }
    big = ("review", "approve", "ana", {"approved_amount": 500})
    run = run_case(
        definition,
        file=FILE,
        answers=[big, send("fee_changed", {"fee": 50}, "system:portal")],
        people=PEOPLE,
    )
    assert "withdrew pay.approval#1: owed changed" in run.history
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert run.state.values["owed"] == Decimal(450)
