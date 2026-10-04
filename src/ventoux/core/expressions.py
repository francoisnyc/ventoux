"""Expressions: structured JSON with the operators of decision D3 (layer 2)."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

# The fixed list (D3). Adding an operator is a design decision recorded in the brief, never just a
# code change.
OPERATORS = (
    "var",
    "==",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "and",
    "or",
    "!",
    "+",
    "-",
    "*",
    "/",
    "if",
    "in",
    "cat",
    "string",
    "exists",
    "count",
    "sum",
    "item",
)


class Var(BaseModel):
    """A declared field of the case file: `{"var": "approved_amount"}`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    var: str


class ExpressionInvalid(Exception):
    """An expression that can't be accepted: refused before anything runs."""


type Expression = Decimal | str | bool | Var


def parse_expression(data: object) -> Expression:
    """The expression stored as `data`, or `ExpressionInvalid` saying what is wrong with it."""
    # `bool` first: in Python `True` is also an `int`, and it must never become the number 1.
    if isinstance(data, bool | str):
        return data
    if isinstance(data, int | Decimal):
        return Decimal(data)
    if isinstance(data, float):
        # Refused, not converted: the reader already turned 0.1 into a binary approximation (D3).
        raise ExpressionInvalid(
            f"{data} is a binary float, and numbers must be exact decimals: read the JSON with "
            "json.loads(text, parse_float=Decimal)"
        )
    if data is None:
        raise ExpressionInvalid("null is not a value in an expression; use exists(field)")
    if isinstance(data, dict):
        if len(data) != 1:
            raise ExpressionInvalid(
                "an operator is an object with exactly one key, "
                f"and this one has {len(data)}: {', '.join(data)}"
            )
        [(operator, arguments)] = data.items()
        # Fail closed: anything not on the list is refused, so `now` can't be written.
        if operator not in OPERATORS:
            raise ExpressionInvalid(
                f"`{operator}` is not an operator. The operators are: {', '.join(OPERATORS)}. "
                "Logic that doesn't fit is a compute activity."
            )
        if operator == "var":
            # Stricter than JsonLogic (D3): no default to fall back on, and no reading everything.
            if not isinstance(arguments, str) or not arguments:
                raise ExpressionInvalid(
                    'var takes the name of one field, like {"var": "approved_amount"}: '
                    "no default, and never the whole case file"
                )
            return Var(var=arguments)
        if isinstance(arguments, list):
            for argument in arguments:
                parse_expression(argument)
    # Fail closed: whatever isn't recognised above is refused, never passed through.
    raise ExpressionInvalid(f"not an expression: {data!r}")
