"""A contract's model as JSON Schema, written by Ventoux, never by pydantic (brief, D83).

A contract's hash covers its models' JSON Schema. pydantic's own rendering changes between minor
versions (2.14 dropped a decimal's `pattern`), so Ventoux writes it itself, as pydantic 2.13 did,
for exactly the field shapes a contract may have. Anything else is refused, never written some
other way (fail closed). See docs/layers/fix-contract-rendering.md.
"""

import inspect
from datetime import date
from decimal import Decimal
from types import NoneType, UnionType
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, RootModel
from pydantic.fields import FieldInfo

from ventoux.core.output_sources import OutputSource
from ventoux.core.policy import Policy
from ventoux.core.references import Reference

# What a contract's field may be, as its refusals say it.
A_FIELD = (
    "a contract's field is its type, its marks (a policy, a reference, a source) and, if it is "
    "optional, `= None`"
)


class Unwritable(ValueError):
    """A model holding something its contract's promise can't be written with: what, then what
    to do, with no full stop, so the contract can add its reference and reason."""


def contract_schema(model: type[BaseModel]) -> dict[str, object]:
    """`model` as JSON Schema, as pydantic 2.13 wrote it. `Unwritable` if it holds anything a
    contract's field may not."""
    refuse_what_it_isnt(model)
    if model.model_config:
        raise Unwritable(
            f"{model.__name__} sets model_config: a contract's model sets none. Remove it"
        )
    for name, field in model.model_fields.items():
        refuse_extras(model, name, field)
    fields = model.model_fields
    schema: dict[str, object] = {
        "properties": {name: field_schema(model, name, field) for name, field in fields.items()},
        "title": model.__name__,
        "type": "object",
    }
    required = [name for name, field in fields.items() if field.is_required()]
    if required:  # left out when nothing is, as pydantic 2.13 did
        schema["required"] = required
    # The class's own docstring, never a parent's: Python gives each class its own `__doc__`.
    if model.__doc__:
        schema["description"] = inspect.cleandoc(model.__doc__)
    return schema


# Pydantic's hooks by which a class writes its own schema: Ventoux writes a contract's, so none.
HOOKS = ("__get_pydantic_json_schema__", "__get_pydantic_core_schema__")


def refuse_what_it_isnt(model: type[BaseModel]) -> None:
    """Refuse a model whose schema, as Ventoux writes it, would say what it isn't: a `RootModel`
    (its value is its root alone, never an object holding it), or one that writes its own schema,
    itself or through a base other than `BaseModel` (the hook wouldn't reach the hash) (tutor's
    review of #98)."""
    if issubclass(model, RootModel):
        raise Unwritable(
            f"{model.__name__} is a RootModel, whose value is its root alone, never an object "
            "holding it: a contract's model is a BaseModel with named fields. Make it one"
        )
    for base in model.__mro__:
        if base in (BaseModel, object):
            continue  # pydantic's own: what Ventoux writes stands for them
        for hook in HOOKS:
            if hook in vars(base):  # defined on that class itself, never only inherited
                raise Unwritable(
                    f"{model.__name__} defines {hook} (in {base.__name__}): a contract's model "
                    "writes no schema of its own; Ventoux writes it. Remove it"
                )


# A decimal is a number, or a text shaped like one, as pydantic 2.13 wrote it. Read left to right:
#   (?!^[-+.]*$)   not only signs and dots
#   [+-]?          an optional sign
#   0*\d*          digits (leading zeros allowed)
#   \.?\d*         an optional dot, then digits
DECIMAL = [
    {"type": "number"},
    {"pattern": r"^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$", "type": "string"},
]


