"""Rules: on a moment, when a condition holds, then act on the case (layer 11a).

A rule reacts to a moment, never to a state: when its moment comes, it reads its condition on the
case file as it is then, once, and remembers nothing (brief, D38). What should start whenever a
state holds is a step's `requires` and `when`, which admission reads after every event.
See docs/layers/11-rules.md.
"""

from ventoux.case.admission import holds
from ventoux.case.definition import CaseDefinition, Reached, Rule, Started
from ventoux.case.state import CaseState, RuleFiring


def said(moment: object) -> str:
    """A rule's moment as the history says it: `opened`, `started pay`, `reached checked`."""
    if isinstance(moment, Started):
        return f"started {moment.started}"
    if isinstance(moment, Reached):
        return f"reached {moment.reached}"
    return "opened"


def reach(state: CaseState, milestones: tuple[str, ...]) -> None:
    """Record each milestone reached: a fact, never undone, and a moment for rules."""
    for milestone in milestones:
        if milestone not in state.milestones:
            state.milestones.append(milestone)
            state.history.append(f"reached {milestone}")
            state.moments.append(f"reached {milestone}")


def fire_rules(case: CaseDefinition, state: CaseState) -> None:
    """Take each moment in the order it came, and fire the rules on it in the order they are
    written. A milestone a rule reaches is a moment too, so rules can follow rules (brief, D38)."""
    while state.moments:
        moment = state.moments.pop(0)
        for name, rule in case.rules.items():
            if said(rule.on) == moment:
                fire(state, name, rule, moment)


def fire(state: CaseState, name: str, rule: Rule, moment: str) -> None:
    """One firing: read the condition on the case file now, then reach what the rule reaches."""
    entry = f"{name}#{sum(1 for firing in state.firings if firing.rule == name) + 1}"
    state.firings.append(RuleFiring(entry, name, moment, "done"))
    if rule.when is not None and not holds(rule.when, state.values, f"{name}'s condition"):
        state.history.append(f"{entry} on {moment}: its condition is false")
        return
    state.history.append(f"{entry} on {moment}: reaching {' and '.join(rule.then.reach)}")
    reach(state, rule.then.reach)
