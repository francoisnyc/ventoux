"""Layer 12c: change requests. One person proposes a change to an open case, someone else
approves it, and the case applies it, checked again against the case as it is then (brief, D52).

See docs/layers/12-releases.md (12c) and docs/guides/cases.md, "Changing an open case".
"""

import copy
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from test_case import REFUND, reworkable
from test_sensitive import FILE, NATIONAL_ID, claim

from ventoux.case.definition import parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import ChangeProposed
from ventoux.core.sensitive import Sensitive
from ventoux.testing import (
    CATALOG,
    START,
    AnswerRefused,
    Change,
    ChangeRefused,
    edit,
    propose,
    retry,
    run_case,
)

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


# --- Slice 2: edits ---


def refused_edit(field: str, value: object, before: list[object] | None = None) -> str:
    """What the engine says when Ana proposes editing `field` to `value`, after `before`."""
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            REFUND,
            file=LARGE,
            answers=[*(before if before is not None else [TYPED_WRONG]), edit(field, value, "ana")],
            people=PEOPLE,
        )
    return str(refused.value)


def test_a_proposal_is_checked_when_made() -> None:
    # Refused at once, and nothing is pending: a request that could never apply waits for nobody.
    assert refused_edit("approved", 250) == (
        "approved is not a field of refund: only a declared field is edited"
    )
    assert refused_edit("approved_amount", 250, before=[]) == (
        "approved_amount holds no value yet: an edit changes a value, never gives the first"
    )
    # The type, never the value: a refusal reaches people who may not see it (brief, D30).
    assert refused_edit("approved_amount", "250") == (
        "approved_amount is a number, and the edit gives a string"
    )


def test_a_record_of_what_happened_is_never_edited() -> None:
    # An outcome or a step's output records what happened: only a declared field is edited.
    assert refused_edit("review.outcome", "reject") == (
        "review.outcome is not a field of refund: only a declared field is edited"
    )
    assert refused_edit("pay.refund_id", "refund-2") == (
        "pay.refund_id is not a field of refund: only a declared field is edited"
    )


def test_an_edit_never_launders_a_value() -> None:
    # An edit to the value the field holds would change nothing but its sources: an untrusted
    # value would read as two people's. Refused when proposed (brief, D52).
    assert refused_edit("approved_amount", 2500) == (
        "approved_amount already holds that value: an edit changes it"
    )
    # And when applied: Sam's rework gave the field the edit's value meanwhile, so Lee's approval
    # applies nothing, and the value stays Sam's.
    reworked = run_case(
        reworkable(),
        file=LARGE,
        answers=[
            TYPED_WRONG,
            edit("approved_amount", 250, "ana"),
            propose("review", "sam"),
            ("review#2", "approve", "sam", {"approved_amount": 250}),
            ("case.change#1", "approve", "lee"),
        ],
        people=PEOPLE,
    )
    assert reworked.history[-1] == (
        "case.change#1 not applied: approved_amount already holds that value: an edit changes it"
    )
    assert reworked.state.sources["approved_amount"] == frozenset({"person:sam"})


def test_an_edit_whose_field_changed_is_not_applied() -> None:
    # Lee judged a correction of 2500; Sam's rework set 300 meanwhile: the edit isn't applied,
    # and the value stays Sam's (brief, D52).
    reworked = run_case(
        reworkable(),
        file=LARGE,
        answers=[
            TYPED_WRONG,
            edit("approved_amount", 250, "ana"),
            propose("review", "sam"),
            ("review#2", "approve", "sam", {"approved_amount": 300}),
            ("case.change#1", "approve", "lee"),
        ],
        people=PEOPLE,
    )
    assert reworked.history[-2:] == [
        "lee answered case.change#1 approve as support-lead",
        "case.change#1 not applied: approved_amount changed since it was proposed: propose it again",
    ]
    assert reworked.state.values["approved_amount"] == Decimal(300)


def test_an_edited_value_is_its_deciders() -> None:
    edited = [TYPED_WRONG, edit("approved_amount", 250, "ana"), ("case.change#1", "approve", "lee")]
    run = run_case(REFUND, file=LARGE, answers=edited, people=PEOPLE)
    assert run.state.values["approved_amount"] == Decimal(250)
    assert run.state.sources["approved_amount"] == frozenset({"person:ana", "person:lee"})
    # So neither approves the payment that reads it (brief, D11); Sam does.
    with pytest.raises(
        AnswerRefused, match="^lee set approved_amount, which pay uses, so cannot approve it$"
    ):
        run_case(
            REFUND,
            file=LARGE,
            answers=[*edited, ("pay.approval#2", "approve", "lee")],
            people=PEOPLE,
        )
    paid = run_case(
        REFUND, file=LARGE, answers=[*edited, ("pay.approval#2", "approve", "sam")], people=PEOPLE
    )
    assert paid.closed
    # A field declared untrusted keeps its mark: an edit never makes untrusted data trusted.
    declared = copy.deepcopy(REFUND)
    declared["fields"]["approved_amount"]["source"] = "untrusted:customer"
    marked = run_case(declared, file=LARGE, answers=edited, people=PEOPLE)
    assert marked.state.sources["approved_amount"] == frozenset(
        {"person:ana", "person:lee", "untrusted:customer"}
    )


