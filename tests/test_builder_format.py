"""The rest of the format, written from Python (layer 14b): each test reads the JSON written, and
the engine's parser accepts it. See docs/layers/14-builder.md, choices 17 to 28.
"""

import json
from decimal import Decimal
from typing import Any

import pytest

from ventoux import (
    OPENED,
    Approval,
    Case,
    Field,
    Outcome,
    Payload,
    Plan,
    SentBy,
    Then,
    Transition,
    after,
    four_eyes,
)
from ventoux.case.definition import parse_case
from ventoux.core.plan import parse_plan
from ventoux.tooling.builder.written import NotWritable, package, written


def data(case: Case) -> Any:
    """`case`'s JSON as the engine reads it, after `parse_case` accepted it."""
    found = json.loads(written(case), parse_float=Decimal)
    parse_case(found)
    return found


def test_milestones_step_options_and_closing_are_written_as_given() -> None:
    claim = Case(
        "claim",
        title="Insurance claim",
        description="One claim",
        stays_open=False,
        forgetting="while_open",
    )
    paid = claim.milestone("paid", title="Claim paid", description="Money sent")
    assess = claim.task(
        "assess",
        title="Assess the claim",
        roles=["adjuster"],
        outcomes={"ok": Outcome("Assessed", reaches=[paid], description="Done")},
        automatic=False,
        proposed_by=["adjuster"],
        repeatable=True,
        reaches=[paid],
        requires=[],
    )
    claim.activity("pay", "payments.refund@2", title="Pay", requires=[assess, paid])
    claim.close_reason("withdrawn", title="Withdrawn by the customer", roles=["adjuster"])
    claim.closes_when(paid)
    written_data = data(claim)
    assert written_data["display"] == {"title": "Insurance claim", "description": "One claim"}
    assert written_data["milestones"] == {
        "paid": {"display": {"title": "Claim paid", "description": "Money sent"}}
    }
    assert written_data["steps"]["assess"] == {
        "kind": "task",
        "display": {"title": "Assess the claim"},
        "roles": ["adjuster"],
        "automatic": False,
        "proposed_by": ["adjuster"],
        "repeatable": True,
        "reaches": ["paid"],
        "outcomes": {
            "ok": {"display": {"title": "Assessed", "description": "Done"}, "reaches": ["paid"]}
        },
    }
    assert written_data["steps"]["pay"]["requires"] == ["assess", "paid"]
    assert written_data["close_reasons"] == {
        "withdrawn": {"display": {"title": "Withdrawn by the customer"}, "roles": ["adjuster"]}
    }
    assert (written_data["closes_when"], written_data["stays_open"]) == (["paid"], False)
    assert written_data["forgetting"] == "while_open"


def test_closes_when_is_said_once() -> None:
    claim = Case("claim", title="Insurance claim")
    paid = claim.milestone("paid", title="Claim paid")
    claim.closes_when(paid)
    with pytest.raises(ValueError, match="claim already closes when paid"):
        claim.closes_when(paid)


def test_a_fields_options_are_written_as_given() -> None:
    claim = Case("claim", title="Insurance claim")
    claim.field(
        "diagnosis",
        Field.string(),
        title="Diagnosis",
        description="As the doctor wrote it",
        visible_to=["adjuster"],
        sensitive=True,
    )
    claim.field("estimate", Field.number(), title="Estimate", source="untrusted:customer")
    claim.field("kind", Field.outcome("car", "home"), title="Kind of claim")
    claim.task("assess", title="Assess", roles=["adjuster"], outcomes={"ok": Outcome("Fine")})
    fields = data(claim)["fields"]
    assert fields["diagnosis"] == {
        "type": "string",
        "display": {"title": "Diagnosis", "description": "As the doctor wrote it"},
        "visible_to": ["adjuster"],
        "sensitive": True,
    }
    assert fields["estimate"]["source"] == "untrusted:customer"
    assert fields["kind"]["outcomes"] == ["car", "home"]


