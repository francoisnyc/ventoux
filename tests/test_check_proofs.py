"""Case validation as a proof: an error claims only what holds in every case, and what holds in
every case is said (brief, D34). Two fixes, each shown with a run.

Tests go through `parse_case`, `validate_case` and `run_case`. See
docs/layers/fix-check-proofs.md.
"""

from typing import Any

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_case_validation import (
    ACCEPTED,
    CLAIM_FILE,
    CLAIM_PEOPLE,
    StatusInput,
    guide_json,
    with_ledger,
)

from ventoux.case.definition import parse_case
from ventoux.case.memory import CaseRun
from ventoux.case.validate import validate_case
from ventoux.core.validate import Issue
from ventoux.testing import run_case

# --- 1. A rule's write with no mark comes from what the rule read, and nothing more ---

LEDGER = with_ledger(taking=StatusInput)  # `status` only from kyc


def keeping_status(value: dict[str, Any], mark: str | None = None) -> dict[str, Any]:
    """The claims guide's case: once the customer is checked, `keep_status` sets `kyc_status`
    (marked `mark`, or not at all) to `value`, and `record` sends it where only kyc's is taken."""
    claim = guide_json(0)
    claim["fields"]["kyc_status"] = {"type": "string", "display": {"title": "KYC status"}}
    if mark is not None:
        claim["fields"]["kyc_status"]["source"] = mark
    claim["rules"] = {
        "keep_status": {
            "display": {"title": "Keep what KYC said"},
            "on": {"reached": "checked"},
            "then": {"set": {"kyc_status": value}, "reach": ["status_kept"]},
        }
    }
    # `record` waits for what only `keep_status` reaches, so kyc_status is surely set.
    claim["milestones"]["status_kept"] = {"display": {"title": "KYC status kept"}}
    claim["steps"]["record"] = {
        "kind": "activity",
        "display": {"title": "Record the check"},
        "activity": "ledger.record@1",
        "requires": ["status_kept", "assessed"],
        "inputs": {"amount": {"var": "payout"}, "status": {"var": "kyc_status"}},
    }
    return claim


def recorded(definition: dict[str, Any]) -> CaseRun:
    return run_case(
        definition,
        file=CLAIM_FILE,
        answers=[ACCEPTED],
        people=CLAIM_PEOPLE,
        catalog=LEDGER,
        activities={"ledger.record@1": lambda inputs: {"entry_id": "led-1"}},
    )


def test_a_rules_write_with_no_mark_isnt_refused_for_coming_from_nothing() -> None:
    # On main, the check claimed `record` refused every time, yet the run sent kyc's status.
    definition = keeping_status({"var": "check.status"})
    assert validate_case(parse_case(definition), LEDGER) == []
    run = recorded(definition)
    assert "keep_status#1 on reached checked: setting kyc_status, from system:kyc" in run.history
    assert (
        "scheduled record#1: ledger.record@1 (amount from person:ana; status from system:kyc)"
        in run.history
    )
    assert run.needs_attention == []


def test_a_rules_write_refused_by_what_it_read_or_its_mark_is_still_claimed() -> None:
    # The workflow's outcome comes from the contract, not from kyc (brief, D29): refused.
    by_what_it_read = keeping_status({"var": "check.outcome"})
    reason = (
        "ledger.record@1 takes status only from kyc, and this value comes from kyc_status "
        "(system:kyc.check@1)"
    )
    assert validate_case(parse_case(by_what_it_read), LEDGER) == [
        Issue("steps.record.inputs.status", "INPUT_POLICY", f"{reason}: use a value kyc gave")
    ]
    assert recorded(by_what_it_read).needs_attention == [f"record#1: {reason}"]
    # A mark adds its source whoever writes the field (brief, D12): refused too.
    by_its_mark = keeping_status({"var": "check.status"}, mark="untrusted:customer")
    reason = (
        "ledger.record@1 takes status only from kyc, and this value comes from kyc_status "
        "(system:kyc, untrusted:customer)"
    )
    assert validate_case(parse_case(by_its_mark), LEDGER) == [
        Issue("steps.record.inputs.status", "INPUT_POLICY", f"{reason}: use a value kyc gave")
    ]
    assert recorded(by_its_mark).needs_attention == [f"record#1: {reason}"]
