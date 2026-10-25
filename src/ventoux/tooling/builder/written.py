"""A definition's JSON as text: one layout, the same bytes every time (layer 14a) (brief, D58).

The layout is the standard library's `json.dumps(data, indent=2, ensure_ascii=False)`, then one
line break. The standard library can't write a `Decimal` as the decimal it is, only through a
binary float, so the layout is written here: one function, the same text `json.dumps` gives for
everything else (a test holds the two together). See docs/layers/14-builder.md, choice 4.
"""

import json
from decimal import Decimal

from ventoux.tooling.builder.case import Case

INDENT = "  "


class NotWritable(ValueError):
    """A value the JSON can't hold so that it reads back the same."""


def written(case: Case) -> str:
    """`case`'s `case.json`, as its bytes will be: what is checked, released and run."""
    text = layout(case.definition()) + "\n"
    # Fail closed: a text that doesn't read back to itself would be another definition once read.
    again = layout(json.loads(text, parse_float=Decimal)) + "\n"
    if again != text:
        raise NotWritable(f"{case.name} doesn't read back as written")
    return text


def layout(value: object, level: int = 0) -> str:
    """`value` in `json.dumps`'s `indent=2` layout, starting at nesting `level`."""
    inner, outer = INDENT * (level + 1), INDENT * level
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{inner}{text(key)}: {layout(item, level + 1)}" for key, item in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + outer + "}"
    if isinstance(value, list | tuple):
        if not value:
            return "[]"
        items = [f"{inner}{layout(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(items) + "\n" + outer + "]"
    if isinstance(value, str):
        return text(value)
    # `bool` first: in Python `True` is also an `int`.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return decimal(value)
    raise NotWritable(f"{value!r} can't be written into a definition")


def text(value: str) -> str:
    """A JSON string, as `json.dumps` writes it, keeping non-ASCII characters as they are."""
    return json.dumps(value, ensure_ascii=False)


def decimal(value: Decimal) -> str:
    """`value` as the decimal the engine holds: `100.0` stays `100.0` (brief, D50)."""
    if not value.is_finite():
        raise NotWritable(f"{value} is not a number JSON can hold")
    # Python: format "f" writes every digit, never an exponent: `Decimal("1E-7")` is `0.0000001`.
    said = format(value, "f")
    # `Decimal("1E+2")` would be written `100`, and read back as another decimal (brief, D50).
    if str(Decimal(said)) != str(value):
        raise NotWritable(f'{value} reads back as {Decimal(said)}: write Decimal("{said}")')
    return said
