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
from ventoux.case.forgetting import ForgetRefused
from ventoux.case.runtime import decide
from ventoux.case.state import CaseState, ChangeProposed, ForgetApproved, Opened, StepRun
from ventoux.core.catalog import Catalog
from ventoux.core.sensitive import Sensitive
from ventoux.testing import (
    CATALOG,
    START,
    AnswerRefused,
    Change,
    ChangeRefused,
    as_json,
    close,
    edit,
    finish,
    forget,
    propose,
    retry,
    run_case,
    skip,
    wrapped,
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
    with pytest.raises(
        ChangeRefused,
        match="^rename is not a kind of change: a change is an edit, a skip or a migration$",
    ):
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


# --- Slice 3: skips ---

SMALL = {"order_id": "ord-1", "amount": 40}
SMALL_REVIEW = ("review", "approve", "ana", {"approved_amount": 40})
# Who operates, here, besides Omar and Olga: Ana and Sam work the refund too, Lee leads the team,
# Pia opened the case.
OPERATING = {
    "ana": ["support", "operations"],
    "sam": ["support", "operations"],
    "lee": ["support-lead", "operations"],
    "pia": ["support", "operations"],
    "omar": ["operations"],
    "olga": ["operations"],
}


def account_closed(inputs: dict[str, Any]) -> dict[str, Any]:
    """The payment provider: the customer's account is closed, so it never succeeds."""
    raise ConnectionError("account closed")


def test_a_self_approved_skip_is_refused() -> None:
    # Nothing is skipped automatically, nor by one person alone (brief, D17) (brief, D52).
    with pytest.raises(AnswerRefused, match="^omar proposed case.change#1, so cannot approve it$"):
        run_case(
            REFUND,
            file=SMALL,
            answers=[SMALL_REVIEW, skip("pay#1", "omar"), ("case.change#1", "approve", "omar")],
            people=OPERATING,
            activities={"payments.refund@2": account_closed},
        )


def refused_skip_approval(
    definition: dict[str, Any], file: dict[str, Any], before: list[Any], by: str
) -> str:
    """What the engine says when `by` approves Omar's skip of `pay#1`, after `before`."""
    with pytest.raises(AnswerRefused) as refused:
        run_case(
            definition,
            file=file,
            answers=[*before, skip("pay#1", "omar"), ("case.change#1", "approve", by)],
            people=OPERATING,
            activities={"payments.refund@2": account_closed},
            opened_by="pia",
        )
    return str(refused.value)


def test_a_skip_excludes_who_the_run_excluded() -> None:
    # Skipping a run decides its fate, as approving it did: whoever may not approve the run may
    # not approve its skip, nor whoever proposed or approved it (brief, D52).
    assert refused_skip_approval(REFUND, SMALL, [SMALL_REVIEW], "ana") == (
        "ana set approved_amount, which pay uses, so cannot approve it, nor skip pay#1"
    )
    assert refused_skip_approval(REFUND, SMALL, [SMALL_REVIEW], "pia") == (
        "pia opened the case, so cannot approve a change to it"
    )
    approved = [TYPED_WRONG, ("pay.approval#1", "approve", "lee")]
    assert refused_skip_approval(REFUND, LARGE, approved, "lee") == (
        "lee approved pay.approval#1, so cannot approve skipping pay#1"
    )
    proposed = copy.deepcopy(REFUND)
    proposed["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support"]}
    # Kept open for Sam's proposal, so it names how a person closes it.
    proposed["stays_open"] = True
    proposed["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    by_sam = [SMALL_REVIEW, propose("pay", "sam")]
    assert refused_skip_approval(proposed, SMALL, by_sam, "sam") == (
        "sam proposed pay, so cannot approve it, nor skip pay#1"
    )
    # A run that failed before it started (its amount untrusted, which pay refuses) keeps its
    # proposer too.
    untrusted = kept_open()
    untrusted["fields"]["approved_amount"]["source"] = "untrusted:customer"
    approved_by_lee = [*by_sam, ("pay.approval#1", "approve", "lee")]
    refused_start = run_case(
        untrusted, file=SMALL, answers=approved_by_lee, people=OPERATING, opened_by="pia"
    )
    assert refused_start.state.runs[-1].started is False
    assert refused_skip_approval(untrusted, SMALL, approved_by_lee, "sam") == (
        "sam proposed pay, so cannot approve it, nor skip pay#1"
    )
    # Olga is none of them: she approves it.
    skipped = run_case(
        proposed,
        file=SMALL,
        answers=[*by_sam, skip("pay#1", "omar"), ("case.change#1", "approve", "olga")],
        people=OPERATING,
        activities={"payments.refund@2": account_closed},
        opened_by="pia",
    )
    assert "applied case.change#1: pay#1 skipped by omar, approved by olga" in skipped.history


def test_a_skipped_run_is_neither_done_nor_failed() -> None:
    # `call_customer` requires pay: a skipped run isn't done, so it never starts; nothing pay
    # would have given is in the case file; nothing needs attention, so the case closes.
    skipped = run_case(
        REFUND,
        file=SMALL,
        answers=[SMALL_REVIEW, skip("pay#1", "omar"), ("case.change#1", "approve", "olga")],
        people=OPERATING,
        activities={"payments.refund@2": account_closed},
    )
    assert skipped.history[-4:] == [
        "omar proposed case.change#1: skip pay#1, to be approved by operations",
        "olga answered case.change#1 approve as operations",
        "applied case.change#1: pay#1 skipped by omar, approved by olga",
        "closed: nothing left to do",
    ]
    assert [run.status for run in skipped.state.runs] == ["done", "skipped"]
    assert "pay.outcome" not in skipped.state.values
    assert not skipped.reached("pay") and not skipped.reached("call_customer")
    assert skipped.needs_attention == []


def refused_skip(answers: list[Any]) -> str:
    """What the engine says when Omar proposes skipping `pay#1`, after `answers`."""
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            REFUND,
            file=SMALL,
            answers=[*answers, skip("pay#1", "omar")],
            people=OPERATING,
            activities={"payments.refund@2": account_closed},
        )
    return str(refused.value)


