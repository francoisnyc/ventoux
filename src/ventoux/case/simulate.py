"""Simulating a story: its timeline played on the in-memory engine, each firing shown beside its
rule's reading (layer 11g2).

Pure, like all of `ventoux.case`: the story and its definition are given, already read; reading
their files and printing are the command line's (`ventoux.tooling.cli`). Only the story's fakes
run, so nothing real is called and nothing is sent (brief, D45).
See docs/layers/11-rules.md (11g) and docs/guides/cases.md, "Simulating a story".
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ventoux.case.admission import ProposalRefused, RetryRefused
from ventoux.case.answers import AnswerRefused
from ventoux.case.closing import CloseRefused, needs_attention, pending
from ventoux.case.definition import CallStep, CaseDefinition, PlanStep
from ventoux.case.memory import Activity, Driver, as_json, no_plans, outcome_of, wrapped
from ventoux.case.reading import EVERY_RULE, Reading, read_rules
from ventoux.case.runtime import CaseRefused, EventRefused
from ventoux.case.state import (
    Answered,
    CaseState,
    CloseAsked,
    Event,
    Opened,
    Proposed,
    Retried,
    Sent,
)
from ventoux.case.story import OPENS, Entry, Fake, Story, said_at, seconds_after_opening
from ventoux.case.timers import next_due, set_timers, utc
from ventoux.core.catalog import Catalog
from ventoux.core.interpreter import Outcome
from ventoux.core.sensitive import Sensitive

# What the engine refuses, saying why, and changes nothing for: the story shows it and goes on.
REFUSALS = (AnswerRefused, ProposalRefused, RetryRefused, CaseRefused, CloseRefused, EventRefused)


class StoryRefused(Exception):
    """A story that can't run against its definition: one line per problem."""


class FakeFailed(Exception):
    """What a fake that `fails` raises: the engine records the failure, never its message."""


@dataclass(frozen=True)
class Line:
    """One line of the timeline: the story's, or the engine's; a firing carries its reading."""

    text: str
    reading: Reading | None = None  # the rule's reading, printed beside its first line


@dataclass(frozen=True)
class Group:
    """What happened at one time, in order."""

    at: str  # `day 2 09:00`
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class Simulation:
    """What a story did: each rule's reading, the timeline, and what is left at the end."""

    story: Story
    case: CaseDefinition
    readings: tuple[Reading, ...]
    timeline: tuple[Group, ...]
    end_at: str  # when the story ended
    end: tuple[str, ...]  # its status, and every kind of pending work, one line each

    def timeline_lines(self) -> dict[str, list[str]]:
        """The timeline as a story expects it: each time and its lines, without the readings."""
        return {group.at: [line.text for line in group.lines] for group in self.timeline}

    def difference(self) -> str | None:
        """Where what the story expects and what it did first differ; None if they don't, or if
        it expects nothing. Compared whole, so a firing nobody expected fails it (brief, D45)."""
        expect = self.story.expect
        if expect is None:
            return None
        wanted = told(expect.timeline, expect.end)
        printed = told(self.timeline_lines(), list(self.end))
        for index in range(max(len(wanted), len(printed))):
            want = wanted[index] if index < len(wanted) else None
            got = printed[index] if index < len(printed) else None
            if want != got:
                where = (want or got or ("", ""))[0]
                return (
                    f"the story's expectation fails at {where}:\n"
                    f"  expected: {want[1] if want else '(nothing more)'}\n"
                    f"  printed:  {got[1] if got else '(nothing more)'}"
                )
        return None

    def __str__(self) -> str:
        lines = [
            f"Story: {self.story.title}",
            f"Definition: {self.case.case} ({self.story.definition})",
            f"Opens: {utc(OPENS)}, day 0 00:00",
            "",
            "Rules",
            f"  {EVERY_RULE}",
        ]
        for reading in self.readings:
            lines += ["", *(f"  {line}" for line in str(reading).splitlines())]
        lines += ["", "Timeline"]
        for group in self.timeline:
            lines.append(group.at)
            for line in group.lines:
                lines.append(f"  {line.text}")
                if line.reading is not None:
                    # Beside a firing, the rule's whole reading, its fine print included.
                    first, *rest = str(line.reading).splitlines()
                    lines += [f"    ↳ {first}", *(f"    {more}" for more in rest)]
        lines += ["", f"At the end, {self.end_at}", *(f"  {line}" for line in self.end)]
        return "\n".join(lines) + "\n"


