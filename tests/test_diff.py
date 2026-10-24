"""The semantic diff: two packages compared by what they do (layer 13a; brief, D55).

See docs/layers/13-diff.md (13a) and docs/guides/releases.md, "What changed: the diff".
"""

import copy
import inspect
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, create_model

from ventoux.case.changes import COMPARISONS, Change, DiffRefused
from ventoux.case.diff import Diff, diff
from ventoux.case.memory import CaseRun
from ventoux.case.releases import Package, changed, digest, package
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract
from ventoux.core.output_sources import source
from ventoux.core.policy import (
    Policy,
    UnknownPolicy,
    compared,
    only_from,
    trusted_only,
)
from ventoux.testing import (
    CATALOG,
    fake_refund,
    payments_refund,
    run_case,
)
from ventoux.testing import (
    orders_lookup_2 as lookup_2,
)
from ventoux.tooling.cli import main

ROOT = Path(__file__).parent.parent
REFUND = ROOT / "examples" / "refund" / "refund.json"
FOUR_EYES = ROOT / "examples" / "refund" / "refund-four-eyes.json"

# A version of a definition a test compares: a case alone, or a package with its plans.
type Definition = dict[str, Any] | Package


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
    """The development catalog, and `contracts`."""
    catalog = copy.deepcopy(CATALOG)
    for contract in contracts:
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
    # Path by path, as a hash failure says it (brief, D57); an input or output only one contract
    # has is said once, by name, never again as its path.
    with_a_note = refund_input(trusted_only(), note=(str, ...))
    with_a_fee = create_model("RefundOutput", refund_id=(str, ...), fee=(Decimal, ...))
    noted = refund_contract(6, with_a_note, risk="medium", output=with_a_fee)
    found = diff(packed(refund()), packed(calling("payments.refund@6")), catalog_with(noted))
    assert lines(found) == [
        (
            "not proven steps.pay.activity: payments.refund@2 -> payments.refund@6: input note "
            "only in payments.refund@6"
        ),
        (
            "not proven steps.pay.activity: payments.refund@2 -> payments.refund@6: output fee "
            "only in payments.refund@6"
        ),
        (
            "not proven steps.pay.activity: payments.refund@2 -> payments.refund@6: input.required: "
            '["order_id", "amount", "idempotency_key"] -> ["order_id", "amount", "idempotency_key", '
            '"note"]'
        ),
        (
            "not proven steps.pay.activity: payments.refund@2 -> payments.refund@6: "
            'output.required: ["refund_id"] -> ["refund_id", "fee"]'
        ),
        "not proven steps.pay.activity: payments.refund@2 -> payments.refund@6: risk: high -> medium",
    ]


def test_a_verdict_names_its_comparison() -> None:
    # Looser or stricter only from a comparison on the closed list; not proven from none.
    with pytest.raises(ValueError, match="looser needs one of COMPARISONS"):
        Change("steps.pay.when", "looser", "a guess")
    with pytest.raises(ValueError, match="not proven needs one of COMPARISONS, and only it"):
        Change("fields.amount.source", "not proven", "none -> untrusted:llm", "untrusted mark")
    with pytest.raises(ValueError, match="stricter needs one of COMPARISONS"):
        Change("steps.pay.approval.count", "stricter", "1 -> 2", "approvals")  # 13b's


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


# --- Slice 4: renames and order ------------------------------------------------------------------


def test_a_renamed_step_is_removed_and_added() -> None:
    # A migration's mapping isn't in either package, so a rename is never guessed; that the new
    # step behaves exactly as the removed one did is a proof, and is said (brief, D53, D55).
    after = refund()
    steps = after["steps"]
    after["steps"] = {
        "review": steps["review"],
        "pay": steps["pay"],
        "call": steps["call_customer"],
    }
    found = diff(packed(refund()), packed(after), CATALOG)
    assert lines(found) == [
        "not proven steps.call_customer: removed",
        (
            "not proven steps.call: added: behaves as the removed call_customer did: open cases "
            "need a migration mapping call_customer to call (brief, D53)"
        ),
    ]
    assert found.wording == ()


