"""Audit records: each act a case decides, as data, with the decisions it caused (layer 19a).

Read field by field, never through their lines. See docs/layers/19-audit-keys.md and brief, D76.
"""

import dataclasses
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from cases.refund import refund
from test_case import REFUND, reworkable, with_check_order
from test_change_requests import FORGETTERS, OPERATING, TYPED_WRONG, account_closed
from test_change_requests import LARGE as LARGE_ORD_1
from test_change_requests import PEOPLE as CHANGERS
from test_child_cases import PEOPLE as REPAIRERS
from test_child_cases import claim as claim_with_repair
from test_child_cases import repair
from test_events import RECEIPT, waiting_for_a_receipt
from test_migrations import REFUND_1, REFUND_3, RENAMES, on_refund_1
from test_migrations import REVIEWED as REVIEWED_250
from test_plan_step import refund_order, refund_with_plan
from test_rules import DUPLICATE, WITHDRAWS, withdrawable
from test_sensitive import FILE, NATIONAL_ID, OPENING, claim, lookup
from test_set import APPROVED, with_owed
from test_set import FILE as WITH_FEE
from test_set import PEOPLE as SET_PEOPLE

from ventoux.case.admission import ProposalRefused
from ventoux.case.audit import Act, Decision, Fact
from ventoux.case.memory import CaseRun
from ventoux.case.recording import record_refused
from ventoux.case.requests import ChangeRefused
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, ChangeProposed, Proposed
from ventoux.core.sensitive import Sensitive
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.converter import ExactPayloadConverter
from ventoux.testing import (
    CATALOG,
    AnswerRefused,
    close,
    edit,
    forget,
    later,
    load_definition,
    migrate,
    propose,
    retry,
    run_case,
    shown,
    skip,
)
from ventoux.testing import (
    claim as claim_entry,
)

ROOT = Path(__file__).parent.parent
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"]}
LARGE = {"order_id": "ord-2", "amount": 250}
REVIEWED = [("review", "approve", "ana", {"approved_amount": 250})]
LATER = 1_800_000_000  # a time after the opening, in seconds since the epoch


def test_a_refused_act_is_one_record_saying_why_and_nothing_else_changes() -> None:
    run = run_case(refund, LARGE, REVIEWED, PEOPLE, engine=3)
    # Ana reviewed it, and isn't a team lead: her approval is refused (brief, D11).
    act = Answered("pay.approval#1", "approve", "ana", frozenset({"support"}), at=LATER)
    with pytest.raises(AnswerRefused) as refused:
        decide(run.definition, CATALOG, run.state, act)

    after = record_refused(run.definition, run.state, act, refused.value)

    record = after.audit[-1]
    assert record.number == len(run.state.audit) + 1
    assert record.at == LATER
    assert record.act == Act(
        "answered", by="ana", roles=("support",), entry="pay.approval#1", outcome="approve"
    )
    # The entry as it was asked: a refused act may name one that doesn't exist, so no step is
    # guessed from it.
    assert record.decisions == [
        Decision("refused", entry="pay.approval#1", reason=str(refused.value))
    ]
    line = f"refused ana's answer approve to pay.approval#1: {refused.value}"
    assert record.lines == [line]
    # Nothing else changed: the refused act is recorded, and the case waits on (brief, D76).
    assert after.history == [*run.state.history, line]
    assert after.recorded == run.state.recorded + 1  # the counter, with the record (brief, D77)
    unchanged = dataclasses.replace(
        after, audit=run.state.audit, history=run.state.history, recorded=run.state.recorded
    )
    assert unchanged == run.state
    # A refused proposal names its step: the act gives it (brief, D76).
    proposal = Proposed("pay", "sam", frozenset({"support"}), at=LATER)
    with pytest.raises(ProposalRefused) as refusal:
        decide(run.definition, CATALOG, run.state, proposal)
    after = record_refused(run.definition, run.state, proposal, refusal.value)
    assert after.audit[-1].decisions == [Decision("refused", step="pay", reason=str(refusal.value))]


