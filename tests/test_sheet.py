"""The case map and the "will never do" sheet (layer 13c; brief, D56).

See docs/layers/13-diff.md (13c) and docs/guides/cases.md, "What a case can do, and will never do".
"""

import inspect
import re
from collections.abc import Callable

from test_diff import (
    ROOT,
    Definition,
    as_package,
    calling,
    catalog_with,
    packed,
    policy_witness,
    readers_witness,
    refund,
    refund_contract,
    refund_input,
    sensitive_witness,
    settling,
)
from test_diff_people import approval_witness, exclusions_witness, forgetting_witness

from ventoux.case.releases import Package
from ventoux.case.sheet import ENGINE_WIDE, NEVERS, case_map, never_sheet, nevers
from ventoux.core.catalog import Catalog
from ventoux.core.policy import only_from
from ventoux.testing import CATALOG, run_case

TESTS = ROOT / "tests"


# --- Slice 3: the case map -----------------------------------------------------------------------


def test_the_case_map_reads_every_entry_in_the_formats_order() -> None:
    assert case_map(packed(refund()), CATALOG) == (
        "# refund: what a case can do\n"
        "\n"
        "## Fields\n"
        "\n"
        "- order_id is a reference to orders, seen by support and support-lead.\n"
        "- amount is a number, seen by support and support-lead.\n"
        "- approved_amount is a number, seen by support and support-lead.\n"
        "\n"
        "## Steps\n"
        "\n"
        "- review is a task for support, answered approve or reject. It starts by itself when the "
        "case opens. Answered approve, it sets approved_amount.\n"
        "- pay calls payments.refund@2 (high risk, it writes), giving order_id from order_id and "
        "amount from approved_amount. It starts by itself once review is done, if "
        'review.outcome = "approve". One support-lead approves it, when approved_amount > 100.\n'
        "  - Where approved_amount > 100 is false, it runs with no approval.\n"
        "- call_customer is a task for support, answered called. It starts by itself once pay is "
        'done, if pay.outcome = "declined".\n'
        "\n"
        "## Closing\n"
        "\n"
        "- It closes when nothing is left to do. Its records may be forgotten, open or closed.\n"
    )


# --- Slice 3: the "will never do" sheet ----------------------------------------------------------


def test_the_sheet_says_the_engines_guarantees_once_then_the_packages() -> None:
    sheet = never_sheet(packed(refund()), CATALOG)
    engine = "".join(f"- {line} ({decisions}).\n" for line, decisions in ENGINE_WIDE)
    assert sheet == (
        "# refund will never\n"
        "\n"
        "## For every case, by Ventoux's engine\n"
        "\n"
        f"{engine}"
        "\n"
        "## For every case of refund\n"
        "\n"
        "- call anything but payments.refund@2 (high risk, it writes).\n"
        "- change the world, by what its contracts declare, but through payments.refund@2.\n"
        "- give payments.refund@2 its order_id or its amount from untrusted data.\n"
        "- show order_id, amount or approved_amount to anyone but support or support-lead.\n"
        "- show any step's outcome or outputs to anyone but support or support-lead.\n"
        "- let whoever answers review approve pay.\n"
    )


# Each engine-wide guarantee, and the tests that already prove it (13c, choice 40).
PROVEN = {
    "D20": [
        "test_layers.py::test_pure_layers_may_not_run_text_as_code",
        "test_layers.py::test_pure_layers_may_not_read_the_clock_randomness_or_io",
    ],
    "D5": [
        "test_catalog.py::test_a_definition_naming_an_activity_not_in_the_catalog_stops_the_case"
    ],
    "D38": ["test_rules.py::test_untrusted_data_cant_decide"],
    "D11, D25": [
        "test_approvals.py::test_every_approver_is_someone_else",
        "test_case.py::test_the_person_who_proposed_a_step_cannot_approve_it",
        "test_case.py::test_the_opener_cannot_approve",
    ],
    "D11": [
        "test_validate.py::test_one_approval_unlocks_one_high_risk_run",
        "test_case.py::test_an_approval_unlocks_one_run_with_its_own_key",
    ],
    "D17": ["test_case.py::test_a_failed_step_needs_attention_and_keeps_the_case_open"],
    "D31": [
        "test_sensitive.py::test_a_workflow_step_is_never_given_a_sensitive_value",
        "test_sensitive.py::test_a_sensitive_value_never_prints",
    ],
}


