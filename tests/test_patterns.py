"""Patterns: data that expands into raw rules when the definition is read (layer 11h1).

Tests go through `parse_case`, `validate_case`, `read_rules`, `read_patterns`, `run_case` and the
stories under `examples/`. See docs/layers/11-rules.md (11h), the brief, D46, and
docs/guides/cases.md, "Patterns".
"""

import copy
from typing import Any

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_timers import CHASE, CHASE_REVIEW, REFUND

from ventoux.case.definition import CaseInvalid, ReminderRule, SlaRule, parse_case

# An sla on the refund's review: a team lead chases a review not done within two days of its
# start. It expands into the guide's timer, `chase_review` ("Rules on time").
CHASE_SLA = {
    "display": {"title": "Chase a review not done within two days"},
    "sla": {"step": "review", "within": "2d"},
    "then": {"start": ["chase"]},
}


def with_rules(**rules: Any) -> dict[str, Any]:
    """The quickstart's refund with the guide's `chase` task, and `rules` as written."""
    definition = copy.deepcopy(REFUND)
    definition["steps"]["chase"] = copy.deepcopy(CHASE)
    definition["rules"] = copy.deepcopy(rules)
    return definition


# --- Slice 1: a rule entry that is a pattern ---


def test_a_rule_entry_neither_raw_nor_a_pattern_is_refused() -> None:
    # Fail closed: an entry is a raw rule or a pattern Ventoux knows, never guessed as one.
    deadline = {"display": {"title": "A deadline"}, "deadline": {"step": "review"}}
    with pytest.raises(CaseInvalid) as refused:
        parse_case(with_rules(chase_review=deadline))
    assert str(refused.value) == (
        "rules.chase_review: a rule is a raw rule, with on, when and then, or a pattern: "
        "sla or reminder"
    )


def test_a_patterns_own_field_misspelt_is_refused() -> None:
    misspelt = copy.deepcopy(CHASE_SLA)
    misspelt["sla"] = {"step": "review", "whithin": "2d"}
    with pytest.raises(CaseInvalid) as refused:
        parse_case(with_rules(chase_sla=misspelt))
    assert str(refused.value).splitlines() == [
        "rules.chase_sla.sla.within: required",
        "rules.chase_sla.sla.whithin: not a field here",
    ]


def test_a_pattern_expands_when_the_definition_is_read() -> None:
    case = parse_case(with_rules(chase_sla=CHASE_SLA))
    # Every reader of rules, the runtime and validation included, sees the expansion.
    assert list(case.rules) == ["chase_sla"]
    rule = case.rules["chase_sla"]
    # The same rule as the guide's timer, written raw under the sla's name and title.
    raw = copy.deepcopy(CHASE_REVIEW) | {"display": CHASE_SLA["display"]}
    assert rule == parse_case(with_rules(chase_sla=raw)).rules["chase_sla"]
    # The definition keeps the pattern as written, beside its expansion.
    assert isinstance(case.written["chase_sla"], SlaRule)
    assert case.written["chase_sla"].sla.within == "2d"


def test_a_patterns_rules_stand_where_it_is_written() -> None:
    # Rules on one moment act in the definition's order (brief, D38), so a pattern's rules stand
    # where it is written, never after every raw rule.
    late = copy.deepcopy(CHASE_REVIEW) | {"on": {"after": "3d", "since": {"started": "review"}}}
    case = parse_case(with_rules(chase_review=CHASE_REVIEW, chase_sla=CHASE_SLA, chase_late=late))
    assert list(case.rules) == ["chase_review", "chase_sla", "chase_late"]
    assert not isinstance(case.written["chase_review"], SlaRule | ReminderRule)


# --- Slice 2: sla ---


@pytest.mark.parametrize(
    ("sla", "message"),
    [
        (
            {"step": "assess", "within": "2d"},
            "rules.chase_sla.sla.step: assess is not a step",
        ),
        (
            {"step": "review", "within": "0m"},
            "rules.chase_sla.sla.within: a timer waits at least 1m: write a later age",
        ),
        (
            {"step": "review", "within": "2 days"},
            'rules.chase_sla.sla.within: an age looks like "30m", "12h" or "1d"',
        ),
    ],
)
def test_an_sla_that_cant_mean_anything_is_refused(sla: dict[str, str], message: str) -> None:
    written = copy.deepcopy(CHASE_SLA) | {"sla": sla}
    with pytest.raises(CaseInvalid) as refused:
        parse_case(with_rules(chase_sla=written))
    assert str(refused.value) == message


def test_an_sla_expands_into_a_timer_on_each_run() -> None:
    # Its `when` and `then` are the rule's as written; no `when` saying "if it isn't done": the
    # timer ends with its run (brief, D44).
    written = copy.deepcopy(CHASE_SLA) | {"when": {">": [{"var": "amount"}, 100]}}
    raw = copy.deepcopy(CHASE_REVIEW) | {
        "display": CHASE_SLA["display"],
        "when": {">": [{"var": "amount"}, 100]},
    }
    expanded = parse_case(with_rules(chase_sla=written)).rules
    assert expanded == parse_case(with_rules(chase_sla=raw)).rules
    assert parse_case(with_rules(chase_sla=written)).pattern_of("chase_sla") == "chase_sla"
    assert parse_case(with_rules(chase_review=CHASE_REVIEW)).pattern_of("chase_review") is None


