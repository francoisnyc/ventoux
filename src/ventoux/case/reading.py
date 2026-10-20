"""Reading rules: each rule in plain words, worked out from the definition alone (layer 11g1).

A reading is never given a case file, so it can't quote a value from one: the constants it shows
are the rule's own (brief, D45). It names steps, milestones and events as the history does, so a
firing and its reading, side by side, use the same words.
See docs/layers/11-rules.md (11g).
"""

from dataclasses import dataclass

from ventoux.case.definition import (
    After,
    AnsweredTask,
    CaseDefinition,
    EventArrived,
    Reached,
    Rule,
    Started,
    Then,
)
from ventoux.core.expressions import Expression, ExpressionInvalid, render


class ReadingRefused(Exception):
    """A rule the reader can't read whole: never read with a part left out (fail closed)."""


@dataclass(frozen=True)
class Reading:
    """A rule in plain words: its name and title, and its sentence."""

    name: str  # the rule's name, as the history says it
    title: str  # the rule's own title
    sentence: str  # its moment, its condition and what it does

    def __str__(self) -> str:
        return f"{self.name}: {self.title}\n  {self.sentence}"


def read_rules(case: CaseDefinition) -> list[Reading]:
    """Each of `case`'s rules in plain words, in the order they are written."""
    return [read_rule(name, rule) for name, rule in case.rules.items()]


def read_rule(name: str, rule: Rule) -> Reading:
    """One rule in plain words: `When checked is reached …: reach high_risk.`"""
    moment = when(name, rule.on)
    if rule.when is not None:
        # A rule remembers nothing: its condition is read when it fires (brief, D38), a timer's
        # when the timer fires, never when it is set (brief, D44).
        read = "the timer fires, not when it is set" if isinstance(rule.on, After) else "it fires"
        moment += f", if {expression(name, 'condition', rule.when)} (read when {read})"
    sentence = f"{moment[0].upper()}{moment[1:]}: {', then '.join(actions(name, rule.then))}."
    return Reading(name, rule.display.title, sentence)


def when(name: str, on: object) -> str:
    """When the rule fires: `when checked is reached …`, `2d after each run of review starts`."""
    if isinstance(on, After):
        return f"{on.after} after {after(name, on.since)}"
    if on == "opened":
        return "when the case opens"
    if isinstance(on, Reached):
        return f"when {on.reached} is reached (once: a milestone is never undone)"
    if isinstance(on, Started):
        return f"each time a run of {on.started} starts"
    if isinstance(on, AnsweredTask):
        return f"each time {on.answered} is answered, whatever the outcome"
    if isinstance(on, EventArrived):
        return f"each time {on.event} arrives"
    raise unknown(name, on)


def after(name: str, since: object) -> str:
    """What a timer waits after: `each run of review starts`, `checked is reached …`."""
    if since == "opened":
        return "the case opens"
    if isinstance(since, Reached):
        return f"{since.reached} is reached (once: a milestone is never undone)"
    if isinstance(since, Started):
        return f"each run of {since.started} starts"
    if isinstance(since, AnsweredTask):
        return f"each answer to {since.answered}, whatever the outcome"
    if isinstance(since, EventArrived):
        return f"each arrival of {since.event}"
    # A timer is never set on a timer (brief, D44): one here is a moment the reader doesn't know.
    raise unknown(name, since)


def unknown(name: str, moment: object) -> ReadingRefused:
    """Fail closed: a moment the reader doesn't know is refused, never read as another one."""
    return ReadingRefused(f"can't read {name}'s moment {moment!r}: it isn't a moment Ventoux knows")


# What a rule may do, in the order the engine does it: stop, set, reach, start (brief, D40)
# (brief, D42). A closed list: a new action is a decision recorded in the brief.
ACTIONS = ("stop", "set", "reach", "start")


def actions(name: str, then: Then) -> list[str]:
    """What the rule does, each action in the engine's order: `stop review`, `reach paid`."""
    for action in type(then).model_fields:
        # Fail closed: an action the reader doesn't know is refused, never left out.
        if action not in ACTIONS:
            raise ReadingRefused(
                f"can't read {name}'s then.{action}: it isn't an action Ventoux knows"
            )
    done: list[str] = []
    if then.stop:
        done.append(f"stop {' and '.join(then.stop)}")
    if then.set:
        values = (
            f"{field} to {expression(name, f'value of {field}', v)}"
            for field, v in then.set.items()
        )
        done.append(f"set {', '.join(values)}")
    if then.reach:
        done.append(f"reach {' and '.join(then.reach)}")
    if then.start:
        done.append(f"start {' and '.join(then.start)}")
    return done


def expression(name: str, what: str, written: Expression) -> str:
    """An expression of the rule, on one line as the expression renderer writes it (layer 2)."""
    try:
        return render(written)
    except ExpressionInvalid as refused:
        raise ReadingRefused(f"can't read {name}'s {what}: {refused}") from None
