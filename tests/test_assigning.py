"""Layer 17b: assigning a task. An assigner moves work between people, or back to its queue,
without its holder; they never answer it, and never move the approval of a step they may not
approve (brief, D70).

See docs/layers/17-assignment.md (17b) and docs/guides/cases.md, "Assigning, reassigning,
returning to the queue".
"""

from typing import Any

import pytest
from test_case import REFUND, guide_seen_by_support

from ventoux.testing import AnswerRefused, ClaimRefused, assign, claim, run_case, unassign

ORDER = {"order_id": "ord-1", "amount": 250}
REVIEWED_BY_ANA = ("review", "approve", "ana", {"approved_amount": 250})
REVIEWED_BY_SAM = ("review", "approve", "sam", {"approved_amount": 250})

# The guide's people: Ana reviews refunds, Sam reviews and leads the team, Lee leads it; Omar
# operates. The team leads' role assigns (the development catalog).
PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "omar": ["operations"],
}
WITH_PIA = {**PEOPLE, "pia": ["support-lead"]}  # a second team lead, for a reassignment


def test_a_reassignment_by_someone_not_allowed_to_assign_is_refused() -> None:
    # The curriculum's negative test: Ana holds the review, and Omar, whose role doesn't assign,
    # can't move it to Sam (brief, D70).
    with pytest.raises(
        ClaimRefused,
        match="^omar may not assign review#1: assigning is done by support-lead, and omar has "
        "operations$",
    ):
        run_case(
            REFUND,
            file=ORDER,
            answers=[claim("review#1", "ana"), assign("review#1", "sam", by="omar")],
            people=PEOPLE,
        )


def test_an_assigner_reassigns_a_held_entry_without_its_holder() -> None:
    # Ana claims the review and goes on leave; Lee, who leads the team, gives it to Sam. Lee can't
    # answer the review herself: assigning moves work, it doesn't answer it (brief, D70).
    script = [claim("review#1", "ana"), assign("review#1", "sam", by="lee")]
    run = run_case(REFUND, file=ORDER, answers=script, people=PEOPLE)
    assert run.assignees == {"review#1": "sam"}
    assert run.history[-1] == "lee assigned review#1 to sam as support-lead, from ana"
    assert run.waiting_for == ["review by support"]
    # Sam's answer is taken; Ana's, now, is refused.
    with pytest.raises(AnswerRefused, match="^sam holds review#1: ask sam to give it back"):
        run_case(REFUND, file=ORDER, answers=[*script, REVIEWED_BY_ANA], people=PEOPLE)
    answered = run_case(REFUND, file=ORDER, answers=[*script, REVIEWED_BY_SAM], people=PEOPLE)
    assert answered.reached("review")


def test_an_assigner_assigns_an_entry_nobody_holds_and_may_assign_it_to_themselves() -> None:
    # In the queue, the review goes to whomever Lee names. Sam may answer it, so assigning it to
    # himself is taken, as his claim would be (brief, D70).
    run = run_case(REFUND, file=ORDER, answers=[assign("review#1", "ana", by="lee")], people=PEOPLE)
    assert run.assignees == {"review#1": "ana"}
    assert run.history[-1] == "lee assigned review#1 to ana as support-lead"
    himself = run_case(
        REFUND, file=ORDER, answers=[assign("review#1", "sam", by="sam")], people=PEOPLE
    )
    assert himself.assignees == {"review#1": "sam"}
    assert himself.history[-1] == "sam assigned review#1 to sam as support-lead"


@pytest.mark.parametrize(
    ("script", "message"),
    [
        # Lee can't answer the review, so she can't be asked to, even by herself.
        (
            [assign("review#1", "lee", by="lee")],
            (
                "^lee may not assign review#1 to lee: review#1 is answered by support, and lee has "
                "support-lead$"
            ),
        ),
        (
            [assign("review#1", "omar", by="lee")],
            (
                "^lee may not assign review#1 to omar: review#1 is answered by support, and omar has "
                "operations$"
            ),
        ),
        # An assignment to the holder changes nothing.
        (
            [claim("review#1", "ana"), assign("review#1", "ana", by="lee")],
            "^ana already holds review#1$",
        ),
    ],
)
def test_an_assignment_is_refused_to_whoever_couldnt_answer_or_already_holds(
    script: list[Any], message: str
) -> None:
    # Being assigned grants nothing: the assignee is judged as their claim would be (brief, D70).
    with pytest.raises(ClaimRefused, match=message):
        run_case(REFUND, file=ORDER, answers=script, people=PEOPLE)


