"""The evaluator: an expression's value against the case file, failing closed."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, Overflow

from ventoux.core.expressions.model import (
    CONTEXT,
    DECIMAL128,
    Add,
    And,
    Cat,
    Comparison,
    Count,
    CountOver,
    Div,
    Exists,
    Expression,
    ExpressionError,
    If,
    In,
    Item,
    Mul,
    Not,
    Or,
    String,
    Sub,
    Sum,
    SumOver,
    Value,
    Var,
    a_kind,
    fits_decimal128,
    kind,
)
from ventoux.core.expressions.render import (
    render,
)


@dataclass(frozen=True)
class Element:
    """The record of a list field that `count` or `sum` is looking at, for `item` to read."""

    fields: Mapping[str, object]
    label: str  # "element 2 of items", for messages


def evaluate(
    expression: Expression, values: Mapping[str, object], element: Element | None = None
) -> Value:
    """The value of `expression` against the case file's `values`, or `ExpressionError`.

    `element` is the record `count` or `sum` is looking at, for `item` to read; it is passed down
    unchanged, and is `None` everywhere else.
    """
    if isinstance(expression, bool | str | Decimal):
        return expression
    if isinstance(expression, Var):
        return readable(expression.var, values.get(expression.var))
    if isinstance(expression, Item):
        if element is None:
            # Fail closed, though `parse_expression` refuses `item` outside `count` and `sum`.
            raise ExpressionError("item is only readable inside count and sum")
        field = f"item.{expression.item}"
        return readable(field, element.fields.get(expression.item), f" ({element.label})")
    if isinstance(expression, Comparison):
        left, right = (evaluate(argument, values, element) for argument in expression.args)
        return compare(expression.operator, left, right)
    if isinstance(expression, And | Or):
        # Every part is evaluated before combining, so an error is never hidden behind a part
        # that already decided the answer (brief, D20). Python's `all` and `any` would stop early.
        parts = [
            boolean(expression.operator, evaluate(a, values, element)) for a in expression.args
        ]
        return all(parts) if isinstance(expression, And) else any(parts)
    if isinstance(expression, Not):
        return not boolean("!", evaluate(expression.args[0], values, element))
    if isinstance(expression, Add | Sub | Mul | Div):
        numbers = [
            number(expression.operator, evaluate(a, values, element)) for a in expression.args
        ]
        if isinstance(expression, Div) and numbers[1] == 0:
            # The fields say where to look; never the values, which may be hidden from whoever
            # reads the history (brief, D30).
            raise ExpressionError(f"division by zero in {render(expression)}")
        result = numbers[0]
        for n in numbers[1:]:
            result = calculate(expression.operator, result, n)
        return result
    if isinstance(expression, Exists):
        # The one way to ask about a missing value, said out loud in the definition.
        return values.get(expression.exists) is not None
    if isinstance(expression, In):
        found, options = evaluate(expression.args[0], values, element), expression.args[1]
        # Same rule as `==`: no coercion, and in Python `True in [1]` would be true.
        if kind(found) != kind(options[0]):
            raise ExpressionError(
                f"`in` looks for a {kind(found)} in a list of {kind(options[0])}s"
            )
        return found in options
    if isinstance(expression, Cat):
        return "".join(text(evaluate(argument, values, element)) for argument in expression.args)
    if isinstance(expression, String):
        value = evaluate(expression.args[0], values, element)
        if isinstance(value, bool):
            return "true" if value else "false"
        # A number keeps its own digits: `250.00` stays `250.00`. Formatting is a compute activity.
        return str(value)
    if isinstance(expression, If):
        condition, then, otherwise = expression.args
        return evaluate(
            then if boolean("if", evaluate(condition, values, element)) else otherwise,
            values,
            element,
        )
    if isinstance(expression, Count):
        return Decimal(len(matching(expression.operator, expression.args, values)))
    if isinstance(expression, Sum):
        total = Decimal(0)
        # `value` is read only for the elements `where` chose, as `if` reads only its branch.
        for here in matching(expression.operator, expression.args, values):
            amount = number("sum", evaluate(expression.args.value, values, here))
            total = calculate("+", total, amount)
        return total
    # Fail closed: anything the evaluator has no case for is an error, never a default.
    raise ExpressionError(f"can't evaluate {expression!r}: it isn't a parsed expression")


def matching(
    operator: str, args: CountOver | SumOver, values: Mapping[str, object]
) -> list[Element]:
    """The elements of `args.over` that `args.where` chooses (all of them, with no `where`)."""
    over, where = args.over.var, args.where
    chosen = []
    # Every element is looked at: no early exit, so an error in any of them stops the step.
    for position, fields in enumerate(records(operator, over, values), start=1):
        here = Element(fields, f"element {position} of {over}")
        if where is None or boolean("where", evaluate(where, values, here)):
            chosen.append(here)
    return chosen


def readable(name: str, value: object, where: str = "") -> Value:
    """`value` of the field `name`, if an expression can read it, else `ExpressionError`."""
    if value is None:
        # Fail closed: a missing value is an error that stops the step, never `false` (brief, D20).
        raise ExpressionError(f"{name} has no value{where}")
    # The case file is data from outside: check what it holds, never assume it.
    if not isinstance(value, bool | str | Decimal):
        raise ExpressionError(
            f"{name} holds {a_kind(value)}, and an expression reads only decimals, texts and "
            f"booleans{where}"
        )
    if isinstance(value, Decimal) and not value.is_finite():
        raise ExpressionError(
            f"{name} holds a number that isn't finite, which an expression can't use{where}"
        )
    if isinstance(value, Decimal) and not fits_decimal128(value):
        raise ExpressionError(f"{name} holds a number that doesn't fit {DECIMAL128}{where}")
    return value


def records(operator: str, name: str, values: Mapping[str, object]) -> list[Mapping[str, object]]:
    """The list field `name` that `count` or `sum` reads: a list of records, each a mapping."""
    held = values.get(name)
    if held is None:
        raise ExpressionError(f"{name} has no value")
    if not isinstance(held, list) or not all(isinstance(element, Mapping) for element in held):
        raise ExpressionError(
            f"{name} holds {a_kind(held)}, and {operator} reads a list of records"
        )
    return held


def calculate(operator: str, a: Decimal, b: Decimal) -> Decimal:
    """`a` and `b` combined by one of the four arithmetic operators, in decimal128."""
    if operator == "/" and b == 0:
        raise ExpressionError("division by zero")
    try:
        if operator == "+":
            return CONTEXT.add(a, b)
        if operator == "-":
            return CONTEXT.subtract(a, b)
        if operator == "*":
            return CONTEXT.multiply(a, b)
        if operator == "/":
            return CONTEXT.divide(a, b)
    except Overflow:
        raise ExpressionError(
            f"`{operator}` gives a number too large for an expression (decimal128)"
        ) from None
    # Fail closed, though the parser builds only the four above.
    raise ExpressionError(f"`{operator}` is not arithmetic")


def compare(operator: str, left: Value, right: Value) -> bool:
    """`left` and `right` compared by one of the six comparison operators."""
    if operator in ("==", "!="):
        # No coercion: in Python `True == 1`, so the types are compared first (brief, D20).
        if kind(left) != kind(right):
            raise ExpressionError(
                f"`{operator}` compares values of the same type, "
                f"and it was given a {kind(left)} and a {kind(right)}"
            )
        equal = left == right
        return equal if operator == "==" else not equal
    a, b = number(operator, left), number(operator, right)
    if operator == ">":
        return a > b
    if operator == ">=":
        return a >= b
    if operator == "<":
        return a < b
    if operator == "<=":
        return a <= b
    # Fail closed, though the parser builds only the six above.
    raise ExpressionError(f"`{operator}` is not a comparison")


def boolean(operator: str, value: Value) -> bool:
    """`value` as a boolean for `operator`; nothing is truthy (brief, D20)."""
    if not isinstance(value, bool):
        verb = "takes a boolean" if operator in ("!", "if", "where") else "combines booleans"
        raise ExpressionError(f"`{operator}` {verb}, and it was given {a_kind(value)}")
    return value


def text(value: Value) -> str:
    """`value` as a text for `cat`; a number or a boolean is turned into text only by `string`."""
    if not isinstance(value, str):
        raise ExpressionError(
            f"`cat` joins texts, and it was given {a_kind(value)}; "
            "write string(…) to turn it into text"
        )
    return value


def number(operator: str, value: Value) -> Decimal:
    """`value` as a number for `operator`; no coercion from a text or a boolean (brief, D20)."""
    if not isinstance(value, Decimal):
        verb = {
            "+": "adds",
            "sum": "adds",
            "-": "subtracts",
            "*": "multiplies",
            "/": "divides",
        }.get(operator, "compares")
        raise ExpressionError(f"`{operator}` {verb} numbers, and it was given {a_kind(value)}")
    return value
