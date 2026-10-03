"""The quickstart's refund case, run end to end: the tracer bullet's acceptance tests.

They go only through the seams the quickstart shows (`run_case` and what a run reports), so they
stay green while later layers replace everything behind them. See docs/layers/tracer-refund.md.
"""

from pathlib import Path

import pytest

from ventoux.testing import AnswerRefused, load_definition, run_case

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")


def test_an_undeclared_outcome_is_refused() -> None:
    with pytest.raises(AnswerRefused, match="aprove"):
        run_case(
            REFUND, file={"order_id": "ord-1", "amount": 40}, answers=[("review", "aprove", "ana")]
        )


def test_small_refund_needs_no_team_lead() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-1", "amount": 40},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
    )
    assert run.closed
    assert run.reached("pay")


def test_large_refund_waits_for_a_team_lead() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-2", "amount": 250},
        answers=[("review", "approve", "ana", {"approved_amount": 250})],
    )
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert not run.reached("pay")
    assert not run.closed


def test_rejected_review_closes_without_paying() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-3", "amount": 250},
        answers=[("review", "reject", "ana")],
    )
    assert run.closed
    assert not run.reached("pay")


def test_the_reviewer_cannot_approve_the_payment() -> None:
    # Sam is a team lead, but he reviewed: his answer set the amount paid (D11).
    with pytest.raises(AnswerRefused, match="sam"):
        run_case(
            REFUND,
            file={"order_id": "ord-4", "amount": 250},
            answers=[
                ("review", "approve", "sam", {"approved_amount": 250}),
                ("pay", "approve", "sam"),
            ],
        )


def test_a_team_lead_who_did_not_review_approves_and_the_refund_is_paid() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-5", "amount": 250},
        answers=[
            ("review", "approve", "ana", {"approved_amount": 250}),
            ("pay", "approve", "sam"),
        ],
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
        )
