"""Rules: on a moment, when a condition holds, then act on the case (layer 11a).

A rule reacts to a moment, never to a state: when its moment comes, it reads its condition on the
case file as it is then, once, and remembers nothing (brief, D38). What should start whenever a
state holds is a step's `requires` and `when`, which admission reads after every event.
See docs/layers/11-rules.md.
"""

from ventoux.case.admission import StepStopped, holds
from ventoux.case.definition import CaseDefinition, Reached, Started
from ventoux.case.state import CaseState, RuleFiring
from ventoux.case.types import rule_problem
from ventoux.core.catalog import Catalog


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


def fire_rules(case: CaseDefinition, catalog: Catalog, state: CaseState) -> None:
    """Take each moment in the order it came, and fire the rules on it in the order they are
    written. A milestone a rule reaches is a moment too, so rules can follow rules (brief, D38)."""
    while state.moments:
        moment = state.moments.pop(0)
        for name, rule in case.rules.items():
            if said(rule.on) == moment:
                fire(case, catalog, state, name, moment)


def fire(case: CaseDefinition, catalog: Catalog, state: CaseState, name: str, moment: str) -> None:
    """One firing: read the condition on the case file now, then act on what it says."""
    entry = f"{name}#{sum(1 for firing in state.firings if firing.rule == name) + 1}"
    firing = RuleFiring(entry, name, moment, "done")
    state.firings.append(firing)
    try:
        decided = read(case, catalog, state, name)
    except StepStopped as unreadable:
        # Fail closed: a condition that can't be read is never false. The rule acts on nothing
        # and waits for a person, keeping the case open (brief, D17) (brief, D38).
        firing.status, firing.reason = "failed", str(unreadable)
        state.history.append(f"{entry} failed: {firing.reason}")
        return
    act(case, state, firing, decided)


def read(case: CaseDefinition, catalog: Catalog, state: CaseState, name: str) -> bool:
    """Whether the rule's condition holds on the case file now (no condition: it does), or
    `StepStopped` saying why it can't be read."""
    # Checked over the case's types first, so a misspelt outcome fails it instead of reading as
    # false (brief, D35).
    if (problem := rule_problem(case, catalog, name)) is not None:
        raise StepStopped(problem)
    when = case.rules[name].when
    return when is None or holds(when, state.values, f"{name}'s condition")


def act(case: CaseDefinition, state: CaseState, firing: RuleFiring, decided: bool) -> None:
    """Do what the rule says, if its condition held; say so either way."""
    firing.status, firing.reason = "done", ""
    if not decided:
        state.history.append(f"{firing.entry} on {firing.moment}: its condition is false")
        return
    reaches = case.rules[firing.rule].then.reach
    state.history.append(f"{firing.entry} on {firing.moment}: reaching {' and '.join(reaches)}")
    reach(state, reaches)


def retry_rule(
    case: CaseDefinition, catalog: Catalog, state: CaseState, firing: RuleFiring, said: str
) -> None:
    """An operator retries a failed rule: its condition is read again, on the case file as it is
    now, for the same moment; `StepStopped` if it still can't be (brief, D26) (brief, D38). `said` is the
    history's line for the retry, written once the condition is read."""
    decided = read(case, catalog, state, firing.rule)
    state.history.append(said)
    act(case, state, firing, decided)
