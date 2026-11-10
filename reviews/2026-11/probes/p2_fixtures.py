# Shared table for the p2_* probes: every recorded history under tests/histories, with the workflow ID, workflow class and converter its own test replays it with.
"""Not a probe itself. Reaches past the supported names for the tests' own workflow classes (each
fixture replays only against the class that recorded it), imported from the test modules."""

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "examples" / "quickstart"))
HERE = ROOT / "tests" / "histories"

import test_audit_export  # noqa: E402
import test_temporal_approvals  # noqa: E402
import test_temporal_case  # noqa: E402
import test_temporal_case_release  # noqa: E402
import test_temporal_change_requests  # noqa: E402
import test_temporal_children  # noqa: E402
import test_temporal_migrations  # noqa: E402
import test_temporal_registry  # noqa: E402
import test_temporal_workflow_step  # noqa: E402
from temporalio.client import WorkflowHistory  # noqa: E402

from ventoux.testing import (  # noqa: E402
    DevelopmentCases,
    DevelopmentForget,
    development_converter,
    fixture_converter,
)

# name -> (workflow ID, workflow class, whether its test expects the replay to be refused)
FIXTURES: dict[str, tuple[str, type[Any], bool]] = {
    "before_11b_proposal": ("refund-1", DevelopmentCases, False),
    "before_11c_plan_closed": ("refund-1", test_temporal_case.CasesWithPlans, False),
    "before_11c_workflow_closed": ("refund-1", test_temporal_workflow_step.CasesWithKyc, False),
    "before_11c_workflow_cancelled_outside": (
        "refund-1", test_temporal_workflow_step.CasesWithKyc, False),
    "before_11f_refund": ("refund-1", DevelopmentCases, False),
    "before_11f_switched": ("refund-1", DevelopmentCases, False),
    "before_11h2_approved": ("refund-1", DevelopmentCases, False),
    "before_11h2_switched": ("refund-1", DevelopmentCases, False),
    "before_fix_retry_rejected": ("refund-1", DevelopmentCases, False),
    "before_fix_retry_rejected_retried": ("refund-1", DevelopmentCases, False),
    "before_fix_retry_rejected_unapproved": ("refund-1", DevelopmentCases, True),
    "before_fix_untrusted_moment_set": ("refund-1", DevelopmentCases, False),
    "before_fix_untrusted_moment_closed": ("refund-1", DevelopmentCases, True),
    "before_12c_forget_request": ("claim-7/forget", DevelopmentForget, False),
}
for name, cases in test_temporal_case_release.BEFORE_12B.items():
    FIXTURES[name] = ("refund-1", cases, False)
for name, (id, cases) in test_temporal_change_requests.BEFORE_12C.items():
    FIXTURES[name] = (id, cases, False)
for name, cases in test_temporal_migrations.BEFORE_12D.items():
    FIXTURES[name] = ("refund-1", cases, False)
for name, cases in test_temporal_registry.BEFORE_12E.items():
    FIXTURES[name] = ("refund-1", cases, False)
for name, (id, cases) in test_temporal_children.BEFORE_18D.items():
    FIXTURES[name] = (id, cases, False)
for name, (id, cases) in test_audit_export.AT_19B.items():
    FIXTURES[name] = (id, cases, False)

assert test_temporal_approvals  # imported so its workflow classes are the tests' own


def load(name: str) -> tuple[WorkflowHistory, list[type[Any]], Any]:
    """The history, the workflow class to replay it with, and the converter holding its keys."""
    id, cases, _ = FIXTURES[name]
    path = HERE / f"{name}.json"
    has_keys = path.with_suffix(".keys.json").exists()
    converter = fixture_converter(path) if has_keys else development_converter()
    return WorkflowHistory.from_json(id, path.read_text()), [cases], converter


def every_history_file() -> list[str]:
    return sorted(p.stem for p in HERE.glob("*.json") if not p.name.endswith(".keys.json"))
