# Shows a product (and a quotient) of two positive numbers too small for decimal128 evaluating to zero, silently, where one too large is an error.
"""Run: uv run python reviews/2026-11/probes/p3_expression_underflow_is_zero.py

`CONTEXT` (src/ventoux/core/expressions/model.py) traps `Overflow`, never `Underflow`. Past the
supported names: `parse_expression` and `evaluate` from `ventoux.core.expressions`.
"""

from decimal import Decimal

from ventoux.core.expressions.evaluate import evaluate
from ventoux.core.expressions.model import ExpressionError
from ventoux.core.expressions.parse import parse_expression

positive = parse_expression({">": [{"*": [{"var": "a"}, {"var": "a"}]}, 0]})
product = parse_expression({"*": [{"var": "a"}, {"var": "a"}]})
tiny, huge = Decimal("1E-6143"), Decimal("1E+6143")
print("a * a, a = 1E-6143:", repr(evaluate(product, {"a": tiny})))
print("a * a > 0, a = 1E-6143:", evaluate(positive, {"a": tiny}))
try:
    evaluate(product, {"a": huge})
    large = "a value"
except ExpressionError as error:
    large = f"ExpressionError: {error}"
print("a * a, a = 1E+6143:", large)
if evaluate(positive, {"a": tiny}) is False:
    print(
        "RESULT: BROKEN - a result too small for decimal128 is zero with no error, so "
        "`a * a > 0` is false for a positive a; a result too large is an error"
    )
else:
    print("RESULT: HELD - a result too small for decimal128 is an error")
