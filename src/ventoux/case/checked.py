"""The check a package passes before it is released: every issue of its plans and its case.

One function, which `ventoux release`, CI's summary, `ventoux check` and the authoring loop all
check with, never a copy of it (brief, D50) (brief, D63). Pure, so `authoring` can reach it.
"""

import json
from decimal import Decimal
from typing import Any

from ventoux.case.releases import Package
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.validate import Issue, validate


def issues_of(released: Package, catalog: Catalog) -> list[Issue]:
    """Every issue in the package: each plan's (layer 3), then the case's (layer 10), against
    `catalog`. What `ventoux release` refuses on, what CI's summary says before merge, and what
    the authoring loop checks each draft with: one function, never a copy (brief, D50)
    (brief, D63)."""
    stored: dict[str, Any] = {
        reference: json.loads(text, parse_float=Decimal)
        for reference, text in released.written.plans.items()
    }
    issues = [
        Issue(f"plans.{reference}.{issue.path}", issue.code, issue.message, issue.severity)
        for reference, plan in released.plans.items()
        for issue in validate(plan, catalog)
    ]
    issues += validate_case(released.case, catalog, stored)
    return issues


def is_error(issue: Issue) -> bool:
    """Whether `issue` refuses the package: anything but a warning (fail closed)."""
    return issue.severity != "warning"


def said(issue: Issue) -> str:
    """An issue as a line: `steps.pay.when: EXPRESSION_INVALID: …`."""
    return f"{issue.path}: {issue.code}: {issue.message}"
