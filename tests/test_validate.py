"""Static validation: what can be proven about a plan by reading it (layer 3).

See docs/layers/03-validation.md and docs/guides/plans.md.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.core.plan import parse_plan
from ventoux.core.validate import Issue, validate
from ventoux.testing import CATALOG

GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "plans.md"


def guide_plan() -> dict[str, Any]:
    """The guide's example plan, the first JSON block in it, as stored data."""
    example = GUIDE.read_text().split("```json\n")[1].split("```")[0]
    plan: dict[str, Any] = json.loads(example, parse_float=Decimal)
    return plan


def issues(plan: dict[str, Any]) -> list[Issue]:
    return validate(parse_plan(plan), CATALOG)


def changed(**states: Any) -> dict[str, Any]:
    """The guide's plan with some states replaced (or added)."""
    plan = copy.deepcopy(guide_plan())
    plan["states"] |= states
    return plan


def test_only_a_parsed_plan_is_validated() -> None:
    # Fail closed: raw data is never read as a plan with nothing wrong.
    with pytest.raises(TypeError, match="validate takes a parsed plan"):
        validate(guide_plan(), CATALOG)  # type: ignore[arg-type]


def test_initial_must_be_a_state() -> None:
    plan = changed() | {"initial": "chek_order"}
    assert Issue(
        "initial",
        "UNKNOWN_TARGET",
        '"chek_order" is not a state: the states are approve_refund, check_order, failed, paid, '
        "pay",
    ) in issues(plan)


def test_every_target_must_be_a_state() -> None:
    plan = changed(
        pay={**guide_plan()["states"]["pay"], "on": {"done": "pai", "declined": "failed"}}
    )
    assert Issue(
        "states.pay.on.done",
        "UNKNOWN_TARGET",
        '"pai" is not a state: the states are approve_refund, check_order, failed, paid, pay',
    ) in issues(plan)


def test_a_target_in_a_list_is_found_by_its_position() -> None:
    lookup = guide_plan()["states"]["check_order"]
    fork = [
        {"when": {">": [{"var": "amount"}, 100]}, "target": "approve_refund"},
        {"target": "pai"},
    ]
    plan = changed(check_order={**lookup, "on": {"done": fork, "not_found": "failed"}})
    assert [i for i in issues(plan) if i.code == "UNKNOWN_TARGET"] == [
        Issue(
            "states.check_order.on.done[1]",
            "UNKNOWN_TARGET",
            '"pai" is not a state: the states are approve_refund, check_order, failed, paid, pay',
        )
    ]


def test_the_guides_example_has_no_issues() -> None:
    assert issues(guide_plan()) == []


def test_every_activity_is_in_the_catalog() -> None:
    plan = changed(pay={**guide_plan()["states"]["pay"], "activity": "payments.refund@3"})
    assert Issue(
        "states.pay.activity",
        "UNKNOWN_ACTIVITY",
        "payments.refund@3 is not in the catalog. Registered: payments.refund@2. "
        "Use a registered version, or register this one first.",
    ) in issues(plan)


def pay_with_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    return changed(pay={**guide_plan()["states"]["pay"], "inputs": inputs})


ORDER_ID = {"var": "order_id"}
AMOUNT = {"var": "amount"}


def test_an_input_the_contract_does_not_take_is_refused() -> None:
    plan = pay_with_inputs({"order_id": ORDER_ID, "amount": AMOUNT, "amout": AMOUNT})
    assert issues(plan) == [
        Issue(
            "states.pay.inputs.amout",
            "UNKNOWN_INPUT",
            "payments.refund@2 has no input amout: its inputs are amount, order_id",
        )
    ]


def test_an_input_the_contract_needs_must_be_given() -> None:
    plan = pay_with_inputs({"order_id": ORDER_ID})
    assert issues(plan) == [
        Issue(
            "states.pay.inputs",
            "MISSING_INPUT",
            "payments.refund@2 needs the input amount: add it to inputs",
        )
    ]


def test_the_idempotency_key_is_filled_by_the_engine_never_by_a_plan() -> None:
    # The engine builds the key from the case, the step and its run (brief, D17); a plan that set
    # it could make two runs share one key, and the second refund would be skipped as a duplicate.
    key = {"var": "order_id"}
    plan = pay_with_inputs({"order_id": ORDER_ID, "amount": AMOUNT, "idempotency_key": key})
    assert issues(plan) == [
        Issue(
            "states.pay.inputs.idempotency_key",
            "ENGINE_INPUT",
            "idempotency_key is filled by the engine, never by a plan: remove it",
        )
    ]


def with_code(plan: dict[str, Any], code: str) -> list[Issue]:
    """Only the issues of one kind: for a plan that breaks other rules too."""
    return [issue for issue in issues(plan) if issue.code == code]


