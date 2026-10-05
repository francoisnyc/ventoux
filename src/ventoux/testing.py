"""Run cases in memory, in tests: no Temporal server, scripted answers, fake activities."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ventoux.case.runner import Activity, AnswerRefused, Run, run
from ventoux.core.catalog import ActivityContract, Catalog, Display, RetryPolicy, Timeouts

__all__ = ["AnswerRefused", "load_definition", "run_case"]


class RefundInput(BaseModel):
    order_id: str
    amount: Decimal
    idempotency_key: str  # filled by the engine, never by a definition


class RefundOutput(BaseModel):
    refund_id: str


payments_refund = ActivityContract(
    name="payments.refund",
    version=1,
    input=RefundInput,
    output=RefundOutput,
    risk="high",
    effect="write",
    timeouts=Timeouts(start_to_close=30, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=5, initial_interval=1, backoff_coefficient=2),
    idempotency_key="idempotency_key",
    outcomes=["declined"],
    display=Display(
        title="Refund a customer",
        description="Refunds an order through the payment provider.",
        outcomes={"declined": "The payment provider declined the refund"},
    ),
)


class LookupInput(BaseModel):
    order_id: str


class LookupOutput(BaseModel):
    status: str


orders_lookup = ActivityContract(
    name="orders.lookup",
    version=1,
    input=LookupInput,
    output=LookupOutput,
    risk="low",
    effect="read",  # reads only, so no idempotency key
    timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
    idempotency_key=None,
    outcomes=["not_found"],
    display=Display(
        title="Look up an order",
        description="Reads an order's status from the orders system.",
        outcomes={"not_found": "No such order"},
    ),
)


class DraftInput(BaseModel):
    to_customer: str
    template: str
    idempotency_key: str


class DraftOutput(BaseModel):
    draft_id: str


letters_draft = ActivityContract(
    name="letters.draft",
    version=1,
    input=DraftInput,
    output=DraftOutput,
    risk="low",  # it only drafts: a person reviews and sends
    effect="write",
    timeouts=Timeouts(start_to_close=30, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=5, initial_interval=1, backoff_coefficient=2),
    idempotency_key="idempotency_key",
    outcomes=[],
    display=Display(
        title="Draft a letter",
        description="Drafts a letter to a customer for a person to review. Never sends.",
    ),
)

# The development catalog: what a case can call in tests and the quickstart.
CATALOG = Catalog()
for contract in (payments_refund, orders_lookup, letters_draft):
    CATALOG.register(contract)


# Fake implementations, against no real system: nothing is paid, read or sent.
def fake_refund(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"refund_id": f"refund-{inputs['order_id']}"}


def fake_lookup(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"status": "delivered"}


def fake_draft(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"draft_id": f"draft-{inputs['template']}"}


FAKES: dict[str, Activity] = {
    "payments.refund@1": fake_refund,
    "orders.lookup@1": fake_lookup,
    "letters.draft@1": fake_draft,
}


# TRACER: a fixed directory of people and roles; roles come with layer 7 (design question 12).
PEOPLE: dict[str, set[str]] = {"ana": {"support"}, "sam": {"support", "support-lead"}}


def load_definition(path: Path) -> dict[str, Any]:
    """Read a case definition from its JSON file (I/O, so here and not in `case`)."""
    # TRACER: nothing is checked before the case runs; the validator comes in layer 3.
    # Numbers as exact decimals, never binary floats (brief, D20).
    definition: dict[str, Any] = json.loads(path.read_text(), parse_float=Decimal)
    return definition


def run_case(
    definition: dict[str, Any],
    file: dict[str, Any],
    answers: list[tuple[Any, ...]],
) -> Run:
    """Open a case with `file`, play the scripted `answers`, and report where it ended."""
    return run(definition, file, answers, CATALOG, FAKES, PEOPLE)
