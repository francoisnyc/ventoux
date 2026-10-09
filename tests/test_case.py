"""The case layer: a case definition, and the runtime that runs it in memory (layer 8a).

Tests go through `parse_case` and `run_case`, and read what a run reports.
See docs/layers/08-case.md and docs/guides/cases.md.
"""

import copy
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.testing import (
    AnswerRefused,
    CaseRefused,
    InputRefused,
    load_definition,
    run_case,
)

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


# --- Slice 2: the case file ---


@pytest.mark.parametrize(
    ("file", "message"),
    [
        (
            {"order_id": "ord-1", "amount": 250, "approved_amount": 250},
            "approved_amount is set by a person in review, never given at the opening",
        ),
        (
            {"order_id": "ord-1", "amount": 250, "colour": "red"},
            "colour is not a field of refund: its fields are amount, approved_amount and order_id",
        ),
        (
            {"order_id": 1001, "amount": 40},
            "order_id is a reference to orders, and the opening gives 1001",
        ),
    ],
)
def test_the_opening_gives_the_declared_fields_of_their_types(
    file: dict[str, Any], message: str
) -> None:
    with pytest.raises(CaseRefused, match=f"^{message}$"):
        run_case(REFUND, file=file, answers=[], people=PEOPLE)


def test_a_float_is_refused_never_guessed() -> None:
    # A binary float may already have lost its exact value (brief, D20).
    with pytest.raises(CaseRefused, match="^amount is a number, and the opening gives 0.1$"):
        run_case(REFUND, file={"order_id": "ord-1", "amount": 0.1}, answers=[], people=PEOPLE)
    with pytest.raises(
        AnswerRefused, match="^approved_amount is a number, and the answer gives 40.5$"
    ):
        run_case(
            REFUND,
            file={"order_id": "ord-1", "amount": 40},
            answers=[("review", "approve", "ana", {"approved_amount": 40.5})],
            people=PEOPLE,
        )


def test_opening_values_say_who_gave_them() -> None:
    small = {"order_id": "ord-1", "amount": 40}
    review = [("review", "approve", "ana", {"approved_amount": 40})]
    by_a_system = run_case(REFUND, file=small, answers=review, people=PEOPLE)
    assert "opened by system:opener, with amount and order_id" in by_a_system.history
    by_lee = run_case(REFUND, file=small, answers=review, people=PEOPLE, opened_by="lee")
    assert "opened by lee, with amount and order_id" in by_lee.history
    assert (
        "scheduled pay#1: payments.refund@2 (order_id from person:lee; amount from person:ana)"
        in by_lee.history
    )
    # Who opened it is written one way, as who answers (brief, D22).
    with pytest.raises(CaseRefused, match="'Lee' is not written as a person's identifier"):
        run_case(REFUND, file=small, answers=review, people=PEOPLE, opened_by="Lee")


def test_a_forms_values_land_in_the_case_file() -> None:
    # A field declared untrusted keeps its mark when a person's form sets it (layer 7's review):
    # the form adds who answered, and payments.refund@2 takes no untrusted amount.
    definition = refund()
    definition["fields"]["approved_amount"]["source"] = "untrusted:customer"
    with pytest.raises(InputRefused, match="amount"):
        run_case(
            definition,
            file={"order_id": "ord-1", "amount": 40},
            answers=[("review", "approve", "ana", {"approved_amount": 40})],
            people=PEOPLE,
        )