def pay_on(on: dict[str, Any]) -> dict[str, Any]:
    return changed(pay={**guide_plan()["states"]["pay"], "on": on})


def approval_with(wait: dict[str, Any], on: dict[str, Any]) -> dict[str, Any]:
    return changed(approve_refund={"wait": wait, "on": on})


APPROVE_OR_REJECT = {"outcomes": ["approve", "reject"]}


def test_an_activity_never_gives_an_event_its_contract_does_not_declare() -> None:
    plan = pay_on({"done": "paid", "declined": "failed", "cancelled": "failed"})
    assert issues(plan) == [
        Issue(
            "states.pay.on.cancelled",
            "UNKNOWN_EVENT",
            "payments.refund@2 never gives cancelled: its events are done, declined",
        )
    ]


def test_every_outcome_an_activity_declares_is_handled() -> None:
    # Unhandled, a declined refund would leave the plan with nowhere to go (brief, D17).
    plan = pay_on({"done": "paid"})
    assert issues(plan) == [
        Issue(
            "states.pay.on",
            "MISSING_EVENT",
            "declined is not handled: say where the plan goes on declined",
        )
    ]


def test_a_wait_never_gives_an_outcome_it_does_not_offer() -> None:
    on = {"approve": "pay", "reject": "failed", "escalate": "failed"}
    plan = approval_with(APPROVE_OR_REJECT, on)
    assert issues(plan) == [
        Issue(
            "states.approve_refund.on.escalate",
            "UNKNOWN_EVENT",
            "the wait approve_refund never gives escalate: its events are approve, reject",
        )
    ]


def test_every_outcome_a_wait_offers_is_handled() -> None:
    plan = approval_with(APPROVE_OR_REJECT, {"approve": "pay"})
    assert issues(plan) == [
        Issue(
            "states.approve_refund.on",
            "MISSING_EVENT",
            "reject is not handled: say where the plan goes on reject",
        )
    ]


def test_a_wait_without_a_timeout_never_times_out() -> None:
    plan = approval_with(
        APPROVE_OR_REJECT, {"approve": "pay", "reject": "failed", "timeout": "failed"}
    )
    assert issues(plan) == [
        Issue(
            "states.approve_refund.on.timeout",
            "UNKNOWN_EVENT",
            "the wait approve_refund never gives timeout: its events are approve, reject; "
            "declare wait.timeout to wait for timeout",
        )
    ]


def test_a_wait_with_a_timeout_handles_it() -> None:
    wait = APPROVE_OR_REJECT | {"timeout": "48h"}
    plan = approval_with(wait, {"approve": "pay", "reject": "failed"})
    assert issues(plan) == [
        Issue(
            "states.approve_refund.on",
            "MISSING_EVENT",
            "timeout is not handled: say where the plan goes on timeout",
        )
    ]


def test_no_outcome_is_named_timeout() -> None:
    wait = {"outcomes": ["accept", "decline", "timeout"]}
    plan = approval_with(wait, {"accept": "pay", "decline": "failed", "timeout": "failed"})
    assert with_code(plan, "RESERVED_OUTCOME") == [
        Issue(
            "states.approve_refund.wait.outcomes",
            "RESERVED_OUTCOME",
            "timeout is the event of a wait's timeout, not an outcome: name the outcome differently",
        )
    ]


def lookup_forking_on(when: Any) -> dict[str, Any]:
    """The guide's plan with check_order forking on `when`: approval if it holds, else pay."""
    lookup = guide_plan()["states"]["check_order"]
    fork = [{"when": when, "target": "approve_refund"}, {"target": "pay"}]
    return changed(check_order={**lookup, "on": {"done": fork, "not_found": "failed"}})


def test_an_input_reads_only_declared_fields() -> None:
    plan = pay_with_inputs({"order_id": ORDER_ID, "amount": {"var": "amout"}})
    assert issues(plan) == [
        Issue("states.pay.inputs.amount", "EXPRESSION_INVALID", "amout is not a declared field")
    ]


def test_a_condition_gives_a_boolean() -> None:
    plan = lookup_forking_on({"+": [{"var": "amount"}, 1]})
    assert with_code(plan, "EXPRESSION_INVALID") == [
        Issue(
            "states.check_order.on.done[0].when",
            "EXPRESSION_INVALID",
            "a condition gives a boolean, and this gives a number: write a comparison, "
            "such as amount > 100",
        )
    ]


def test_a_condition_is_checked_inside_too() -> None:
    plan = lookup_forking_on({">": [{"var": "amount"}, "100"]})
    assert with_code(plan, "EXPRESSION_INVALID") == [
        Issue(
            "states.check_order.on.done[0].when",
            "EXPRESSION_INVALID",
            ">[1]: `>` compares numbers, and this is a string",
        )
    ]