# --- Slice 3: reminder ---

# A team lead reminds the reviewer, by hand, a day and two days after a review starts.
REMIND = {
    "kind": "task",
    "display": {"title": "Remind the reviewer"},
    "roles": ["support-lead"],
    "automatic": False,
    "repeatable": True,
    "outcomes": {"reminded": {"display": {"title": "Reviewer reminded"}}},
}
REMIND_REVIEW: dict[str, Any] = {
    "display": {"title": "Remind the reviewer of an open review"},
    "reminder": {"task": "review", "after": ["1d", "2d"], "start": "remind"},
}


def reminded(**rules: Any) -> dict[str, Any]:
    """The refund with the `remind` task, and `rules` as written (by default, the reminder). The
    guide's `chase` stays only if a rule starts it."""
    definition = with_rules(**(rules or {"remind_review": REMIND_REVIEW}))
    definition["steps"]["remind"] = copy.deepcopy(REMIND)
    if "chase" not in str(definition["rules"]):
        del definition["steps"]["chase"]
    return definition


def test_a_reminder_expands_into_one_rule_per_age() -> None:
    case = parse_case(reminded())
    assert list(case.rules) == ["remind_review_1d", "remind_review_2d"]
    for age in ("1d", "2d"):
        raw = {
            "display": REMIND_REVIEW["display"],
            "on": {"after": age, "since": {"started": "review"}},
            "then": {"start": ["remind"]},
        }
        rule = f"remind_review_{age}"
        assert case.rules[rule] == parse_case(reminded(**{rule: raw})).rules[rule]
        assert case.pattern_of(rule) == "remind_review"


@pytest.mark.parametrize(
    ("reminder", "message"),
    [
        (
            {"task": "pay", "after": ["1d"], "start": "remind"},
            "rules.remind_review.reminder.task: pay is not a task",
        ),
        (
            {"task": "review", "after": ["1d"], "start": "nudge"},
            "rules.remind_review.reminder.start: nudge is not a step",
        ),
        (
            {"task": "review", "after": ["1d"], "start": "chase"},
            (
                "rules.remind_review.reminder.start: chase isn't repeatable, so only its first "
                "reminder would ever run: make chase repeatable"
            ),
        ),
        (
            {"task": "review", "after": ["1d", "24h"], "start": "remind"},
            (
                "rules.remind_review.reminder.after: 1d and 24h are the same time: give each "
                "reminder its own"
            ),
        ),
        (
            {"task": "review", "after": [], "start": "remind"},
            (
                "rules.remind_review.reminder.after: a reminder comes after at least one age: "
                'list them, such as ["2d"]'
            ),
        ),
    ],
)
def test_a_reminder_that_cant_mean_anything_is_refused(
    reminder: dict[str, Any], message: str
) -> None:
    written = copy.deepcopy(REMIND_REVIEW) | {"reminder": reminder}
    definition = reminded(remind_review=written)
    if reminder["start"] != "remind":
        del definition["steps"]["remind"]  # only the step the reminder names
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == message


def test_a_reminder_does_nothing_but_start_its_step() -> None:
    # A reminder informs; it never reaches, stops or sets (brief, D46).
    written = copy.deepcopy(REMIND_REVIEW) | {"then": {"reach": ["paid"]}}
    with pytest.raises(CaseInvalid) as refused:
        parse_case(reminded(remind_review=written))
    assert str(refused.value) == "rules.remind_review.then: not a field here"


def test_an_expanded_name_that_clashes_is_refused() -> None:
    clash = copy.deepcopy(CHASE_REVIEW)
    with pytest.raises(CaseInvalid) as refused:
        parse_case(reminded(remind_review=REMIND_REVIEW, remind_review_2d=clash))
    assert str(refused.value) == (
        "rules.remind_review: it gives the rule remind_review_2d, which is already a rule: "
        "rename one of them"
    )


def test_expanded_names_are_stable() -> None:
    # A name depends only on the pattern's name and its own parts: a rule written before it, or
    # the ages in another order, rename nothing (brief, D46).
    before = {"chase_review": CHASE_REVIEW, "remind_review": REMIND_REVIEW}
    swapped = copy.deepcopy(REMIND_REVIEW)
    swapped["reminder"]["after"] = ["2d", "1d"]
    assert set(parse_case(reminded(**before)).rules) == {
        "chase_review",
        "remind_review_1d",
        "remind_review_2d",
    }
    assert set(parse_case(reminded(remind_review=swapped)).rules) == {
        "remind_review_1d",
        "remind_review_2d",
    }
