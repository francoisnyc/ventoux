"""Expressions: structured JSON with a fixed list of operators, checked and evaluated fail closed.

See docs/layers/02-plan-expressions.md and docs/guides/expressions.md.
"""

import decimal
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from ventoux.core.expressions import (
    Add,
    And,
    BooleanType,
    Cat,
    Count,
    DateType,
    Div,
    Eq,
    Exists,
    Expression,
    ExpressionError,
    ExpressionInvalid,
    FieldType,
    Gt,
    If,
    In,
    Item,
    ListType,
    Mul,
    Not,
    NumberType,
    OptionType,
    Or,
    OutcomeType,
    ReferenceType,
    String,
    StringType,
    Sub,
    Sum,
    Var,
    check,
    evaluate,
    parse_expression,
    render,
)

NOT_AN_OPERATOR = (
    "`now` is not an operator. The operators are: var, ==, !=, >, >=, <, <=, and, or, !, +, -, *, "
    "/, if, in, cat, string, exists, count, sum, item, date. Logic that doesn't fit is a compute "
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
        "approved_amount holds a binary float, and an expression reads only decimals, "
        "texts, booleans and dates"
    )


@pytest.mark.parametrize("arguments", [[1], [1, 2, 3], 1])
def test_a_comparison_takes_two_arguments(arguments: object) -> None:
    # JsonLogic reads `{"<": [1, x, 3]}` as "between"; ours refuses it: ours is only stricter.
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
    assert str(stopped.value) == (
        "`>` compares two numbers or two dates, and it was given a string"
    )


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
        ({"and": [True, 1]}, "`and` combines booleans, and it was given a number"),
        ({"or": [False, "yes"]}, "`or` combines booleans, and it was given a string"),
        ({"!": [0]}, "`!` takes a boolean, and it was given a number"),
    ],
)
def test_nothing_is_truthy(data: object, message: str) -> None:
    # JsonLogic reads 1 and "yes" as true and 0 as false; a condition here is true or false.
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
    # JsonLogic reads `{"-": [5]}` as -5; ours refuses it. Write 0 - 5.
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
    # The fields tell a developer where to look; the values tell an operator what happened.
    assert str(stopped.value) == "division by zero in amount / items"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"+": [1, "2"]}, "`+` adds numbers, and it was given a string"),
        ({"-": [True, 1]}, "`-` subtracts numbers, and it was given a boolean"),
        ({"*": [2, "3"]}, "`*` multiplies numbers, and it was given a string"),
        ({"/": ["6", 2]}, "`/` divides numbers, and it was given a string"),
    ],
)
def test_arithmetic_never_coerces(data: object, message: str) -> None:
    # JsonLogic reads `{"+": [1, "2"]}` as 3; ours refuses a text.
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
    # The process-wide context is someone else's setting; it never decides a result.
    with decimal.localcontext(prec=5, rounding=decimal.ROUND_DOWN):
        assert evaluate(third, {}) == expected


def test_arithmetic_rounds_half_to_even() -> None:
    # A sum that needs 35 digits, from literals that fit: decimal128 keeps 34, rounding a final 5
    # to the even neighbour. The numbers are written out: computing them here would use Python's
    # own 28-digit context, the very thing this test guards against.
    ends_in_0 = Decimal("1" + "0" * 33)
    ends_in_1 = Decimal("1" + "0" * 32 + "1")
    ends_in_2 = Decimal("1" + "0" * 32 + "2")
    assert evaluate(parse_expression({"+": [ends_in_0, Decimal("0.5")]}), {}) == ends_in_0
    assert evaluate(parse_expression({"+": [ends_in_1, Decimal("0.5")]}), {}) == ends_in_2


