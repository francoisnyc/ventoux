"""Runtime expressions in Python: values only a case holds, told apart from build-time values by
their type (layer 14a) (brief, D58).

A field is not a number the builder knows: each case holds its own. So `approved > 100` can't be
`True` or `False` when the file runs; it is an `Expr[bool]`, written into the JSON as
`{">": [{"var": "approved_amount"}, 100]}` and decided by each case (brief, D20). A Python value
beside one (`100`) is a build-time literal, written as it is.

Each kind of value has its own class, so `==` takes only what the expression check accepts beside
it (layer 14b): a number with a number, a text with a text, an outcome with its name, a reference
with a reference. Every operator is a function named after the JSON's, with a trailing `_` where
Python has the name already. See docs/layers/14-builder.md.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, NoReturn, overload

from ventoux.core.expressions import ExpressionInvalid, parse_expression, render

# A build-time number: exact, never a binary float (brief, D20), never `True` (brief, D47).
type Number = int | Decimal


class BuildTimeDecision(TypeError):
    """A runtime expression asked for a Python value while the builder file runs."""


class Expr[T]:
    """A runtime expression: what each case decides when it runs. `T` says what it holds:
    `Decimal`, `str` or `bool`. Its JSON, kept in `data`, is the stored form (brief, D20)."""

    def __init__(self, data: object) -> None:
        self.data = data  # the expression as the JSON writes it: `{"var": "approved_amount"}`

    def __bool__(self) -> NoReturn:
        # Fail closed: `if`, `and`, `or`, `not` and `0 < x < 9` ask for a bool now, which only a
        # case can give (brief, D58).
        raise BuildTimeDecision(
            f"{said(self)} is decided by each case, when it runs, never when the file runs: give "
            "it as `when=`, and use and_, or_ and not_ to combine conditions"
        )

    def __repr__(self) -> str:
        return f"Expr({said(self)})"


# Python: `==` and `!=` normally give a bool; here they build an expression, as SQLAlchemy's
# columns do. Each kind takes only what may stand beside it, which narrows the parameter of
# `object.__eq__`: so each override is deliberate, and says so to mypy.


class BoolExpr(Expr[bool]):
    """A truth value each case holds: a `boolean` field, or what a comparison gives."""

    def __eq__(self, other: "BoolExpr | bool") -> "BoolExpr":  # type: ignore[override]
        return BoolExpr({"==": [self.data, of_kind(other, BoolExpr, bool)]})

    def __ne__(self, other: "BoolExpr | bool") -> "BoolExpr":  # type: ignore[override]
        return BoolExpr({"!=": [self.data, of_kind(other, BoolExpr, bool)]})


class NumberExpr(Expr[Decimal]):
    """A number each case holds: compared and computed with other numbers."""

    def __eq__(self, other: "NumberExpr | Number") -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"==": [self.data, number(other)]})

    def __ne__(self, other: "NumberExpr | Number") -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"!=": [self.data, number(other)]})

    def __gt__(self, other: "NumberExpr | Number") -> BoolExpr:
        return BoolExpr({">": [self.data, number(other)]})

    def __ge__(self, other: "NumberExpr | Number") -> BoolExpr:
        return BoolExpr({">=": [self.data, number(other)]})

    def __lt__(self, other: "NumberExpr | Number") -> BoolExpr:
        return BoolExpr({"<": [self.data, number(other)]})

    def __le__(self, other: "NumberExpr | Number") -> BoolExpr:
        return BoolExpr({"<=": [self.data, number(other)]})

    def __add__(self, other: "NumberExpr | Number") -> "NumberExpr":
        return NumberExpr({"+": [self.data, number(other)]})

    def __radd__(self, other: Number) -> "NumberExpr":
        return NumberExpr({"+": [number(other), self.data]})

    def __sub__(self, other: "NumberExpr | Number") -> "NumberExpr":
        return NumberExpr({"-": [self.data, number(other)]})

    def __rsub__(self, other: Number) -> "NumberExpr":
        return NumberExpr({"-": [number(other), self.data]})

    def __mul__(self, other: "NumberExpr | Number") -> "NumberExpr":
        return NumberExpr({"*": [self.data, number(other)]})

    def __rmul__(self, other: Number) -> "NumberExpr":
        return NumberExpr({"*": [number(other), self.data]})

    def __truediv__(self, other: "NumberExpr | Number") -> "NumberExpr":
        return NumberExpr({"/": [self.data, number(other)]})

    def __rtruediv__(self, other: Number) -> "NumberExpr":
        return NumberExpr({"/": [number(other), self.data]})


class TextExpr(Expr[str]):
    """A text each case holds: a `string` field, or what `cat` and `string` give."""

    def __eq__(self, other: "TextExpr | str") -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"==": [self.data, of_kind(other, TextExpr, str)]})

    def __ne__(self, other: "TextExpr | str") -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"!=": [self.data, of_kind(other, TextExpr, str)]})


class OutcomeExpr(Expr[str]):
    """A task's or a step's answer: one of a closed list of names, compared with a name
    (brief, D9). Whether the name is one of its outcomes is the expression check's to say."""

    def __eq__(self, other: str) -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"==": [self.data, of_kind(other, OutcomeExpr, str)]})

    def __ne__(self, other: str) -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"!=": [self.data, of_kind(other, OutcomeExpr, str)]})


