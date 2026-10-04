"""Expressions: structured JSON with the operators of decision D3 (layer 2)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, DivisionByZero, InvalidOperation, Overflow
from typing import ClassVar, Literal

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
    | If
    | In
    | Cat
    | String
    | Exists
    | Item
    | Count
    | Sum
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


class If(Node):
    """`{"if": [condition, then, else]}`."""

    operator: ClassVar[str] = "if"
    args: tuple[Expression, Expression, Expression] = Field(alias="if")


class In(Node):
    """`{"in": [a, [x, y, …]]}`: a is one of the listed values."""

    operator: ClassVar[str] = "in"
    args: tuple[Expression, tuple[Value, ...]] = Field(alias="in")


class Cat(Node):
    """`{"cat": [a, b, …]}`: the texts joined."""

    operator: ClassVar[str] = "cat"
    args: tuple[Expression, ...] = Field(alias="cat", min_length=1)


class String(Node):
    """`{"string": [a]}`: a number, boolean or reference as text."""

    operator: ClassVar[str] = "string"
    args: tuple[Expression] = Field(alias="string")


class Exists(Node):
    """`{"exists": "approved_amount"}`: whether the field has a value."""

    exists: str


class Item(Node):
    """`{"item": "amount"}`: a field of the current element, inside `count` and `sum`."""

    item: str


class CountOver(Node):
    """What `count` reads: a list field, and which of its elements to count."""

    over: Var
    where: Expression | None = None


class SumOver(Node):
    """What `sum` reads: a list field, which of its elements, and the number each one adds."""

    over: Var
    where: Expression | None = None
    value: Expression


class Count(Node):
    """`{"count": {"over": list, "where": condition}}`: how many elements match."""

    operator: ClassVar[str] = "count"
    args: CountOver = Field(alias="count")


class Sum(Node):
    """`{"sum": {"over": list, "where": condition, "value": number}}`: their total."""

    operator: ClassVar[str] = "sum"
    args: SumOver = Field(alias="sum")


COMPARISONS: dict[str, type[Eq] | type[Ne] | type[Gt] | type[Ge] | type[Lt] | type[Le]] = {
    kind.operator: kind for kind in (Eq, Ne, Gt, Ge, Lt, Le)
}


# The types a field can be declared with, in the shape definitions use: `{"type": "number"}`.
# Recursive through `ListType`, so the alias comes first, as `Expression` does.
type FieldType = NumberType | StringType | BooleanType | OutcomeType | ReferenceType | ListType


class NumberType(Node):
    """A number: one type, exact decimal (D3)."""

    type: Literal["number"] = "number"


class StringType(Node):
    """A text."""

    type: Literal["string"] = "string"


class BooleanType(Node):
    """`true` or `false`."""

    type: Literal["boolean"] = "boolean"


class OutcomeType(Node):
    """A task's answer: a closed list of names (D9)."""

    type: Literal["outcome"] = "outcome"
    outcomes: tuple[str, ...] = Field(min_length=1)


class ReferenceType(Node):
    """The ID of a record kept in another system, typed by that system's name (D16)."""

    type: Literal["reference"] = "reference"
    system: str


class ListType(Node):
    """A list of records, each with the declared fields; read with `count`, `sum` and `item`."""

    type: Literal["list"] = "list"
    fields: dict[str, FieldType]


class ExpressionInvalid(Exception):
    """An expression that can't be accepted: refused before anything runs."""


class ExpressionError(Exception):
    """An expression that can't be evaluated against these values: the step stops."""


def parse_expression(data: object) -> Expression:
    """The expression stored as `data`, or `ExpressionInvalid` saying what is wrong with it."""
    expression = parse(data)
    if item_outside(expression):
        raise ExpressionInvalid(
            "item reads a field of the current element, so it is only allowed inside count and sum"
        )
    return expression


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
        if operator == "exists":
            if not isinstance(arguments, str) or not arguments:
                raise ExpressionInvalid(
                    'exists takes the name of one field, like {"exists": "approved_amount"}'
                )
            return Exists(exists=arguments)
    # Fail closed: whatever isn't recognised above is refused, never passed through.
    raise ExpressionInvalid(f"not an expression: {data!r}")


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
    # `!` alone gets an example: JsonLogic also accepts `{"!": x}`, which we refuse (D3).
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
        if not isinstance(literal, bool | str | Decimal):
            raise ExpressionInvalid(IN_LIST + "; the list holds literal values")
        literals.append(literal)
    kinds = list(dict.fromkeys(kind(literal) for literal in literals))  # in the list's order
    if len(kinds) > 1:
        raise ExpressionInvalid(
            f"`in`'s list holds values of one type, and this one mixes {' and '.join(kinds)}"
        )
    return parse(value), tuple(literals)