def told(timeline: dict[str, list[str]], end: list[str]) -> list[tuple[str, str]]:
    """Every line, with where it is: `(day 2 09:00, line)`, then `(the end, line)`."""
    return [(at, line) for at, lines in timeline.items() for line in lines] + [
        ("the end", line) for line in end
    ]


def simulate(story: Story, case: CaseDefinition, catalog: Catalog) -> Simulation:
    """Play `story` on `case`, on the in-memory engine, with only the story's fakes running.
    Refuses a story that can't run against `case` before playing anything (fail closed)."""
    refuse_what_cant_run(story, case)
    readings = {reading.name: reading for reading in read_rules(case)}
    fakes = {reference: run_fake(fake) for reference, fake in story.fakes.items()}
    held = frozenset(
        name
        for name, step in case.steps.items()
        if isinstance(step, CallStep) and story.fakes[step.called].held
    )
    player = Player(story, case, readings, Driver(case, catalog, fakes, held, no_plans, fakes))
    player.open()
    for entry in story.timeline:
        player.play(entry)
    last = story.timeline[-1].at if story.timeline else said_at(0)
    end_at = story.until or last
    player.state = player.fire_due(OPENS + seconds_after_opening(end_at))
    return Simulation(
        story,
        case,
        tuple(readings.values()),
        tuple(Group(at, tuple(lines)) for at, lines in player.groups),
        end_at,
        tuple(end_of(player.state)),
    )


def refuse_what_cant_run(story: Story, case: CaseDefinition) -> None:
    """What makes a story unable to run against `case`, all at once: a plan step, a contract
    with no fake, a fake for nothing the definition calls. Nothing real is ever reached for."""
    problems = [
        f"steps.{name}: a story can't run a plan step yet: plans in stories come later"
        for name, step in case.steps.items()
        if isinstance(step, PlanStep)
    ]
    callers: dict[str, list[str]] = {}
    for name, step in case.steps.items():
        if isinstance(step, CallStep):
            callers.setdefault(step.called, []).append(name)
    problems += [
        f"fakes: no fake for {called}, which {' and '.join(steps)} calls: add one, so nothing "
        "real is called"
        for called, steps in callers.items()
        if called not in story.fakes
    ]
    problems += [
        f"fakes.{reference}: the definition calls no {reference}: remove it, or name a contract "
        "a step calls"
        for reference in story.fakes
        if reference not in callers
    ]
    if problems:
        raise StoryRefused("\n".join(problems))


def run_fake(fake: Fake) -> Activity:
    """The code a fake stands for: it gives its output, its outcome, or fails, and calls nothing."""

    def run(inputs: dict[str, Any]) -> dict[str, Any]:
        if fake.outcome is not None:
            raise Outcome(fake.outcome)  # a business outcome, which `decide` checks is declared
        if fake.fails is not None:
            raise FakeFailed(fake.fails)
        return as_json(fake.gives or {})

    return run


