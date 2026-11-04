"""Layer 17c: assignment rules. The definition names who is asked when each entry opens: the
opener, or whoever gave a task's latest answer, judged as their claim would be (brief, D71).

See docs/layers/17-assignment.md (17c) and docs/guides/cases.md, "Assignment rules".
"""

import copy
from typing import Any

import pytest
from test_approvals import FOUR_EYES
from test_case import PEOPLE, REFUND, guide_json

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, run_case


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
            (
                "^steps.review.assign.step: pay is an activity step; only a task is answered by "
                "a person$"
            ),
        ),
        ({"to": "answered", "step": "review", "who": "lee"}, "^steps.review.assign.who: "),
    ],
)
def test_a_malformed_rule_is_refused_when_read(rule: dict[str, Any], message: str) -> None:
    # Fail closed: a rule the engine can't read as one of its two picks is no rule (brief, D71).
    with pytest.raises(CaseInvalid, match=message):
        parse_case(with_review_assigned(rule))


def test_an_approval_needing_several_people_has_no_rule() -> None:
    # One entry collects several people's approvals, so nobody holds it (brief, D47) (brief, D69):
    # a rule naming one person can never be followed. That is the cause, said once: the pick
    # isn't judged as well (one cause, one issue).
    definition = copy.deepcopy(FOUR_EYES)
    definition["steps"]["pay"]["approval"]["assign"] = {"to": "answered", "step": "review"}
    issues = validate_case(parse_case(definition), CATALOG)
    found = [i for i in issues if i.path == "steps.pay.approval.assign"]
    assert [(i.code, i.severity, i.message) for i in found] == [
        (
            "ASSIGNS_SEVERAL",
            "error",
            (
                "pay's approval needs 2 people, so nobody holds it and a rule can't ask one; "
                "remove the rule, or its count"
            ),
        )
    ]


def guide_follow_up() -> dict[str, Any]:
    """The quickstart's refund with the guide's follow-up: its last JSON block, "Assignment
    rules", so the guide can't drift from what runs."""
    definition = copy.deepcopy(REFUND)
    definition["steps"].update(guide_json(-1))
    return definition


def test_the_guides_follow_up_is_asked_of_whoever_answered_the_review() -> None:
    # Ana answers the review; the follow-up opens and its rule asks her, judged as her claim
    # would be, with the roles she answered with (brief, D69) (brief, D71).
    run = run_case(
        guide_follow_up(),
        file={"order_id": "ord-1", "amount": 40},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
    )
    assert run.assignees == {"follow_up#1": "ana"}
    at = run.history.index("started follow_up#1: waiting for done by support")
    assert run.history[at + 1] == "follow_up#1 assigned to ana by its rule"
