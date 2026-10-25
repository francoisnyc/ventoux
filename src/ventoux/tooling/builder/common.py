"""What a case and a plan write alike: a `display`, an expression where one is required, a field
a form sets (layer 14b) (brief, D58)."""

from typing import Any

from ventoux.tooling.builder.expressions import Expr
from ventoux.tooling.builder.fields import Data


def display(title: str, description: str | None) -> Data:
    """What people read: a title, and a description if one is given (brief, D5)."""
    data: Data = {"title": title}
    if description is not None:
        data["description"] = description
    return data


def given(value: object) -> Expr[Any]:
    """`value`, where a runtime expression is required: refused if it is a Python value, which
    the type checker refuses first (brief, D58)."""
    if not isinstance(value, Expr):
        raise TypeError(
            f"{value!r} is a Python value where a runtime expression is required: give a field, "
            "an expression, or literal(…) for a constant"
        )
    return value


def field_name(field: object, of: str = "the case file") -> str:
    """The name of `field`, a field of `of`: anything else can't be set by a form or a rule."""
    data = field.data if isinstance(field, Expr) else None
    if isinstance(data, dict) and set(data) == {"var"} and "." not in data["var"]:
        name: str = data["var"]
        return name
    raise TypeError(f"{field!r} is not a field of {of}: a form sets fields only")
