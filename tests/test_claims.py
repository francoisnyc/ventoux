"""Layer 17a: claiming a task. A task's roles say who may answer it; its holder, who is asked to.
Holding grants nothing, and only the holder answers a held entry (brief, D69).

See docs/layers/17-assignment.md (17a) and docs/guides/cases.md, "Who is asked: claiming and
assigning tasks".
"""

import pytest
from test_case import REFUND

from ventoux.testing import AnswerRefused, ClaimRefused, claim, run_case

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
