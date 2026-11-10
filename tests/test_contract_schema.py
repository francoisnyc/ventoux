"""A contract's models, written as JSON Schema by Ventoux, never by pydantic (brief, D83).

See docs/layers/fix-contract-rendering.md.
"""

from typing import Annotated, Any

import pytest
from pydantic import BaseModel, Field, ValidationError

from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts


class LookupOutput(BaseModel):
    status: str


def lookup_with(input: type[BaseModel], output: type[BaseModel] = LookupOutput) -> ActivityContract:
    """`orders.lookup@1`, a read-only contract, with `input` and `output` as its models."""
    fields: dict[str, Any] = {
        "name": "orders.lookup",
        "version": 1,
        "input": input,
        "output": output,
        "risk": "low",
        "effect": "read",
        "timeouts": Timeouts(start_to_close=10, schedule_to_start=60),
        "retry": RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
        "idempotency_key": None,
        "outcomes": [],
        "display": Display(title="Look up an order", description="Reads an order's status."),
    }
    return ActivityContract(**fields)


def test_a_field_with_a_description_is_refused_when_the_contract_is_made() -> None:
    class Described(BaseModel):
        order_id: Annotated[str, Field(description="the order's ID")]

    with pytest.raises(ValidationError) as refused:
        lookup_with(Described)
    said = str(refused.value)
    assert "orders.lookup@1: input order_id (Described) has a description" in said
    assert "a contract's field is its type, its marks" in said
