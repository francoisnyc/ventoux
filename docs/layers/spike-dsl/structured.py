"""Structured JSON expressions: the third candidate of design question 11, built to measure it.

Not product code: the smallest version that answers the spike's questions (how much code is a
parser-free, fail-closed, typed expression form?). Imported by expressions.py.

The shape extends the tracer's (`{">": [{"field": "approved_amount"}, 100]}`): an expression is a
JSON literal (string, number, boolean), a field reference, or an object with exactly one operator
key. Pydantic does the parsing, so an unknown operator is a validation error, never a default.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class FieldRef(Node):
    field: str  # a case-file field, an outcome (`assess.outcome`) or `event.count`


class ItemRef(Node):
    item: str  # a field of the current item inside `sum`


class Eq(Node):
    args: tuple[Expr, Expr] = Field(alias="=")


class Ne(Node):
    args: tuple[Expr, Expr] = Field(alias="!=")


class Gt(Node):
    args: tuple[Expr, Expr] = Field(alias=">")


class Ge(Node):
    args: tuple[Expr, Expr] = Field(alias=">=")


class Lt(Node):
    args: tuple[Expr, Expr] = Field(alias="<")


class Le(Node):
    args: tuple[Expr, Expr] = Field(alias="<=")


class And(Node):
    args: list[Expr] = Field(alias="and", min_length=2)


class Or(Node):
    args: list[Expr] = Field(alias="or", min_length=2)


class Not(Node):
    arg: Expr = Field(alias="not")


class Add(Node):
    args: tuple[Expr, Expr] = Field(alias="+")


class Sub(Node):
    args: tuple[Expr, Expr] = Field(alias="-")


class If(Node):
    args: tuple[Expr, Expr, Expr] = Field(alias="if")


class Concat(Node):
    args: list[Expr] = Field(alias="concat", min_length=2)


class ToString(Node):
    arg: Expr = Field(alias="string")


class SumOf(Node):
    over: FieldRef
    where: Expr | None = None
    value: ItemRef


class Sum(Node):
    sum: SumOf


Operator = Eq | Ne | Gt | Ge | Lt | Le | And | Or | Not | Add | Sub | If | Concat | ToString | Sum
Expr = bool | int | float | str | FieldRef | ItemRef | Operator
for model in (Eq, Ne, Gt, Ge, Lt, Le, And, Or, Not, Add, Sub, If, Concat, ToString, SumOf, Sum):
    model.model_rebuild()

EXPR: TypeAdapter[Any] = TypeAdapter(Expr)


def parse(data: object) -> Any:
    """Validate JSON data as an expression; raises pydantic.ValidationError otherwise."""
    return EXPR.validate_python(data)


class EvalError(Exception):
    """Anything the evaluator can't evaluate. Never a permissive default (fail closed)."""


COMPARE = {
    Gt: lambda a, b: a > b,
    Ge: lambda a, b: a >= b,
    Lt: lambda a, b: a < b,
    Le: lambda a, b: a <= b,
}


def lookup(path: str, context: dict[str, Any]) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise EvalError(f"`{path}` has no value")  # a missing field is an error, never false
        value = value[part]
    return value


def number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvalError(f"expected a number, got {value!r}")
    return value


def boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise EvalError(f"expected true or false, got {value!r}")
    return value


def evaluate(expr: Any, context: dict[str, Any], item: dict[str, Any] | None = None) -> Any:
    match expr:
        case bool() | int() | float() | str():
            return expr
        case FieldRef(field=path):
            return lookup(path, context)
        case ItemRef(item=name):
            if item is None:
                raise EvalError(f"`item.{name}` outside a sum")
            return lookup(name, item)
        case Eq(args=(a, b)) | Ne(args=(a, b)):
            left, right = evaluate(a, context, item), evaluate(b, context, item)
            if type(left) is not type(right):
                raise EvalError(f"can't compare {left!r} with {right!r}")
            return (left == right) if isinstance(expr, Eq) else (left != right)
        case Gt(args=(a, b)) | Ge(args=(a, b)) | Lt(args=(a, b)) | Le(args=(a, b)):
            compare = COMPARE[type(expr)]
            return compare(number(evaluate(a, context, item)), number(evaluate(b, context, item)))
        # Lists, not generators: every operand is evaluated, so an error is never hidden by a
        # `false` on the other side (fail closed). Stricter than CEL, which may absorb it.
        case And(args=args):
            return all([boolean(evaluate(arg, context, item)) for arg in args])  # noqa: C419
        case Or(args=args):
            return any([boolean(evaluate(arg, context, item)) for arg in args])  # noqa: C419
        case Not(arg=arg):
            return not boolean(evaluate(arg, context, item))
        case Add(args=(a, b)):
            return number(evaluate(a, context, item)) + number(evaluate(b, context, item))
        case Sub(args=(a, b)):
            return number(evaluate(a, context, item)) - number(evaluate(b, context, item))
        case If(args=(condition, then, otherwise)):
            chosen = then if boolean(evaluate(condition, context, item)) else otherwise
            return evaluate(chosen, context, item)
        case Concat(args=args):
            parts = [evaluate(arg, context, item) for arg in args]
            if not all(isinstance(part, str) for part in parts):
                raise EvalError(f"concat needs strings, got {parts!r}")
            return "".join(parts)
        case ToString(arg=arg):
            value = evaluate(arg, context, item)
            if isinstance(value, bool) or not isinstance(value, int | float | str):
                raise EvalError(f"can't turn {value!r} into text")
            return str(value)
        case Sum(sum=SumOf(over=over, where=where, value=value)):
            items = lookup(over.field, context)
            if not isinstance(items, list):
                raise EvalError(f"`{over.field}` is not a list")
            chosen = [i for i in items if where is None or boolean(evaluate(where, context, i))]
            return sum(number(evaluate(value, context, i)) for i in chosen)
        case _:
            raise EvalError(f"unknown expression {expr!r}")


