"""Layer 9b on Temporal: keys, the codec, and no sensitive value in plain text anywhere.

See docs/layers/09-case-data.md (9b) and docs/guides/case-data.md ("On Temporal").
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from temporalio.api.common.v1 import Payload
from temporalio.api.failure.v1 import Failure
from temporalio.converter import (
    ActivitySerializationContext,
    DataConverter,
    WorkflowSerializationContext,
)
from temporalio.exceptions import ApplicationError

from ventoux.core.sensitive import Sensitive
from ventoux.temporal.converter import ExactPayloadConverter, data_converter
from ventoux.tooling.keys import FileKeys, KeyRefused

NATIONAL_ID = "1 85 05 78 006 084 36"


def test_a_key_is_made_once(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    # Never made again, even by another provider on the same file: a reused ID never inherits
    # or remakes a case's key (brief, D31).
    with pytest.raises(KeyRefused, match="^a key was already made for claim-7: open the case"):
        FileKeys(tmp_path / "keys.json").create("claim-7")
    # A case without one has nothing to seal or open with: fail closed, never plain text.
    no_key = "^there is no key for claim-8, so its sensitive values can't be read or written$"
    with pytest.raises(KeyRefused, match=no_key):
        keys.seal("claim-8", NATIONAL_ID.encode(), "sensitive/0")
    with pytest.raises(KeyRefused, match=no_key):
        keys.open("claim-8", b"anything", "sensitive/0")


def test_a_part_opens_only_where_it_was_sealed(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    keys.create("claim-8")
    sealed = keys.seal("claim-7", NATIONAL_ID.encode(), "sensitive/0")
    assert NATIONAL_ID.encode() not in sealed
    assert keys.open("claim-7", sealed, "sensitive/0") == NATIONAL_ID.encode()
    # The key never leaves the provider: it seals and opens, and nothing else reads it.
    assert not any(
        name.startswith(("key", "get")) for name in dir(keys) if not name.startswith("_")
    )
    damaged = sealed[:-1] + bytes([sealed[-1] ^ 1])
    for case, data, part in [
        ("claim-8", sealed, "sensitive/0"),  # another case
        ("claim-7", sealed, "sensitive/1"),  # another place in the payload
        ("claim-7", damaged, "sensitive/0"),
    ]:
        with pytest.raises(KeyRefused, match=f"^a sealed part of {case} doesn't open"):
            keys.open(case, data, part)


def converter(keys: FileKeys, workflow_id: str | None) -> DataConverter:
    """Ventoux's data converter as Temporal hands it a payload of `workflow_id`'s: a case, or a
    child `<case ID>/<entry>`. None: Temporal gave no workflow ID."""
    plain = data_converter(keys)
    if workflow_id is None:
        return plain
    return plain.with_context(WorkflowSerializationContext("default", workflow_id))


def test_a_sensitive_value_crosses_encrypted(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    value = {"national_id": Sensitive(NATIONAL_ID), "amount": Decimal("1200.50")}

    async def go() -> None:
        claim_7 = converter(keys, "claim-7")
        [payload] = await claim_7.encode([value])
        # Its own part, encrypted; the rest of the payload stays readable.
        assert NATIONAL_ID.encode() not in payload.SerializeToString()
        assert b'"amount": 1200.50' in payload.data
        assert set(payload.metadata) == {"encoding", "encrypted/0"}
        assert (await claim_7.decode([payload], [Any]))[0] == value

    asyncio.run(go())


def test_a_child_uses_its_cases_key(tmp_path: Path) -> None:
    # Temporal gives a child workflow's payloads the child's ID: `claim-7/collect#1`.
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    value = [Sensitive(NATIONAL_ID)]

    async def go() -> None:
        [payload] = await converter(keys, "claim-7/collect#1").encode([value])
        assert (await converter(keys, "claim-7").decode([payload], [Any]))[0] == value
        activity = ActivitySerializationContext(
            "default", "1", "orders.lookup@1", "q", "claim-7/collect#1", "ventoux.plan", False
        )
        in_activity = data_converter(keys).with_context(activity)
        assert (await in_activity.decode([payload], [Any]))[0] == value

    asyncio.run(go())


def test_the_codec_fails_closed(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    value = [Sensitive(NATIONAL_ID)]

    async def go() -> None:
        with pytest.raises(KeyRefused, match="^there is no key for claim-9"):
            await converter(keys, "claim-9").encode([value])
        with pytest.raises(KeyRefused, match="^a sensitive part has no case"):
            await converter(keys, None).encode([value])
        [payload] = await converter(keys, "claim-7").encode([value])
        with pytest.raises(KeyRefused, match="^a sensitive part has no case"):
            await converter(keys, None).decode([payload], [Any])
        damaged = Payload()
        damaged.CopyFrom(payload)
        sealed = damaged.metadata["encrypted/0"]
        damaged.metadata["encrypted/0"] = sealed[:-1] + bytes([sealed[-1] ^ 1])
        with pytest.raises(KeyRefused, match="^a sealed part of claim-7 doesn't open"):
            await converter(keys, "claim-7").decode([damaged], [Any])
        # A converter given a payload the codec never decoded refuses it, never guesses.
        with pytest.raises(ValueError, match="^a sensitive part arrived encrypted"):
            ExactPayloadConverter().from_payloads([payload])
        # Its own marker can't be forged by data: a dict with that key is refused.
        with pytest.raises(TypeError, match="‹sensitive›"):
            await converter(keys, "claim-7").encode([{"‹sensitive›": 0}])

    asyncio.run(go())


def test_a_payload_without_parts_needs_no_key(tmp_path: Path) -> None:
    # A case without a sensitive value, and every history written before 9b, needs no key.
    keys = FileKeys(tmp_path / "keys.json")
    value = {"amount": Decimal(250), "order_id": "ord-1"}

    async def go() -> None:
        [payload] = await converter(keys, "refund-1").encode([value])
        assert payload == ExactPayloadConverter().to_payloads([value])[0]
        assert (await converter(keys, "refund-1").decode([payload], [Any]))[0] == value

    asyncio.run(go())


def test_a_failure_crosses_encrypted(tmp_path: Path) -> None:
    # Temporal keeps a failure's message and stack trace outside payloads: both are sealed, at
    # every level of its causes, whoever raised it.
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")

    async def go() -> None:
        claim_7 = converter(keys, "claim-7")
        try:
            try:
                raise LookupError(f"no customer {NATIONAL_ID}")
            except LookupError as cause:
                raise RuntimeError(f"lookup of {NATIONAL_ID} failed") from cause
        except RuntimeError as error:
            failure = Failure()
            await claim_7.encode_failure(error, failure)
        assert NATIONAL_ID.encode() not in failure.SerializeToString()
        assert failure.message == failure.cause.message == "Encoded failure"
        back = await claim_7.decode_failure(failure)
        # Read back where the key is, as it was raised.
        assert isinstance(back, ApplicationError)
        assert back.message == f"lookup of {NATIONAL_ID} failed"
        assert isinstance(back.cause, ApplicationError)
        assert back.cause.message == f"no customer {NATIONAL_ID}"

    asyncio.run(go())
