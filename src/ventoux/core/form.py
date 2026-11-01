"""A form: the values a person gives with an outcome, for the fields it sets (brief, D9).

The form's schema is the declared types of exactly the fields its outcome sets: nothing is guessed,
converted or left out.
"""

from collections.abc import Mapping
from decimal import Decimal

from ventoux.core.dates import given_day
from ventoux.core.expressions import (
    BooleanType,
    DateType,
    FieldType,
    NumberType,
    OutcomeType,
    ReferenceType,
    StringType,
    a_kind,
)
from ventoux.core.expressions.check import a_type
from ventoux.core.sensitive import plain


def form_problem(
    outcome: str,
    sets: tuple[str, ...],
    form: Mapping[str, object] | None,
    types: Mapping[str, FieldType],
) -> str | None:
    """What is wrong with `form` as the answer `outcome`, which sets the fields `sets`; or None."""
    given = dict(form or {})
    for field in sets:
        if field not in given:
            return f"{outcome} sets {field}, and the answer doesn't give it"
    for field in given:
        if field not in sets:
            return f"the answer gives {field}, which {outcome} doesn't set"
    for field in sets:
        # The value inside its wrapper, if the client wrapped it (brief, D31).
        value = plain(given[field])
        if not fits(value, types[field]):
            # The type, never the value: it may be hidden from whoever reads the history (brief, D30).
            return misfit(field, types[field], value, "the answer")
    return None


def misfit(field: str, declared: FieldType, value: object, given_by: str) -> str:
    """Why `value` isn't of the type `declared`, naming its kind, never the value (brief, D30): `amount
    is a number, and the opening gives a string`. A text that isn't a day says how a date is
    written (brief, D66)."""
    if isinstance(declared, DateType) and isinstance(value, str):
        return (
            f"{field} is a date, written YYYY-MM-DD, and {given_by} gives a string that isn't one"
        )
    return f"{field} is {a_type(declared)}, and {given_by} gives {a_kind(value)}"


def read_as(value: object, declared: FieldType) -> object:
    """`value` as the case file keeps it, once `fits` accepted it: a date's text read into the day
    it names, which is how a date crosses a payload (brief, D66); any other value as it is.
    The one reading a form does: nothing else is converted (brief, D9)."""
    if isinstance(declared, DateType):
        return given_day(value)
    return value


def fits(value: object, declared: FieldType) -> bool:
    """Whether `value` is of the type `declared`, exactly: a number is a finite `Decimal`, never a
    float, which may have lost its exact value (brief, D20), and never a boolean."""
    if isinstance(declared, NumberType):
        return isinstance(value, Decimal) and value.is_finite()
    if isinstance(declared, StringType | ReferenceType):
        return isinstance(value, str)
    if isinstance(declared, BooleanType):
        return isinstance(value, bool)
    if isinstance(declared, OutcomeType):
        return isinstance(value, str) and value in declared.outcomes
    if isinstance(declared, DateType):
        # A day, or its text exactly YYYY-MM-DD; never a moment or a number (brief, D66).
        return given_day(value) is not None
    # Fail closed: a type this check doesn't know (a list, for now) fits nothing.
    return False