def test_every_state_is_reachable() -> None:
    plan = changed(cancelled={"final": "failed"})
    assert issues(plan) == [
        Issue(
            "states.cancelled",
            "UNREACHABLE_STATE",
            "no path from check_order reaches cancelled: remove it, or add a transition to it",
        )
    ]


def test_from_every_state_the_plan_can_end() -> None:
    # A declined refund waits for a retry that only ever leads back to itself: the plan is stuck.
    pay = guide_plan()["states"]["pay"]
    plan = changed(
        pay={**pay, "on": {"done": "paid", "declined": "retry_payment"}},
        retry_payment={"wait": {"outcomes": ["retry"]}, "on": {"retry": "retry_payment"}},
    )
    assert issues(plan) == [
        Issue(
            "states.retry_payment",
            "NO_PATH_TO_FINAL",
            "the plan can never end from retry_payment: add a path to a final state",
        )
    ]


def guide_fork() -> dict[str, Any]:
    """The guide's plan with its second JSON block, the fork that skips the approval."""
    block = GUIDE.read_text().split("```json\n")[2].split("```")[0]
    fork: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    return changed(**fork)


def test_an_approval_offers_exactly_approve_and_reject() -> None:
    plan = approval_with({"outcomes": ["approve", "edit"]}, {"approve": "pay", "edit": "failed"})
    assert with_code(plan, "APPROVAL_OUTCOMES") == [
        Issue(
            "states.approve_refund.wait.outcomes",
            "APPROVAL_OUTCOMES",
            "a wait offering approve is an approval, and offers exactly approve and reject; "
            "this one offers approve, edit: use another word than approve",
        )
    ]
    # Fail closed: a wait that isn't a proper approval approves nothing.
    assert [issue.code for issue in issues(plan)] == ["APPROVAL_OUTCOMES", "APPROVAL_REQUIRED"]


def test_a_high_risk_activity_is_never_reached_without_an_approval() -> None:
    assert issues(guide_fork()) == [
        Issue(
            "states.pay",
            "APPROVAL_REQUIRED",
            "payments.refund@2 is high risk, and check_order → pay reaches it without an "
            "approval: route every path to pay through an approval",
        )
    ]


def test_a_low_risk_activity_needs_no_approval() -> None:
    # orders.lookup@1 is low risk: check_order runs first, before any approval, and that's fine.
    assert with_code(guide_plan(), "APPROVAL_REQUIRED") == []


def test_one_approval_unlocks_one_high_risk_run() -> None:
    pay = guide_plan()["states"]["pay"]
    plan = changed(
        pay={**pay, "on": {"done": "refund_fee", "declined": "failed"}},
        refund_fee={**pay, "on": {"done": "paid", "declined": "failed"}},
    )
    assert issues(plan) == [
        Issue(
            "states.pay",
            "APPROVAL_REUSED",
            "one approval would unlock two high-risk runs: after pay, refund_fee can run without "
            "a new approval: add an approval before refund_fee",
        )
    ]


def retry_after_decline(retry_to: str) -> dict[str, Any]:
    """The guide's plan where a declined refund waits for a person to retry, going to `retry_to`."""
    pay = guide_plan()["states"]["pay"]
    return changed(
        pay={**pay, "on": {"done": "paid", "declined": "retry_payment"}},
        retry_payment={
            "wait": {"outcomes": ["retry", "give_up"]},
            "on": {"retry": retry_to, "give_up": "failed"},
        },
    )


def test_a_loop_back_to_a_high_risk_activity_needs_a_new_approval() -> None:
    assert issues(retry_after_decline("pay")) == [
        Issue(
            "states.pay",
            "APPROVAL_REUSED",
            "one approval would unlock two high-risk runs: after pay, pay can run without "
            "a new approval: add an approval before pay",
        )
    ]


def test_a_loop_through_the_approval_is_approved_each_time() -> None:
    assert issues(retry_after_decline("approve_refund")) == []


def test_every_problem_is_listed_not_only_the_first() -> None:
    lookup = guide_plan()["states"]["check_order"]
    pay = guide_plan()["states"]["pay"]
    plan = changed(
        check_order={**lookup, "inputs": {"order_id": ORDER_ID, "amout": AMOUNT}},
        pay={**pay, "on": {"done": "pai"}},
        cancelled={"final": "failed"},
    )
    assert [(issue.path, issue.code) for issue in issues(plan)] == [
        ("states.check_order.inputs.amout", "UNKNOWN_INPUT"),
        ("states.pay.on", "MISSING_EVENT"),
        ("states.pay.on.done", "UNKNOWN_TARGET"),
        # With no valid way out, pay can never end, and nothing reaches paid any more.
        ("states.pay", "NO_PATH_TO_FINAL"),
        ("states.paid", "UNREACHABLE_STATE"),
        ("states.cancelled", "UNREACHABLE_STATE"),
    ]