def test_the_quickstarts_small_refund_records_each_act_and_what_it_decided() -> None:
    run = run_case(
        refund,
        {"order_id": "ord-1", "amount": 40},
        [("review", "approve", "ana", {"approved_amount": 40})],
        PEOPLE,
        engine=3,
    )
    opening, answer, paid = run.audit
    assert [each.number for each in run.audit] == [1, 2, 3]
    assert {(each.release, each.engine) for each in run.audit} == {(None, 3)}  # a draft
    assert opening.act == Act("opened", values={"order_id": "ord-1", "amount": Decimal(40)})
    assert opening.decisions == [
        Decision("started", step="review", entry="review#1", rule="steps.review")
    ]
    assert answer.act == Act(
        "answered",
        by="ana",
        roles=("support",),
        entry="review",
        outcome="approve",
        values={"approved_amount": Decimal(40)},
    )
    # Pay starts on what its condition, its approval's condition and its inputs read: no approval
    # was needed, since the amount is under 100, and the record says on which facts.
    assert answer.decisions == [
        Decision("answered", step="review", entry="review#1", rule="steps.review.outcomes.approve"),
        Decision(
            "started",
            step="pay",
            entry="pay#1",
            rule="steps.pay.when",
            read=(
                Fact("review.outcome", ("person:ana",), "approve"),
                Fact("approved_amount", ("person:ana",), Decimal(40)),
                Fact("order_id", ("system:opener",), "ord-1"),
            ),
        ),
    ]
    assert paid.act.kind == "completed" and paid.act.entry == "pay#1"
    assert paid.decisions == [
        Decision("completed", step="pay", entry="pay#1", rule="steps.pay"),
        Decision("closed", reason="nothing left to do"),
    ]
    # The history, line for line: each record keeps the lines its act added, and nothing else.
    assert [line for each in run.audit for line in each.lines] == run.history


def test_an_approval_that_starts_its_step_is_one_record() -> None:
    # The guide's example: Sam's approval is one act, and pay starting is what it caused.
    run = run_case(
        refund, LARGE, [*REVIEWED, ("pay.approval#1", "approve", "sam")], PEOPLE, engine=3
    )
    _, review, approval, _ = run.audit
    amount = Fact("approved_amount", ("person:ana",), Decimal(250))
    # The review's answer let pay run once a team lead approves: asked, on the amount.
    assert review.decisions[-1] == Decision(
        "admitted",
        step="pay",
        entry="pay.approval#1",
        rule="steps.pay.approval.when",
        read=(amount,),
    )
    assert approval.act == Act(
        "answered",
        by="sam",
        roles=("support", "support-lead"),
        entry="pay.approval#1",
        outcome="approve",
    )
    # What the approver saw: the approval's condition and the inputs (brief, D11).
    assert approval.decisions == [
        Decision(
            "approved",
            step="pay",
            entry="pay.approval#1",
            rule="steps.pay.approval",
            read=(amount, Fact("order_id", ("system:opener",), "ord-2")),
        ),
        Decision(
            "started",
            step="pay",
            entry="pay#1",
            rule="steps.pay.when",
            read=(
                Fact("review.outcome", ("person:ana",), "approve"),
                amount,
                Fact("order_id", ("system:opener",), "ord-2"),
            ),
        ),
    ]


def down_then_up() -> Any:
    """A payment provider that fails once, with a message quoting the order, then pays."""
    calls: list[object] = []

    def pay(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs)
        if len(calls) == 1:
            raise ConnectionError(f"provider unreachable while refunding {inputs['order_id']}")
        return {"refund_id": "ref-1"}

    return pay


def test_a_failure_is_recorded_by_its_type_and_a_retry_says_so() -> None:
    run = run_case(
        refund,
        {"order_id": "ord-1", "amount": 40},
        [("review", "approve", "ana", {"approved_amount": 40}), retry("pay#1", "omar")],
        {**PEOPLE, "omar": ["operations"]},
        activities={"payments.refund@2": down_then_up()},
        engine=3,
    )
    _, _, failure, retried, _ = run.audit
    assert failure.act == Act("failed", entry="pay#1")
    # Its type, never what it said: the message may quote anything (brief, D31) (brief, D76).
    assert failure.decisions == [
        Decision(
            "failed",
            step="pay",
            entry="pay#1",
            rule="steps.pay",
            reason="payments.refund@2 failed with ConnectionError: ‹sensitive›",
        )
    ]
    assert "provider unreachable" not in repr(run.audit)
    assert retried.act == Act("retried", by="omar", roles=("operations",), entry="pay#1")
    assert [(each.kind, each.entry) for each in retried.decisions] == [
        ("retried", "pay#1"),
        ("started", "pay#1"),
    ]


