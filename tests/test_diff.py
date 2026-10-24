"""The semantic diff: two packages compared by what they do (layer 13a; brief, D55).

See docs/layers/13-diff.md (13a) and docs/guides/releases.md, "What changed: the diff".
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, create_model

from ventoux.case.diff import Diff, DiffRefused, diff
from ventoux.case.releases import Package, changed, digest, package
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


# --- Slice 1: nothing the digest sees is left out ------------------------------------------------

REFUND_PACKAGE = ROOT / "examples" / "packages" / "refund"


def settling() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The releases guide's package: the refund, settled by the plan `refund-order@1`."""
    case: dict[str, Any] = json.loads((REFUND_PACKAGE / "case.json").read_text())
    plan: dict[str, Any] = json.loads((REFUND_PACKAGE / "plans" / "refund-order.json").read_text())
    return case, [plan]


def test_a_change_the_diff_doesnt_judge_is_said_not_proven() -> None:
    # Two conditions are never compared: neither is a proof (brief, D55). Both are shown, as the
    # expression renderer writes them, and the reader judges.
    after = refund()
    after["steps"]["pay"]["approval"]["when"] = {">": [{"var": "approved_amount"}, 150]}
    found = diff(packed(refund()), packed(after), CATALOG)
    assert lines(found) == [
        "not proven steps.pay.approval.when: approved_amount > 100 -> approved_amount > 150"
    ]
    assert found.changes[0].comparison is None


