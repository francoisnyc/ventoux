"""A date: a day on the calendar, written exactly `YYYY-MM-DD` (brief, D66).

One function reads the text, so every place a date enters (an expression's literal, a form, the
opening, an event) refuses the same texts the same way.
"""

from datetime import date

from pydantic import BaseModel

HOW_TO_WRITE = 'write a date as YYYY-MM-DD, such as "2026-10-31"'


def calendar_date(text: str) -> date | None:
    """The day `text` names, if it is exactly `YYYY-MM-DD` and a real day; else None.

    Not `date.fromisoformat`: since Python 3.11 it also reads `20261031` and the week date
    `2026-W44-6`, which a date never is (brief, D66). So the shape is checked first, character by character.
    """
    if not written_as_a_date(text):
        return None
    try:
        # Year 0, month 13 and 30 February are refused here, as no such day exists.
        return date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
    except ValueError:
        return None


def written_as_a_date(text: str) -> bool:
    """Whether `text` is ten characters: four digits, a dash, two digits, a dash, two digits."""
    digits = text[0:4] + text[5:7] + text[8:10]
    return (
        len(text) == 10
        and text[4] == "-"
        and text[7] == "-"
        # ASCII only: `str.isdigit` would also take digits from other scripts, such as "٢".
        and all(character in "0123456789" for character in digits)
    )


def is_day(value: object) -> bool:
    """Whether `value` is a day, a `date` exactly. To Python a `datetime` is a `date` too; to
    Ventoux it is a moment, and refused. The exact type says so without importing `datetime`,
    which a pure layer may not (brief, D66)."""
    return type(value) is date


def given_day(value: object) -> date | None:
    """The day `value` is, if it is one: a `date` (never a `datetime`, which is a moment, though
    Python counts it a `date`), or a text `calendar_date` reads. Else None: a number, a moment
    and any other text are never turned into a day (brief, D66)."""
    if type(value) is date:  # as `is_day` reads it, written out so the type checker sees it
        return value
    if isinstance(value, str):
        return calendar_date(value)
    return None


def date_fields(model: type[BaseModel]) -> list[str]:
    """The fields of `model` declared as a day, `date` exactly, in order."""
    return [name for name, field in model.model_fields.items() if field.annotation is date]
