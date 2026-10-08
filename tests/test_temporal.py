"""The Temporal adapter: plans run as workflows, against Temporal's test server (layer 6).

See docs/layers/06-temporal.md and docs/guides/plans.md, "Running a plan on Temporal".
"""

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from ventoux.temporal.converter import DATA_CONVERTER


def round_trip(value: Any) -> Any:
    """`value` written as Temporal writes a payload, and read back."""

    async def both_ways() -> Any:
        payloads = await DATA_CONVERTER.encode([value])
        return (await DATA_CONVERTER.decode(payloads, [Any]))[0]

    return asyncio.run(both_ways())


def test_a_float_is_refused() -> None:
    # A binary float may already have lost its exact value: 0.1 is 0.1000000000000000055…
    with pytest.raises(TypeError, match="0.1 is a binary float"):
        round_trip({"amount": 0.1})


def test_a_decimal_comes_back_exactly() -> None:
    back = round_trip({"amount": Decimal("0.1"), "count": 3})
    assert back == {"amount": Decimal("0.1"), "count": 3}
    assert isinstance(back["amount"], Decimal)  # never the text "0.1", never a float
