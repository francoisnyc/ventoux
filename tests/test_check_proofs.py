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
from test_patterns import closed_first
from test_timers import PEOPLE, SMALL
from test_untrusted_moment import cancelled

from ventoux.case.definition import parse_case
from ventoux.case.memory import CaseRun
from ventoux.case.validate import validate_case
from ventoux.core.validate import Issue
from ventoux.testing import CATALOG, run_case

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


# --- 2. A start on the moment a rule always closes the case is refused every time ---

SAY_GOODBYE = closed_first()["rules"]["say_goodbye"]
WITHDRAW = closed_first()["rules"]["withdraw"]


def goodbye_first(
    say_goodbye: dict[str, Any] | None = None, withdraw: dict[str, Any] | None = None
) -> dict[str, Any]:
    """11h's probe C5, its rules the other way round: on `cancelled`, `say_goodbye` starts the
    goodbye call, then `withdraw` reaches `withdrawn`, which closes the case. Each is changed by
    what is given."""
    definition = closed_first()
    definition["rules"] = {
        "say_goodbye": SAY_GOODBYE | (say_goodbye or {}),
        "withdraw": WITHDRAW | (withdraw or {}),
    }
    definition["fields"]["note_seen"] = {"type": "string", "display": {"title": "Note seen"}}
    return definition


def issues(definition: dict[str, Any]) -> list[Issue]:
    return validate_case(parse_case(definition), CATALOG)


def cancelling(definition: dict[str, Any]) -> CaseRun:
    return run_case(definition, file=SMALL, answers=[cancelled("anything")], people=PEOPLE)


NOTHING_NEW = "so refund closes and nothing new starts: start it on another moment"


def test_a_start_on_the_moment_a_rule_always_closes_never_starts() -> None:
    # Its start is a proposal, decided after the moment's rules, when the case is closing.
    assert issues(goodbye_first()) == [
        Issue(
            "rules.say_goodbye.then.start",
            "NEVER_STARTS",
            "say_goodbye can never start goodbye: it fires on event cancelled, where withdraw "
            f"always reaches withdrawn, {NOTHING_NEW}",
        )
    ]
    run = cancelling(goodbye_first())
    assert (
        "say_goodbye#1 on event cancelled: goodbye not started: withdrawn is reached, so the case "
        "closes and nothing new starts"
    ) in run.history
    assert run.closed
    # The closing rule's own start too: in one `then`, the reach acts before the start.
    itself = goodbye_first()
    itself["rules"] = {
        "withdraw": WITHDRAW | {"then": {"reach": ["withdrawn"], "start": ["goodbye"]}}
    }
    assert issues(itself) == [
        Issue(
            "rules.withdraw.then.start",
            "NEVER_STARTS",
            "withdraw can never start goodbye: it fires on event cancelled and always reaches "
            f"withdrawn, {NOTHING_NEW}",
        )
    ]
    assert (
        "withdraw#1 on event cancelled: goodbye not started: withdrawn is reached, so the case "
        "closes and nothing new starts"
    ) in cancelling(itself).history
    # Whatever the starting rule's own condition and sets: false, it starts nothing; true, the
    # start is refused; unreadable, its retry comes once the case is closing.
    for own in (
        {"when": {"==": [{"var": "cancelled.note"}, "anything"]}},
        {"then": {"start": ["goodbye"], "set": {"note_seen": {"var": "cancelled.note"}}}},
    ):
        assert [i.code for i in issues(goodbye_first(say_goodbye=own))] == ["NEVER_STARTS"], own
        run = cancelling(goodbye_first(say_goodbye=own))
        assert not [line for line in run.history if line.startswith("scheduled goodbye")], own


def test_a_step_only_such_a_start_starts_never_runs() -> None:
    # Before the fix the check counted say_goodbye as able to start goodbye, wherever it was
    # written, so a step nobody else starts was silent.
    before = goodbye_first()
    del before["steps"]["goodbye"]["proposed_by"]
    after = closed_first()  # 11h1's form: say_goodbye written after withdraw
    del after["steps"]["goodbye"]["proposed_by"]
    never_runs = Issue(
        "steps.goodbye",
        "NEVER_RUNS",
        "goodbye can never run: it starts only when a rule starts it, and say_goodbye can never "
        "start it: fix say_goodbye first",
    )
    # One cause, both issues, as 11b decided: the rule's own, and the step's pointing at it.
    assert [i.code for i in issues(before)] == ["NEVER_RUNS", "NEVER_STARTS"]
    assert never_runs in issues(before)
    # After withdraw, say_goodbye never acts at all: `NEVER_FIRES` says why, not `NEVER_STARTS`.
    assert [i.code for i in issues(after)] == ["NEVER_RUNS", "NEVER_FIRES"]
    assert never_runs in issues(after)
    for definition in (before, after):
        run = cancelling(definition)
        assert not [line for line in run.history if line.startswith("scheduled goodbye")]
        assert run.closed


def test_a_start_where_the_closing_rule_may_not_close_isnt_claimed() -> None:
    # Claimed only where the closing rule always closes, as 11h1 scoped `NEVER_FIRES`.
    for withdraw in (
        # A condition may be false: here the customer's note isn't "never".
        {"when": {"==": [{"var": "cancelled.note"}, "never"]}},
        # A value it sets may fail to be read, and then nothing in its `then` acts.
        {"then": {"reach": ["withdrawn"], "set": {"note_seen": {"var": "cancelled.note"}}}},
    ):
        definition = goodbye_first(withdraw=withdraw)
        assert not [i for i in issues(definition) if i.code in ("NEVER_STARTS", "NEVER_RUNS")]
    run = cancelling(goodbye_first(withdraw={"when": {"==": [{"var": "cancelled.note"}, "never"]}}))
    assert "say_goodbye#1 on event cancelled: starting goodbye" in run.history
    # Nor on a step's start, which untrusted data may steer: then the closing rule reaches
    # nothing, and the start goes through (brief, D43). Here the customer's note starts review_it.
    steered = goodbye_first(
        say_goodbye={"on": {"started": "review_it"}},
        withdraw={"on": {"started": "review_it"}},
    )
    steered["steps"]["review_it"] = steered["steps"]["goodbye"] | {"proposed_by": []}
    steered["rules"]["start_review_it"] = SAY_GOODBYE | {
        "when": {"!=": [{"var": "cancelled.note"}, ""]},
        "then": {"start": ["review_it"]},
    }
    assert not [i for i in issues(steered) if i.code in ("NEVER_STARTS", "NEVER_RUNS")]
    run = cancelling(steered)
    assert not run.reached("withdrawn")
    assert "say_goodbye#1 on started review_it: starting goodbye" in run.history
