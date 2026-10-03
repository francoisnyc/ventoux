"""The catalog: what a definition can call, looked up by `name@version` (layer 1).

See docs/layers/01-catalog.md and docs/guides/activities.md.
"""

from typing import Any

import pytest
from pydantic import BaseModel

from ventoux.core.catalog import (
    ActivityContract,
    Catalog,
    Display,
    NotInCatalog,
    RetryPolicy,
    Timeouts,
)


class LookupInput(BaseModel):
    order_id: str


class LookupOutput(BaseModel):
    status: str


def lookup_contract(**changes: Any) -> ActivityContract:
    """A read-only contract, `orders.lookup@1`, with any field changed."""
    fields: dict[str, Any] = {
        "name": "orders.lookup",
        "version": 1,
        "input": LookupInput,
        "output": LookupOutput,
        "risk": "low",
        "effect": "read",
        "timeouts": Timeouts(start_to_close=10, schedule_to_start=60),
        "retry": RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
        "idempotency_key": None,
        "outcomes": [],
        "display": Display(title="Look up an order", description="Reads an order's status."),
    }
    return ActivityContract(**fields | changes)


def test_an_unknown_activity_is_not_in_the_catalog() -> None:
    with pytest.raises(NotInCatalog, match="payments.refund@1 is not in the catalog"):
        Catalog().get("payments.refund@1")


@pytest.mark.parametrize(
    "reference", ["payments.refund", "payments.refund@1.0", "payments.refund@0", "@1"]
)
def test_a_malformed_reference_says_what_a_reference_looks_like(reference: str) -> None:
    with pytest.raises(NotInCatalog, match="a reference is name@N"):
        Catalog().get(reference)


def test_a_registered_contract_is_found_by_its_reference() -> None:
    catalog = Catalog()
    contract = lookup_contract()
    catalog.register(contract)
    assert catalog.get("orders.lookup@1") is contract


def test_an_unknown_version_names_the_registered_ones() -> None:
    catalog = Catalog()
    catalog.register(lookup_contract())
    catalog.register(lookup_contract(version=2))
    with pytest.raises(
        NotInCatalog,
        match="orders.lookup@3 is not in the catalog. Registered: orders.lookup@1, orders.lookup@2",
    ):
        catalog.get("orders.lookup@3")
