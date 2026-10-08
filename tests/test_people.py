"""People in the loop: roles, forms and approvals (layer 7).

Tests go through the catalog, `parse_plan`, `validate` and `run_plan`, and read what a run reports.
See docs/layers/07-people.md and docs/guides/plans.md, "People in the loop".
"""

import pytest

from ventoux.core.catalog import Catalog


def test_a_role_is_written_as_a_label() -> None:
    with pytest.raises(ValueError, match="'Support Lead' is not a role: a role is lowercase"):
        Catalog().register_role("Support Lead")


def test_a_role_approves_up_to_a_risk_or_nothing() -> None:
    with pytest.raises(ValueError, match="'hihg' is not a risk: a role approves up to low, medium"):
        Catalog().register_role("support-lead", approves="hihg")


def test_the_catalog_lists_its_roles_with_what_each_may_approve() -> None:
    catalog = Catalog()
    catalog.register_role("support-lead", approves="high")
    catalog.register_role("support")
    assert catalog.roles == {"support": None, "support-lead": "high"}
