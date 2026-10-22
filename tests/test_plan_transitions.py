"""A plan's path is never chosen by untrusted data (brief, D49).

Tests go through `run_plan`, `run_case`, `validate` and `validate_case`, and read what each reports.
See docs/layers/fix-plan-transitions.md.
"""

from decimal import Decimal
from typing import Any

from ventoux.core.provenance import sourced
from ventoux.testing import run_case, run_plan


def branching(note_source: str | None = None) -> dict[str, Any]:
    """A plan that looks the order up, then goes to `paid` if `note` says "go", else `failed`.
    `note_source` marks the field, as a plan declares an untrusted one."""
    note: dict[str, Any] = {"type": "string"}
    if note_source is not None:
        note["source"] = note_source
    return {
        "plan": "check-only",
        "version": 1,
        "display": {"title": "Check the order"},
        "fields": {"order_id": {"type": "reference", "system": "orders"}, "note": note},
        "initial": "check_order",
        "states": {
            "check_order": {
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "order_id"}},
                "on": {
                    "done": [
                        {"target": "paid", "when": {"==": [{"var": "note"}, "go"]}},
                        {"target": "failed"},
                    ],
                    "not_found": "failed",
                },
            },
            "paid": {"final": "succeeded"},
            "failed": {"final": "failed"},
        },
    }


ORDER = sourced("ord-1", "system:opener")


def test_a_transition_reading_untrusted_data_stops_the_plan() -> None:
    # Whatever the note says, the plan stops before reading it: untrusted data can't choose its
    # path (brief, D49). The message names the field and its source, never the value.
    for said in ("go", "anything else"):
        run = run_plan(
            branching(),
            fields={"order_id": ORDER, "note": sourced(said, "untrusted:customer")},
            answers=[],
        )
        assert run.status == "stopped"
        assert run.reason == (
            "on done, the transition to paid reads note (untrusted:customer), and untrusted "
            "data can't choose a plan's path"
        )
        assert said not in run.reason


def test_an_unrecognised_source_stops_the_plan_too() -> None:
    # Fail closed: a source the engine doesn't recognise is never read as trusted.
    run = run_plan(
        branching(),
        fields={"order_id": ORDER, "note": sourced("go", "rumour:mill")},
        answers=[],
    )
    assert run.status == "stopped"
    assert run.reason == (
        "on done, the transition to paid reads note (rumour:mill), and untrusted data can't "
        "choose a plan's path"
    )


def first_holds(plan: dict[str, Any]) -> dict[str, Any]:
    """The plan with a transition on a trusted amount tried before the one on the note."""
    plan["fields"]["amount"] = {"type": "number"}
    plan["states"]["check_order"]["on"]["done"].insert(
        0, {"target": "paid", "when": {"<": [{"var": "amount"}, 100]}}
    )
    return plan


def test_a_transition_never_tried_refuses_nothing() -> None:
    # The first transition reads a trusted amount and holds: the one on the note is never tried,
    # so untrusted data chose nothing. Trusted data still chooses the path.
    small = run_plan(
        first_holds(branching()),
        fields={
            "order_id": ORDER,
            "amount": sourced(Decimal(40), "system:opener"),
            "note": sourced("anything", "untrusted:customer"),
        },
        answers=[],
    )
    assert small.status == "succeeded"
    trusted = run_plan(
        branching(),
        fields={"order_id": ORDER, "note": sourced("other", "person:ana")},
        answers=[],
    )
    assert trusted.status == "failed"


def branching_case() -> dict[str, Any]:
    """A case whose plan step gives the plan the customer's note, and reaches `settled`, the
    milestone that closes it."""
    return {
        "case": "settle",
        "display": {"title": "Settle"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}},
            "note": {
                "type": "string",
                "display": {"title": "What the customer wrote"},
                "source": "untrusted:customer",
            },
        },
        "steps": {
            "settle": {
                "kind": "plan",
                "display": {"title": "Settle"},
                "plan": "check-only@1",
                "inputs": {"order_id": {"var": "order_id"}, "note": {"var": "note"}},
                "reaches": ["settled"],
            }
        },
        "milestones": {"settled": {"display": {"title": "Settled"}}},
        "closes_when": ["settled"],
    }


def test_a_plan_step_branching_on_untrusted_data_needs_attention() -> None:
    # The bug: the customer's "go" closed the case. Now the plan stops whatever the note says, the
    # step needs attention, and nothing is reached (brief, D17, D49).
    for said in ("go", "anything else"):
        run = run_case(
            branching_case(),
            file={"order_id": "ord-1", "note": said},
            answers=[],
            people={},
            plans={"check-only@1": branching()},
        )
        assert run.needs_attention == [
            (
                "settle#1: check-only@1 stopped: on done, the transition to paid reads note "
                "(untrusted:customer), and untrusted data can't choose a plan's path"
            )
        ]
        assert "reached settled" not in run.history
        assert not run.closed
