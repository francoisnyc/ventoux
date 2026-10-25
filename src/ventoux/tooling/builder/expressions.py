"""Runtime expressions in Python: values only a case holds, told apart from build-time values by
their type (layer 14a) (brief, D58).

A field is not a number the builder knows: each case holds its own. So `approved > 100` can't be
`True` or `False` when the file runs; it is an `Expr[bool]`, written into the JSON as
`{">": [{"var": "approved_amount"}, 100]}` and decided by each case (brief, D20). A Python value beside one
(`100`) is a build-time literal, written as it is.
See docs/layers/14-builder.md.
"""

from decimal import Decimal
from typing import Any, NoReturn, overload

from ventoux.core.expressions import parse_expression, render

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

    # Python: `==` and `!=` normally give a bool; here they build an expression, as SQLAlchemy's
    # columns do, so the override of `object.__eq__` is deliberate.
    def __eq__(self, other: object) -> "Expr[bool]":  # type: ignore[override]
        return Expr({"==": [self.data, operand(other)]})

    def __ne__(self, other: object) -> "Expr[bool]":  # type: ignore[override]
        return Expr({"!=": [self.data, operand(other)]})

    def __repr__(self) -> str:
        return f"Expr({said(self)})"


class NumberExpr(Expr[Decimal]):
    """A number each case holds: compared and computed with other numbers."""

    def __gt__(self, other: "NumberExpr | Number") -> Expr[bool]:
        return Expr({">": [self.data, number(other)]})

    def __ge__(self, other: "NumberExpr | Number") -> Expr[bool]:
        return Expr({">=": [self.data, number(other)]})

    def __lt__(self, other: "NumberExpr | Number") -> Expr[bool]:
        return Expr({"<": [self.data, number(other)]})

    def __le__(self, other: "NumberExpr | Number") -> Expr[bool]:
        return Expr({"<=": [self.data, number(other)]})

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


def operand(value: object) -> object:
    """`value` as an operand's JSON: an expression's own, or a build-time literal."""
    if isinstance(value, Expr):
        return value.data
    # `bool` first: in Python `True` is also an `int`, and it is a truth value here, never 1.
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int | Decimal | float):
        return a_number(value)
    raise TypeError(
        f"{value!r} can't be written into a definition: a literal is a number (int or Decimal), "
        "a text or True or False"
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
def literal(value: bool) -> Expr[bool]: ...  # type: ignore[overload-overlap]
@overload
def literal(value: Number) -> NumberExpr: ...
@overload
def literal(value: str) -> Expr[str]: ...
def literal(value: bool | Number | str) -> Expr[Any]:
    """A build-time value given where a runtime expression is required: `literal(250)`."""
    data = operand(value)
    if isinstance(value, bool | str):
        return Expr(data)
    return NumberExpr(data)


def and_(first: Expr[bool], second: Expr[bool], *more: Expr[bool]) -> Expr[bool]:
    """All the conditions hold: `and`, of two or more, every one evaluated (brief, D20)."""
    return Expr({"and": [condition.data for condition in (first, second, *more)]})


def or_(first: Expr[bool], second: Expr[bool], *more: Expr[bool]) -> Expr[bool]:
    """Any of the conditions holds: `or`, of two or more, every one evaluated (brief, D20)."""
    return Expr({"or": [condition.data for condition in (first, second, *more)]})


def not_(condition: Expr[bool]) -> Expr[bool]:
    """`condition` doesn't hold: `!` (brief, D20)."""
    return Expr({"!": [condition.data]})


def said(expression: Expr[Any]) -> str:
    """`expression` in its one-line form, as diffs and readings write it (brief, D20)."""
    return render(parse_expression(expression.data))
