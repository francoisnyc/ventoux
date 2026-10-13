"""Reference inputs: an input that takes the ID of a record in one system (brief, D30).

Written on the input field it describes, in the contract's input model, as an input policy is.
See docs/guides/activities.md.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, GetJsonSchemaHandler
from pydantic_core import CoreSchema

from ventoux.core.expressions import FieldType, ListType, ReferenceType


@dataclass(frozen=True)
class Reference:
    """An input takes a reference to a record in `system`: `Annotated[str, reference("crm")]`."""

    system: str  # the registered system whose records it names, such as `crm`

    # Pydantic: on an object inside `Annotated[...]`, `__get_pydantic_json_schema__` is called when
    # the model's JSON Schema is made, and may add to the field's schema.
    def __get_pydantic_json_schema__(
        self, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        # The system goes into the published schema, which the contract hash covers: declaring or
        # changing one changes the contract. A field with none adds nothing (brief, D30).
        schema: dict[str, Any] = handler(core_schema)
        schema["x-reference"] = self.system
        return schema


def reference(system: str) -> Reference:
    """The system an input's reference names: `Annotated[str, reference("crm")]`."""
    return Reference(system)


def marks(model: type[BaseModel], field: str) -> list[Reference]:
    """The references written on `field` of `model`; a well-formed contract has at most one."""
    # Pydantic: `metadata` holds what `Annotated[...]` attached to the field.
    return [m for m in model.model_fields[field].metadata if isinstance(m, Reference)]


def references(model: type[BaseModel]) -> dict[str, str]:
    """The system each input of `model` takes a reference to; an input with none isn't listed."""
    return {name: found[0].system for name in model.model_fields if (found := marks(model, name))}


def unregistered(fields: Mapping[str, FieldType], systems: Collection[str]) -> list[str]:
    """What is wrong with `fields` whose references name a system not in `systems`: a typo is
    caught when a case opens or a plan starts, never a system nobody runs (brief, D30)."""
    problems: list[str] = []
    for name, declared in fields.items():
        if isinstance(declared, ReferenceType) and declared.system not in systems:
            problems.append(
                f"{name} is a reference to {declared.system}, which is not a registered system"
            )
        elif isinstance(declared, ListType):
            # A list's records may hold references too: `documents.document_id`.
            inner = unregistered(declared.fields, systems)
            problems += [f"{name}.{problem}" for problem in inner]
    return problems
