"""The renderer: an expression on one line, FEEL-style, for people to read."""

import json
from datetime import date
from decimal import Decimal

from ventoux.core.expressions.model import (
    Add,
    And,
    Cat,
    Comparison,
    Count,
    CountOver,
    Div,
    Exists,
    Expression,
    ExpressionInvalid,
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
    Var,
)


def render(expression: Expression) -> str:
    """`expression` on one line, for diffs and reviews: `review.outcome = "approve"`.

    FEEL-style, the expression language of DMN and Camunda 8, which business readers know: `=` for
    `==`, and `not(...)` (brief, D20). For reading only: nothing ever parses it back, so none of
    FEEL's behaviour comes with it. What is stored is the JSON.
    """
    if isinstance(expression, bool):
        return "true" if expression else "false"
    if isinstance(expression, str):
        # JSON's escapes: a quote inside a text can't make the line read as something else.
        return json.dumps(expression, ensure_ascii=False)
    if isinstance(expression, Decimal):
        return str(expression)
    if isinstance(expression, date):
        return f'date("{expression.isoformat()}")'  # FEEL's literal; never its `today()`
    if isinstance(expression, Var):
        return expression.var
    if isinstance(expression, Exists):
        return f"exists({expression.exists})"
    if isinstance(expression, Item):
        return f"item.{expression.item}"
    if isinstance(expression, Comparison | And | Or | Add | Sub | Mul | Div):
        level = precedence(expression)
        symbol = "=" if expression.operator == "==" else expression.operator
        return f" {symbol} ".join(operand(a, level) for a in expression.args)
    if isinstance(expression, Not):
        # A call, as in FEEL: `not(a and b)` needs no other brackets to read unambiguously.
        return f"not({render(expression.args[0])})"
    if isinstance(expression, If):
        condition, then, otherwise = (operand(a, precedence(expression)) for a in expression.args)
        return f"if {condition} then {then} else {otherwise}"
    if isinstance(expression, In):
        options = ", ".join(render(option) for option in expression.args[1])
        return f"{operand(expression.args[0], precedence(expression))} in [{options}]"
    if isinstance(expression, Cat | String):
        return f"{expression.operator}({', '.join(render(a) for a in expression.args)})"
    if isinstance(expression, Count):
        return f"count({chosen(expression.args)})"
    if isinstance(expression, Sum):
        return f"sum({render(expression.args.value)} over {chosen(expression.args)})"
    # Fail closed: an expression the renderer doesn't know is refused, never printed as a guess.
    raise ExpressionInvalid(f"can't render {expression!r}: it isn't a parsed expression")


def chosen(args: CountOver | SumOver) -> str:
    """The elements `count` or `sum` reads: `items` or `items where item.risk = "high"`."""
    where = f" where {render(args.where)}" if args.where is not None else ""
    return f"{args.over.var}{where}"


OR_LEVEL = 1  # where `or` binds, between `if` (0) and `and` (2)


def operand(child: Expression, level: int) -> str:
    """`child` rendered inside an operator of precedence `level`, in parentheses if needed.

    A child that binds no tighter than its parent is bracketed, so the line shows exactly what is
    stored: `(amount - fee) - 1` and `amount - (fee - 1)` are different expressions.
    """
    text = render(child)
    # `and` binds tighter than `or`, but `a and b or c` is easy to misread: always bracket the mix.
    mixed = isinstance(child, And) and level == OR_LEVEL
    return f"({text})" if precedence(child) <= level or mixed else text


def precedence(expression: Expression) -> int:
    """How tightly `expression` binds when rendered: `if` loosest, a field or a call tightest."""
    if isinstance(expression, If):
        return 0
    if isinstance(expression, Or):
        return OR_LEVEL
    if isinstance(expression, And):
        return 2
    if isinstance(expression, Comparison | In):
        return 4
    if isinstance(expression, Add | Sub):
        return 5
    if isinstance(expression, Mul | Div):
        return 6
    return 7