class ReferenceExpr(Expr[str]):
    """The ID of a record kept in another system, compared only with another reference: never with
    a text, which would say nothing about which system (brief, D16)."""

    def __eq__(self, other: "ReferenceExpr") -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"==": [self.data, of_kind(other, ReferenceExpr, ReferenceExpr)]})

    def __ne__(self, other: "ReferenceExpr") -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"!=": [self.data, of_kind(other, ReferenceExpr, ReferenceExpr)]})


class DateExpr(Expr[date]):
    """A day each case holds: compared with another day, or a build-time `date` (brief, D66)."""

    def __eq__(self, other: "DateExpr | date") -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"==": [self.data, a_day(other)]})

    def __ne__(self, other: "DateExpr | date") -> BoolExpr:  # type: ignore[override]
        return BoolExpr({"!=": [self.data, a_day(other)]})

    def __gt__(self, other: "DateExpr | date") -> BoolExpr:
        return BoolExpr({">": [self.data, a_day(other)]})

    def __ge__(self, other: "DateExpr | date") -> BoolExpr:
        return BoolExpr({">=": [self.data, a_day(other)]})

    def __lt__(self, other: "DateExpr | date") -> BoolExpr:
        return BoolExpr({"<": [self.data, a_day(other)]})

    def __le__(self, other: "DateExpr | date") -> BoolExpr:
        return BoolExpr({"<=": [self.data, a_day(other)]})


def a_day(value: object) -> object:
    """`value` as a date operand's JSON: a date expression's own, or a build-time day written
    `{"date": "2026-10-31"}`. A `datetime` is a `date` to Python, so it is refused by its exact
    type: a moment is never a day (brief, D66)."""
    if isinstance(value, DateExpr):
        return value.data
    if isinstance(value, datetime):
        day = value.date()
        raise TypeError(
            f"{value!r} is a moment, and a date compares with a day: write "
            f"date({day.year}, {day.month}, {day.day})"
        )
    if type(value) is date:
        return {"date": value.isoformat()}
    raise TypeError(f"{value!r} can't be compared with DateExpr: write a date, date(2026, 10, 31)")