def test_a_form_value_is_recorded_as_the_case_file_keeps_it() -> None:
    # The client wraps every value of a form, since it can't tell which are sensitive; the record,
    # like the case file, keeps wrapped only the sensitive ones (brief, D31) (brief, D76).
    definition = claim()
    definition["steps"]["assess"]["outcomes"]["accept"]["sets"] = [
        "national_id",
        "estimated_damage",
    ]
    # Given plain: `run_case` plays the client, which wraps every value of the form.
    form = {"national_id": NATIONAL_ID, "estimated_damage": 900}
    opening = {name: value for name, value in OPENING.items() if name != "estimated_damage"}
    run = run_case(
        definition, opening, [("assess", "accept", "ana", form)], {"ana": ["adjuster"]}, engine=3
    )
    [answer] = [each for each in run.audit if each.act.kind == "answered"]
    assert answer.act.values == {
        "national_id": Sensitive(NATIONAL_ID),
        "estimated_damage": Decimal(900),
    }


STRAY = "17 May 1985"  # typed into a box the task doesn't have


def test_a_refused_answer_keeps_no_value_under_a_name_that_is_no_field() -> None:
    # A name the case doesn't know is never read as "not sensitive": the answer is refused, its
    # line says the name, and the value is dropped still wrapped (brief, D89).
    run = run_case(claim(), OPENING, [], {"ana": ["adjuster"]}, engine=3)
    form = {"scratch": Sensitive(STRAY)}  # wrapped, as the client sends every form value
    act = Answered("assess#1", "accept", "ana", frozenset({"adjuster"}), form, at=LATER)
    with pytest.raises(AnswerRefused) as refused:
        decide(run.definition, CATALOG, run.state, act)

    after = record_refused(run.definition, run.state, act, refused.value)

    assert str(refused.value) == "the answer gives scratch, which accept doesn't set"
    assert after.audit[-1].act.values == {}
    # Nor is it in the state the case continues as new with, which carries each record not yet
    # exported (brief, D27).
    assert STRAY not in str(state_as_data(after))


def test_a_refused_edit_keeps_no_value_under_a_name_that_is_no_field() -> None:
    # The same door, by an edit: a proposal to edit a name the case doesn't have is refused, and
    # its record holds nothing of the value (brief, D89).
    run = run_case(claim(), OPENING, [], {"ana": ["adjuster"]}, engine=3)
    roles = frozenset(CHANGERS["ana"])
    act = ChangeProposed("edit", "scratch", Sensitive(STRAY), "ana", roles, at=LATER)
    with pytest.raises(ChangeRefused) as refused:
        decide(run.definition, CATALOG, run.state, act)

    after = record_refused(run.definition, run.state, act, refused.value)

    assert str(refused.value) == "scratch is not a field of claim: only a declared field is edited"
    assert after.audit[-1].act.values == {}
    assert STRAY not in str(state_as_data(after))


def test_a_refused_answers_value_for_a_real_field_follows_that_field() -> None:
    # Only a name that is no field is dropped. A field the outcome doesn't set is still a field:
    # its value is recorded as the case file would keep it, wrapped if sensitive, plain if not
    # (brief, D76) (brief, D89).
    run = run_case(claim(), OPENING, [], {"ana": ["adjuster"]}, engine=3)
    form = {"national_id": Sensitive(NATIONAL_ID), "policy_id": Sensitive("pol-9")}
    act = Answered("assess#1", "accept", "ana", frozenset({"adjuster"}), form, at=LATER)
    with pytest.raises(AnswerRefused) as refused:
        decide(run.definition, CATALOG, run.state, act)

    after = record_refused(run.definition, run.state, act, refused.value)

    assert after.audit[-1].act.values == {
        "national_id": Sensitive(NATIONAL_ID),
        "policy_id": "pol-9",
    }


