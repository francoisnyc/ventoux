"""From JSON to an expression: one clear refusal for anything that isn't one."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from ventoux.core.dates import HOW_TO_WRITE, calendar_date
from ventoux.core.expressions.model import (
    COMPARISONS,
    DECIMAL128,
    OPERATORS,
    Add,
    And,
    Cat,
    Count,
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
    Value,
    Var,
    fits_decimal128,
    kind,
)


def parse_expression(data: object) -> Expression:
    """The expression stored as `data`, or `ExpressionInvalid` saying what is wrong with it."""
    if too_deep(data):
        raise ExpressionInvalid(
            f"an expression is nested at most {MAX_DEPTH} levels deep, and this one goes deeper; "
            "logic this deep belongs in a compute activity"
        )
    expression = parse(data)
    if item_outside(expression):
        raise ExpressionInvalid(
            "item reads a field of the current element, so it is only allowed inside count and sum"
        )
    return expression


MAX_DEPTH = 32  # plenty for a condition people can read; a model could write far deeper


def too_deep(data: object) -> bool:
    """Whether `data` nests more than `MAX_DEPTH` objects, each object being one level.

    Counted with a list of pending parts, not by recursion, so an input thousands of levels deep is
    refused before it can exhaust Python's stack.
    """
    pending: list[tuple[object, int]] = [(data, 0)]
    while pending:
        part, depth = pending.pop()
        if isinstance(part, dict):
            if depth + 1 > MAX_DEPTH:
                return True
            pending.extend((child, depth + 1) for child in part.values())
        elif isinstance(part, list):
            pending.extend((child, depth) for child in part)
    return False


def item_outside(node: object) -> bool:
    """Whether `node` reads `item` anywhere but inside a `count` or `sum`."""
    if isinstance(node, Item):
        return True
    if isinstance(node, Count | Sum):
        return False  # `over` is a field; `where` and `value` may read the current element
    if isinstance(node, BaseModel):
        return any(item_outside(child) for child in node.__dict__.values())
    if isinstance(node, tuple):
        return any(item_outside(child) for child in node)
    return False


def parse(data: object) -> Expression:
    """`data` parsed recursively; `parse_expression` then checks where `item` is used."""
    # `bool` first: in Python `True` is also an `int`, and it must never become the number 1.
    if isinstance(data, bool | str):
        return data
    if isinstance(data, int | Decimal):
        # Fail closed: `Infinity > 100` is true, so an infinite amount would pass any threshold.
        if not Decimal(data).is_finite():
            raise ExpressionInvalid(f"{data} is not a number an expression can use")
        if not fits_decimal128(Decimal(data)):
            raise ExpressionInvalid(f"{data} doesn't fit {DECIMAL128}")
        return Decimal(data)
    if isinstance(data, float):
        # Refused, not converted: the reader already turned 0.1 into a binary approximation.
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
            # No default to fall back on, and no reading everything: stricter than JsonLogic
            # (brief, D20).
            if not isinstance(arguments, str) or not arguments:
                raise ExpressionInvalid(
                    'var takes the name of one field, like {"var": "approved_amount"}: '
                    "no default, and never the whole case file"
                )
            return Var(var=arguments)
        if operator == "count":
            shape = aggregate_shape("count", arguments)
            return Count.model_validate({"count": parsed_fields(shape)})
        if operator == "sum":
            shape = aggregate_shape("sum", arguments)
            return Sum.model_validate({"sum": parsed_fields(shape)})
        if operator == "item":
            if not isinstance(arguments, str) or not arguments:
                raise ExpressionInvalid('item takes the name of one field, like {"item": "amount"}')
            return Item(item=arguments)
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
        if operator == "if":
            return If.model_validate({"if": parsed_arguments("if", arguments, 3)})
        if operator == "in":
            return In.model_validate({"in": in_list(arguments)})
        if operator == "cat":
            return Cat.model_validate({"cat": parsed_arguments("cat", arguments, 1, or_more=True)})
        if operator == "string":
            return String.model_validate({"string": parsed_arguments("string", arguments, 1)})
        if operator == "date":
            return a_day(arguments)
        if operator == "exists":
            if not isinstance(arguments, str) or not arguments:
                raise ExpressionInvalid(
                    'exists takes the name of one field, like {"exists": "approved_amount"}'
                )
            return Exists(exists=arguments)
    # Fail closed: whatever isn't recognised above is refused, never passed through.
    raise ExpressionInvalid(f"not an expression: {data!r}")


def a_day(arguments: object) -> date:
    """The day a `date` literal names, or `ExpressionInvalid` saying how to write one
    (brief, D66)."""
    if not isinstance(arguments, str):
        raise ExpressionInvalid('date takes a text, like {"date": "2026-10-31"}')
    day = calendar_date(arguments)
    if day is None:
        raise ExpressionInvalid(f'date: "{arguments}" is not a day on the calendar; {HOW_TO_WRITE}')
    return day


def parsed_arguments(
    operator: str, arguments: object, count: int, *, or_more: bool = False
) -> list[Expression]:
    """`arguments` parsed, if they are a list of `count` (or more), else `ExpressionInvalid`."""
    if isinstance(arguments, list) and (
        len(arguments) == count or (or_more and len(arguments) > count)
    ):
        return [parse(argument) for argument in arguments]
    plural = "argument" if count == 1 and not or_more else "arguments"
    more = " or more" if or_more else ""
    # `!` alone gets an example: JsonLogic also accepts `{"!": x}`, which we refuse.
    example = ', like {"!": [x]}' if operator == "!" else ""
    raise ExpressionInvalid(f"`{operator}` takes a list of {count}{more} {plural}{example}")


def aggregate_shape(operator: str, arguments: object) -> dict[str, object]:
    """`count`'s or `sum`'s object, if its keys and its `over` are right, else `ExpressionInvalid`."""
    needed = {"over", "value"} if operator == "sum" else {"over"}
    allowed = needed | {"where"}
    if (
        isinstance(arguments, dict)
        and needed <= arguments.keys() <= allowed
        and isinstance(arguments["over"], dict)
        and arguments["over"].keys() == {"var"}
    ):
        return arguments
    value = ', "value": …' if operator == "sum" else ""
    raise ExpressionInvalid(
        f'`{operator}` takes {{"over": {{"var": "items"}}, "where": …{value}}}, '
        'with "where" optional'
    )


def parsed_fields(shape: dict[str, object]) -> dict[str, Expression]:
    """Each of `count`'s or `sum`'s fields (`over`, `where`, `value`) parsed."""
    return {name: parse(field) for name, field in shape.items()}


IN_LIST = '`in` takes a value and a list of values, like {"in": [x, ["approve", "escalate"]]}'


def in_list(arguments: object) -> tuple[Expression, tuple[Value, ...]]:
    """`in`'s value and its list of literals, or `ExpressionInvalid`."""
    if not isinstance(arguments, list) or len(arguments) != 2:
        raise ExpressionInvalid(IN_LIST)
    value, options = arguments
    if isinstance(options, str):
        # JsonLogic's `in` also finds "app" in "approve"; a condition never searches a text.
        raise ExpressionInvalid(IN_LIST + "; it never searches a text")
    if not isinstance(options, list):
        raise ExpressionInvalid(IN_LIST)
    if not options:
        raise ExpressionInvalid("`in` needs at least one value in its list")
    literals: list[Value] = []
    for option in options:
        literal = parse(option)
        if not isinstance(literal, bool | str | Decimal | date):
            raise ExpressionInvalid(IN_LIST + "; the list holds literal values")
        literals.append(literal)
    kinds = list(dict.fromkeys(kind(literal) for literal in literals))  # in the list's order
    if len(kinds) > 1:
        raise ExpressionInvalid(
            f"`in`'s list holds values of one type, and this one mixes {' and '.join(kinds)}"
        )
    return parse(value), tuple(literals)
