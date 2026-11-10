# Shows whether D20's operator list and arithmetic claims, D22's identifier spelling and D23's order of checks on an answer are what the code does.
import decimal
import json
from decimal import Decimal
from pathlib import Path

from ventoux.core.expressions import ExpressionError, ExpressionInvalid, evaluate, parse_expression, render
from ventoux.core.expressions.model import OPERATORS
from ventoux.core.person import identifier_problem  # no public door for the spelling rule alone
from ventoux.testing import run_case

ROWS: list[tuple[str, str, str, bool]] = []


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, str(shown), agrees))


def attempt(action):  # what a call gives, or the refusal's class and first words
    try:
        return "ok", action()
    except Exception as error:  # the probe reports every refusal
        return type(error).__name__, str(error)[:110]


# D20: the list.
LISTED = ["var", "==", "!=", ">", ">=", "<", "<=", "and", "or", "!", "+", "-", "*", "/", "if", "in",
          "cat", "string", "exists", "count", "sum", "item"]
extra = sorted(set(OPERATORS) - set(LISTED))
missing = sorted(set(LISTED) - set(OPERATORS))
row("D20", "'The operators: var ... sum ... item' (+ `date`, D66)", f"extra={extra} missing={missing}", extra == ["date"] and not missing)
CANDIDATES = ["now", "map", "filter", "reduce", "all", "none", "some", "merge", "max", "min", "%", "===", "!==", "!!",
              "substr", "missing", "missing_some", "log", "method", "today", "random", "not", "between", "len", "round"]
accepted = [name for name in CANDIDATES if attempt(lambda n=name: parse_expression({n: [1, 2]}))[0] == "ok"]
row("D20", "'an unknown operator is an error'", f"unlisted operators accepted by the parser: {accepted}", not accepted)
kind, shown = attempt(lambda: evaluate(parse_expression({"==": [{"+": [Decimal("0.1"), Decimal("0.2")]}, Decimal("0.3")]}), {}))
row("D20", "'0.1 + 0.2 == 0.3 holds'", shown, shown is True)
decimal.getcontext().prec = 5  # the process default must not decide
decimal.getcontext().rounding = decimal.ROUND_UP
kind, third = attempt(lambda: evaluate(parse_expression({"/": [1, 3]}), {}))
row("D20", "'1 / 3 keeps 34 significant digits ... never taken from a global default'", third, str(third) == "0." + "3" * 34)
kind, two_thirds = attempt(lambda: evaluate(parse_expression({"/": [2, 3]}), {}))
row("D20", "'rounding half to even' (2/3 ends in 7)", two_thirds, str(two_thirds) == "0." + "6" * 33 + "7")
# A tie at the 35th digit: 1 + 5E-34 has 35 digits as a sum, half-even keeps ...0 ; 1.5E-33+... use multiplication
kind, tie = attempt(lambda: evaluate(parse_expression({"+": [Decimal("1." + "0" * 32 + "2"), Decimal("5E-34")]}), {}))
row("D20", "'rounding half to even' (a tie after an even digit stays)", tie, str(tie) == "1." + "0" * 32 + "2")
kind, tie = attempt(lambda: evaluate(parse_expression({"+": [Decimal("1." + "0" * 32 + "1"), Decimal("5E-34")]}), {}))
row("D20", "'rounding half to even' (a tie after an odd digit goes up)", tie, str(tie) == "1." + "0" * 32 + "2")
decimal.setcontext(decimal.Context())
kind, shown = attempt(lambda: evaluate(parse_expression({"/": [1, 0]}), {}))
row("D20", "'Division by zero is an error'", f"{kind}: {shown}", kind == "ExpressionError")
for operator, first in (("and", False), ("or", True)):
    kind, shown = attempt(lambda: evaluate(parse_expression({operator: [first, {"var": "absent"}]}), {}))
    row("D20", f"'`{operator}` evaluate[s] every operand, so an error is never hidden'", f"{kind}: {shown}", kind == "ExpressionError")
for refused, data in (("a default in var", {"var": ["a", 1]}), ("var of the whole data", {"var": ""}),
                      ("if chains", {"if": [True, 1, False, 2, 3]}), ("a float", 0.1)):
    kind, shown = attempt(lambda: parse_expression(data))
    row("D20", f"'Refused: {refused}'", f"{kind}: {shown}", kind == "ExpressionInvalid")
for refused, data, values in (("truthiness", {"and": [1, True]}, {}), ("coercion in ==", {"==": [1, "1"]}, {}),
                              ("coercion in cat", {"cat": ["a", 1]}, {})):
    kind, shown = attempt(lambda: evaluate(parse_expression(data), values))
    row("D20", f"'Refused: {refused}'", f"{kind}: {shown}", kind in ("ExpressionError", "ExpressionInvalid"))


def nested(levels: int) -> object:
    data: object = True
    for _ in range(levels):
        data = {"!": [data]}
    return data


at_32, at_33 = attempt(lambda: parse_expression(nested(32)))[0], attempt(lambda: parse_expression(nested(33)))
row("D60", "'nested at most 32 levels'", f"32 levels: {at_32}; 33 levels: {at_33[0]}: {at_33[1]}", at_32 == "ok" and at_33[0] == "ExpressionInvalid")
text = render(parse_expression({"and": [{"==": [{"var": "review.outcome"}, "approve"]}, {"or": [{"!=": [{"var": "a"}, 1]}, {"!": [{">": [{"var": "approved_amount"}, 100]}]}]}]}))
row("D20", "'FEEL-style ... `=` and `!=`, `and`, `or`, `not(...)`'", text, text == 'review.outcome = "approve" and (a != 1 or not(approved_amount > 100))')

# D22: the spelling.
GOOD = ["ana", "ana.lee@example.com", "9", "a-b_c.d@e", "0day"]
BAD = ["Ana", "ana lee", "ana:lee", ".ana", "_ana", "@ana", "-ana", "", "ana\n", "ána", "ana/lee", "ａna", "ana+x", "٣ana"]
wrong = [name for name in GOOD if identifier_problem(name) is not None] + [name for name in BAD if identifier_problem(name) is None]
row("D22", "'lowercase letters, digits, . _ @ -, starting with a letter or digit'", f"read the wrong way: {wrong!r}", not wrong)

# D23: the order of the checks, when several refusals apply at once.
claim = json.loads(Path("examples/claim/claim.json").read_text(), parse_float=Decimal)
people = {"bob": [], "Sam": ["adjuster"]}


def refusal(entry: str, outcome: str, who: str) -> str:
    return " | ".join(attempt(lambda: run_case(claim, {"claimed": Decimal(10)}, [(entry, outcome, who)], people)))


shown = refusal("assess#7", "nope", "Sam")
row("D22", "'refuses any other spelling at the answer, before any other check'", shown, "identifier" in shown)
shown = refusal("assess#7", "nope", "bob")
row("D23", "'in the same order: the entry is open, ...' (closed entry, unknown outcome, no role)", shown, "assess#7" in shown and "open" in shown)
shown = refusal("assess#1", "nope", "bob")
row("D23", "'... the outcome is one offered, the person has one of its roles' (unknown outcome, no role)", shown, "nope" in shown and "offer" in shown)
shown = refusal("assess#1", "done", "bob")
row("D23", "'... the person has one of its roles'", shown, "role" in shown)

print("decision | the brief's claim | what a run shows | agrees?")
for decision, claim_text, shown, agrees in ROWS:
    print(f"{decision} | {claim_text} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{d}: {c}" for d, c, _, ok in ROWS if not ok]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
