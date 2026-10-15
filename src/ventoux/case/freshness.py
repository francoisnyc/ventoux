"""Fresh facts: an event's time, and ages (layer 9d).

The case reads no clock: time reaches it only as data on each event, in whole seconds since the
epoch, so the same history decides the same way in memory and on Temporal replay (brief, D33).
See docs/layers/09-case-data.md (9d) and docs/guides/case-data.md ("Fresh facts").
"""

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
