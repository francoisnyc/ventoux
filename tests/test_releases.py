"""Releases: a package, its behaviour digest, its number and its record (layer 12a; brief, D50).

See docs/layers/12-releases.md (12a) and docs/guides/releases.md.
"""

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.releases import (
    Changed,
    Outcome,
    Package,
    PackageRefused,
    Record,
    Released,
    Reworded,
    Unchanged,
    next_release,
    package,
    record,
)
from ventoux.testing import CATALOG
from ventoux.tooling.releases import read_package

ROOT = Path(__file__).parent.parent
REFUND = ROOT / "examples" / "packages" / "refund"


def written(folder: Path = REFUND) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The example package's case and plans, as data a test may change."""
    case = json.loads((folder / "case.json").read_text())
    plans = [json.loads(plan.read_text()) for plan in sorted((folder / "plans").iterdir())]
    return case, plans


def packed(case: dict[str, Any], plans: list[dict[str, Any]] | None = None) -> Package:
    """The package of `case` and `plans`, written as JSON text, as a folder holds them."""
    return package(json.dumps(case), [json.dumps(plan) for plan in plans or []])


def lettered(template: str) -> dict[str, Any]:
    """A case that drafts a letter with `template` passed as a literal input: the warm-up's
    letter (learning question 11)."""
    return {
        "case": "letter",
        "display": {"title": "A letter to a customer"},
        "fields": {"email": {"type": "string", "display": {"title": "Email"}}},
        "steps": {
            "draft": {
                "kind": "activity",
                "display": {"title": "Draft the letter"},
                "activity": "letters.draft@2",
                "inputs": {"to_customer": {"var": "email"}, "template": template},
            }
        },
    }


def record_of(released: Package, outcome: Outcome, commit: str = "4f2a9c1") -> Record:
    """The record CI would write for `outcome`, with the development catalog."""
    assert isinstance(outcome, Released | Reworded), f"{outcome}: nothing is recorded"
    return record(released, outcome, commit, CATALOG)


def released_once(case: dict[str, Any], plans: list[dict[str, Any]] | None = None) -> list[Record]:
    """The records of a package released once, as release 1."""
    first = packed(case, plans)
    outcome = next_release(first, [])
    assert outcome == Released(1, Changed())
    return [record_of(first, outcome)]


def test_a_literal_input_changed_is_a_release() -> None:
    # A literal passed to an activity is behaviour (brief, D5), however much it reads like words:
    # never wording only.
    records = released_once(lettered("Dear customer, we are pleased to confirm your refund."))
    changed = copy.deepcopy(lettered("Dear customer, we are happy to confirm your refund."))
    outcome = next_release(packed(changed), records)
    assert isinstance(outcome, Released) and outcome.release == 2
    assert outcome.changed.behaviour == ("steps.draft.inputs.template",)
    assert outcome.changed.wording == ()


def with_two_rules(first: str, second: str) -> dict[str, Any]:
    """The refund package's case with two rules on the review's answer, in the order given."""
    case, _ = written()
    case["milestones"] = {
        name: {"display": {"title": name.capitalize()}} for name in ("noted", "flagged")
    }
    rules = {
        "note": {
            "display": {"title": "Note the review"},
            "on": {"answered": "review"},
            "then": {"reach": ["noted"]},
        },
        "flag": {
            "display": {"title": "Flag the review"},
            "on": {"answered": "review"},
            "then": {"reach": ["flagged"]},
        },
    }
    case["rules"] = {first: rules[first], second: rules[second]}
    return case


def test_rules_reordered_are_a_release() -> None:
    # Rules on one moment act in the order written (brief, D38): reordering them is behaviour.
    _, plans = written()
    records = released_once(with_two_rules("note", "flag"), plans)
    outcome = next_release(packed(with_two_rules("flag", "note"), plans), records)
    assert outcome == Released(2, Changed(behaviour=("rules",)))


def test_steps_reordered_are_a_release() -> None:
    # Admission asks each step in the order written, so the commands come in that order.
    case, plans = written()
    records = released_once(case, plans)
    steps = case["steps"]
    case["steps"] = {name: steps[name] for name in ("settle", "review", "call_customer")}
    assert next_release(packed(case, plans), records) == Released(2, Changed(("steps",)))


