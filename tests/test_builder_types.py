"""Build time and runtime, told apart by type: what the type checker refuses in a builder file
(layer 14a, choice 3).

A runtime expression is an `Expr`; a plain Python value where one is required fails mypy before
anything runs. These tests run mypy on small builder files, all in one call, as a developer's
editor or CI would (brief, D58). See docs/layers/14-builder.md.
"""

from pathlib import Path

import pytest
from mypy import api

# Each snippet is a builder file, checked as written; its errors are what mypy says about it.
SNIPPETS = {
    "plain_when": """
from ventoux import Case, Field

refund = Case("refund", title="Customer refund")
amount = refund.field("amount", Field.number(), title="Amount requested")
pay = refund.activity("pay", "payments.refund@2", title="Refund the customer", when=True)
""",
    "plain_input": """
from ventoux import Case

refund = Case("refund", title="Customer refund")
pay = refund.activity("pay", "payments.refund@2", title="Refund the customer", inputs={"amount": 250})
""",
    "text_beside_a_number": """
from ventoux import Approval, Case, Field

refund = Case("refund", title="Customer refund")
amount = refund.field("amount", Field.number(), title="Amount requested")
check = Approval(when=amount > "100", roles=["support-lead"], reason="Large refunds")
""",
    "literal_input": """
from ventoux import Case, literal

refund = Case("refund", title="Customer refund")
pay = refund.activity(
    "pay", "payments.refund@2", title="Refund the customer", inputs={"amount": literal(250)}
)
""",
    "outcome_beside_a_number": """
from ventoux import Case, Outcome

refund = Case("refund", title="Customer refund")
review = refund.task("review", title="Review", roles=["support"], outcomes={"ok": Outcome("Fine")})
pay = refund.activity("pay", "payments.refund@2", title="Refund", when=review.outcome == 5)
""",
    "kinds_compared_as_written": """
from ventoux import Case, Field, Outcome

refund = Case("refund", title="Customer refund")
amount = refund.field("amount", Field.number(), title="Amount")
note = refund.field("note", Field.string(), title="Note")
urgent = refund.field("urgent", Field.boolean(), title="Urgent")
order_id = refund.reference("order_id", system="orders", title="Order")
review = refund.task("review", title="Review", roles=["support"], outcomes={"ok": Outcome("Fine")})
for condition in (
    amount == 5, note == "x", urgent == True, review.outcome == "ok", order_id == order_id
):
    refund.activity(f"pay_{len(refund.steps)}", "payments.refund@2", title="Pay", when=condition)
""",
    "text_beside_a_reference": """
from ventoux import Case

refund = Case("refund", title="Customer refund")
order_id = refund.reference("order_id", system="orders", title="Order")
pay = refund.activity("pay", "payments.refund@2", title="Refund", when=order_id == "ord-1")
""",
    "step_where_a_milestone_is_required": """
from ventoux import Case

refund = Case("refund", title="Customer refund")
pay = refund.activity("pay", "payments.refund@2", title="Refund")
call = refund.activity("call", "letters.draft@2", title="Write", reaches=[pay])
""",
    "sla_since_first_start": """
from ventoux import Case, Outcome, Then

claim = Case("claim", title="Claim")
assess = claim.task("assess", title="Assess", roles=["adjuster"], outcomes={"ok": Outcome("Fine")})
escalate = claim.activity("escalate", "letters.draft@2", title="Escalate")
claim.sla(
    "late", title="Late", step=assess, within="5d", since="first_start", then=Then(start=[escalate])
)
""",
    "timer_on_a_timer": """
from ventoux import Case, Outcome, Then, after

claim = Case("claim", title="Claim")
assess = claim.task("assess", title="Assess", roles=["adjuster"], outcomes={"ok": Outcome("Fine")})
paid = claim.milestone("paid", title="Paid")
claim.rule(
    "late",
    title="Late",
    on=after("2d", since=after("1d", since=assess.started)),
    then=Then(reach=[paid]),
)
""",
    "number_as_a_transition_condition": """
from ventoux import Field, Plan, Transition

plan = Plan("refund-order", 1, title="Refund an order")
amount = plan.field("amount", Field.number())
plan.activity("pay", "payments.refund@2", on={"done": [Transition("paid", when=amount)]})
""",
    "quickstart": (
        Path(__file__).parent.parent / "examples/quickstart/cases/refund.py"
    ).read_text(),
}