def owed_and_known() -> dict[str, Any]:
    """The refund whose rule works out what is owed, and then reaches `owed_known`."""
    definition = with_owed()
    definition["milestones"] = {"owed_known": {"display": {"title": "What is owed is known"}}}
    definition["rules"]["work_out_owed"]["then"]["reach"] = ["owed_known"]
    return definition


def test_a_rule_that_sets_and_reaches_says_what_it_wrote_on_what_it_read() -> None:
    # The rule's set and reach are decisions of the act whose moment it fired on (brief, D38).
    run = run_case(owed_and_known(), WITH_FEE, [APPROVED], SET_PEOPLE, engine=3)
    [answer] = [each for each in run.audit if each.act.kind == "answered"]
    rule = "rules.work_out_owed"
    set_, reached = [each for each in answer.decisions if each.rule == rule]
    assert set_ == Decision(
        "set",
        entry="work_out_owed#1",
        rule=rule,
        read=(
            Fact("approved_amount", ("person:ana",), Decimal(40)),
            Fact("fee", ("system:opener",), Decimal(5)),
            Fact("review.outcome", ("person:ana",), "approve"),
        ),
        wrote=Fact("owed", ("person:ana", "system:opener"), Decimal(35)),
    )
    assert reached == Decision("reached", entry="work_out_owed#1", rule=rule, target="owed_known")


def test_a_rules_stop_and_a_persons_close_say_what_they_stopped() -> None:
    # The withdrawal's answer reaches `withdrawn`, whose rule stops the waiting review (brief, D40).
    run = run_case(withdrawable(), {"order_id": "ord-1", "amount": 40}, WITHDRAWS, PEOPLE, engine=3)
    logged = run.audit[-1]
    assert [(each.kind, each.target, each.rule) for each in logged.decisions] == [
        ("answered", None, "steps.log_withdrawal.outcomes.logged"),
        ("reached", "withdrawn", "steps.log_withdrawal.outcomes.logged"),
        ("stopped", "review#1", "rules.withdraw"),
        ("closed", None, None),
    ]
    stopped = logged.decisions[2]
    assert (stopped.step, stopped.entry, stopped.reason) == (
        "review",
        "withdraw#1",
        "stopped by withdraw#1",
    )
    # Ana closes it as a duplicate while the review waits: her close stops it, then it closes.
    staying = withdrawable() | {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}
    run = run_case(
        staying, {"order_id": "ord-1", "amount": 40}, [close("duplicate", "ana")], PEOPLE, engine=3
    )
    closing = run.audit[-1]
    assert closing.act == Act("closed", by="ana", roles=("support",), outcome="duplicate")
    assert [(each.kind, each.step, each.target, each.rule) for each in closing.decisions] == [
        ("stopped", "review", "review#1", "close_reasons.duplicate"),
        ("closed", None, None, None),
    ]


def test_a_change_request_says_what_it_changed_or_why_not() -> None:
    # An edit: proposed by Ana, approved by Lee; what it wrote is both of theirs (brief, D52).
    proposed = [TYPED_WRONG, edit("approved_amount", 250, "ana")]
    edited = [*proposed, ("case.change#1", "approve", "lee")]
    run = run_case(REFUND, LARGE_ORD_1, edited, CHANGERS, engine=3)
    proposal, approval = run.audit[-2:]
    assert proposal.act == Act(
        "change proposed",
        by="ana",
        roles=("support",),
        entry="approved_amount",
        outcome="edit",
        values={"approved_amount": Decimal(250)},
    )
    assert approval.decisions[0] == Decision(
        "edited",
        entry="case.change#1",
        wrote=Fact("approved_amount", ("person:ana", "person:lee"), Decimal(250)),
    )
    # Rejected: nothing changed, and the record says who rejected it.
    rejected = [*proposed, ("case.change#1", "reject", "lee")]
    run = run_case(REFUND, LARGE_ORD_1, rejected, CHANGERS, engine=3)
    assert run.audit[-1].decisions == [
        Decision("rejected", entry="case.change#1", reason="lee rejected it")
    ]
    # Approved, but its field changed meanwhile: not applied, and refused, saying why.
    reworked = [
        *proposed,
        propose("review", "sam"),
        ("review#2", "approve", "sam", {"approved_amount": 300}),
        ("case.change#1", "approve", "lee"),
    ]
    run = run_case(reworkable(), LARGE_ORD_1, reworked, CHANGERS, engine=3)
    assert run.audit[-1].decisions == [
        Decision(
            "refused",
            entry="case.change#1",
            reason="approved_amount changed since it was proposed: propose it again",
        )
    ]
    # A skip of a failed run, approved by another operator.
    skipped = [
        ("review", "approve", "ana", {"approved_amount": 40}),
        skip("pay#1", "omar"),
        ("case.change#1", "approve", "olga"),
    ]
    run = run_case(
        REFUND,
        {"order_id": "ord-1", "amount": 40},
        skipped,
        OPERATING,
        activities={"payments.refund@2": account_closed},
        engine=3,
    )
    [skipping] = [
        each for each in run.audit if each.act.entry == "case.change#1" and each.act.by == "olga"
    ]
    assert skipping.decisions[0] == Decision(
        "skipped", step="pay", entry="case.change#1", target="pay#1"
    )