def test_changes_come_in_the_packages_order() -> None:
    # The case before its plans; its sections in the order the format writes them; each map in
    # the new version's order, a removed entry where it was (brief, D55).
    case, plans = settling()
    task = {
        "kind": "task",
        "display": {"title": "A task"},
        "roles": ["support"],
        "outcomes": {"done": {"display": {"title": "Done"}}},
    }
    steps = case["steps"]
    case["steps"] = {"review": steps["review"], "note": task} | steps  # note, between two
    after, after_plans = copy.deepcopy(case), copy.deepcopy(plans)
    after["forgetting"] = "never"
    after_plans[0]["states"]["approve_refund"]["approval"]["timeout"] = "72h"
    kept = {name: step for name, step in after["steps"].items() if name != "note"}
    audit = task | {"outcomes": {"checked": {"display": {"title": "Checked"}}}}
    after["steps"] = {"audit": audit} | kept  # audit first, note gone
    after["steps"]["settle"]["when"] = {"==": [{"var": "review.outcome"}, "reject"]}
    after["fields"]["approved_amount"]["source"] = "untrusted:customer"
    expected = [
        "stricter   fields.approved_amount.source: none -> untrusted:customer",
        "not proven steps.audit: added",
        "not proven steps.note: removed",
        'not proven steps.settle.when: review.outcome = "approve" -> review.outcome = "reject"',
        "stricter   forgetting: allowed -> never",  # judged since 13b
        "not proven plans.refund-order@1.states.approve_refund.approval.timeout: 48h -> 72h",
    ]
    assert lines(diff(packed(case, plans), packed(after, after_plans), CATALOG)) == expected
    # The same every time.
    assert lines(diff(packed(case, plans), packed(after, after_plans), CATALOG)) == expected


def test_the_diff_reads_only_packages_and_the_catalog() -> None:
    # It is given no case file, so it can't quote a value from one: what it shows is what the
    # definitions and the catalog write (brief, D55).
    given = [parameter.annotation for parameter in inspect.signature(diff).parameters.values()]
    assert given == [Package, Package, Catalog]


# --- Slice 7: output sources (added to 13a in its review) ----------------------------------------


def looking_up(reference: str) -> dict[str, Any]:
    """A case looking an order up with `reference`, then deciding on its status: a rule reaches
    `delivered` once the lookup says so."""
    return {
        "case": "delivery",
        "display": {"title": "A delivery"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}}
        },
        "milestones": {
            "looked_up": {"display": {"title": "Looked up"}},
            "delivered": {"display": {"title": "Delivered"}},
        },
        "steps": {
            "lookup": {
                "kind": "activity",
                "display": {"title": "Look the order up"},
                "activity": reference,
                "inputs": {"order_id": {"var": "order_id"}},
                "reaches": ["looked_up"],
            }
        },
        "rules": {
            "delivery": {
                "display": {"title": "Delivered, as the orders system says"},
                "on": {"reached": "looked_up"},
                "when": {"==": [{"var": "lookup.status"}, "delivered"]},
                "then": {"reach": ["delivered"]},
            }
        },
    }


def test_an_output_source_made_a_system_is_looser() -> None:
    # @1 declares no source for `status`, so it is untrusted:undeclared and decides nothing; @2
    # says the orders system gives it (brief, D29). A case may now decide on it.
    found = diff(
        packed(looking_up("orders.lookup@1")), packed(looking_up("orders.lookup@2")), CATALOG
    )
    assert lines(found)[0] == (
        "looser     steps.lookup.activity: orders.lookup@1 -> orders.lookup@2: output status: "
        "was untrusted:undeclared; now system:orders"
    )
    assert found.changes[0].comparison == "output source"


def test_an_output_source_made_untrusted_is_stricter() -> None:
    found = diff(
        packed(looking_up("orders.lookup@2")), packed(looking_up("orders.lookup@1")), CATALOG
    )
    assert lines(found)[0] == (
        "stricter   steps.lookup.activity: orders.lookup@2 -> orders.lookup@1: output status: "
        "was system:orders; now untrusted:undeclared"
    )