@pytest.mark.parametrize("special", [Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN")])
def test_a_number_is_finite(special: Decimal) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(special)
    assert str(refused.value) == f"{special} is not a number an expression can use"
    with pytest.raises(ExpressionError) as stopped:
        evaluate(Var(var="amount"), {"amount": special})
    # The kind, never the value: a message may reach people who may not see it (brief, D30).
    assert (
        str(stopped.value)
        == "amount holds a number that isn't finite, which an expression can't use"
    )


def test_a_result_too_large_for_decimal128_is_an_error() -> None:
    huge = parse_expression({"*": [Decimal("1E+6000"), Decimal("1E+6000")]})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(huge, {})
    assert str(stopped.value) == "`*` gives a number too large for an expression (decimal128)"


IN_LIST = '`in` takes a value and a list of values, like {"in": [x, ["approve", "escalate"]]}'


@pytest.mark.parametrize(
    ("data", "message"),
    [
        # JsonLogic chains `if` (`[c1, a, c2, b, else]`); ours takes exactly three.
        ({"if": [True, 1, False, 2, 3]}, "`if` takes a list of 3 arguments"),
        ({"if": [True, 1]}, "`if` takes a list of 3 arguments"),
        # JsonLogic's `in` also searches a text ("app" in "approve"); ours never does.
        ({"in": ["app", "approve"]}, IN_LIST + "; it never searches a text"),
        ({"in": ["approve"]}, IN_LIST),
        ({"in": ["approve", []]}, "`in` needs at least one value in its list"),
        (
            {"in": [1, ["a", 1]]},
            "`in`'s list holds values of one type, and this one mixes string and number",
        ),
        ({"in": ["a", [{"var": "x"}]]}, IN_LIST + "; the list holds literal values"),
        ({"cat": []}, "`cat` takes a list of 1 or more arguments"),
        ({"string": 5}, "`string` takes a list of 1 argument"),
        (
            {"exists": ["approved_amount"]},
            'exists takes the name of one field, like {"exists": "approved_amount"}',
        ),
        ({"exists": ""}, 'exists takes the name of one field, like {"exists": "approved_amount"}'),
    ],
)
def test_if_in_cat_string_exists_take_their_shape(data: object, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(data)
    assert str(refused.value) == message


def test_if_in_cat_string_exists_parse() -> None:
    outcome = Var(var="review.outcome")
    approved = {"==": [{"var": "review.outcome"}, "approve"]}
    assert parse_expression({"if": [approved, {"var": "approved_amount"}, 0]}) == If.model_validate(
        {"if": [parse_expression(approved), Var(var="approved_amount"), Decimal(0)]}
    )
    assert parse_expression({"in": [{"var": "review.outcome"}, ["approve", "escalate"]]}) == (
        In.model_validate({"in": [outcome, ["approve", "escalate"]]})
    )
    assert parse_expression({"cat": ["Refund of ", {"string": [{"var": "amount"}]}]}) == (
        Cat.model_validate(
            {"cat": ["Refund of ", String.model_validate({"string": [Var(var="amount")]})]}
        )
    )
    assert parse_expression({"exists": "approved_amount"}) == Exists(exists="approved_amount")


def test_an_if_condition_is_a_boolean() -> None:
    with pytest.raises(ExpressionError) as stopped:
        evaluate(parse_expression({"if": [1, "yes", "no"]}), {})
    assert str(stopped.value) == "`if` takes a boolean, and it was given a number"


def test_exists_says_whether_a_field_has_a_value() -> None:
    values = {"approved_amount": Decimal(250), "reason": None}
    assert evaluate(parse_expression({"exists": "approved_amount"}), values) is True
    assert evaluate(parse_expression({"exists": "amount"}), values) is False
    # A JSON null is no value either, for `exists` and for `var`.
    assert evaluate(parse_expression({"exists": "reason"}), values) is False
    with pytest.raises(ExpressionError) as stopped:
        evaluate(parse_expression({"var": "reason"}), values)
    assert str(stopped.value) == "reason has no value"


def test_if_evaluates_only_the_branch_its_condition_chooses() -> None:
    # Unlike `and` and `or`: the condition says which branch means something, so a guard on a
    # missing value works. The type check (slice 8) still checks both branches before anything runs.
    guarded = parse_expression(
        {"if": [{"exists": "approved_amount"}, {"var": "approved_amount"}, 0]}
    )
    assert evaluate(guarded, {}) == Decimal(0)
    assert evaluate(guarded, {"approved_amount": Decimal(250)}) == Decimal(250)


def test_in_looks_for_a_value_of_the_list_type() -> None:
    with pytest.raises(ExpressionError) as stopped:
        evaluate(
            parse_expression({"in": [{"var": "review.outcome"}, ["approve", "escalate"]]}),
            {"review.outcome": Decimal(1)},
        )
    assert str(stopped.value) == "`in` looks for a number in a list of strings"


def test_in() -> None:
    escalated = parse_expression({"in": [{"var": "review.outcome"}, ["approve", "escalate"]]})
    assert evaluate(escalated, {"review.outcome": "escalate"}) is True
    assert evaluate(escalated, {"review.outcome": "reject"}) is False
    assert evaluate(parse_expression({"in": [Decimal("2.0"), [1, 2]]}), {}) is True


def test_cat_joins_texts_only() -> None:
    # JsonLogic's `cat` turns 250 into "250"; ours asks for it to be said with `string`.
    with pytest.raises(ExpressionError) as stopped:
        evaluate(
            parse_expression({"cat": ["Refund of ", {"var": "amount"}]}), {"amount": Decimal(250)}
        )
    assert str(stopped.value) == (
        "`cat` joins texts, and it was given a number; write string(…) to turn it into text"
    )


def test_string_writes_a_value_as_text() -> None:
    values = {"approved_amount": Decimal("250.00"), "urgent": True, "order_id": "ORD-7"}
    letter = parse_expression(
        {
            "cat": [
                "Refund of ",
                {"string": [{"var": "approved_amount"}]},
                " for ",
                {"var": "order_id"},
            ]
        }
    )
    assert evaluate(letter, values) == "Refund of 250.00 for ORD-7"
    assert evaluate(parse_expression({"string": [{"var": "urgent"}]}), values) == "true"
    assert evaluate(parse_expression({"string": [{"var": "order_id"}]}), values) == "ORD-7"


ITEM_OUTSIDE = (
    "item reads a field of the current element, so it is only allowed inside count and sum"
)


@pytest.mark.parametrize("data", [{"item": "amount"}, {">": [{"item": "amount"}, 100]}])
def test_item_is_refused_outside_count_and_sum(data: object) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(data)
    assert str(refused.value) == ITEM_OUTSIDE


COUNT_SHAPE = '`count` takes {"over": {"var": "items"}, "where": …}, with "where" optional'
SUM_SHAPE = '`sum` takes {"over": {"var": "items"}, "where": …, "value": …}, with "where" optional'
HIGH = {"==": [{"item": "risk"}, "high"]}


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"count": [{"var": "items"}]}, COUNT_SHAPE),
        ({"count": {"over": "items"}}, COUNT_SHAPE),
        ({"count": {"over": {"var": "items"}, "value": {"item": "amount"}}}, COUNT_SHAPE),
        ({"count": {"over": {"var": "items"}, "map": []}}, COUNT_SHAPE),
        ({"sum": {"over": {"var": "items"}, "where": HIGH}}, SUM_SHAPE),
        ({"sum": {"over": {"cat": ["a"]}, "value": {"item": "amount"}}}, SUM_SHAPE),
    ],
)
def test_count_and_sum_take_their_shape(data: object, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(data)
    assert str(refused.value) == message


def test_count_and_sum_parse_with_item_inside() -> None:
    items = Var(var="items")
    high = Eq.model_validate({"==": [Item(item="risk"), "high"]})
    assert parse_expression({"count": {"over": {"var": "items"}, "where": HIGH}}) == (
        Count.model_validate({"count": {"over": items, "where": high}})
    )
    assert parse_expression({"count": {"over": {"var": "items"}}}) == (
        Count.model_validate({"count": {"over": items}})
    )
    total = {"sum": {"over": {"var": "items"}, "where": HIGH, "value": {"item": "amount"}}}
    assert parse_expression(total) == Sum.model_validate(
        {"sum": {"over": items, "where": high, "value": Item(item="amount")}}
    )


@pytest.mark.parametrize("name", ["", ["amount", 0]])
def test_item_names_one_field(name: object) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(
            {"count": {"over": {"var": "items"}, "where": {"==": [{"item": name}, 1]}}}
        )
    assert str(refused.value) == 'item takes the name of one field, like {"item": "amount"}'


@pytest.mark.parametrize(
    ("held", "message"),
    [
        (None, "items has no value"),
        (Decimal(3), "items holds a number, and count reads a list of records"),
        ("items", "items holds a string, and count reads a list of records"),
        ([Decimal(3)], "items holds a list, and count reads a list of records"),
    ],
)
def test_count_reads_a_list_of_records(held: object, message: str) -> None:
    high_risk = parse_expression({"count": {"over": {"var": "items"}, "where": HIGH}})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(high_risk, {"items": held})
    assert str(stopped.value) == message


def test_an_element_missing_a_field_is_an_error() -> None:
    items = [{"risk": "high", "amount": Decimal(10)}, {"amount": Decimal(20)}]
    high_risk = parse_expression({"count": {"over": {"var": "items"}, "where": HIGH}})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(high_risk, {"items": items})
    assert str(stopped.value) == "item.risk has no value (element 2 of items)"


def test_sum_adds_numbers_only() -> None:
    items = [{"risk": "high", "amount": "10"}]
    total = parse_expression({"sum": {"over": {"var": "items"}, "value": {"item": "amount"}}})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(total, {"items": items})
    assert str(stopped.value) == "`sum` adds numbers, and it was given a string"


def test_where_is_a_condition() -> None:
    items = [{"risk": "high", "amount": Decimal(10)}]
    truthy = parse_expression({"count": {"over": {"var": "items"}, "where": {"item": "risk"}}})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(truthy, {"items": items})
    assert str(stopped.value) == "`where` takes a boolean, and it was given a string"


ITEMS = [
    {"risk": "high", "amount": Decimal("6000.50")},
    {"risk": "low", "amount": Decimal(900)},
    {"risk": "high", "amount": Decimal("4000.25")},
]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"count": {"over": {"var": "items"}}}, Decimal(3)),
        ({"count": {"over": {"var": "items"}, "where": HIGH}}, Decimal(2)),
        ({"sum": {"over": {"var": "items"}, "value": {"item": "amount"}}}, Decimal("10900.75")),
        (
            {"sum": {"over": {"var": "items"}, "where": HIGH, "value": {"item": "amount"}}},
            Decimal("10000.75"),
        ),
        # Learning question 7: are the high-risk items worth more than 10,000 in total?
        (
            {
                ">": [
                    {"sum": {"over": {"var": "items"}, "where": HIGH, "value": {"item": "amount"}}},
                    10000,
                ]
            },
            True,
        ),
        ({"count": {"over": {"var": "none"}}}, Decimal(0)),
        ({"sum": {"over": {"var": "none"}, "value": {"item": "amount"}}}, Decimal(0)),
    ],
)
def test_count_and_sum(data: object, expected: object) -> None:
    assert evaluate(parse_expression(data), {"items": ITEMS, "none": []}) == expected


