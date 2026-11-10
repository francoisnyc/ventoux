"""A contract's input and output, described by Ventoux: never by pydantic (the contract hash fix)
(brief, D83).

A contract's hash covers its promise, and its promise holds its models as JSON Schema. Written by
pydantic, that schema changed when pydantic did (2.13 writes a decimal's text form with a pattern,
2.14 doesn't), and with it the hash. A contract's field is one of a closed set (brief, D20)
(brief, D36), so Ventoux writes each itself, exactly as pydantic 2.13.5 did: every hash recorded
so far stands. What Ventoux doesn't describe is refused when the contract is made.
"""

import inspect
from datetime import date
from decimal import Decimal
from types import NoneType, UnionType
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from ventoux.core.output_sources import OutputSource
from ventoux.core.policy import Policy
from ventoux.core.references import Reference

# What may sit in a contract field's `Annotated[...]`: Ventoux's own markers, which it writes.
MARKERS = (Reference, Policy, OutputSource)
# What a field may not set: pydantic would write each into the schema, and Ventoux doesn't.
FIELD_SETTINGS = (
    "title",
    "alias",
    "validation_alias",
    "serialization_alias",
    "examples",
    "json_schema_extra",
    "discriminator",
    "default_factory",
)
MODEL_SETTINGS = ("title", "json_schema_extra")  # in a model's `model_config`
NOT_WRITTEN = (
    "which Ventoux doesn't write into the contract's promise, so its hash wouldn't cover it"
)


def undescribed(side: str, model: type[BaseModel]) -> list[str]:
    """Everything on `model` (a contract's `side`, input or output) Ventoux doesn't describe,
    one line each, saying what is wrong, then what to do."""
    found = [
        f"{side} {model.__name__} sets {setting} in its model_config, {NOT_WRITTEN}: remove it"
        for setting in MODEL_SETTINGS
        if model.model_config.get(setting) is not None
    ]
    for name, field in model.model_fields.items():
        where = f"{side} {name}"
        found += [
            f"{where} has a constraint ({type(item).__name__}), {NOT_WRITTEN}: remove it, and "
            "check the value where it is used"
            for item in field.metadata
            if not isinstance(item, MARKERS)
        ]
        found += [
            f"{where} sets its {setting}, {NOT_WRITTEN}: remove it"
            for setting in FIELD_SETTINGS
            if getattr(field, setting, None) is not None
        ]
        default = field.default
        if default is not PydanticUndefined and not isinstance(default, (str, bool, type(None))):
            found.append(
                f"{where} defaults to a {type(default).__name__}: a default is None, true or "
                "false, or a text; give one of those, or none"
            )
    return found


# The text form of a decimal, as pydantic 2.13.5 wrote it: kept, so every recorded hash stands.
DECIMAL_TEXT = "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$"


def described(model: type[BaseModel]) -> dict[str, Any]:
    """`model`, a contract's input or output, as JSON Schema: written by Ventoux, as pydantic
    2.13.5 wrote it (brief, D83)."""
    schema: dict[str, Any] = {
        "properties": {name: field_described(name, f) for name, f in model.model_fields.items()},
        "title": model.__name__,
        "type": "object",
    }
    required = [name for name, field in model.model_fields.items() if field.is_required()]
    if required:
        schema["required"] = required  # in the fields' order, as declared
    if model.__doc__:
        schema["description"] = inspect.cleandoc(model.__doc__)  # a docstring, its indent removed
    return schema


def field_described(name: str, field: FieldInfo) -> dict[str, Any]:
    """One field: its type's forms (and null, if it is optional), its title, its description and
    default, and what Ventoux's markers on it say."""
    kind, optional = unwrapped(field.annotation)
    forms = forms_of(kind) + ([{"type": "null"}] if optional else [])
    schema: dict[str, Any] = {"anyOf": forms} if len(forms) > 1 else dict(forms[0])
    schema["title"] = name.title().replace("_", " ").strip()  # `risk_score` → `Risk Score`
    if field.description is not None:
        schema["description"] = field.description
    if field.default is not PydanticUndefined:
        schema["default"] = field.default  # None, true or false, or a text: refused otherwise
    for marker in field.metadata:
        if isinstance(marker, Reference):
            schema["x-reference"] = marker.system
        elif isinstance(marker, Policy):
            schema.setdefault("x-input-policies", []).append(marker.promise())
        elif isinstance(marker, OutputSource):
            schema["x-source"] = marker.source
    return schema


def unwrapped(annotation: Any) -> tuple[Any, bool]:
    """The type a field holds, and whether it may also be None: `Decimal | None` is
    `(Decimal, True)`."""
    # typing: `Decimal | None` is a union; its other member is the type held.
    if get_origin(annotation) in (Union, UnionType):
        held = [member for member in get_args(annotation) if member is not NoneType]
        if len(held) == 1:
            return held[0], True
    return annotation, False


def forms_of(kind: Any) -> list[dict[str, Any]]:
    """The JSON Schema forms a value of `kind` takes: a decimal is a number or its text."""
    if kind is str:
        return [{"type": "string"}]
    if kind is bool:
        return [{"type": "boolean"}]
    if kind is Decimal:
        return [{"type": "number"}, {"pattern": DECIMAL_TEXT, "type": "string"}]
    if kind is date:
        return [{"format": "date", "type": "string"}]
    # typing: `Literal["low", "high"]` takes exactly those values; get_args gives them.
    if get_origin(kind) is Literal:
        values = list(get_args(kind))
        if len(values) == 1:
            return [{"const": values[0], "type": "string"}]
        return [{"enum": values, "type": "string"}]
    # Fail closed: a contract's own rules refuse any other type before it reaches here.
    raise ValueError(f"{kind} is no type a contract's field takes, so it can't be described")
