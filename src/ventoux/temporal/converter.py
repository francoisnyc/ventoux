"""How values cross Temporal: JSON whose numbers stay exact decimals (brief, D20).

Temporal's default converter can't write a `Decimal` at all, and Pydantic's writes it as the text
`"0.1"`, which comes back a string: `amount > 100` would then compare a text with a number. This
one writes a `Decimal` as a JSON number and reads every number with a fraction back as a `Decimal`,
as `load_definition` reads a definition.
"""

import dataclasses
import json
from decimal import Decimal
from typing import Any

from temporalio.api.common.v1 import Payload
from temporalio.converter import (
    CompositePayloadConverter,
    DataConverter,
    DefaultPayloadConverter,
    EncodingPayloadConverter,
    JSONPlainPayloadConverter,
)


def exact_json(value: Any) -> str:
    """`value` as JSON text, every number written exactly; anything else is refused."""
    if isinstance(value, float):
        # Fail closed: a binary float may already have lost its exact value, so it never enters.
        raise TypeError(
            f"{value!r} is a binary float, which may not hold the exact value: give numbers as "
            "Decimal (brief, D20)"
        )
    if value is None or isinstance(value, (bool, int, str)):
        return json.dumps(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError(f"{value} is not a number JSON can hold: give a finite Decimal")
        return str(value)  # a JSON number, digit for digit: `0.1`, `1E+2`
    if isinstance(value, dict):
        return (
            "{"
            + ", ".join(f"{json.dumps(key)}: {exact_json(item)}" for key, item in value.items())
            + "}"
        )
    raise TypeError(f"{type(value).__name__} can't be written exactly as JSON")


class ExactJSON(EncodingPayloadConverter):
    """Temporal's plain JSON encoding, written and read with exact numbers."""

    @property
    def encoding(self) -> str:
        return "json/plain"  # the name Temporal's own JSON converter uses, so the UI reads it

    def to_payload(self, value: Any) -> Payload | None:
        return Payload(
            metadata={"encoding": self.encoding.encode()}, data=exact_json(value).encode()
        )

    def from_payload(self, payload: Payload, type_hint: type | None = None) -> Any:
        # Numbers with a fraction or an exponent come back as `Decimal`, never as `float`.
        return json.loads(payload.data, parse_float=Decimal)


class ExactPayloadConverter(CompositePayloadConverter):
    """Temporal's default converters, with exact JSON in place of its plain JSON."""

    def __init__(self) -> None:
        super().__init__(
            *(
                converter
                for converter in DefaultPayloadConverter.default_encoding_payload_converters
                if not isinstance(converter, JSONPlainPayloadConverter)
            ),
            ExactJSON(),
        )


# Temporal: a data converter turns values into payloads and back; client and worker must use the
# same one.
DATA_CONVERTER = dataclasses.replace(
    DataConverter.default, payload_converter_class=ExactPayloadConverter
)