class ListExpr(Expr[list[object]]):
    """A list of records each case holds, read with `count` and `sum`. Each element's field is read
    with an accessor typed as the list declares it: `lines.number("amount")`."""

    def __init__(self, data: object, declared: Mapping[str, str]) -> None:
        super().__init__(data)
        self.declared = declared  # each element field's type: `{"amount": "number"}`

    def number(self, name: str) -> NumberExpr:
        """The element's number field `name`, inside `count` or `sum`."""
        return NumberExpr(self.item(name, "number"))

    def text(self, name: str) -> TextExpr:
        """The element's text field `name`, inside `count` or `sum`."""
        return TextExpr(self.item(name, "string"))

    def boolean(self, name: str) -> BoolExpr:
        """The element's truth value `name`, inside `count` or `sum`."""
        return BoolExpr(self.item(name, "boolean"))

    def reference(self, name: str) -> ReferenceExpr:
        """The element's reference `name`, inside `count` or `sum`."""
        return ReferenceExpr(self.item(name, "reference"))

    def item(self, name: str, kind: str) -> object:
        """`{"item": name}`, refused unless the list declares `name` as a `kind`: read otherwise,
        it would write another definition than the one declared."""
        list_name = self.data["var"] if isinstance(self.data, dict) else self.data
        if name not in self.declared:
            raise TypeError(f"{list_name} declares no field {name}")
        if self.declared[name] != kind:
            raise TypeError(f"{list_name} declares {name} as a {self.declared[name]}, not a {kind}")
        return {"item": name}


def of_kind(value: object, kind: type[Expr[Any]], literal_type: type) -> object:
    """`value` beside an expression of `kind`: one of the same kind, or a literal of
    `literal_type`. Refused otherwise, as the type checker refuses it first."""
    if isinstance(value, kind):
        return value.data
    # `bool` is checked as itself: in Python `True` is also an `int`.
    if not isinstance(value, Expr) and type(value) is literal_type:
        return value
    raise TypeError(f"{value!r} can't be compared with {kind.__name__}")


def operand(value: object) -> object:
    """`value` as an operand's JSON: an expression's own, or a build-time literal."""
    if isinstance(value, Expr):
        return value.data
    if isinstance(value, date):  # a `datetime` too, which `a_day` refuses (brief, D66)
        return a_day(value)
    # `bool` first: in Python `True` is also an `int`, and it is a truth value here, never 1.
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int | Decimal | float):
        return a_number(value)
    raise TypeError(
        f"{value!r} can't be written into a definition: a literal is a number (int or Decimal), "
        "a text, True or False, or a date"
    )


def number(value: object) -> object:
    """`value` as a number operand's JSON: a number expression's own, or a build-time number."""
    if isinstance(value, NumberExpr):
        return value.data
    return a_number(value)


def a_number(value: object) -> Number:
    """`value`, a build-time number, refused if it isn't an exact one (brief, D20)."""
    if isinstance(value, float):
        raise TypeError(
            f'{value} is a binary float: write Decimal("{value}"), so the number is exact'
        )
    # `bool` first: in Python `True` is also an `int`, and it is never the number 1 (brief, D47).
    if isinstance(value, bool) or not isinstance(value, int | Decimal):
        raise TypeError(f"{value!r} is not a number: write an int or a Decimal")
    if not Decimal(value).is_finite():
        raise TypeError(f"{value} is not a number a definition can hold")
    return value


# `True` is also an `int`, so the first two overlap for mypy; `bool` comes first, so it wins.
@overload
def literal(value: bool) -> BoolExpr: ...  # type: ignore[overload-overlap]
@overload
def literal(value: Number) -> NumberExpr: ...
@overload
def literal(value: str) -> TextExpr: ...
def literal(value: bool | Number | str) -> Expr[Any]:
    """A build-time value given where a runtime expression is required: `literal(250)`."""
    data = operand(value)
    if isinstance(value, bool):
        return BoolExpr(data)
    if isinstance(value, str):
        return TextExpr(data)
    return NumberExpr(data)


def and_(first: Expr[bool], second: Expr[bool], *more: Expr[bool]) -> BoolExpr:
    """All the conditions hold: `and`, of two or more, every one evaluated (brief, D20)."""
    return BoolExpr({"and": [condition.data for condition in (first, second, *more)]})