def field_schema(model: type[BaseModel], name: str, field: FieldInfo) -> dict[str, object]:
    """One field: its type, possibly optional, `default: null` if it has `= None`, its title,
    and its marks."""
    annotation = field.annotation
    # typing: `str | None` is a union; its other member is the type.
    optional = get_origin(annotation) in (Union, UnionType) and NoneType in get_args(annotation)
    if optional:
        members = [member for member in get_args(annotation) if member is not NoneType]
        if len(members) != 1:
            raise Unwritable(f"{name} ({model.__name__}) is {annotation}: {A_FIELD}")
        annotation = members[0]
    schema = type_schema(model, name, annotation)
    if optional:  # one list of choices, a decimal's two forms included, then null
        choices = schema.pop("anyOf", None) or [dict(schema)]
        schema = {"anyOf": [*choices, {"type": "null"}]}
    if not field.is_required():
        schema["default"] = None  # the only default a contract's field may have
    schema["title"] = title(name)
    for mark in field.metadata:  # in the order written; refuse_extras let only marks through
        if isinstance(mark, Policy):
            policies = schema.setdefault("x-input-policies", [])
            assert isinstance(policies, list)
            policies.append(mark.promise())
        elif isinstance(mark, Reference):
            schema["x-reference"] = mark.system
        elif isinstance(mark, OutputSource):
            schema["x-source"] = mark.source
    return schema


def type_schema(model: type[BaseModel], name: str, annotation: Any) -> dict[str, Any]:
    """A field's type, as pydantic 2.13 wrote it: a text, true or false, a decimal, a day, or one
    of some texts. `Unwritable` for any other type (fail closed)."""
    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is Decimal:
        return {"anyOf": [dict(choice) for choice in DECIMAL]}
    if annotation is date:
        return {"format": "date", "type": "string"}
    # typing: `Literal["low", "high"]` takes exactly those values; get_args gives them.
    texts = get_args(annotation)
    if get_origin(annotation) is Literal and all(isinstance(text, str) for text in texts):
        if len(texts) == 1:
            return {"const": texts[0], "type": "string"}
        return {"enum": list(texts), "type": "string"}
    raise Unwritable(f"{name} ({model.__name__}) is {annotation}: {A_FIELD}")


def title(name: str) -> str:
    """A field's title, as pydantic derives it from its name: `address_2nd` gives `Address 2Nd`."""
    return name.title().replace("_", " ").strip()


# What pydantic would write into a field's schema, or use to name it, beside its type: never in a
# contract, so never frozen into a hash. Each attribute of pydantic's `FieldInfo`, as said.
EXTRAS = {
    "default_factory": "a default_factory",
    "alias": "an alias",
    "validation_alias": "an alias",
    "serialization_alias": "an alias",
    "title": "a title",
    "field_title_generator": "a title",
    "description": "a description",
    "examples": "examples",
    "json_schema_extra": "json_schema_extra",
    "deprecated": "a deprecation",
    "discriminator": "a discriminator",
}

# What a contract's field may set, each read and checked here: its type, its default (`None`
# only, below) and its marks. Anything else set is refused.
MAY_SET = ("annotation", "default", "metadata")

# The marks a contract's field may carry, each written by Ventoux: a policy (brief, D21), a
# reference (brief, D30) and an output's source (brief, D29).
MARKS = (Policy, Reference, OutputSource)


def refuse_extras(model: type[BaseModel], name: str, field: FieldInfo) -> None:
    """Refuse what pydantic would write into the schema and a contract's field never holds."""
    where = f"{name} ({model.__name__})"
    for attribute, said in EXTRAS.items():
        if getattr(field, attribute) is not None:
            raise Unwritable(f"{where} has {said}: {A_FIELD}. Remove it")
    # Fail closed: what a field may set is listed, never what it may not, so a setting a later
    # pydantic adds is refused too. A blank `FieldInfo` holds pydantic's defaults; its private
    # attributes (`_…`) are its own bookkeeping (the tutor's review of #98).
    blank = FieldInfo()
    for attribute in FieldInfo.__slots__:
        if attribute.startswith("_") or attribute in MAY_SET:
            continue
        if getattr(field, attribute) != getattr(blank, attribute):
            raise Unwritable(f"{where} sets {attribute}: {A_FIELD}. Remove it")
    # Pydantic: a field with no default holds `PydanticUndefined` (`is_required()` says so).
    if not field.is_required() and field.default is not None:
        raise Unwritable(f"{where} has a default other than None: {A_FIELD}. Remove it")
    # A constraint (`Field(gt=0)`) or any other `Annotated` extra lands in `metadata`, beside marks.
    if any(not isinstance(mark, MARKS) for mark in field.metadata):
        raise Unwritable(
            f"{where} has a constraint or mark Ventoux doesn't know: {A_FIELD}. Remove it"
        )