@pytest.mark.parametrize(
    ("script", "message"),
    [
        (
            [claim("review#1", "ana"), unassign("review#1", by="omar")],
            (
                "^omar may not assign review#1: assigning is done by support-lead, and omar has "
                "operations$"
            ),
        ),
        ([unassign("review#1", by="lee")], "^nobody holds review#1$"),
    ],
)
def test_an_unassign_is_refused_to_whoever_cant_assign_and_of_what_nobody_holds(
    script: list[Any], message: str
) -> None:
    with pytest.raises(ClaimRefused, match=message):
        run_case(REFUND, file=ORDER, answers=script, people=PEOPLE)


def test_an_entry_whose_holder_never_acts_is_returned_to_its_queue() -> None:
    # The tutor's case from 17a: Ana claims the review and never acts. Lee returns it to its
    # queue without her, and Sam answers it (brief, D70).
    script = [claim("review#1", "ana"), unassign("review#1", by="lee")]
    run = run_case(REFUND, file=ORDER, answers=script, people=PEOPLE)
    assert run.assignees == {}
    assert run.history[-1] == "lee returned review#1 to its queue as support-lead, from ana"
    answered = run_case(REFUND, file=ORDER, answers=[*script, REVIEWED_BY_SAM], people=PEOPLE)
    assert answered.reached("review")


# Sam, who leads the team and reviews too, set the amount pay sends.
SAM_REVIEWED = [REVIEWED_BY_SAM]
SAM_EXCLUDED = (
    "^sam may not assign pay.approval#1: sam set approved_amount, which pay uses, so cannot "
    "approve it$"
)


@pytest.mark.parametrize(
    "script",
    [
        [*SAM_REVIEWED, assign("pay.approval#1", "lee", by="sam")],  # assign
        [*SAM_REVIEWED, claim("pay.approval#1", "lee"), assign("pay.approval#1", "pia", by="sam")],
        [*SAM_REVIEWED, claim("pay.approval#1", "lee"), unassign("pay.approval#1", by="sam")],
    ],
)
def test_nobody_moves_the_approval_of_their_own_decision(script: list[Any]) -> None:
    # The guide's example: Sam's role assigns, but he set what pay sends, so he can never approve
    # it, and so may not choose who does, nor take it from whoever holds it (brief, D11) (brief,
    # D70). He may still assign anything else.
    with pytest.raises(ClaimRefused, match=SAM_EXCLUDED):
        run_case(REFUND, file=ORDER, answers=script, people=WITH_PIA)


def test_an_excluded_assigner_still_assigns_what_isnt_their_decision() -> None:
    run = run_case(REFUND, file=ORDER, answers=[assign("review#1", "ana", by="sam")], people=PEOPLE)
    assert run.assignees == {"review#1": "ana"}


def test_the_opener_moves_no_approval_of_the_case() -> None:
    # Whoever opened the case approves none of its steps, so moves none of their approvals
    # (brief, D11) (brief, D25) (brief, D70).
    with pytest.raises(
        ClaimRefused,
        match="^lee may not assign pay.approval#1: lee opened the case, so cannot approve its "
        "steps$",
    ):
        run_case(
            REFUND,
            file=ORDER,
            answers=[REVIEWED_BY_ANA, assign("pay.approval#1", "sam", by="lee")],
            people=PEOPLE,
            opened_by="lee",
        )


def test_an_assigner_needs_only_to_be_someone_else_not_to_approve_it() -> None:
    # The approved amount is shown to support only, so Lee, a team lead without support, can't
    # see it and can't approve pay (brief, D30). She is no party to the decision, so she may
    # still give its approval to Sam, who sees it: only the exclusions apply (brief, D70).
    run = run_case(
        guide_seen_by_support(),
        file=ORDER,
        answers=[REVIEWED_BY_ANA, assign("pay.approval#1", "sam", by="lee")],
        people=PEOPLE,
    )
    assert run.assignees == {"pay.approval#1": "sam"}
