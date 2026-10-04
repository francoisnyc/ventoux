"""Expressions: structured JSON with the operators of decision D3 (layer 2)."""

from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Context, Decimal, DivisionByZero, InvalidOperation, Overflow
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

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

# Arithmetic as IEEE 754 decimal128 (D3): 34 significant digits, rounding half to even, exponents
# within ±6144, and an error rather than a special value when something goes wrong. Passed to every
# operation explicitly, so the process-wide `decimal.getcontext()` never decides a result.
CONTEXT = Context(
    prec=34,
    rounding=ROUND_HALF_EVEN,
    Emax=6144,
    Emin=-6143,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)

# What an expression gives, and what it is: a literal, a field, or one operator with its arguments.
# Recursive, so the models below can hold expressions; a `type` alias is resolved when first used.
type Value = Decimal | str | bool
type Expression = (
    Decimal
    | str
    | bool
    | Var
    | Eq
    | Ne
    | Gt
    | Ge
    | Lt
    | Le
    | And
    | Or
    | Not
    | Add
    | Sub
    | Mul
    | Div
)


class Node(BaseModel):
    """One operator and its arguments, stored as `{"operator": arguments}`."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Var(Node):
    """A declared field of the case file: `{"var": "approved_amount"}`."""

    var: str


class Comparison(Node):
    """Two arguments compared. Each kind names its operator, the key it is stored under."""

    operator: ClassVar[str]
    args: tuple[Expression, Expression]


class Eq(Comparison):
    """`{"==": [a, b]}`: a equals b."""

    operator: ClassVar[str] = "=="
    args: tuple[Expression, Expression] = Field(alias="==")


class Ne(Comparison):
    """`{"!=": [a, b]}`: a differs from b."""

    operator: ClassVar[str] = "!="
    args: tuple[Expression, Expression] = Field(alias="!=")


class Gt(Comparison):
    """`{">": [a, b]}`: a is greater than b."""

    operator: ClassVar[str] = ">"
    args: tuple[Expression, Expression] = Field(alias=">")


class Ge(Comparison):
    """`{">=": [a, b]}`: a is greater than or equal to b."""

    operator: ClassVar[str] = ">="
    args: tuple[Expression, Expression] = Field(alias=">=")


class Lt(Comparison):
    """`{"<": [a, b]}`: a is less than b."""

    operator: ClassVar[str] = "<"
    args: tuple[Expression, Expression] = Field(alias="<")


class Le(Comparison):
    """`{"<=": [a, b]}`: a is less than or equal to b."""

    operator: ClassVar[str] = "<="
    args: tuple[Expression, Expression] = Field(alias="<=")


class And(Node):
    """`{"and": [a, b, …]}`: every argument is true."""

    operator: ClassVar[str] = "and"

    args: tuple[Expression, ...] = Field(alias="and", min_length=2)


class Or(Node):
    """`{"or": [a, b, …]}`: at least one argument is true."""

    operator: ClassVar[str] = "or"

    args: tuple[Expression, ...] = Field(alias="or", min_length=2)


class Not(Node):
    """`{"!": [a]}`: a is false."""

    operator: ClassVar[str] = "!"

    args: tuple[Expression] = Field(alias="!")


class Add(Node):
    """`{"+": [a, b, …]}`: the sum of the arguments."""

    operator: ClassVar[str] = "+"
    args: tuple[Expression, ...] = Field(alias="+", min_length=2)


class Sub(Node):
    """`{"-": [a, b]}`: a minus b."""

    operator: ClassVar[str] = "-"
    args: tuple[Expression, Expression] = Field(alias="-")


class Mul(Node):
    """`{"*": [a, b, …]}`: the product of the arguments."""

    operator: ClassVar[str] = "*"
    args: tuple[Expression, ...] = Field(alias="*", min_length=2)


class Div(Node):
    """`{"/": [a, b]}`: a divided by b."""

    operator: ClassVar[str] = "/"
    args: tuple[Expression, Expression] = Field(alias="/")


COMPARISONS: dict[str, type[Eq] | type[Ne] | type[Gt] | type[Ge] | type[Lt] | type[Le]] = {
    kind.operator: kind for kind in (Eq, Ne, Gt, Ge, Lt, Le)
}


class ExpressionInvalid(Exception):
    """An expression that can't be accepted: refused before anything runs."""


class ExpressionError(Exception):
    """An expression that can't be evaluated against these values: the step stops."""