def test_a_list_is_not_an_expression() -> None:
    # A list literal is allowed only as `in`'s second argument.
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(["approve", "escalate"])
    assert str(refused.value) == "not an expression: ['approve', 'escalate']"


# The refund case's fields, as the type check sees them (slice 8).
REFUND: dict[str, FieldType] = {
    "amount": NumberType(),
    "approved_amount": NumberType(),
    "urgent": BooleanType(),
    "note": StringType(),
    "order_id": ReferenceType(system="orders"),
    "review.outcome": OutcomeType(outcomes=("approve", "reject")),
    "items": ListType(fields={"risk": StringType(), "amount": NumberType()}),
    "incident_date": DateType(),  # the guide's dates (brief, D66)
    "branch": OptionType(system="branches"),  # the guide's option (brief, D67)
}


def test_a_misspelled_outcome_is_rejected_before_anything_runs() -> None:
    misspelled = parse_expression({"==": [{"var": "review.outcome"}, "aprove"]})
    with pytest.raises(ExpressionInvalid) as refused:
        check(misspelled, REFUND)
    assert str(refused.value) == (
        '==[1]: review.outcome has no outcome "aprove"; its outcomes are approve, reject'
    )


def test_an_undeclared_field_is_rejected() -> None:
    misspelled = parse_expression({">": [{"var": "aproved_amount"}, 100]})
    with pytest.raises(ExpressionInvalid) as refused:
        check(misspelled, REFUND)
    assert str(refused.value) == ">[0]: aproved_amount is not a declared field"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {">": [{"var": "approved_amount"}, "100"]},
            ">[1]: `>` compares two numbers or two dates, and this is a string",
        ),
        (
            {"==": [{"var": "approved_amount"}, "100"]},
            "==[1]: `==` compares values of the same type, and this is a string, not a number",
        ),
        (
            {"!=": [{"var": "urgent"}, {"var": "note"}]},
            "!=[1]: `!=` compares values of the same type, and this is a string, not a boolean",
        ),
    ],
)
def test_a_text_compared_with_a_number_is_rejected(data: object, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        check(parse_expression(data), REFUND)
    assert str(refused.value) == message


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"if": [{"var": "urgent"}, {"var": "approved_amount"}, "none"]},
            "if[2]: `if`'s branches give the same type, and this is a string, not a number",
        ),
        ({"if": [{"var": "amount"}, 1, 2]}, "if[0]: `if` takes a boolean, and this is a number"),
    ],
)
def test_an_if_is_checked_on_both_branches(data: object, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        check(parse_expression(data), REFUND)
    assert str(refused.value) == message


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"and": [{"var": "amount"}, True]},
            "and[0]: `and` combines booleans, and this is a number",
        ),
        ({"or": [True, {"var": "note"}]}, "or[1]: `or` combines booleans, and this is a string"),
        ({"!": [{"var": "note"}]}, "![0]: `!` takes a boolean, and this is a string"),
        (
            {"+": [{"var": "amount"}, {"var": "note"}]},
            "+[1]: `+` adds numbers, and this is a string",
        ),
        ({"/": [{"var": "urgent"}, 2]}, "/[0]: `/` divides numbers, and this is a boolean"),
        (
            {"cat": ["Refund of ", {"var": "amount"}]},
            "cat[1]: `cat` joins texts, and this is a number; write string(…) to turn it into text",
        ),
        (
            {"string": [{"var": "review.outcome"}]},
            (
                "string[0]: `string` takes a number, a boolean, a reference, an option or a date, "
                "and this is an outcome"
            ),
        ),
    ],
)
def test_logic_arithmetic_and_text_are_checked(data: object, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        check(parse_expression(data), REFUND)
    assert str(refused.value) == message


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"in": [{"var": "review.outcome"}, ["approve", "rejct"]]},
            'in[1][1]: review.outcome has no outcome "rejct"; its outcomes are approve, reject',
        ),
        (
            {"in": [{"var": "amount"}, ["a", "b"]]},
            "in[1]: `in` looks for a number in a list of strings",
        ),
        (
            {"in": [{"var": "order_id"}, ["ORD-7"]]},
            (
                "in[0]: `in` looks for a number, a string, a boolean, an outcome or a date, "
                "and this is a reference to orders"
            ),
        ),
        ({"exists": "aproved_amount"}, "aproved_amount is not a declared field"),
        ({"==": [{"var": "items"}, 1]}, "==[0]: items is a list; read it with count or sum"),
    ],
)
def test_in_exists_and_lists_are_checked(data: object, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        check(parse_expression(data), REFUND)
    assert str(refused.value) == message


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"count": {"over": {"var": "amount"}}},
            "count.over: amount is a number, and count reads a list",
        ),
        ({"count": {"over": {"var": "itms"}}}, "count.over: itms is not a declared field"),
        (
            {"count": {"over": {"var": "items"}, "where": {"==": [{"item": "risks"}, "high"]}}},
            "count.where.==[0]: item.risks is not a field of the elements of items",
        ),
        (
            {"count": {"over": {"var": "items"}, "where": {"item": "risk"}}},
            "count.where: `where` takes a boolean, and this is a string",
        ),
        (
            {"sum": {"over": {"var": "items"}, "value": {"item": "risk"}}},
            "sum.value: `sum` adds numbers, and this is a string",
        ),
    ],
)
def test_count_sum_and_item_are_checked(data: object, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        check(parse_expression(data), REFUND)
    assert str(refused.value) == message


HIGH_TOTAL = {"sum": {"over": {"var": "items"}, "where": HIGH, "value": {"item": "amount"}}}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"==": [{"var": "review.outcome"}, "approve"]}, BooleanType()),
        (
            {
                "and": [
                    {"==": [{"var": "review.outcome"}, "approve"]},
                    {">": [{"var": "approved_amount"}, 100]},
                ]
            },
            BooleanType(),
        ),
        ({"in": [{"var": "review.outcome"}, ["approve", "reject"]]}, BooleanType()),
        ({"if": [{"exists": "approved_amount"}, {"var": "approved_amount"}, 0]}, NumberType()),
        ({"cat": ["Refund of ", {"string": [{"var": "approved_amount"}]}]}, StringType()),
        ({"cat": ["Review: ", {"var": "review.outcome"}]}, StringType()),
        ({"==": [{"var": "order_id"}, {"var": "order_id"}]}, BooleanType()),
        (
            {"if": [{"var": "urgent"}, {"var": "order_id"}, {"var": "order_id"}]},
            ReferenceType(system="orders"),
        ),
        ({"count": {"over": {"var": "items"}, "where": HIGH}}, NumberType()),
        ({">": [HIGH_TOTAL, 10000]}, BooleanType()),
    ],
)
def test_check_gives_the_type(data: object, expected: FieldType) -> None:
    assert check(parse_expression(data), REFUND) == expected


