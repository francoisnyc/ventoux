"""The check: an expression's type against the declared fields, before anything runs."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from ventoux.core.expressions.model import (
    Add,
    And,
    BooleanType,
    Cat,
    Comparison,
    Count,
    DateType,
    Div,
    Exists,
    Expression,
    ExpressionInvalid,
    FieldType,
    If,
    In,
    Item,
    ListType,
    Mul,
    Node,
    Not,
    NumberType,
    Or,
    OutcomeType,
    ReferenceType,
    String,
    StringType,
    Sub,
    Sum,
    SumOver,
    Var,
    kind,
)


def check(expression: Expression, fields: Mapping[str, FieldType]) -> FieldType:
    """The type `expression` gives, checked against the declared `fields`, or `ExpressionInvalid`.

    An error starts with where it is inside the expression: `and[1].==[0]: …`.
    """
    return type_of(expression, fields, "")


def type_of(
    expression: Expression,
    fields: Mapping[str, FieldType],
    path: str,
    element: tuple[str, ListType] | None = None,
) -> FieldType:
    """The type of `expression`, found at `path` inside the expression being checked.

    `element` is the list `count` or `sum` is reading (its name and type), for `item`; it is passed
    down unchanged, and is `None` everywhere else.
    """
    if isinstance(expression, bool):
        return BooleanType()
    if isinstance(expression, str):
        return StringType()
    if isinstance(expression, Decimal):
        return NumberType()
    if isinstance(expression, date):
        return DateType()
    if isinstance(expression, Var):
        if expression.var not in fields:
            raise refused(path, f"{expression.var} is not a declared field")
        declared = fields[expression.var]
        # A list field is only read by `count` and `sum`, which check their `over` themselves.
        if isinstance(declared, ListType):
            raise refused(path, f"{expression.var} is a list; read it with count or sum")
        return declared
    if isinstance(expression, Exists):
        if expression.exists not in fields:
            raise refused(path, f"{expression.exists} is not a declared field")
        return BooleanType()
    if isinstance(expression, In):
        found = type_of(expression.args[0], fields, inside(path, "in[0]"), element)
        if not isinstance(found, NumberType | StringType | BooleanType | OutcomeType | DateType):
            raise refused(
                inside(path, "in[0]"),
                "`in` looks for a number, a string, a boolean, an outcome or a date, "
                f"and this is {a_type(found)}",
            )
        for position, literal in enumerate(expression.args[1]):
            if isinstance(found, OutcomeType) and isinstance(literal, str):
                # Outcomes are closed lists, in a list as in `==` (brief, D9).
                if literal not in found.outcomes:
                    raise refused(
                        inside(path, f"in[1][{position}]"),
                        f'{name_of(expression.args[0])} has no outcome "{literal}"; '
                        f"its outcomes are {', '.join(found.outcomes)}",
                    )
            elif kind(literal) != found.type:
                raise refused(
                    inside(path, "in[1]"),
                    f"`in` looks for {a_type(found)} in a list of {kind(literal)}s",
                )
        return BooleanType()
    if isinstance(expression, Comparison):
        operator = expression.operator
        steps = [inside(path, f"{operator}[{i}]") for i in range(2)]
        types = [
            type_of(a, fields, step, element)
            for a, step in zip(expression.args, steps, strict=True)
        ]
        if operator not in ("==", "!="):
            ordering_problem(operator, steps, types)
            return BooleanType()
        for argument, step, other, other_argument in zip(
            expression.args, steps, reversed(types), reversed(expression.args), strict=True
        ):
            # Outcomes are closed lists, so a misspelled one is caught here, not at runtime
            # (brief, D9).
            if isinstance(other, OutcomeType) and isinstance(argument, str):
                if argument not in other.outcomes:
                    raise refused(
                        step,
                        f'{name_of(other_argument)} has no outcome "{argument}"; '
                        f"its outcomes are {', '.join(other.outcomes)}",
                    )
                return BooleanType()
        # Otherwise the same type on both sides: a reference only to the same system (brief, D16).
        if types[0] != types[1]:
            raise refused(
                steps[1],
                f"`{operator}` compares values of the same type, "
                f"and this is {a_type(types[1])}, not {a_type(types[0])}",
            )
        return BooleanType()
    if isinstance(expression, And | Or):
        each_argument(
            expression.operator,
            expression.args,
            fields,
            element,
            path,
            "combines booleans",
            (BooleanType,),
        )
        return BooleanType()
    if isinstance(expression, Not):
        each_argument(
            "!", expression.args, fields, element, path, "takes a boolean", (BooleanType,)
        )
        return BooleanType()
    if isinstance(expression, Add | Sub | Mul | Div):
        verb = {"+": "adds", "-": "subtracts", "*": "multiplies", "/": "divides"}[
            expression.operator
        ]
        each_argument(
            expression.operator,
            expression.args,
            fields,
            element,
            path,
            f"{verb} numbers",
            (NumberType,),
        )
        return NumberType()
    if isinstance(expression, Cat):
        # An outcome is a text too; a number, boolean or reference becomes one through `string`.
        each_argument(
            "cat",
            expression.args,
            fields,
            element,
            path,
            "joins texts",
            (StringType, OutcomeType),
            "; write string(…) to turn it into text",
        )
        return StringType()
    if isinstance(expression, String):
        each_argument(
            "string",
            expression.args,
            fields,
            element,
            path,
            "takes a number, a boolean, a reference or a date",
            (NumberType, BooleanType, ReferenceType, DateType),
        )
        return StringType()
    if isinstance(expression, If):
        steps = [inside(path, f"if[{i}]") for i in range(3)]
        condition, then, otherwise = (
            type_of(a, fields, step, element)
            for a, step in zip(expression.args, steps, strict=True)
        )
        if not isinstance(condition, BooleanType):
            raise refused(steps[0], f"`if` takes a boolean, and this is {a_type(condition)}")
        # Both branches are checked, though only one runs (slice 6): either may be the one.
        if then != otherwise:
            raise refused(
                steps[2],
                f"`if`'s branches give the same type, and this is {a_type(otherwise)}, "
                f"not {a_type(then)}",
            )
        return then
    if isinstance(expression, Item):
        if element is None:
            # Fail closed, though `parse_expression` refuses `item` outside `count` and `sum`.
            raise refused(path, "item is only readable inside count and sum")
        over, listed = element
        if expression.item not in listed.fields:
            raise refused(path, f"item.{expression.item} is not a field of the elements of {over}")
        return listed.fields[expression.item]
    if isinstance(expression, Count | Sum):
        operator, args = expression.operator, expression.args
        over = args.over.var
        if over not in fields:
            raise refused(inside(path, f"{operator}.over"), f"{over} is not a declared field")
        declared = fields[over]
        if not isinstance(declared, ListType):
            raise refused(
                inside(path, f"{operator}.over"),
                f"{over} is {a_type(declared)}, and {operator} reads a list",
            )
        here = (over, declared)
        if args.where is not None:
            step = inside(path, f"{operator}.where")
            found = type_of(args.where, fields, step, here)
            if not isinstance(found, BooleanType):
                raise refused(step, f"`where` takes a boolean, and this is {a_type(found)}")
        if isinstance(args, SumOver):
            step = inside(path, "sum.value")
            found = type_of(args.value, fields, step, here)
            if not isinstance(found, NumberType):
                raise refused(step, f"`sum` adds numbers, and this is {a_type(found)}")
        return NumberType()
    # Fail closed: an expression the check doesn't know is refused, never assumed to be fine.
    raise refused(path, f"can't check {expression!r}")


def ordering_problem(operator: str, steps: list[str], types: list[FieldType]) -> None:
    """Refuse an ordering unless it compares two numbers or two dates (brief, D20) (brief, D66)."""
    orders = f"`{operator}` compares two numbers or two dates"
    for step, found in zip(steps, types, strict=True):
        if not isinstance(found, NumberType | DateType):
            raise refused(step, f"{orders}, and this is {a_type(found)}")
    if type(types[0]) is not type(types[1]):
        raise refused(steps[1], f"{orders}, and this is {a_type(types[1])}, not {a_type(types[0])}")


def each_argument(
    operator: str,
    arguments: tuple[Expression, ...],
    fields: Mapping[str, FieldType],
    element: tuple[str, ListType] | None,
    path: str,
    what_it_does: str,
    accepted: tuple[type[Node], ...],
    hint: str = "",
) -> None:
    """Check that each of `operator`'s arguments has one of the `accepted` types."""
    for position, argument in enumerate(arguments):
        step = inside(path, f"{operator}[{position}]")
        found = type_of(argument, fields, step, element)
        if not isinstance(found, accepted):
            raise refused(step, f"`{operator}` {what_it_does}, and this is {a_type(found)}{hint}")


def refused(path: str, message: str) -> ExpressionInvalid:
    """The check's error: where it is inside the expression, then what is wrong."""
    return ExpressionInvalid(f"{path}: {message}" if path else message)


def inside(path: str, step: str) -> str:
    """`step` appended to `path`: `and[1]` then `==[0]` gives `and[1].==[0]`."""
    return f"{path}.{step}" if path else step


def a_type(found: FieldType) -> str:
    """A type as a message says it: `a number`, `an outcome`, `a reference to orders`."""
    if isinstance(found, ReferenceType):
        return f"a reference to {found.system}"
    article = "an" if found.type[0] in "aeiou" else "a"
    return f"{article} {found.type}"


def name_of(expression: Expression) -> str:
    """How a message names an argument: a field by its name."""
    return expression.var if isinstance(expression, Var) else "this value"
