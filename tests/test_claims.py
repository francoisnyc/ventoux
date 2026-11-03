"""Layer 17a: claiming a task. A task's roles say who may answer it; its holder, who is asked to.
Holding grants nothing, and only the holder answers a held entry (brief, D69).

See docs/layers/17-assignment.md (17a) and docs/guides/cases.md, "Who is asked: claiming and
assigning tasks".
"""

from typing import Any

import pytest
from test_approvals import FOUR_EYES
from test_case import REFUND, guide_seen_by_support

from ventoux.case.definition import parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, Claimed
from ventoux.testing import CATALOG, START, AnswerRefused, ClaimRefused, claim, give_back, run_case

ORDER = {"order_id": "ord-1", "amount": 250}

# The guide's people: Ana reviews refunds, Sam reviews and leads the team, Lee leads it; Omar
# operates.
PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "omar": ["operations"],
}


def test_a_claim_without_the_tasks_role_is_refused() -> None:
    # The curriculum's negative test: a claim is checked as an answer would be, so someone who
    # couldn't answer the review can't be the one asked to (brief, D69).
    with pytest.raises(
        ClaimRefused,
        match="^omar may not claim review#1: review#1 is answered by support, and omar has "
        "operations$",
    ):
        run_case(REFUND, file=ORDER, answers=[claim("review#1", "omar")], people=PEOPLE)


def test_a_claim_makes_its_person_the_holder() -> None:
    # The guide's first example, as written: Ana holds the review, and the case still waits for
    # the same thing, naming nobody (brief, D24, D69).
    run = run_case(REFUND, file=ORDER, answers=[claim("review#1", "ana")], people=PEOPLE)
    assert run.waiting_for == ["review by support"]
    assert run.assignees == {"review#1": "ana"}
    assert run.history[-1] == "ana claimed review#1 as support"


def test_only_the_holder_answers_a_held_entry() -> None:
    # Holding narrows who may answer, never widens: Sam has the review's role, and is still
    # refused while Ana holds it (brief, D69).
    with pytest.raises(
        AnswerRefused,
        match="^ana holds review#1: ask ana to give it back, or someone who assigns to reassign "
        "it$",
    ):
        run_case(
            REFUND,
            file=ORDER,
            answers=[
                claim("review#1", "ana"),
                ("review", "approve", "sam", {"approved_amount": 250}),
            ],
            people=PEOPLE,
        )
    # The holder's answer is taken, and the assignment ends with the entry.
    run = run_case(
        REFUND,
        file=ORDER,
        answers=[claim("review#1", "ana"), ("review", "approve", "ana", {"approved_amount": 250})],
        people=PEOPLE,
    )
    assert run.reached("review")
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert run.assignees == {}


@pytest.mark.parametrize(
    ("who", "message"),
    [
        ("sam", "^ana holds review#1; ask someone who assigns to reassign it$"),
        ("ana", "^ana already holds review#1$"),
    ],
)
def test_a_held_entry_is_not_claimed_again(who: str, message: str) -> None:
    # One holder at a time: someone else's claim would take the work from Ana, and her own would
    # change nothing (brief, D69).
    with pytest.raises(ClaimRefused, match=message):
        run_case(
            REFUND,
            file=ORDER,
            answers=[claim("review#1", "ana"), claim("review#1", who)],
            people=PEOPLE,
        )


@pytest.mark.parametrize(
    ("script", "message"),
    [
        (
            [claim("review#1", "ana"), give_back("review#1", "sam")],
            "^sam doesn't hold review#1; ana does$",
        ),
        ([give_back("review#1", "ana")], "^nobody holds review#1$"),
    ],
)
def test_only_the_holder_gives_an_entry_back(script: list[Any], message: str) -> None:
    # Giving back is the holder's: anyone else would free work that isn't theirs (brief, D69).
    with pytest.raises(ClaimRefused, match=message):
        run_case(REFUND, file=ORDER, answers=script, people=PEOPLE)


