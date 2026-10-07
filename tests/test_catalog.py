"""The catalog: what a definition can call, looked up by `name@version` (layer 1).

See docs/layers/01-catalog.md and docs/guides/activities.md.
"""

import copy
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, ValidationError

from ventoux import testing
from ventoux.core.catalog import Catalog, ContractConflict, NotInCatalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.contract_hash import contract_hash
from ventoux.core.hash_check import check_hashes
from ventoux.core.policy import Policy, only_from, trusted_only
from ventoux.testing import CATALOG, load_definition, payments_refund, run_case

ROOT = Path(__file__).parent.parent


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


def test_a_definition_naming_an_activity_not_in_the_catalog_stops_the_case() -> None:
    refund = copy.deepcopy(load_definition(ROOT / "examples" / "refund" / "refund.json"))
    refund["steps"]["pay"]["activity"] = "payments.refund@2"
    with pytest.raises(NotInCatalog, match="Registered: payments.refund@1"):
        run_case(
            refund,
            file={"order_id": "ord-1", "amount": 40},
            answers=[("review", "approve", "ana", {"approved_amount": 40})],
        )


def test_every_development_contract_matches_its_recorded_hash() -> None:
    # The CI check (D5): a contract edited without a new version fails here.
    recorded = json.loads((ROOT / "contracts.lock.json").read_text())
    assert check_hashes(CATALOG, recorded) == []


def test_the_guides_example_is_the_development_refund_contract() -> None:
    guide = (ROOT / "docs" / "guides" / "activities.md").read_text()
    example = guide.split("```python\n")[1].split("```")[0]
    # Our own documentation, run so it can't drift from the code; never a definition (data).
    namespace: dict[str, Any] = {}
    exec(example, namespace)  # noqa: S102 -- our guide, agreed in docs/layers/01-catalog.md
    assert contract_hash(namespace["payments_refund"]) == contract_hash(payments_refund)


@pytest.mark.parametrize(
    ("part", "values"),
    [
        (Timeouts, {"start_to_close": 0, "schedule_to_start": 60}),
        (Timeouts, {"start_to_close": 10, "schedule_to_start": -5}),
        # In Temporal, maximum_attempts=0 means retry forever.
        (RetryPolicy, {"maximum_attempts": 0, "initial_interval": 1, "backoff_coefficient": 2}),
        (RetryPolicy, {"maximum_attempts": 3, "initial_interval": 0, "backoff_coefficient": 2}),
        # Below 1, each retry comes sooner than the last, hammering a failing system.
        (RetryPolicy, {"maximum_attempts": 3, "initial_interval": 1, "backoff_coefficient": 0.5}),
    ],
)
def test_impossible_timeouts_and_retries_are_refused(
    part: type[Timeouts] | type[RetryPolicy], values: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError, match="greater than"):
        part.model_validate(values)


def test_the_order_of_outcomes_is_not_part_of_the_promise() -> None:
    titles = {"not_found": "No such order", "archived": "The order is archived"}
    display = Display(title="Look up an order", description="Reads an order.", outcomes=titles)
    one_way = lookup_contract(outcomes=["not_found", "archived"], display=display)
    other_way = lookup_contract(outcomes=["archived", "not_found"], display=display)
    assert contract_hash(one_way) == contract_hash(other_way)


def test_a_contract_with_no_implementation_stops_the_case_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(testing.FAKES, "payments.refund@1")
    refund = load_definition(ROOT / "examples" / "refund" / "refund.json")
    with pytest.raises(LookupError, match="no implementation of payments.refund@1"):
        run_case(
            refund,
            file={"order_id": "ord-1", "amount": 40},
            answers=[("review", "approve", "ana", {"approved_amount": 40})],
        )


def refund(**changes: Any) -> ActivityContract:
    """The guide's contract, `payments.refund@2`, with any field changed."""
    fields = {name: getattr(payments_refund, name) for name in ActivityContract.model_fields}
    return ActivityContract(**fields | changes)


