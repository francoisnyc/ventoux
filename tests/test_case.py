"""The case layer: a case definition, and the runtime that runs it in memory (layer 8a).

Tests go through `parse_case` and `run_case`, and read what a run reports.
See docs/layers/08-case.md and docs/guides/cases.md.
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import load_definition, run_case

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")


def refund(**changes: Any) -> dict[str, Any]:
    """A copy of the quickstart's refund, to change."""
    definition = copy.deepcopy(REFUND)
    definition.update(changes)
    return definition


def without(definition: dict[str, Any], *path: str) -> dict[str, Any]:
    """`definition` with the key at `path` removed."""
    inner = definition
    for key in path[:-1]:
        inner = inner[key]
    del inner[path[-1]]
    return definition


# --- Slice 0: the case definition ---


def test_the_quickstarts_refund_is_read() -> None:
    case = parse_case(REFUND)
    assert list(case.steps) == ["review", "pay"]
    assert case.display.title == "Customer refund"


@pytest.mark.parametrize(
    "path",
    [
        ("display",),
        ("fields", "amount", "display"),
        ("steps", "pay", "display"),
        ("steps", "review", "outcomes", "reject", "display"),
        ("steps", "pay", "approval", "display"),
    ],
)
def test_everything_people_read_has_a_title(path: tuple[str, ...]) -> None:
    # A business title on everything people read (brief, D1): a step without one is refused.
    with pytest.raises(CaseInvalid, match=f"^{'.'.join(path)}: required$"):
        parse_case(without(refund(), *path))


def test_a_title_is_never_empty() -> None:
    definition = refund()
    definition["steps"]["pay"]["display"]["title"] = ""
    with pytest.raises(CaseInvalid, match="steps.pay.display.title: "):
        parse_case(definition)


def changed(change: str) -> dict[str, Any]:
    """The refund with one of the changes below made."""
    definition = refund()
    steps = definition["steps"]
    if change == "kind":
        steps["pay"]["kind"] = "script"
    elif change == "sequence":
        definition["sequence"] = ["review", "pya"]
    elif change == "requires":
        steps["pay"]["requires"] = ["reviwe"]
    elif change == "milestone":
        definition["milestones"] = {"review": {"display": {"title": "Reviewed"}}}
    elif change == "reaches":
        steps["pay"]["reaches"] = ["paid"]
    elif change == "sets":
        steps["review"]["outcomes"]["approve"]["sets"] = ["approved_amout"]
    return definition


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("kind", "steps.pay.kind: a step is a task or an activity, and this one is 'script'"),
        ("sequence", "sequence: pya is not a step"),
        ("requires", "steps.pay.requires: reviwe is neither a milestone nor a step"),
        ("milestone", "milestones.review: a milestone is not named like a step"),
        ("reaches", "steps.pay.reaches: paid is not a milestone"),
        ("sets", "steps.review.outcomes.approve.sets: approved_amout is not a field"),
    ],
)
def test_a_definition_that_names_nothing_is_refused(change: str, message: str) -> None:
    with pytest.raises(CaseInvalid, match=f"^{message}$"):
        parse_case(changed(change))


def test_a_step_nobody_can_start_is_refused() -> None:
    manual = refund()
    manual["steps"]["pay"]["automatic"] = False
    with pytest.raises(
        CaseInvalid,
        match="^steps.pay: a step that doesn't start by itself names proposed_by, who may "
        "propose it$",
    ):
        parse_case(manual)
    again = refund()
    again["steps"]["review"]["repeatable"] = True
    with pytest.raises(
        CaseInvalid,
        match="^steps.review: a repeatable step runs again only when proposed: name "
        "proposed_by, who may propose it$",
    ):
        parse_case(again)


def test_an_expression_the_engine_does_not_know_is_refused_when_read() -> None:
    definition = refund()
    definition["steps"]["pay"]["approval"]["when"] = {"now": []}
    with pytest.raises(CaseInvalid, match="steps.pay.approval.when: `now` is not an operator"):
        parse_case(definition)


# --- Slice 1: the runtime replaces the tracer's walk ---

# Who has which role: the test plays the Ventoux API (brief, D22).
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"]}


def test_a_case_waiting_for_its_review_says_so() -> None:
    # Design question 14 (brief, D24): the tracer crashed when nobody had answered the review.
    run = run_case(REFUND, file={"order_id": "ord-1", "amount": 250}, answers=[], people=PEOPLE)
    assert run.waiting_for == ["review by support"]
    assert not run.reached("review")
    assert not run.closed