def test_a_reference_compares_only_with_the_same_system() -> None:
    fields: dict[str, FieldType] = {**REFUND, "policy_id": ReferenceType(system="policies")}
    mixed = parse_expression({"==": [{"var": "order_id"}, {"var": "policy_id"}]})
    with pytest.raises(ExpressionInvalid) as refused:
        check(mixed, fields)
    assert str(refused.value) == (
        "==[1]: `==` compares values of the same type, "
        "and this is a reference to policies, not a reference to orders"
    )


def test_render_refuses_what_it_does_not_know() -> None:
    unknown = cast(Expression, {"now": []})
    with pytest.raises(ExpressionInvalid) as refused:
        render(unknown)
    assert str(refused.value) == "can't render {'now': []}: it isn't a parsed expression"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"var": "approved_amount"}, "approved_amount"),
        ({"var": "review.outcome"}, "review.outcome"),
        (Decimal("250.00"), "250.00"),
        (True, "true"),
        ("approve", '"approve"'),
        ('say "yes" or no', '"say \\"yes\\" or no"'),
        ({"exists": "approved_amount"}, "exists(approved_amount)"),
    ],
)
def test_render_literals_and_fields(data: object, expected: str) -> None:
    assert render(parse_expression(data)) == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({">": [{"var": "approved_amount"}, 100]}, "approved_amount > 100"),
        ({"!=": [{"var": "review.outcome"}, "reject"]}, 'review.outcome != "reject"'),
        ({"and": [{"var": "urgent"}, {"var": "vip"}, True]}, "urgent and vip and true"),
        ({"or": [{"var": "urgent"}, {"var": "vip"}]}, "urgent or vip"),
        ({"!": [{"var": "urgent"}]}, "not(urgent)"),
        ({"+": [{"var": "amount"}, 1, 2]}, "amount + 1 + 2"),
        ({"/": [{"var": "amount"}, 3]}, "amount / 3"),
        ({"if": [{"var": "urgent"}, 1, 0]}, "if urgent then 1 else 0"),
        (
            {"in": [{"var": "review.outcome"}, ["approve", "escalate"]]},
            'review.outcome in ["approve", "escalate"]',
        ),
        (
            {"cat": ["Refund of ", {"string": [{"var": "amount"}]}]},
            'cat("Refund of ", string(amount))',
        ),
        ({"count": {"over": {"var": "items"}}}, "count(items)"),
        (
            {"count": {"over": {"var": "items"}, "where": HIGH}},
            'count(items where item.risk = "high")',
        ),
        (
            {"sum": {"over": {"var": "items"}, "value": {"item": "amount"}}},
            "sum(item.amount over items)",
        ),
        (HIGH_TOTAL, 'sum(item.amount over items where item.risk = "high")'),
    ],
)
def test_render_each_operator(data: object, expected: str) -> None:
    assert render(parse_expression(data)) == expected