# Each code in the guide's table, and a plan that breaks that rule as the row's example does.
GUIDE_EXAMPLES: dict[str, Any] = {
    "UNKNOWN_TARGET": lambda: pay_on({"done": "pai", "declined": "failed"}),
    "UNKNOWN_ACTIVITY": lambda: changed(
        pay={**guide_plan()["states"]["pay"], "activity": "payments.refund@3"}
    ),
    "UNKNOWN_INPUT": lambda: pay_with_inputs(
        {"order_id": ORDER_ID, "amount": AMOUNT, "amout": AMOUNT}
    ),
    "MISSING_INPUT": lambda: pay_with_inputs({"order_id": ORDER_ID}),
    "ENGINE_INPUT": lambda: pay_with_inputs(
        {"order_id": ORDER_ID, "amount": AMOUNT, "idempotency_key": ORDER_ID}
    ),
    "UNKNOWN_EVENT": lambda: pay_on({"done": "paid", "declined": "failed", "cancelled": "failed"}),
    "MISSING_EVENT": lambda: pay_on({"done": "paid"}),
    "RESERVED_OUTCOME": lambda: approval_with(
        {"outcomes": ["accept", "decline", "timeout"]},
        {"accept": "pay", "decline": "failed", "timeout": "failed"},
    ),
    "APPROVAL_OUTCOMES": lambda: approval_with(
        {"outcomes": ["approve", "edit"]}, {"approve": "pay", "edit": "failed"}
    ),
    "EXPRESSION_INVALID": lambda: pay_with_inputs(
        {"order_id": ORDER_ID, "amount": {"var": "amout"}}
    ),
    "UNREACHABLE_STATE": lambda: changed(refund_fee={"final": "failed"}),
    "NO_PATH_TO_FINAL": lambda: changed(
        pay={**guide_plan()["states"]["pay"], "on": {"done": "paid", "declined": "retry_payment"}},
        retry_payment={"wait": {"outcomes": ["retry"]}, "on": {"retry": "retry_payment"}},
    ),
    "APPROVAL_REQUIRED": guide_fork,
    "APPROVAL_REUSED": lambda: changed(
        pay={**guide_plan()["states"]["pay"], "on": {"done": "refund_fee", "declined": "failed"}},
        refund_fee={**guide_plan()["states"]["pay"], "on": {"done": "paid", "declined": "failed"}},
    ),
    "UNKNOWN_SOURCE": lambda: with_source("amount", "untrusted:lml"),
}


def guide_table() -> list[tuple[str, str]]:
    """The guide's table of issues, as (code, example message); "as above" is the block above it."""
    guide = GUIDE.read_text()
    above = guide.split("The check says:\n\n```\n")[1].split("```")[0]
    above_message = " ".join(above.split()).split("APPROVAL_REQUIRED ")[1]
    table = guide.split("| Code |")[1].split("\n\n")[0]
    rows = [line.split("|") for line in table.splitlines() if line.startswith("| `")]
    return [
        (
            code.strip().strip("`"),
            above_message if says.strip() == "as above" else says.strip()[1:-1],
        )
        for _, code, _, says, _ in rows
    ]


def test_the_guide_lists_every_issue_code() -> None:
    assert [code for code, _ in guide_table()] == list(GUIDE_EXAMPLES)


@pytest.mark.parametrize(("code", "says"), guide_table())
def test_the_guides_messages_are_what_validate_says(code: str, says: str) -> None:
    assert says in [issue.message for issue in with_code(GUIDE_EXAMPLES[code](), code)]


def with_source(field: str, source: str) -> dict[str, Any]:
    """The guide's plan with `field` declared from `source`."""
    plan = changed()
    plan["fields"][field] = {**plan["fields"][field], "source": source}
    return plan


def test_a_source_label_must_be_registered() -> None:
    # Labels are registered by the platform team, so a typo is caught (brief, D12).
    assert with_code(with_source("amount", "untrusted:lml"), "UNKNOWN_SOURCE") == [
        Issue(
            "fields.amount.source",
            "UNKNOWN_SOURCE",
            "untrusted:lml has a label nobody registered: the labels are customer, document, "
            "email, llm, web; use one of them, or ask the platform team to register it",
        )
    ]


def test_a_registered_label_is_accepted() -> None:
    assert with_code(with_source("amount", "untrusted:llm"), "UNKNOWN_SOURCE") == []