def or_(first: Expr[bool], second: Expr[bool], *more: Expr[bool]) -> BoolExpr:
    """Any of the conditions holds: `or`, of two or more, every one evaluated (brief, D20)."""
    return BoolExpr({"or": [condition.data for condition in (first, second, *more)]})


def not_(condition: Expr[bool]) -> BoolExpr:
    """`condition` doesn't hold: `!` (brief, D20)."""
    return BoolExpr({"!": [condition.data]})


# `True` is also an `int`, so the truth values' signature overlaps the numbers' for mypy; it comes
# first, so it wins.
@overload
def if_(  # type: ignore[overload-overlap]
    condition: Expr[bool], then: BoolExpr | bool, otherwise: BoolExpr | bool
) -> BoolExpr: ...
@overload
def if_(
    condition: Expr[bool], then: NumberExpr | Number, otherwise: NumberExpr | Number
) -> NumberExpr: ...
@overload
def if_(condition: Expr[bool], then: TextExpr | str, otherwise: TextExpr | str) -> TextExpr: ...
def if_(condition: Expr[bool], then: object, otherwise: object) -> Expr[Any]:
    """`then` when `condition` holds, else `otherwise`, both of one kind: `if` (brief, D20)."""
    data = {"if": [condition.data, operand(then), operand(otherwise)]}
    branches = (then, otherwise)
    # `bool` first: in Python `True` is also an `int`.
    if any(isinstance(b, BoolExpr | bool) for b in branches):
        return BoolExpr(data)
    if any(isinstance(b, TextExpr | str) for b in branches):
        return TextExpr(data)
    return NumberExpr(data)


def in_(
    value: NumberExpr | TextExpr | BoolExpr | OutcomeExpr | DateExpr,
    listed: Sequence[Number | str | bool | date],
) -> BoolExpr:
    """`value` is one of the `listed` build-time values: `in` (brief, D20)."""
    return BoolExpr({"in": [value.data, [operand(each) for each in listed]]})


def cat(*texts: TextExpr | OutcomeExpr | str) -> TextExpr:
    """The texts joined, an outcome being a text: `cat` (brief, D20)."""
    return TextExpr({"cat": [operand(text) for text in texts]})


def string(value: NumberExpr | BoolExpr | ReferenceExpr | DateExpr) -> TextExpr:
    """A number, a truth value, a reference or a date as a text: `string` (brief, D20)."""
    return TextExpr({"string": [value.data]})


def exists(field: Expr[Any]) -> BoolExpr:
    """Whether `field` has a value, never read as false when it hasn't: `exists` (brief, D20)."""
    data = field.data
    if not (isinstance(data, dict) and set(data) == {"var"}):
        raise TypeError(f"{field!r} is not a field: exists asks whether a field has a value")
    return BoolExpr({"exists": data["var"]})


def count(over: ListExpr, where: Expr[bool] | None = None) -> NumberExpr:
    """How many elements of `over` match `where`: `count` (brief, D20)."""
    shape: dict[str, object] = {"over": over.data}
    if where is not None:
        shape["where"] = where.data
    return NumberExpr({"count": shape})


def sum_(over: ListExpr, value: NumberExpr, where: Expr[bool] | None = None) -> NumberExpr:
    """The total of `value` over the elements of `over` that match `where`: `sum` (brief, D20)."""
    shape: dict[str, object] = {"over": over.data}
    if where is not None:
        shape["where"] = where.data
    shape["value"] = value.data
    return NumberExpr({"sum": shape})


def said(expression: Expr[Any]) -> str:
    """`expression` in its one-line form, as diffs and readings write it (brief, D20); its JSON
    when it can't be read alone (an `item`, read only inside `count` and `sum`)."""
    try:
        return render(parse_expression(expression.data))
    except ExpressionInvalid:
        return str(expression.data)
