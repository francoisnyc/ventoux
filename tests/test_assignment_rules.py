"""Layer 17c: assignment rules. The definition names who is asked when each entry opens: the
opener, or whoever gave a task's latest answer, judged as their claim would be (brief, D71).

See docs/layers/17-assignment.md (17c) and docs/guides/cases.md, "Assignment rules".
"""

import copy
import json
from typing import Any

import pytest
from test_approvals import FOUR_EYES
from test_case import PEOPLE, REFUND, guide_json, guide_refund_with_rework

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.diff import diff
from ventoux.case.plain import plain
from ventoux.case.releases import package
from ventoux.case.sheet import case_map
from ventoux.case.validate import validate_case
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.converter import ExactPayloadConverter
from ventoux.testing import CATALOG, claim, give_back, propose, run_case


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


@pytest.mark.parametrize(
    ("definition", "opened_by", "line"),
    [
        # The review asks whoever answered it, but nobody has yet.
        (
            with_review_assigned({"to": "answered", "step": "review"}),
            None,
            "review#1 in its queue: its rule found nobody: review hasn't been answered",
        ),
        # A system opened the case: there is no opener to ask.
        (
            with_review_assigned({"to": "opener"}),
            None,
            "review#1 in its queue: its rule found nobody: a system opened the case",
        ),
        # Lee opened it, but she can't answer the review: she isn't support.
        (
            with_review_assigned({"to": "opener"}),
            "lee",
            "review#1 in its queue: review#1 is answered by support, and lee has support-lead",
        ),
    ],
)
def test_a_rule_that_finds_nobody_who_can_answer_leaves_the_entry_in_its_queue(
    definition: dict[str, Any], opened_by: str | None, line: str
) -> None:
    # A rule never stops a case: whom it can't ask, the queue gets, saying why (brief, D71).
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 40},
        answers=[],
        people=PEOPLE,
        opened_by=opened_by,
    )
    assert run.assignees == {}
    assert line in run.history
    assert run.waiting_for == ["review by support"]


def test_a_rule_asks_the_opener_judged_with_the_roles_stated_with_the_opening() -> None:
    run = run_case(
        with_review_assigned({"to": "opener"}),
        file={"order_id": "ord-1", "amount": 40},
        answers=[],
        people=PEOPLE,
        opened_by="ana",
    )
    assert run.assignees == {"review#1": "ana"}
    assert "review#1 assigned to ana by its rule" in run.history


def test_answered_asks_whoever_gave_the_latest_answer() -> None:
    # 250 needs a team lead's approval, so the case waits, and the review is sent back each time, and each new review is asked of whoever did the last:
    # first Ana, then, once Sam has reviewed, Sam. The latest answer is the one that counts, as
    # its outcome does (brief, D9) (brief, D71).
    definition = guide_refund_with_rework()
    definition["steps"]["review"]["assign"] = {"to": "answered", "step": "review"}
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 250},
        answers=[
            ("review", "approve", "ana", {"approved_amount": 250}),
            propose("review", "ana"),
            give_back("review#2", "ana"),
            ("review", "approve", "sam", {"approved_amount": 250}),
            propose("review", "ana"),
        ],
        people=PEOPLE,
    )
    assert "review#2 assigned to ana by its rule" in run.history
    assert run.assignees == {"review#3": "sam"}
    assert "review#3 assigned to sam by its rule" in run.history


def with_triage() -> dict[str, Any]:
    """The reworkable refund, a team lead taking each refund for approval first: `pay`'s
    approval is asked of whoever took it, whose answer reaches nothing `pay` reads."""
    definition = guide_refund_with_rework()
    definition["steps"]["triage"] = {
        "kind": "task",
        "display": {"title": "Take the refund for approval"},
        "roles": ["support-lead"],
        "requires": ["review"],
        "outcomes": {"taken": {"display": {"title": "Taken"}}},
    }
    definition["steps"]["pay"]["requires"] = ["triage"]
    definition["steps"]["pay"]["approval"]["assign"] = {"to": "answered", "step": "triage"}
    return definition


REVIEWED = ("review", "approve", "ana", {"approved_amount": 250})
TRIAGED = ("triage", "taken", "lee")
REWORKED = [propose("review", "ana"), ("review", "approve", "ana", {"approved_amount": 300})]


def test_an_approvals_rule_asks_whom_it_picks() -> None:
    run = run_case(
        with_triage(),
        file={"order_id": "ord-1", "amount": 250},
        answers=[REVIEWED, TRIAGED],
        people=PEOPLE,
    )
    assert run.assignees == {"pay.approval#1": "lee"}
    assert run.history[-1] == "pay.approval#1 assigned to lee by its rule"


def test_a_kept_holder_outranks_the_rule_and_the_rule_picks_when_nobody_is_kept() -> None:
    # Lee gives the approval back and Sam claims it; the review is reworked, so it is asked again.
    # Sam, a person's choice, is kept, not the rule's Lee (brief, D69) (brief, D71).
    kept = run_case(
        with_triage(),
        file={"order_id": "ord-1", "amount": 250},
        answers=[
            REVIEWED,
            TRIAGED,
            give_back("pay.approval#1", "lee"),
            claim("pay.approval#1", "sam"),
            *REWORKED,
        ],
        people=PEOPLE,
    )
    assert kept.assignees == {"pay.approval#2": "sam"}
    # With nobody holding it when it is withdrawn, the new entry is the rule's again.
    picked = run_case(
        with_triage(),
        file={"order_id": "ord-1", "amount": 250},
        answers=[REVIEWED, TRIAGED, give_back("pay.approval#1", "lee"), *REWORKED],
        people=PEOPLE,
    )
    assert picked.assignees == {"pay.approval#2": "lee"}
    assert "pay.approval#2 assigned to lee by its rule" in picked.history


