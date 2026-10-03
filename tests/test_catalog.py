"""The catalog: what a definition can call, looked up by `name@version` (layer 1).

See docs/layers/01-catalog.md and docs/guides/activities.md.
"""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from ventoux.core.catalog import (
    ActivityContract,
    Catalog,
    ContractConflict,
    Display,
    NotInCatalog,
    RetryPolicy,
    Timeouts,
    check_hashes,
    contract_hash,
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


def test_a_reused_reference_with_different_content_is_refused() -> None:
    catalog = Catalog()
    catalog.register(lookup_contract())
    # Same name and version, longer timeout: a changed promise under the same name.
    changed = lookup_contract(timeouts=Timeouts(start_to_close=30, schedule_to_start=60))
    with pytest.raises(
        ContractConflict,
        match="orders.lookup@1 is already registered with different content: "
        "register it as orders.lookup@2",
    ):
        catalog.register(changed)


def test_registering_the_same_contract_again_changes_nothing() -> None:
    catalog = Catalog()
    catalog.register(lookup_contract())
    catalog.register(lookup_contract())  # built again, equal content: a no-op
    assert catalog.get("orders.lookup@1") == lookup_contract()


def test_a_registered_contract_cannot_be_changed_in_place() -> None:
    catalog = Catalog()
    contract = lookup_contract()
    catalog.register(contract)
    with pytest.raises(ValidationError, match="frozen"):
        contract.timeouts.start_to_close = 30
    with pytest.raises(ValidationError, match="frozen"):
        contract.version = 2


def test_a_side_effecting_contract_without_an_idempotency_key_is_refused() -> None:
    # Without a key, a retry after a timeout could do it twice (D17).
    with pytest.raises(ValidationError, match="must say which input carries its idempotency key"):
        lookup_contract(effect="write", idempotency_key=None)


def test_an_idempotency_key_must_be_an_input_field() -> None:
    with pytest.raises(ValidationError, match="'request_id' is not a field of its input"):
        lookup_contract(effect="write", idempotency_key="request_id")


def test_where_an_activity_runs_is_not_part_of_its_contract() -> None:
    # What vs where: a task queue belongs in a deployment binding (D5).
    with pytest.raises(ValidationError, match="'queue'.*belongs in a deployment binding"):
        lookup_contract(queue="payments")


def test_a_part_of_a_contract_refuses_fields_it_does_not_know() -> None:
    with pytest.raises(ValidationError, match="heartbeat"):
        Timeouts.model_validate({"start_to_close": 10, "schedule_to_start": 60, "heartbeat": 5})


@pytest.mark.parametrize(
    "changes", [{"name": "Payments Refund"}, {"name": "payments."}, {"version": 0}]
)
def test_a_contract_no_reference_could_name_is_refused(changes: dict[str, Any]) -> None:
    # It could be registered, but never looked up.
    with pytest.raises(ValidationError, match="no reference could name it"):
        lookup_contract(**changes)


@pytest.mark.parametrize(
    ("outcomes", "titles"),
    [(["not_found"], {}), ([], {"not_found": "No such order"})],
)
def test_every_outcome_has_a_title_and_every_title_an_outcome(
    outcomes: list[str], titles: dict[str, str]
) -> None:
    display = Display(title="Look up an order", description="Reads an order.", outcomes=titles)
    with pytest.raises(ValidationError, match="outcomes and their display titles must match"):
        lookup_contract(outcomes=outcomes, display=display)


def catalog_of(*contracts: ActivityContract) -> Catalog:
    catalog = Catalog()
    for contract in contracts:
        catalog.register(contract)
    return catalog


def test_a_contract_changed_without_a_new_version_is_reported() -> None:
    recorded = {"orders.lookup@1": contract_hash(lookup_contract())}
    # The same reference, edited in place: a longer timeout.
    edited = lookup_contract(timeouts=Timeouts(start_to_close=30, schedule_to_start=60))
    assert check_hashes(catalog_of(edited), recorded) == [
        "orders.lookup@1 changed without a new version: register it as orders.lookup@2."
    ]


def test_a_contract_with_no_recorded_hash_is_reported_with_the_line_to_add() -> None:
    contract = lookup_contract()
    assert check_hashes(catalog_of(contract), {}) == [
        f'orders.lookup@1 is not recorded yet: add "orders.lookup@1": "{contract_hash(contract)}".'
    ]


def test_a_wording_change_is_not_a_new_promise() -> None:
    reworded = lookup_contract(
        display=Display(title="Look up an order", description="Reads the status of an order.")
    )
    assert contract_hash(reworded) == contract_hash(lookup_contract())


def test_registering_a_reworded_contract_is_not_a_conflict() -> None:
    catalog = catalog_of(lookup_contract())
    reworded = lookup_contract(
        display=Display(title="Look up an order", description="Reads the status of an order.")
    )
    catalog.register(reworded)  # the same promise, worded differently
    assert contract_hash(catalog.get("orders.lookup@1")) == contract_hash(reworded)


def test_the_same_schema_written_twice_is_the_same_promise() -> None:
    class LookupInput(BaseModel):  # a second class, written separately, with the same schema
        order_id: str

    catalog = catalog_of(lookup_contract())
    catalog.register(lookup_contract(input=LookupInput))  # no conflict