def test_one_system_for_another_is_not_proven() -> None:
    # Neither is a proof: what each system says is trusted, and a policy may name one and not
    # the other (brief, D21).
    from_crm = lookup_2.model_validate(
        dict(lookup_2)
        | {
            "version": 3,
            # Named as @2's output is, so only the source differs.
            "output": create_model(
                "LookupOutputFromOrders", status=(Annotated[str, source("system:crm")], ...)
            ),
        }
    )
    found = diff(
        packed(looking_up("orders.lookup@2")),
        packed(looking_up("orders.lookup@3")),
        catalog_with(from_crm),
    )
    assert lines(found) == [
        (
            "not proven steps.lookup.activity: orders.lookup@2 -> orders.lookup@3: output status: "
            "was system:orders; now system:crm"
        )
    ]
    assert found.changes[0].comparison is None


# --- Slice 5: a witness for each comparison ------------------------------------------------------
#
# A witness is a pair of definitions the diff reads as looser by one comparison, and two runs:
# the old version refuses what the new one lets through. Read the other way, the same pair is
# stricter, so one witness proves both verdicts (brief, D55).

SUPPORT = {"ana": ["support"], "lee": ["support-lead"]}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 50})  # under 100: no approval...
# ...unless the amount is untrusted, which can't remove an approval (brief, D38): a team lead's.
APPROVED = ("pay.approval#1", "approve", "lee")


def refund_runs(case: dict[str, Any], catalog: Catalog = CATALOG) -> CaseRun:
    """The refund run to its payment: reviewed, 50 approved, and approved by a team lead if
    the amount is marked untrusted."""
    untrusted = "source" in case["fields"]["approved_amount"]
    return run_case(
        case,
        file={"order_id": "ord-1", "amount": 50},
        answers=[REVIEWED, APPROVED] if untrusted else [REVIEWED],
        people=SUPPORT,
        activities={"payments.refund@3": fake_refund},
        catalog=catalog,
    )


def policy_witness() -> tuple[dict[str, Any], dict[str, Any], Catalog, bool, bool]:
    """@2 refuses an amount marked untrusted; @3, with no policy on it, takes it."""
    before = marked("untrusted:customer")
    after = copy.deepcopy(before)
    after["steps"]["pay"]["activity"] = "payments.refund@3"
    refused = policy_refused(refund_runs(before, LOOSE))
    taken = refund_runs(after, LOOSE).reached("pay")
    return before, after, LOOSE, refused, taken


def policy_refused(run: CaseRun) -> bool:
    """Whether the payment was refused by its input policy on `amount`, and only that."""
    return not run.reached("pay") and run.needs_attention == [
        (
            "pay#1: payments.refund@2 takes amount only from a system or a person, never from "
            "untrusted data, and this value comes from approved_amount (person:ana, "
            "untrusted:customer)"
        )
    ]


def mark_witness() -> tuple[dict[str, Any], dict[str, Any], Catalog, bool, bool]:
    """The same amount, refused while its field carries the mark, taken once it doesn't."""
    before, after = marked("untrusted:customer"), marked(None)
    return (
        before,
        after,
        CATALOG,
        policy_refused(refund_runs(before)),
        refund_runs(after).reached("pay"),
    )


def identified(sensitive: bool) -> dict[str, Any]:
    """A case checking a customer's ID through the KYC team's workflow, the ID sensitive or not."""
    field: dict[str, Any] = {
        "type": "string",
        "display": {"title": "ID"},
        "visible_to": ["support"],
    }
    if sensitive:
        field["sensitive"] = True
    return {
        "case": "identified",
        "display": {"title": "A customer identified"},
        "fields": {"national_id": field},
        "steps": {
            "kyc": {
                "kind": "workflow",
                "display": {"title": "Check the customer"},
                "workflow": "kyc.check@1",
                "inputs": {"customer_id": {"var": "national_id"}},
            }
        },
    }


def checks(case: dict[str, Any]) -> CaseRun:
    """The KYC workflow given the ID."""
    run = run_case(
        case,
        file={"national_id": "1 85 05 78 006 084 36"},
        answers=[],
        people=SUPPORT,
    )
    return run


def sensitive_witness() -> tuple[dict[str, Any], dict[str, Any], Catalog, bool, bool]:
    """A sensitive ID is never given to a workflow step; once not sensitive, it is."""
    before, after = identified(True), identified(False)
    refused = checks(before).needs_attention == [
        (
            "kyc#1: kyc.check@1 is a workflow step and can't be given national_id, a sensitive "
            "field: its worker doesn't hold the case's key"
        )
    ]
    return before, after, CATALOG, refused, checks(after).reached("kyc")


