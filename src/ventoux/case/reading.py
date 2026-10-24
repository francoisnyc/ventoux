"""Reading rules: each rule in plain words, worked out from the definition alone (layer 11g1).

A reading is never given a case file, so it can't quote a value from one: the constants it shows
are the rule's own (brief, D45). It names steps, milestones and events as the history does, so a
firing and its reading, side by side, use the same words.
See docs/layers/11-rules.md (11g).
"""

from collections.abc import Callable, Mapping
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
    ReminderRule,
    Rule,
    SlaRule,
    Started,
    TaskStep,
    Then,
    WaitStep,
)
from ventoux.case.freshness import as_said
from ventoux.case.sequence import requirements
from ventoux.case.visibility import seen_by
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.expressions import (
    Expression,
    ExpressionInvalid,
    ListType,
    OutcomeType,
    ReferenceType,
    render,
)
from ventoux.core.plan import ActivityState, ApprovalState, FinalState, Plan, Transition, WaitState


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
    "what a stop does",  # what a close does, to one step: a call isn't cut off (brief, D40)
    "a start is a proposal",  # admission decides, as for a person's (brief, D39)
    "reaching closes the case",  # a closes_when milestone cancels what is open (brief, D10)
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


@dataclass(frozen=True)
class PatternReading:
    """A pattern in plain words: its own sentence, and the rules it expands into, each of which
    reads as any other rule (brief, D46)."""

    name: str  # the name the pattern is written under
    title: str  # the pattern's own title
    kind: str  # `sla` or `reminder`
    sentence: str  # what it does, as one sentence
    rules: tuple[str, ...]  # the rules it expands into, in order

    def __str__(self) -> str:
        noun = "the rule" if len(self.rules) == 1 else "the rules"
        expands = f"{noun} {listed_and(list(self.rules))}"
        return f"{self.name}: {self.title}\n  {self.sentence}\n  It expands to {expands}."


def read_patterns(case: CaseDefinition) -> list[PatternReading]:
    """Each of `case`'s patterns in plain words, in the order they are written. Its rules are
    read by `read_rules`, as any other (brief, D46)."""
    found: list[PatternReading] = []
    for name, entry in case.written.items():
        if isinstance(entry, Rule):
            continue
        rules = tuple(rule for rule in case.rules if case.pattern_of(rule) == name)
        if isinstance(entry, SlaRule):
            step, within = entry.sla.step, entry.sla.within
            condition = (
                f", and if {expression(name, 'condition', entry.when)} (read when the timer fires)"
                if entry.when is not None
                else ""
            )
            sentence = (
                f"An sla on {step}: if a run of {step} isn't finished within {within} of its "
                f"latest start{condition}, {', then '.join(actions(name, entry.then))}."
            )
            found.append(PatternReading(name, entry.display.title, "sla", sentence, rules))
        elif isinstance(entry, ReminderRule):
            reminder = entry.reminder
            condition = (
                f", if {expression(name, 'condition', entry.when)} (read at each reminder)"
                if entry.when is not None
                else ""
            )
            ages = listed_and(list(reminder.after))
            sentence = (
                f"A reminder of {reminder.task}: while a run of {reminder.task} is open, start "
                f"{reminder.start} {ages} after it starts{condition}."
            )
            found.append(PatternReading(name, entry.display.title, "reminder", sentence, rules))
        else:
            # Fail closed: an entry the reader doesn't know is refused, never left out.
            raise ReadingRefused(
                f"can't read {name}: {entry!r} is neither a raw rule nor a pattern Ventoux knows"
            )
    return found


