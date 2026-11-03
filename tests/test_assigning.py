"""Layer 17b: assigning a task. An assigner moves work between people, or back to its queue,
without its holder; they never answer it, and never move the approval of a step they may not
approve (brief, D70).

See docs/layers/17-assignment.md (17b) and docs/guides/cases.md, "Assigning, reassigning,
returning to the queue".
"""

import pytest
from test_case import REFUND

from ventoux.testing import AnswerRefused, ClaimRefused, assign, claim, run_case

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
