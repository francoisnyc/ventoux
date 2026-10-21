"""Patterns: data that expands into raw rules when the definition is read (layer 11h1).

Tests go through `parse_case`, `validate_case`, `read_rules`, `read_patterns`, `run_case` and the
stories under `examples/`. See docs/layers/11-rules.md (11h), the brief, D46, and
docs/guides/cases.md, "Patterns".
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_timers import CHASE, CHASE_REVIEW, PEOPLE, REFUND, SMALL
from test_untrusted_moment import LETTER, cancelled, say_goodbye

from ventoux.case.definition import CaseInvalid, ReminderRule, SlaRule, parse_case
from ventoux.case.reading import ReadingRefused, read_patterns, read_rules
from ventoux.case.simulate import simulate
from ventoux.case.story import parse_story
from ventoux.case.validate import validate_case
from ventoux.core.validate import Issue
from ventoux.testing import CATALOG, later, run_case

EXAMPLES = Path(__file__).parent.parent / "examples"

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


# --- Slice 4: readings and simulations ---


def test_a_pattern_reads_as_its_sentence_and_its_rules() -> None:
    sla = copy.deepcopy(CHASE_SLA) | {"when": {">": [{"var": "amount"}, 100]}}
    case = parse_case(reminded(chase_sla=sla, remind_review=REMIND_REVIEW))
    assert [str(reading) for reading in read_patterns(case)] == [
        (
            "chase_sla: Chase a review not done within two days\n"
            "  An sla on review: if a run of review isn't finished within 2d of its latest start, "
            "and if amount > 100 (read when the timer fires), start chase.\n"
            "  It expands to the rule chase_sla."
        ),
        (
            "remind_review: Remind the reviewer of an open review\n"
            "  A reminder of review: while a run of review is open, start remind 1d and 2d after it "
            "starts.\n"
            "  It expands to the rules remind_review_1d and remind_review_2d."
        ),
    ]
    # Its rules read as any other: the fine print stays on them.
    readings = {reading.name: reading for reading in read_rules(case)}
    assert (
        readings["remind_review_2d"].sentence == "2d after each run of review starts: start remind."
    )
    assert readings["chase_sla"].sentence == (
        "2d after each run of review starts, if amount > 100 (read when the timer fires, not when "
        "it is set): start chase."
    )


def test_a_pattern_the_reader_doesnt_know_is_refused() -> None:
    # `parse_case` refuses an entry that is no pattern first; this one didn't come through it.
    case = parse_case(with_rules(chase_sla=CHASE_SLA))
    object.__setattr__(case, "written", {"chase_sla": {"deadline": "2d"}})
    with pytest.raises(ReadingRefused) as refused:
        read_patterns(case)
    assert str(refused.value) == (
        "can't read chase_sla: {'deadline': '2d'} is neither a raw rule nor a pattern Ventoux knows"
    )


def simulated(path: Path) -> str:
    """What `ventoux simulate` prints for the story at `path`."""
    raw = json.loads(path.read_text())
    definition = json.loads((path.parent / raw["definition"]).read_text())
    return str(simulate(parse_story(raw), parse_case(definition), CATALOG))


def test_a_firing_of_an_expanded_rule_shows_its_pattern() -> None:
    printed = simulated(EXAMPLES / "refund" / "stories" / "review-reminded.json")
    # At the top, the pattern's reading, then each of its rules' readings, under it.
    assert (
        "  remind_review: Remind the reviewer of an open review\n"
        "    A reminder of review: while a run of review is open, start remind 1d, 2d and 4d "
        "after it starts.\n"
        "    It expands to the rules remind_review_1d, remind_review_2d and remind_review_4d.\n"
        "\n"
        "    remind_review_1d: Remind the reviewer of an open review\n"
        "      1d after each run of review starts: start remind.\n"
    ) in printed
    # Beside a firing, the pattern's sentence, then the rule's whole reading.
    assert (
        "  remind_review_2d#1 on 2d after started review#1: starting remind\n"
        "    ↳ from the reminder remind_review: A reminder of review: while a run of review is "
        "open, start remind 1d, 2d and 4d after it starts.\n"
        "    ↳ remind_review_2d: Remind the reviewer of an open review\n"
        "      2d after each run of review starts: start remind.\n"
    ) in printed
    # A raw rule's firing shows as before: its reading alone.
    raw = simulated(EXAMPLES / "refund" / "stories" / "nobody-reviews.json")
    assert "↳ from the" not in raw


# --- Slice 5: every check that reads rules, on expanded rules ---


def issues(definition: dict[str, Any]) -> list[Issue]:
    return validate_case(parse_case(definition), CATALOG)


def test_an_sla_on_a_step_that_can_never_run_never_fires() -> None:
    definition = with_rules(chase_sla=CHASE_SLA | {"sla": {"step": "audit", "within": "2d"}})
    definition["steps"]["audit"] = {
        "kind": "task",
        "display": {"title": "Audit the refund"},
        "roles": ["support"],
        "requires": ["audited"],
        "outcomes": {"done": {"display": {"title": "Audited"}}},
    }
    definition["milestones"] = {"audited": {"display": {"title": "Audited"}}}
    assert [i for i in issues(definition) if i.code == "NEVER_FIRES"] == [
        Issue(
            "rules.chase_sla.sla",
            "NEVER_FIRES",
            "chase_sla can never fire: it fires on 2d after started audit, which can never run: "
            "fix audit first",
        )
    ]
    run = run_case(definition, file=SMALL, answers=[later("5d")], people=PEOPLE)
    assert not [line for line in run.history if "chase_sla" in line]


def test_a_reminder_that_starts_its_own_task_never_starts_it() -> None:
    # A reminder comes while its task's run is open, since its timer ends with the run: starting
    # that task again is refused every time.
    own = {"task": "review", "after": ["1d"], "start": "review"}
    definition = reminded(remind_review=REMIND_REVIEW | {"reminder": own})
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    del definition["steps"]["remind"]
    assert issues(definition) == [
        Issue(
            "rules.remind_review.reminder.start",
            "NEVER_STARTS",
            "remind_review_1d, from the reminder remind_review: remind_review_1d can never start "
            "review: it fires on 1d after started review, while review is running: start it on "
            "another moment",
        )
    ]
    run = run_case(definition, file=SMALL, answers=[later("2d")], people=PEOPLE)
    assert [line for line in run.history if line.startswith("remind_review_1d#1")] == [
        (
            "remind_review_1d#1 on 1d after started review#1: review not started: review is "
            "already running: review#1"
        )
    ]


def goodbye_sla() -> dict[str, Any]:
    """The customer's note starts the goodbye call (untrusted data steers it); an sla on that
    call reaches `withdrawn`, which closes the case."""
    definition = say_goodbye()
    del definition["rules"]["close_it"]
    definition["rules"]["goodbye_sla"] = {
        "display": {"title": "Withdraw a goodbye call left a day"},
        "sla": {"step": "goodbye", "within": "1d"},
        "then": {"reach": ["withdrawn"]},
    }
    return definition


def test_an_sla_on_a_run_untrusted_data_steers_decides_nothing() -> None:
    assert [i for i in issues(goodbye_sla()) if i.code == "UNTRUSTED_TRIGGER"] == [
        Issue(
            "rules.goodbye_sla.sla",
            "UNTRUSTED_TRIGGER",
            "goodbye_sla fires on 1d after started goodbye, which untrusted data steers however "
            "goodbye starts (untrusted:customer), and untrusted data can't decide, so it never "
            "reaches withdrawn: start goodbye only on trusted data, or let a person decide in a "
            "task",
        )
    ]
    run = run_case(goodbye_sla(), file=SMALL, answers=[cancelled(), later("2d")], people=PEOPLE)
    assert not run.reached("withdrawn")
    assert any(
        line.startswith("goodbye_sla#1 on 1d after started goodbye#1: reaches nothing")
        for line in run.history
    )


def test_a_reminder_on_a_run_untrusted_data_steers_cant_send_what_its_policy_refuses() -> None:
    definition = say_goodbye(steps={"letter": LETTER | {"repeatable": True}})
    del definition["rules"]["close_it"]
    definition["rules"]["remind_goodbye"] = {
        "display": {"title": "Draft a reminder of the goodbye call"},
        "reminder": {"task": "goodbye", "after": ["1d"], "start": "letter"},
    }
    assert [i for i in issues(definition) if i.code == "INPUT_POLICY"] == [
        Issue(
            "rules.remind_goodbye.reminder.start",
            "INPUT_POLICY",
            "remind_goodbye_1d, from the reminder remind_goodbye: letter fails on its inputs "
            "every time remind_goodbye_1d starts it: letters.draft@2 takes to_customer only from "
            "a system or a person, never from untrusted data, and remind_goodbye_1d fires on 1d "
            "after started goodbye, which untrusted data steers (untrusted:customer): start "
            "goodbye only on trusted data, or let a person decide in a task",
        )
    ]
    run = run_case(definition, file=SMALL, answers=[cancelled(), later("2d")], people=PEOPLE)
    assert [line for line in run.needs_attention if line.startswith("letter#1")] == [
        (
            "letter#1: letters.draft@2 takes to_customer only from a system or a person, never from "
            "untrusted data, and say_goodbye#1's condition, which started goodbye, reads "
            "cancelled.note (untrusted:customer)"
        )
    ]


def test_a_patterns_condition_reading_what_may_be_unset_warns() -> None:
    above = {"when": {">": [{"var": "approved_amount"}, 100]}}
    assert issues(with_rules(chase_sla=CHASE_SLA | above)) == [
        Issue(
            "rules.chase_sla.when",
            "MAY_BE_UNSET",
            "chase_sla reads approved_amount, which may not be set when 2d after started review "
            "comes: then chase_sla fails and needs attention: read it only when it is set, or "
            "fire it on another moment",
            "warning",
        )
    ]
    run = run_case(
        with_rules(chase_sla=CHASE_SLA | above), file=SMALL, answers=[later("3d")], people=PEOPLE
    )
    assert any(line.startswith("chase_sla#1") for line in run.needs_attention)
    # A reminder's rules each say so, naming the reminder.
    assert [i.message for i in issues(reminded(remind_review=REMIND_REVIEW | above))] == [
        f"remind_review_{age}, from the reminder remind_review: remind_review_{age} reads "
        f"approved_amount, which may not be set when {age} after started review comes: then "
        f"remind_review_{age} fails and needs attention: read it only when it is set, or fire "
        "it on another moment"
        for age in ("1d", "2d")
    ]


def test_an_sla_keeps_no_case_open_at_its_opening() -> None:
    # An sla's timer is set only as a run starts: a case whose steps all wait to be proposed
    # still closes as it opens.
    definition = with_rules(chase_sla=CHASE_SLA)
    definition["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    assert [i.code for i in issues(definition)] == ["CLOSES_AT_OPENING"]
    run = run_case(definition, file=SMALL, answers=[], people=PEOPLE)
    assert run.closed


def test_a_reminder_makes_no_loop() -> None:
    # A rule's start never waits, so a reminder can't come round by itself (brief, D39): the
    # check says nothing of the reminded refund, and its story ends.
    assert issues(reminded()) == []
