"""Layer 12c: change requests. One person proposes a change to an open case, someone else
approves it, and the case applies it, checked again against the case as it is then (brief, D52).

See docs/layers/12-releases.md (12c) and docs/guides/cases.md, "Changing an open case".
"""

from decimal import Decimal
from pathlib import Path

import pytest
from test_case import REFUND

from ventoux.testing import AnswerRefused, Change, ChangeRefused, edit, run_case

ROOT = Path(__file__).parent.parent
LARGE = {"order_id": "ord-1", "amount": 250}
TYPED_WRONG = ("review", "approve", "ana", {"approved_amount": 2500})  # Ana meant 250

# Ana and Sam work the refund, Lee leads the team; Omar and Olga operate; Pia opens cases.
PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "pia": ["support", "support-lead"],
    "omar": ["operations"],
    "olga": ["operations"],
}


# --- Slice 1: the lifecycle ---


def test_a_self_approved_change_is_refused() -> None:
    # The curriculum's negative test: nobody approves a change they proposed (brief, D52).
    with pytest.raises(AnswerRefused, match="^ana proposed case.change#1, so cannot approve it$"):
        run_case(
            REFUND,
            file=LARGE,
            answers=[
                TYPED_WRONG,
                edit("approved_amount", 250, "ana"),
                ("case.change#1", "approve", "ana"),
            ],
            people=PEOPLE,
        )
    # Refused, and the request waits on: someone else may approve it.
    waiting = run_case(
        REFUND,
        file=LARGE,
        answers=[TYPED_WRONG, edit("approved_amount", 250, "ana")],
        people=PEOPLE,
    )
    assert "approval of case.change#1 (edit approved_amount) by support or support-lead" in (
        waiting.waiting_for
    )
    assert waiting.state.values["approved_amount"] == Decimal(2500)


def test_the_opener_approves_no_change() -> None:
    # Pia opened the case: she approves none of its steps (brief, D25), nor a change to it, which
    # decides as much as a step's run (brief, D52).
    with pytest.raises(
        AnswerRefused, match="^pia opened the case, so cannot approve a change to it$"
    ):
        run_case(
            REFUND,
            file=LARGE,
            answers=[
                TYPED_WRONG,
                edit("approved_amount", 250, "ana"),
                ("case.change#1", "approve", "pia"),
            ],
            people=PEOPLE,
            opened_by="pia",
        )


def test_a_rejected_change_changes_nothing() -> None:
    proposed = [TYPED_WRONG, edit("approved_amount", 250, "ana")]
    rejected = run_case(
        REFUND, file=LARGE, answers=[*proposed, ("case.change#1", "reject", "lee")], people=PEOPLE
    )
    assert rejected.history[-2:] == [
        "lee answered case.change#1 reject as support-lead",
        "case.change#1 not applied: lee rejected it",
    ]
    assert rejected.state.values["approved_amount"] == Decimal(2500)
    assert rejected.waiting_for == ["approval of pay by support-lead"]
    # Answered once: a second answer is refused, as on any entry (layer 6).
    with pytest.raises(AnswerRefused, match="^case.change#1 is closed$"):
        run_case(
            REFUND,
            file=LARGE,
            answers=[
                *proposed,
                ("case.change#1", "reject", "lee"),
                ("case.change#1", "approve", "sam"),
            ],
            people=PEOPLE,
        )


def test_what_a_request_doesnt_know_is_refused() -> None:
    # Fail closed: a kind, an outcome or a role the engine doesn't know is refused, never read as
    # one it does; a refused proposal leaves nothing pending.
    with pytest.raises(ChangeRefused, match="^rename is not a kind of change: a change is an edit"):
        run_case(
            REFUND,
            file=LARGE,
            answers=[TYPED_WRONG, Change("rename", "approved_amount", 250, "ana")],
            people=PEOPLE,
        )
    with pytest.raises(
        AnswerRefused, match="^case.change#1 offers approve or reject, and the answer is 'aprove'$"
    ):
        run_case(
            REFUND,
            file=LARGE,
            answers=[
                TYPED_WRONG,
                edit("approved_amount", 250, "ana"),
                ("case.change#1", "aprove", "lee"),
            ],
            people=PEOPLE,
        )
    with pytest.raises(
        ChangeRefused,
        match="^an edit is proposed by support or support-lead, and omar has operations$",
    ):
        run_case(
            REFUND,
            file=LARGE,
            answers=[TYPED_WRONG, edit("approved_amount", 250, "omar")],
            people=PEOPLE,
        )
    with pytest.raises(
        AnswerRefused,
        match="^an edit is approved by support or support-lead, and omar has operations$",
    ):
        run_case(
            REFUND,
            file=LARGE,
            answers=[
                TYPED_WRONG,
                edit("approved_amount", 250, "ana"),
                ("case.change#1", "approve", "omar"),
            ],
            people=PEOPLE,
        )
