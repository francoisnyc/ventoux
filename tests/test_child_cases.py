"""Layer 18c: child cases. A case step opens a whole case, pinned by its parent's release, given
its opening from the parent's case file, and reporting back as the step's outputs (brief, D74).

See docs/layers/18-lifecycle.md (18c) and docs/guides/cases.md, "Child cases".
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from ventoux.case.definition import parse_case
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
