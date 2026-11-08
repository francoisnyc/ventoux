"""The conformance suite: definitions with the validation results any implementation must give
(layer 20a) (brief, D80). See docs/layers/20-deployment.md and docs/guides/deployment.md."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from ventoux.testing import CATALOG
from ventoux.tooling.conformance import SuiteUnreadable, catalog_data, mismatches

ROOT = Path(__file__).parent.parent
REFUND = ROOT / "examples" / "refund" / "refund.json"  # a valid case with no plan step


def a_suite(folder: Path, *entries: dict[str, Any]) -> Path:
    """A suite in `folder`: the development catalog, the refund case, and `entries`."""
    (folder / "catalogs").mkdir(parents=True)
    (folder / "catalogs" / "development.json").write_text(
        json.dumps(catalog_data(CATALOG), indent=2, sort_keys=True) + "\n"
    )
    (folder / "cases").mkdir()
    shutil.copy(REFUND, folder / "cases" / "refund.json")
    (folder / "suite.json").write_text(json.dumps({"engine": 3, "entries": list(entries)}))
    return folder


def refund_entry(expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "the refund case",
        "kind": "package",
        "case": "cases/refund.json",
        "plans": [],
        "cases": {},
        "catalog": "development",
        "expected": expected,
    }


def test_an_entry_expecting_an_issue_a_valid_definition_doesnt_give_is_a_mismatch(
    tmp_path: Path,
) -> None:
    expected = {
        "issues": [{"path": "steps.pay.when", "code": "UNKNOWN_FIELD", "severity": "error"}]
    }
    suite = a_suite(tmp_path, refund_entry(expected))
    assert mismatches(suite) == [
        "the refund case: expected steps.pay.when UNKNOWN_FIELD (error), not given"
    ]


CLOSED_EARLY = ROOT / "examples" / "checks" / "closed-before-it-acts.json"  # gives NEVER_FIRES
NEVER_FIRES = {"path": "rules.say_goodbye.on", "code": "NEVER_FIRES", "severity": "error"}


def closed_early_entry(expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "closed before it acts",
        "kind": "package",
        "case": "cases/closed-before-it-acts.json",
        "plans": [],
        "cases": {},
        "catalog": "development",
        "expected": expected,
    }


def test_an_entry_expected_valid_whose_definition_gives_an_issue_is_a_mismatch(
    tmp_path: Path,
) -> None:
    suite = a_suite(tmp_path, closed_early_entry({"issues": []}))
    shutil.copy(CLOSED_EARLY, suite / "cases")
    assert mismatches(suite) == [
        "closed before it acts: given rules.say_goodbye.on NEVER_FIRES (error), not expected"
    ]


def test_issues_are_compared_in_any_order_as_a_multiset_never_by_message(tmp_path: Path) -> None:
    # Expected twice, given once: one is missing. In another order: nothing else said.
    twice = closed_early_entry({"issues": [NEVER_FIRES, NEVER_FIRES]})
    suite = a_suite(tmp_path, twice)
    shutil.copy(CLOSED_EARLY, suite / "cases")
    assert mismatches(suite) == [
        "closed before it acts: expected rules.say_goodbye.on NEVER_FIRES (error), not given"
    ]


def test_an_issue_of_another_severity_is_both_missing_and_extra(tmp_path: Path) -> None:
    warning = {**NEVER_FIRES, "severity": "warning"}
    suite = a_suite(tmp_path, closed_early_entry({"issues": [warning]}))
    shutil.copy(CLOSED_EARLY, suite / "cases")
    assert mismatches(suite) == [
        "closed before it acts: expected rules.say_goodbye.on NEVER_FIRES (warning), not given",
        "closed before it acts: given rules.say_goodbye.on NEVER_FIRES (error), not expected",
    ]


def test_an_expected_issue_carrying_a_message_is_refused_since_wording_is_never_compared(
    tmp_path: Path,
) -> None:
    worded = {**NEVER_FIRES, "message": "never fires"}
    suite = a_suite(tmp_path, closed_early_entry({"issues": [worded]}))
    shutil.copy(CLOSED_EARLY, suite / "cases")
    with pytest.raises(SuiteUnreadable) as refused:
        mismatches(suite)
    assert "entries.0.expected.issues.0.message: Extra inputs are not permitted" in str(
        refused.value
    )


def with_unreadable_case(suite: Path) -> Path:
    """`suite` with `cases/unreadable.json`: the refund case, `automatic` written as a word."""
    case = json.loads(REFUND.read_text())
    case["steps"]["review"]["automatic"] = "yes"
    (suite / "cases" / "unreadable.json").write_text(json.dumps(case))
    return suite


def unreadable_entry(expected: dict[str, Any]) -> dict[str, Any]:
    return {**refund_entry(expected), "name": "unreadable", "case": "cases/unreadable.json"}


def test_a_definition_refused_when_read_matches_the_paths_it_is_refused_at(tmp_path: Path) -> None:
    expected = {"read": "refused", "at": ["steps.review.automatic"]}
    suite = with_unreadable_case(a_suite(tmp_path, unreadable_entry(expected)))
    assert mismatches(suite) == []


def test_a_definition_refused_when_read_but_expected_to_read_is_a_mismatch(tmp_path: Path) -> None:
    suite = with_unreadable_case(a_suite(tmp_path, unreadable_entry({"issues": []})))
    assert mismatches(suite) == [
        "unreadable: expected to be read, refused when read at steps.review.automatic"
    ]


def test_a_definition_that_reads_but_expected_refused_is_a_mismatch(tmp_path: Path) -> None:
    expected = {"read": "refused", "at": ["steps.review.automatic"]}
    suite = a_suite(tmp_path, refund_entry(expected))
    assert mismatches(suite) == [
        "the refund case: expected refused when read at steps.review.automatic, read"
    ]


def test_a_definition_refused_at_another_path_is_a_mismatch(tmp_path: Path) -> None:
    expected = {"read": "refused", "at": ["steps.review.repeatable"]}
    suite = with_unreadable_case(a_suite(tmp_path, unreadable_entry(expected)))
    assert mismatches(suite) == [
        (
            "unreadable: expected refused when read at steps.review.repeatable, "
            "refused at steps.review.automatic"
        )
    ]


PACKAGE = ROOT / "examples" / "packages" / "refund"  # a case with a plan step, and its plan


def with_package(suite: Path) -> Path:
    """`suite` with the refund package's case and its plan."""
    shutil.copy(PACKAGE / "case.json", suite / "cases" / "refund-package.json")
    (suite / "plans").mkdir(exist_ok=True)
    shutil.copy(PACKAGE / "plans" / "refund-order.json", suite / "plans")
    return suite