def readers_witness() -> tuple[dict[str, Any], dict[str, Any], Catalog, bool, bool]:
    """`amount` absent from a team lead's view, then present."""
    before, after = seen_by("support"), seen_by("support", "support-lead")

    def sees(case: dict[str, Any]) -> bool:
        run = run_case(case, file={"order_id": "ord-1", "amount": 50}, answers=[], people=SUPPORT)
        return "amount" in run.view(["support-lead"]).values

    return before, after, CATALOG, not sees(before), sees(after)


def output_witness() -> tuple[dict[str, Any], dict[str, Any], Catalog, bool, bool]:
    """A rule reaching `delivered` on the lookup's status acts on nothing while the contract
    leaves it undeclared, and reaches it once the orders system gives it (brief, D29, D38)."""
    before, after = looking_up("orders.lookup@1"), looking_up("orders.lookup@2")

    def delivered(case: dict[str, Any]) -> CaseRun:
        delivers = {"orders.lookup@1": lambda _: {"status": "delivered"}}
        delivers["orders.lookup@2"] = delivers["orders.lookup@1"]
        return run_case(
            case, file={"order_id": "ord-1"}, answers=[], people=SUPPORT, activities=delivers
        )

    old, new = delivered(before), delivered(after)
    refused = (
        "delivered" not in old.state.milestones
        and (
            "delivery#1 on reached looked_up: reaches nothing: its condition reads lookup.status, "
            "from untrusted:undeclared, and untrusted data can't decide"
        )
        in old.history
    )
    return before, after, CATALOG, refused, "delivered" in new.state.milestones


WITNESSES = {
    "input policy": policy_witness,
    "untrusted mark": mark_witness,
    "sensitive": sensitive_witness,
    "readers": readers_witness,
    "output source": output_witness,
}


@pytest.mark.parametrize("comparison", list(WITNESSES))
def test_each_comparison_has_a_witness(comparison: str) -> None:
    witnessed(comparison, *WITNESSES[comparison]())


def witnessed(
    comparison: str,
    before: Definition,
    after: Definition,
    catalog: Catalog,
    refused: bool,
    taken: bool,
) -> None:
    """Check a witness: the old version refuses what the new one takes, and the diff reads the
    pair as looser by `comparison`, and the other way round as stricter."""
    assert refused, f"{comparison}: the old version lets it through"
    assert taken, f"{comparison}: the new version refuses it"
    old, new = as_package(before), as_package(after)
    # What is judged, by which comparison; a change said and not proven beside it may stay (the
    # output's class renamed between orders.lookup@1 and @2 is one: its contract also differs).
    looser = diff(old, new, catalog).changes
    stricter = diff(new, old, catalog).changes
    assert [(c.verdict, c.comparison) for c in looser if c.comparison] == [("looser", comparison)]
    assert [(c.verdict, c.comparison) for c in stricter if c.comparison] == [
        ("stricter", comparison)
    ]


def as_package(definition: Definition) -> Package:
    """A witness's version as a package: a case alone is packed with no plans."""
    return definition if isinstance(definition, Package) else packed(definition)


def test_the_witnesses_cover_every_comparison() -> None:
    # A comparison can't give a verdict without a run that shows it (brief, D55). 13b's
    # witnesses, on people and runs, are in test_diff_people.py.
    from test_diff_people import WITNESSES as PEOPLE

    assert list(WITNESSES | PEOPLE) == list(COMPARISONS)


# --- Slice 6: the command, and the guide ---------------------------------------------------------

GUIDE = ROOT / "docs" / "guides" / "releases.md"


def folder_of(path: Path, case: dict[str, Any], plans: list[dict[str, Any]] | None = None) -> Path:
    """A package folder at `path` holding `case` and `plans`."""
    path.mkdir(parents=True)
    (path / "case.json").write_text(json.dumps(case, indent=2))
    if plans:
        (path / "plans").mkdir()
        for plan in plans:
            (path / "plans" / f"{plan['plan']}.json").write_text(json.dumps(plan, indent=2))
    return path


