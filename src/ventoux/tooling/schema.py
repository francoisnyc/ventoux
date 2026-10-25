"""The JSON Schema of a case and of a plan, generated from the models the engine parses with
(layer 14e) (brief, D60). Shape only: `ventoux check` stays the check.

The models say almost all of it themselves (`extra="forbid"`, the name patterns, the operators).
Two things a model holds in another shape than the JSON, and marks with `x-written`: a field's
type, gathered under `declared` by a validator, is written flat beside `display`; a plan field's
`source`, moved into `sources` by a validator, is written on the field. `Published` renders those
marks as the JSON is written, from the type models' own schemas, never typed by hand.
"""

from copy import deepcopy
from typing import Any

from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode, JsonSchemaValue
from pydantic_core import core_schema

from ventoux.case.definition import CaseDefinition
from ventoux.core.plan import Plan

Defs = dict[str, JsonSchemaValue]


class Published(GenerateJsonSchema):
    """Pydantic's schema generator, with the format's own rendering of three things.

    Pydantic: `model_json_schema(schema_generator=...)` takes a subclass like this one; each method
    renders one kind of core schema, and `generate` the whole.
    """

    def dict_schema(self, schema: core_schema.DictSchema) -> JsonSchemaValue:
        """A dict whose keys follow a pattern refuses any other key: Pydantic writes the pattern
        (`patternProperties`) and nothing about other keys, which the parser refuses."""
        written = super().dict_schema(schema)
        if "patternProperties" in written:
            written.setdefault("additionalProperties", False)
        return written

    def generate(
        self, schema: core_schema.CoreSchema, mode: JsonSchemaMode = "validation"
    ) -> JsonSchemaValue:
        written = super().generate(schema, mode)
        defs: Defs = written.get("$defs", {})
        for name, definition in list(defs.items()):
            defs[name] = as_written(definition, defs)
        return as_written(written, defs)


def as_written(definition: JsonSchemaValue, defs: Defs) -> JsonSchemaValue:
    """`definition` rendered as its `x-written` mark says, if it has one."""
    mark = definition.pop("x-written", None)
    if mark is None:
        return definition
    if "source_on" in mark:
        source_written_on_field(definition, mark["source_on"], defs)
    if "flat" in mark:
        return type_written_flat(definition, mark["flat"], defs)
    return definition


def type_written_flat(definition: JsonSchemaValue, under: str, defs: Defs) -> JsonSchemaValue:
    """`definition` with the type it holds `under` written flat: one shape per declared type, each
    the type's own schema plus the other keys, closed. `{"type": "number", "display": {...}}`."""
    declared = definition["properties"].pop(under)
    others = definition["properties"]
    required = [key for key in definition.get("required", ()) if key != under]
    shapes = [
        with_properties(defs, branch["$ref"], others, required) for branch in declared["oneOf"]
    ]
    return {
        "title": definition["title"],
        "description": definition["description"],
        "oneOf": shapes,
    }


def source_written_on_field(definition: JsonSchemaValue, fields: str, defs: Defs) -> None:
    """`definition`'s `sources` written on each of its `fields` instead, as the parser reads
    them: `{"type": "string", "source": "untrusted:customer"}`."""
    sources = definition["properties"].pop("sources")
    declared = definition["properties"][fields]["additionalProperties"]
    source = {"source": sources["additionalProperties"]}
    definition["properties"][fields]["additionalProperties"] = {
        "oneOf": [with_properties(defs, branch["$ref"], source, []) for branch in declared["oneOf"]]
    }


def with_properties(
    defs: Defs, reference: str, properties: JsonSchemaValue, required: list[str]
) -> JsonSchemaValue:
    """The schema `reference` points at (`#/$defs/NumberType`), with `properties` added beside its
    own, still closed to any other key."""
    shape = deepcopy(defs[reference.rpartition("/")[2]])
    shape["properties"] = {**shape["properties"], **properties}
    shape["required"] = sorted({*shape.get("required", ()), *required})
    return shape


def case_schema() -> dict[str, Any]:
    """The schema of `case.json`, from `CaseDefinition`, the model `parse_case` validates with."""
    return CaseDefinition.model_json_schema(schema_generator=Published)


def plan_schema() -> dict[str, Any]:
    """The schema of a plan file, from `Plan`, the model `parse_plan` validates with."""
    return Plan.model_json_schema(schema_generator=Published)