class Player:
    """Plays a story's entries through the in-memory driver, one event at a time, writing down
    what each decision adds to the history at that decision's time."""

    def __init__(
        self, story: Story, case: CaseDefinition, readings: dict[str, Reading], driver: Driver
    ) -> None:
        self.story, self.case, self.readings, self.driver = story, case, readings, driver
        self.state = CaseState("story")
        self.groups: list[tuple[str, list[Line]]] = []
        self.read_beside: set[str] = set()  # firings already shown with their reading

    def open(self) -> None:
        """The case opens at day 0 00:00, with the story's values, each sensitive one wrapped as
        the client sends it (brief, D31)."""
        file = wrapped(self.case, as_json(self.story.file))
        self.decide(OPENS, "the case opens", lambda: Opened(file, self.story.opened_by, at=OPENS))

    def play(self, entry: Entry) -> None:
        """One entry: first every timer due by its time fires, then what it does happens."""
        at = OPENS + seconds_after_opening(entry.at)
        self.state = self.fire_due(at)
        if entry.finish is not None:
            command = self.driver.held.pop(entry.finish.entry, None)
            if command is None:
                # The story's own mistake, never the engine's refusal: fail closed, loudly.
                raise StoryRefused(
                    f"{entry.at}: {entry.finish.entry} isn't a held run going on: nothing finishes"
                )
            outcome = outcome_of(command, self.driver.activity, at)
            self.decide(at, f"{entry.finish.entry} finishes", lambda: outcome)
            return
        made = self.event(entry, at)
        if made is None:
            self.write(at, [Line("(time passes)")])
            return
        said, event = made
        self.decide(at, said, event)

    def event(self, entry: Entry, at: int) -> tuple[str, Callable[[], Event]] | None:
        """What `entry` does, as the story's line and the event the API would send."""
        if (answer := entry.answer) is not None:
            name = answer.step or answer.entry or ""
            given = {field: Sensitive(v) for field, v in as_json(answer.form).items()} or None
            with_form = f", with {', '.join(answer.form)}" if answer.form else ""
            return f"{answer.by} answers {name}: {answer.outcome}{with_form}", lambda: Answered(
                name, answer.outcome, answer.by, self.roles(answer.by), given, at=at
            )
        if (proposal := entry.propose) is not None:
            return f"{proposal.by} proposes {proposal.step}", lambda: Proposed(
                proposal.step, proposal.by, self.roles(proposal.by), at=at
            )
        if (retry := entry.retry) is not None:
            return f"{retry.by} retries {retry.entry}", lambda: Retried(
                retry.entry, retry.by, self.roles(retry.by), at=at
            )
        if (close := entry.close) is not None:
            return f"{close.by} closes the case as {close.reason}", lambda: CloseAsked(
                close.reason, close.by, self.roles(close.by), at=at
            )
        if (sent := entry.send) is not None:
            with_payload = f", with {', '.join(sent.payload)}" if sent.payload else ""
            return f"{sent.by} sends {sent.event}{with_payload}", lambda: Sent(
                sent.event, as_json(sent.payload), sent.by, self.roles(sent.by), at=at
            )
        return None

    def roles(self, who: str) -> frozenset[str]:
        """A person's roles, as the story states them; a system or a stranger has none."""
        return frozenset(self.story.people.get(who, ()))

    def decide(self, at: int, said: str, event: Callable[[], Event]) -> None:
        """The story's line, then what the engine does with its event, or why it refuses it."""
        before = len(self.state.history)
        try:
            self.state = self.driver.carry(self.state, event())
        except REFUSALS as refusal:
            # `decide` changes nothing when it refuses: the story goes on as if it hadn't come.
            self.write(at, [Line(said), Line(f"refused: {refusal}")])
            return
        self.write(at, [Line(said), *self.lines(self.state.history[before:])])

    def fire_due(self, at: int) -> CaseState:
        """Every timer due by `at` fires, one at a time, each at its own due time (brief, D44)."""
        state = self.state
        while (due := next_due(state, at)) is not None:
            before = len(state.history)
            state = self.driver.carry(state, due)
            self.state = state
            self.write(due.at, self.lines(state.history[before:]))
        return state

    def lines(self, history: list[str]) -> list[Line]:
        """The engine's lines; the first line of each firing carries its rule's reading."""
        found: list[Line] = []
        for text in history:
            firing = self.firing_of(text)
            if firing is not None and firing not in self.read_beside:
                self.read_beside.add(firing)
                found.append(Line(text, self.readings[firing.split("#")[0]]))
            else:
                found.append(Line(text))
        return found

    def firing_of(self, text: str) -> str | None:
        """The firing a history line is about, `chase_review#1`, if it begins with one."""
        first = text.split(" ")[0].removesuffix(":")
        rule, mark, number = first.partition("#")
        if mark and rule in self.case.rules and number.isascii() and number.isdigit():
            return first
        return None

    def write(self, at: int, lines: list[Line]) -> None:
        """Add `lines` at `at`: to the last group if it is at the same time, else a new one."""
        if not lines:
            return
        label = said_at(at - OPENS)
        if self.groups and self.groups[-1][0] == label:
            self.groups[-1][1].extend(lines)
        else:
            self.groups.append((label, list(lines)))


def end_of(state: CaseState) -> list[str]:
    """The case's status, then every kind of pending work, each on its line (brief, D10). With
    none, it says so; pending work it can't name is an error, never left unsaid."""
    running = [run.entry for run in state.runs if run.status in ("running", "retrying")]
    parts = [
        *([f"waiting for: {', '.join(state.waiting.values())}"] if state.waiting else []),
        *([f"running: {', '.join(running)}"] if running else []),
        *(f"needs attention: {line}" for line in needs_attention(state)),
        *([f"approved, waiting to start: {', '.join(state.given)}"] if state.given else []),
        *(
            [f"proposed, waiting to start: {', '.join(state.waiting_to_start)}"]
            if state.waiting_to_start
            else []
        ),
        *(f"timer: {timer}" for timer in set_timers(state)),
    ]
    if not parts and pending(state):
        # Fail closed: pending work the story can't name would be a silent gap in what it shows.
        raise RuntimeError("the case has pending work the story can't name")
    return [f"status: {state.phase}", *(parts or ["nothing pending"])]