def failing_once() -> Callable[[dict[str, Any]], dict[str, Any]]:
    """The payment provider, down for the first call, then up."""
    calls: list[str] = []

    def pay(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs["idempotency_key"])
        if len(calls) == 1:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-ord-1"}

    return pay


def test_an_edit_withdraws_and_lapses_what_saw_the_old_value() -> None:
    # An open approval saw the old value: withdrawn, and asked again (brief, D25).
    edited = [TYPED_WRONG, edit("approved_amount", 250, "ana"), ("case.change#1", "approve", "lee")]
    run = run_case(REFUND, file=LARGE, answers=edited, people=PEOPLE)
    assert run.history[-3:] == [
        "applied case.change#1: approved_amount edited by ana, approved by lee",
        "withdrew pay.approval#1: approved_amount changed",
        "asked pay.approval#2: approval of pay by support-lead",
    ]
    # Every approval on the entry at once (brief, D47).
    two = copy.deepcopy(REFUND)
    two["steps"]["pay"]["approval"]["count"] = 2
    half = run_case(
        two,
        file=LARGE,
        answers=[TYPED_WRONG, ("pay.approval#1", "approve", "sam"), *edited[1:]],
        people=PEOPLE,
    )
    assert "withdrew pay.approval#1: approved_amount changed, with 1 of 2 approvals given" in (
        half.history
    )
    # An approval spent on a run that failed saw the old value too: it lapses with the edit, and
    # the run's retry asks again, never stopping on a change two people approved (brief, D52).
    retried = run_case(
        REFUND,
        file=LARGE,
        answers=[
            TYPED_WRONG,
            ("pay.approval#1", "approve", "sam"),
            *edited[1:],
            retry("pay#1", "omar"),
        ],
        people=PEOPLE,
        activities={"payments.refund@2": failing_once()},
    )
    assert retried.history[-4:] == [
        "applied case.change#1: approved_amount edited by ana, approved by lee",
        "lapsed pay.approval#1: approved_amount changed",
        "omar retried pay#1 as operations",
        "asked pay.approval#2: approval of pay by support-lead",
    ]
    assert retried.needs_attention == []


# Kim and Lee see the claim's national ID; Ana and Sam don't. All four may edit a case file.
CLAIMS = {
    "ana": ["adjuster", "support"],
    "sam": ["support", "support-lead"],
    "kim": ["claims-sensitive", "support"],
    "lee": ["claims-sensitive", "support-lead"],
}
CORRECTED_ID = "2 90 01 75 123 456 78"


def test_a_sensitive_value_is_edited_sealed() -> None:
    # The new value crosses sealed, as an answer's form does, and no line quotes it (brief, D31).
    run = run_case(
        claim(),
        file=FILE,
        answers=[edit("national_id", CORRECTED_ID, "kim"), ("case.change#1", "approve", "lee")],
        people=CLAIMS,
    )
    kept = run.state.values["national_id"]
    assert isinstance(kept, Sensitive) and kept.value == CORRECTED_ID
    assert not any(CORRECTED_ID in line or NATIONAL_ID in line for line in run.history)
    # Sent in plain text, it has already crossed unsealed: refused, saying so.
    opened = run_case(claim(), file=FILE, answers=[], people=CLAIMS).state
    plain_text = ChangeProposed(
        "edit", "national_id", CORRECTED_ID, "kim", frozenset(CLAIMS["kim"]), at=START
    )
    with pytest.raises(
        ChangeRefused, match="^national_id is sensitive and was given in plain text"
    ):
        decide(parse_case(claim()), CATALOG, opened, plain_text)


def test_an_edit_is_judged_by_people_who_see_it() -> None:
    # Nobody proposes or approves a value hidden from them: an approver judges what they see
    # (brief, D30).
    with pytest.raises(
        ChangeRefused, match="^ana can't see national_id: it needs claims-sensitive$"
    ):
        run_case(
            claim(), file=FILE, answers=[edit("national_id", CORRECTED_ID, "ana")], people=CLAIMS
        )
    with pytest.raises(
        AnswerRefused, match="^sam can't see national_id: it needs claims-sensitive$"
    ):
        run_case(
            claim(),
            file=FILE,
            answers=[edit("national_id", CORRECTED_ID, "kim"), ("case.change#1", "approve", "sam")],
            people=CLAIMS,
        )


def test_an_edit_excludes_the_values_writer() -> None:
    # Ana's answer gave the value: Sam's edit overrules her, so she doesn't approve it (brief, D11).
    with pytest.raises(
        AnswerRefused, match="^ana set approved_amount, so cannot approve a change to it$"
    ):
        run_case(
            REFUND,
            file=LARGE,
            answers=[
                TYPED_WRONG,
                edit("approved_amount", 250, "sam"),
                ("case.change#1", "approve", "ana"),
            ],
            people=PEOPLE,
        )
    # Nor do the two people who decided an earlier edit of it.
    edited = [TYPED_WRONG, edit("approved_amount", 250, "ana"), ("case.change#1", "approve", "lee")]
    with pytest.raises(
        AnswerRefused, match="^lee set approved_amount, so cannot approve a change to it$"
    ):
        run_case(
            REFUND,
            file=LARGE,
            answers=[
                *edited,
                edit("approved_amount", 260, "sam"),
                ("case.change#2", "approve", "lee"),
            ],
            people=PEOPLE,
        )
