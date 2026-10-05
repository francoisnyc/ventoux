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
        "payments.refund@3 is not in the catalog. Registered: payments.refund@1. "
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
            "payments.refund@1 has no input amout: its inputs are amount, order_id",
        )
    ]


def test_an_input_the_contract_needs_must_be_given() -> None:
    plan = pay_with_inputs({"order_id": ORDER_ID})
    assert issues(plan) == [
        Issue(
            "states.pay.inputs",
            "MISSING_INPUT",
            "payments.refund@1 needs the input amount: add it to inputs",
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