A, B = {"var": "a"}, {"var": "b"}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"and": [{"or": [A, B]}, {">": [{"var": "amount"}, 0]}]}, "(a or b) and amount > 0"),
        ({"or": [{"and": [A, B]}, True]}, "(a and b) or true"),
        ({"!": [{"and": [A, B]}]}, "not(a and b)"),
        ({"-": [{"var": "amount"}, {"-": [{"var": "fee"}, 1]}]}, "amount - (fee - 1)"),
        ({"-": [{"-": [{"var": "amount"}, {"var": "fee"}]}, 1]}, "(amount - fee) - 1"),
        ({"*": [{"+": [{"var": "amount"}, 1]}, 2]}, "(amount + 1) * 2"),
        ({"+": [{"var": "amount"}, {"*": [1, 2]}]}, "amount + 1 * 2"),
        ({"==": [{"==": [A, B]}, True]}, "(a = b) = true"),
        ({">": [{"if": [A, 1, 0]}, 0]}, "(if a then 1 else 0) > 0"),
        ({"if": [A, {"if": [B, 1, 2]}, 3]}, "if a then (if b then 1 else 2) else 3"),
        ({"and": [{"in": [A, ["x"]]}, {"!": [B]}]}, 'a in ["x"] and not(b)'),
    ],
)
def test_render_brackets_only_what_needs_it(data: object, expected: str) -> None:
    assert render(parse_expression(data)) == expected


GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "expressions.md"


def guide_table(header: str) -> list[tuple[str, str]]:
    """The rows of the guide's table under `header`, as (first cell, second cell), code unquoted."""
    lines = GUIDE.read_text().splitlines()
    start = lines.index(header) + 2  # the header, then the |---| line
    rows = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        first, second = (cell.strip() for cell in line.strip("|").split(" | "))
        rows.append((unquote(first), unquote(second)))
    # An emptied table would run no tests and pass silently: fail closed here too.
    assert rows, f"the guide's table {header} has no rows"
    return rows


def unquote(cell: str) -> str:
    """A table cell's code without its backticks: `x` or `` x `` (when x holds a backtick)."""
    return cell[3:-3] if cell.startswith("`` ") else cell[1:-1]


@pytest.mark.parametrize(("stored", "reads_as"), guide_table("| Stored | Reads as |"))
def test_the_guide_reads_as_the_renderer_renders(stored: str, reads_as: str) -> None:
    assert render(parse_expression(json.loads(stored, parse_float=Decimal))) == reads_as


@pytest.mark.parametrize(("wrote", "message"), guide_table("| You wrote | Refused with |"))
def test_the_guide_refuses_as_the_check_refuses(wrote: str, message: str) -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        check(parse_expression(json.loads(wrote, parse_float=Decimal)), REFUND)
    assert str(refused.value) == message


