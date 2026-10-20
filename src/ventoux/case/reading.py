"""Reading rules: each rule in plain words, worked out from the definition alone (layer 11g1).

A reading is never given a case file, so it can't quote a value from one: the constants it shows
are the rule's own (brief, D45). It names steps, milestones and events as the history does, so a
firing and its reading, side by side, use the same words.
See docs/layers/11-rules.md (11g).
"""

from dataclasses import dataclass
from typing import NamedTuple

from ventoux.case.definition import (
    After,
    AnsweredTask,
    CallStep,
    CaseDefinition,
    EventArrived,
    PlanStep,
    Reached,
    Rule,
    Started,
    Then,
)
from ventoux.core.expressions import Expression, ExpressionInvalid, render


class ReadingRefused(Exception):
    """A rule the reader can't read whole: never read with a part left out (fail closed)."""


# Each part of a rule's behaviour a reading may say, the parts people get wrong. A closed list:
# each has a witness, a test that runs the engine doing what it says (brief, D45).
CLAUSES = (
    "condition read when it fires",  # a rule remembers nothing (brief, D38)
    "timer's condition read when it fires",  # never when it is set (brief, D44)
    "actions in the engine's order",  # stop, set, reach, start (brief, D40) (brief, D42)
    "timer on a run",  # ends with its run; a failed run keeps it (brief, D40) (brief, D44)
    "timer on an instant",  # lives until it fires (brief, D44)
    "timer holds the case",  # pending work, cancelled by a close (brief, D10)
    "listening",  # a rule on an event holds nothing (brief, D41)
    "untrusted data decides nothing",  # on a rule that reaches or stops (brief, D38) (brief, D43)
    "set value carries what it read",  # setting informs, it never decides (brief, D42)
    "start checked against inputs",  # a start goes ahead, its inputs checked (brief, D39)
    "only while the case decides",  # not once closing, nor closes_when reached (brief, D38)
    "every rule",  # EVERY_RULE, said once above a definition's readings
)

# What holds for every rule, said once above a definition's readings rather than on each
# (brief, D17) (brief, D38).
EVERY_RULE = (
    "A rule remembers nothing: its condition is read once, when it fires. A rule whose condition "
    "or value can't be read acts on nothing, and needs attention."
)


class Clause(NamedTuple):
    """One part of a rule's behaviour, said in the fine print under its sentence."""

    kind: str  # one of CLAUSES
    text: str  # how it reads


@dataclass(frozen=True)
class Reading:
    """A rule in plain words: its name and title, its sentence, and the fine print that applies
    to it."""

    name: str  # the rule's name, as the history says it
    title: str  # the rule's own title
    sentence: str  # its moment, its condition and what it does
    fine_print: tuple[str, ...]  # each part people get wrong that applies to it, one per line
    clauses: tuple[str, ...]  # which of CLAUSES it says, in the sentence or the fine print

    def __str__(self) -> str:
        lines = [f"{self.name}: {self.title}", f"  {self.sentence}"]
        return "\n".join(lines + [f"  - {line}" for line in self.fine_print])


def read_rules(case: CaseDefinition) -> list[Reading]:
    """Each of `case`'s rules in plain words, in the order they are written. Only the definition
    is read: a reading can't quote a value from a case file (brief, D45)."""
    return [read_rule(name, rule, case) for name, rule in case.rules.items()]


def read_rule(name: str, rule: Rule, case: CaseDefinition) -> Reading:
    """One rule in plain words: `When checked is reached …: reach high_risk.`"""
    said: list[str] = []
    moment = when(name, rule.on)
    if rule.when is not None:
        # A rule remembers nothing: its condition is read when it fires (brief, D38), a timer's
        # when the timer fires, never when it is set (brief, D44).
        timer = isinstance(rule.on, After)
        read = "the timer fires, not when it is set" if timer else "it fires"
        moment += f", if {expression(name, 'condition', rule.when)} (read when {read})"
        said.append(
            "timer's condition read when it fires" if timer else "condition read when it fires"
        )
    done = actions(name, rule.then)
    if len(done) > 1:
        said.append("actions in the engine's order")
    sentence = f"{moment[0].upper()}{moment[1:]}: {', then '.join(done)}."
    fine = fine_print(name, rule, case)
    return Reading(
        name,
        rule.display.title,
        sentence,
        tuple(clause.text for clause in fine),
        tuple(said + [clause.kind for clause in fine]),
    )


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


