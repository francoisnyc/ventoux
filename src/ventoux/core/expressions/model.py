"""What an expression is: the operators, numbers and values, the field types, the errors."""

from decimal import ROUND_HALF_EVEN, Context, Decimal, DivisionByZero, InvalidOperation, Overflow
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

# The fixed list of operators. Adding one is a design decision recorded in the brief, never just a
# code change (brief, D20).
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

# Arithmetic as IEEE 754 decimal128: 34 significant digits, rounding half to even, exponents
# within ±6144, and an error rather than a special value when something goes wrong. Passed to every
# operation explicitly, so the process-wide `decimal.getcontext()` never decides a result
# (brief, D20).
CONTEXT = Context(
    prec=34,
    rounding=ROUND_HALF_EVEN,
    Emax=6144,
    Emin=-6143,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)

DECIMAL128 = "a decimal128 number (34 digits, exponents within ±6144)"


def fits_decimal128(number: Decimal) -> bool:
    """Whether `number` is exactly a decimal128 number: putting it through `CONTEXT` changes nothing.

    Both evaluators must hold the same numbers; the TypeScript one couldn't hold 1E+999999, or 35
    digits, exactly, so the two would disagree (brief, D20).
    """
    try:
        return CONTEXT.create_decimal(number) == number
    except Overflow:
        return False


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
    """A number: one type, exact decimal (brief, D20)."""

    type: Literal["number"] = "number"


class StringType(Node):
    """A text."""

    type: Literal["string"] = "string"


class BooleanType(Node):
    """`true` or `false`."""

    type: Literal["boolean"] = "boolean"


class OutcomeType(Node):
    """A task's answer: a closed list of names (brief, D9)."""

    type: Literal["outcome"] = "outcome"
    outcomes: tuple[str, ...] = Field(min_length=1)


class ReferenceType(Node):
    """The ID of a record kept in another system, typed by that system's name (brief, D16)."""

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


def kind(value: Value) -> str:
    """The name of a value's type, as the guide and the field declarations write it."""
    # `bool` first, as in the parser.
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    return "number"