def package_entry(plans: list[str]) -> dict[str, Any]:
    return {
        **refund_entry({"issues": []}),
        "name": "the refund package",
        "case": "cases/refund-package.json",
        "plans": plans,
    }


def test_a_package_is_read_with_its_plans_as_the_one_check_reads_it(tmp_path: Path) -> None:
    suite = with_package(a_suite(tmp_path, package_entry(["plans/refund-order.json"])))
    assert mismatches(suite) == []


def test_a_package_that_cant_be_put_together_is_a_broken_entry_said_never_a_result(
    tmp_path: Path,
) -> None:
    suite = with_package(a_suite(tmp_path, package_entry([])))
    assert mismatches(suite) == [
        (
            "the refund package: a broken entry, not a package: refund-order@1 is run by a plan "
            "step and isn't in plans/: add it"
        )
    ]


def with_plans(suite: Path) -> Path:
    """`suite` with the refund order plan, one sending `done` nowhere, and one unreadable."""
    plan = json.loads((PACKAGE / "plans" / "refund-order.json").read_text())
    (suite / "plans").mkdir(exist_ok=True)
    (suite / "plans" / "refund-order.json").write_text(json.dumps(plan))
    plan["states"]["check_order"]["on"]["done"] = "nowhere"
    (suite / "plans" / "nowhere.json").write_text(json.dumps(plan))
    plan["states"]["check_order"]["activity"] = 3
    (suite / "plans" / "unreadable.json").write_text(json.dumps(plan))
    return suite


def plan_entry(name: str, expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "plan",
        "plan": f"plans/{name}.json",
        "catalog": "development",
        "expected": expected,
    }


def test_a_plan_alone_is_read_and_checked_against_its_catalog(tmp_path: Path) -> None:
    unreached = [
        {"path": f"states.{state}", "code": "UNREACHABLE_STATE", "severity": "error"}
        for state in ("approve_refund", "pay", "paid")
    ]
    nowhere = {"path": "states.check_order.on.done", "code": "UNKNOWN_TARGET", "severity": "error"}
    suite = with_plans(
        a_suite(
            tmp_path,
            plan_entry("refund-order", {"issues": []}),
            plan_entry("nowhere", {"issues": [nowhere, *unreached]}),
            plan_entry("unreadable", {"read": "refused", "at": ["states.check_order.activity"]}),
        )
    )
    assert mismatches(suite) == []


def test_a_plan_entry_is_compared_as_a_package_is(tmp_path: Path) -> None:
    suite = with_plans(a_suite(tmp_path, plan_entry("nowhere", {"issues": []})))
    assert mismatches(suite)[0] == (
        "nowhere: given states.approve_refund UNREACHABLE_STATE (error), not expected"
    )
