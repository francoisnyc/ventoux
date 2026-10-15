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
    """The JSON block `index` of the guide's section on the check, as stored data; a fragment
    (`"requires": [...]`) is read as an object."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[index + 1].split("```")[0]
    fragment = block if block.lstrip().startswith("{") else "{" + block + "}"
    loaded: dict[str, Any] = json.loads(fragment, parse_float=Decimal)
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


# --- Slice 2: the curriculum's negative test ---


def deadlocked_claim() -> dict[str, Any]:
    """The guide's claim with `assess` also requiring `paid`, as the guide shows it."""
    claim = guide_json(0)
    claim["steps"]["assess"] |= guide_json(1)
    return claim


def errors(definition: dict[str, Any]) -> list[Issue]:
    return [issue for issue in issues(definition) if issue.severity == "error"]


def test_the_deadlocked_claim_is_refused() -> None:
    # One issue for the steps that wait on each other, none for each of them.
    assert errors(deadlocked_claim()) == [
        Issue(
            "steps.assess.requires",
            "DEADLOCK",
            "assess and pay wait on each other: assess requires paid, which only pay reaches; "
            "pay requires assessed, which only assess reaches: remove one of these requirements",
        )
    ]


def test_a_step_requiring_itself_is_deadlocked() -> None:
    claim = guide_json(0)
    claim["steps"]["check"]["requires"] = ["check"]
    assert errors(claim) == [
        Issue(
            "steps.check.requires",
            "DEADLOCK",
            "check waits on itself: check requires check: remove this requirement",
        ),
        Issue(
            "steps.assess.requires",
            "NEVER_RUNS",
            "assess can never run: it requires checked, which only check reaches, and check can "
            "never run: fix check first",
        ),
        Issue(
            "steps.pay.requires",
            "NEVER_RUNS",
            "pay can never run: it requires assessed, which only assess reaches, and assess can "
            "never run: fix assess first",
        ),
    ]


def test_sequence_and_requires_can_deadlock() -> None:
    # `sequence` makes pay require assess; assess requiring pay closes the circle. The message
    # says where the requirement nobody wrote on pay comes from.
    claim = guide_json(0)
    claim["steps"]["assess"]["requires"] = ["checked", "pay"]
    claim["steps"]["pay"]["requires"] = []
    claim["sequence"] = ["assess", "pay"]
    assert errors(claim) == [
        Issue(
            "steps.assess.requires",
            "DEADLOCK",
            "assess and pay wait on each other: assess requires pay; pay comes after assess in "
            "sequence: remove one of these requirements",
        )
    ]


NOTIFY = {
    "kind": "task",
    "display": {"title": "Tell the customer"},
    "roles": ["adjuster"],
    "requires": ["assessed"],
    "outcomes": {"told": {"display": {"title": "Told"}}},
}


def test_a_step_waiting_on_a_deadlock_never_runs() -> None:
    claim = deadlocked_claim()
    claim["steps"]["notify"] = NOTIFY
    claim["steps"]["remind"] = {**NOTIFY, "requires": ["assess"]}
    assert errors(claim)[1:] == [
        Issue(
            "steps.notify.requires",
            "NEVER_RUNS",
            "notify can never run: it requires assessed, which only assess reaches, and assess can "
            "never run: fix assess first",
        ),
        Issue(
            "steps.remind.requires",
            "NEVER_RUNS",
            "remind can never run: it requires assess, which can never run: fix assess first",
        ),
    ]


# --- Slice 3: closing ---


def test_a_step_after_the_close_never_runs() -> None:
    # `closes_when` is checked before admission (layer 8b): once paid is reached the case is
    # closing, and nothing starts.
    thank = {**NOTIFY, "display": {"title": "Thank the customer"}, "requires": ["paid"]}
    assert issues(claim_with(thank=thank)) == [
        Issue(
            "steps.thank.requires",
            "NEVER_RUNS",
            "thank can never run: it requires paid, and claim closes once paid is reached, before "
            "thank could start: remove paid from its requires, or from closes_when",
        )
    ]


def test_a_step_nobody_may_propose_never_runs() -> None:
    # A role nobody registered counts for nothing, as when the case runs (brief, D22).
    recheck = {
        **NOTIFY,
        "display": {"title": "Check the customer again"},
        "requires": ["checked"],
        "automatic": False,
        "proposed_by": ["supprt"],
    }
    assert issues(claim_with(recheck=recheck)) == [
        Issue(
            "steps.recheck.proposed_by",
            "NEVER_RUNS",
            "recheck can never run: it starts only when proposed, and none of its proposed_by "
            "roles (supprt) is registered: name a registered role",
        )
    ]


def test_a_case_that_closes_at_opening_is_refused() -> None:
    # Nothing is pending when it opens, so it closes at once, and every proposal after is refused.
    # Here it is the only cause, so the only issue.
    claim = guide_json(0)
    claim["steps"]["check"] |= {"automatic": False, "proposed_by": ["adjuster"]}
    assert issues(claim) == [
        Issue(
            "steps",
            "CLOSES_AT_OPENING",
            "nothing starts by itself when claim opens, so it closes at once and every proposal "
            "is refused: let a step start by itself with nothing required, or add stays_open",
        )
    ]


def test_closing_at_opening_is_said_beside_a_step_dead_for_its_own_reason() -> None:
    # Two causes, two fixes: the case closes at once, and approve needs reviewed, which nothing
    # reaches. A step dead for its own reason keeps its own issue.
    claim = claim_with(approve=APPROVE)
    claim["steps"]["check"] |= {"automatic": False, "proposed_by": ["adjuster"]}
    assert [issue.code for issue in issues(claim)] == ["CLOSES_AT_OPENING", "NEVER_RUNS"]
    assert issues(claim)[1].path == "steps.approve.requires"


def test_a_case_nobody_can_close_is_refused() -> None:
    claim = guide_json(0)
    claim["stays_open"] = True
    claim["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate claim"}, "roles": ["supprt"]}
    }
    assert issues(claim) == [
        Issue(
            "close_reasons",
            "NEVER_CLOSES",
            "claim stays open, and no close reason names a registered role, so nobody could ever "
            "close it: name a registered role in a close reason",
        )
    ]
    claim["close_reasons"]["duplicate"]["roles"] = ["supprt", "adjuster"]
    assert issues(claim) == []
