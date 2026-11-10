"""A contract's promise, written by Ventoux, never by pydantic (the contract hash fix) (brief,
D83). See docs/layers/fix-contract-hash.md."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from described_shapes import SHAPES
from pydantic import BaseModel, ConfigDict, Field

from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.described import described


class Plain(BaseModel):
    """What a contract takes or gives when the test doesn't care: one text."""

    order_id: str


def contract(taking: type[BaseModel] = Plain, giving: type[BaseModel] = Plain) -> ActivityContract:
    """`ledger.record@1`, taking `taking` and giving `giving`."""
    return ActivityContract(
        name="ledger.record",
        version=1,
        input=taking,
        output=giving,
        risk="low",
        effect="compute",
        timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
        retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
        idempotency_key=None,
        outcomes=[],
        display=Display(title="Record", description="Record an amount"),
    )


class AtLeastZero(BaseModel):
    amount: Annotated[Decimal, Field(ge=0)]


class Short(BaseModel):
    order_id: Annotated[str, Field(max_length=12)]


class Patterned(BaseModel):
    order_id: Annotated[str, Field(pattern="^o-")]


class Titled(BaseModel):
    order_id: str = Field(title="Order")


class Aliased(BaseModel):
    order_id: str = Field(alias="orderId")


class WithExamples(BaseModel):
    order_id: str = Field(examples=["o-1"])


class Extra(BaseModel):
    order_id: str = Field(json_schema_extra={"x-owner": "payments"})


class DecimalDefault(BaseModel):
    amount: Decimal = Decimal("1.50")


class ModelExtra(BaseModel):
    model_config = ConfigDict(json_schema_extra={"x-owner": "payments"})
    order_id: str


class ModelTitled(BaseModel):
    model_config = ConfigDict(title="Order")
    order_id: str


class OutputAtLeastZero(BaseModel):
    paid: Annotated[Decimal, Field(ge=0)]


NOT_WRITTEN = (
    "which Ventoux doesn't write into the contract's promise, so its hash wouldn't cover it"
)


@pytest.mark.parametrize(
    ("given", "said"),
    [
        (
            {"taking": AtLeastZero},
            (
                f"ledger.record@1: input amount has a constraint (Ge), {NOT_WRITTEN}: remove it, and "
                "check the value where it is used"
            ),
        ),
        (
            {"taking": Short},
            f"ledger.record@1: input order_id has a constraint (MaxLen), {NOT_WRITTEN}",
        ),
        (
            {"taking": Patterned},
            (
                f"ledger.record@1: input order_id has a constraint (_PydanticGeneralMetadata), "
                f"{NOT_WRITTEN}"
            ),
        ),
        ({"taking": Titled}, f"ledger.record@1: input order_id sets its title, {NOT_WRITTEN}"),
        ({"taking": Aliased}, f"ledger.record@1: input order_id sets its alias, {NOT_WRITTEN}"),
        (
            {"taking": WithExamples},
            f"ledger.record@1: input order_id sets its examples, {NOT_WRITTEN}",
        ),
        (
            {"taking": Extra},
            f"ledger.record@1: input order_id sets its json_schema_extra, {NOT_WRITTEN}",
        ),
        (
            {"taking": DecimalDefault},
            (
                "ledger.record@1: input amount defaults to a Decimal: a default is None, true or "
                "false, or a text; give one of those, or none"
            ),
        ),
        (
            {"taking": ModelExtra},
            (
                f"ledger.record@1: input ModelExtra sets json_schema_extra in its model_config, "
                f"{NOT_WRITTEN}"
            ),
        ),
        (
            {"taking": ModelTitled},
            f"ledger.record@1: input ModelTitled sets title in its model_config, {NOT_WRITTEN}",
        ),
        (
            {"giving": OutputAtLeastZero},
            f"ledger.record@1: output paid has a constraint (Ge), {NOT_WRITTEN}",
        ),
    ],
    ids=[
        "ge",
        "max_length",
        "pattern",
        "title",
        "alias",
        "examples",
        "json_schema_extra",
        "a decimal default",
        "a model's json_schema_extra",
        "a model's title",
        "an output's constraint",
    ],
)
def test_what_ventoux_doesnt_describe_is_refused_when_the_contract_is_made(
    given: dict[str, Any], said: str
) -> None:
    with pytest.raises(ValueError) as refused:
        contract(**given)
    assert said in str(refused.value)


RECORDED = Path(__file__).parent / "described" / "pydantic-2.13.5.json"


@pytest.mark.parametrize("model", SHAPES, ids=lambda model: model.__name__)
def test_every_shape_is_written_as_pydantic_2_13_5_wrote_it(model: type[BaseModel]) -> None:
    # Compared with the recording, never with the pydantic installed: that is the point.
    recorded = json.loads(RECORDED.read_text())
    assert described(model) == recorded[model.__name__]
