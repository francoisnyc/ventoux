"""A crude case runner for the tracer bullet: opens a case, plays answers, closes it.

Pure, like all of `ventoux.case`: no clock, no randomness, no I/O. Activities are passed in, so
every side effect happens outside this module.
"""

# TRACER: the whole runner is replaced by the case runtime in layer 8.

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ventoux.core.before_activity import checked_inputs
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import ExpressionError, evaluate, parse_expression
from ventoux.core.provenance import provenance

# Where the case file's first values came from: the system that opened the case (brief, D12).
OPENER = "system:opener"

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
    catalog: Catalog,
    implementations: Mapping[str, Activity],
    roles_of: Mapping[str, set[str]],
) -> Run:
    """Run the case `definition` from `file`, playing the scripted `answers` in order."""
    # The case file, plus each task's latest outcome as "<step>.outcome".
    values = {name: case_value(value) for name, value in file.items()}
    # Every value carries where it came from (brief, D12): the opening system, or who answered.
    sources = {name: frozenset({OPENER}) for name in file}
    result = Run()
    # TRACER: `sequence` is walked in order; the case runtime (layer 8) admits steps by rules.
    for name in definition["sequence"]:
        step = definition["steps"][name]
        if step["kind"] == "task":
            answer_task(name, step, answer_for(name, answers), values, sources, roles_of)
        elif not decides(step.get("when"), values):
            continue  # not needed: its rule says it doesn't run
        elif needs_approval(step, values) and not approved(name, step, answers, sources, roles_of):
            roles = " or ".join(step["approval"]["roles"])
            result.waiting_for.append(f"approval of {name} by {roles}")
            break  # the step waits, and nothing after it starts
        else:
            # Fail closed: an activity the catalog doesn't hold stops the case (NotInCatalog).
            contract = catalog.get(step["activity"])
            # The check before an activity, as in a plan: every input policy against the real
            # sources, then the contract's input schema; a refusal raises InputRefused.
            # TRACER: the key `<step>#1` names no run (case runtime on Temporal, layer 8).
            # Each step runs once here; a case gets a workflow ID and run ID for its keys when
            # it runs as a workflow. Plans' keys name their run since layer 6.
            inputs = checked_inputs(
                contract,
                {key: parse_expression(expr) for key, expr in step["inputs"].items()},
                values,
                sources,
                f"{name}#1",
            )
            if contract.reference not in implementations:
                raise LookupError(f"no implementation of {contract.reference} is available")
            implementations[contract.reference](inputs)
        result.steps_reached.append(name)
    # A case closes when nothing is left to do (brief, D10): here, when no step is waiting.
    result.closed = not result.waiting_for
    return result


# TRACER: approvals and roles, replaced in layer 7 (design question 13 for the answer's shape).
def approved(
    name: str,
    step: dict[str, Any],
    answers: list[tuple[Any, ...]],
    sources: dict[str, frozenset[str]],
    roles_of: Mapping[str, set[str]],
) -> bool:
    """Whether the step's approval has been given by someone allowed to give it."""
    answer = next((a for a in answers if a[0] == name), None)
    if answer is None:
        return False
    _, outcome, person, *_ = answer
    require_role(person, step["approval"]["roles"], f"approve {name}", roles_of)
    # "Someone else" is computed, never listed (brief, D11): whoever's answer flows into the step,
    # through its inputs or its condition, may not approve it.
    used = [*step["inputs"].values(), *([step["when"]] if "when" in step else [])]
    flowed_in = frozenset().union(*(provenance(parse_expression(e), sources) for e in used))
    if f"person:{person}" in flowed_in:
        raise AnswerRefused(f"{person} set a value {name} uses, so cannot approve it")
    return bool(outcome == "approve")


def require_role(
    person: str, roles: list[str], action: str, roles_of: Mapping[str, set[str]]
) -> None:
    """Refuse `person` unless they have one of `roles` (the engine re-checks every answer)."""
    if not roles_of.get(person, set()) & set(roles):
        raise AnswerRefused(f"{person} cannot {action}: needs {' or '.join(roles)}")


def needs_approval(step: dict[str, Any], values: dict[str, Any]) -> bool:
    """Whether the step has an approval whose condition holds now."""
    return "approval" in step and decides(step["approval"]["when"], values)


def answer_for(step_name: str, answers: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    """The scripted answer to `step_name`."""
    return next(answer for answer in answers if answer[0] == step_name)


def answer_task(
    name: str,
    step: dict[str, Any],
    answer: tuple[Any, ...],
    values: dict[str, Any],
    sources: dict[str, frozenset[str]],
    roles_of: Mapping[str, set[str]],
) -> None:
    """Record a person's answer to a task, after checking it is one the task accepts."""
    _, outcome, person, *form = answer
    require_role(person, step["roles"], f"answer {name}", roles_of)
    # A task's outcomes are a closed list (brief, D9): anything else is refused, never guessed.
    if outcome not in step["outcomes"]:
        raise AnswerRefused(f"{name} has no outcome {outcome!r}")
    values[f"{name}.outcome"] = outcome
    sources[f"{name}.outcome"] = frozenset({f"person:{person}"})
    # An outcome sets only the case-file fields it declares (brief, D9).
    for field_name in step["outcomes"][outcome].get("sets", []):
        values[field_name] = case_value(form[0][field_name])
        sources[field_name] = frozenset({f"person:{person}"})


def decides(condition: Any, values: dict[str, Any]) -> bool:
    """A step's condition: `true` or `false`, or an error that stops the case. None: it runs."""
    if condition is None:
        return True
    # Fail closed: the expression is parsed (an unknown operator is refused) and evaluated (a
    # missing field is an error); anything but a boolean is an error too, never read as false.
    decided = evaluate(parse_expression(condition), values)
    if not isinstance(decided, bool):
        raise ExpressionError(f"a condition gives true or false, and this one gives {decided!r}")
    return decided


# TRACER: answers are read by their declared types in layer 7, the case file in layer 8. Here a
# whole number becomes the exact decimal expressions read, and anything else passes as is.
def case_value(value: Any) -> Any:
    """`value` as the case file holds it: a whole number as a `Decimal`."""
    return Decimal(value) if isinstance(value, int) and not isinstance(value, bool) else value