def edited(edit: str) -> tuple[Package, Package, Catalog]:
    """The refund before and after `edit`, one of EDITS, and the catalog to compare them with."""
    case, plans = settling()
    quick = refund()
    after, after_plans, before, catalog = copy.deepcopy(case), copy.deepcopy(plans), case, CATALOG
    if edit == "a condition":
        after["steps"]["settle"]["when"] = {"==": [{"var": "review.outcome"}, "reject"]}
    elif edit == "a step added":
        after["steps"]["audit"] = {
            "kind": "task",
            "display": {"title": "Audit"},
            "roles": ["fraud"],
            "outcomes": {"done": {"display": {"title": "Done"}}},
        }
    elif edit == "a step removed":
        del after["steps"]["call_customer"]
    elif edit == "steps reordered":
        after["steps"] = dict(reversed(list(after["steps"].items())))
    elif edit == "a field retyped":
        after["fields"]["amount"]["type"] = "string"
    elif edit == "a field made sensitive":
        after["fields"]["amount"] |= {"sensitive": True, "visible_to": ["support"]}
    elif edit == "a field marked untrusted":
        after["fields"]["amount"]["source"] = "untrusted:customer"
    elif edit == "a field narrowed":
        after["fields"]["amount"]["visible_to"] = ["support"]
    elif edit == "a plan's transition":
        after_plans[0]["states"]["check_order"]["on"]["not_found"] = "paid"
    elif edit == "a plan's field marked":
        after_plans[0]["fields"]["amount"]["source"] = "untrusted:customer"
    elif edit == "a plan's contract":
        after_plans[0]["states"]["check_order"]["activity"] = "orders.lookup@2"
    elif edit == "forgetting":
        after["forgetting"] = "never"
    elif edit == "stays open":
        after["stays_open"] = True
        after["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    elif edit == "a contract":
        before, after, after_plans, catalog = quick, calling("payments.refund@3"), [], LOOSE
    elif edit == "a sequence":
        before, after, after_plans = quick, refund(), []
        after["sequence"] = ["review"]
    else:
        raise AssertionError(edit)
    plans_before = [] if before is quick else plans
    return packed(before, plans_before), packed(after, after_plans), catalog


EDITS = [
    "a condition",
    "a step added",
    "a step removed",
    "steps reordered",
    "a field retyped",
    "a field made sensitive",
    "a field marked untrusted",
    "a field narrowed",
    "a plan's transition",
    "a plan's field marked",
    "a plan's contract",
    "forgetting",
    "stays open",
    "a contract",
    "a sequence",
]


@pytest.mark.parametrize("edit", EDITS)
def test_the_diff_says_everything_the_digest_sees(edit: str) -> None:
    # Every path where 12a's comparison sees a behaviour change is covered by a change: the
    # diff never says less than the digest (brief, D55).
    before, after, catalog = edited(edit)
    seen = changed(before, after).behaviour
    found = diff(before, after, catalog)
    assert seen, f"{edit}: the edit changes no behaviour"
    said = [change.path for change in found.changes]
    for path in seen:
        assert any(path == where or path.startswith(f"{where}.") for where in said), (
            f"{edit}: {path} changed and the diff doesn't say it: {said}"
        )


def test_the_same_behaviour_has_no_changes() -> None:
    case, plans = settling()
    reformatted = package(json.dumps(case, indent=4), [json.dumps(plans[0], indent=1)])
    explicit = copy.deepcopy(case)
    explicit["stays_open"] = False  # the default, written out
    reworded = copy.deepcopy(case)
    reworded["steps"]["settle"]["display"]["title"] = "Pay the refund"
    for after in (reformatted, packed(explicit, plans), packed(reworded, plans)):
        assert digest(after) == digest(packed(case, plans))
        assert diff(packed(case, plans), after, CATALOG).changes == ()


def test_wording_is_listed_apart() -> None:
    case, plans = settling()
    after = copy.deepcopy(case)
    after["steps"]["settle"]["display"]["title"] = "Pay the refund"
    found = diff(packed(case, plans), packed(after, plans), CATALOG)
    assert found.changes == ()
    assert str(found) == (
        "refund: no behaviour change; 1 wording change\n"
        'wording    steps.settle.display.title: "Settle the refund" -> "Pay the refund"\n'
    )
    assert str(diff(packed(case, plans), packed(case, plans), CATALOG)) == (
        "refund: nothing changed\n"
    )


def test_not_proven_counts_with_looser() -> None:
    # Every doubt reads as looser: in the summary, what isn't proven is counted with it, as what
    # may loosen, before what is stricter (brief, D55).
    after = calling("payments.refund@3")
    after["steps"]["pay"]["approval"]["when"] = {">": [{"var": "approved_amount"}, 150]}
    after["fields"]["approved_amount"]["source"] = "untrusted:customer"
    found = diff(packed(refund()), packed(after), LOOSE)
    assert found.summary() == (
        "refund: 3 behaviour changes: 2 may loosen (1 looser, 1 not proven), 1 stricter; "
        "no wording change"
    )


def test_an_added_entrys_wording_is_part_of_it() -> None:
    before, after, catalog = edited("a step added")
    found = diff(before, after, catalog)
    assert "not proven steps.audit: added" in lines(found)
    assert found.wording == ()


# --- Slice 2: untrusted marks and sensitive values -----------------------------------------------


def marked(source: str | None) -> dict[str, Any]:
    """The refund, its `approved_amount` marked with `source`, or unmarked."""
    case = refund()
    if source is not None:
        case["fields"]["approved_amount"]["source"] = source
    return case


def test_an_untrusted_mark_removed_is_looser() -> None:
    # Values written there no longer carry the distrust a `trusted_only` input refuses.
    found = diff(packed(marked("untrusted:customer")), packed(marked(None)), CATALOG)
    assert lines(found) == ["looser     fields.approved_amount.source: untrusted:customer -> none"]
    assert found.changes[0].comparison == "untrusted mark"


def test_an_untrusted_mark_added_is_stricter() -> None:
    found = diff(packed(marked(None)), packed(marked("untrusted:customer")), CATALOG)
    assert lines(found) == ["stricter   fields.approved_amount.source: none -> untrusted:customer"]


def test_a_relabelled_mark_is_not_proven() -> None:
    # No policy reads a label today; "today" proves nothing for every later kind.
    found = diff(packed(marked("untrusted:customer")), packed(marked("untrusted:llm")), CATALOG)
    assert lines(found) == [
        "not proven fields.approved_amount.source: untrusted:customer -> untrusted:llm"
    ]


def with_a_note(source: str | None) -> dict[str, Any]:
    """The refund with an event from the portal carrying the customer's note, marked `source`."""
    case = refund()
    note: dict[str, Any] = {"type": "string", "display": {"title": "Note"}}
    if source is not None:
        note["source"] = source
    case["events"] = {
        "cancelled": {
            "display": {"title": "Cancelled by the customer"},
            "sent_by": {"system": "portal"},
            "payload": {"note": note},
        }
    }
    return case


def test_marks_on_payloads_and_plans_are_judged() -> None:
    found = diff(packed(with_a_note("untrusted:customer")), packed(with_a_note(None)), CATALOG)
    assert lines(found) == [
        "looser     events.cancelled.payload.note.source: untrusted:customer -> none"
    ]
    case, plans = settling()
    after = copy.deepcopy(plans)
    after[0]["fields"]["amount"]["source"] = "untrusted:customer"
    found = diff(packed(case, after), packed(case, plans), CATALOG)
    assert lines(found) == [
        "looser     plans.refund-order@1.fields.amount.source: untrusted:customer -> none"
    ]


def sensitive(on: bool) -> dict[str, Any]:
    """The refund, its `amount` sensitive or not, seen by support either way."""
    case = refund()
    case["fields"]["amount"]["visible_to"] = ["support"]
    if on:
        case["fields"]["amount"]["sensitive"] = True
    return case


def test_sensitive_removed_is_looser() -> None:
    # No longer wrapped: it may be given to a workflow step, whose worker another team runs.
    found = diff(packed(sensitive(True)), packed(sensitive(False)), CATALOG)
    assert lines(found) == ["looser     fields.amount.sensitive: true -> false"]
    assert found.changes[0].comparison == "sensitive"


def test_sensitive_added_is_stricter() -> None:
    found = diff(packed(sensitive(False)), packed(sensitive(True)), CATALOG)
    assert lines(found) == ["stricter   fields.amount.sensitive: false -> true"]


# --- Slice 3: who sees what ----------------------------------------------------------------------


def seen_by(*roles: str) -> dict[str, Any]:
    """The refund, its `amount` seen only by `roles`."""
    case = refund()
    case["fields"]["amount"]["visible_to"] = list(roles)
    return case


def test_visible_to_widened_is_looser() -> None:
    found = diff(packed(seen_by("support")), packed(seen_by("support", "support-lead")), CATALOG)
    assert lines(found) == [
        "looser     fields.amount.visible_to: seen by support -> support, support-lead"
    ]
    assert found.changes[0].comparison == "readers"


def test_visible_to_narrowed_is_stricter() -> None:
    # Without visible_to, every role the case names sees it: support and support-lead.
    found = diff(packed(refund()), packed(seen_by("support")), CATALOG)
    assert lines(found) == [
        "stricter   fields.amount.visible_to: seen by support, support-lead -> support"
    ]


def test_readers_both_added_and_removed_are_not_proven() -> None:
    found = diff(packed(seen_by("support")), packed(seen_by("support-lead")), CATALOG)
    assert lines(found) == ["not proven fields.amount.visible_to: seen by support -> support-lead"]
    assert found.changes[0].comparison is None


def test_a_new_role_sees_every_unnarrowed_field() -> None:
    # A change the JSON diff hides: nothing about the fields changes in the JSON, but a field
    # without visible_to is seen by every role the case names (brief, D30, D53), so `fraud`,
    # named by a new step, now sees each, and every outcome and output (brief, D55).
    before = seen_by("support")
    after = copy.deepcopy(before)
    after["steps"]["fraud_check"] = {
        "kind": "task",
        "display": {"title": "Check for fraud"},
        "roles": ["fraud"],
        "requires": ["review"],
        "outcomes": {"clear": {"display": {"title": "Clear"}}},
    }
    found = diff(packed(before), packed(after), CATALOG)
    roles = "seen by support, support-lead -> fraud, support, support-lead"
    because = "(because steps.fraud_check.roles names fraud)"
    assert lines(found) == [
        f"looser     fields.order_id.visible_to: {roles} {because}",
        f"looser     fields.approved_amount.visible_to: {roles} {because}",
        f"looser     steps: every outcome and output: {roles} {because}",
        "not proven steps.fraud_check: added",
    ]
