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

from temporalio import workflow
from temporalio.api.common.v1 import Payload
from temporalio.client import Client
from temporalio.converter import (
    CompositePayloadConverter,
    DataConverter,
    DefaultPayloadConverter,
    EncodingPayloadConverter,
    JSONPlainPayloadConverter,
    value_to_type,
)

# Temporal: the workflow sandbox imports a payload converter's module afresh, inside it. What it
# imports from Ventoux is passed through, imported once and shared, so a `Sensitive` it reads back
# is the very class `case` and `core` check for, and `cryptography` (compiled code, which can't be
# imported twice) is never imported again.
with workflow.unsafe.imports_passed_through():
    from ventoux.core.sensitive import PLACEHOLDER, Sensitive
    from ventoux.temporal.codec import ENCRYPTED, SENSITIVE, SensitiveCodec, SensitiveFailures
    from ventoux.tooling.keys import KeyProvider

# Where a sensitive value stood in the JSON: `{"‹sensitive›": 0}`, the number of its part.
MARK = PLACEHOLDER


def exact_json(value: Any, parts: list[str]) -> str:
    """`value` as JSON text, every number written exactly; anything else is refused. Each
    sensitive value is written as `{"‹sensitive›": n}`, and its own JSON added to `parts` as the
    `n`th: it crosses in its own part of the payload, which the codec encrypts (brief, D31)."""
    if isinstance(value, Sensitive):
        parts.append(exact_json(value.value, parts))
        return json.dumps({MARK: len(parts) - 1})
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
        return decimal_number(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # A dataclass, such as a run's start or report, is written as an object of its fields.
        fields = {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
        return exact_json(fields, parts)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(exact_json(item, parts) for item in value) + "]"
    if isinstance(value, dict):
        # JSON keys are texts: a key 1 would come back as "1", a different key.
        if not all(isinstance(key, str) for key in value):
            raise TypeError(f"{sorted(map(repr, value))}: a key must be a text to cross as JSON")
        # The marker is Ventoux's: data written with it would read back as a sensitive value.
        if MARK in value:
            raise TypeError(f"{MARK} is the converter's own key: no data may use it")
        return (
            "{"
            + ", ".join(
                f"{json.dumps(key)}: {exact_json(item, parts)}" for key, item in value.items()
            )
            + "}"
        )
    raise TypeError(f"{type(value).__name__} can't be written exactly as JSON")


def decimal_number(value: Decimal) -> str:
    """`value` as a JSON number, digit for digit, that reads back as a `Decimal`: `0.1`, `1E+2`.

    JSON reads `250` as an int, and an expression refuses an int (a number in `core` is a Decimal),
    so a whole Decimal is written with an exponent, `250E0`, which reads back as `Decimal("250")`.
    An int stays an int, so a run decides on Temporal exactly as it does in memory.
    """
    written = str(value)
    is_whole = not any(mark in written for mark in ".Ee")
    return written + "E0" if is_whole else written


class ExactJSON(EncodingPayloadConverter):
    """Temporal's plain JSON encoding, written and read with exact numbers."""

    @property
    def encoding(self) -> str:
        return "json/plain"  # the name Temporal's own JSON converter uses, so the UI reads it

    def to_payload(self, value: Any) -> Payload | None:
        parts: list[str] = []
        data = exact_json(value, parts)
        metadata = {"encoding": self.encoding.encode()}
        # Temporal: a payload's metadata is a map of texts to bytes, kept with it in history.
        metadata |= {f"{SENSITIVE}{n}": part.encode() for n, part in enumerate(parts)}
        return Payload(metadata=metadata, data=data.encode())

    def from_payload(self, payload: Payload, type_hint: type | None = None) -> Any:
        if any(name.startswith(ENCRYPTED) for name in payload.metadata):
            # Fail closed: the codec never opened it, so there is no value to read.
            raise ValueError(
                "a sensitive part arrived encrypted: connect with data_converter(keys) from "
                "ventoux.temporal.converter, whose codec opens it"
            )
        # Numbers with a fraction or an exponent come back as `Decimal`, never as `float`.
        parts = [
            json.loads(payload.metadata[f"{SENSITIVE}{n}"], parse_float=Decimal)
            for n in range(sum(name.startswith(SENSITIVE) for name in payload.metadata))
        ]

        def rewrapped(found: dict[str, Any]) -> Any:
            """Each `{"‹sensitive›": n}` read back as the `n`th part, wrapped again."""
            return Sensitive(parts[found[MARK]]) if set(found) == {MARK} else found

        # Python: `object_hook` is called on every JSON object read, innermost first.
        value = json.loads(payload.data, parse_float=Decimal, object_hook=rewrapped)
        # Temporal: `value_to_type` builds the type the receiver asked for (a dataclass, say).
        return value if type_hint is None else value_to_type(type_hint, value)


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


def data_converter(keys: KeyProvider) -> DataConverter:
    """Ventoux's data converter: exact numbers (brief, D20), and each sensitive value sealed with
    its case's key by `keys`, failures included (brief, D31). Client and worker use the same."""
    # Temporal: a data converter turns values into payloads and back; its codec then works on the
    # payloads' bytes, outside workflow code.
    return dataclasses.replace(
        DataConverter.default,
        payload_converter_class=ExactPayloadConverter,
        payload_codec=SensitiveCodec(keys),
        failure_converter_class=SensitiveFailures,
    )


def registry_converter() -> DataConverter:
    """Exact numbers, and no key: for a client that reads and writes no case's values, such as
    the `ventoux` command talking to a registry, none of whose payloads is sensitive."""
    return dataclasses.replace(DataConverter.default, payload_converter_class=ExactPayloadConverter)


def require_ventoux_converter(client: Client) -> None:
    """Refuse a client that would write numbers some other way (brief, D20), or sensitive values
    in plain text (brief, D31)."""
    converter = client.data_converter
    # Fail closed: with another converter an amount could cross as the text "250", and a
    # contract's schema would read it back as a number: nothing would say it had changed hands.
    if converter.payload_converter_class is not ExactPayloadConverter:
        raise ValueError(
            "this client doesn't keep exact numbers: connect it with `data_converter(keys)` from "
            "ventoux.temporal.converter"
        )
    if not isinstance(converter.payload_codec, SensitiveCodec) or (
        converter.failure_converter_class is not SensitiveFailures
    ):
        raise ValueError(
            "this client doesn't encrypt sensitive values: connect it with data_converter(keys) "
            "from ventoux.temporal.converter"
        )


def keys_of(client: Client) -> KeyProvider:
    """The key provider `client`'s converter seals with, once checked."""
    require_ventoux_converter(client)
    codec = client.data_converter.payload_codec
    assert isinstance(codec, SensitiveCodec)  # checked just above
    return codec.keys
