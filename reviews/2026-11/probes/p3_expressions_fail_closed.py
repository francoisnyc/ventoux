# Shows the expression evaluator and parser refusing what they don't know: wrong arity, mixed types, missing values, floats, NaN, depth, with no value quoted in an error.
"""Run: uv run python reviews/2026-11/probes/p3_expressions_fail_closed.py

Each line is an expression that must be refused, at parsing or at evaluation, and a recognisable
value that no error may quote (D20, D30). Past the supported names: `parse_expression`, `evaluate`.
"""

import json
from decimal import Decimal
from typing import Any

from ventoux.core.expressions.evaluate import evaluate
from ventoux.core.expressions.model import ExpressionError
from ventoux.core.expressions.parse import ExpressionInvalid, parse_expression

VALUE = "RECOGNISABLE-9931"
D = Decimal
deep: Any = True
for _ in range(40):
    deep = {"!": [deep]}
REFUSED: list[tuple[Any, dict[str, Any]]] = [
    ('{"==": [true, 1]}', {}),
    ('{"==": [{"var": "a"}, 1]}', {"a": VALUE}),
    ('{"==": [{"var": "a"}, 1]}', {}),
    ('{"==": [{"var": "a"}, 1]}', {"a": 1}),
    ('{"==": [{"var": "a"}, 1]}', {"a": 1.5}),
    ('{"==": [{"var": "a"}, 1]}', {"a": D("NaN")}),
    ('{"==": [{"var": "a"}, 1]}', {"a": D("Infinity")}),
    ('{">": [{"var": "a"}, 1]}', {"a": VALUE}),
    ('{"and": [{"var": "a"}, true]}', {"a": VALUE}),
    ('{"!": [{"var": "a"}]}', {"a": VALUE}),
    ('{"if": [{"var": "a"}, 1, 2]}', {"a": VALUE}),
    ('{"+": [{"var": "a"}, 1]}', {"a": VALUE}),
    ('{"/": [{"var": "a"}, 0]}', {"a": D("9931.9931")}),
    ('{"*": [{"var": "a"}, {"var": "a"}]}', {"a": D("9931E+6100")}),
    ('{"*": [{"var": "a"}, 3]}', {"a": D("3333333333333333333333333333339931.5")}),
    ('{"cat": [{"var": "a"}, "x"]}', {"a": D("9931")}),
    ('{"in": [{"var": "a"}, [1, 2]]}', {"a": VALUE}),
    ('{"count": {"over": {"var": "xs"}}}', {"xs": [VALUE]}),
    ('{"sum": {"over": {"var": "xs"}, "value": {"item": "n"}}}', {"xs": [{"n": VALUE}]}),
    ('{"sum": {"over": {"var": "xs"}, "value": {"item": "n"}}}', {"xs": [{}]}),
    ("1e400", {}),
    ("NaN", {}),
    ("1.5e0", {}),
    ("null", {}),
    ("[1]", {}),
    ("{}", {}),
    ('{"unknown": [1]}', {}),
    ('{"+": [1]}', {}),
    ('{"!": [true, false]}', {}),
    ('{"if": [true, 1]}', {}),
    ('{"and": []}', {}),
    ('{"in": [1, []]}', {}),
    ('{"in": [1, [1, "x"]]}', {}),
    ('{"==": [1, 1], "!=": [1, 2]}', {}),
    ('{"var": "a", "default": 0}', {}),
    ('{"<": [{"date": "2026-02-30"}, {"date": "2026-03-01"}]}', {}),
    (deep, {}),
]
slipped, quoted = [], []
for written, values in REFUSED:
    data = json.loads(written) if isinstance(written, str) else written
    try:
        result = evaluate(parse_expression(data), values)
        slipped.append(f"{written} gave {result!r}")
    except (ExpressionInvalid, ExpressionError) as error:
        if VALUE in str(error) or "9931" in str(error):
            quoted.append(f"{written}: {error}")
for line in slipped + quoted:
    print(line)
print(
    f"{len(REFUSED)} expressions, {len(slipped)} evaluated after all, {len(quoted)} errors quoting a value"
)
if slipped or quoted:
    print(
        "RESULT: BROKEN - an expression the engine should refuse gave a value, or an error quoted one"
    )
else:
    print(
        "RESULT: HELD - each is refused as ExpressionInvalid or ExpressionError, and no error "
        "quotes the case file's value"
    )
