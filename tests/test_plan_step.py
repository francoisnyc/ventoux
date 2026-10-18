"""Layer 8c, slice 1: a plan step runs a plan as one step of a case, in memory (brief, D28).

Tests go through `parse_case` and `run_case`, and read what a run reports.
See docs/layers/08-case.md (8c) and docs/guides/cases.md, "Plan steps".
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseState, Completed, Opened, StartPlan
from ventoux.testing import CATALOG, FAKES, START, close, load_definition, propose, retry, run_case

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")

PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"]}
LARGE = {"order_id": "ord-1", "amount": 250}
LARGE_EXACT = {"order_id": "ord-1", "amount": Decimal(250)}  # as the API passes it on
REVIEWED = ("review", "approve", "ana", {"approved_amount": 250})

PLANS_GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "plans.md"


def refund_order() -> dict[str, Any]:
    """The plans guide's `refund-order` plan, its first JSON block, as stored data."""
    example = PLANS_GUIDE.read_text().split("```json\n")[1].split("```")[0]
    plan: dict[str, Any] = json.loads(example, parse_float=Decimal)
    return plan


# The guide's plan step: the refund paid through the plans guide's `refund-order` plan.
SETTLE: dict[str, Any] = {
    "kind": "plan",
    "display": {"title": "Settle the refund"},
    "plan": "refund-order@1",
    "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
    "requires": ["review"],
    "when": {"==": [{"var": "review.outcome"}, "approve"]},
}


def refund_with_plan(**settle: Any) -> dict[str, Any]:
    """The quickstart's refund, `pay` and `call_customer` replaced by the guide's plan step, with `settle` changed."""
    definition = copy.deepcopy(REFUND)
    del definition["steps"]["pay"], definition["steps"]["call_customer"], definition["sequence"]
    definition["steps"]["settle"] = {**copy.deepcopy(SETTLE), **settle}
    return definition


def test_a_plan_step_is_read_with_its_shape_checked() -> None:
    # The plan carries its own approvals, checked when it is read (layer 3): no second kind here.
    approval = {"roles": ["support-lead"], "display": {"reason": "Refunds need a team lead"}}
    with pytest.raises(
        CaseInvalid,
        match="^steps.settle: a plan step has no approval: its plan asks for its own$",
    ):
        parse_case(refund_with_plan(approval=approval))
    unnamed = refund_with_plan()
    del unnamed["steps"]["settle"]["plan"]
    with pytest.raises(CaseInvalid, match="^steps.settle.plan: required$"):
        parse_case(unnamed)
    with pytest.raises(
        CaseInvalid,
        match='^steps.settle.plan: a plan reference looks like "refund-order@1"$',
    ):
        parse_case(refund_with_plan(plan="refund-order"))
    assert "settle" in parse_case(refund_with_plan()).steps


def test_a_plan_the_deployment_lacks_fails_the_step() -> None:
    # Fail closed: a plan nobody supplied never runs as something else; a person looks at it.
    run = run_case(refund_with_plan(), file=LARGE, answers=[REVIEWED], people=PEOPLE, plans={})
    assert run.needs_attention == ["settle#1: no plan refund-order@1 is available"]
    assert not run.closed


def test_a_plan_that_stops_fails_the_step() -> None:
    # The plan pays straight after its lookup: no approval, so the engine stops it before the
    # refund, and the case's step fails, waiting for a person (brief, D17).
    unapproved = refund_order()
    unapproved["states"]["check_order"]["on"]["done"] = "pay"
    run = run_case(
        refund_with_plan(),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        plans={"refund-order@1": unapproved},
    )
    assert run.needs_attention == [
        (
            "settle#1: refund-order@1 stopped: payments.refund@2 is high risk, and nobody "
            "approved this run of pay"
        )
    ]
    assert not run.closed


