"""Provenance: where a value came from, as a set of sources (brief, D12).

A source is a text, `origin:name`. See docs/layers/04-provenance.md.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ventoux.core.expressions import (
    Add,
    And,
    Cat,
    Count,
    Div,
    Exists,
    Expression,
    If,
    In,
    Item,
    Mul,
    Not,
    Or,
    String,
    Sub,
    Sum,
    Var,
)
from ventoux.core.expressions.model import Comparison

# The origins a value can come from: a system, or a person's answer, both trusted; or something a
# developer declared untrusted, such as `untrusted:llm` (brief, D12).
TRUSTED_ORIGINS = ("system:", "person:")
UNTRUSTED_ORIGIN = "untrusted:"
# A plan field with no declared source: the case gives it, and the plan can't see its origin. Only
# the static check uses it; the runtime check sees the real sources (docs/layers/04-provenance.md).
CASE = "case"


# How a label is written, `customer` or `customer-portal`: a lowercase letter, then lowercase
# letters, digits or `-`.
LABEL = re.compile(r"[a-z][a-z0-9-]*")


def is_label(text: str) -> bool:
    """Whether `text` is written as a label: `llm` and `customer-portal` are, `LLM` and `` aren't."""
    return LABEL.fullmatch(text) is not None


def is_trusted(source: str) -> bool:
    """Whether `source` is one the engine trusts: from a system, a person, or the case."""
    return source == CASE or source.startswith(TRUSTED_ORIGINS)


def is_untrusted(source: str) -> bool:
    """Whether `source` was declared untrusted, such as `untrusted:llm`."""
    return source.startswith(UNTRUSTED_ORIGIN)


@dataclass(frozen=True)
class Sourced:
    """A value, and where it came from: the sources it was derived from."""

    value: object  # the value itself, as expressions read it
    sources: frozenset[str]  # where it came from, such as `system:opener` or `untrusted:llm`


def sourced(value: object, *sources: str) -> Sourced:
    """`value`, with its sources: `sourced(Decimal("250"), "system:opener")`."""
    return Sourced(value, frozenset(sources))


class NoSources(LookupError):
    """A field whose sources aren't known: never read as "no sources"."""


def provenance(expression: Expression, sources: Mapping[str, frozenset[str]]) -> frozenset[str]:
    """The sources of `expression`'s value: those of every field it reads, from `sources`."""
    found: frozenset[str] = frozenset()
    for field in fields_read(expression):
        # Fail closed: a field whose sources aren't known is an error, never "no sources", which
        # would read as a value written in the definition.
        if field not in sources:
            raise NoSources(f"{field} has no known sources")
        found |= sources[field]
    return found


def fields_read(expression: Expression) -> list[str]:
    """The fields `expression` reads, in order, conditions included."""
    if isinstance(expression, Decimal | str | bool):
        return []  # a literal reads nothing
    if isinstance(expression, Var):
        return [expression.var]
    if isinstance(expression, Exists):
        return [expression.exists]  # whether a value exists depends on whoever set it
    if isinstance(expression, Item):
        return []  # an element of the list `count` or `sum` reads: the list is already counted
    if isinstance(expression, Count | Sum):
        # The list, which elements count, and (for `sum`) what each adds.
        parts = [expression.args.over, expression.args.where]
        if isinstance(expression, Sum):
            parts.append(expression.args.value)
        return [field for part in parts if part is not None for field in fields_read(part)]
    if isinstance(expression, In):
        return fields_read(expression.args[0])  # the list after it holds only literals
    if isinstance(
        expression, Comparison | And | Or | Not | Add | Sub | Mul | Div | If | Cat | String
    ):
        # Each argument is an expression; `if`'s condition included, since it decides the value.
        return [field for argument in expression.args for field in fields_read(argument)]
    # Fail closed: what this walk doesn't know is an error, never "reads no field". A new operator
    # lands here until it says what it reads (brief, D20).
    raise TypeError(f"not an expression: {type(expression).__name__}")