def parse_expression(data: object) -> Expression:
    """The expression stored as `data`, or `ExpressionInvalid` saying what is wrong with it."""
    # `bool` first: in Python `True` is also an `int`, and it must never become the number 1.
    if isinstance(data, bool | str):
        return data
    if isinstance(data, int | Decimal):
        # Fail closed: `Infinity > 100` is true, so an infinite amount would pass any threshold.
        if not Decimal(data).is_finite():
            raise ExpressionInvalid(f"{data} is not a number an expression can use")
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
        if operator in COMPARISONS:
            parsed = parsed_arguments(operator, arguments, 2)
            return COMPARISONS[operator].model_validate({operator: parsed})
        if operator == "and":
            return And.model_validate({"and": parsed_arguments("and", arguments, 2, or_more=True)})
        if operator == "or":
            return Or.model_validate({"or": parsed_arguments("or", arguments, 2, or_more=True)})
        if operator == "!":
            return Not.model_validate({"!": parsed_arguments("!", arguments, 1)})
        if operator == "+":
            return Add.model_validate({"+": parsed_arguments("+", arguments, 2, or_more=True)})
        if operator == "-":
            return Sub.model_validate({"-": parsed_arguments("-", arguments, 2)})
        if operator == "*":
            return Mul.model_validate({"*": parsed_arguments("*", arguments, 2, or_more=True)})
        if operator == "/":
            return Div.model_validate({"/": parsed_arguments("/", arguments, 2)})
        if isinstance(arguments, list):
            for argument in arguments:
                parse_expression(argument)
    # Fail closed: whatever isn't recognised above is refused, never passed through.
    raise ExpressionInvalid(f"not an expression: {data!r}")


def parsed_arguments(
    operator: str, arguments: object, count: int, *, or_more: bool = False
) -> list[Expression]:
    """`arguments` parsed, if they are a list of `count` (or more), else `ExpressionInvalid`."""
    if isinstance(arguments, list) and (
        len(arguments) == count or (or_more and len(arguments) > count)
    ):
        return [parse_expression(argument) for argument in arguments]
    plural = "argument" if count == 1 else "arguments"
    more = " or more" if or_more else ""
    # `!` alone gets an example: JsonLogic also accepts `{"!": x}`, which we refuse (D3).
    example = ', like {"!": [x]}' if operator == "!" else ""
    raise ExpressionInvalid(f"`{operator}` takes a list of {count}{more} {plural}{example}")


def evaluate(expression: Expression, values: Mapping[str, object]) -> Value:
    """The value of `expression` against the case file's `values`, or `ExpressionError`."""
    if isinstance(expression, bool | str | Decimal):
        return expression
    if isinstance(expression, Var):
        if expression.var not in values:
            # Fail closed: a missing value is an error that stops the step, never `false` (D3).
            raise ExpressionError(f"{expression.var} has no value")
        value = values[expression.var]
        # The case file is data from outside: check what it holds, never assume it.
        if not isinstance(value, bool | str | Decimal):
            raise ExpressionError(
                f"{expression.var} holds {value!r}, a {type(value).__name__}, and an expression "
                "reads only decimals, texts and booleans"
            )
        if isinstance(value, Decimal) and not value.is_finite():
            raise ExpressionError(
                f"{expression.var} holds {value}, which is not a number an expression can use"
            )
        return value
    if isinstance(expression, Comparison):
        left, right = (evaluate(argument, values) for argument in expression.args)
        return compare(expression.operator, left, right)
    if isinstance(expression, And | Or):
        # Every part is evaluated before combining, so an error is never hidden behind a part
        # that already decided the answer (D3). Python's `all` and `any` would stop early.
        parts = [boolean(expression.operator, evaluate(a, values)) for a in expression.args]
        return all(parts) if isinstance(expression, And) else any(parts)
    if isinstance(expression, Not):
        return not boolean("!", evaluate(expression.args[0], values))
    if isinstance(expression, Add | Sub | Mul | Div):
        numbers = [number(expression.operator, evaluate(a, values)) for a in expression.args]
        result = numbers[0]
        for n in numbers[1:]:
            result = calculate(expression.operator, result, n)
        return result
    # Fail closed: anything the evaluator has no case for is an error, never a default.
    raise ExpressionError(f"can't evaluate {expression!r}: it isn't a parsed expression")


def calculate(operator: str, a: Decimal, b: Decimal) -> Decimal:
    """`a` and `b` combined by one of the four arithmetic operators, in decimal128."""
    if operator == "/" and b == 0:
        raise ExpressionError(f"division by zero: {shown(a)} / {shown(b)}")
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
        # No coercion (D3): in Python `True == 1`, so the types are compared first.
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
    """`value` as a boolean for `operator`; nothing is truthy (D3)."""
    if not isinstance(value, bool):
        verb = "takes a boolean" if operator == "!" else "combines booleans"
        raise ExpressionError(
            f"`{operator}` {verb}, and it was given a {kind(value)}: {shown(value)}"
        )
    return value


def number(operator: str, value: Value) -> Decimal:
    """`value` as a number for `operator`; no coercion from a text or a boolean (D3)."""
    if not isinstance(value, Decimal):
        verb = {"+": "adds", "-": "subtracts", "*": "multiplies", "/": "divides"}.get(
            operator, "compares"
        )
        raise ExpressionError(
            f"`{operator}` {verb} numbers, and it was given a {kind(value)}: {shown(value)}"
        )
    return value


def kind(value: Value) -> str:
    """The name of a value's type, as the guide and the field declarations write it."""
    # `bool` first, as in the parser.
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    return "number"


def shown(value: Value) -> str:
    """`value` as a message shows it: `250`, `'250'`, `true`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return repr(value)
    return str(value)
