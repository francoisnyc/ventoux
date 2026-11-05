"""Layer 18a: required steps. A required step is work the case owes: it may not close by itself
until the step's latest run is done, and only its doing or a person's close ends that (brief, D72).

See docs/layers/18-lifecycle.md (18a) and docs/guides/cases.md, "Required steps".
"""

import copy
import json
import runpy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, load_definition, propose, run_case
from ventoux.tooling.builder.written import written

ROOT = Path(__file__).parent.parent
GUIDE = ROOT / "docs" / "guides" / "cases.md"
SECTION = "## Required steps"
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")  # the quickstart's


def guide_confirm() -> dict[str, Any]:
    """The guide's required `confirm` step, as stored data, read from the guide itself so the
    guide can't drift from what is tested."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[1].split("```")[0]
    fragment: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    return fragment


def refund_confirmed() -> dict[str, Any]:
    """The quickstart's refund, with the guide's required `confirm` step."""
    definition = copy.deepcopy(REFUND)
    definition["steps"] |= guide_confirm()
    return definition


def test_a_required_step_nothing_can_ever_start_is_refused_at_validation() -> None:
    # The curriculum's negative test. A step that can never run is already an error for every
    # step (NEVER_RUNS, from layer 10's fixpoint); a required one gets that issue alone, one
    # cause, one issue (brief, D72).
    definition = refund_confirmed()
    definition["milestones"] = {"reported": {"display": {"title": "Reported"}}}
    definition["steps"]["confirm"]["requires"] = ["reported"]  # nothing reaches it
    found = validate_case(parse_case(definition), CATALOG)
    assert [(issue.path, issue.code, issue.message) for issue in found] == [
        (
            "steps.confirm.requires",
            "NEVER_RUNS",
            (
                "confirm can never run: it requires reported, which no step or rule reaches: "
                "reach reported from a step or a rule, or remove the requirement"
            ),
        )
    ]


def test_a_required_step_with_a_condition_is_refused_when_read() -> None:
    # A required step is owed in every case, so it has no `when`: a step owed only sometimes is
    # started by a rule, or proposed, and isn't required (brief, D72).
    definition = refund_confirmed()
    definition["steps"]["confirm"]["when"] = {"==": [{"var": "review.outcome"}, "reject"]}
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == (
        "steps.confirm: a required step is owed in every case, so it has no when: start it from "
        "a rule, or drop required"
    )


ORDER = {"order_id": "ord-1", "amount": 250}
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "omar": ["operations"]}


def test_a_case_that_owes_a_required_step_stays_open_and_says_so() -> None:
    # The guide's example, as written: a rejected refund starts nothing more, but the case owes
    # `confirm`, so it doesn't close by itself, and says what it owes and who may start it.
    refund = refund_confirmed()
    rejected = run_case(refund, file=ORDER, answers=[("review", "reject", "ana")], people=PEOPLE)
    assert rejected.waiting_for == ["confirm, required, proposed by support"]
    assert not rejected.closed

    confirmed = run_case(
        refund,
        file=ORDER,
        answers=[
            ("review", "reject", "ana"),
            propose("confirm", "ana"),
            ("confirm", "confirmed", "ana"),
        ],
        people=PEOPLE,
    )
    assert confirmed.closed


def test_the_builder_writes_the_guides_required_step() -> None:
    # The builder guide's example is the cases guide's refund, word for word as data: the same
    # JSON whichever way it is written (brief, D58).
    found = runpy.run_path(str(ROOT / "examples" / "builder" / "required.py"))["refund"]
    assert json.loads(written(found), parse_float=Decimal) == refund_confirmed()
