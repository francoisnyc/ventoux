"""The Python builder: what it writes, and what it refuses while the file runs (layer 14a).

The builder writes data; these tests read the data it writes, through `written` and
`run_case`, never its objects' insides. See docs/layers/14-builder.md.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ventoux import Case, Field, Outcome, and_, literal, not_, or_
from ventoux.case.definition import parse_case
from ventoux.case.releases import behaviour_digest
from ventoux.testing import load_definition
from ventoux.tooling.builder.expressions import BuildTimeDecision
from ventoux.tooling.builder.written import NotWritable, written


def test_a_runtime_value_asked_for_a_build_time_decision_is_refused() -> None:
    refund = Case("refund", title="Customer refund")
    amount = refund.field("amount", Field.number(), title="Amount requested")
    with pytest.raises(BuildTimeDecision, match=r"amount > 100 is decided by each case"):
        if amount > 100:
            pass
    with pytest.raises(BuildTimeDecision):
        # Python asks the first comparison for a bool, to decide whether to read the second.
        0 < amount < 100  # noqa: B015


def test_a_comparison_writes_d20s_json() -> None:
    refund = Case("refund", title="Customer refund")
    amount = refund.field("amount", Field.number(), title="Amount requested")
    assert (amount > 100).data == {">": [{"var": "amount"}, 100]}
    assert (100 < amount).data == {">": [{"var": "amount"}, 100]}  # Python turns it round
    assert (amount * Decimal("0.5") + 1).data == {
        "+": [{"*": [{"var": "amount"}, Decimal("0.5")]}, 1]
    }
    assert literal(250).data == 250


def test_a_float_or_a_truth_value_is_refused_as_a_number() -> None:
    refund = Case("refund", title="Customer refund")
    amount = refund.field("amount", Field.number(), title="Amount requested")
    with pytest.raises(TypeError, match=r"binary float: write Decimal\(\"0.1\"\)"):
        amount > 0.1  # type: ignore[operator]  # noqa: B015
    with pytest.raises(TypeError, match="not a number"):
        literal(Decimal("NaN"))
    with pytest.raises(TypeError, match="True is not a number"):
        amount + True


ROOT = Path(__file__).parent.parent
BUILT = ROOT / "examples" / "quickstart" / "build" / "refund" / "case.json"


def test_the_quickstarts_refund_reads_as_the_hand_written_one() -> None:
    # The same definition, so the same behaviour digest: the two can't drift apart in behaviour
    # (choice 15). `examples/refund/refund.json` stays hand-written: JSON is a front door too.
    from cases.refund import refund

    built = json.loads(written(refund), parse_float=Decimal)
    by_hand = load_definition(ROOT / "examples" / "refund" / "refund.json")
    assert built == by_hand
    assert behaviour_digest(parse_case(built), {}) == behaviour_digest(parse_case(by_hand), {})


def test_the_written_json_is_the_committed_one_byte_for_byte() -> None:
    from cases.refund import refund

    assert written(refund) == BUILT.read_text()
    assert written(refund) == written(refund)


def test_the_layout_is_the_standard_librarys() -> None:
    from cases.refund import refund

    data = json.loads(written(refund))  # no decimals in it, so `json.dumps` can write it
    assert written(refund) == json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def test_a_number_that_would_read_back_as_another_is_refused() -> None:
    refund = Case("refund", title="Customer refund")
    amount = refund.field("amount", Field.number(), title="Amount requested")
    refund.activity("pay", "payments.refund@2", title="Refund", when=amount > Decimal("1E+2"))
    with pytest.raises(NotWritable, match=r"1E\+2 reads back as 100"):
        written(refund)


def test_two_entries_of_one_name_are_refused() -> None:
    # A dict would keep the second and drop the first without a word.
    refund = Case("refund", title="Customer refund")
    refund.field("amount", Field.number(), title="Amount requested")
    with pytest.raises(ValueError, match="refund already has a field named amount"):
        refund.field("amount", Field.number(), title="Amount, again")


def test_and_or_and_not_are_functions_writing_d20s_operators() -> None:
    refund = Case("refund", title="Customer refund")
    amount = refund.field("amount", Field.number(), title="Amount requested")
    assert and_(amount > 1, amount < 9).data == {
        "and": [{">": [{"var": "amount"}, 1]}, {"<": [{"var": "amount"}, 9]}]
    }
    assert or_(amount > 1, amount == 5).data == {
        "or": [{">": [{"var": "amount"}, 1]}, {"==": [{"var": "amount"}, 5]}]
    }
    assert not_(amount > 1).data == {"!": [{">": [{"var": "amount"}, 1]}]}


def test_a_plain_value_the_type_checker_missed_is_refused_when_the_file_runs() -> None:
    # The type check comes first; a file run without it still can't write a constant where each
    # case decides (fail closed).
    refund = Case("refund", title="Customer refund")
    with pytest.raises(TypeError, match="True is a Python value where a runtime expression"):
        refund.activity("pay", "payments.refund@2", title="Refund", when=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="250 is a Python value"):
        refund.activity("pay", "payments.refund@2", title="Refund", inputs={"amount": 250})  # type: ignore[dict-item]


def test_a_form_sets_fields_only() -> None:
    refund = Case("refund", title="Customer refund")
    amount = refund.field("amount", Field.number(), title="Amount requested")
    review = refund.task(
        "review", title="Review", roles=["support"], outcomes={"ok": Outcome("Fine")}
    )
    with pytest.raises(TypeError, match="not a field of the case file"):
        refund.task(
            "check",
            title="Check",
            roles=["support"],
            outcomes={"ok": Outcome("Fine", sets=[amount + 1, review.outcome])},
        )
