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
    BooleanType,
    Cat,
    Count,
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


IN_LIST = '`in` takes a value and a list of values, like {"in": [x, ["approve", "escalate"]]}'


@pytest.mark.parametrize(
    ("data", "message"),
    [
        # JsonLogic chains `if` (`[c1, a, c2, b, else]`); ours takes exactly three (D3).
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
    assert str(stopped.value) == "`if` takes a boolean, and it was given a number: 1"


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
        "`cat` joins texts, and it was given a number: 250; write string(…) to turn it into text"
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
        (Decimal(3), "items holds Decimal('3'), and count reads a list of records"),
        ("items", "items holds 'items', and count reads a list of records"),
        ([Decimal(3)], "items holds [Decimal('3')], and count reads a list of records"),
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
    assert str(stopped.value) == "`sum` adds numbers, and it was given a string: '10'"


def test_where_is_a_condition() -> None:
    items = [{"risk": "high", "amount": Decimal(10)}]
    truthy = parse_expression({"count": {"over": {"var": "items"}, "where": {"item": "risk"}}})
    with pytest.raises(ExpressionError) as stopped:
        evaluate(truthy, {"items": items})
    assert str(stopped.value) == "`where` takes a boolean, and it was given a string: 'high'"


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
            ">[1]: `>` compares numbers, and this is a string",
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
            "string[0]: `string` takes a number, a boolean or a reference, and this is an outcome",
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
                "in[0]: `in` looks for a number, a string, a boolean or an outcome, "
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