def test_a_case_before_engine_3_records_nothing_until_it_migrates_to_it() -> None:
    # Opened at engine 2, it decides and replays as it always did, and makes no record.
    run = on_refund_1([REVIEWED_250], engine=2)
    assert run.audit == [] and run.state.engine == 2
    # Moved to engine 3 by a migration: its records start with the act that moved it, saying what
    # came before wasn't recorded; never a partial trail passed off as whole (brief, D76).
    moved = on_refund_1(
        [REVIEWED_250, migrate(REFUND_1, {}, "pia", 3), ("case.change#1", "approve", "lee")],
        engine=2,
    )
    [first] = moved.audit
    assert (first.number, first.engine, first.release) == (1, 3, "refund 1")
    assert first.act == Act(
        "answered",
        by="lee",
        roles=("platform", "support-lead"),
        entry="case.change#1",
        outcome="approve",
    )
    assert first.decisions[0] == Decision(
        "migrated",
        entry="case.change#1",
        target="refund 1",
        reason="what came before engine 3 was not recorded",
    )


def test_forgetting_approved_is_recorded_with_both_people() -> None:
    run = run_case(claim(), FILE, [forget("pia", "olu")], FORGETTERS, engine=3)
    forgetting = run.audit[-1]
    assert forgetting.act == Act("forget approved", by="olu", roles=("privacy",))
    assert [(each.kind, each.reason) for each in forgetting.decisions] == [
        ("forgotten", "proposed by pia as privacy, approved by olu as privacy"),
        ("stopped", "the case is being forgotten"),
        ("closed", "forgotten"),
    ]


def test_a_child_case_is_started_and_read_by_its_parent_and_records_its_own() -> None:
    # The guide's claim and its repair: the parent records the child's start and its end as its
    # own decisions; the child, a case of its own, records its own acts (brief, D74).
    run = run_case(
        claim_with_repair(),
        {"order_id": "ord-1", "vehicle": "veh-9"},
        [("assess", "accept", "ana", {"payout": 900})],
        REPAIRERS,
        cases={"repair@3": repair()},
        case_answers={"repair": [("fix", "fixed", "lee", {"cost": 640})]},
        engine=3,
    )
    parent = [(d.kind, d.entry) for each in run.audit for d in each.decisions]
    assert ("started", "repair#1") in parent and ("completed", "repair#1") in parent
    ended = next(each for each in run.audit if each.act.kind == "child ended")
    assert ended.act.values["cost"] == Decimal(640)
    child = run.children["repair#1"].audit
    assert child[0].act.kind == "opened" and child[-1].decisions[-1].kind == "closed"