def test_events_wait_steps_and_payloads() -> None:
    claim = Case("claim", title="Insurance claim")
    cancelled = claim.event(
        "cancelled",
        title="Cancelled by the customer",
        sent_by=SentBy(system="portal"),
        payload={"note": Payload(Field.string(), title="Note", source="untrusted:customer")},
    )
    claim.event("reopened", title="Reopened", sent_by=SentBy(roles=["adjuster"]))
    claim.wait("withdrawal", event=cancelled, title="Wait for a withdrawal")
    found = data(claim)
    assert found["events"]["cancelled"] == {
        "display": {"title": "Cancelled by the customer"},
        "sent_by": {"system": "portal"},
        "payload": {
            "note": {
                "type": "string",
                "display": {"title": "Note"},
                "source": "untrusted:customer",
            }
        },
    }
    assert found["events"]["reopened"]["sent_by"] == {"roles": ["adjuster"]}
    assert found["steps"]["withdrawal"] == {
        "kind": "wait",
        "display": {"title": "Wait for a withdrawal"},
        "event": "cancelled",
    }
    assert (cancelled.text("note") == "x").data == {"==": [{"var": "cancelled.note"}, "x"]}


def test_a_payload_field_is_read_as_its_event_declares_it() -> None:
    claim = Case("claim", title="Insurance claim")
    cancelled = claim.event(
        "cancelled",
        title="Cancelled",
        sent_by=SentBy(system="portal"),
        payload={"note": Payload(Field.string(), title="Note")},
    )
    with pytest.raises(TypeError, match="cancelled carries note as a string, not a number"):
        cancelled.number("note")
    with pytest.raises(TypeError, match="cancelled carries no field reason"):
        cancelled.text("reason")


def test_rules_moments_and_timers() -> None:
    claim = Case("claim", title="Insurance claim")
    payout = claim.field("payout", Field.number(), title="Payout")
    approved = claim.field("approved", Field.number(), title="Approved")
    paid = claim.milestone("paid", title="Paid")
    assess = claim.task(
        "assess", title="Assess", roles=["adjuster"], outcomes={"ok": Outcome("Fine")}
    )
    chase = claim.activity("chase", "letters.draft@2", title="Chase", repeatable=True)
    claim.rule(
        "on_open",
        title="Note the opening",
        on=OPENED,
        when=payout > 0,
        then=Then(set=[(approved, payout)], reach=[paid], start=[chase], stop=[assess]),
    )
    claim.rule("late", title="Late", on=after("2d", since=assess.started), then=Then(start=[chase]))
    claim.rule("done", title="Done", on=assess.answered, then=Then(reach=[paid]))
    claim.rule("noted", title="Noted", on=paid.reached, then=Then(start=[chase]))
    rules = data(claim)["rules"]
    assert rules["on_open"] == {
        "display": {"title": "Note the opening"},
        "on": "opened",
        "when": {">": [{"var": "payout"}, 0]},
        "then": {
            "set": {"approved": {"var": "payout"}},
            "reach": ["paid"],
            "start": ["chase"],
            "stop": ["assess"],
        },
    }
    assert rules["late"]["on"] == {"after": "2d", "since": {"started": "assess"}}
    assert rules["done"]["on"] == {"answered": "assess"}
    assert rules["noted"]["on"] == {"reached": "paid"}


def test_sla_and_reminder_are_written_as_patterns() -> None:
    # Written in `rules` as patterns, expanded when the definition is read (brief, D46).
    claim = Case("claim", title="Insurance claim")
    assess = claim.task(
        "assess", title="Assess", roles=["adjuster"], outcomes={"ok": Outcome("Fine")}
    )
    chase = claim.activity("chase", "letters.draft@2", title="Chase", repeatable=True)
    escalate = claim.activity("escalate", "letters.draft@2", title="Escalate", automatic=False)
    claim.sla("assess_late", title="Late", step=assess, within="5d", then=Then(start=[escalate]))
    claim.reminder("chased", title="Chase", task=assess, after=["2d", "4d"], start=chase)
    rules = data(claim)["rules"]
    assert rules["assess_late"] == {
        "display": {"title": "Late"},
        "sla": {"step": "assess", "within": "5d"},
        "then": {"start": ["escalate"]},
    }
    assert rules["chased"] == {
        "display": {"title": "Chase"},
        "reminder": {"task": "assess", "after": ["2d", "4d"], "start": "chase"},
    }


