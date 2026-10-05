"""Static validation: what can be proven about a plan by reading it, before anything runs.

`parse_plan` checks a plan's shape; `validate` checks its meaning, reading the plan as a graph whose
arrows are the transitions in each state's `on`. It lists every problem at once. See
docs/guides/plans.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import ActivityContract
from ventoux.core.expressions import (
    BooleanType,
    Expression,
    ExpressionInvalid,
    FieldType,
    check,
)
from ventoux.core.expressions.check import a_type
from ventoux.core.plan import ActivityState, FinalState, Plan, Transition, WaitState

TIMEOUT = "timeout"  # the event of a wait's timeout, so never one of its outcomes


@dataclass(frozen=True)
class Issue:
    """One problem in a plan: where it is, which kind it is, and what to do about it."""

    path: str  # where in the plan, as layer 2 writes it: `states.pay.on.done[1]`
    code: str  # which rule it breaks, such as `UNKNOWN_TARGET`
    message: str  # what is wrong, then what to do


def validate(plan: Plan, catalog: Catalog) -> list[Issue]:
    """Every problem in `plan`, a parsed plan, read against the activities in `catalog`."""
    # Fail closed: anything but a parsed plan is refused, never read as a plan with no problems.
    if not isinstance(plan, Plan):
        raise TypeError(f"validate takes a parsed plan (see parse_plan), not {type(plan).__name__}")
    issues: list[Issue] = []
    if plan.initial not in plan.states:
        issues.append(Issue("initial", "UNKNOWN_TARGET", not_a_state(plan.initial, plan)))
    for name, state in plan.states.items():
        if isinstance(state, FinalState):
            continue  # a final state has no `on`: nowhere to go
        if isinstance(state, ActivityState):
            issues += activity_issues(f"states.{name}", state, catalog)
            for field, expression in state.inputs.items():
                issues += expression_issues(
                    f"states.{name}.inputs.{field}", expression, plan.fields
                )
        else:
            issues += wait_issues(f"states.{name}", name, state)
        for event, transitions in state.on.items():
            for path, transition in each_transition(f"states.{name}.on.{event}", transitions):
                if transition.target not in plan.states:
                    issues.append(
                        Issue(path, "UNKNOWN_TARGET", not_a_state(transition.target, plan))
                    )
                if transition.when is not None:
                    issues += expression_issues(
                        f"{path}.when", transition.when, plan.fields, condition=True
                    )
    return issues


def activity_issues(path: str, state: ActivityState, catalog: Catalog) -> list[Issue]:
    """What is wrong with an activity state, read against its contract in the catalog."""
    try:
        contract = catalog.get(state.activity)
    except NotInCatalog as missing:
        # The catalog's own message, which names the versions it does hold.
        return [Issue(f"{path}.activity", "UNKNOWN_ACTIVITY", str(missing))]
    # An activity gives `done`, or one of the business failures its contract declares (brief, D17).
    # Anything else that goes wrong needs a person, never a transition the plan takes on its own.
    events = ("done", *contract.outcomes)
    return input_issues(path, state, contract) + event_issues(
        path, state.on, events, gives=f"{contract.reference} never gives"
    )


def wait_issues(path: str, name: str, state: WaitState) -> list[Issue]:
    """What is wrong with a wait state: its outcomes, and the events its `on` handles."""
    issues: list[Issue] = []
    if TIMEOUT in state.wait.outcomes:
        issues.append(
            Issue(
                f"{path}.wait.outcomes",
                "RESERVED_OUTCOME",
                f"{TIMEOUT} is the event of a wait's timeout, not an outcome: "
                "name the outcome differently",
            )
        )
    # A wait gives one of its outcomes, or `timeout` when it declares one.
    timed = (
        (TIMEOUT,) if state.wait.timeout is not None and TIMEOUT not in state.wait.outcomes else ()
    )
    events = (*state.wait.outcomes, *timed)
    hint = "" if timed else f"; declare wait.timeout to wait for {TIMEOUT}"
    return issues + event_issues(
        path, state.on, events, gives=f"the wait {name} never gives", timeout_hint=hint
    )


def event_issues(
    path: str,
    on: Mapping[str, object],
    events: tuple[str, ...],
    gives: str,
    timeout_hint: str = "",
) -> list[Issue]:
    """`on` against the events a state can give: each handled, and nothing else."""
    issues: list[Issue] = []
    for event in on:
        if event not in events:
            hint = timeout_hint if event == TIMEOUT else ""
            issues.append(
                Issue(
                    f"{path}.on.{event}",
                    "UNKNOWN_EVENT",
                    f"{gives} {event}: its events are {', '.join(events)}{hint}",
                )
            )
    for event in events:
        if event not in on:
            issues.append(
                Issue(
                    f"{path}.on",
                    "MISSING_EVENT",
                    f"{event} is not handled: say where the plan goes on {event}",
                )
            )
    return issues


def input_issues(path: str, state: ActivityState, contract: ActivityContract) -> list[Issue]:
    """The state's inputs against the contract's input fields, the idempotency key aside."""
    issues: list[Issue] = []
    key = contract.idempotency_key
    # The engine fills the key, from the case, the step and its run, so retries reuse it and two
    # runs never share it (brief, D17). A plan may neither set it nor be asked for it.
    fields = {name: field for name, field in contract.input.model_fields.items() if name != key}
    for name in state.inputs:
        if name == key:
            issues.append(
                Issue(
                    f"{path}.inputs.{name}",
                    "ENGINE_INPUT",
                    f"{name} is filled by the engine, never by a plan: remove it",
                )
            )
        elif name not in fields:
            issues.append(
                Issue(
                    f"{path}.inputs.{name}",
                    "UNKNOWN_INPUT",
                    f"{contract.reference} has no input {name}: its inputs are "
                    f"{', '.join(sorted(fields))}",
                )
            )
    for name, field in fields.items():
        # Pydantic: `is_required()` is true for a field declared with no default.
        if field.is_required() and name not in state.inputs:
            issues.append(
                Issue(
                    f"{path}.inputs",
                    "MISSING_INPUT",
                    f"{contract.reference} needs the input {name}: add it to inputs",
                )
            )
    return issues


def expression_issues(
    path: str, expression: Expression, fields: Mapping[str, FieldType], condition: bool = False
) -> list[Issue]:
    """An expression checked against the plan's fields (layer 2's `check`); a condition must give a
    boolean. A plan binds no new values, so the fields are the same at every state."""
    try:
        found = check(expression, fields)
    except ExpressionInvalid as refused:
        # The check's own message, which starts with the path inside the expression (`>[1]`).
        return [Issue(path, "EXPRESSION_INVALID", str(refused))]
    if condition and not isinstance(found, BooleanType):
        # Nothing is truthy: a condition gives true or false, never a number read as one.
        return [
            Issue(
                path,
                "EXPRESSION_INVALID",
                f"a condition gives a boolean, and this gives {a_type(found)}: write a comparison, "
                "such as amount > 100",
            )
        ]
    return []


def each_transition(path: str, transitions: tuple[Transition, ...]) -> list[tuple[str, Transition]]:
    """Each transition with its path: `on.done` when it was written as a bare state name, else
    `on.done[1]` by its position in the list."""
    if len(transitions) == 1 and transitions[0].when is None:
        return [(path, transitions[0])]
    return [(f"{path}[{position}]", t) for position, t in enumerate(transitions)]


def not_a_state(name: str, plan: Plan) -> str:
    return f'"{name}" is not a state: the states are {", ".join(sorted(plan.states))}'
