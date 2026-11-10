"""A contract's models, written as JSON Schema by Ventoux, never by pydantic (brief, D83).

See docs/layers/fix-contract-rendering.md.
"""

from decimal import Decimal
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts


class LookupInput(BaseModel):
    order_id: str


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


class Defaulted(BaseModel):
    order_id: str = "ord-1"


class Made(BaseModel):
    order_id: str = Field(default_factory=lambda: "ord-1")


class Aliased(BaseModel):
    order_id: Annotated[str, Field(alias="id")]


class Titled(BaseModel):
    order_id: Annotated[str, Field(title="Order")]


class WithExamples(BaseModel):
    order_id: Annotated[str, Field(examples=["ord-1"])]


class Extra(BaseModel):
    order_id: Annotated[str, Field(json_schema_extra={"x-mine": 1})]


class Constrained(BaseModel):
    amount: Annotated[Decimal, Field(gt=0)]


class Noted(BaseModel):
    order_id: Annotated[str, "a note"]


class Configured(BaseModel):
    model_config = ConfigDict(title="Lookup")

    order_id: str


@pytest.mark.parametrize(
    ("model", "said"),
    [
        (Defaulted, "input order_id (Defaulted) has a default other than None"),
        (Made, "input order_id (Made) has a default_factory"),
        (Aliased, "input order_id (Aliased) has an alias"),
        (Titled, "input order_id (Titled) has a title"),
        (WithExamples, "input order_id (WithExamples) has examples"),
        (Extra, "input order_id (Extra) has json_schema_extra"),
        (Constrained, "input amount (Constrained) has a constraint or mark Ventoux doesn't know"),
        (Noted, "input order_id (Noted) has a constraint or mark Ventoux doesn't know"),
        (Configured, "input Configured sets model_config"),
    ],
)
def test_anything_else_pydantic_would_write_is_refused(model: type[BaseModel], said: str) -> None:
    with pytest.raises(ValidationError) as refused:
        lookup_with(model)
    assert f"orders.lookup@1: {said}" in str(refused.value)


def test_an_output_is_refused_the_same_way() -> None:
    class Described(BaseModel):
        status: Annotated[str, Field(description="the order's status")]

    with pytest.raises(ValidationError, match=r"output status \(Described\) has a description"):
        lookup_with(LookupInput, Described)