def test_only_a_failed_latest_run_is_skipped() -> None:
    assert refused_skip([]) == "pay#1 is not a run of refund"
    # Still running: it hasn't failed.
    with pytest.raises(ChangeRefused, match="^pay#1 can't be skipped: it hasn't failed$"):
        run_case(
            REFUND,
            file=SMALL,
            answers=[SMALL_REVIEW, skip("pay#1", "omar")],
            people=OPERATING,
            held=["pay"],
        )
    # A later run of its step (a refresh, beside it): only a step's latest run is skipped, as
    # only it is retried (brief, D26).
    failed = run_case(
        REFUND,
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=OPERATING,
        activities={"payments.refund@2": account_closed},
    ).state
    failed.runs.append(StepRun("pay#2", "pay", "running"))
    later = ChangeProposed("skip", "pay#1", None, "omar", frozenset(["operations"]), at=START)
    with pytest.raises(
        ChangeRefused,
        match="^pay#1 can't be skipped: pay#2 has run since, and only a step's latest run is "
        "skipped$",
    ):
        decide(parse_case(REFUND), CATALOG, failed, later)


def kept_open() -> dict[str, Any]:
    """The refund, its payment proposed by support, kept open until a person closes it."""
    definition = copy.deepcopy(REFUND)
    definition["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support"]}
    definition["stays_open"] = True
    definition["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    return definition


def test_a_skip_of_a_run_retried_meanwhile_is_not_applied() -> None:
    # Olga's retry ran the payment while Omar's skip waited: Lee's approval applies nothing.
    retried = run_case(
        kept_open(),
        file=SMALL,
        answers=[
            SMALL_REVIEW,
            propose("pay", "sam"),
            skip("pay#1", "omar"),
            retry("pay#1", "olga"),
            ("case.change#1", "approve", "lee"),
        ],
        people=OPERATING,
        activities={"payments.refund@2": failing_once()},
    )
    assert retried.history[-1] == (
        "case.change#1 not applied: pay#1 can't be skipped: it hasn't failed"
    )
    assert retried.reached("pay")


def notifying() -> dict[str, Any]:
    """The refund that closes once paid, with a letter drafted beside the payment."""
    definition = copy.deepcopy(REFUND)
    definition["closes_when"] = ["paid"]
    definition["milestones"] = {"paid": {"display": {"title": "Refund paid"}}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["steps"]["notify"] = {
        "kind": "activity",
        "display": {"title": "Draft a letter about the refund"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "order_id"}, "template": "refund"},
    }
    return definition


def letter_down(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("provider unreachable")


def test_a_skip_lets_a_held_close_complete() -> None:
    # `paid` is reached, and the failed letter holds the close: nothing new starts, but a skip of
    # the run that holds it is taken, and the case closes (brief, D34) (brief, D52).
    skipped = run_case(
        notifying(),
        file=SMALL,
        answers=[SMALL_REVIEW, skip("notify#1", "omar"), ("case.change#1", "approve", "olga")],
        people=OPERATING,
        activities={"letters.draft@2": letter_down},
    )
    assert skipped.history[-2:] == [
        "applied case.change#1: notify#1 skipped by omar, approved by olga",
        "closed: paid reached",
    ]
    assert skipped.flags == []


def test_a_skipped_runs_timers_end_with_it() -> None:
    # A timer set on a run's start lives while the run does: skipped, the run has ended, and so
    # has the timer, saying so (brief, D44) (brief, D52).
    definition = kept_open()
    definition["milestones"] = {"chased": {"display": {"title": "Payment chased"}}}
    definition["rules"] = {
        "chase_pay": {
            "display": {"title": "Chase a payment left failing for two days"},
            "on": {"after": "2d", "since": {"started": "pay"}},
            "then": {"reach": ["chased"]},
        }
    }
    skipped = run_case(
        definition,
        file=SMALL,
        answers=[
            SMALL_REVIEW,
            propose("pay", "sam"),
            skip("pay#1", "omar"),
            ("case.change#1", "approve", "olga"),
        ],
        people=OPERATING,
        activities={"payments.refund@2": account_closed},
    )
    assert skipped.history[-1] == "cancelled chase_pay, 2d after started pay#1: pay#1 is skipped"
    assert skipped.timers == []


# --- Slice 4: pending requests and the close ---


def test_a_pending_request_is_cancelled_by_the_close() -> None:
    # Not pending work: a request keeps no case open (brief, D10). When the case closes, it is
    # cancelled, saying so, as an open approval is (brief, D52).
    closable = copy.deepcopy(REFUND)
    closable["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    }
    closed = run_case(
        closable,
        file=LARGE,
        answers=[TYPED_WRONG, edit("approved_amount", 250, "ana"), close("duplicate", "sam")],
        people=PEOPLE,
    )
    assert "cancelled case.change#1: closed as duplicate by sam" in closed.history
    assert closed.closed and closed.state.changes == {}
    # Closing by itself, with nothing left to do, cancels it too.
    paid = run_case(
        REFUND,
        file=SMALL,
        answers=[SMALL_REVIEW, edit("approved_amount", 45, "ana"), finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    assert paid.history[-2:] == [
        "cancelled case.change#1: nothing left to do",
        "closed: nothing left to do",
    ]
    assert paid.waiting_for == []


# --- Slice 6: forgetting under the same rules ---

FORGETTERS = {"pia": ["privacy"], "olu": ["privacy"]}


def test_forget_excludes_the_opener_from_engine_2() -> None:
    # Olu opened the claim: from engine 2 the case refuses his approval of forgetting it, as of
    # any change to it, depending on nothing the request did (brief, D52).
    with pytest.raises(
        ForgetRefused, match="^olu opened the case, so cannot approve forgetting it$"
    ):
        run_case(
            claim(), file=FILE, answers=[forget("pia", "olu")], people=FORGETTERS, opened_by="olu"
        )
    # A case opened at engine 1 keeps 9c's rule, so a history recorded then replays as it was
    # (brief, D51).
    case = parse_case(claim())
    opening = Opened(wrapped(case, as_json(FILE)), "olu", at=START, engine=1)
    opened, _ = decide(case, CATALOG, CaseState("claim-7/run"), opening)
    approved = ForgetApproved(
        "pia", frozenset({"privacy"}), "olu", frozenset({"privacy"}), at=START
    )
    forgotten, _ = decide(case, CATALOG, opened, approved)
    assert forgotten.history[-1] == "closed: forgotten"


# --- Slice 7: the guide, and what the history says ---

GUIDE = (ROOT / "docs" / "guides" / "cases.md").read_text()
SECTION = GUIDE.split("## Changing an open case\n")[1].split("\n## ")[0]


def guide_blocks(language: str) -> list[str]:
    """The section's code blocks in `language` (`""` for plain ones), in order."""
    parts = SECTION.split("```")
    return [
        part.removeprefix(language + "\n")
        for part in parts[1::2]
        if part.split("\n")[0] == language
    ]


def test_the_guides_change_example_runs_as_written() -> None:
    # Our own documentation, run so it can't drift from the code; never a definition (data).
    registering, typo, skipping, on_temporal = guide_blocks("python")
    catalog = Catalog()
    exec(registering, {"catalog": catalog})  # noqa: S102
    assert (catalog.editors, catalog.operators) == (["support", "support-lead"], ["operations"])
    namespace: dict[str, Any] = {
        "run_case": run_case,
        "refund": REFUND,
        "edit": edit,
        "skip": skip,
        "account_closed": account_closed,
        "PEOPLE": {**PEOPLE, "olga": ["operations"]},
    }
    for code in (typo, skipping):
        exec(code, namespace)  # noqa: S102
    for name, shown in zip(("typo", "skipped"), guide_blocks(""), strict=True):
        lines = shown.splitlines()
        history = namespace[name].history
        first = history.index(lines[0])
        assert history[first : first + len(lines)] == lines, name
    assert "propose_change(case," in on_temporal  # run on Temporal's test server (12c, slice 7)
    # The refusals the prose quotes are the engine's: each is said by a test above.
    said = " ".join(SECTION.split())
    for quoted in (
        "pay.outcome is not a field of refund: only a declared field is edited",
        "approved_amount holds no value yet: an edit changes a value, never gives the first",
        "approved_amount is a number, and the edit gives a string",
        "approved_amount already holds that value: an edit changes it",
        (
            "case.change#1 not applied: approved_amount changed since it was proposed: propose "
            "it again"
        ),
        "pay#1 can't be skipped: it hasn't failed",
        "lee answered case.change#1 reject as support-lead",
        "case.change#1 not applied: lee rejected it",
    ):
        assert f"`{quoted}`" in said, quoted
    assert refused_edit("pay.outcome", "done") == (
        "pay.outcome is not a field of refund: only a declared field is edited"
    )


SECRET_ORDER = "ORD-7-SECRET"  # an order, and amounts, to look for where they mustn't be
SECRET_AMOUNTS = (12345, 54321, 67890, 77777)


def test_the_history_names_no_value() -> None:
    # Every line a request adds names people, roles, fields, runs and requests, never a value:
    # a history reaches people who may not see one (brief, D30) (brief, D52).
    file = {"order_id": SECRET_ORDER, "amount": SECRET_AMOUNTS[0]}
    review = ("review", "approve", "ana", {"approved_amount": SECRET_AMOUNTS[0]})
    edited = run_case(
        reworkable(),
        file=file,
        answers=[
            review,
            edit("approved_amount", SECRET_AMOUNTS[1], "ana"),
            ("case.change#1", "reject", "lee"),
            edit("approved_amount", SECRET_AMOUNTS[1], "ana"),
            ("case.change#2", "approve", "lee"),
            edit("approved_amount", SECRET_AMOUNTS[2], "sam"),
            propose("review", "sam"),
            ("review#2", "approve", "sam", {"approved_amount": SECRET_AMOUNTS[3]}),
            ("case.change#3", "approve", "lee"),
        ],
        people=PEOPLE,
    )
    skipped = run_case(
        REFUND,
        file=file,
        answers=[review, ("pay.approval#1", "approve", "lee"), skip("pay#1", "omar")],
        people=OPERATING,
        activities={"payments.refund@2": account_closed},
    )
    lines = [line for line in edited.history + skipped.history if "change#" in line]
    assert len(lines) >= 10
    for line in lines:
        assert SECRET_ORDER not in line
        assert not any(str(amount) in line for amount in SECRET_AMOUNTS), line