def listed_and(parts: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`."""
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


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
    fine += stops(rule.then, case)
    fine += starts(rule.then, case)
    fine += closes(rule.then, case)
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
    decides = bool(then.reach or then.stop)
    fine: list[Clause] = []
    if decides:
        # Reaching or stopping decides for the case, so untrusted data stops the whole rule
        # (brief, D38) (brief, D40) (brief, D42).
        why = [
            *(["its condition reads untrusted data"] if rule.when is not None else []),
            *([f"untrusted data steered {steered}"] if steered else []),
        ]
        if why:  # else nothing it reads or rests on can be untrusted
            fine.append(
                Clause("untrusted data decides nothing", f"If {', or '.join(why)}, {UNTRUSTED}")
            )
    if then.set:
        # Setting informs: the value carries everything its rule read (brief, D42). A rule that
        # also reaches or stops doesn't act on a steered start, so its values never carry that.
        also = f", and what steered {steered}" if steered and not decides else ""
        carried = f"The values it sets carry the sources of everything it read{also}."
        fine.append(Clause("set value carries what it read", carried))
    if decides:
        return fine  # untrusted data stops it whole: what it starts never rests on untrusted data
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


def stops(then: Then, case: CaseDefinition) -> list[Clause]:
    """What a stop does to each step it names: what a close does, to one step. What hasn't started
    is cancelled at once; a running call can't be cut off halfway (brief, D10) (brief, D40)."""
    fine: list[Clause] = []
    for name in then.stop:
        step = case.steps[name]
        if isinstance(step, TaskStep):
            text = f"Stopping {name} cancels its open task at once."
        elif isinstance(step, WaitStep):
            text = f"Stopping {name} cancels its open wait at once."
        elif isinstance(step, CallStep | PlanStep):
            waiting = (
                f"waiting for {its_approval(step)}, or to start"
                if approved(step)
                else "waiting to start"
            )
            text = (
                f"Stopping {name} cancels a run {waiting}, at once; a running call is only asked "
                "to stop, may still finish, and is flagged if it does; a failed run isn't stopped."
            )
        else:
            # Fail closed: a kind of step the reader doesn't know is refused, never guessed.
            raise ReadingRefused(
                f"can't read what stopping {name} does: {step!r} is no kind of step"
            )
        fine.append(Clause("what a stop does", text))
    return fine


def approved(step: object) -> bool:
    """Whether a run of `step` may wait for a person's approval before it starts (brief, D11)."""
    return isinstance(step, CallStep) and step.approval is not None


def its_approval(step: object) -> str:
    """`its approval`, saying how many give it when several people do (brief, D47)."""
    count = step.approval.count if isinstance(step, CallStep) and step.approval else 1
    return f"its approval by {count} people" if count > 1 else "its approval"


def starts(then: Then, case: CaseDefinition) -> list[Clause]:
    """What a start does: the engine proposes a run, and admission decides at once, as for a
    person's proposal; a start it can't make is recorded, and nothing runs, then or later
    (brief, D39)."""
    required = requirements(case) if then.start else {}
    fine: list[Clause] = []
    for name in then.start:
        step = case.steps[name]
        calls = isinstance(step, CallStep | PlanStep)
        why = [
            *(["its requirements aren't met"] if required[name] else []),
            *(["its condition is false"] if step.when is not None else []),
            "it is already running"
            + (f" or waiting for {its_approval(step)}" if approved(step) else ""),
            *(["it has run and isn't repeatable"] if not step.repeatable else []),
            *(["its latest run needs attention"] if calls else []),
        ]
        text = (
            f"Starting {name} is a proposal, decided at once as a person's is: nothing starts, "
            f"and the history says why, if {listed(why)}."
        )
        if isinstance(step, CallStep | PlanStep) and step.max_age:
            # A rule's start never waits for a refresh, which lands with no person in it
            # (brief, D39).
            text += (
                " If a fact it needs fresh is stale, its run fails and needs attention: a rule's "
                "start doesn't wait for it to be fetched again."
            )
        if approved(step):
            text += f" It waits for {its_approval(step)} when one is needed."
        fine.append(Clause("a start is a proposal", text))
    return fine


def closes(then: Then, case: CaseDefinition) -> list[Clause]:
    """What reaching a `closes_when` milestone does: the case closes, cancelling what is open, and
    running calls finish (brief, D10) (brief, D34)."""
    reached = [milestone for milestone in then.reach if milestone in case.closes_when]
    if not reached:
        return []
    others = [milestone for milestone in case.closes_when if milestone not in then.reach]
    verb = "is" if len(others) == 1 else "are"
    once = f" once {' and '.join(others)} {verb} reached too" if others else ""
    return [
        Clause(
            "reaching closes the case",
            f"Reaching {' and '.join(reached)} closes the case{once}, unless a failed run holds "
            "the close: open tasks, approvals and timers are cancelled, and running calls finish.",
        )
    ]


def listed(parts: list[str]) -> str:
    """`a`, `a, or b`, `a, b, or c`: the reasons a start may be refused, read as one list."""
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])}, or {parts[-1]}"


# --- Every other entry, read (brief, D56) --------------------------------------------------------

# The fine print of an entry's reading, a closed list too: each has a witness, a test that reads
# an entry with it and runs a case where the engine does what it says (brief, D45) (brief, D56).
ENTRY_CLAUSES = (
    "unapproved where its condition is false",  # an approval's `when` (brief, D11)
    "approvers are distinct people",  # several approve, one rejection rejects (brief, D47)
    "the proposer never approves",  # whoever proposes a run (brief, D25)
)

# What a contract's declared effect does, as a reading says it: declared, never read from a name.
EFFECTS = {"read": "reads", "compute": "computes", "write": "writes", "notify": "notifies"}


@dataclass(frozen=True)
class EntryReading:
    """An entry of a definition in plain words: its sentence, and the fine print that applies."""

    path: str  # the entry, as the JSON writes it: `steps.pay`, `fields.amount`, `closing`
    sentence: str
    fine_print: tuple[str, ...] = ()  # each part people get wrong that applies, one per line
    clauses: tuple[str, ...] = ()  # which of ENTRY_CLAUSES the fine print says

    def __str__(self) -> str:
        return "\n".join([self.sentence, *(f"- {line}" for line in self.fine_print)])


def read_entry(
    path: str, case: CaseDefinition, plans: Mapping[str, Plan], catalog: Catalog
) -> object | None:
    """The reading of the entry at `path` (`steps.pay`, `rules.chase`, `closing`,
    `plans.refund-order@1.states.pay`), from the definition and the catalog alone: never given a
    case file, so it can't quote a value from one. None if the version has no such entry."""
    parts = path.split(".")
    section, name = parts[0], parts[1] if len(parts) > 1 else ""
    if path == "closing":
        return read_closing(case)
    if section == "plans" and len(parts) >= 4 and name in plans:
        plan, what, entry = plans[name], parts[2], parts[3]
        if what == "states" and entry in plan.states:
            return read_state(entry, plan, catalog)
        if what == "fields" and entry in plan.fields:
            return read_plan_field(entry, plan)
        return None
    readers: dict[str, Callable[[], object]] = {
        "steps": lambda: read_step(name, case, catalog),
        "fields": lambda: read_field(name, case, catalog),
        "events": lambda: read_event(name, case),
        "close_reasons": lambda: read_close_reason(name, case),
        "rules": lambda: read_written_rule(name, case),
    }
    present: dict[str, Mapping[str, object]] = {
        "steps": case.steps,
        "fields": case.fields,
        "events": case.events,
        "close_reasons": case.close_reasons,
        "rules": case.written,
    }
    if section not in readers or name not in present[section]:
        return None
    return readers[section]()


def read_written_rule(name: str, case: CaseDefinition) -> object:
    """A rule as written: a raw rule's reading, or a pattern's (brief, D46)."""
    if isinstance(case.written[name], Rule):
        return read_rule(name, case.rules[name], case)
    return next(reading for reading in read_patterns(case) if reading.name == name)


def read_step(name: str, case: CaseDefinition, catalog: Catalog) -> EntryReading:
    """A step: what it is, when it may start, who approves it, what it reaches and how old its
    facts may be (brief, D56)."""
    step = case.steps[name]
    if not isinstance(step, TaskStep | CallStep | PlanStep | WaitStep):
        # Fail closed: a kind of step the reader doesn't know is refused, never guessed.
        raise ReadingRefused(f"can't read {name}: {step!r} is no kind of step")
    sentences = [what_it_is(name, step, catalog), when_it_starts(name, step, case)]
    fine: list[Clause] = []
    if isinstance(step, CallStep) and step.approval is not None:
        sentences.append(who_approves(name, step))
        fine += approval_print(name, step)
    if isinstance(step, TaskStep):
        sentences += answered(name, step)
    if step.reaches:
        sentences.append(f"Done, it reaches {listed_and(list(step.reaches))}.")
    if isinstance(step, CallStep | PlanStep) and step.max_age:
        ages = [f"{fact} at most {as_said(age)} old" for fact, age in step.max_age.items()]
        sentences.append(f"It needs {listed_and(ages)}.")
    return EntryReading(
        f"steps.{name}",
        " ".join(sentences),
        tuple(clause.text for clause in fine),
        tuple(clause.kind for clause in fine),
    )


def what_it_is(name: str, step: object, catalog: Catalog) -> str:
    """`pay calls payments.refund@2 (high risk, it writes), giving amount from approved_amount`."""
    if isinstance(step, TaskStep):
        return (
            f"{name} is a task for {' or '.join(step.roles)}, answered "
            f"{' or '.join(step.outcomes)}."
        )
    if isinstance(step, CallStep):
        return f"{name} calls {called_with(name, step.called, catalog)}{giving(name, step.inputs)}."
    if isinstance(step, PlanStep):
        return f"{name} runs the plan {step.plan}{giving(name, step.inputs)}."
    if isinstance(step, WaitStep):
        return f"{name} waits for {step.event}."
    raise ReadingRefused(f"can't read {name}: {step!r} is no kind of step")


def called_with(name: str, reference: str, catalog: Catalog) -> str:
    """`payments.refund@2 (high risk, it writes)`: its risk and its declared effect, never a guess
    from its name (brief, D56)."""
    try:
        contract = catalog.lookup(reference)
    except NotInCatalog as missing:
        raise ReadingRefused(f"can't read {name}: {missing}") from None
    return f"{reference} ({contract.risk} risk, it {EFFECTS[contract.effect]})"


def giving(name: str, inputs: Mapping[str, Expression]) -> str:
    """`, giving order_id from order_id and amount from approved_amount`; nothing if none."""
    given = [f"{field} from {expression(name, f'input {field}', v)}" for field, v in inputs.items()]
    return f", giving {listed_and(given)}" if given else ""


def when_it_starts(
    name: str, step: TaskStep | CallStep | PlanStep | WaitStep, case: CaseDefinition
) -> str:
    """`It starts by itself once review is done, if review.outcome = "approve".`"""
    required = [
        f"{needed} is done" if needed in case.steps else f"{needed} is reached"
        for needed in requirements(case)[name]
    ]
    once = f"once {listed_and(required)}" if required else ""
    if step.automatic:
        said = f"It starts by itself {once or 'when the case opens'}"
    else:
        who = (
            f"{' or '.join(step.proposed_by)} proposes it"
            if step.proposed_by
            else ("a rule starts it")
        )
        said = f"It starts only when {who}{f', {once}' if once else ''}"
    if step.when is not None:
        said += f", if {expression(name, 'condition', step.when)}"
    if step.automatic and step.proposed_by:
        said += f"; {' or '.join(step.proposed_by)} may propose it"
    if step.repeatable:
        said += "; it may run again when proposed"
    return said + "."


def who_approves(name: str, step: CallStep) -> str:
    """`One support-lead approves it, when approved_amount > 100.`"""
    approval = step.approval
    assert approval is not None
    roles = " or ".join(approval.roles)
    if approval.count == 1:
        said = f"One {roles} approves it"
    else:
        said = f"{counted_people(approval.count)} approve it, each a {roles}"
    if approval.when is not None:
        return f"{said}, when {expression(name, 'approval condition', approval.when)}."
    return f"{said}, on every run."


NUMBER_WORDS = ("One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten")


def counted_people(count: int) -> str:
    """`Two people`, `11 people`."""
    word = NUMBER_WORDS[count - 1] if 1 <= count <= len(NUMBER_WORDS) else str(count)
    return f"{word} people"


def approval_print(name: str, step: CallStep) -> list[Clause]:
    """What people get wrong about an approval, each only where it applies (brief, D56)."""
    approval = step.approval
    assert approval is not None
    fine: list[Clause] = []
    if approval.when is not None:
        # Asked only where its condition holds: elsewhere the step runs unapproved, a high-risk
        # one included (brief, D11).
        condition = expression(name, "approval condition", approval.when)
        fine.append(
            Clause(
                "unapproved where its condition is false",
                f"Where {condition} is false, it runs with no approval.",
            )
        )
    if approval.count > 1:
        fine.append(
            Clause(
                "approvers are distinct people",
                f"The {approval.count} approvers are different people, each someone else; one "
                "rejection rejects the approval.",
            )
        )
    if step.proposed_by:
        fine.append(
            Clause("the proposer never approves", "Whoever proposes a run never approves it.")
        )
    return fine


def answered(name: str, step: TaskStep) -> list[str]:
    """`Answered approve, it sets approved_amount.`, for each outcome that sets or reaches."""
    said: list[str] = []
    for outcome, declared in step.outcomes.items():
        does = [
            *([f"sets {listed_and(list(declared.sets))}"] if declared.sets else []),
            *([f"reaches {listed_and(list(declared.reaches))}"] if declared.reaches else []),
        ]
        if does:
            said.append(f"Answered {outcome}, it {' and '.join(does)}.")
    return said


def read_field(name: str, case: CaseDefinition, catalog: Catalog) -> EntryReading:
    """A field: its type, who sees it (registered roles, as the case computes it), whether it is
    sensitive, and its mark (brief, D12) (brief, D30) (brief, D31)."""
    field = case.fields[name]
    seen = [role for role in seen_by(case, name) if role in catalog.roles]
    sentences = [
        f"{name} is {kind_of(name, field.declared)}, seen by {listed_and(seen) if seen else 'nobody'}."
    ]
    if field.sensitive:
        sentences.append("It is sensitive: wrapped, and never given to a workflow step.")
    if field.source is not None:
        sentences.append(f"It is marked {field.source}, whoever writes it.")
    return EntryReading(f"fields.{name}", " ".join(sentences))


def kind_of(name: str, declared: object) -> str:
    """A declared type, as people read it: `a number`, `a reference to orders`."""
    if isinstance(declared, ReferenceType):
        return f"a reference to {declared.system}"
    if isinstance(declared, ListType):
        return f"a list of {listed_and(list(declared.fields))}"
    if isinstance(declared, OutcomeType):
        return f"one of {' or '.join(declared.outcomes)}"
    kinds = {"number": "a number", "string": "a text", "boolean": "true or false"}
    kind = getattr(declared, "type", None)
    if kind not in kinds:
        raise ReadingRefused(f"can't read {name}'s type: {declared!r} isn't a type Ventoux knows")
    return kinds[str(kind)]


def read_event(name: str, case: CaseDefinition) -> EntryReading:
    """An event: who sends it, and what it carries, each with its mark (brief, D41)."""
    event = case.events[name]
    sender = event.sent_by.system or " or ".join(event.sent_by.roles or ())
    carried = [
        f"{field} ({kind_of(field, payload.declared)}"
        f"{f', marked {payload.source}' if payload.source else ''})"
        for field, payload in event.payload.items()
    ]
    carrying = f", carrying {listed_and(carried)}" if carried else ", carrying nothing"
    return EntryReading(f"events.{name}", f"{name} is sent by {sender}{carrying}.")


def read_close_reason(name: str, case: CaseDefinition) -> EntryReading:
    """A close reason: who may close the case with it (brief, D10)."""
    reason = case.close_reasons[name]
    return EntryReading(
        f"close_reasons.{name}", f"{name}: {' or '.join(reason.roles)} may close the case with it."
    )


# Forgetting, as a case map says it (brief, D32).
FORGETTING = {
    "allowed": "Its records may be forgotten, open or closed.",
    "while_open": "Its records may be forgotten only while it is open.",
    "never": "Its records are never forgotten.",
}


def read_closing(case: CaseDefinition) -> EntryReading:
    """How a case closes, and whether it may be forgotten (brief, D10) (brief, D32)."""
    if case.stays_open:
        closes = "It never closes by itself: a person closes it with a reason."
    elif case.closes_when:
        verb = "is" if len(case.closes_when) == 1 else "are"
        closes = f"It closes once {listed_and(list(case.closes_when))} {verb} reached."
    else:
        closes = "It closes when nothing is left to do."
    return EntryReading("closing", f"{closes} {FORGETTING[case.forgetting]}")


def read_state(name: str, plan: Plan, catalog: Catalog) -> EntryReading:
    """A plan's state: what it calls, who approves or answers it, and where each answer leads."""
    state = plan.states[name]
    path = f"plans.{plan.plan}@{plan.version}.states.{name}"
    if isinstance(state, FinalState):
        return EntryReading(path, f"{name} ends the plan: {state.final}.")
    if isinstance(state, ActivityState):
        does = f"{name} calls {called_with(name, state.activity, catalog)}{giving(name, state.inputs)}."
    elif isinstance(state, ApprovalState):
        within = f", within {state.approval.timeout}" if state.approval.timeout else ""
        does = (
            f"{name}: one {' or '.join(state.approval.roles)} approves {state.approval.of}{within}."
        )
    elif isinstance(state, WaitState):
        within = f", within {state.wait.timeout}" if state.wait.timeout else ""
        does = (
            f"{name} waits for {' or '.join(state.wait.outcomes)} by "
            f"{' or '.join(state.wait.roles)}{within}."
        )
    else:
        raise ReadingRefused(f"can't read {name}: {state!r} is no kind of state")
    moves = [
        f"on {event}, {', or '.join(leads(name, transition) for transition in transitions)}"
        for event, transitions in state.on.items()
    ]
    return EntryReading(path, f"{does} {'; '.join(moves).capitalize()}.")


def leads(name: str, transition: Transition) -> str:
    """`pay`, or `pay if amount > 100`."""
    if transition.when is None:
        return transition.target
    return f"{transition.target} if {expression(name, 'transition', transition.when)}"


def read_plan_field(name: str, plan: Plan) -> EntryReading:
    """A plan's field: its type, and its mark (brief, D12)."""
    source = plan.sources.get(name)
    marked = f" It is marked {source}, whoever gives it." if source else ""
    return EntryReading(
        f"plans.{plan.plan}@{plan.version}.fields.{name}",
        f"{name} is {kind_of(name, plan.fields[name])}.{marked}",
    )
