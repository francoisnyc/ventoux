"""Expressions: structured JSON with D3's operators, checked and evaluated fail closed (layer 2).

See docs/layers/02-plan-expressions.md and docs/guides/expressions.md.
"""

import decimal
import json
from decimal import Decimal
from typing import cast

import pytest

from ventoux.core.expressions import (
    Add,
    And,
    Div,
    Expression,
    ExpressionError,
    ExpressionInvalid,
    Gt,
    Mul,
    Not,
    Or,
    Sub,
    Var,
    evaluate,
    parse_expression,
)

NOT_AN_OPERATOR = (
    "`now` is not an operator. The operators are: var, ==, !=, >, >=, <, <=, and, or, !, +, -, *, "
    "/, if, in, cat, string, exists, count, sum, item. Logic that doesn't fit is a compute "
    "activity."
)


def test_an_unknown_operator_is_refused_with_one_message() -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression({"now": []})
    assert str(refused.value) == NOT_AN_OPERATOR


def test_an_unknown_operator_inside_another_is_refused() -> None:
    with pytest.raises(ExpressionInvalid, match="`map` is not an operator"):
        parse_expression({">": [{"map": []}, 0]})


def test_a_field_and_literals_parse() -> None:
    assert parse_expression({"var": "approved_amount"}) == Var(var="approved_amount")
    assert parse_expression(Decimal("0.1")) == Decimal("0.1")
    assert parse_expression(100) == Decimal(100)
    assert parse_expression("approve") == "approve"
    assert parse_expression(True) is True


def test_a_float_is_refused_because_it_has_already_lost_precision() -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(0.1)
    assert str(refused.value) == (
        "0.1 is a binary float, and numbers must be exact decimals: read the JSON with "
        "json.loads(text, parse_float=Decimal)"
    )


def test_null_is_not_a_value() -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(None)
    assert str(refused.value) == "null is not a value in an expression; use exists(field)"


def test_an_object_holds_exactly_one_operator() -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression({"var": "review.outcome", "==": [1, 1]})
    assert str(refused.value) == (
        "an operator is an object with exactly one key, and this one has 2: var, =="
    )


@pytest.mark.parametrize("name", [["approved_amount", 0], "", 7])
def test_var_names_one_field_with_no_default(name: object) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression({"var": name})
    assert str(refused.value) == (
        'var takes the name of one field, like {"var": "approved_amount"}: '
        "no default, and never the whole case file"
    )


def test_a_field_with_no_value_is_an_error_not_false() -> None:
    with pytest.raises(ExpressionError) as stopped:
        evaluate(Var(var="approved_amount"), {"amount": Decimal(250)})
    assert str(stopped.value) == "approved_amount has no value"


def test_an_operator_the_evaluator_does_not_know_is_an_error_not_false() -> None:
    # A raw dict that skipped the parser, like the tracer's `{"now": []}`, which read as false.
    unknown = cast(Expression, {"now": []})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(unknown, {})
    assert str(stopped.value) == "can't evaluate {'now': []}: it isn't a parsed expression"


def test_a_field_reads_its_value_and_a_literal_is_itself() -> None:
    values = {"approved_amount": Decimal("250.00"), "review.outcome": "approve"}
    assert evaluate(Var(var="approved_amount"), values) == Decimal("250.00")
    assert evaluate(Var(var="review.outcome"), values) == "approve"
    assert evaluate(Decimal(100), values) == Decimal(100)
    assert evaluate("approve", values) == "approve"
    assert evaluate(False, values) is False


def test_a_value_an_expression_cannot_read_is_an_error() -> None:
    with pytest.raises(ExpressionError) as stopped:
        evaluate(Var(var="approved_amount"), {"approved_amount": 250.0})
    assert str(stopped.value) == (
        "approved_amount holds 250.0, a float, and an expression reads only decimals, "
        "texts and booleans"
    )


@pytest.mark.parametrize("arguments", [[1], [1, 2, 3], 1])
def test_a_comparison_takes_two_arguments(arguments: object) -> None:
    # JsonLogic reads `{"<": [1, x, 3]}` as "between"; ours refuses it (D3: only stricter).
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression({"<": arguments})
    assert str(refused.value) == "`<` takes a list of 2 arguments"