def test_an_event_and_a_claim_are_acts_with_what_they_caused() -> None:
    # The receipt the wait waits for arrives: the wait is done, and pay starts (brief, D41).
    script = [
        claim_entry("review#1", "ana"),
        ("review", "approve", "ana", {"approved_amount": 40}),
        RECEIPT,
    ]
    run = run_case(
        waiting_for_a_receipt(), {"order_id": "ord-1", "amount": 40}, script, PEOPLE, engine=2
    )
    assert run.audit == []  # engine 2: nothing recorded
    run = run_case(
        waiting_for_a_receipt(), {"order_id": "ord-1", "amount": 40}, script, PEOPLE, engine=3
    )
    claimed = run.audit[1]
    # A claim decides nothing about the case: the act, and its line (brief, D69).
    assert claimed.act == Act("claimed", by="ana", roles=("support",), entry="review#1")
    assert claimed.decisions == [] and claimed.lines != []
    receipt = run.audit[3]
    assert receipt.act == Act(
        "event", by="system:portal", entry="receipt_sent", values={"receipt": "doc-7"}
    )
    assert [(each.kind, each.entry, each.rule) for each in receipt.decisions] == [
        ("completed", "wait_for_receipt#1", "steps.wait_for_receipt"),
        ("started", "pay#1", "steps.pay.when"),
    ]


def test_a_timer_a_plan_a_proposal_and_a_record_shown_are_each_recorded() -> None:
    # A timer: two days after the review started, its rule starts the chase (brief, D44).
    chased = load_definition(ROOT / "examples" / "refund" / "refund-chased.json")
    run = run_case(chased, {"order_id": "ord-1", "amount": 40}, [later("3d")], PEOPLE, engine=3)
    timer = next(each for each in run.audit if each.act.kind == "timer")
    assert timer.act == Act("timer", entry="chase_review")
    assert [(each.kind, each.entry, each.rule) for each in timer.decisions] == [
        ("started", "chase#1", "rules.chase_review")
    ]
    # A plan step: started on its inputs, completed when its plan ends (brief, D28).
    run = run_case(
        refund_with_plan(),
        {"order_id": "ord-1", "amount": 250},
        [("review", "approve", "ana", {"approved_amount": 250})],
        PEOPLE,
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "approve", "sam")]},
        engine=3,
    )
    decided = [(d.kind, d.entry) for each in run.audit for d in each.decisions]
    assert ("started", "settle#1") in decided and ("completed", "settle#1") in decided
    # A person's proposal, which admission starts at once, while the payment waits for a team
    # lead (brief, D61).
    run = run_case(
        with_check_order(),
        LARGE,
        [*REVIEWED, propose("check_order", "ana")],
        PEOPLE,
        engine=3,
    )
    proposal = next(each for each in run.audit if each.act.kind == "proposed")
    assert proposal.act == Act("proposed", by="ana", roles=("support",), entry="check_order")
    assert (proposal.decisions[0].kind, proposal.decisions[0].entry) == ("started", "check_order#1")
    # A record shown decides nothing: the act and its line (brief, D16).
    run = run_case(claim(), FILE, [shown("customer_id", "ana")], {"ana": ["adjuster"]}, engine=3)
    showing = run.audit[-1]
    assert showing.act == Act("shown", by="ana", roles=("adjuster",), entry="customer_id")
    assert showing.decisions == []


def known(inputs: dict[str, Any]) -> dict[str, Any]:
    """The orders system, which knows every order: a stand-in for any activity."""
    return {"status": "known"}


def checked_claim() -> dict[str, Any]:
    """The case data guide's claim, with a step whose condition reads the national ID, and whose
    input is computed from it."""
    definition = claim()
    definition["steps"]["check"] = lookup(
        {"cat": ["id:", {"var": "national_id"}]},
        when={"==": [{"var": "national_id"}, NATIONAL_ID]},
    )
    return definition


def test_a_sensitive_value_is_never_unwrapped_in_a_record() -> None:
    run = run_case(
        checked_claim(),
        FILE,
        [],
        {"ana": ["adjuster"]},
        activities={"orders.lookup@1": known},
        engine=3,
    )
    opening = run.audit[0]
    assert opening.act.values["national_id"] == Sensitive(NATIONAL_ID)
    [started] = [
        decision
        for each in run.audit
        for decision in each.decisions
        if decision.kind == "started" and decision.step == "check"
    ]
    assert {fact.field: fact.value for fact in started.read}["national_id"] == (
        Sensitive(NATIONAL_ID)
    )
    # Nowhere in any record in clear: a record keeps it wrapped, as the state does (brief, D31).
    assert NATIONAL_ID not in repr(run.audit)


