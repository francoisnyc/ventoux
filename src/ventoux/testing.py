"""Run cases in memory, in tests: no Temporal server, scripted answers, fake activities."""

import json
from pathlib import Path
from typing import Any

from ventoux.case.runner import AnswerRefused, run

__all__ = ["AnswerRefused", "load_definition", "run_case"]


def load_definition(path: Path) -> dict[str, Any]:
    """Read a case definition from its JSON file (I/O, so here and not in `case`)."""
    definition: dict[str, Any] = json.loads(path.read_text())
    return definition


def run_case(
    definition: dict[str, Any],
    file: dict[str, Any],
    answers: list[tuple[Any, ...]],
) -> None:
    """Open a case with `file`, play the scripted `answers`, and report where it ended."""
    run(definition, file, answers)