def fine_print(name: str, rule: Rule, case: CaseDefinition) -> list[Clause]:
    """The parts of the rule's behaviour people get wrong, each only where it applies."""
    anchor = rule.on.since if isinstance(rule.on, After) else rule.on
    fine: list[Clause] = []
    if isinstance(rule.on, After):
        fine.append(timer_anchor(name, anchor))
        fine.append(
            Clause(
                "timer holds the case",
                "While it is set, the timer keeps the case open; a close cancels it.",
            )
        )
    if isinstance(anchor, EventArrived):
        # Listening is not waiting: only a set timer or a step waiting for the event holds the
        # case (brief, D10) (brief, D41).
        fine.append(
            Clause("listening", f"Listening for {anchor.event} doesn't keep the case open.")
        )
    fine += trust(rule, case)
    fine.append(deciding(case))
    return fine


def timer_anchor(name: str, since: object) -> Clause:
    """What a timer is set on, and when it ends: with its run, if set on a run's start; when it
    fires, if set on an instant (brief, D44)."""
    if isinstance(since, Started):
        return Clause(
            "timer on a run",
            f"The timer is set as each run of {since.started} starts, and ends when that run "
            "does: done, rejected or cancelled, a stop included. A failed run keeps it: a retry "
            "is the same run.",
        )
    if since == "opened":
        instant = "when the case opens"
    elif isinstance(since, Reached):
        instant = f"when {since.reached} is reached"
    elif isinstance(since, AnsweredTask):
        instant = f"at each answer to {since.answered}"
    elif isinstance(since, EventArrived):
        instant = f"at each arrival of {since.event}"
    else:
        raise unknown(name, since)
    return Clause("timer on an instant", f"The timer is set {instant}, and lives until it fires.")


def trust(rule: Rule, case: CaseDefinition) -> list[Clause]:
    """What untrusted data does to the rule: what its condition reads and, on a run's start, what
    steered that run (brief, D43)."""
    then = rule.then
    anchor = rule.on.since if isinstance(rule.on, After) else rule.on
    steered = f"the run of {anchor.started}" if isinstance(anchor, Started) else None
    if then.reach or then.stop:
        # Reaching or stopping decides for the case, so untrusted data stops the whole rule
        # (brief, D38) (brief, D40) (brief, D42).
        why = [
            *(["its condition reads untrusted data"] if rule.when is not None else []),
            *([f"untrusted data steered {steered}"] if steered else []),
        ]
        if not why:
            return []  # nothing it reads or rests on can be untrusted
        return [Clause("untrusted data decides nothing", f"If {', or '.join(why)}, {UNTRUSTED}")]
    fine: list[Clause] = []
    if then.set:
        # Setting informs: the value carries everything its rule read (brief, D42).
        also = f", and what steered {steered}" if steered else ""
        carried = f"The values it sets carry the sources of everything it read{also}."
        fine.append(Clause("set value carries what it read", carried))
    taking = [step for step in then.start if takes_inputs(case, step)]
    read = [
        *(["its condition reads"] if rule.when is not None else []),
        *([f"steered {steered}"] if steered else []),
    ]
    if taking and read:
        # A start goes ahead, and what chose it is checked against each input's policy
        # (brief, D39) (brief, D43).
        what = "What " + ", and what ".join(read)
        counts = "count" if len(read) > 1 else "counts"
        fine.append(
            Clause(
                "start checked against inputs",
                f"{what} {counts} for the inputs of {' and '.join(taking)}: an input whose "
                "policy refuses an untrusted source is refused, and its run fails.",
            )
        )
    return fine


UNTRUSTED = "it acts on nothing, and says why: untrusted data can't decide."


def takes_inputs(case: CaseDefinition, step: str) -> bool:
    """Whether `step` sends anything to what it calls: only then can an input policy refuse."""
    found = case.steps[step]
    return isinstance(found, CallStep | PlanStep) and bool(found.inputs)


def deciding(case: CaseDefinition) -> Clause:
    """A rule acts only while the case decides: not once every `closes_when` milestone is
    reached, nor once the case is closing (brief, D34) (brief, D38)."""
    if not case.closes_when:
        return Clause(
            "only while the case decides",
            "Only while the case decides: not once the case is closing.",
        )
    milestones = " and ".join(case.closes_when)
    verb = "is" if len(case.closes_when) == 1 else "are"
    return Clause(
        "only while the case decides",
        f"Only while the case decides: not once {milestones} {verb} reached, nor once the case "
        "is closing.",
    )
