"""Fresh facts: an event's time, and ages (layer 9d).

The case reads no clock: time reaches it only as data on each event, in whole seconds since the
epoch, so the same history decides the same way in memory and on Temporal replay (brief, D33).
See docs/layers/09-case-data.md (9d) and docs/guides/case-data.md ("Fresh facts").
"""

from collections.abc import Mapping
from dataclasses import dataclass

from ventoux.case.state import CaseState

# Each unit an age may be written in, and how many seconds it holds: `30m`, `12h`, `1d`.
UNITS = {"m": 60, "h": 60 * 60, "d": 24 * 60 * 60}


class TimeRefused(Exception):
    """An event whose time the case can't use: what is wrong with it."""


def refuse_unless_whole(at: object) -> None:
    """An event's time is a whole number of seconds; anything else is refused, never rounded or
    guessed (fail closed). Checked here, at runtime, on nothing a type checker did."""
    # Python: `bool` is a kind of `int` (`True == 1`), so it is refused by name.
    if isinstance(at, bool) or not isinstance(at, int):
        raise TimeRefused(
            "an event's time is a whole number of seconds since the epoch, and this one is a "
            f"{type(at).__name__}: stamp it from the workflow's time"
        )


def seconds_in(age: str) -> int:
    """How many seconds an age written `30m`, `12h` or `1d` holds: a whole number, then a unit.
    Raises `ValueError` for anything else."""
    number, unit = age[:-1], age[-1:]
    # Only the digits 0 to 9: no sign, point or space, and no digits of other scripts.
    if unit not in UNITS or not (number.isascii() and number.isdigit()):
        raise ValueError('an age looks like "30m", "12h" or "1d"')
    return int(number) * UNITS[unit]


# Each unit an age is said in, largest first, with its name: `3 weeks`, `5 hours`.
SAID = (("week", 7 * UNITS["d"]), ("day", UNITS["d"]), ("hour", UNITS["h"]), ("minute", UNITS["m"]))
NAMES = {"m": "minute", "h": "hour", "d": "day"}


@dataclass(frozen=True)
class Stale:
    """A fact a step reads that is older than its `max_age` allows, or whose age is unknown."""

    field: str
    age: int | None  # seconds since it was obtained; None: no time was recorded for it
    limit: str  # the step's `max_age` for it, as written: `1d`
    run: str | None  # the step run that obtained it, such as `check_order#1`; None: no run did


def stale_facts(max_age: Mapping[str, str], state: CaseState, at: int) -> list[Stale]:
    """Each fact `max_age` names that is too old at `at`, in the order it names them. A field
    nobody has set isn't stale: reading it fails, saying so. An age is read again here, on
    nothing parsing did."""
    stale: list[Stale] = []
    for field, limit in max_age.items():
        if field not in state.values:
            continue
        obtained = state.obtained.get(field)
        if obtained is None:
            stale.append(Stale(field, None, limit, None))  # fail closed: its age is unknown
        elif at - obtained.at > seconds_in(limit):
            stale.append(Stale(field, at - obtained.at, limit, obtained.run))
    return stale


def ago(seconds: int) -> str:
    """An age as people read it, in its largest whole unit, rounded down: `3 days`, `5 hours`,
    `less than a minute`."""
    for name, size in SAID:
        if seconds >= size:
            return counted(seconds // size, name)
    return "less than a minute"


def as_said(age: str) -> str:
    """An age as written, as people read it: `1d` is `1 day`, `36h` is `36 hours`."""
    return counted(int(age[:-1]), NAMES[age[-1]])


def counted(number: int, name: str) -> str:
    return f"{number} {name}" if number == 1 else f"{number} {name}s"
