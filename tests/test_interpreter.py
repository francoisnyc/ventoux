"""The deterministic interpreter: running a plan in memory (layer 5).

Tests go through `run_plan`, the in-memory driver, and read what a run reports. See
docs/layers/05-interpreter.md and docs/guides/plans.md, "Running a plan".
"""

from typing import Any

import pytest

from ventoux.core.interpreter import RunRefused
from ventoux.core.provenance import sourced
from ventoux.testing import run_plan


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
