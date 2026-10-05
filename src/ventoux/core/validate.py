"""Static validation: what can be proven about a plan by reading it, before anything runs.

`parse_plan` checks a plan's shape; `validate` checks its meaning, reading the plan as a graph whose
arrows are the transitions in each state's `on`. It lists every problem at once. See
docs/guides/plans.md.
"""

from dataclasses import dataclass

from ventoux.core.catalog import Catalog
from ventoux.core.plan import FinalState, Plan, Transition


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
        for event, transitions in state.on.items():
            for path, transition in each_transition(f"states.{name}.on.{event}", transitions):
                if transition.target not in plan.states:
                    issues.append(
                        Issue(path, "UNKNOWN_TARGET", not_a_state(transition.target, plan))
                    )
    return issues


def each_transition(path: str, transitions: tuple[Transition, ...]) -> list[tuple[str, Transition]]:
    """Each transition with its path: `on.done` when it was written as a bare state name, else
    `on.done[1]` by its position in the list."""
    if len(transitions) == 1 and transitions[0].when is None:
        return [(path, transitions[0])]
    return [(f"{path}[{position}]", t) for position, t in enumerate(transitions)]


def not_a_state(name: str, plan: Plan) -> str:
    return f'"{name}" is not a state: the states are {", ".join(sorted(plan.states))}'