def test_a_pick_the_approval_may_exclude_is_a_warning() -> None:
    # Without its `when`, pay reads review's answer only through approved_amount, which an edit
    # or a rule may give instead: whoever answered the review may be excluded, not in every case,
    # so it is said, never refused (brief, D37) (brief, D71).
    definition = with_pay_assigned({"to": "answered", "step": "review"})
    del definition["steps"]["pay"]["when"]
    issues = validate_case(parse_case(definition), CATALOG)
    found = [i for i in issues if i.path == "steps.pay.approval.assign"]
    assert [(i.code, i.severity, i.message) for i in found] == [
        (
            "ASSIGNS_MAY_BE_EXCLUDED",
            "warning",
            (
                "whoever answered review may be excluded from approving pay: their answer can "
                "reach what pay reads; then the approval goes to its queue"
            ),
        )
    ]


def test_a_task_the_step_doesnt_require_may_find_nobody() -> None:
    # The review asks whoever answered it, which no run of it can have done before the first:
    # said, never refused. A task the step requires has been answered by then: no warning.
    issues = validate_case(
        parse_case(with_review_assigned({"to": "answered", "step": "review"})), CATALOG
    )
    found = [i for i in issues if i.path == "steps.review.assign"]
    assert [(i.code, i.severity, i.message) for i in found] == [
        (
            "MAY_ASSIGN_NOBODY",
            "warning",
            (
                "review doesn't require review, so it may not have been answered when review "
                "opens; then review goes to its queue"
            ),
        )
    ]
    required = validate_case(parse_case(with_triage()), CATALOG)
    assert not [i for i in required if i.code == "MAY_ASSIGN_NOBODY"]


def test_whom_a_rule_may_ask_crosses_as_data_and_a_state_from_before_has_none() -> None:
    # Ana opened the case and answered the review: both cross continue-as-new, with their roles
    # (brief, D27) (brief, D71). A state carried from before 17c has neither, so a rule then
    # finds nobody, and the entry is in its queue (fail closed).
    run = run_case(
        guide_follow_up(),
        file={"order_id": "ord-1", "amount": 250},
        answers=[("review", "approve", "ana", {"approved_amount": 250})],
        people=PEOPLE,
        opened_by="ana",
    )
    converter = ExactPayloadConverter()
    payload = converter.to_payload(state_as_data(run.state))
    assert payload is not None
    back = state_from_data(converter.from_payload(payload, dict), {})
    assert back == run.state
    before = state_as_data(run.state)
    del before["answerers"], before["opener"]
    older = state_from_data(before, {})
    assert older.answerers == {} and older.opener is None


def changes_to(rule_before: dict[str, Any] | None, rule_after: dict[str, Any] | None) -> list[Any]:
    """The diff's changes to the review's rule, from `rule_before` to `rule_after` (None: none)."""
    versions = []
    for rule in (rule_before, rule_after):
        definition = copy.deepcopy(REFUND)
        if rule is not None:
            definition["steps"]["review"]["assign"] = rule
        versions.append(package(json.dumps(definition, default=str), []))
    found = diff(versions[0], versions[1], CATALOG)
    return [c for c in found.changes if c.path.startswith("steps.review.assign")]


OPENER, ANSWERED = {"to": "opener"}, {"to": "answered", "step": "review"}


@pytest.mark.parametrize(
    ("before", "after", "verdict", "said"),
    [
        # Only the holder answers a held entry (brief, D69): a rule narrows who may.
        (None, OPENER, "stricter", "added: asked of whoever opened the case"),
        (OPENER, None, "looser", "removed: asked of whoever opened the case"),
        # Another person asked: a doubt, so read as looser (brief, D55).
        (
            OPENER,
            ANSWERED,
            "not proven",
            "asked of whoever opened the case -> asked of whoever answered review",
        ),
    ],
)
def test_the_diff_judges_a_rule(
    before: dict[str, Any] | None, after: dict[str, Any] | None, verdict: str, said: str
) -> None:
    [change] = changes_to(before, after)
    assert (change.path, change.verdict, change.said) == ("steps.review.assign", verdict, said)
    assert change.comparison == ("assignment" if verdict != "not proven" else None)


def test_the_diff_judges_an_approvals_rule() -> None:
    before, after = REFUND, with_triage_rule_only()
    found = diff(
        package(json.dumps(before, default=str), []),
        package(json.dumps(after, default=str), []),
        CATALOG,
    )
    [change] = [c for c in found.changes if c.path == "steps.pay.approval.assign"]
    assert (change.verdict, change.said, change.comparison) == (
        "stricter",
        "added: asked of whoever answered review",
        "assignment",
    )


def with_triage_rule_only() -> dict[str, Any]:
    """The refund with only a rule added to `pay`'s approval: one change for the diff to judge."""
    return with_pay_assigned({"to": "answered", "step": "review"})


def test_the_plain_forms_read_a_rule_aloud() -> None:
    # The case map says who each run is asked of, for a task and for an approval; the plain diff
    # reads the step before and after, so the same sentence says what changed (brief, D56)
    # (brief, D71).
    before = package(json.dumps(REFUND, default=str), [])
    after_case = with_review_assigned({"to": "opener"})
    after_case["steps"]["pay"]["approval"]["assign"] = {"to": "answered", "step": "review"}
    after = package(json.dumps(after_case, default=str), [])
    mapped = case_map(after, CATALOG)
    assert "Each run is asked of whoever opened the case." in mapped
    assert "Each approval is asked of whoever answered review." in mapped
    assert "Each run is asked of" not in case_map(before, CATALOG)
    shown = plain(diff(before, after, CATALOG), before, after, CATALOG)
    assert "Each run is asked of whoever opened the case." in shown
