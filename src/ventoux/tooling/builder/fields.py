"""The types a field is declared with, in a case, a plan, an event's payload or a list's elements:
`Field.number()` (layer 14a) (brief, D58).

Each type says what the JSON declares (`{"type": "number"}`) and which runtime expression the field
reads as, so `amount > 100` type-checks and `note > 100` doesn't.
See docs/layers/14-builder.md.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ventoux.tooling.builder.expressions import (
    BoolExpr,
    DateExpr,
    Expr,
    ListExpr,
    NumberExpr,
    OutcomeExpr,
    ReferenceExpr,
    TextExpr,
)

# A definition's JSON, as plain data: dicts, lists, texts, numbers and truth values.
type Data = dict[str, Any]


@dataclass(frozen=True)
class FieldType[E: Expr[Any]]:
    """A field's type: what the JSON declares, and the runtime expression the field reads as."""

    declared: Data  # `{"type": "number"}`, written flat beside the field's other keys
    reads_as: Callable[[object], E]  # given `{"var": name}`, the field as an expression


class Field:
    """The types a field is declared with (brief, D20): `Field.number()`."""

    @staticmethod
    def number() -> FieldType[NumberExpr]:
        """A number: one type, an exact decimal (brief, D20)."""
        return FieldType({"type": "number"}, NumberExpr)

    @staticmethod
    def string() -> FieldType[TextExpr]:
        """A text."""
        return FieldType({"type": "string"}, TextExpr)

    @staticmethod
    def boolean() -> FieldType[BoolExpr]:
        """`true` or `false`."""
        return FieldType({"type": "boolean"}, BoolExpr)

    @staticmethod
    def outcome(*outcomes: str) -> FieldType[OutcomeExpr]:
        """One of a closed list of names, as a task's answer is (brief, D9)."""
        return FieldType({"type": "outcome", "outcomes": list(outcomes)}, OutcomeExpr)

    @staticmethod
    def reference(system: str) -> FieldType[ReferenceExpr]:
        """The ID of a record kept in `system`, never a copy of it (brief, D8)."""
        return FieldType({"type": "reference", "system": system}, ReferenceExpr)

    @staticmethod
    def date() -> FieldType[DateExpr]:
        """A day on the calendar, with no time and no time zone (brief, D66)."""
        return FieldType({"type": "date"}, DateExpr)

    @staticmethod
    def list(**fields: FieldType[Any]) -> FieldType[ListExpr]:
        """A list of records, each with `fields`, read with `count` and `sum` (brief, D20)."""
        declared = {name: kind.declared for name, kind in fields.items()}
        types = {name: str(kind.declared["type"]) for name, kind in fields.items()}

        def reads_as(data: object) -> ListExpr:
            return ListExpr(data, types)

        return FieldType({"type": "list", "fields": declared}, reads_as)
