"""A form: the values a person gives with an outcome, for the fields it sets (brief, D9).

The form's schema is the declared types of exactly the fields its outcome sets: nothing is guessed,
converted or left out.
"""

from collections.abc import Mapping
from decimal import Decimal

from ventoux.core.dates import given_day
from ventoux.core.expressions import (
    AttachmentType,
    BooleanType,
    DateType,
    FieldType,
    ListType,
    NumberType,
    OptionType,
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


# The longest ID an attachment may hold: room for any store's ID, never for a file (brief, D68).
LONGEST_ID = 200
# The most items a list holds: so one decision starts at most this many runs of a step that
# repeats over it (brief, D39) (brief, D73). A deliberate limit (brief, D48).
MOST_ITEMS = 100


def misfit(field: str, declared: FieldType, value: object, given_by: str) -> str:
    """Why `value` isn't of the type `declared`, naming its kind, never the value (brief, D30):
    `amount is a number, and the opening gives a string`. A text that isn't a day says how a date
    is written (brief, D66)."""
    if isinstance(declared, ListType):
        if isinstance(value, list) and len(value) > MOST_ITEMS:
            return f"{field} holds at most {MOST_ITEMS} items, and {given_by} gives {len(value)}"
        wrong = list_misfit(field, value, declared)
        return f"{field} is {a_list(declared)}, and {given_by} gives {wrong}"
    if isinstance(declared, DateType) and isinstance(value, str):
        return (
            f"{field} is a date, written YYYY-MM-DD, and {given_by} gives a string that isn't one"
        )
    if isinstance(declared, AttachmentType) and isinstance(value, str):
        # What it gave may be the file itself: say how one is given, never quote it (brief, D30).
        return (
            f"{field} is an attachment, the ID a store issued, at most {LONGEST_ID} characters: "
            f"upload the file to {declared.store} and give its ID"
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
    if isinstance(declared, OptionType):
        # A text; whether it is one of the system's list is its check's to say (brief, D67).
        return isinstance(value, str) and value != ""
    if isinstance(declared, AttachmentType):
        # A short text: an ID, never the file. Whether the store issued it is its check's to say
        # (brief, D68).
        return isinstance(value, str) and 0 < len(value) <= LONGEST_ID
    if isinstance(declared, ListType):
        # At most MOST_ITEMS records, each with exactly the declared fields, each of its type
        # (brief, D73).
        return (
            isinstance(value, list)
            and len(value) <= MOST_ITEMS
            and all(item_misfit("the list", item, declared) is None for item in value)
        )
    # Fail closed: a type this check doesn't know fits nothing.
    return False


def a_list(declared: ListType) -> str:
    """A list's shape as a message says it: `a list of records with sku (a string) and amount (a
    number)`."""
    fields = [f"{name} ({a_type(kind)})" for name, kind in declared.fields.items()]
    shown = ", ".join(fields[:-1]) + f" and {fields[-1]}" if len(fields) > 1 else fields[0]
    return f"a list of records with {shown}"


def list_misfit(field: str, value: object, declared: ListType) -> str:
    """What a value that isn't the list gives, naming kinds and declared names, never a value nor a
    name the value brings (brief, D30)."""
    if not isinstance(value, list):
        return a_kind(value)
    for item in value:
        if (wrong := item_misfit(field, item, declared)) is not None:
            return wrong
    raise ValueError("list_misfit is asked only of a value that doesn't fit")  # never reached


def item_misfit(field: str, item: object, declared: ListType) -> str | None:
    """What is wrong with one item of the list `field`, said as what the value gives; None if it
    fits."""
    if not isinstance(item, dict):
        return f"an item that is {a_kind(item)}"
    for name in declared.fields:
        if name not in item:
            return f"an item without {name}"
    if any(name not in declared.fields for name in item):
        return f"an item with a field {field} doesn't declare"
    for name, kind in declared.fields.items():
        if not fits(item[name], kind):
            return f"an item whose {name} is {a_kind(item[name])}"
    return None
