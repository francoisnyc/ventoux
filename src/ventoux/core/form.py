"""A form: the values a person gives with an outcome, for the fields it sets (brief, D9).

The form's schema is the declared types of exactly the fields its outcome sets: nothing is guessed,
converted or left out.
"""

from collections.abc import Mapping
from decimal import Decimal

from ventoux.core.expressions import (
    BooleanType,
    FieldType,
    NumberType,
    OutcomeType,
    ReferenceType,
    StringType,
)
from ventoux.core.expressions.check import a_type


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
        if not fits(given[field], types[field]):
            return f"{field} is {a_type(types[field])}, and the answer gives {given[field]!r}"
    return None


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
    # Fail closed: a type this check doesn't know (a list, for now) fits nothing.
    return False
