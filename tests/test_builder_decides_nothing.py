"""The builder writes data and decides nothing (layer 14b, choice 25).

Each definition here is one the engine refuses. The builder writes it as given; the refusal comes
from the engine's own parsing and validation, as `ventoux check` will say it, never smoothed over
by the builder. See docs/layers/14-builder.md.
"""

import json
from decimal import Decimal

import pytest

from ventoux import Approval, Case, Field, Outcome, Plan, Then, Transition
from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.validate import validate_case
from ventoux.core.plan import parse_plan
from ventoux.core.validate import validate
from ventoux.testing import CATALOG
from ventoux.tooling.builder.written import written


def read(definition: Case | Plan) -> object:
    return json.loads(written(definition), parse_float=Decimal)


def test_a_sensitive_field_given_to_a_workflow_step_is_written_and_refused_by_the_check() -> None:
    # Its worker doesn't hold the case's key (brief, D31) (brief, D36).
    claim = Case("claim", title="Insurance claim")
    customer = claim.reference(
        "customer_id", system="crm", title="Customer", sensitive=True, visible_to=["adjuster"]
    )
    claim.workflow(
        "kyc", "kyc.check@1", title="Check the customer", inputs={"customer_id": customer}
    )
    data = read(claim)
    assert data["steps"]["kyc"]["inputs"] == {"customer_id": {"var": "customer_id"}}  # type: ignore[index]
    codes = [issue.code for issue in validate_case(parse_case(data), CATALOG)]
    assert "SENSITIVE_TO_WORKFLOW" in codes


def untrusted_plan(target: str) -> Plan:
    plan = Plan("route", 1, title="Route a request")
    note = plan.field("note", Field.string(), source="untrusted:customer")
    plan.initial("ask")
    plan.wait(
        "ask",
        outcomes=["done"],
        roles=["support"],
        on={"done": [Transition(target, when=note == "urgent"), Transition("end")]},
    )
    plan.final("end", "succeeded")
    return plan


def test_a_plan_path_chosen_by_untrusted_data_is_written_and_refused_by_the_check() -> None:
    # Untrusted data never chooses a plan's path (brief, D49).
    plan = untrusted_plan("end")
    codes = [issue.code for issue in validate(parse_plan(read(plan)), CATALOG)]
    assert "UNTRUSTED_TRANSITION" in codes


def test_a_transition_to_no_state_is_written_and_refused_by_the_check() -> None:
    plan = untrusted_plan("nowhere")
    data = read(plan)
    assert data["states"]["ask"]["on"]["done"][0]["target"] == "nowhere"  # type: ignore[index]
    codes = [issue.code for issue in validate(parse_plan(data), CATALOG)]
    assert "UNKNOWN_TARGET" in codes


def test_an_item_outside_count_or_sum_is_written_and_refused_when_read() -> None:
    claim = Case("claim", title="Insurance claim")
    lines = claim.field("lines", Field.list(amount=Field.number()), title="Lines")
    total = claim.field("total", Field.number(), title="Total")
    paid = claim.milestone("paid", title="Paid")
    claim.task("assess", title="Assess", roles=["adjuster"], outcomes={"ok": Outcome("Fine")})
    claim.rule(
        "copy",
        title="Copy an amount",
        on=paid.reached,
        then=Then(set=[(total, lines.number("amount"))]),
    )
    with pytest.raises(CaseInvalid, match="item"):
        parse_case(read(claim))


def test_a_count_the_engine_refuses_is_written_and_refused_when_read() -> None:
    # `true` is never read as the number 1 (brief, D47).
    refund = Case("refund", title="Customer refund")
    refund.activity(
        "pay",
        "payments.refund@2",
        title="Pay",
        approval=Approval(roles=["support-lead"], reason="Large", count=True),
    )
    data = read(refund)
    assert data["steps"]["pay"]["approval"]["count"] is True  # type: ignore[index]
    with pytest.raises(CaseInvalid, match="how many people must approve"):
        parse_case(data)
