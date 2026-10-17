"""Rules: on a moment, when a condition holds, then act on the case (layer 11a).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md and docs/guides/cases.md, "Rules".
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import load_definition, propose, run_case

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"]}


def with_rule(**rule: Any) -> dict[str, Any]:
    """The quickstart's refund with a `large` milestone and one rule, `flag_large`, changed by
    `rule`."""
    definition = copy.deepcopy(REFUND)
    definition["milestones"] = {"large": {"display": {"title": "Large refund"}}}
    definition["rules"] = {
        "flag_large": {
            "display": {"title": "Flag a large refund"},
            "on": "opened",
            "when": {">": [{"var": "amount"}, 1000]},
            "then": {"reach": ["large"]},
        }
        | rule
    }
    return definition


# --- Slice 0: the shape ---


def test_a_rule_reaching_an_undeclared_milestone_is_refused() -> None:
    with pytest.raises(CaseInvalid, match="^rules.flag_large.then.reach: lage is not a milestone$"):
        parse_case(with_rule(then={"reach": ["lage"]}))


def test_a_rule_named_like_a_step_or_a_milestone_is_refused() -> None:
    # A rule's firings are entries (`review#1`) beside step runs, so its name is its own.
    for name in ("review", "large"):
        definition = with_rule()
        definition["rules"] = {name: definition["rules"]["flag_large"]}
        with pytest.raises(CaseInvalid, match=f"^rules.{name}: a rule is not named like a "):
            parse_case(definition)


@pytest.mark.parametrize(
    ("on", "message"),
    [
        ({"started": "pai"}, "rules.flag_large.on.started: pai is not a step"),
        ({"reached": "lage"}, "rules.flag_large.on.reached: lage is not a milestone"),
    ],
)
def test_a_rule_on_what_the_case_doesnt_declare_is_refused(
    on: dict[str, str], message: str
) -> None:
    with pytest.raises(CaseInvalid, match=f"^{message}$"):
        parse_case(with_rule(on=on))


@pytest.mark.parametrize("on", [{"started": "pay"}, {"reached": "large"}, "opened"])
def test_a_rule_names_one_of_three_moments(on: object) -> None:
    parse_case(with_rule(on=on))  # the case opened, a step started, a milestone reached


@pytest.mark.parametrize(
    "on", ["closed", {"answered": "review"}, {"started": "pay", "reached": "large"}]
)
def test_an_unknown_moment_is_refused_in_one_line(on: object) -> None:
    moments = '"opened", {"started": <step>} or {"reached": <milestone>}'
    with pytest.raises(CaseInvalid, match=f"^rules.flag_large.on: a moment is {moments}$"):
        parse_case(with_rule(on=on))


def test_a_rule_without_a_title_is_refused() -> None:
    # Every rule has a business title, as steps do: people read rules too (brief, D1).
    definition = with_rule()
    del definition["rules"]["flag_large"]["display"]
    with pytest.raises(CaseInvalid, match="^rules.flag_large.display: required$"):
        parse_case(definition)


@pytest.mark.parametrize("then", [{"reach": []}, {}])
def test_a_rule_that_does_nothing_is_refused(then: dict[str, Any]) -> None:
    with pytest.raises(CaseInvalid, match="^rules.flag_large.then.reach: "):
        parse_case(with_rule(then=then))
    if then:
        with pytest.raises(CaseInvalid, match="a rule reaches at least one milestone$"):
            parse_case(with_rule(then=then))


# --- Slice 1: reaching ---


def test_a_false_condition_reaches_nothing() -> None:
    run = run_case(
        with_rule(), file={"order_id": "ord-1", "amount": 250}, answers=[], people=PEOPLE
    )
    assert "flag_large#1 on opened: its condition is false" in run.history
    assert "reached large" not in run.history


def test_a_rule_on_the_opening_reaches_its_milestone_once() -> None:
    run = run_case(
        with_rule(), file={"order_id": "ord-1", "amount": 5000}, answers=[], people=PEOPLE
    )
    assert run.history[:3] == [
        "opened by system:opener, with amount and order_id",
        "flag_large#1 on opened: reaching large",
        "reached large",
    ]
    assert run.history.count("reached large") == 1


def test_a_rule_fires_on_each_run_of_its_step() -> None:
    # Two runs of the review: the rule fires on each, and reaches its milestone once.
    definition = with_rule(on={"started": "review"}, when=None)
    definition["steps"]["review"].update({"repeatable": True, "proposed_by": ["support"]})
    definition["stays_open"] = True  # so the review can be proposed again once rejected
    definition["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 250},
        answers=[("review", "reject", "ana"), propose("review", "ana")],
        people=PEOPLE,
    )
    assert [line for line in run.history if line.startswith("flag_large#")] == [
        "flag_large#1 on started review: reaching large",
        "flag_large#2 on started review: reaching large",
    ]
    assert run.history.count("reached large") == 1


def test_a_milestone_a_rule_reaches_starts_what_requires_it() -> None:
    # A rule on a milestone another rule reached: rules follow rules, and the step requiring the
    # last one starts in the same decision.
    definition = with_rule()
    definition["milestones"]["escalated"] = {"display": {"title": "Escalated"}}
    definition["rules"]["escalate"] = {
        "display": {"title": "Escalate a large refund"},
        "on": {"reached": "large"},
        "then": {"reach": ["escalated"]},
    }
    definition["steps"]["check_large"] = {
        "kind": "task",
        "display": {"title": "Check a large refund"},
        "roles": ["support-lead"],
        "requires": ["escalated"],
        "outcomes": {"checked": {"display": {"title": "Checked"}}},
    }
    run = run_case(
        definition, file={"order_id": "ord-1", "amount": 5000}, answers=[], people=PEOPLE
    )
    assert run.history[1:6] == [
        "flag_large#1 on opened: reaching large",
        "reached large",
        "escalate#1 on reached large: reaching escalated",
        "reached escalated",
        "started review#1: waiting for approve or reject by support",
    ]
    assert run.waiting_for == ["review by support", "check_large by support-lead"]


def test_rules_on_one_moment_fire_in_the_order_written() -> None:
    definition = with_rule()
    rule = definition["rules"].pop("flag_large")
    definition["rules"] = {"second_in_name": rule, "first_in_name": rule | {"when": None}}
    run = run_case(
        definition, file={"order_id": "ord-1", "amount": 5000}, answers=[], people=PEOPLE
    )
    assert [line for line in run.history if " on opened" in line] == [
        "second_in_name#1 on opened: reaching large",
        "first_in_name#1 on opened: reaching large",
    ]