# Each "You wrote" cell of the guide's refusal table, and the code that does it.
GUIDE_REFUSALS: dict[str, Any] = {
    '`effect="write"` with no `idempotency_key`': lambda: refund(idempotency_key=None),
    '`idempotency_key="request_id"`, not an input field': lambda: refund(
        idempotency_key="request_id"
    ),
    '`queue="payments"` in a contract': lambda: refund(queue="payments"),
    '`name="Payments Refund"`, or `version=0`': lambda: refund(name="Payments Refund"),
    '`outcomes=["declined"]` with no title for it': lambda: refund(
        display=Display(title="Refund a customer", description="Refunds an order.")
    ),
    "`RetryPolicy(maximum_attempts=0, …)`": lambda: RetryPolicy(
        maximum_attempts=0, initial_interval=1, backoff_coefficient=2
    ),
    '`catalog.register(payments_refund.model_copy(update={"risk": "hihg"}))`': lambda: (
        Catalog().register(payments_refund.model_copy(update={"risk": "hihg"}))
    ),
    "`only_from()`, naming no system": lambda: only_from(),
    "A policy kind of your own, `class Unless(Policy)` on `amount`": lambda: refund(
        input=RefundWithUnless
    ),
    "A second, different `payments.refund@2`": lambda: catalog_of(payments_refund).register(
        refund(risk="medium")
    ),
    '`catalog.get("payments.refund@3")`': lambda: catalog_of(payments_refund).get(
        "payments.refund@3"
    ),
    '`catalog.get("payments.refund@1.0")`': lambda: Catalog().get("payments.refund@1.0"),
}


def guide_refusal_rows() -> list[tuple[str, str]]:
    """The rows of the guide's table "What the catalog refuses", as (you wrote, Ventoux says)."""
    guide = (ROOT / "docs" / "guides" / "activities.md").read_text()
    table = guide.split("## What the catalog refuses")[1].split("\n## ")[0]
    rows = [line for line in table.splitlines() if line.startswith("| ")][1:]  # after the header
    return [(cells[1].strip(), cells[2].strip()) for cells in (row.split("|") for row in rows)]


def messages(error: Exception) -> list[str]:
    """What a refusal says, one message per problem: `field: message` for Pydantic's own."""
    if not isinstance(error, ValidationError):
        return [str(error)]
    said = []
    for problem in error.errors():
        message = problem["msg"].removeprefix("Value error, ")
        where = ".".join(str(part) for part in problem["loc"])
        said.append(f"{where}: {message}" if where else message)
    return said


def as_compared(message: str) -> str:
    """A message without the guide's code marks, its first letter's case or its final full stop."""
    message = message.replace("`", "").removesuffix(".")
    return message[:1].lower() + message[1:]


@pytest.mark.parametrize(("wrote", "says"), guide_refusal_rows())
def test_the_guides_refusals_are_what_the_catalog_says(wrote: str, says: str) -> None:
    # Every refusal says what is wrong, then what to do; the guide shows each word of it.
    assert wrote in GUIDE_REFUSALS, f"the guide's row {wrote!r} has no test"
    with pytest.raises(Exception) as refused:  # each row raises its own kind of error
        GUIDE_REFUSALS[wrote]()
    assert as_compared(says) in [as_compared(message) for message in messages(refused.value)]


def test_a_copy_that_breaks_the_rules_is_refused_at_registration() -> None:
    # `model_copy` runs no checks (learning question 31), so `register` checks again.
    broken = payments_refund.model_copy(update={"risk": "hihg", "idempotency_key": None})
    with pytest.raises(ValidationError, match="risk"):
        Catalog().register(broken)


def test_a_copy_with_a_broken_part_is_refused_at_registration() -> None:
    timeouts = payments_refund.timeouts.model_copy(update={"start_to_close": 0})
    broken = payments_refund.model_copy(update={"timeouts": timeouts})
    with pytest.raises(ValidationError, match="start_to_close"):
        Catalog().register(broken)


@dataclass(frozen=True)
class Unless(Policy):
    """A kind of policy a contract writer invented: the engine doesn't know it."""

    def refuses(self, sources: frozenset[str]) -> str | None:
        return None

    def describe(self) -> str:
        return "unless it's urgent"


class RefundWithUnless(BaseModel):
    order_id: str
    amount: Annotated[Decimal, Unless()]
    idempotency_key: str


