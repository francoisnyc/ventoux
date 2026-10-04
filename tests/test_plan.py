"""Plans: a state machine written as data, shape only (layer 2).

See docs/layers/02-plan-expressions.md. References and reachability are layer 3's.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.core.expressions import NumberType, Var, parse_expression
from ventoux.core.plan import (
    ActivityState,
    FinalState,
    PlanInvalid,
    Transition,
    WaitState,
    parse_plan,
)

# The design note's example: the refund paid as a one-state plan.
REFUND_PAY: dict[str, Any] = {
    "plan": "refund-pay",
    "version": 1,
    "display": {"title": "Refund the customer"},
    "fields": {
        "order_id": {"type": "reference", "system": "orders"},
        "amount": {"type": "number"},
    },
    "initial": "pay",
    "states": {
        "pay": {
            "activity": "payments.refund@1",
            "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
            "on": {"done": "paid", "declined": "failed"},
        },
        "paid": {"final": "succeeded"},
        "failed": {"final": "failed"},
    },
}


def changed(path: list[str], value: object) -> dict[str, Any]:
    """The example plan with the value at `path` replaced (or removed, when `value` is ...)."""
    plan = copy.deepcopy(REFUND_PAY)
    holder = plan
    for key in path[:-1]:
        holder = holder[key]
    if value is ...:
        del holder[path[-1]]
    else:
        holder[path[-1]] = value
    return plan


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (
            {"on": {"done": "paid"}},
            "states.pay: a state is one of activity, wait or final, and this one is none",
        ),
        (
            {"activity": "payments.refund@1", "final": "succeeded", "on": {"done": "paid"}},
            "states.pay: a state is one of activity, wait or final, and this one is activity and final",
        ),
    ],
)
def test_a_state_is_exactly_one_kind(state: object, message: str) -> None:
    with pytest.raises(PlanInvalid) as refused:
        parse_plan(changed(["states", "pay"], state))
    assert str(refused.value) == message


NOT_AN_OPERATOR = (
    "`now` is not an operator. The operators are: var, ==, !=, >, >=, <, <=, and, or, !, +, -, *, "
    "/, if, in, cat, string, exists, count, sum, item. Logic that doesn't fit is a compute "
    "activity."
)
WAIT = {"wait": {"outcomes": ["approve", "reject"], "timeout": "48h"}, "on": {"approve": "paid"}}


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (["plan"], "Refund Pay", 'plan: a plan name looks like "refund-pay"'),
        (["version"], 0, "version: a version is a whole number, 1 or more"),
        (["display", "title"], ..., "display.title: required"),
        (["queue"], "payments", "queue: not a field here"),
        (
            ["fields", "amount"],
            {"type": "money"},
            (
                "fields.amount: a field's type is one of "
                "number, string, boolean, outcome, reference or list, and this one is money"
            ),
        ),
        (
            ["states", "pay", "activity"],
            "payments.refund",
            'states.pay.activity: an activity reference looks like "payments.refund@1"',
        ),
        (["states", "pay", "queue"], "payments", "states.pay.queue: not a field here"),
        (
            ["states", "pay", "inputs", "amount"],
            {"now": []},
            "states.pay.inputs.amount: " + NOT_AN_OPERATOR,
        ),
        (
            ["states", "Pay Now"],
            {"final": "succeeded"},
            'states.Pay Now: a state name looks like "await_approval"',
        ),
        (
            ["states", "pay"],
            {**WAIT, "wait": {"outcomes": []}},
            "states.pay.wait.outcomes: a wait has at least one outcome",
        ),
        (
            ["states", "pay"],
            {**WAIT, "wait": {"outcomes": ["approve"], "timeout": "2 days"}},
            'states.pay.wait.timeout: a duration looks like "30s", "5m", "48h" or "7d"',
        ),
        (
            ["states", "paid", "final"],
            "done",
            "states.paid.final: a final state is succeeded or failed",
        ),
    ],
)
def test_a_malformed_plan_is_rejected(path: list[str], value: object, message: str) -> None:
    with pytest.raises(PlanInvalid) as refused:
        parse_plan(changed(path, value))
    assert str(refused.value) == message


def test_every_problem_is_listed() -> None:
    plan = changed(["display", "title"], ...)
    plan["states"]["pay"]["activity"] = "payments.refund"
    with pytest.raises(PlanInvalid) as refused:
        parse_plan(plan)
    assert str(refused.value).splitlines() == [
        "display.title: required",
        'states.pay.activity: an activity reference looks like "payments.refund@1"',
    ]


def test_the_example_plan_parses() -> None:
    plan = parse_plan(REFUND_PAY)
    assert plan.display.title == "Refund the customer"
    assert plan.fields["amount"] == NumberType()
    pay = plan.states["pay"]
    assert isinstance(pay, ActivityState)
    assert pay.inputs["amount"] == Var(var="amount")
    # A bare state name is shorthand for one transition with no condition.
    assert pay.on["done"] == (Transition(target="paid"),)
    assert plan.states["paid"] == FinalState(final="succeeded")


def test_a_wait_state_with_conditional_transitions_parses() -> None:
    state = {
        "wait": {"outcomes": ["approve", "reject"], "timeout": "48h"},
        "on": {
            "approve": [
                {"when": {">": [{"var": "amount"}, 1000]}, "target": "failed"},
                {"target": "pay"},
            ],
            "reject": "failed",
            "timeout": "failed",
        },
    }
    plan = parse_plan(changed(["states", "await_approval"], state))
    waiting = plan.states["await_approval"]
    assert isinstance(waiting, WaitState)
    assert waiting.wait.outcomes == ("approve", "reject")
    first, otherwise = waiting.on["approve"]
    assert first.when == parse_expression({">": [{"var": "amount"}, 1000]})
    assert otherwise == Transition(target="pay")


def test_the_guides_plan_state_parses() -> None:
    guide = (Path(__file__).parent.parent / "docs" / "guides" / "expressions.md").read_text()
    snippet = guide.split("## In a plan")[1].split("```json\n")[1].split("```")[0]
    state = json.loads("{" + snippet + "}", parse_float=Decimal)["pay"]
    assert isinstance(parse_plan(changed(["states", "pay"], state)).states["pay"], ActivityState)