def nested(levels: int) -> object:
    """`not(not(…(true)…))`, `levels` objects deep."""
    data: object = True
    for _ in range(levels):
        data = {"!": [data]}
    return data


TOO_DEEP = (
    "an expression is nested at most 32 levels deep, and this one goes deeper; "
    "logic this deep belongs in a compute activity"
)


@pytest.mark.parametrize("levels", [33, 3000])
def test_an_expression_nested_too_deep_is_refused(levels: int) -> None:
    # A model writing expressions could produce this; Python's RecursionError helps nobody.
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression(nested(levels))
    assert str(refused.value) == TOO_DEEP


def test_an_expression_32_levels_deep_parses() -> None:
    assert evaluate(parse_expression(nested(32)), {}) is True


OUTSIDE_DECIMAL128 = [Decimal("1E+999999"), Decimal("1E-7000"), Decimal("1" * 35)]


@pytest.mark.parametrize("number", OUTSIDE_DECIMAL128)
def test_a_literal_outside_decimal128_is_refused(number: Decimal) -> None:
    # The TypeScript evaluator couldn't hold it exactly, so the two would disagree (brief, D20).
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression({">": [{"var": "amount"}, number]})
    assert str(refused.value) == (
        f"{number} doesn't fit a decimal128 number (34 digits, exponents within ±6144)"
    )