def proposed_settle() -> dict[str, Any]:
    """The refund with the plan step, which a team lead proposes; it stays open until closed."""
    definition = refund_with_plan(automatic=False, proposed_by=["support-lead"])
    reason = {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    return definition | {"stays_open": True, "close_reasons": {"duplicate": reason}}


def test_who_may_not_approve_crosses_into_the_plan() -> None:
    # Sam proposes settling the refund; nothing he gave flows into it (Ana's review set the
    # amount), so only D25's rule keeps him from approving his own proposal inside the plan. A
    # plan step is no way around it: his approval is refused, and nothing is paid.
    paid: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paid.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    def settled(approver: str, opened_by: str | None = None) -> bool:
        paid.clear()
        run = run_case(
            proposed_settle(),
            file=LARGE,
            answers=[REVIEWED, propose("settle", "sam")],
            people=PEOPLE,
            opened_by=opened_by,
            activities={"payments.refund@2": refund},
            plans={"refund-order@1": refund_order()},
            plan_answers={"settle": [("approve_refund", "approve", approver)]},
        )
        return run.reached("settle") and paid == ["memory/settle#1/pay#1"]

    assert not settled("sam")
    assert paid == []
    assert settled("lee")  # someone else approves it
    # The opener too (brief, D25): Lee opened the case, so Lee approves nothing in it.
    assert not settled("lee", opened_by="lee")


def test_a_plan_supplied_under_another_reference_fails_the_step() -> None:
    # Fail closed: the case references refund-order@1, and runs that plan or nothing.
    other = refund_order() | {"version": 2}
    run = run_case(
        refund_with_plan(),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        plans={"refund-order@1": other},
    )
    assert run.needs_attention == [
        "settle#1: refund-order@1 is supplied as refund-order@2: supply the plan it names"
    ]


def test_a_plan_steps_inputs_keep_their_sources() -> None:
    # The amount a customer typed is marked untrusted in the case file; paid through the plan,
    # it is still refused at payments.refund@2, which takes an amount only from a system or a
    # person (brief, D12, D21): the plan's check sees the real source, not "the case".
    definition = refund_with_plan(
        inputs={"order_id": {"var": "order_id"}, "amount": {"var": "amount"}}
    )
    definition["fields"]["amount"]["source"] = "untrusted:customer"
    run = run_case(
        definition,
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "approve", "sam")]},
    )
    [attention] = run.needs_attention
    assert attention.startswith("settle#1: refund-order@1 stopped: payments.refund@2 takes amount")
    assert "untrusted:customer" in attention
    assert (
        "started settle#1: plan refund-order@1 (order_id from system:opener; amount from "
        "system:opener, untrusted:customer), run memory/settle#1"
    ) in run.history


def test_a_plan_steps_keys_name_its_step_run() -> None:
    keys: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        return {"refund_id": "refund-ord-1"}

    run = run_case(
        refund_with_plan(),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        activities={"payments.refund@2": refund},
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "approve", "sam")]},
    )
    # The case's key for the step run, then the plan's own (brief, D28).
    assert keys == ["memory/settle#1/pay#1"]
    assert run.reached("settle")
    assert run.history[-3:] == [
        (
            "started settle#1: plan refund-order@1 (order_id from system:opener; amount from "
            "person:ana), run memory/settle#1"
        ),
        "settle#1 done",
        "closed: nothing left to do",
    ]


def test_how_a_plan_ends_is_how_its_step_ends() -> None:
    # Sam rejects the refund inside the plan: it ends in its failed final state. That is an
    # outcome of the step, which a step can react to, never a failure needing attention.
    rejected = run_case(
        refund_with_plan(),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "reject", "sam")]},
    )
    assert "settle#1 gave failed" in rejected.history
    assert rejected.needs_attention == []
    assert rejected.closed
    # Nobody answers the plan's wait: it waits, the step runs on, and the case stays open.
    waiting = run_case(
        refund_with_plan(),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        plans={"refund-order@1": refund_order()},
    )
    assert waiting.status == "open"
    assert not waiting.reached("settle")


def test_a_plan_ends_done_or_failed_and_nothing_else() -> None:
    # Fail closed: a plan step can't "complete" with an outcome no plan gives; it fails instead.
    case = parse_case(refund_with_plan())
    state, _ = decide(case, CATALOG, CaseState("memory"), Opened(LARGE_EXACT, None, at=START))
    form = {"approved_amount": Decimal(250)}
    review = Answered("review#1", "approve", "ana", frozenset({"support"}), form, at=START)
    state, commands = decide(case, CATALOG, state, review)
    assert [type(command) for command in commands] == [StartPlan]
    state, _ = decide(case, CATALOG, state, Completed("settle#1", {}, "declined", at=START))
    assert state.history[-1] == (
        "settle#1 failed: refund-order@1 ended with declined: a plan ends done or failed"
    )


# --- Tutor review: closing a case stops its plan steps ---

DUPLICATE = {"display": {"title": "Duplicate request"}, "roles": ["support"]}


def test_closing_a_case_ends_its_waiting_plan_step() -> None:
    # The plan waits for a team lead's approval when Ana closes the case as a duplicate. The
    # plan's open wait is cancelled, the plan ends, its step run is cancelled because the case is
    # closing, and the case closes: never "closing" forever, waiting on a decision nobody sees
    # (brief, D10, D28).
    run = run_case(
        refund_with_plan() | {"close_reasons": {"duplicate": DUPLICATE}},
        file=LARGE,
        answers=[REVIEWED, close("duplicate", "ana")],
        people=PEOPLE,
        plans={"refund-order@1": refund_order()},
    )
    assert run.status == "closed"
    assert run.history[-2:] == [
        "settle#1 cancelled: the case is closing",
        "closed: duplicate, by ana",
    ]


# Layer 10c, G7: a plan's reference field takes only a reference to its system (brief, D36).


