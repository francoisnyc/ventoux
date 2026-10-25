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
