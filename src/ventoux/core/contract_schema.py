"""A contract's model as JSON Schema, written by Ventoux, never by pydantic (brief, D83).

A contract's hash covers its models' JSON Schema. pydantic's own rendering changes between minor
versions (2.14 dropped a decimal's `pattern`), so Ventoux writes it itself, as pydantic 2.13 did,
for exactly the field shapes a contract may have. Anything else is refused, never written some
other way (fail closed). See docs/layers/fix-contract-rendering.md.
"""

from pydantic import BaseModel
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
    """A model holding something its contract's promise can't be written with."""


def contract_schema(model: type[BaseModel]) -> dict[str, object]:
    """`model` as JSON Schema, as pydantic 2.13 wrote it. `Unwritable` if it holds anything a
    contract's field may not."""
    if model.model_config:
        raise Unwritable(f"{model.__name__} sets model_config: a contract's model sets none.")
    for name, field in model.model_fields.items():
        refuse_extras(model, name, field)
    return model.model_json_schema()


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

# The marks a contract's field may carry, each written by Ventoux: a policy (brief, D21), a
# reference (brief, D30) and an output's source (brief, D29).
MARKS = (Policy, Reference, OutputSource)


def refuse_extras(model: type[BaseModel], name: str, field: FieldInfo) -> None:
    """Refuse what pydantic would write into the schema and a contract's field never holds."""
    where = f"{name} ({model.__name__})"
    for attribute, said in EXTRAS.items():
        if getattr(field, attribute) is not None:
            raise Unwritable(f"{where} has {said}: {A_FIELD}. Remove it.")
    # Pydantic: a field with no default holds `PydanticUndefined` (`is_required()` says so).
    if not field.is_required() and field.default is not None:
        raise Unwritable(f"{where} has a default other than None: {A_FIELD}. Remove it.")
    # A constraint (`Field(gt=0)`) or any other `Annotated` extra lands in `metadata`, beside marks.
    if any(not isinstance(mark, MARKS) for mark in field.metadata):
        raise Unwritable(
            f"{where} has a constraint or mark Ventoux doesn't know: {A_FIELD}. Remove it."
        )
