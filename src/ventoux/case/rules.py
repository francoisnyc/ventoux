"""Rules: on a moment, when a condition holds, then act on the case (layer 11a).

A rule reacts to a moment, never to a state: when its moment comes, it reads its condition on the
case file as it is then, once, and remembers nothing (brief, D38). What should start whenever a
state holds is a step's `requires` and `when`, which admission reads after every event.
See docs/layers/11-rules.md.
"""

from typing import NoReturn

from ventoux.case.admission import StepStopped, holds
from ventoux.case.closing import close_held
from ventoux.case.definition import AnsweredTask, CaseDefinition, EventArrived, Reached, Started
from ventoux.case.state import CaseState, Command, Obtained, RuleFiring, RuleStart
from ventoux.case.stopping import stop_step
from ventoux.case.types import rule_problem
from ventoux.case.writers import read_sources, untrusted_of
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import ExpressionError, OutcomeType, a_kind, evaluate, render
from ventoux.core.expressions.check import a_type
from ventoux.core.form import fits
from ventoux.core.sensitive import Sensitive, plain
from ventoux.core.sensitive_inputs import reads_sensitive


def said(moment: object) -> str:
    """A rule's moment as the history says it: `opened`, `started pay`, `reached checked`,
    `answered review`, `event cancelled`. A moment it doesn't know is an error, never read as the
    opening (fail closed)."""
    if isinstance(moment, Started):
        return f"started {moment.started}"
    if isinstance(moment, Reached):
        return f"reached {moment.reached}"
    if isinstance(moment, AnsweredTask):
        return f"answered {moment.answered}"
    if isinstance(moment, EventArrived):
        return f"event {moment.event}"
    if moment == "opened":
        return "opened"
    unknown_moment(moment)


def unknown_moment(moment: object) -> NoReturn:
    """Refuse a moment Ventoux doesn't know, wherever one is read: never read as the opening, or
    as one that can come (fail closed). `parse_case` refuses it first; this is for a definition
    that didn't come through it."""
    raise ValueError(f"{moment!r} is not a moment Ventoux knows")


def reach(state: CaseState, milestones: tuple[str, ...]) -> None:
    """Record each milestone reached: a fact, never undone, and a moment for rules."""
    for milestone in milestones:
        if milestone not in state.milestones:
            state.milestones.append(milestone)
            state.history.append(f"reached {milestone}")
            state.moments.append(f"reached {milestone}")


def fire_rules(
    case: CaseDefinition, catalog: Catalog, state: CaseState, commands: list[Command], at: int
) -> None:
    """Take each moment in the order it came, and fire the rules on it in the order they are
    written. A milestone a rule reaches is a moment too, so rules can follow rules (brief, D38).
    A stop may ask for a command: a plan's stop, a workflow's cancellation (brief, D40); `at`,
    the time of the event being decided, is what a stop measures facts' ages against."""
    while state.moments:
        moment = state.moments.pop(0)
        for name, rule in case.rules.items():
            if said(rule.on) == moment:
                fire(case, catalog, state, name, moment, commands, at)


def fire(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    moment: str,
    commands: list[Command],
    at: int,
) -> None:
    """One firing: read the condition on the case file now, then act on what it says."""
    entry = f"{name}#{sum(1 for firing in state.firings if firing.rule == name) + 1}"
    firing = RuleFiring(entry, name, moment, "done")
    state.firings.append(firing)
    if (stopped := nothing_decided(case, state)) is not None:
        state.history.append(f"{entry} on {moment}: not applied: {stopped}")
        return
    try:
        decided, computed = read(case, catalog, state, name)
    except StepStopped as unreadable:
        # Fail closed: a condition that can't be read is never false. The rule acts on nothing
        # and waits for a person, keeping the case open (brief, D17) (brief, D38).
        firing.status, firing.reason = "failed", str(unreadable)
        state.history.append(f"{entry} failed: {firing.reason}")
        return
    act(case, catalog, state, firing, decided, computed, commands, at)


def read(
    case: CaseDefinition, catalog: Catalog, state: CaseState, name: str
) -> tuple[bool, dict[str, object]]:
    """Whether the rule's condition holds on the case file now (no condition: it does), and, if it
    does, each value it sets; or `StepStopped` saying why it can't be read. Every value is computed
    before anything acts, so a rule acts whole or not at all (brief, D42)."""
    # Checked over the case's types first, so a misspelt outcome fails it instead of reading as
    # false (brief, D35).
    if (problem := rule_problem(case, catalog, name)) is not None:
        raise StepStopped(problem)
    rule = case.rules[name]
    if rule.when is not None and not holds(rule.when, state.values, f"{name}'s condition"):
        return False, {}
    # Read on the case file as the condition saw it, so the order of `set`'s keys doesn't matter.
    return True, {field: computed(case, state.values, name, field) for field in rule.then.set}


def computed(case: CaseDefinition, values: dict[str, object], name: str, field: str) -> object:
    """The value the rule `name` sets `field` to, or `StepStopped`: one that can't be read, or isn't
    of the field's type, is never written (fail closed). Messages name the field and the kind of
    value, never the value (brief, D30)."""
    expression = case.rules[name].then.set[field]
    whose = f"{name}'s {field}"
    try:
        value = evaluate(expression, values)
    except ExpressionError as error:
        raise StepStopped(f"{whose} {render(expression)} can't be evaluated: {error}") from None
    declared = case.fields[field].declared
    if not fits(plain(value), declared):
        if isinstance(declared, OutcomeType) and isinstance(plain(value), str):
            outcomes = " or ".join(declared.outcomes)
            raise StepStopped(f"{whose} gives a text that is none of its outcomes: {outcomes}")
        raise StepStopped(f"{whose} gives {a_kind(value)}, and {field} is {a_type(declared)}")
    # Kept wrapped if it is sensitive, or computed from a sensitive value (brief, D31).
    if case.fields[field].sensitive or reads_sensitive(expression, values):
        return value if isinstance(value, Sensitive) else Sensitive(value)
    return value


