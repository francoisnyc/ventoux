"""Case validation: what can be proven about a case definition by reading it (layer 10).

Tests go through `parse_case`, then `validate_case`, and read the issues it gives.
See docs/layers/10-case-validation.md and docs/guides/cases.md.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.validate import Issue
from ventoux.testing import CATALOG, load_definition

ROOT = Path(__file__).parent.parent
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
GUIDE = ROOT / "docs" / "guides" / "cases.md"
SECTION = "## What `ventoux check` proves about a case"


def guide_json(index: int) -> dict[str, Any]:
    """The JSON block `index` of the guide's section on the check, as stored data."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[index + 1].split("```")[0]
    loaded: dict[str, Any] = json.loads(block, parse_float=Decimal)
    return loaded


def issues(definition: dict[str, Any]) -> list[Issue]:
    return validate_case(parse_case(definition), CATALOG)


# --- Slice 0: the seam ---


def test_only_a_parsed_case_is_validated() -> None:
    # Fail closed: a definition nobody parsed is refused, never read as one with no problems.
    with pytest.raises(TypeError, match="parse_case"):
        validate_case(REFUND, CATALOG)  # type: ignore[arg-type]


def test_an_issue_is_an_error_unless_it_says_otherwise() -> None:
    # Fail closed: a check that forgets to say how serious its issue is refuses the definition.
    assert Issue("steps.pay", "NEVER_RUNS", "pay can never run").severity == "error"
    warned = Issue("closes_when", "CLOSE_UNREACHABLE", "paid can never be reached", "warning")
    assert warned.severity == "warning"


def test_the_guides_claim_has_no_issues() -> None:
    assert issues(guide_json(0)) == []


def test_the_quickstart_refund_has_no_issues() -> None:
    assert issues(REFUND) == []


# --- Slice 1: steps that never run ---


def claim_with(**steps: Any) -> dict[str, Any]:
    """The guide's claim with some steps replaced (or added), and a `reviewed` milestone."""
    claim = guide_json(0)
    claim["milestones"]["reviewed"] = {"display": {"title": "Claim reviewed"}}
    claim["steps"] |= steps
    return claim


APPROVE = {
    "kind": "task",
    "display": {"title": "Approve the assessment"},
    "roles": ["adjuster"],
    "requires": ["reviewed"],
    "outcomes": {"ok": {"display": {"title": "Approved"}}},
}


def test_a_step_requiring_what_nothing_reaches_never_runs() -> None:
    assert issues(claim_with(approve=APPROVE)) == [
        Issue(
            "steps.approve.requires",
            "NEVER_RUNS",
            "approve can never run: it requires reviewed, which no step reaches: reach reviewed "
            "from a step, or remove the requirement",
        )
    ]


def test_the_order_of_the_steps_does_not_matter() -> None:
    # A case has no position: `pay` written before the steps it waits on can still run. One pass
    # in the written order would find `pay` and `assess` not yet possible, and refuse them.
    claim = guide_json(0)
    claim["steps"] = dict(reversed(claim["steps"].items()))
    assert list(claim["steps"]) == ["pay", "assess", "check"]
    assert issues(claim) == []
