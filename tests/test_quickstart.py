"""The quickstart's refund case, run end to end: the tracer bullet's acceptance tests.

They go only through the seams the quickstart shows (`run_case` and what a run reports), so they
stay green while later layers replace everything behind them. See docs/layers/tracer-refund.md.
"""

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from ventoux.case.definition import CaseInvalid
from ventoux.testing import AnswerRefused, CaseRefused, load_definition, run_case

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")

# Who has which role, as the quickstart's tests say it: the test plays the Ventoux API, which
# states each person's roles with their answer (brief, D22).
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"]}


def test_an_undeclared_outcome_is_refused() -> None:
    with pytest.raises(AnswerRefused, match="aprove"):
        run_case(
            REFUND,
            file={"order_id": "ord-1", "amount": 40},
            answers=[("review", "aprove", "ana")],
            people=PEOPLE,
        )


def test_small_refund_needs_no_team_lead() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-1", "amount": 40},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
    )
    assert run.closed
    assert run.reached("pay")


def test_large_refund_waits_for_a_team_lead() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-2", "amount": 250},
        answers=[("review", "approve", "ana", {"approved_amount": 250})],
        people=PEOPLE,
    )
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert not run.reached("pay")
    assert not run.closed


def test_rejected_review_closes_without_paying() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-3", "amount": 250},
        answers=[("review", "reject", "ana")],
        people=PEOPLE,
    )
    assert run.closed
    assert not run.reached("pay")


def test_the_reviewer_cannot_approve_the_payment() -> None:
    # Sam is a team lead, but Sam reviewed: Sam's answer set the amount paid (brief, D11).
    with pytest.raises(
        AnswerRefused, match="sam set approved_amount, which pay uses, so cannot approve it"
    ):
        run_case(
            REFUND,
            file={"order_id": "ord-4", "amount": 250},
            answers=[
                ("review", "approve", "sam", {"approved_amount": 250}),
                ("pay", "approve", "sam"),
            ],
            people=PEOPLE,
        )


def test_a_team_lead_who_did_not_review_approves_and_the_refund_is_paid() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-5", "amount": 250},
        answers=[
            ("review", "approve", "ana", {"approved_amount": 250}),
            ("pay", "approve", "sam"),
        ],
        people=PEOPLE,
    )
    assert run.reached("pay")
    assert run.closed


def test_approving_needs_the_approval_role() -> None:
    # Ana didn't review this one, but she isn't a team lead.
    with pytest.raises(AnswerRefused, match="support-lead"):
        run_case(
            REFUND,
            file={"order_id": "ord-6", "amount": 250},
            answers=[
                ("review", "approve", "sam", {"approved_amount": 250}),
                ("pay", "approve", "ana"),
            ],
            people=PEOPLE,
        )


def test_answering_a_task_needs_its_role() -> None:
    # Eve has no role on refunds, so she can't review one.
    with pytest.raises(AnswerRefused, match="support"):
        run_case(
            REFUND,
            file={"order_id": "ord-7", "amount": 40},
            answers=[("review", "approve", "eve", {"approved_amount": 40})],
            people=PEOPLE,
        )


def test_an_approval_the_engine_cannot_evaluate_stops_the_case() -> None:
    # The tracer review's finding, kept as a regression test (brief: fail closed). The tracer's
    # evaluator returned the unknown `{"now": []}` unchanged, `holds` read it as false, so the
    # approval was "not needed" and a 250 refund was paid without a team lead. Since layer 8 the
    # definition is refused when read, before anything runs.
    definition = copy.deepcopy(REFUND)
    definition["steps"]["pay"]["approval"]["when"] = {"now": []}
    with pytest.raises(CaseInvalid, match="`now` is not an operator"):
        run_case(
            definition,
            file={"order_id": "ord-4", "amount": 250},
            answers=[("review", "approve", "ana", {"approved_amount": 250})],
            people=PEOPLE,
        )


def test_a_definition_is_read_with_exact_decimals(tmp_path: Path) -> None:
    # A JSON number becomes a Decimal as it is read: as a float, 0.1 would already be inexact.
    stored = tmp_path / "definition.json"
    stored.write_text('{"threshold": 0.1}')
    assert load_definition(stored)["threshold"] == Decimal("0.1")


def test_whoever_decides_whether_the_step_runs_cannot_approve_it() -> None:
    # Pay the amount the customer's system sent, but only once the review set an approved amount:
    # Sam's answer decides whether the refund runs, so Sam can't approve it (brief, D11). Found in
    # layer 4: the tracer's own walk missed a field read through `exists`.
    refund = copy.deepcopy(REFUND)
    refund["steps"]["pay"]["inputs"]["amount"] = {"var": "amount"}
    refund["steps"]["pay"]["when"] = {"exists": "approved_amount"}
    refund["steps"]["pay"]["approval"]["when"] = {">": [{"var": "amount"}, 100]}
    with pytest.raises(
        AnswerRefused, match="sam set approved_amount, which decides whether pay runs"
    ):
        run_case(
            refund,
            file={"order_id": "ord-8", "amount": 250},
            answers=[
                ("review", "approve", "sam", {"approved_amount": 250}),
                ("pay", "approve", "sam"),
            ],
            people=PEOPLE,
        )


def test_an_input_that_does_not_fit_is_refused_before_the_refund() -> None:
    # The same check as a plan's, before every activity (docs/layers/05-interpreter.md). Since
    # layer 8 the case file is checked against its fields' types when the case opens, earlier.
    with pytest.raises(CaseRefused, match="order_id is a reference to orders, and the opening"):
        run_case(
            REFUND,
            file={"order_id": 1001, "amount": 40},  # a number: payments.refund@2 takes a text
            answers=[("review", "approve", "ana", {"approved_amount": 40})],
            people=PEOPLE,
        )


def test_a_misspelled_approval_is_refused_never_read_as_not_approved() -> None:
    # Found in the tracer review: `"aprove"` was quietly treated as "not approved" (design
    # question 13). An approval's answers are checked like a task's (brief, D23).
    with pytest.raises(AnswerRefused, match="pay's approval offers approve or reject"):
        run_case(
            REFUND,
            file={"order_id": "ord-9", "amount": 250},
            answers=[
                ("review", "approve", "ana", {"approved_amount": 250}),
                ("pay", "aprove", "sam"),
            ],
            people=PEOPLE,
        )


def test_a_rejected_approval_closes_the_case_without_paying() -> None:
    # Found in the tracer review: a rejection left the case waiting for approval forever. A
    # rejection is an outcome: the step doesn't run, and the case closes (brief, D23).
    run = run_case(
        REFUND,
        file={"order_id": "ord-10", "amount": 250},
        answers=[
            ("review", "approve", "ana", {"approved_amount": 250}),
            ("pay", "reject", "sam"),
        ],
        people=PEOPLE,
    )
    assert not run.reached("pay")
    assert run.waiting_for == []
    assert run.closed


def test_a_person_spelled_another_way_is_refused() -> None:
    # "Sam" is not "sam": the reviewer can't approve under another spelling (brief, D22).
    with pytest.raises(AnswerRefused, match="'Sam' is not written as a person's identifier"):
        run_case(
            REFUND,
            file={"order_id": "ord-11", "amount": 250},
            answers=[
                ("review", "approve", "sam", {"approved_amount": 250}),
                ("pay", "approve", "Sam"),
            ],
            people={**PEOPLE, "Sam": ["support", "support-lead"]},
        )