def act(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    firing: RuleFiring,
    decided: bool,
    computed: dict[str, object],
    commands: list[Command],
    at: int,
) -> None:
    """Do what the rule says, if its condition held and read only trusted values; say so either
    way. Stop first, then set, then reach, then start (brief, D40) (brief, D42). `computed` holds
    each value it sets, read before anything acts."""
    firing.status, firing.reason = "done", ""
    if (stopped := nothing_decided(case, state)) is not None:  # a retry while the close is held
        state.history.append(f"{firing.entry} on {firing.moment}: not applied: {stopped}")
        return
    then = case.rules[firing.rule].then
    # Untrusted data informs; it never decides. Reaching a milestone, or stopping a step, decides
    # for the case, so a condition reading an untrusted value stops the rule whatever it gave, its
    # starts included (brief, D38) (brief, D40). A rule that only starts steps acts: what it read
    # counts for their inputs' policies (brief, D39). The message names the value and its source,
    # never the value (brief, D30).
    untrusted = untrusted_read(case, catalog, state, firing.rule)
    if (then.reach or then.stop) and untrusted is not None:
        acts = (("reaches", then.reach), ("starts", then.start), ("stops", then.stop))
        verbs = [verb for verb, does in acts if does]  # `reaches and starts`, `stops`
        does = " and ".join([", ".join(verbs[:-1]), verbs[-1]] if len(verbs) > 1 else verbs)
        state.history.append(
            f"{firing.entry} on {firing.moment}: {does} nothing: its condition reads "
            f"{untrusted}, and untrusted data can't decide"
        )
        return
    if not decided:
        state.history.append(f"{firing.entry} on {firing.moment}: its condition is false")
        return
    if then.stop:
        # At once, so the rules after it and admission's next round see the stopped run.
        said = f"{firing.entry} on {firing.moment}"
        state.history.append(f"{said}: stopping {' and '.join(then.stop)}")
        for step in then.stop:
            stop_step(case, catalog, state, step, firing.entry, said, commands, at)
    for field, value in computed.items():
        write(case, catalog, state, firing, field, value, at)
    if then.reach:
        state.history.append(
            f"{firing.entry} on {firing.moment}: reaching {' and '.join(then.reach)}"
        )
        reach(state, then.reach)
    # Each start is the engine's proposal, with what the condition read now: admission decides,
    # once the rules on this moment have fired (brief, D39).
    read = read_sources(case, catalog, state, case.rules[firing.rule].when)
    for step in then.start:
        state.rule_starts.append(
            RuleStart(firing.entry, firing.moment, step, people_in(read), untrusted_of(read))
        )


def write(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    firing: RuleFiring,
    field: str,
    value: object,
    at: int,
) -> None:
    """Write a value the rule set: it comes from everything its rule read, its value and its
    condition, plus the field's mark; it is as old as the oldest fact it read, obtained by the
    firing, never "now" (brief, D33) (brief, D42). The line names the field and the sources, never
    the value (brief, D30)."""
    rule = case.rules[firing.rule]
    read: dict[str, frozenset[str]] = {}
    for expression in (rule.then.set[field], rule.when):
        read |= read_sources(case, catalog, state, expression)
    mark = case.fields[field].source
    sources = frozenset().union(*read.values(), {mark} if mark else set())
    ages = [state.obtained[name].at for name in read if name in state.obtained]
    state.values[field] = value
    state.sources[field] = sources
    state.obtained[field] = Obtained(min(ages, default=at), firing.entry)
    state.history.append(
        f"{firing.entry} on {firing.moment}: setting {field}, from {', '.join(sorted(sources))}"
    )


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


def people_in(read: dict[str, frozenset[str]]) -> dict[str, str]:
    """Each person whose answer a condition read, and the first field of theirs it read."""
    people: dict[str, str] = {}
    for field, sources in read.items():
        for source in sorted(sources):
            if source.startswith("person:"):
                people.setdefault(source.removeprefix("person:"), field)
    return people


def untrusted_read(
    case: CaseDefinition, catalog: Catalog, state: CaseState, name: str
) -> str | None:
    """The first value the rule's condition reads from a source the engine doesn't trust, said as
    `kyc.analyst_notes, from untrusted:llm`; None if it reads only trusted ones."""
    read = read_sources(case, catalog, state, case.rules[name].when)
    for field, untrusted in untrusted_of(read).items():
        return f"{field}, from {', '.join(sorted(untrusted))}"
    return None


def retry_rule(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    firing: RuleFiring,
    said: str,
    commands: list[Command],
    at: int,
) -> None:
    """An operator retries a failed rule: its condition is read again, on the case file as it is
    now, for the same moment; `StepStopped` if it still can't be (brief, D26) (brief, D38). `said` is the
    history's line for the retry, written once the condition is read."""
    decided, computed = read(case, catalog, state, firing.rule)
    state.history.append(said)
    act(case, catalog, state, firing, decided, computed, commands, at)
