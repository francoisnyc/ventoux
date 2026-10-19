"""Rules that update the case file: a value comes from everything its rule read (layer 11e).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md (11e) and docs/guides/cases.md, "Rules that update the case file".
"""

import copy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_case_validation import PLANS, settled

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.state import Obtained
from ventoux.case.validate import validate_case
from ventoux.core.sensitive import Sensitive, plain
from ventoux.core.validate import Issue
from ventoux.testing import (
    CATALOG,
    DAY,
    START,
    AnswerRefused,
    CaseRefused,
    ProposalRefused,
    close,
    finish,
    later,
    load_definition,
    propose,
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
            "gives a string: set it from a number"
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


# --- Slice 4: time ---


def with_settle() -> dict[str, Any]:
    """The refund with what is owed, and `settle`, which support proposes to pay what is owed, at
    most a day old."""
    definition = with_owed()
    definition["steps"]["settle"] = {
        "kind": "activity",
        "display": {"title": "Pay what is owed"},
        "activity": "payments.refund@2",
        "automatic": False,
        "proposed_by": ["support"],
        "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "owed"}},
        "max_age": {"owed": "1d"},
        "approval": {"roles": ["support-lead"], "display": {"reason": "A team lead pays it"}},
    }
    return definition


def test_a_set_value_is_as_old_as_its_oldest_fact() -> None:
    # The fee was given at the opening, the approved amount two days later: what is owed is as old
    # as the fee, never "obtained now" (brief, D33, D42).
    run = run_case(with_settle(), file=FILE, answers=[later("2d"), APPROVED], people=PEOPLE)
    assert run.state.obtained["approved_amount"].at == START + 2 * DAY
    assert run.state.obtained["owed"] == Obtained(START, "work_out_owed#1")


def test_a_stale_set_value_is_never_fetched_again() -> None:
    # A rule doesn't fire again because a fact was refreshed, so a computed value can never be
    # fetched again, and the refusal says it was computed (brief, D33, D42).
    with pytest.raises(
        ProposalRefused,
        match="^owed was obtained 2 days ago, and settle needs it at most 1 day old: it was "
        "computed by work_out_owed#1, so it can't be fetched again$",
    ):
        run_case(
            with_settle(),
            file=FILE,
            answers=[later("2d"), APPROVED, propose("settle", "ana")],
            people=PEOPLE,
            held=["pay"],  # the case stays open while the refund runs
        )


# --- Slice 5: sensitive and visible ---


def with_national_id() -> dict[str, Any]:
    """The refund with a national ID only fraud sees, and a risk band a rule sets from it."""
    definition = with_owed()
    definition["fields"] |= {
        "national_id": {
            "type": "string",
            "sensitive": True,
            "visible_to": ["fraud"],
            "display": {"title": "National ID"},
        },
        "risk_band": {
            "type": "string",
            "sensitive": True,
            "visible_to": ["fraud"],
            "display": {"title": "Risk band"},
        },
    }
    definition["rules"]["band"] = {
        "display": {"title": "Work out the risk band"},
        "on": "opened",
        "then": {"set": {"risk_band": {"cat": ["band-", {"var": "national_id"}]}}},
    }
    return definition


def test_a_value_from_a_sensitive_field_is_set_only_on_a_sensitive_one() -> None:
    # A value computed from a sensitive one is sensitive too (brief, D31, D42).
    definition = with_national_id()
    definition["fields"]["risk_band"]["sensitive"] = False
    with pytest.raises(
        CaseInvalid,
        match="^rules.band.then.set.risk_band: risk_band is set from national_id, which is "
        "sensitive: declare risk_band sensitive$",
    ):
        parse_case(definition)


def test_a_condition_on_a_sensitive_field_counts_too() -> None:
    definition = with_national_id()
    definition["fields"]["risk_band"]["sensitive"] = False
    definition["rules"]["band"]["when"] = {"==": [{"var": "national_id"}, "x"]}
    definition["rules"]["band"]["then"]["set"] = {"risk_band": {"var": "risk_band_given"}}
    definition["fields"]["risk_band_given"] = {"type": "string", "display": {"title": "Given"}}
    with pytest.raises(
        CaseInvalid,
        match="^rules.band.then.set.risk_band: risk_band is set from "
        "national_id, which is sensitive: declare risk_band sensitive$",
    ):
        parse_case(definition)


@pytest.mark.parametrize(
    ("seen_by", "said"),
    [(None, "every role of the case"), (["support", "fraud"], "support or fraud")],
    ids=["everyone", "a wider list"],
)
def test_a_set_field_is_seen_by_no_one_its_sources_hide_from(
    seen_by: list[str] | None, said: str
) -> None:
    # A field only fraud sees can't be copied into one support sees: a view may hide more than
    # its source, never less (brief, D30, D42).
    definition = with_owed()
    definition["fields"] |= {
        "fraud_score": {
            "type": "number",
            "visible_to": ["fraud"],
            "display": {"title": "Fraud score"},
        },
        "escalate": {"type": "boolean", "display": {"title": "Escalate"}},
    }
    if seen_by is not None:
        definition["fields"]["escalate"]["visible_to"] = seen_by
    definition["rules"]["escalation"] = {
        "display": {"title": "Escalate a risky refund"},
        "on": "opened",
        "when": {">": [{"var": "fraud_score"}, 70]},
        "then": {"set": {"escalate": {"var": "fraud_score_known"}}},
    }
    definition["fields"]["fraud_score_known"] = {"type": "boolean", "display": {"title": "Known"}}
    with pytest.raises(
        CaseInvalid,
        match=f"^rules.escalation.then.set.escalate: escalate is seen by {said}, and is set from "
        "fraud_score, which only fraud sees: let only fraud see escalate$",
    ):
        parse_case(definition)


def test_a_set_field_may_hide_more_than_its_sources() -> None:
    definition = with_owed()
    definition["fields"]["owed"]["visible_to"] = ["support-lead"]
    parse_case(definition)


def test_a_set_sensitive_value_stays_wrapped() -> None:
    # Computed on plain values inside the worker, kept wrapped, never written out (brief, D31).
    run = run_case(
        with_national_id(), file=FILE | {"national_id": "190101-1234"}, answers=[], people=PEOPLE
    )
    risk_band = run.state.values["risk_band"]
    assert isinstance(risk_band, Sensitive)
    assert plain(risk_band) == "band-190101-1234"
    assert not any("190101" in line for line in run.history)
    assert run.view(["support"]).values.get("risk_band") is None


# --- Slice 6: the close ---


def test_set_stops_with_the_close() -> None:
    # Once every closes_when milestone is reached, nothing new is decided, a set included, even
    # on the moment that reached the last one (brief, D38, D42).
    definition = with_owed(closes_when=["paid"])
    definition["milestones"] = {"paid": {"display": {"title": "Paid"}}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["rules"]["work_out_owed"] |= {"on": {"reached": "paid"}}
    del definition["rules"]["work_out_owed"]["when"]
    run = run_case(definition, file=FILE, answers=[APPROVED], people=PEOPLE)
    assert run.closed
    assert "owed" not in run.state.values
    assert (
        "work_out_owed#1 on reached paid: not applied: paid is reached, so the case closes and "
        "nothing new is decided"
    ) in run.history


def test_set_doesnt_act_while_the_case_closes() -> None:
    definition = with_owed()
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "A duplicate"}, "roles": ["support"]}
    }
    definition["milestones"] = {"paid": {"display": {"title": "Paid"}}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["rules"]["work_out_owed"] |= {"on": {"reached": "paid"}}
    del definition["rules"]["work_out_owed"]["when"]
    run = run_case(
        definition,
        file=FILE,
        answers=[APPROVED, close("duplicate", "ana"), finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    assert "owed" not in run.state.values
    assert (
        "work_out_owed#1 on reached paid: not applied: the case is closing, so nothing new is "
        "decided"
    ) in run.history


# --- Slice 7: validation stays a proof ---


def issues(definition: dict[str, Any]) -> list[Issue]:
    return validate_case(parse_case(definition), CATALOG)


def coded(definition: dict[str, Any], code: str) -> list[Issue]:
    return [issue for issue in issues(definition) if issue.code == code]


def with_flagged() -> dict[str, Any]:
    """The large claim, with `flagged` set from `large_claim` by a rule written before the rule
    that sets `large_claim`, and the milestone reached on `flagged` instead."""
    definition = with_large_claim()
    rules = definition["rules"]
    definition["fields"]["flagged"] = {"type": "boolean", "display": {"title": "Flagged"}}
    flag = {
        "display": {"title": "Flag what is large"},
        "on": {"answered": "review"},
        "then": {"set": {"flagged": {"var": "large_claim"}}},
    }
    rules["flag_large"]["on"] = {"answered": "review"}
    rules["flag_large"]["when"] = {"==": [{"var": "flagged"}, True]}
    definition["rules"] = {"flag": flag, **rules}  # written before size_up
    return definition


def test_sources_go_round_until_nothing_changes() -> None:
    # Read once in the written order, `flagged` would look like it comes from nobody untrusted,
    # since `large_claim` is worked out after it. Going round until nothing changes, it comes
    # from the customer, so the rule reaching on it never acts (brief, D34, D42).
    assert coded(with_flagged(), "UNTRUSTED_TRIGGER") == [
        Issue(
            "rules.flag_large.when",
            "UNTRUSTED_TRIGGER",
            "flag_large's condition reads flagged, which comes from untrusted:customer whoever "
            "writes it, and untrusted data can't decide, so it never reaches large: read a value "
            "a person or a trusted system gives, such as a task's answer",
        )
    ]


def with_two_sizers() -> dict[str, Any]:
    """The large claim, which a second rule also sets, from the review's answer: untrusted when
    `size_up` sets it, and not when `review_size` does."""
    definition = with_large_claim()
    definition["rules"]["flag_large"]["on"] = {"answered": "review"}
    definition["rules"]["review_size"] = {
        "display": {"title": "Size the claim from the review"},
        "on": {"answered": "review"},
        "then": {"set": {"large_claim": {"==": [{"var": "review.outcome"}, "approve"]}}},
    }
    return definition


def test_a_field_only_some_writers_make_untrusted_warns() -> None:
    # Whether flag_large acts depends on which rule set large_claim last: a warning, never an
    # error, which must hold for every case (brief, D34, D42).
    found = [i for i in issues(with_two_sizers()) if i.path == "rules.flag_large.when"]
    assert found == [
        Issue(
            "rules.flag_large.when",
            "WRITER_DECIDES",
            "flag_large's condition reads large_claim, which comes from untrusted:customer when "
            "size_up sets it, and not when review_size does, and untrusted data can't decide, so "
            "whether it reaches large depends on which rule set large_claim last: set large_claim "
            "only from trusted values",
            "warning",
        )
    ]


def test_a_field_every_writer_makes_untrusted_is_refused() -> None:
    definition = with_two_sizers()
    definition["rules"]["review_size"]["when"] = {">": [{"var": "estimate"}, 1]}
    assert [i.code for i in issues(definition) if i.path == "rules.flag_large.when"] == [
        "UNTRUSTED_TRIGGER"
    ]


def with_owed_from_the_estimate() -> dict[str, Any]:
    """The refund paying what is owed, which `work_out_owed` sets from the customer's estimate."""
    definition = with_owed()
    definition["fields"]["estimate"] = with_large_claim()["fields"]["estimate"]
    definition["rules"]["work_out_owed"]["then"]["set"] = {
        "owed": {"-": [{"var": "estimate"}, {"var": "fee"}]}
    }
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    return definition


def test_an_input_given_a_value_every_writer_makes_untrusted_is_refused() -> None:
    assert [i.code for i in issues(with_owed_from_the_estimate()) if "inputs" in i.path] == [
        "INPUT_POLICY"
    ]


def test_an_input_given_a_value_only_some_writers_make_untrusted_warns() -> None:
    # Refused only when work_out_owed wrote last: a warning, never an error (brief, D42).
    definition = with_owed_from_the_estimate()
    definition["rules"]["owe_all"] = {
        "display": {"title": "Owe all of it"},
        "on": {"answered": "review"},
        "then": {"set": {"owed": {"var": "approved_amount"}}},
    }
    found = [i for i in issues(definition) if i.path == "steps.pay.inputs.amount"]
    assert found == [
        Issue(
            "steps.pay.inputs.amount",
            "WRITER_DECIDES",
            "payments.refund@2 takes amount only from a system or a person, never from untrusted "
            "data, and this value comes from owed (person:answering review, the opener, "
            "untrusted:customer): owed comes from untrusted:customer when work_out_owed sets it, "
            "and not when owe_all does: whether pay is refused depends on which rule set owed "
            "last: set owed only from values the policy takes",
            "warning",
        )
    ]


@pytest.mark.parametrize(
    ("sizers", "code"),
    [(with_large_claim, "INPUT_POLICY"), (with_two_sizers, "WRITER_DECIDES")],
    ids=["every writer untrusted", "some writers untrusted"],
)
def test_a_condition_steering_on_a_set_field_is_claimed_only_where_proven(
    sizers: Any, code: str
) -> None:
    # pay's own `when` lets it start; read untrusted, its inputs are refused (brief, D39). Only
    # where every writer makes it untrusted is that an error (brief, D42).
    definition = sizers()
    del definition["rules"]["flag_large"]
    definition["steps"]["pay"]["when"] = {"==": [{"var": "large_claim"}, False]}
    assert {i.code for i in issues(definition) if i.path.startswith("steps.pay.inputs")} == {code}


@pytest.mark.parametrize(
    ("second_writer", "code"),
    [(False, "INPUT_POLICY"), (True, "WRITER_DECIDES")],
    ids=["every writer untrusted", "some writers untrusted"],
)
def test_a_plan_step_given_a_set_field_is_claimed_only_where_proven(
    second_writer: bool, code: str
) -> None:
    # The plan's payment takes amount only from a system or a person (brief, D36): what the
    # case gives it is followed into the plan, a set field's writers included (brief, D42).
    definition = settled(inputs={"order_id": {"var": "order_id"}, "amount": {"var": "owed"}})
    owed = with_owed_from_the_estimate()
    definition["fields"] |= {name: owed["fields"][name] for name in ("fee", "owed", "estimate")}
    definition["rules"] = {"work_out_owed": owed["rules"]["work_out_owed"]}
    if second_writer:
        definition["rules"]["owe_all"] = {
            "display": {"title": "Owe all of it"},
            "on": {"answered": "review"},
            "then": {"set": {"owed": {"var": "approved_amount"}}},
        }
    found = validate_case(parse_case(definition), CATALOG, plans=PLANS)
    assert [i.code for i in found if i.path == "steps.settle.inputs.amount"] == [code]


def test_a_value_rules_set_may_be_unset() -> None:
    # Nothing pay waits for ensures work_out_owed has set what is owed: it may fail, its
    # condition may be false. Not "given at the opening": the opening never gives it (brief, D42).
    definition = with_owed()
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    assert coded(definition, "MAY_BE_UNSET") == [
        Issue(
            "steps.pay.inputs.amount",
            "MAY_BE_UNSET",
            "pay reads owed, which only rules set (work_out_owed), and nothing pay waits for "
            "ensures they have: then pay fails and needs attention: require a milestone only they "
            "reach, or read it only when it exists",
            "warning",
        )
    ]
    # The proof: run as it is, with a rule whose condition is false, pay fails.
    definition["rules"]["work_out_owed"]["when"] = {"==": [{"var": "review.outcome"}, "reject"]}
    run = run_case(definition, file=FILE, answers=[APPROVED], people=PEOPLE)
    assert run.needs_attention == ["pay#1: amount can't be evaluated: owed has no known sources"]


def test_a_rule_reading_a_value_rules_set_may_find_it_unset() -> None:
    assert [i.code for i in issues(with_large_claim()) if i.path == "rules.flag_large.when"] == [
        "UNTRUSTED_TRIGGER"
    ]
    definition = with_large_claim()
    definition["fields"]["estimate"].pop("source")
    assert [i.code for i in issues(definition) if i.path == "rules.flag_large.when"] == [
        "MAY_BE_UNSET"
    ]


def test_a_value_rules_set_is_surely_set_behind_their_milestone() -> None:
    # work_out_owed sets what is owed before it reaches owed_known, and acts whole or not at all:
    # a step requiring owed_known reads it set (brief, D42).
    definition = with_owed()
    definition["milestones"] = {"owed_known": {"display": {"title": "What is owed is known"}}}
    definition["rules"]["work_out_owed"]["then"]["reach"] = ["owed_known"]
    definition["steps"]["pay"]["requires"] = ["owed_known"]
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    assert coded(definition, "MAY_BE_UNSET") == []
    # A step reaching the same milestone, setting nothing, takes the proof away.
    definition["steps"]["review"]["reaches"] = ["owed_known"]
    assert [i.path for i in coded(definition, "MAY_BE_UNSET")] == ["steps.pay.inputs.amount"]


def test_a_set_expression_is_type_checked() -> None:
    # The same check the runtime makes before the rule reads anything (brief, D35, D42).
    definition = with_owed()
    definition["rules"]["work_out_owed"]["then"]["set"] = {"owed": {"string": [{"var": "fee"}]}}
    assert coded(definition, "EXPRESSION_INVALID") == [
        Issue(
            "rules.work_out_owed.then.set.owed",
            "EXPRESSION_INVALID",
            "owed is a number, and this gives a string: set it from a number",
        )
    ]


def test_a_set_expression_reads_an_outcome() -> None:
    # A rule recording whether the refund was declined, as support follows it up, tells
    # declined from done: someone reads it (brief, D37, D42).
    definition = with_owed()
    definition["steps"]["call_customer"] |= {"display": {"title": "Follow the refund up"}}
    del definition["steps"]["call_customer"]["when"]
    definition["fields"]["declined"] = {"type": "boolean", "display": {"title": "Declined"}}
    definition["rules"]["record_decline"] = {
        "display": {"title": "Record a declined refund"},
        "on": {"started": "call_customer"},
        "then": {"set": {"declined": {"==": [{"var": "pay.outcome"}, "declined"]}}},
    }
    assert coded(definition, "OUTCOME_UNREAD") == []


def test_a_set_reading_on_the_opening_what_a_person_sets_fails_every_time() -> None:
    # On the opening nothing has run, so a value only the review sets is never there: the rule
    # fails every time it fires (brief, D37, D42), as test_a_retried_set_reads_again runs it.
    definition = with_owed()
    rule = definition["rules"]["work_out_owed"]
    rule["on"] = "opened"
    del rule["when"]
    assert [(i.path, i.code) for i in issues(definition) if i.path.startswith("rules.")] == [
        ("rules.work_out_owed.then.set.owed", "SET_AFTER")
    ]


def test_a_set_guarded_by_its_condition_is_not_warned() -> None:
    # The condition is read first: once review.outcome is approve, approved_amount is set.
    assert [i for i in issues(with_owed()) if i.path.startswith("rules.")] == []


def with_settle_reading_what_it_reaches() -> dict[str, Any]:
    """The refund, where `settle` pays what is owed, and what is owed is set only once `settle`
    has reached `settled`."""
    definition = with_owed()
    definition["milestones"] = {"settled": {"display": {"title": "Settled"}}}
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    definition["steps"]["pay"]["reaches"] = ["settled"]
    definition["rules"]["work_out_owed"]["on"] = {"reached": "settled"}
    return definition


def test_set_after_a_rule_is_claimed_only_where_proven() -> None:
    # work_out_owed fires only once pay is done, and pay reads what it sets every time it starts:
    # pay fails every time (brief, D37, D42).
    assert coded(with_settle_reading_what_it_reaches(), "SET_AFTER") == [
        Issue(
            "steps.pay.inputs.amount",
            "SET_AFTER",
            "pay reads owed, which only work_out_owed sets, and work_out_owed fires only after "
            "pay: pay fails every time it starts: read it in a step that comes after "
            "work_out_owed, or run pay after work_out_owed",
        )
    ]
    # A rule on pay's start fires once pay has read it, but a retry reads it again: no proof.
    definition = with_settle_reading_what_it_reaches()
    definition["rules"]["work_out_owed"]["on"] = {"started": "pay"}
    assert coded(definition, "SET_AFTER") == []
    assert [i.path for i in coded(definition, "MAY_BE_UNSET")] == ["steps.pay.inputs.amount"]


def test_a_max_age_on_a_set_value_is_never_refreshed() -> None:
    # A rule doesn't fire again because a fact was refreshed (brief, D33, D42).
    found = [i for i in issues(with_settle()) if i.code == "NEVER_REFRESHED"]
    assert found == [
        Issue(
            "steps.settle.max_age.owed",
            "NEVER_REFRESHED",
            "owed comes from work_out_owed, a rule that computes it, which doesn't fire again "
            "when a fact is fetched again: whenever it is older than settle's max_age allows, a "
            "proposal of settle is refused: keep it only if a person should decide each time",
            "warning",
        )
    ]


# Each other check that reads writers, sources or what a value reveals, with a set field.


def test_a_set_only_rule_whose_moment_never_comes_never_fires() -> None:
    definition = with_owed()
    definition["milestones"] = {"never": {"display": {"title": "Never reached"}}}
    definition["rules"]["work_out_owed"]["on"] = {"reached": "never"}
    assert [i.path for i in coded(definition, "NEVER_FIRES")] == ["rules.work_out_owed.on"]


def test_a_rule_setting_on_the_opening_doesnt_keep_the_case_open() -> None:
    # Setting a field starts nothing, so a case whose only step must be proposed still closes at
    # once (CLOSES_AT_OPENING stays a proof), as the run shows.
    definition = with_owed()
    definition["steps"] = {"review": definition["steps"]["review"] | {"automatic": False}}
    definition["steps"]["review"]["proposed_by"] = ["support"]
    del definition["sequence"]
    definition["rules"]["work_out_owed"] |= {"on": "opened"}
    del definition["rules"]["work_out_owed"]["when"]
    definition["rules"]["work_out_owed"]["then"]["set"] = {"owed": {"var": "fee"}}
    assert [i.code for i in issues(definition)] == ["CLOSES_AT_OPENING"]
    assert run_case(definition, file=FILE, answers=[], people=PEOPLE).closed


def test_a_workflow_step_given_a_value_computed_from_a_sensitive_one_is_refused() -> None:
    # The set field is declared sensitive, as it must be, so SENSITIVE_TO_WORKFLOW still sees it.
    definition = with_national_id()
    definition["steps"]["kyc"] = {
        "kind": "workflow",
        "display": {"title": "Check the customer"},
        "workflow": "kyc.check@1",
        "inputs": {"customer_id": {"var": "risk_band"}},
    }
    assert "SENSITIVE_TO_WORKFLOW" in [i.code for i in issues(definition)]


def test_a_reference_a_rule_copies_goes_where_its_system_is_expected() -> None:
    definition = with_owed()
    definition["fields"]["refunded_order"] = {
        "type": "reference",
        "system": "orders",
        "display": {"title": "Order"},
    }
    definition["rules"]["work_out_owed"]["then"]["set"] = {"refunded_order": {"var": "order_id"}}
    definition["steps"]["pay"]["inputs"]["order_id"] = {"var": "refunded_order"}
    assert [i.code for i in issues(definition) if i.code in ("REFERENCE", "INPUT_TYPE")] == []


def test_an_input_given_a_set_field_of_another_type_is_refused() -> None:
    definition = with_owed()
    definition["fields"]["note"] = {"type": "string", "display": {"title": "Note"}}
    definition["rules"]["work_out_owed"]["then"]["set"] = {"note": {"string": [{"var": "fee"}]}}
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "note"}
    assert "INPUT_TYPE" in [i.code for i in issues(definition)]


def test_an_approver_who_cant_see_a_set_field_is_warned() -> None:
    definition = with_owed()
    definition["fields"]["owed"]["visible_to"] = ["fraud"]
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    assert "APPROVER_CANT_SEE" in [i.code for i in issues(definition)]


def test_a_rule_that_reaches_and_sets_on_untrusted_data_never_sets_either() -> None:
    definition = with_large_claim()
    definition["rules"]["size_up"]["then"]["reach"] = ["large"]
    assert next(i.message for i in coded(definition, "UNTRUSTED_TRIGGER")).startswith(
        "size_up's condition reads estimate, which comes from untrusted:customer whoever writes "
        "it, and untrusted data can't decide, so it never reaches large or sets large_claim"
    )
