"""Layer 18c: child cases. A case step opens a whole case, pinned by its parent's release, given
its opening from the parent's case file, and reporting back as the step's outputs (brief, D74).

See docs/layers/18-lifecycle.md (18c) and docs/guides/cases.md, "Child cases".
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG

ROOT = Path(__file__).parent.parent
GUIDE = ROOT / "docs" / "guides" / "cases.md"
SECTION = "## Child cases"


def guide_steps() -> dict[str, Any]:
    """The guide's `repair` and `pay_garage` steps, as stored data, read from the guide."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[1].split("```")[0]
    loaded: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    return loaded


def claim() -> dict[str, Any]:
    """A claim reduced to what the guide's section needs: an adjuster assesses it, setting the
    payout, then the guide's steps repair the vehicle and pay the garage."""
    return {
        "case": "claim",
        "display": {"title": "Insurance claim"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}},
            "vehicle": {"type": "string", "display": {"title": "Vehicle"}},
            "payout": {"type": "number", "display": {"title": "Payout"}},
        },
        "milestones": {"assessed": {"display": {"title": "Claim assessed"}}},
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess the claim"},
                "roles": ["adjuster"],
                "outcomes": {
                    "accept": {
                        "display": {"title": "Accept the claim"},
                        "sets": ["payout"],
                        "reaches": ["assessed"],
                    }
                },
            },
            **guide_steps(),
        },
    }


def test_a_child_case_that_isnt_supplied_is_refused() -> None:
    # The curriculum's negative test: a case references its child, never defines it, and a child
    # nobody supplied is missing, never read as one with nothing to check (brief, D74).
    issues = validate_case(parse_case(claim()), CATALOG)
    assert [(i.path, i.code, i.message) for i in issues if i.code == "UNKNOWN_CASE"] == [
        (
            "steps.repair.case",
            "UNKNOWN_CASE",
            "repair@3 isn't supplied: add it to the package's cases/",
        )
    ]


# --- Slice 2: what a case step and a report can't be, refused when read (brief, D74) ---


def test_a_case_step_has_no_approval() -> None:
    # The child's own steps carry their approvals, as a plan's do (brief, D28).
    definition = claim()
    definition["steps"]["repair"]["approval"] = copy.deepcopy(
        definition["steps"]["pay_garage"]["approval"]
    )
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == (
        "steps.repair: a case step has no approval: its child's steps ask for their own"
    )


def test_a_case_step_is_never_repeated() -> None:
    # One child per run: a deliberate limit (brief, D74), said as for a plan step (brief, D73).
    definition = claim()
    definition["steps"]["repair"]["for_each"] = {"over": "vehicle", "key": "vehicle"}
    with pytest.raises(CaseInvalid, match="^steps.repair.for_each: not a field here$"):
        parse_case(definition)


def repair() -> dict[str, Any]:
    """The guide's repair: a garage fixes the vehicle within its budget and reports the cost."""
    return {
        "case": "repair",
        "display": {"title": "Vehicle repair"},
        "fields": {
            "vehicle": {"type": "string", "display": {"title": "Vehicle"}},
            "budget": {"type": "number", "display": {"title": "Budget"}},
            "cost": {"type": "number", "display": {"title": "Cost"}},
        },
        "milestones": {"fixed": {"display": {"title": "Vehicle fixed"}}},
        "steps": {
            "fix": {
                "kind": "task",
                "display": {"title": "Fix the vehicle"},
                "roles": ["garage"],
                "outcomes": {
                    "fixed": {
                        "display": {"title": "Fixed"},
                        "sets": ["cost"],
                        "reaches": ["fixed"],
                    }
                },
            }
        },
        "reports": ["cost"],
    }


@pytest.mark.parametrize(
    ("field", "declared", "said"),
    [
        (
            None,
            None,
            "reports.mileage: repair has no field mileage: a report lists the case's own fields",
        ),
        (
            "owner",
            {"type": "string", "sensitive": True, "visible_to": ["garage"]},
            "reports.owner: owner is sensitive, and a report carries no sensitive field yet",
        ),
        (
            "parts",
            {"type": "list", "fields": {"sku": {"type": "string"}}},
            "reports.parts: parts is a list, and a report carries no list",
        ),
    ],
)
def test_a_report_carries_only_the_cases_own_plain_values(
    field: str | None, declared: dict[str, Any] | None, said: str
) -> None:
    # A report's values land as the step's outputs, each an exact value (brief, D29); a sensitive
    # one is its own door (brief, D74).
    definition = repair()
    if field is None:
        definition["reports"] = ["cost", "mileage"]
    else:
        assert declared is not None
        definition["fields"][field] = declared | {"display": {"title": field}}
        definition["reports"] = ["cost", field]
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == said