def test_a_field_named_display_is_behaviour() -> None:
    # Wording is found by its type, never by a key's name: a case-file field called `display`
    # retyped is a release, never wording only.
    case, plans = written()
    case["fields"]["display"] = {"type": "number", "display": {"title": "Shown amount"}}
    records = released_once(case, plans)
    case["fields"]["display"]["type"] = "string"
    outcome = next_release(packed(case, plans), records)
    assert outcome == Released(2, Changed(behaviour=("fields.display.type",)))


def test_a_fields_type_changed_is_a_release() -> None:
    # A field's `type` names its shape, so it is kept even at its default.
    case, plans = written()
    records = released_once(case, plans)
    case["fields"]["amount"]["type"] = "string"
    outcome = next_release(packed(case, plans), records)
    assert outcome == Released(2, Changed(behaviour=("fields.amount.type",)))


def test_a_title_changed_is_wording_only() -> None:
    case, plans = written()
    records = released_once(case, plans)
    case["steps"]["settle"]["display"]["title"] = "Pay the refund"
    case["steps"]["review"]["outcomes"]["reject"]["display"]["title"] = "Turn the refund down"
    outcome = next_release(packed(case, plans), records)
    paths = ("steps.review.outcomes.reject.display.title", "steps.settle.display.title")
    assert outcome == Reworded(1, 2, Changed(wording=paths))


def test_an_approval_reason_changed_is_wording_only() -> None:
    records = released_once(json.loads((ROOT / "examples/refund/refund.json").read_text()))
    case = json.loads((ROOT / "examples/refund/refund.json").read_text())
    case["steps"]["pay"]["approval"]["display"]["reason"] = "A team lead checks refunds over 100"
    outcome = next_release(packed(case), records)
    assert outcome == Reworded(1, 2, Changed(wording=("steps.pay.approval.display.reason",)))


def test_reformatting_changes_no_digest() -> None:
    case, plans = written()
    records = released_once(case, plans)
    # Another layout, and an object's keys in another order: the same definition.
    review = case["steps"]["review"]
    case["steps"]["review"] = dict(reversed(list(review.items())))
    texts = [json.dumps(plan, indent=4) for plan in plans]
    assert next_release(package(json.dumps(case, indent=1), texts), records) == Unchanged(1)


def test_an_explicit_default_changes_no_digest() -> None:
    case, plans = written()
    records = released_once(case, plans)
    case["stays_open"] = False
    case["steps"]["review"]["repeatable"] = False
    case["steps"]["settle"]["max_age"] = {}
    assert next_release(packed(case, plans), records) == Unchanged(1)


def refused(case: dict[str, Any], plans: list[dict[str, Any]]) -> str:
    """Why the package of `case` and `plans` is refused."""
    with pytest.raises(PackageRefused) as refusal:
        packed(case, plans)
    return str(refusal.value)


def test_a_missing_plan_is_refused() -> None:
    case, _ = written()
    assert refused(case, []) == "refund-order@1 is run by a plan step and isn't in plans/: add it"


def test_a_plan_nobody_runs_is_refused() -> None:
    # Shipped and never run: fail closed, as a plan supplied under another reference is (D28).
    case, plans = written()
    spare = {**plans[0], "version": 2}
    assert refused(case, [*plans, spare]) == (
        "refund-order@2 is run by no plan step: remove it, or name it in a step"
    )


def test_a_plan_given_twice_is_refused() -> None:
    case, plans = written()
    assert refused(case, [*plans, plans[0]]) == (
        "refund-order@1 is given twice: keep one file for it"
    )


def test_a_stray_file_is_refused(tmp_path: Path) -> None:
    folder = copied(tmp_path)
    (folder / "notes.txt").write_text("to do")
    (folder / "plans" / "draft.yaml").write_text("plan: draft")
    with pytest.raises(PackageRefused) as refusal:
        read_package(folder)
    assert str(refusal.value) == (
        "notes.txt isn't part of a package: a package holds case.json and plans/\n"
        "plans/draft.yaml isn't a plan's file: each plan is a .json file"
    )


def test_a_plans_change_is_a_release_of_its_package() -> None:
    case, plans = written()
    records = released_once(case, plans)
    plans[0]["states"]["approve_refund"]["approval"]["timeout"] = "72h"
    path = "plans.refund-order@1.states.approve_refund.approval.timeout"
    assert next_release(packed(case, plans), records) == Released(2, Changed(behaviour=(path,)))


def copied(tmp_path: Path) -> Path:
    """The example package, copied where a test may change it."""
    folder = tmp_path / "refund"
    shutil.copytree(REFUND, folder)
    return folder
