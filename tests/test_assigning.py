"""Layer 17b: assigning a task. An assigner moves work between people, or back to its queue,
without its holder; they never answer it, and never move the approval of a step they may not
approve (brief, D70).

See docs/layers/17-assignment.md (17b) and docs/guides/cases.md, "Assigning, reassigning,
returning to the queue".
"""

import pytest
from test_case import REFUND

from ventoux.testing import ClaimRefused, assign, claim, run_case

ORDER = {"order_id": "ord-1", "amount": 250}

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
