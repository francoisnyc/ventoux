"""Run cases in memory, in tests: no Temporal server, scripted answers, fake activities."""

import json
from pathlib import Path
from typing import Any

from ventoux.case.runner import Activity, AnswerRefused, Run, run

__all__ = ["AnswerRefused", "load_definition", "run_case"]


def fake_refund(inputs: dict[str, Any]) -> dict[str, Any]:
    """`payments.refund@1` against a fake payment system: nothing is paid."""
    return {"refund_id": f"refund-{inputs['order_id']}"}


# TRACER: a hard-coded fake activity; the registry and its development activities come in layer 1.
FAKE_ACTIVITIES: dict[str, Activity] = {"payments.refund@1": fake_refund}


# TRACER: a fixed directory of people and roles; roles come with layer 7 (design question 12).
PEOPLE: dict[str, set[str]] = {"ana": {"support"}, "sam": {"support", "support-lead"}}


def load_definition(path: Path) -> dict[str, Any]:
    """Read a case definition from its JSON file (I/O, so here and not in `case`)."""
    definition: dict[str, Any] = json.loads(path.read_text())
    return definition


def run_case(
    definition: dict[str, Any],
    file: dict[str, Any],
    answers: list[tuple[Any, ...]],
) -> Run:
    """Open a case with `file`, play the scripted `answers`, and report where it ended."""
    return run(definition, file, answers, FAKE_ACTIVITIES, PEOPLE)