def test_the_command_says_the_diff(tmp_path: Path, capsys: Any) -> None:
    old = folder_of(tmp_path / "old", marked("untrusted:customer"))
    new = folder_of(tmp_path / "new", marked(None))
    # Compared: exit 0, even with a looser change; that is the reviewer's to judge.
    assert main(["diff", str(old), str(new)]) == 0
    assert capsys.readouterr().out == (
        "refund: 1 behaviour change: 1 may loosen (1 looser, 0 not proven), 0 stricter; "
        "no wording change\n"
        "looser     fields.approved_amount.source: untrusted:customer -> none\n"
    )
    # Refused: a contract the catalog doesn't hold, or a package that isn't one; exit 1.
    elsewhere = folder_of(tmp_path / "elsewhere", calling("payments.refund@9"))
    assert main(["diff", str(old), str(elsewhere)]) == 1
    assert "payments.refund@9 is not in the catalog" in capsys.readouterr().err
    (new / "notes.txt").write_text("to do")
    assert main(["diff", str(old), str(new)]) == 1
    assert capsys.readouterr().err == (
        f"{new}: notes.txt isn't part of a package: a package holds case.json and plans/\n"
    )
    # Unreadable: exit 2.
    (new / "notes.txt").unlink()
    (new / "case.json").write_text("{")
    assert main(["diff", str(old), str(new)]) == 2
    assert capsys.readouterr().err.startswith(f"{new}: case.json isn't JSON: ")


def guide_runs() -> list[tuple[list[str], str]]:
    """Each `$ ventoux diff …` in the guide's "What changed: the diff", with what it prints."""
    # Up to the next section of the guide: the plain form's own `## ` headings are inside it.
    section = GUIDE.read_text().split("## What changed: the diff")[1]
    section = section.split("\n## What the tool says")[0]
    runs = []
    for block in section.split("```\n")[1::2]:
        command_line, *printed = block.strip().splitlines()
        assert command_line.startswith("$ ventoux diff ")
        runs.append((command_line.removeprefix("$ ventoux ").split(), "\n".join(printed) + "\n"))
    return runs


def test_the_guides_example_runs_as_written(tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)  # the guide's paths are relative, from the repository's root
    # First, the refund moved to a @3 that takes any amount: a catalog holding it.
    folder_of(tmp_path / "refund-before", refund())
    folder_of(tmp_path / "refund-after", calling("payments.refund@3"))
    # Then the releases guide's package, and the next version the guide describes: a fraud check
    # for the fraud role, the amount marked as typed by the customer, 72 hours to approve, and
    # the settlement reworded.
    case, plans = settling()
    folder_of(tmp_path / "examples" / "packages" / "refund", case, plans)
    after, after_plans = copy.deepcopy(case), copy.deepcopy(plans)
    after["fields"]["amount"]["source"] = "untrusted:customer"
    after["steps"]["fraud_check"] = {
        "kind": "task",
        "display": {"title": "Check for fraud"},
        "roles": ["fraud"],
        "requires": ["review"],
        "outcomes": {"clear": {"display": {"title": "No fraud found"}}},
    }
    after["steps"]["settle"]["display"]["title"] = "Pay the refund"
    after_plans[0]["states"]["approve_refund"]["approval"]["timeout"] = "72h"
    folder_of(tmp_path / "refund-next", after, after_plans)
    # The four-eyes refund, back to one team lead (13b).
    folder_of(tmp_path / "refund-four-eyes", json.loads(FOUR_EYES.read_text()))
    one_lead = json.loads(FOUR_EYES.read_text())
    one_lead["steps"]["pay"]["approval"]["count"] = 1
    folder_of(tmp_path / "refund-one-lead", one_lead)
    runs = guide_runs()
    assert len(runs) == 4  # the fourth, the same refunds in plain words (13c)
    catalogs = (LOOSE, CATALOG, CATALOG, CATALOG)
    for (arguments, printed), catalog in zip(runs, catalogs, strict=True):
        monkeypatch.setattr("ventoux.tooling.cli.CATALOG", catalog)
        assert main(arguments) == 0
        assert capsys.readouterr().out == printed
