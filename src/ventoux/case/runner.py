"""A crude case runner for the tracer bullet: opens a case, plays answers, closes it.

Pure, like all of `ventoux.case`: no clock, no randomness, no I/O. Activities are passed in, so
every side effect happens outside this module.
"""

# TRACER: the whole runner is replaced by the case runtime in layer 8.

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

Activity = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class Run:
    """Where a case ended: closed or not, which steps ran, what it waits for."""

    closed: bool = False
    steps_reached: list[str] = field(default_factory=list[str])
    waiting_for: list[str] = field(default_factory=list[str])

    def reached(self, step: str) -> bool:
        return step in self.steps_reached


class AnswerRefused(Exception):
    """A person's answer the engine will not accept, with the reason."""


def run(
    definition: dict[str, Any],
    file: dict[str, Any],
    answers: list[tuple[Any, ...]],
    activities: Mapping[str, Activity],
    roles_of: Mapping[str, set[str]],
) -> Run:
    """Run the case `definition` from `file`, playing the scripted `answers` in order."""
    values = dict(file)  # the case file, plus each task's latest outcome as "<step>.outcome"
    # TRACER: who set each value, a crude stand-in for provenance tags (layer 4).
    set_by: dict[str, str] = {}
    result = Run()
    # TRACER: `sequence` is walked in order; the case runtime (layer 8) admits steps by rules.
    for name in definition["sequence"]:
        step = definition["steps"][name]
        if step["kind"] == "task":
            answer_task(name, step, answer_for(name, answers), values, set_by, roles_of)
        elif not holds(step.get("when"), values):
            continue  # not needed: its rule says it doesn't run
        elif needs_approval(step, values) and not approved(name, step, answers, set_by, roles_of):
            roles = " or ".join(step["approval"]["roles"])
            result.waiting_for.append(f"approval of {name} by {roles}")
            break  # the step waits, and nothing after it starts
        else:
            inputs = {key: evaluate(expr, values) for key, expr in step["inputs"].items()}
            # TRACER: activities are looked up by name; the registry (layer 1) checks contracts.
            activities[step["activity"]](inputs)
        result.steps_reached.append(name)
    # A case closes when nothing is left to do (D10): here, when no step is waiting.
    result.closed = not result.waiting_for
    return result


# TRACER: approvals and roles, replaced in layer 7 (design question 13 for the answer's shape).
def approved(
    name: str,
    step: dict[str, Any],
    answers: list[tuple[Any, ...]],
    set_by: dict[str, str],
    roles_of: Mapping[str, set[str]],
) -> bool:
    """Whether the step's approval has been given by someone allowed to give it."""
    answer = next((a for a in answers if a[0] == name), None)
    if answer is None:
        return False
    _, outcome, person, *_ = answer
    require_role(person, step["approval"]["roles"], f"approve {name}", roles_of)
    # "Someone else" is computed, never listed (D11): whoever set a value the step uses, in its
    # inputs or its condition, may not approve it.
    used = fields_read([*step["inputs"].values(), step.get("when")])
    if person in {set_by[f] for f in used if f in set_by}:
        raise AnswerRefused(f"{person} set a value {name} uses, so cannot approve it")
    return bool(outcome == "approve")


def require_role(
    person: str, roles: list[str], action: str, roles_of: Mapping[str, set[str]]
) -> None:
    """Refuse `person` unless they have one of `roles` (the engine re-checks every answer)."""
    if not roles_of.get(person, set()) & set(roles):
        raise AnswerRefused(f"{person} cannot {action}: needs {' or '.join(roles)}")


def fields_read(exprs: list[Any]) -> set[str]:
    """The case-file fields the expressions read."""
    found: set[str] = set()
    for expr in exprs:
        if isinstance(expr, dict) and "field" in expr:
            found.add(expr["field"])
        elif isinstance(expr, dict):
            for operands in expr.values():
                found |= fields_read(operands)
    return found


def needs_approval(step: dict[str, Any], values: dict[str, Any]) -> bool:
    """Whether the step has an approval whose condition holds now."""
    return "approval" in step and holds(step["approval"]["when"], values)


def answer_for(step_name: str, answers: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    """The scripted answer to `step_name`."""
    return next(answer for answer in answers if answer[0] == step_name)


def answer_task(
    name: str,
    step: dict[str, Any],
    answer: tuple[Any, ...],
    values: dict[str, Any],
    set_by: dict[str, str],
    roles_of: Mapping[str, set[str]],
) -> None:
    """Record a person's answer to a task, after checking it is one the task accepts."""
    _, outcome, person, *form = answer
    require_role(person, step["roles"], f"answer {name}", roles_of)
    # A task's outcomes are a closed list (D9): anything else is refused, never guessed.
    if outcome not in step["outcomes"]:
        raise AnswerRefused(f"{name} has no outcome {outcome!r}")
    values[f"{name}.outcome"] = outcome
    set_by[f"{name}.outcome"] = person
    # An outcome sets only the case-file fields it declares (D9).
    for field_name in step["outcomes"][outcome].get("sets", []):
        values[field_name] = form[0][field_name]
        set_by[field_name] = person


# TRACER: a minimal structured condition (`=`, `>`, `field`, literals), replaced by the
# expression language in layer 2 (design question 11). Plain code: never `eval`.
def evaluate(expr: Any, values: dict[str, Any]) -> Any:
    """The value of `expr` against the case file."""
    if isinstance(expr, dict) and "field" in expr:
        return values[expr["field"]]
    if isinstance(expr, dict) and "=" in expr:
        left, right = (evaluate(e, values) for e in expr["="])
        return left == right
    if isinstance(expr, dict) and ">" in expr:
        left, right = (evaluate(e, values) for e in expr[">"])
        return left > right
    return expr


def holds(condition: Any, values: dict[str, Any]) -> bool:
    """Whether a step's condition holds; no condition always holds."""
    return condition is None or evaluate(condition, values) is True