@dataclass(frozen=True)
class Element:
    """The record of a list field that `count` or `sum` is looking at, for `item` to read."""

    fields: Mapping[str, object]
    label: str  # "element 2 of items", for messages


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
        if not isinstance(found, NumberType | StringType | BooleanType | OutcomeType):
            raise refused(
                inside(path, "in[0]"),
                "`in` looks for a number, a string, a boolean or an outcome, "
                f"and this is {a_type(found)}",
            )
        for position, literal in enumerate(expression.args[1]):
            if isinstance(found, OutcomeType) and isinstance(literal, str):
                # Outcomes are closed lists (D9), in a list as in `==`.
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
            for step, found in zip(steps, types, strict=True):
                if not isinstance(found, NumberType):
                    raise refused(
                        step, f"`{operator}` compares numbers, and this is {a_type(found)}"
                    )
            return BooleanType()
        for argument, step, other, other_argument in zip(
            expression.args, steps, reversed(types), reversed(expression.args), strict=True
        ):
            # Outcomes are closed lists (D9), so a misspelled one is caught here, not at runtime.
            if isinstance(other, OutcomeType) and isinstance(argument, str):
                if argument not in other.outcomes:
                    raise refused(
                        step,
                        f'{name_of(other_argument)} has no outcome "{argument}"; '
                        f"its outcomes are {', '.join(other.outcomes)}",
                    )
                return BooleanType()
        # Otherwise the same type on both sides: a reference only to the same system (D16).
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
            "takes a number, a boolean or a reference",
            (NumberType, BooleanType, ReferenceType),
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
        # that already decided the answer (D3). Python's `all` and `any` would stop early.
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
            # Both: the fields say where to look, the values what happened.
            raise ExpressionError(
                f"division by zero in {render(expression)} "
                f"({shown(numbers[0])} / {shown(numbers[1])})"
            )
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
        # Fail closed: a missing value is an error that stops the step, never `false` (D3).
        raise ExpressionError(f"{name} has no value{where}")
    # The case file is data from outside: check what it holds, never assume it.
    if not isinstance(value, bool | str | Decimal):
        raise ExpressionError(
            f"{name} holds {value!r}, a {type(value).__name__}, and an expression "
            f"reads only decimals, texts and booleans{where}"
        )
    if isinstance(value, Decimal) and not value.is_finite():
        raise ExpressionError(
            f"{name} holds {value}, which is not a number an expression can use{where}"
        )
    return value


def records(operator: str, name: str, values: Mapping[str, object]) -> list[Mapping[str, object]]:
    """The list field `name` that `count` or `sum` reads: a list of records, each a mapping."""
    held = values.get(name)
    if held is None:
        raise ExpressionError(f"{name} has no value")
    if not isinstance(held, list) or not all(isinstance(element, Mapping) for element in held):
        raise ExpressionError(f"{name} holds {held!r}, and {operator} reads a list of records")
    return held


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
        verb = "takes a boolean" if operator in ("!", "if", "where") else "combines booleans"
        raise ExpressionError(
            f"`{operator}` {verb}, and it was given a {kind(value)}: {shown(value)}"
        )
    return value


def text(value: Value) -> str:
    """`value` as a text for `cat`; a number or a boolean is turned into text only by `string`."""
    if not isinstance(value, str):
        raise ExpressionError(
            f"`cat` joins texts, and it was given a {kind(value)}: {shown(value)}; "
            "write string(…) to turn it into text"
        )
    return value


def number(operator: str, value: Value) -> Decimal:
    """`value` as a number for `operator`; no coercion from a text or a boolean (D3)."""
    if not isinstance(value, Decimal):
        verb = {
            "+": "adds",
            "sum": "adds",
            "-": "subtracts",
            "*": "multiplies",
            "/": "divides",
        }.get(operator, "compares")
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


def render(expression: Expression) -> str:
    """`expression` on one line, for diffs and reviews: `approved_amount > 100`.

    For reading only: nothing ever parses it back. What is stored is the JSON.
    """
    if isinstance(expression, bool):
        return "true" if expression else "false"
    if isinstance(expression, str):
        # JSON's escapes: a quote inside a text can't make the line read as something else.
        return json.dumps(expression, ensure_ascii=False)
    if isinstance(expression, Decimal):
        return str(expression)
    if isinstance(expression, Var):
        return expression.var
    if isinstance(expression, Exists):
        return f"exists({expression.exists})"
    if isinstance(expression, Item):
        return f"item.{expression.item}"
    if isinstance(expression, Comparison | And | Or | Add | Sub | Mul | Div):
        level = precedence(expression)
        return f" {expression.operator} ".join(operand(a, level) for a in expression.args)
    if isinstance(expression, Not):
        return f"not {operand(expression.args[0], precedence(expression))}"
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
    """The elements `count` or `sum` reads: `items` or `items where item.risk == "high"`."""
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
    if isinstance(expression, Not):
        return 3
    if isinstance(expression, Comparison | In):
        return 4
    if isinstance(expression, Add | Sub):
        return 5
    if isinstance(expression, Mul | Div):
        return 6
    return 7
