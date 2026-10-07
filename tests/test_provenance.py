"""Provenance: an expression's value carries the sources of every field it reads (layer 4).

See docs/layers/04-provenance.md.
"""

import pytest

from ventoux.core.expressions import parse_expression
from ventoux.core.provenance import NoSources, provenance


def test_a_field_without_sources_is_an_error() -> None:
    # Fail closed: no sources would mean "written in the definition", which every input accepts.
    expression = parse_expression({"cat": [{"var": "customer_email"}, {"var": "suggested"}]})
    with pytest.raises(NoSources, match="suggested has no known sources"):
        provenance(expression, {"customer_email": frozenset({"system:crm"})})


SOURCES = {
    "amount": frozenset({"system:orders"}),
    "approved_amount": frozenset({"person:ana"}),
    "suggested": frozenset({"untrusted:llm"}),
    "items": frozenset({"untrusted:document"}),
}


def test_a_literal_has_no_sources() -> None:
    # A value written in the definition, reviewed like code: it comes from no system and no one.
    assert provenance(parse_expression("reply"), SOURCES) == frozenset()


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ({"var": "amount"}, {"system:orders"}),
        ({"cat": [{"var": "suggested"}, "@corp.com"]}, {"untrusted:llm"}),
        ({"+": [{"var": "amount"}, {"var": "approved_amount"}]}, {"system:orders", "person:ana"}),
        # `if`'s condition decides which value comes out, so its sources come with it.
        (
            {"if": [{"var": "suggested"}, {"var": "amount"}, {"var": "approved_amount"}]},
            {"untrusted:llm", "system:orders", "person:ana"},
        ),
        ({"in": [{"var": "suggested"}, ["yes", "no"]]}, {"untrusted:llm"}),
        ({"exists": "approved_amount"}, {"person:ana"}),
        # `count` and `sum` read the list; `item` reads its elements, so the list's sources.
        (
            {"count": {"over": {"var": "items"}, "where": {">": [{"item": "price"}, 0]}}},
            {"untrusted:document"},
        ),
        (
            {
                "sum": {
                    "over": {"var": "items"},
                    "where": {"<": [{"item": "price"}, {"var": "amount"}]},
                    "value": {"item": "price"},
                }
            },
            {"untrusted:document", "system:orders"},
        ),
    ],
)
def test_every_field_read_is_a_source(expression: object, expected: set[str]) -> None:
    assert provenance(parse_expression(expression), SOURCES) == expected


def test_something_that_is_not_an_expression_is_an_error() -> None:
    # Fail closed: what the walk doesn't know is refused, never read as reading no field.
    with pytest.raises(TypeError, match="not an expression: dict"):
        provenance({"var": "amount"}, SOURCES)  # type: ignore[arg-type]
