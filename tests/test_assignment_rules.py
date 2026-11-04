"""Layer 17c: assignment rules. The definition names who is asked when each entry opens: the
opener, or whoever gave a task's latest answer, judged as their claim would be (brief, D71).

See docs/layers/17-assignment.md (17c) and docs/guides/cases.md, "Assignment rules".
"""

import copy
from typing import Any

import pytest
from test_case import REFUND

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG


def with_pay_assigned(rule: dict[str, Any]) -> dict[str, Any]:
    """The quickstart's refund, `pay`'s approval asked of whom `rule` picks."""
    definition = copy.deepcopy(REFUND)
    definition["steps"]["pay"]["approval"]["assign"] = rule
    return definition


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        (
            {"to": "answered", "step": "review"},
            (
                "whoever answered review is excluded from approving pay in every run, since pay "
                "reads review.outcome; leave the approval to its queue, or ask whoever answered "
                "another task"
            ),
        ),
        (
            {"to": "opener"},
            (
                "whoever opened the case approves none of its steps; leave the approval to its "
                "queue, or ask whoever answered a task"
            ),
        ),
    ],
)
def test_an_approval_asked_of_someone_it_always_excludes_is_refused(
    rule: dict[str, Any], message: str
) -> None:
    # The curriculum's negative test: a rule that can only pick people who can never answer is
    # refused at validation, where it is proven for every case (brief, D37) (brief, D71).
    issues = validate_case(parse_case(with_pay_assigned(rule)), CATALOG)
    found = [issue for issue in issues if issue.code == "ASSIGNS_EXCLUDED"]
    assert [(i.path, i.severity, i.message) for i in found] == [
        ("steps.pay.approval.assign", "error", message)
    ]


def with_review_assigned(rule: dict[str, Any]) -> dict[str, Any]:
    """The quickstart's refund, its review asked of whom `rule` picks."""
    definition = copy.deepcopy(REFUND)
    definition["steps"]["review"]["assign"] = rule
    return definition


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ({"to": "lee"}, "^steps.review.assign.to: "),
        ({"to": "answered"}, '^steps.review.assign: "answered" names the task whose answerer is'),
        ({"to": "opener", "step": "review"}, '^steps.review.assign: "opener" is the person who'),
        (
            {"to": "answered", "step": "reveiw"},
            "^steps.review.assign.step: reveiw is not a step$",
        ),
        (
            {"to": "answered", "step": "pay"},
            "^steps.review.assign.step: pay is an activity step; only a task is answered by a "
            "person$",
        ),
        ({"to": "answered", "step": "review", "who": "lee"}, "^steps.review.assign.who: "),
    ],
)
def test_a_malformed_rule_is_refused_when_read(rule: dict[str, Any], message: str) -> None:
    # Fail closed: a rule the engine can't read as one of its two picks is no rule (brief, D71).
    with pytest.raises(CaseInvalid, match=message):
        parse_case(with_review_assigned(rule))