def test_four_eyes_is_an_approval_by_two_people() -> None:
    # The builder's name for `"count": 2` (brief, D47).
    refund = Case("refund", title="Customer refund")
    amount = refund.field("amount", Field.number(), title="Amount")
    refund.activity(
        "pay",
        "payments.refund@2",
        title="Pay",
        approval=four_eyes(roles=["support-lead"], reason="Large", when=amount > 10000),
    )
    refund.activity(
        "pay_small",
        "payments.refund@2",
        title="Pay",
        approval=Approval(roles=["support-lead"], reason="Small", count=1),
    )
    steps = data(refund)["steps"]
    assert steps["pay"]["approval"] == {
        "when": {">": [{"var": "amount"}, 10000]},
        "roles": ["support-lead"],
        "count": 2,
        "display": {"reason": "Large"},
    }
    assert steps["pay_small"]["approval"]["count"] == 1


def test_a_plan_is_written_as_its_json() -> None:
    plan = Plan("review-claim", 2, title="Review a claim", description="Two steps")
    amount = plan.field("amount", Field.number())
    note = plan.field("note", Field.string(), source="untrusted:customer")
    plan.initial("ask")
    plan.wait(
        "ask",
        outcomes=["accept", "refuse"],
        roles=["adjuster"],
        sets={"accept": [amount]},
        timeout="2d",
        on={"accept": [Transition("pay", when=amount > 100), Transition("done")], "refuse": "done"},
    )
    plan.approval("check", of="pay", roles=["support-lead"], on={"approve": "pay"})
    plan.activity("pay", "payments.refund@2", inputs={"amount": amount}, on={"done": "done"})
    plan.final("done", "succeeded")
    found = json.loads(written(plan), parse_float=Decimal)
    parse_plan(found)
    assert found["display"] == {"title": "Review a claim", "description": "Two steps"}
    assert found["fields"] == {
        "amount": {"type": "number"},
        "note": {"type": "string", "source": "untrusted:customer"},
    }
    assert found["initial"] == "ask"
    assert found["states"]["ask"] == {
        "wait": {
            "outcomes": ["accept", "refuse"],
            "roles": ["adjuster"],
            "sets": {"accept": ["amount"]},
            "timeout": "2d",
        },
        "on": {
            "accept": [
                {"target": "pay", "when": {">": [{"var": "amount"}, 100]}},
                {"target": "done"},
            ],
            "refuse": "done",
        },
    }
    assert found["states"]["check"] == {
        "approval": {"of": "pay", "roles": ["support-lead"]},
        "on": {"approve": "pay"},
    }
    assert found["states"]["done"] == {"final": "succeeded"}
    assert note.data == {"var": "note"}


def test_initial_is_said_once() -> None:
    plan = Plan("review-claim", 1, title="Review a claim")
    plan.initial("ask")
    with pytest.raises(ValueError, match="review-claim already starts in ask"):
        plan.initial("pay")


def test_a_package_holds_one_file_per_plan_name() -> None:
    # Two versions of one plan would need two files of one name, plans/settle.json.
    claim = Case("claim", title="Insurance claim")
    for version in (1, 2):
        settle = Plan("settle", version, title="Settle")
        settle.final("done", "succeeded")
        claim.plan_step(f"settle_{version}", settle, title="Settle")
    with pytest.raises(NotWritable, match="claim runs settle@1 and settle@2"):
        package(claim)
