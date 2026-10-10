"""Output sources: where each value an activity or a workflow gives comes from (brief, D29).

A source is written on the output field it describes, in the contract's output model, as an input
policy is written on an input field. See docs/guides/activities.md.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, GetJsonSchemaHandler
from pydantic_core import CoreSchema

from ventoux.core.provenance import is_label

# The two origins an output may declare: a system the platform team vouches for, or a registered
# label for untrusted content. Never `person:` (an activity is never a person's answer) and never
# `trusted:` (trust is what a source earns, not a source) (brief, D12).
ORIGINS = ("system:", "untrusted:")
# An output field with no declared source: untrusted, so forgetting a source can only make a value
# less trusted, never more (brief, D6). `undeclared` is the engine's label, never registered.
UNDECLARED_LABEL = "undeclared"
UNDECLARED = f"untrusted:{UNDECLARED_LABEL}"
# What an output field may hold: what the case file holds exactly and expressions read (brief, D20).
# Numbers are exact decimals, never binary floats; a reference is a text. A nested model would put a
# Python object in the case file, not data, so it is refused too (tutor review of layer 8d).
HELD = (Decimal, str, bool)
HELD_NAMES = "a decimal (Decimal), a text (str) or true or false (bool)"


@dataclass(frozen=True)
class OutputSource:
    """Where the value of one output field comes from: `system:kyc` or `untrusted:llm`."""

    source: str  # the source every value of this field is tagged with in the case file

    # Pydantic: on an object inside `Annotated[...]`, `__get_pydantic_json_schema__` is called when
    # the model's JSON Schema is made, and may add to the field's schema.
    def __get_pydantic_json_schema__(
        self, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> dict[str, Any]:
        # The source goes into the published schema, which the contract hash covers: declaring or
        # changing one changes the contract. A field with none adds nothing (brief, D29).
        schema: dict[str, Any] = handler(core_schema)
        schema["x-source"] = self.source
        return schema


def source(text: str) -> OutputSource:
    """The source of an output field: `Annotated[str, source("system:kyc")]`."""
    return OutputSource(text)


def is_output_source(text: str) -> bool:
    """Whether `text` is a source an output may declare: `system:kyc` and `untrusted:llm` are,
    `person:ana`, `trusted:kyc` and `system:` aren't."""
    origin, _, name = text.partition(":")
    return f"{origin}:" in ORIGINS and is_label(name)


def declared_sources(output: type[BaseModel]) -> dict[str, str]:
    """The sources the contract writes, by output field; a field with none isn't listed."""
    return {
        name: declared.source
        for name, field in output.model_fields.items()
        for declared in field.metadata
        if isinstance(declared, OutputSource)
    }


def output_sources(output: type[BaseModel]) -> dict[str, str]:
    """Each output field's source: the one declared, or `untrusted:undeclared` (brief, D6)."""
    declared = declared_sources(output)
    return {name: declared.get(name, UNDECLARED) for name in output.model_fields}


def is_held(value: object) -> bool:
    """Whether the case file can hold `value` exactly: `Decimal("0.1")`, `"ord-1"`, `True` are,
    `0.1` and `3` aren't. By its exact type: a `bool` is an `int` to Python, an `int` is not held."""
    return type(value) in HELD
