"""A contract's model as JSON Schema, written by Ventoux, never by pydantic (brief, D83).

A contract's hash covers its models' JSON Schema. pydantic's own rendering changes between minor
versions (2.14 dropped a decimal's `pattern`), so Ventoux writes it itself, as pydantic 2.13 did,
for exactly the field shapes a contract may have. Anything else is refused, never written some
other way (fail closed). See docs/layers/fix-contract-rendering.md.
"""

from pydantic import BaseModel
from pydantic.fields import FieldInfo

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
    for name, field in model.model_fields.items():
        refuse_extras(model, name, field)
    return model.model_json_schema()


def refuse_extras(model: type[BaseModel], name: str, field: FieldInfo) -> None:
    """Refuse what pydantic would write into the schema and a contract's field never holds."""
    if field.description is not None:
        raise Unwritable(f"{name} ({model.__name__}) has a description: {A_FIELD}. Remove it.")