def reads(expr: Any) -> set[str]:
    """The case-file fields an expression reads: what provenance analysis needs (layer 4)."""
    match expr:
        case FieldRef(field=path):
            return {path}
        case Sum(sum=SumOf(over=over, where=where)):
            return {over.field} | (reads(where) if where is not None else set())
        case Node():
            found: set[str] = set()
            for value in expr.__dict__.values():
                children = value if isinstance(value, list | tuple) else [value]
                for child in children:
                    found |= reads(child)
            return found
        case _:
            return set()


# Field types, as a case definition declares them. An outcome is a closed list of names (D9).
Type = Literal["number", "string", "boolean"] | tuple[str, ...]


class Rejected(Exception):
    """A definition the validator rejects."""


def type_of(expr: Any, fields: dict[str, Type]) -> Type:
    """Check an expression against declared field types, before anything runs (layer 3)."""
    match expr:
        case bool():
            return "boolean"
        case int() | float():
            return "number"
        case str():
            return "string"
        case FieldRef(field=path):
            if path not in fields:
                raise Rejected(f"`{path}` is not a declared field")
            return fields[path]
        case Eq(args=(a, b)) | Ne(args=(a, b)):
            left, right = type_of(a, fields), type_of(b, fields)
            for side, other, literal in ((left, right, b), (right, left, a)):
                if isinstance(side, tuple):  # an outcome compared with a name it doesn't declare
                    if other != "string" or (isinstance(literal, str) and literal not in side):
                        raise Rejected(f"{literal!r} is not one of the outcomes {list(side)}")
                    return "boolean"
            if left != right:
                raise Rejected(f"can't compare {left} with {right}")
            return "boolean"
        case Gt(args=args) | Ge(args=args) | Lt(args=args) | Le(args=args):
            if [type_of(arg, fields) for arg in args] != ["number", "number"]:
                raise Rejected("comparisons need two numbers")
            return "boolean"
        case And(args=args) | Or(args=args):
            if any(type_of(arg, fields) != "boolean" for arg in args):
                raise Rejected("and/or need true or false on every side")
            return "boolean"
        case Not(arg=arg):
            if type_of(arg, fields) != "boolean":
                raise Rejected("not needs true or false")
            return "boolean"
        case Add(args=args) | Sub(args=args):
            if [type_of(arg, fields) for arg in args] != ["number", "number"]:
                raise Rejected("arithmetic needs two numbers")
            return "number"
        case If(args=(condition, then, otherwise)):
            if type_of(condition, fields) != "boolean":
                raise Rejected("if needs a true or false condition")
            then_type, otherwise_type = type_of(then, fields), type_of(otherwise, fields)
            if then_type != otherwise_type:
                raise Rejected(f"if's branches differ: {then_type} and {otherwise_type}")
            return then_type
        case Concat(args=args):
            if any(type_of(arg, fields) != "string" for arg in args):
                raise Rejected("concat needs text; use `string` to turn a number into text")
            return "string"
        case ToString(arg=arg):
            type_of(arg, fields)
            return "string"
        case Sum():
            return "number"  # item fields aren't typed in this sketch
        case _:
            raise Rejected(f"unknown expression {expr!r}")


OPERATORS = {"=": "=", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<=", "+": "+", "-": "-"}


def render(expr: Any) -> str:
    """A readable one-line form for people and diffs (printing needs no parser)."""
    match expr:
        case bool():
            return "true" if expr else "false"
        case str():
            return '"' + expr.replace('"', '\\"') + '"'
        case int() | float():
            return repr(expr)
        case FieldRef(field=path) | ItemRef(item=path):
            return path
        case Not(arg=arg):
            return f"not ({render(arg)})"
        case And(args=args) | Or(args=args):
            joiner = " and " if isinstance(expr, And) else " or "
            return joiner.join(
                f"({render(a)})" if isinstance(a, And | Or) else render(a) for a in args
            )
        case If(args=(c, a, b)):
            return f"{render(c)} ? {render(a)} : {render(b)}"
        case Concat(args=args):
            return " & ".join(render(a) for a in args)
        case ToString(arg=arg):
            return f"string({render(arg)})"
        case Sum(sum=SumOf(over=over, where=where, value=value)):
            filtered = f"[{render(where)}]" if where is not None else ""
            return f"sum({over.field}{filtered}.{value.item})"
        case Node():
            (key,) = expr.model_dump(by_alias=True).keys()
            a, b = next(iter(expr.__dict__.values()))
            return f"{render(a)} {OPERATORS[key]} {render(b)}"
        case _:
            raise Rejected(f"unknown expression {expr!r}")
