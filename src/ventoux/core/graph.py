"""A plan as a graph: its transitions as arrows, and searches along them.

`validate` uses these to prove what holds on every path: every state reachable, the plan able to
end, every high-risk activity behind an approval.
"""

from dataclasses import dataclass

from ventoux.core.plan import FinalState, Plan


@dataclass(frozen=True)
class Arrow:
    """One transition seen as an arrow of the graph: from a state, on an event, to a state."""

    source: str  # the state it leaves
    event: str  # what happened there: `done`, an outcome, `timeout`
    target: str  # the state it enters


def arrows(plan: Plan) -> list[Arrow]:
    """Every transition whose target is a state (an unknown target is already an issue)."""
    found = []
    for name, state in plan.states.items():
        if isinstance(state, FinalState):
            continue
        for event, transitions in state.on.items():
            # A condition is a fork the validator can't see through: every branch may run.
            found += [Arrow(name, event, t.target) for t in transitions if t.target in plan.states]
    return found


def reach(starts: set[str], through: list[Arrow], backwards: bool = False) -> set[str]:
    """Every state reachable from `starts` along `through`, `starts` included; `backwards` follows
    each arrow from its target to its source, so it finds the states that can reach `starts`."""
    seen = set(starts)
    waiting = list(starts)
    while waiting:
        here = waiting.pop()
        for arrow in through:
            source, target = (
                (arrow.target, arrow.source) if backwards else (arrow.source, arrow.target)
            )
            if source == here and target not in seen:
                seen.add(target)
                waiting.append(target)
    return seen


def shortest_path(start: str, goal: str, through: list[Arrow]) -> list[str]:
    """The fewest states from `start` to `goal` along `through`, both included; `goal` must be
    reachable. Searched breadth first: nearer states before farther ones."""
    came_from: dict[str, str] = {}
    waiting = [start]
    seen = {start}
    while waiting:
        here = waiting.pop(0)
        if here == goal:
            break
        for arrow in through:
            if arrow.source == here and arrow.target not in seen:
                seen.add(arrow.target)
                came_from[arrow.target] = here
                waiting.append(arrow.target)
    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    return path[::-1]
