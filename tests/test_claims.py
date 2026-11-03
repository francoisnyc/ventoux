"""Layer 17a: claiming a task. A task's roles say who may answer it; its holder, who is asked to.
Holding grants nothing, and only the holder answers a held entry (brief, D69).

See docs/layers/17-assignment.md (17a) and docs/guides/cases.md, "Who is asked: claiming and
assigning tasks".
"""

import pytest
from test_case import REFUND

from ventoux.testing import ClaimRefused, claim, run_case

ORDER = {"order_id": "ord-1", "amount": 250}

# Ana and Lee review refunds, Sam leads the team and reviews too; Omar operates.
PEOPLE = {
    "ana": ["support"],
    "lee": ["support"],
    "sam": ["support", "support-lead"],
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