# Every rule a contract enforces (docs/layers/03-validation.md), each with a change that breaks it.
# A change to a part (`timeouts`, `retry`) is written as that part's changed fields.
CONTRACT_RULES: list[tuple[str, dict[str, Any], str]] = [
    ("a field the contract doesn't know", {"queue": "payments"}, "deployment binding"),
    ("a field a part doesn't know", {"timeouts": {"heartbeat": 5}}, "heartbeat"),
    ("a name no reference could match", {"name": "Payments Refund"}, "no reference could name"),
    ("a version no reference could match", {"version": 0}, "no reference could name"),
    ("a side effect needs a key", {"idempotency_key": None}, "carries its idempotency key"),
    ("the key is an input field", {"idempotency_key": "request_id"}, "not a field of its input"),
    ("outcomes and titles match", {"outcomes": ("declined", "reversed")}, "titles must match"),
    ("a timeout above 0", {"timeouts": {"start_to_close": 0}}, "greater than 0"),
    ("a wait for a worker above 0", {"timeouts": {"schedule_to_start": 0}}, "greater than 0"),
    ("attempts above 0", {"retry": {"maximum_attempts": 0}}, "greater than 0"),
    ("an interval above 0", {"retry": {"initial_interval": 0}}, "greater than 0"),
    ("a backoff of at least 1", {"retry": {"backoff_coefficient": 0.5}}, "greater than or equal"),
    ("a risk from its list", {"risk": "hihg"}, "'low', 'medium' or 'high'"),
    ("an effect from its list", {"effect": "delete"}, "'read', 'compute', 'write' or 'notify'"),
    # Layer 4: the kinds of input policy are the engine's (brief, D21).
    ("a policy kind the engine knows", {"input": RefundWithUnless}, "Ventoux doesn't know"),
]
RULE_NAMES = [rule for rule, _, _ in CONTRACT_RULES]


def built(changes: dict[str, Any]) -> ActivityContract:
    """The guide's contract built with `changes`, each part built anew with its own."""
    fields = {name: getattr(payments_refund, name) for name in ActivityContract.model_fields}
    for name, change in changes.items():
        part = fields.get(name)
        if isinstance(part, BaseModel) and isinstance(change, dict):
            fields[name] = type(part).model_validate(part.model_dump() | change)
        else:
            fields[name] = change
    return ActivityContract.model_validate(fields)


def copied(changes: dict[str, Any]) -> ActivityContract:
    """The guide's contract copied with `changes`, which runs no check at all."""
    update = {}
    for name, change in changes.items():
        part = getattr(payments_refund, name, None)
        if isinstance(part, BaseModel) and isinstance(change, dict):
            update[name] = part.model_copy(update=change)
        else:
            update[name] = change
    return payments_refund.model_copy(update=update)


@pytest.mark.parametrize(("rule", "changes", "says"), CONTRACT_RULES, ids=RULE_NAMES)
def test_every_rule_refuses_a_contract_that_breaks_it(
    rule: str, changes: dict[str, Any], says: str
) -> None:
    with pytest.raises(ValidationError, match=says):
        built(changes)


@pytest.mark.parametrize(("rule", "changes", "says"), CONTRACT_RULES, ids=RULE_NAMES)
def test_every_rule_runs_again_when_a_copy_is_registered(
    rule: str, changes: dict[str, Any], says: str
) -> None:
    broken = copied(changes)  # accepted: a copy is never checked
    with pytest.raises(ValidationError, match=says):
        Catalog().register(broken)


def test_a_policy_kind_the_engine_does_not_know_is_refused() -> None:
    # Fail closed: a kind the engine doesn't know is refused, never ignored (brief, D21).
    with pytest.raises(ValidationError, match="input amount has a policy Ventoux doesn't know"):
        refund(input=RefundWithUnless)


def refund_input(*policies: Policy) -> type[BaseModel]:
    """A refund input, `RefundInput` as in the guide, with `policies` on its amount."""

    amount_type: Any = Annotated[Decimal, *policies] if policies else Decimal

    class RefundInput(BaseModel):
        order_id: str
        amount: amount_type
        idempotency_key: str

    return RefundInput


def test_a_policy_changes_the_hash() -> None:
    # A policy is part of what the contract promises, so adding one is a new version (brief, D21).
    without = contract_hash(refund(input=refund_input()))
    with_policy = contract_hash(refund(input=refund_input(trusted_only())))
    other_policy = contract_hash(refund(input=refund_input(only_from("payments"))))
    assert len({without, with_policy, other_policy}) == 3
