"""Every shape a contract's field may take, as models (the contract hash fix) (brief, D83): what
`described` must write exactly as pydantic 2.13.5 did. Their 2.13.5 schemas are recorded in
`tests/described/pydantic-2.13.5.json` by `scripts/record_described.py`, run once, under the
locked pydantic."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ventoux.core.output_sources import source
from ventoux.core.policy import only_from, trusted_only
from ventoux.core.references import reference


class Kinds(BaseModel):
    text: str
    yes_or_no: bool
    amount: Decimal
    day: date
    one: Literal["only"]
    several: Literal["low", "medium", "high"]


class Optionals(BaseModel):
    text: str | None
    yes_or_no: bool | None
    amount: Decimal | None
    day: date | None
    one: Literal["only"] | None
    several: Literal["low", "high"] | None


class Defaults(BaseModel):
    text: str = "none given"
    yes_or_no: bool = False
    maybe_text: str | None = None
    maybe_amount: Decimal | None = None
    several: Literal["low", "high"] = "low"
    maybe_several: Literal["low", "high"] | None = None


class Described(BaseModel):
    """Refund an order, in the customer's currency.

    Indented lines, as a docstring has them.
    """

    order_id: str = Field(description="the order, as the shop numbers it")
    risk_score: Decimal = Field(description="from 0 to 100")


class Marked(BaseModel):
    customer_id: Annotated[str, reference("crm")]
    maybe_customer_id: Annotated[str | None, reference("crm")] = None
    amount: Annotated[Decimal, trusted_only()]
    note: Annotated[str, only_from("system:crm", "person")]
    both: Annotated[str, reference("crm"), trusted_only()]


class Sourced(BaseModel):
    risk_score: Annotated[Decimal, source("system:kyc")]
    maybe_note: Annotated[str | None, source("untrusted:llm")] = None
    held: Annotated[bool, source("person")]


SHAPES: list[type[BaseModel]] = [Kinds, Optionals, Defaults, Described, Marked, Sourced]
