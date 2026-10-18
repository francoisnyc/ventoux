"""Rules: on a moment, when a condition holds, then act on the case (layer 11a).

A rule reacts to a moment, never to a state: when its moment comes, it reads its condition on the
case file as it is then, once, and remembers nothing (brief, D38). What should start whenever a
state holds is a step's `requires` and `when`, which admission reads after every event.
See docs/layers/11-rules.md.
"""

from ventoux.case.admission import StepStopped, holds
from ventoux.case.closing import close_held
from ventoux.case.definition import AnsweredTask, CaseDefinition, Reached, Started
from ventoux.case.state import CaseState, RuleFiring
from ventoux.case.types import rule_problem
from ventoux.case.writers import writers_of
from ventoux.core.catalog import Catalog
from ventoux.core.provenance import fields_read, is_trusted


def said(moment: object) -> str:
    """A rule's moment as the history says it: `opened`, `started pay`, `reached checked`,
    `answered review`. A moment it doesn't know is an error, never read as the opening (fail
    closed)."""
    if isinstance(moment, Started):
        return f"started {moment.started}"
    if isinstance(moment, Reached):
        return f"reached {moment.reached}"
    if isinstance(moment, AnsweredTask):
        return f"answered {moment.answered}"
    if moment == "opened":
        return "opened"
    raise ValueError(f"{moment!r} is not a moment Ventoux knows")


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
    if (stopped := nothing_decided(case, state)) is not None:
        state.history.append(f"{entry} on {moment}: not applied: {stopped}")
        return
    try:
        decided = read(case, catalog, state, name)
    except StepStopped as unreadable:
        # Fail closed: a condition that can't be read is never false. The rule acts on nothing
        # and waits for a person, keeping the case open (brief, D17) (brief, D38).
        firing.status, firing.reason = "failed", str(unreadable)
        state.history.append(f"{entry} failed: {firing.reason}")
        return
    act(case, catalog, state, firing, decided)


def read(case: CaseDefinition, catalog: Catalog, state: CaseState, name: str) -> bool:
    """Whether the rule's condition holds on the case file now (no condition: it does), or
    `StepStopped` saying why it can't be read."""
    # Checked over the case's types first, so a misspelt outcome fails it instead of reading as
    # false (brief, D35).
    if (problem := rule_problem(case, catalog, name)) is not None:
        raise StepStopped(problem)
    when = case.rules[name].when
    return when is None or holds(when, state.values, f"{name}'s condition")


def act(
    case: CaseDefinition, catalog: Catalog, state: CaseState, firing: RuleFiring, decided: bool
) -> None:
    """Do what the rule says, if its condition held and read only trusted values; say so either
    way."""
    firing.status, firing.reason = "done", ""
    if (stopped := nothing_decided(case, state)) is not None:  # a retry while the close is held
        state.history.append(f"{firing.entry} on {firing.moment}: not applied: {stopped}")
        return
    # Untrusted data informs; it never decides. Reaching a milestone decides for the case, so a
    # condition reading an untrusted value stops it whatever it gave (brief, D38). The message
    # names the value and its source, never the value (brief, D30).
    if (untrusted := untrusted_read(case, catalog, state, firing.rule)) is not None:
        state.history.append(
            f"{firing.entry} on {firing.moment}: reaches nothing: its condition reads {untrusted}, "
            "and untrusted data can't decide"
        )
        return
    if not decided:
        state.history.append(f"{firing.entry} on {firing.moment}: its condition is false")
        return
    reaches = case.rules[firing.rule].then.reach
    state.history.append(f"{firing.entry} on {firing.moment}: reaching {' and '.join(reaches)}")
    reach(state, reaches)


def nothing_decided(case: CaseDefinition, state: CaseState) -> str | None:
    """Why no rule acts now, or None: once every `closes_when` milestone is reached, even while a
    failed run holds the close, or once the case is closing, nothing new is decided
    (brief, D34) (brief, D38)."""
    if close_held(case, state) or (
        state.phase != "open"
        and case.closes_when
        and set(case.closes_when) <= set(state.milestones)
    ):
        names = " and ".join(case.closes_when)
        verb = "are" if len(case.closes_when) > 1 else "is"
        return f"{names} {verb} reached, so the case closes and nothing new is decided"
    if state.phase != "open":
        return f"the case is {state.phase}, so nothing new is decided"
    return None


def untrusted_read(
    case: CaseDefinition, catalog: Catalog, state: CaseState, name: str
) -> str | None:
    """The first value the rule's condition reads from a source the engine doesn't trust, said as
    `kyc.analyst_notes, from untrusted:llm`; None if it reads only trusted ones."""
    when = case.rules[name].when
    could: dict[str, frozenset[str]] | None = None
    for field in [] if when is None else fields_read(when):
        sources = state.sources.get(field)
        if sources is None:
            # Nobody has set it yet, so nothing recorded where it came from: it counts what any
            # of its writers could give, never "no sources" (fail closed) (brief, D39).
            could = could if could is not None else writers_of(case, catalog, state.opened_by)
            sources = could.get(field, frozenset({f"no known source for {field}"}))
        untrusted = sorted(source for source in sources if not is_trusted(source))
        if untrusted:
            return f"{field}, from {', '.join(untrusted)}"
    return None


def retry_rule(
    case: CaseDefinition, catalog: Catalog, state: CaseState, firing: RuleFiring, said: str
) -> None:
    """An operator retries a failed rule: its condition is read again, on the case file as it is
    now, for the same moment; `StepStopped` if it still can't be (brief, D26) (brief, D38). `said` is the
    history's line for the retry, written once the condition is read."""
    decided = read(case, catalog, state, firing.rule)
    state.history.append(said)
    act(case, catalog, state, firing, decided)