def test_an_entry_given_back_is_in_its_queue_again() -> None:
    # Back in the queue, anyone with the role may claim it, or answer it.
    run = run_case(
        REFUND,
        file=ORDER,
        answers=[claim("review#1", "ana"), give_back("review#1", "ana")],
        people=PEOPLE,
    )
    assert run.assignees == {}
    assert run.history[-2:] == ["ana claimed review#1 as support", "ana gave back review#1"]
    again = run_case(
        REFUND,
        file=ORDER,
        answers=[
            claim("review#1", "ana"),
            give_back("review#1", "ana"),
            ("review", "approve", "sam", {"approved_amount": 250}),
        ],
        people=PEOPLE,
    )
    assert again.reached("review")


# What makes `pay`'s approval open: Sam, who leads the team and reviews too, reviewed the refund.
REVIEWED_BY_SAM = ("review", "approve", "sam", {"approved_amount": 250})


def test_a_claim_of_an_approval_is_refused_to_whom_it_excludes() -> None:
    # The guide's example: Sam set approved_amount, which pay sends, so he can never approve the
    # payment; being asked to would grant him nothing (brief, D11, D69).
    with pytest.raises(
        ClaimRefused,
        match="^sam may not claim pay.approval#1: sam set approved_amount, which pay uses, so "
        "cannot approve it$",
    ):
        run_case(
            REFUND,
            file=ORDER,
            answers=[REVIEWED_BY_SAM, claim("pay.approval#1", "sam")],
            people=PEOPLE,
        )


@pytest.mark.parametrize(
    ("definition", "who", "opened_by"),
    [
        (REFUND, "sam", None),  # whose answer set what pay sends (brief, D11)
        (REFUND, "lee", "lee"),  # who opened the case (brief, D11, D25)
        (guide_seen_by_support(), "lee", None),  # who can't see what pay reads (brief, D30)
    ],
)
def test_a_claim_of_an_approval_is_refused_as_its_answer_would_be(
    definition: dict[str, Any], who: str, opened_by: str | None
) -> None:
    # A claim is judged as that person's approval would be, by the same checks, so a claim can
    # never be taken where the answer would be refused (brief, D69).
    case = parse_case(definition)
    run = run_case(
        definition, file=ORDER, answers=[REVIEWED_BY_SAM], people=PEOPLE, opened_by=opened_by
    )
    roles = frozenset(PEOPLE[who])
    with pytest.raises(AnswerRefused) as answering:
        decide(
            case, CATALOG, run.state, Answered("pay.approval#1", "approve", who, roles, at=START)
        )
    with pytest.raises(ClaimRefused) as claiming:
        decide(case, CATALOG, run.state, Claimed("pay.approval#1", who, roles, at=START))
    assert str(claiming.value) == f"{who} may not claim pay.approval#1: {answering.value}"


def test_an_approval_needing_several_people_cant_be_held() -> None:
    # One entry collects several people's approvals (brief, D47), so no one person can hold it.
    with pytest.raises(
        ClaimRefused, match="^pay.approval#1 needs 2 people, so nobody can hold it$"
    ):
        run_case(
            FOUR_EYES,
            file={"order_id": "ord-1", "amount": 12000},
            answers=[
                ("review", "approve", "ana", {"approved_amount": 12000}),
                claim("pay.approval#1", "lee"),
            ],
            people=PEOPLE,
        )


def test_a_claim_of_an_approval_by_who_may_approve_it_is_taken() -> None:
    # Lee leads the team and had no hand in the amount: she may approve it, so she may hold it.
    run = run_case(
        REFUND,
        file=ORDER,
        answers=[REVIEWED_BY_SAM, claim("pay.approval#1", "lee")],
        people=PEOPLE,
    )
    assert run.assignees == {"pay.approval#1": "lee"}
    assert run.history[-1] == "lee claimed pay.approval#1 as support-lead"