def test_records_cross_continue_as_new_as_they_were() -> None:
    # Records not yet exported cross with the rest of the state, through the same converter: a
    # sensitive value stays wrapped, an amount stays an exact decimal (brief, D27, as amended by
    # D76).
    run = run_case(
        checked_claim(),
        FILE,
        [],
        {"ana": ["adjuster"]},
        activities={"orders.lookup@1": known},
        engine=3,
    )
    types = {name: field.declared for name, field in run.definition.fields.items()}
    payload = ExactPayloadConverter().to_payload(state_as_data(run.state))
    assert payload is not None
    back = state_from_data(ExactPayloadConverter().from_payload(payload, dict), types)
    assert back.audit == run.state.audit != []
    assert back.audit[0].act.values["national_id"] == Sensitive(NATIONAL_ID)
    # What a rule wrote and the milestone it reached cross too.
    run = run_case(owed_and_known(), WITH_FEE, [APPROVED], SET_PEOPLE, engine=3)
    types = {name: field.declared for name, field in run.definition.fields.items()}
    payload = ExactPayloadConverter().to_payload(state_as_data(run.state))
    assert payload is not None
    back = state_from_data(ExactPayloadConverter().from_payload(payload, dict), types)
    assert back.audit == run.state.audit
    assert any(each.wrote and each.target is None for r in back.audit for each in r.decisions)
    assert any(each.target == "owed_known" for r in back.audit for each in r.decisions)


REVIEWED_40 = [("review", "approve", "ana", {"approved_amount": 40})]


def test_records_keep_the_names_a_migration_later_changes() -> None:
    # A record is what happened, under the names the case had then: a migration renaming pay to
    # payment changes the case, never the records before it (brief, D53) (brief, D76).
    paid = on_refund_1(
        [
            REVIEWED_250,
            migrate(REFUND_3, RENAMES, "pia", 3),
            ("case.change#1", "approve", "lee"),
            ("fraud_check", "clear", "fay"),
            ("payment.approval#2", "approve", "sam"),
        ],
        engine=3,
    )
    review = paid.audit[1]
    assert review.decisions[-1].step == "pay"  # its approval asked, as pay
    assert review.act.values == {"approved_amount": Decimal(250)}
    approval = next(each for each in paid.audit if each.act.entry == "payment.approval#2")
    assert [(d.kind, d.step) for d in approval.decisions][:2] == [
        ("approved", "payment"),
        ("started", "payment"),
    ]
    assert approval.decisions[0].read[0].field == "amount_approved"


# Each route's scenario, at engine 3: what the other tests here run.
SCENARIOS: dict[str, Callable[[], CaseRun]] = {
    "the small refund": lambda: run_case(
        refund, {"order_id": "ord-1", "amount": 40}, REVIEWED_40, PEOPLE, engine=3
    ),
    "an approval": lambda: run_case(
        refund, LARGE, [*REVIEWED, ("pay.approval#1", "approve", "sam")], PEOPLE, engine=3
    ),
    "a rule's set and reach": lambda: run_case(
        owed_and_known(), WITH_FEE, [APPROVED], SET_PEOPLE, engine=3
    ),
    "a stop": lambda: run_case(
        withdrawable(), {"order_id": "ord-1", "amount": 40}, WITHDRAWS, PEOPLE, engine=3
    ),
    "an edit": lambda: run_case(
        REFUND,
        LARGE_ORD_1,
        [TYPED_WRONG, edit("approved_amount", 250, "ana"), ("case.change#1", "approve", "lee")],
        CHANGERS,
        engine=3,
    ),
    "forgetting": lambda: run_case(claim(), FILE, [forget("pia", "olu")], FORGETTERS, engine=3),
    "an event": lambda: run_case(
        waiting_for_a_receipt(),
        {"order_id": "ord-1", "amount": 40},
        [*REVIEWED_40, RECEIPT],
        PEOPLE,
        engine=3,
    ),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_each_record_keeps_exactly_the_lines_its_act_added(scenario: str) -> None:
    # Numbered from 1 with no gap, and the history, line for line: no act left out, and no
    # line in two records (brief, D76).
    run = SCENARIOS[scenario]()
    assert [each.number for each in run.audit] == list(range(1, len(run.audit) + 1))
    assert [line for each in run.audit for line in each.lines] == run.history