def test_a_comparison_parses_with_its_arguments_parsed() -> None:
    parsed = parse_expression({">": [{"var": "approved_amount"}, 100]})
    assert parsed == Gt.model_validate({">": [Var(var="approved_amount"), Decimal(100)]})


def test_comparing_a_text_with_a_number_is_an_error() -> None:
    over_100 = parse_expression({">": [{"var": "approved_amount"}, 100]})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(over_100, {"approved_amount": "250"})
    assert str(stopped.value) == "`>` compares numbers, and it was given a string: '250'"


@pytest.mark.parametrize(
    ("operator", "left", "right", "expected"),
    [
        (">", 250, 100, True),
        (">", 100, 100, False),
        (">=", 100, 100, True),
        ("<", 99, 100, True),
        ("<=", 101, 100, False),
        ("==", Decimal("250.00"), 250, True),
        ("==", "approve", "approve", True),
        ("==", "approve", "reject", False),
        ("!=", "approve", "reject", True),
        ("==", True, False, False),
    ],
)
def test_comparisons(operator: str, left: object, right: object, expected: bool) -> None:
    assert evaluate(parse_expression({operator: [left, right]}), {}) is expected


@pytest.mark.parametrize(
    ("left", "right", "message"),
    [
        (True, 1, "`==` compares values of the same type, and it was given a boolean and a number"),
        (1, "1", "`==` compares values of the same type, and it was given a number and a string"),
    ],
)
def test_equality_never_coerces(left: object, right: object, message: str) -> None:
    with pytest.raises(ExpressionError) as stopped:
        evaluate(parse_expression({"==": [left, right]}), {})
    assert str(stopped.value) == message


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"and": [True]}, "`and` takes a list of 2 or more arguments"),
        ({"or": True}, "`or` takes a list of 2 or more arguments"),
        ({"!": True}, '`!` takes a list of 1 argument, like {"!": [x]}'),
        ({"!": [True, False]}, '`!` takes a list of 1 argument, like {"!": [x]}'),
    ],
)
def test_logic_operators_take_their_number_of_arguments(data: object, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(data)
    assert str(refused.value) == message


def test_logic_operators_parse_with_their_arguments_parsed() -> None:
    approved = {"==": [{"var": "review.outcome"}, "approve"]}
    parsed_approved = parse_expression(approved)
    urgent = Var(var="urgent")
    assert parse_expression({"and": [approved, {"var": "urgent"}]}) == And.model_validate(
        {"and": [parsed_approved, urgent]}
    )
    assert parse_expression({"or": [approved, {"var": "urgent"}, True]}) == Or.model_validate(
        {"or": [parsed_approved, urgent, True]}
    )
    assert parse_expression({"!": [{"var": "urgent"}]}) == Not.model_validate({"!": [urgent]})


@pytest.mark.parametrize(
    "data",
    [
        {"and": [False, {">": [{"var": "approved_amount"}, 100]}]},
        {"or": [True, {">": [{"var": "approved_amount"}, 100]}]},
    ],
)
def test_and_or_evaluate_every_part_so_an_error_is_never_hidden(data: object) -> None:
    # The first part already decides the answer; the missing amount must still stop the step.
    with pytest.raises(ExpressionError) as stopped:
        evaluate(parse_expression(data), {})
    assert str(stopped.value) == "approved_amount has no value"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"and": [True, 1]}, "`and` combines booleans, and it was given a number: 1"),
        ({"or": [False, "yes"]}, "`or` combines booleans, and it was given a string: 'yes'"),
        ({"!": [0]}, "`!` takes a boolean, and it was given a number: 0"),
    ],
)
def test_nothing_is_truthy(data: object, message: str) -> None:
    # JsonLogic reads 1 and "yes" as true and 0 as false; a condition here is true or false (D3).
    with pytest.raises(ExpressionError) as stopped:
        evaluate(parse_expression(data), {})
    assert str(stopped.value) == message


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"and": [True, True]}, True),
        ({"and": [True, True, False]}, False),
        ({"or": [False, False, True]}, True),
        ({"or": [False, False]}, False),
        ({"!": [False]}, True),
        ({"!": [{"and": [True, {"==": [{"var": "review.outcome"}, "approve"]}]}]}, False),
    ],
)
def test_and_or_not(data: object, expected: bool) -> None:
    assert evaluate(parse_expression(data), {"review.outcome": "approve"}) is expected


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"+": [1]}, "`+` takes a list of 2 or more arguments"),
        ({"*": 2}, "`*` takes a list of 2 or more arguments"),
        ({"-": [5]}, "`-` takes a list of 2 arguments"),
        ({"/": [1, 2, 3]}, "`/` takes a list of 2 arguments"),
    ],
)
def test_arithmetic_takes_its_number_of_arguments(data: object, message: str) -> None:
    # JsonLogic reads `{"-": [5]}` as -5; ours refuses it (D3: only stricter). Write 0 - 5.
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(data)
    assert str(refused.value) == message


