"""The deterministic interpreter: running a plan in memory (layer 5).

Tests go through `run_plan`, the in-memory driver, and read what a run reports. See
docs/layers/05-interpreter.md and docs/guides/plans.md, "Running a plan".
"""

from typing import Any

import pytest

from ventoux.core.interpreter import Outcome, PlanRun, RunRefused
from ventoux.core.provenance import sourced
from ventoux.testing import Activity, run_plan


def ending_at_once() -> dict[str, Any]:
    """The smallest plan: one field, and a start that is already the end."""
    return {
        "plan": "at-once",
        "version": 1,
        "display": {"title": "Ends at once"},
        "fields": {"amount": {"type": "number"}},
        "initial": "done",
        "states": {"done": {"final": "succeeded"}},
    }


def test_a_run_needs_every_field_with_its_sources() -> None:
    with pytest.raises(RunRefused, match="amount comes with no sources"):
        run_plan(ending_at_once(), fields={"amount": sourced(250)}, answers=[])


def test_case_is_not_a_source_at_runtime() -> None:
    # `case` stands in for "the case vouches for it" in the static check only; at runtime a value
    # comes from where it really came from.
    with pytest.raises(RunRefused, match="amount comes from case"):
        run_plan(ending_at_once(), fields={"amount": sourced(250, "case")}, answers=[])


def test_a_run_needs_exactly_the_declared_fields() -> None:
    with pytest.raises(RunRefused, match="amount is missing"):
        run_plan(ending_at_once(), fields={}, answers=[])
    with pytest.raises(RunRefused, match="amout is not a field of at-once: its fields are amount"):
        run_plan(
            ending_at_once(),
            fields={"amount": sourced(250, "system:opener"), "amout": sourced(1, "system:opener")},
            answers=[],
        )


def test_a_run_ends_as_its_final_state_says() -> None:
    run = run_plan(ending_at_once(), fields={"amount": sourced(250, "system:opener")}, answers=[])
    assert run.status == "succeeded"
    assert [str(event) for event in run.history] == [
        "started at-once@1",
        "entered done",
        "ended succeeded",
    ]


def looking_up(**changes: Any) -> dict[str, Any]:
    """A plan that looks an order up: found, it succeeds; not found, it fails."""
    look = {
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "on": {"done": "found", "not_found": "missing"},
    }
    return {
        "plan": "look-up",
        "version": 1,
        "display": {"title": "Look an order up"},
        "fields": {"order_id": {"type": "reference", "system": "orders"}},
        "initial": "look",
        "states": {
            "look": {**look, **changes},
            "found": {"final": "succeeded"},
            "missing": {"final": "failed"},
        },
    }


ORDER = {"order_id": sourced("A-1001", "system:orders")}


def test_an_activity_the_catalog_does_not_hold_stops_the_step() -> None:
    run = run_plan(looking_up(activity="orders.lookup@9"), fields=ORDER, answers=[])
    assert run.status == "stopped"
    assert run.reason is not None and "orders.lookup@9 is not in the catalog" in run.reason


def failing(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("the orders system is down")


def test_an_activity_failure_stops_the_step() -> None:
    run = run_plan(looking_up(), fields=ORDER, answers=[], activities={"orders.lookup@1": failing})
    assert run.status == "stopped"
    assert run.reason == "orders.lookup@1 failed: the orders system is down"


def lines(run: PlanRun) -> list[str]:
    """The run's history, one line per event."""
    return [str(event) for event in run.history]


def test_done_moves_on_with_the_evaluated_inputs() -> None:
    received: list[dict[str, Any]] = []

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        received.append(inputs)
        return {"status": "delivered"}

    run = run_plan(looking_up(), fields=ORDER, answers=[], activities={"orders.lookup@1": lookup})
    assert run.status == "succeeded"
    assert received == [{"order_id": "A-1001"}]
    assert lines(run)[-4:] == [
        "orders.lookup@1 gave done",
        "moved on done to found",
        "entered found",
        "ended succeeded",
    ]


def giving(outcome: str) -> Activity:
    """A fake activity that answers with `outcome`, as a business failure."""

    def activity(inputs: dict[str, Any]) -> dict[str, Any]:
        raise Outcome(outcome)

    return activity


def test_an_outcome_the_contract_does_not_declare_stops_the_step() -> None:
    lost = {"orders.lookup@1": giving("lost")}
    run = run_plan(looking_up(), fields=ORDER, answers=[], activities=lost)
    assert run.status == "stopped"
    assert run.reason == (
        "orders.lookup@1 gave the outcome lost, which its contract doesn't declare: "
        "its outcomes are not_found"
    )


def test_a_declared_outcome_moves_on() -> None:
    not_found = {"orders.lookup@1": giving("not_found")}
    run = run_plan(looking_up(), fields=ORDER, answers=[], activities=not_found)
    assert run.status == "failed"
    assert lines(run)[-4:] == [
        "orders.lookup@1 gave not_found",
        "moved on not_found to missing",
        "entered missing",
        "ended failed",
    ]


def test_an_output_the_contract_does_not_declare_stops_the_step() -> None:
    misnamed = {"orders.lookup@1": lambda inputs: {"state": "delivered"}}
    run = run_plan(looking_up(), fields=ORDER, answers=[], activities=misnamed)
    assert run.status == "stopped"
    assert run.reason == (
        "orders.lookup@1 gave an output its contract doesn't declare: status: Field required"
    )


def test_what_the_plan_does_not_say_stops_the_step() -> None:
    to_nowhere = looking_up(on={"done": "fuond", "not_found": "missing"})
    run = run_plan(to_nowhere, fields=ORDER, answers=[])
    assert run.status == "stopped"
    assert lines(run)[-1] == (
        "stopped at fuond: fuond is not a state of look-up: the states are found, look, "
        "missing: the step needs attention, and nothing after it runs"
    )

    unhandled = looking_up(on={"done": "found"})  # not_found has nowhere to go
    run = run_plan(
        unhandled, fields=ORDER, answers=[], activities={"orders.lookup@1": giving("not_found")}
    )
    assert run.status == "stopped"
    assert run.reason == "on not_found, look says nowhere to go"