@pytest.fixture(scope="module")
def type_errors(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[str]]:
    """What mypy says about each snippet, in strict mode, by the snippet's name."""
    folder = tmp_path_factory.mktemp("snippets")
    for name, source in SNIPPETS.items():
        (folder / f"{name}.py").write_text(source)
    said, _, _ = api.run(
        ["--strict", "--no-error-summary", "--cache-dir", str(folder / ".mypy_cache")]
        + [str(folder / f"{name}.py") for name in SNIPPETS]
    )
    errors: dict[str, list[str]] = {name: [] for name in SNIPPETS}
    for line in said.splitlines():
        name = Path(line.split(":")[0]).stem
        if name in errors and ": error:" in line:
            errors[name].append(line.split(": error: ")[1])
    return errors


def test_a_plain_value_where_a_runtime_expression_is_required_fails_the_type_check(
    type_errors: dict[str, list[str]],
) -> None:
    # The curriculum's negative test: `when=True` is a build-time value, and `when` is decided by
    # each case at runtime (brief, D58).
    assert any('"when"' in error and '"bool"' in error for error in type_errors["plain_when"]), (
        type_errors["plain_when"]
    )


def test_a_plain_value_as_an_input_fails_the_type_check(type_errors: dict[str, list[str]]) -> None:
    # An input is read from each case; a constant is said so, with `literal(250)` (choice 3).
    assert any('"int"' in error and "Expr" in error for error in type_errors["plain_input"]), (
        type_errors["plain_input"]
    )
    assert type_errors["literal_input"] == []


def test_a_text_beside_a_number_fails_the_type_check(type_errors: dict[str, list[str]]) -> None:
    assert any('"str"' in error for error in type_errors["text_beside_a_number"]), type_errors[
        "text_beside_a_number"
    ]


def test_the_quickstarts_builder_file_type_checks(type_errors: dict[str, list[str]]) -> None:
    # So each refusal above comes from its own line, never from the builder refusing everything.
    assert type_errors["quickstart"] == []


def test_equality_is_typed_by_what_the_expression_holds(type_errors: dict[str, list[str]]) -> None:
    # `==` compares the same kind, or an outcome with its name (choice 19): an outcome is never a
    # number, and a reference compares only with a reference, as the expression check says. A
    # mismatched `==` is Python's own to mypy, a `bool`, so it fails where a condition is required.
    for snippet in ("outcome_beside_a_number", "text_beside_a_reference"):
        assert any('"when"' in error and '"bool"' in error for error in type_errors[snippet]), (
            type_errors[snippet]
        )
    assert type_errors["kinds_compared_as_written"] == []


def test_a_step_where_a_milestone_is_required_fails_the_type_check(
    type_errors: dict[str, list[str]],
) -> None:
    errors = type_errors["step_where_a_milestone_is_required"]
    assert any('"Step"; expected "Milestone"' in error for error in errors), errors


def test_since_first_start_is_not_offered(type_errors: dict[str, list[str]]) -> None:
    # An sla measures each run from its own start; `since=first_start` isn't offered (brief, D46).
    errors = type_errors["sla_since_first_start"]
    assert any('"since"' in error for error in errors), errors


def test_a_timer_is_never_set_on_a_timer(type_errors: dict[str, list[str]]) -> None:
    # A timer is set on one of the five moments, never another timer (brief, D44).
    errors = type_errors["timer_on_a_timer"]
    assert any('"since"' in error and '"Timer"' in error for error in errors), errors


def test_a_transitions_condition_is_a_condition(type_errors: dict[str, list[str]]) -> None:
    errors = type_errors["number_as_a_transition_condition"]
    assert any('"when"' in error and '"NumberExpr"' in error for error in errors), errors
