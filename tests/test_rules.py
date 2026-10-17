"""Rules: on a moment, when a condition holds, then act on the case (layer 11a).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md and docs/guides/cases.md, "Rules".
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import load_definition

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")


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