@pytest.mark.parametrize("number", OUTSIDE_DECIMAL128)
def test_a_case_file_value_outside_decimal128_is_an_error(number: Decimal) -> None:
    with pytest.raises(ExpressionError) as stopped:
        evaluate(Var(var="amount"), {"amount": number})
    assert str(stopped.value) == (
        "amount holds a number that doesn't fit a decimal128 number "
        "(34 digits, exponents within ±6144)"
    )


def test_sum_reads_value_only_for_the_elements_where_chose() -> None:
    # An element `where` leaves out may lack the value: like `if`, only the chosen ones are read.
    items = [{"risk": "high", "amount": Decimal(10)}, {"risk": "low"}]
    assert evaluate(parse_expression(HIGH_TOTAL), {"items": items}) == Decimal(10)


# The guide's runtime table, each situation played against the evaluator: until 16a no test read
# it, and one row promised a message nothing gave (docs/layers/16-field-types.md, step 6).
def stopped_with(expression: object, values: dict[str, object]) -> str:
    with pytest.raises(ExpressionError) as stopped:
        evaluate(parse_expression(expression), values)
    return str(stopped.value)


RUNTIME_SITUATIONS: dict[str, Any] = {
    "`approved_amount` has no value yet": lambda: stopped_with(
        {">": [{"var": "approved_amount"}, 100]}, {}
    ),
    '`{"/": [{"var": "amount"}, {"var": "items"}]}`, with 250 and 0': lambda: stopped_with(
        {"/": [{"var": "amount"}, {"var": "items"}]}, {"amount": Decimal(250), "items": Decimal(0)}
    ),
    "a result beyond what decimal128 can hold": lambda: stopped_with(
        {"*": [{"var": "amount"}, {"var": "amount"}]}, {"amount": Decimal("1E+5000")}
    ),
    'an element of `items` lacks `risk`, in `count(items where item.risk == "high")`': lambda: (
        stopped_with(
            {"count": {"over": {"var": "items"}, "where": {"==": [{"item": "risk"}, "high"]}}},
            {"items": [{"risk": "low"}, {"amount": Decimal(5)}]},
        )
    ),
    "`approved_amount > 100`, with a text in `approved_amount`": lambda: stopped_with(
        {">": [{"var": "approved_amount"}, 100]}, {"approved_amount": "250"}
    ),
    '`incident_date < date("2027-01-01")`, with a text in `incident_date`': lambda: stopped_with(
        {"<": [{"var": "incident_date"}, {"date": "2027-01-01"}]}, {"incident_date": "2026-10-31"}
    ),
}


def runtime_rows() -> list[tuple[str, str]]:
    """The runtime table's rows: each situation as written, prose and code, and its error with its
    backticks taken off, as `guide_table` takes them off a cell that is all code."""
    lines = GUIDE.read_text().splitlines()
    start = lines.index("| Situation | Error |") + 2
    rows = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        situation, error = (cell.strip() for cell in line.strip("|").split(" | "))
        rows.append((situation, unquote(error)))
    return rows


def test_the_guides_runtime_errors_are_what_the_evaluator_says() -> None:
    rows = runtime_rows()
    assert [situation for situation, _ in rows] == list(RUNTIME_SITUATIONS)
    for situation, error in rows:
        assert RUNTIME_SITUATIONS[situation]() == error, situation