def test_a_plan_field_takes_only_a_reference_to_its_system() -> None:
    # Before 10c, the plan trusted its field's declared type: an order ID the case made up was
    # looked up and paid. Only the case sees the expression, so the case refuses it, before the
    # plan starts, as `checked_inputs` does for a contract's reference input (brief, D30).
    paid: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paid.append(inputs["order_id"])
        return {"refund_id": "ref-1"}

    made_up = {"cat": ["ord-", {"string": [{"var": "amount"}]}]}
    run = run_case(
        refund_with_plan(inputs={"order_id": made_up, "amount": {"var": "approved_amount"}}),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        activities={"payments.refund@2": refund},
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "approve", "sam")]},
    )
    assert paid == []
    assert run.needs_attention == [
        (
            "settle#1: refund-order@1 takes order_id as a reference to orders, and is given a "
            "computed value"
        )
    ]


# --- Layer 11b: a plan step's condition counts beside its fields (brief, D39) ---


def test_a_plan_step_carries_its_conditions_sources() -> None:
    # The step's condition read the customer's own note, which chose that the plan runs. Its
    # untrusted sources travel with the plan beside its fields, never in them, and count for
    # every activity's input policies there: the refund is refused, though each value it gets is
    # trusted (brief, D38) (brief, D39).
    definition = refund_with_plan(
        when={
            "and": [
                {"==": [{"var": "review.outcome"}, "approve"]},
                {"==": [{"var": "note"}, "refund me"]},
            ]
        }
    )
    definition["fields"]["note"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The customer's note"},
    }
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 40, "note": "refund me"},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "approve", "sam")]},
    )
    [failed] = run.needs_attention
    assert failed.startswith("settle#1: refund-order@1 stopped: ")
    assert failed.endswith(
        "payments.refund@2 takes order_id only from a system or a person, never from untrusted "
        "data, and settle's condition reads note (untrusted:customer)"
    )
    assert "refund me" not in "\n".join(run.history)


def settled_by_a_rule(when: Any) -> dict[str, Any]:
    """The refund with the plan step started only by a rule, `settle_on`, once a team lead's check
    of the review is answered, when `when` holds."""
    definition = refund_with_plan(automatic=False)
    del definition["steps"]["settle"]["when"]
    definition["steps"]["lead_check"] = {
        "kind": "task",
        "display": {"title": "Check the review"},
        "roles": ["support-lead"],
        "automatic": False,
        "outcomes": {"ok": {"display": {"title": "The review is right"}}},
    }
    definition["rules"] = {
        "check": {
            "display": {"title": "Have the review checked"},
            "on": {"answered": "review"},
            "then": {"start": ["lead_check"]},
        },
        "settle_on": {
            "display": {"title": "Settle a checked refund"},
            "on": {"answered": "lead_check"},
            "when": when,
            "then": {"start": ["settle"]},
        },
    }
    return definition


CHECKED = [("review", "approve", "ana", {"approved_amount": 40}), ("lead_check", "ok", "sam")]


def test_a_plan_step_a_rule_starts_carries_what_the_rule_read() -> None:
    # The rule's condition read the customer's note: its untrusted sources travel with the plan,
    # as the step's own condition's do (brief, D39). Before the review's fix, the record was spent
    # before it was read, and the refund was paid on the customer's say.
    on_the_note = settled_by_a_rule({"==": [{"var": "note"}, "refund me"]})
    on_the_note["fields"]["note"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The customer's note"},
    }
    run = run_case(
        on_the_note,
        file={"order_id": "ord-1", "amount": 40, "note": "refund me"},
        answers=CHECKED,
        people=PEOPLE,
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "approve", "lee")]},
    )
    [failed] = run.needs_attention
    assert failed.endswith(
        "payments.refund@2 takes order_id only from a system or a person, never from untrusted "
        "data, and settle_on#1's condition, which started settle, reads note (untrusted:customer)"
    )


def test_a_retried_plan_keeps_who_may_not_approve_in_it() -> None:
    # A retried plan is the same run, started again (brief, D26): who may approve nothing in it
    # stays the same, the people the rule's condition read included (brief, D11) (brief, D39). Sam
    # checked the review, which decided that the plan runs; Lee approves the first run, whose
    # refund fails, and Sam can't approve the retried one.
    calls: list[str] = []

    def failing_once(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs["idempotency_key"])
        if len(calls) == 1:
            raise RuntimeError("the provider is down")
        return {"refund_id": "refund-ord-1"}

    run = run_case(
        settled_by_a_rule({"==": [{"var": "lead_check.outcome"}, "ok"]}),
        file={"order_id": "ord-1", "amount": 40},
        answers=[*CHECKED, retry("settle#1", "omar")],
        people={**PEOPLE, "omar": ["operations"]},
        plans={"refund-order@1": refund_order()},
        plan_answers={
            "settle": [("approve_refund", "approve", "lee"), ("approve_refund", "approve", "sam")]
        },
        activities={**FAKES, "payments.refund@2": failing_once},
    )
    assert "omar retried settle#1 as operations" in run.history
    assert calls == ["memory/settle#1/pay#1"]  # Sam's approval of the retried plan was refused
    assert not run.closed