def test_each_engine_wide_guarantee_names_tests_that_prove_it() -> None:
    assert [decisions for _, decisions in ENGINE_WIDE] == list(PROVEN)
    for decisions, tests in PROVEN.items():
        for test in tests:
            file, name = test.split("::")
            source = (TESTS / file).read_text()
            assert re.search(rf"^def {name}\(", source, re.MULTILINE), f"{decisions}: no {test}"


def test_the_map_and_the_sheet_are_given_no_case_file() -> None:
    for function in (case_map, never_sheet):
        given = [p.annotation for p in inspect.signature(function).parameters.values()]
        assert given == [Package, Catalog]


# --- Each kind of line, with its witness (brief, D56) --------------------------------------------

NEVER_WITNESSED: set[str] = set()


def witness(kind: str) -> Callable[[Callable[[], None]], Callable[[], None]]:
    """Mark a test as the witness of the sheet's lines of `kind`: the sheet says the line, and a
    run shows the engine refusing what it says."""

    def marked(test: Callable[[], None]) -> Callable[[], None]:
        NEVER_WITNESSED.add(kind)
        return test

    return marked


def lines_of(definition: Definition, catalog: Catalog = CATALOG) -> list[tuple[str, str]]:
    """The package's own lines, with their kinds."""
    return [(never.kind, never.line) for never in nevers(as_package(definition), catalog)]


@witness("calls only")
def test_a_run_calls_only_what_the_sheet_says() -> None:
    assert ("calls only", "call anything but payments.refund@2 (high risk, it writes)") in (
        lines_of(refund())
    )
    run = run_case(
        refund(),
        file={"order_id": "ord-1", "amount": 50},
        answers=[("review", "approve", "ana", {"approved_amount": 50})],
        people={"ana": ["support"]},
    )
    called = {found for line in run.history for found in re.findall(r"\b[a-z.]+@\d+\b", line)}
    assert called == {"payments.refund@2"}


@witness("changes the world only through")
def test_what_changes_the_world_is_read_from_declared_effects() -> None:
    # The proof is the declaration (brief, D6): each contract's declared effect, never its name.
    case, plans = settling()
    found = dict(lines_of(packed(case, plans)))
    line = found["changes the world only through"]
    for reference in ("orders.lookup@1", "payments.refund@2"):
        changes = CATALOG.lookup(reference).effect in ("write", "notify")
        assert (reference in line) == changes, reference
    assert line == "change the world, by what its contracts declare, but through payments.refund@2"


@witness("input policy")
def test_an_input_policy_line_is_the_runtimes_refusal() -> None:
    before, _, catalog, refused, _ = policy_witness()
    assert (
        "input policy",
        "give payments.refund@2 its order_id or its amount from untrusted data",
    ) in lines_of(before, catalog)
    assert refused
    from_payments = catalog_with(refund_contract(4, refund_input(only_from("payments"))))
    assert ("input policy", "give payments.refund@4 its amount from anything but payments") in (
        lines_of(calling("payments.refund@4"), from_payments)
    )


@witness("who sees")
def test_a_who_sees_line_is_the_view() -> None:
    before, _, _, refused, _ = readers_witness()
    assert ("who sees", "show amount to anyone but support") in lines_of(before)
    assert refused


@witness("sensitive")
def test_a_sensitive_line_is_the_workflow_steps_refusal() -> None:
    before, _, _, refused, _ = sensitive_witness()
    assert ("sensitive", "give national_id to a workflow step (kyc)") in lines_of(before)
    assert refused


@witness("who may not approve")
def test_a_who_may_not_approve_line_is_the_exclusion() -> None:
    before, _, _, refused, _ = exclusions_witness()
    assert ("who may not approve", "let whoever answers review approve pay") in lines_of(before)
    assert refused


@witness("runs only approved")
def test_a_runs_only_approved_line_is_the_wait_for_approval() -> None:
    before, _, _, refused, _ = approval_witness()
    assert ("runs only approved", "run lookup unless one support-lead approves it") in (
        lines_of(before)
    )
    assert refused
    # With a `when`, nothing is said: the step runs unapproved where it is false.
    assert not any(kind == "runs only approved" for kind, _ in lines_of(refund()))


@witness("forgetting")
def test_a_forgetting_line_is_the_requests_refusal() -> None:
    before, _, _, refused, _ = forgetting_witness()
    assert ("forgetting", "forget a closed case's records") in lines_of(before)
    assert refused


def test_every_kind_of_line_has_a_witness() -> None:
    assert NEVER_WITNESSED == set(NEVERS)
