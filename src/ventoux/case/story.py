"""A story: a definition, and a timeline in simulated time of what people, systems and time do
(layer 11g2).

A story is data, read as a definition is: nothing in it runs as code. Its times are counted from
the opening, `day 3 14:30`, and become the events' times, so a story decides as a real case would
and reads no clock (brief, D33) (brief, D45).
See docs/layers/11-rules.md (11g) and docs/guides/cases.md, "Simulating a story".
"""

from typing import Annotated, Any

from pydantic import AfterValidator, Field, ValidationError, model_validator

from ventoux.case.definition import Shape, problem

# When a story's case opens, day 0 00:00: 1 January 2026, 00:00 UTC, in seconds since the epoch,
# as for the tests (`ventoux.testing.START`), so the timers' due times read as real dates.
OPENS = 1_767_225_600
MINUTE, HOUR, DAY = 60, 60 * 60, 24 * 60 * 60

A_TIME = 'a time looks like "day 3" or "day 3 14:30", counted from the opening'


def seconds_after_opening(at: str) -> int:
    """How long after the opening `at` is: `day 3` or `day 3 14:30`, in seconds. Raises
    `ValueError` for anything else."""
    words = at.split(" ")
    if len(words) not in (2, 3) or words[0] != "day" or not is_number(words[1]):
        raise ValueError(A_TIME)
    hour, minute = 0, 0
    if len(words) == 3:
        clock = words[2].split(":")
        if len(clock) != 2 or not all(is_number(part) and len(part) == 2 for part in clock):
            raise ValueError(A_TIME)
        hour, minute = int(clock[0]), int(clock[1])
        if hour > 23 or minute > 59:
            raise ValueError(A_TIME)
    return int(words[1]) * DAY + hour * HOUR + minute * MINUTE


def is_number(text: str) -> bool:
    """Whether `text` is a whole number written in the digits 0 to 9: no sign, point or space."""
    return text.isascii() and text.isdigit()


def said_at(seconds: int) -> str:
    """A time after the opening as a story writes it, always with its hour: `day 3 14:30`."""
    day, rest = divmod(seconds, DAY)
    return f"day {day} {rest // HOUR:02d}:{rest % HOUR // MINUTE:02d}"


def a_time(at: str) -> str:
    """A time in a story, kept in one form, `day 3 00:00`, so two ways of writing it read alike."""
    return said_at(seconds_after_opening(at))


Time = Annotated[str, AfterValidator(a_time)]


class Answer(Shape):
    """A person answers a task or an approval, named by its step or its entry."""

    step: str | None = None  # the step whose open entry is answered: `review`
    entry: str | None = None  # or the entry itself: `pay.approval#1`
    outcome: str  # the outcome chosen
    by: str  # who answers; their roles come from the story's `people`
    # Pydantic: `default_factory` gives each answer its own empty dict, never one shared.
    form: dict[str, Any] = Field(default_factory=dict)  # the values the form sets

    # Pydantic: a validator with `mode="after"` runs on the whole object, once its fields passed.
    @model_validator(mode="after")
    def names_one(self) -> "Answer":
        if (self.step is None) == (self.entry is None):
            raise ValueError("an answer names its step or its entry: one of them")
        return self


class Propose(Shape):
    """A person proposes a run of a step."""

    step: str
    by: str


class Retry(Shape):
    """An operator retries a failed run or a failed firing."""

    entry: str  # `pay#1`, `flag_large#1`
    by: str


class Close(Shape):
    """A person closes the case with one of its close reasons."""

    reason: str
    by: str


class Send(Shape):
    """An event from outside arrives, sent by a system (`system:portal`) or a person."""

    event: str
    payload: dict[str, Any] = Field(default_factory=dict)  # each value it carries
    by: str


class Finish(Shape):
    """A held run finishes, giving what its fake gives."""

    entry: str  # `pay#1`


# What an entry may do, one at a time: `run_case`'s script, written as data.
ACTIONS = ("answer", "propose", "retry", "close", "send", "finish")


class Entry(Shape):
    """One moment on the timeline: what happens then, or nothing, for time passing."""

    at: Time  # when, counted from the opening
    answer: Answer | None = None
    propose: Propose | None = None
    retry: Retry | None = None
    close: Close | None = None
    send: Send | None = None
    finish: Finish | None = None

    @model_validator(mode="after")
    def does_one_thing(self) -> "Entry":
        """An entry does one thing, so its order with the others is the story's, never guessed."""
        done = [action for action in ACTIONS if getattr(self, action) is not None]
        if len(done) > 1:
            raise ValueError(
                f"an entry does one thing, and this one does {' and '.join(done)}: split it in "
                "two entries"
            )
        return self


class Fake(Shape):
    """What a contract does in a story, in place of the system it stands for: nothing real is
    called, and nothing is sent (brief, D45)."""

    gives: dict[str, Any] | None = None  # its output
    outcome: str | None = None  # or one of its declared outcomes, such as `declined`
    fails: str | None = None  # or a failure, saying this
    held: bool = False  # its runs keep running until a `finish` entry

    @model_validator(mode="after")
    def does_one_thing(self) -> "Fake":
        done = [kind for kind in ("gives", "outcome", "fails") if getattr(self, kind) is not None]
        if len(done) != 1:
            found = f", and this one does {' and '.join(done)}: keep one" if done else ": say which"
            raise ValueError(f"a fake gives, gives an outcome or fails{found}")
        return self


class Expected(Shape):
    """What a story expects, compared exactly with what the simulation prints, so a firing nobody
    expected fails it (brief, D45)."""

    timeline: dict[str, list[str]]  # each time, and its lines, without the readings
    end: list[str]  # the lines under "At the end"


class Story(Shape):
    """A definition, the people and fakes it runs with, and what happens, when."""

    title: str = Field(min_length=1)
    definition: str = Field(min_length=1)  # its path, relative to the story's file
    file: dict[str, Any] = Field(default_factory=dict)  # the values the case opens with
    opened_by: str | None = None  # the person who opened it; otherwise a system did
    # Each person's roles, as the API states them (brief, D22).
    people: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    fakes: dict[str, Fake] = Field(default_factory=dict)  # by contract reference
    timeline: tuple[Entry, ...] = ()
    until: Time | None = None  # when the story ends; time moves on to it, firing what falls due
    expect: Expected | None = None

    @model_validator(mode="after")
    def time_moves_forward(self) -> "Story":
        """Time only moves forward: a story can't go back to before an event it played."""
        for index in range(1, len(self.timeline)):
            now, before = self.timeline[index].at, self.timeline[index - 1].at
            if seconds_after_opening(now) < seconds_after_opening(before):
                raise ValueError(
                    f"timeline.{index}.at: {now} comes before {before}, the entry before it: "
                    "time only moves forward"
                )
        if self.until is not None and self.timeline:
            last = self.timeline[-1].at
            if seconds_after_opening(self.until) < seconds_after_opening(last):
                raise ValueError(
                    f"until: {self.until} comes before {last}, the last entry: time only moves "
                    "forward"
                )
        return self


class StoryInvalid(Exception):
    """A story that can't be read: one line per problem, each with its path."""


def parse_story(data: object) -> Story:
    """The story written as `data`, or `StoryInvalid` listing every problem."""
    try:
        return Story.model_validate(data)
    except ValidationError as error:
        raise StoryInvalid("\n".join(problem(e) for e in error.errors())) from None
