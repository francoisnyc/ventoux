"""A crude case runner for the tracer bullet: opens a case, plays answers, closes it.

Pure, like all of `ventoux.case`: no clock, no randomness, no I/O.
"""

# TRACER: the whole runner is replaced by the case runtime in layer 8.

from typing import Any


class AnswerRefused(Exception):
    """A person's answer the engine will not accept, with the reason."""


def run(definition: dict[str, Any], file: dict[str, Any], answers: list[tuple[Any, ...]]) -> None:
    """Run the case `definition` from `file`, playing the scripted `answers` in order."""
    for step_name, outcome, *_ in answers:
        step = definition["steps"][step_name]
        # A task's outcomes are a closed list (D9): anything else is refused, never guessed.
        if outcome not in step["outcomes"]:
            raise AnswerRefused(f"{step_name} has no outcome {outcome!r}")
