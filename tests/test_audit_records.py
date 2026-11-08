"""Audit records: each act a case decides, as data, with the decisions it caused (layer 19a).

Read field by field, never through their lines. See docs/layers/19-audit-keys.md and brief, D76.
"""

import dataclasses
from decimal import Decimal
from typing import Any

import pytest
from cases.refund import refund
from test_sensitive import FILE, NATIONAL_ID, claim, lookup

from ventoux.case.audit import Act, Decision, Fact
from ventoux.case.recording import record_refused
from ventoux.case.runtime import decide
from ventoux.case.state import Answered
from ventoux.core.sensitive import Sensitive
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.converter import ExactPayloadConverter
from ventoux.testing import CATALOG, AnswerRefused, run_case

PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"]}
LARGE = {"order_id": "ord-2", "amount": 250}
REVIEWED = [("review", "approve", "ana", {"approved_amount": 250})]
LATER = 1_800_000_000  # a time after the opening, in seconds since the epoch


def test_a_refused_act_is_one_record_saying_why_and_nothing_else_changes() -> None:
    run = run_case(refund, LARGE, REVIEWED, PEOPLE, engine=3)
    # Ana reviewed it, and isn't a team lead: her approval is refused (brief, D11).
    act = Answered("pay.approval#1", "approve", "ana", frozenset({"support"}), at=LATER)
    with pytest.raises(AnswerRefused) as refused:
        decide(run.definition, CATALOG, run.state, act)

    after = record_refused(run.definition, run.state, act, refused.value)

    record = after.audit[-1]
    assert record.number == len(run.state.audit) + 1
    assert record.at == LATER
    assert record.act == Act(
        "answered", by="ana", roles=("support",), entry="pay.approval#1", outcome="approve"
    )
    # The entry as it was asked: a refused act may name one that doesn't exist, so no step is
    # guessed from it.
    assert record.decisions == [
        Decision("refused", entry="pay.approval#1", reason=str(refused.value))
    ]
    line = f"refused ana's answer approve to pay.approval#1: {refused.value}"
    assert record.lines == [line]
    # Nothing else changed: the refused act is recorded, and the case waits on (brief, D76).
    assert after.history == [*run.state.history, line]
    assert dataclasses.replace(after, audit=run.state.audit, history=run.state.history) == (
        run.state
    )


def test_the_quickstarts_small_refund_records_each_act_and_what_it_decided() -> None:
    run = run_case(
        refund,
        {"order_id": "ord-1", "amount": 40},
        [("review", "approve", "ana", {"approved_amount": 40})],
        PEOPLE,
        engine=3,
    )
    opening, answer, paid = run.audit
    assert [each.number for each in run.audit] == [1, 2, 3]
    assert {(each.release, each.engine) for each in run.audit} == {(None, 3)}  # a draft
    assert opening.act == Act("opened", values={"order_id": "ord-1", "amount": Decimal(40)})
    assert opening.decisions == [
        Decision("started", step="review", entry="review#1", rule="steps.review")
    ]
    assert answer.act == Act(
        "answered",
        by="ana",
        roles=("support",),
        entry="review",
        outcome="approve",
        values={"approved_amount": Decimal(40)},
    )
    # Pay starts on what its condition, its approval's condition and its inputs read: no approval
    # was needed, since the amount is under 100, and the record says on which facts.
    assert answer.decisions == [
        Decision("answered", step="review", entry="review#1", rule="steps.review.outcomes.approve"),
        Decision(
            "started",
            step="pay",
            entry="pay#1",
            rule="steps.pay.when",
            read=(
                Fact("review.outcome", ("person:ana",), "approve"),
                Fact("approved_amount", ("person:ana",), Decimal(40)),
                Fact("order_id", ("system:opener",), "ord-1"),
            ),
        ),
    ]
    assert paid.act.kind == "completed" and paid.act.entry == "pay#1"
    assert paid.decisions == [
        Decision("completed", step="pay", entry="pay#1", rule="steps.pay"),
        Decision("closed", reason="nothing left to do"),
    ]
    # The history, line for line: each record keeps the lines its act added, and nothing else.
    assert [line for each in run.audit for line in each.lines] == run.history


def test_an_approval_that_starts_its_step_is_one_record() -> None:
    # The guide's example: Sam's approval is one act, and pay starting is what it caused.
    run = run_case(
        refund, LARGE, [*REVIEWED, ("pay.approval#1", "approve", "sam")], PEOPLE, engine=3
    )
    _, review, approval, _ = run.audit
    amount = Fact("approved_amount", ("person:ana",), Decimal(250))
    # The review's answer let pay run once a team lead approves: asked, on the amount.
    assert review.decisions[-1] == Decision(
        "admitted",
        step="pay",
        entry="pay.approval#1",
        rule="steps.pay.approval.when",
        read=(amount,),
    )
    assert approval.act == Act(
        "answered",
        by="sam",
        roles=("support", "support-lead"),
        entry="pay.approval#1",
        outcome="approve",
    )
    # What the approver saw: the approval's condition and the inputs (brief, D11).
    assert approval.decisions == [
        Decision(
            "approved",
            step="pay",
            entry="pay.approval#1",
            rule="steps.pay.approval",
            read=(amount, Fact("order_id", ("system:opener",), "ord-2")),
        ),
        Decision(
            "started",
            step="pay",
            entry="pay#1",
            rule="steps.pay.when",
            read=(
                Fact("review.outcome", ("person:ana",), "approve"),
                amount,
                Fact("order_id", ("system:opener",), "ord-2"),
            ),
        ),
    ]


def known(inputs: dict[str, Any]) -> dict[str, Any]:
    """The orders system, which knows every order: a stand-in for any activity."""
    return {"status": "known"}


def checked_claim() -> dict[str, Any]:
    """The case data guide's claim, with a step whose condition reads the national ID, and whose
    input is computed from it."""
    definition = claim()
    definition["steps"]["check"] = lookup(
        {"cat": ["id:", {"var": "national_id"}]},
        when={"==": [{"var": "national_id"}, NATIONAL_ID]},
    )
    return definition


def test_a_sensitive_value_is_never_unwrapped_in_a_record() -> None:
    run = run_case(
        checked_claim(),
        FILE,
        [],
        {"ana": ["adjuster"]},
        activities={"orders.lookup@1": known},
        engine=3,
    )
    opening = run.audit[0]
    assert opening.act.values["national_id"] == Sensitive(NATIONAL_ID)
    [started] = [
        decision
        for each in run.audit
        for decision in each.decisions
        if decision.kind == "started" and decision.step == "check"
    ]
    assert {fact.field: fact.value for fact in started.read}["national_id"] == (
        Sensitive(NATIONAL_ID)
    )
    # Nowhere in any record in clear: a record keeps it wrapped, as the state does (brief, D31).
    assert NATIONAL_ID not in repr(run.audit)


def test_records_cross_continue_as_new_as_they_were() -> None:
    # Records not yet exported cross with the rest of the state, through the same converter: a
    # sensitive value stays wrapped, an amount stays an exact decimal (brief, D27, as amended by
    # D76).
    run = run_case(
        checked_claim(),
        FILE,
        [],
        {"ana": ["adjuster"]},
        activities={"orders.lookup@1": known},
        engine=3,
    )
    types = {name: field.declared for name, field in run.definition.fields.items()}
    payload = ExactPayloadConverter().to_payload(state_as_data(run.state))
    assert payload is not None
    back = state_from_data(ExactPayloadConverter().from_payload(payload, dict), types)
    assert back.audit == run.state.audit != []
    assert back.audit[0].act.values["national_id"] == Sensitive(NATIONAL_ID)
