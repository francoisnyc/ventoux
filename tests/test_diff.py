"""The semantic diff: two packages compared by what they do (layer 13a; brief, D55).

See docs/layers/13-diff.md (13a) and docs/guides/releases.md, "What changed: the diff".
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, create_model

from ventoux.case.diff import Diff, DiffRefused, diff
from ventoux.case.releases import Package, package
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract
from ventoux.core.policy import (
    Policy,
    UnknownPolicy,
    compared,
    only_from,
    trusted_only,
)
from ventoux.testing import CATALOG, payments_refund

ROOT = Path(__file__).parent.parent
REFUND = ROOT / "examples" / "refund" / "refund.json"


def refund() -> dict[str, Any]:
    """The quickstart's refund, as data a test may change: `pay` calls `payments.refund@2`."""
    data: dict[str, Any] = json.loads(REFUND.read_text())
    return data


def packed(case: dict[str, Any], plans: list[dict[str, Any]] | None = None) -> Package:
    """The package of `case` and `plans`, written as JSON text, as a folder holds them."""
    return package(json.dumps(case), [json.dumps(plan) for plan in plans or []])


def lines(found: Diff) -> list[str]:
    """Each change as the developer form prints it."""
    return [str(change) for change in found.changes]


# --- A catalog with a refund that takes any amount -----------------------------------------------


def refund_input(*amount: Policy, **more: Any) -> type[BaseModel]:
    """@2's input, its `amount` taking `amount`'s policies, with `more` fields. Named as @2's is,
    `RefundInput`, so two contracts' schemas differ only where the test changes them."""
    # Pydantic: `create_model` builds a model class from its name and its fields' types.
    return create_model(
        "RefundInput",
        order_id=(Annotated[str, trusted_only()], ...),
        amount=(Annotated[Decimal, *amount] if amount else Decimal, ...),
        idempotency_key=(str, ...),
        **more,
    )


def refund_contract(version: int, input: type[BaseModel], **more: Any) -> ActivityContract:
    """`payments.refund@<version>`: @2's promise with another input, and `more` changed."""
    return ActivityContract.model_validate(
        dict(payments_refund) | {"version": version, "input": input} | more
    )


def catalog_with(*contracts: ActivityContract) -> Catalog:
    """The development catalog's refund, and `contracts`."""
    catalog = Catalog()
    for contract in (payments_refund, *contracts):
        catalog.register(contract)
    return catalog


LOOSE = catalog_with(refund_contract(3, refund_input()))  # @3 takes any amount


def calling(reference: str) -> dict[str, Any]:
    """The refund, its `pay` calling `reference`."""
    after = refund()
    after["steps"]["pay"]["activity"] = reference
    return after


# --- Slice 0: input policies ---------------------------------------------------------------------


def test_an_input_policy_loosened_is_reported_looser() -> None:
    # The curriculum's negative test: one character in the JSON, and a customer's amount could
    # reach the payment. Never hidden (brief, D55).
    found = diff(packed(refund()), packed(calling("payments.refund@3")), LOOSE)
    assert lines(found) == [
        (
            "looser     steps.pay.activity: payments.refund@2 -> payments.refund@3: input amount: "
            "was only from a system or a person, never from untrusted data; now any value "
            "(no input policy)"
        )
    ]


def test_an_input_policy_tightened_is_stricter() -> None:
    found = diff(packed(calling("payments.refund@3")), packed(refund()), LOOSE)
    assert lines(found) == [
        (
            "stricter   steps.pay.activity: payments.refund@3 -> payments.refund@2: input amount: "
            "was any value (no input policy); now only from a system or a person, never from "
            "untrusted data"
        )
    ]


def test_policies_neither_wider_nor_narrower_are_not_proven() -> None:
    # Neither accepts what the other does: no verdict is a proof, so none is claimed.
    two = catalog_with(
        refund_contract(4, refund_input(only_from("payments"))),
        refund_contract(5, refund_input(only_from("billing"))),
    )
    found = diff(packed(calling("payments.refund@4")), packed(calling("payments.refund@5")), two)
    assert lines(found) == [
        (
            "not proven steps.pay.activity: payments.refund@4 -> payments.refund@5: input amount: "
            "was only from payments; now only from billing"
        )
    ]


TRUSTED = [trusted_only()]


@pytest.mark.parametrize(
    ("old", "new", "how"),
    [
        ([], [], "same"),
        ([], TRUSTED, "narrower"),
        (TRUSTED, [], "wider"),
        (TRUSTED, [only_from("payments")], "narrower"),
        ([only_from("payments")], TRUSTED, "wider"),
        ([only_from("payments")], [only_from("payments", "billing")], "wider"),
        ([only_from("payments", "billing")], [only_from("payments")], "narrower"),
        ([only_from("payments")], [only_from("billing")], "neither"),
        # Every policy applies: two only_from accept what both name.
        (
            [only_from("payments", "billing"), only_from("payments")],
            [only_from("payments")],
            "same",
        ),
        # A system is trusted: trusted_only adds nothing to an only_from.
        ([only_from("payments"), trusted_only()], [only_from("payments")], "same"),
        # Nothing in common: nothing is accepted, which every policy accepts more than.
        ([only_from("payments"), only_from("billing")], [only_from("billing")], "wider"),
    ],
)
def test_policies_are_compared_exactly(old: list[Policy], new: list[Policy], how: str) -> None:
    assert compared(old, new) == how


class Unheard(Policy):
    """A kind of policy the engine doesn't know."""


def test_a_policy_kind_the_diff_doesnt_know_is_refused() -> None:
    with pytest.raises(UnknownPolicy, match="a kind Ventoux doesn't know \\(Unheard\\)"):
        compared([Unheard()], [])

    # A contract the catalog would refuse, built around its checks: the diff refuses it too.
    class Odd(BaseModel):
        order_id: Annotated[str, trusted_only()]
        amount: Annotated[Decimal, Unheard()]
        idempotency_key: str

    odd = ActivityContract.model_construct(**(dict(payments_refund) | {"version": 7, "input": Odd}))
    catalog = catalog_with()
    catalog._contracts[odd.reference] = odd
    with pytest.raises(DiffRefused, match="steps.pay.activity: an input policy of a kind"):
        diff(packed(refund()), packed(calling("payments.refund@7")), catalog)


def test_a_contract_missing_from_the_catalog_refuses_the_diff() -> None:
    with pytest.raises(DiffRefused, match="payments.refund@3 is not in the catalog"):
        diff(packed(refund()), packed(calling("payments.refund@3")), CATALOG)


def test_other_contract_differences_are_said_not_proven() -> None:
    with_a_note = refund_input(trusted_only(), note=(str, ...))
    noted = refund_contract(6, with_a_note, risk="medium")
    found = diff(packed(refund()), packed(calling("payments.refund@6")), catalog_with(noted))
    assert lines(found) == [
        (
            "not proven steps.pay.activity: payments.refund@2 -> payments.refund@6: input note "
            "only in payments.refund@6"
        ),
        (
            "not proven steps.pay.activity: payments.refund@2 -> payments.refund@6: its contract "
            "also differs: input, risk"
        ),
    ]