def test_arithmetic_parses_with_its_arguments_parsed() -> None:
    amount = Var(var="amount")
    assert parse_expression({"+": [{"var": "amount"}, 1, 2]}) == Add.model_validate(
        {"+": [amount, Decimal(1), Decimal(2)]}
    )
    assert parse_expression({"-": [{"var": "amount"}, 1]}) == Sub.model_validate(
        {"-": [amount, Decimal(1)]}
    )
    assert parse_expression({"*": [{"var": "amount"}, 2]}) == Mul.model_validate(
        {"*": [amount, Decimal(2)]}
    )
    assert parse_expression({"/": [{"var": "amount"}, 2]}) == Div.model_validate(
        {"/": [amount, Decimal(2)]}
    )


def test_division_by_zero_is_an_error() -> None:
    per_item = parse_expression({"/": [{"var": "amount"}, {"var": "items"}]})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(per_item, {"amount": Decimal(250), "items": Decimal(0)})
    assert str(stopped.value) == "division by zero: 250 / 0"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"+": [1, "2"]}, "`+` adds numbers, and it was given a string: '2'"),
        ({"-": [True, 1]}, "`-` subtracts numbers, and it was given a boolean: true"),
        ({"*": [2, "3"]}, "`*` multiplies numbers, and it was given a string: '3'"),
        ({"/": ["6", 2]}, "`/` divides numbers, and it was given a string: '6'"),
    ],
)
def test_arithmetic_never_coerces(data: object, message: str) -> None:
    # JsonLogic reads `{"+": [1, "2"]}` as 3; ours refuses a text (D3).
    with pytest.raises(ExpressionError) as stopped:
        evaluate(parse_expression(data), {})
    assert str(stopped.value) == message


def test_numbers_are_exact_decimals() -> None:
    # As a definition is read: JSON numbers become decimals, never binary floats.
    data = json.loads('{"==": [{"+": [0.1, 0.2]}, 0.3]}', parse_float=Decimal)
    assert evaluate(parse_expression(data), {}) is True


def test_a_division_keeps_34_significant_digits_whatever_the_global_context() -> None:
    third = parse_expression({"/": [1, 3]})
    expected = Decimal("0." + "3" * 34)
    assert evaluate(third, {}) == expected
    # The process-wide context is someone else's setting; it never decides a result (D3).
    with decimal.localcontext(prec=5, rounding=decimal.ROUND_DOWN):
        assert evaluate(third, {}) == expected


def test_arithmetic_rounds_half_to_even() -> None:
    # 35 significant digits ending in 5: decimal128 keeps 34, rounding to the even neighbour.
    ends_in_5 = Decimal("1" + "0" * 33 + "5")
    assert evaluate(parse_expression({"+": [ends_in_5, 0]}), {}) == Decimal("1" + "0" * 34)
    ends_in_15 = Decimal("1" + "0" * 32 + "15")
    assert evaluate(parse_expression({"+": [ends_in_15, 0]}), {}) == Decimal("1" + "0" * 32 + "20")


@pytest.mark.parametrize("special", [Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN")])
def test_a_number_is_finite(special: Decimal) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(special)
    assert str(refused.value) == f"{special} is not a number an expression can use"
    with pytest.raises(ExpressionError) as stopped:
        evaluate(Var(var="amount"), {"amount": special})
    assert (
        str(stopped.value) == f"amount holds {special}, which is not a number an expression can use"
    )


def test_a_result_too_large_for_decimal128_is_an_error() -> None:
    huge = parse_expression({"*": [Decimal("1E+6000"), Decimal("1E+6000")]})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(huge, {})
    assert str(stopped.value) == "`*` gives a number too large for an expression (decimal128)"
