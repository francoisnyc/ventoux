# Layer 2: plan schema and expressions

Status: draft, 2026-10-04 (the ten design choices agreed in the session; this note awaits review).

## What this layer is for

Two kinds of data the engine reads and never executes. A **plan** is a state machine written as
data, so later layers can prove things about it by reading it (layer 3). An **expression** is a
JSON tree using only D3's operators: it is parsed, checked against declared field types,
evaluated as a pure function of the values, and rendered on one line for people. User-facing
description: `docs/guides/expressions.md`.

Drawn on: the prototype's `src/core/schema.ts` (the three kinds of state, dispatching on a state's
distinguishing key so errors point at the right fields, the patterns for references and
durations) and the spike's `docs/layers/spike-dsl/structured.py` (one model per operator, the
evaluator, the renderer). The prototype's `src/core/expr.ts` is what we don't do: JSONata, which
fails open.

**Why the tracer has to go.** `case/runner.py:149–164` returns an unknown operator's dict
unchanged, and `holds` tests `is True`. So `"approval": {"when": {"now": []}}` reads as "no
approval needed" and the refund is paid, which is the bug behind the brief's fail-closed rule.
Layer 2 deletes `evaluate` and `holds` and adds a regression test for exactly this case.

## Files

- `src/ventoux/core/expressions.py`: the field types, the expression models, `parse_expression`,
  `check`, `evaluate` and `render`.
- `src/ventoux/core/plan.py`: the plan models and `parse_plan`.
- `src/ventoux/case/runner.py`: uses the core evaluator; `evaluate` and `holds` are gone.
- `src/ventoux/testing.py`: `load_definition` reads JSON with `parse_float=Decimal`.
- `examples/refund/refund.json`: `=` becomes `==` and `field` becomes `var`, in inputs too.
- `tests/test_expressions.py`, `tests/test_plan.py`; the guide's tables run in a test.

No new dependency: Pydantic and the standard library's `decimal`.

## Expressions

**Models.** A frozen Pydantic model with `extra="forbid"` for each operator, as in the sketch. An
expression is a literal, `{"var": name}`, or an object with exactly one key, the operator. Each
operator's argument shape is in the guide's table. The shapes we refuse, with JsonLogic's
reading in brackets:

- a default in `var` (`{"var": ["x", 0]}`);
- `var` of the whole data (`{"var": ""}`);
- `if` with more or fewer than three arguments (chains);
- a unary `-` (negation);
- `<` with three arguments (between);
- `!` of a bare value (only `{"!": [x]}`);
- `in` on a string (substring);
- `null` as a literal.

A list literal is allowed only as the second argument of `in`, and holds at least one literal
value, all of one type (decided in slice 6: list fields hold records for `count` and `sum`, so
`in` never reads one).

**One clear parse error** (choice 2). The sketch's union of operator models gave 38 errors for
`{"now": []}`. A validator runs first, before any union matching. It checks that the value is a
literal or an object with one key, and that the key is an operator. If not, it raises
`ExpressionInvalid` with the one message the guide shows. After that, Pydantic validates only the
named operator's model, so a bad argument gets one error from that model too.

**Numbers** (choices 3 and 4). Every number is a `Decimal`. The parser refuses:

- a Python `float`, which means the JSON was read without `parse_float=Decimal` and `0.1` has
  already lost precision. It says so, and doesn't convert.
- a `bool` where a number is expected, since Python's `True` is an `int`.

Arithmetic uses one module-level context, passed explicitly (`CONTEXT.add(a, b)`,
`CONTEXT.divide(a, b)`), never `getcontext()`. It is decimal128 in full: 34 digits, rounding half
to even, exponents within ±6144, and overflow trapped and turned into an `ExpressionError` (found
in slice 5: Python's default range returned `1E+12000`). A number must be finite, in a literal
and in the case file: `Infinity > 100` is true, so an infinite amount would pass a threshold.
Division by zero names the values (`division by zero: 250 / 0`), since naming the fields needs the
renderer (slice 9). `string` of a number is the
`Decimal`'s own text (`250`, `250.00`, `0.3`); it is never reformatted.

**Field types** (choice 3), the shape case and plan definitions already use:
- `{"type": "number"}`, `{"type": "string"}`, `{"type": "boolean"}`;
- `{"type": "outcome", "outcomes": ["approve", "reject"]}`;
- `{"type": "reference", "system": "orders"}`;
- `{"type": "list", "fields": {"risk": …, "amount": …}}`.

An outcome compares with a text literal only if the text is one of its outcomes, which is how
`"aprove"` is caught. A reference compares only with a reference of the same system.

**The check** (choices 5, 6, 8). `check(expression, fields)` takes a plain mapping from declared
name to field type and returns the expression's type, or raises `ExpressionInvalid` naming the
path inside the expression (`and[1].==[0]`). A `var` names exactly one declared field, dotted
names like `review.outcome` included. Nothing walks into undeclared parts of an object. `item`
is valid only inside `count` and `sum`, and reads a field of the list's elements. Which fields
exist at a given state of a plan or step of a case is not this layer's question: layer 3's
validator builds the mapping and collects issues as `(path, code, message)`. Layer 2 raises the
first error.

What the check decides (slice 8): an ordering and arithmetic need numbers; equality needs the same
type on both sides, model equality doing the work (a reference only to the same system, an outcome
only to the same list), except that a text literal compared with an outcome must be one of its
names, in `==`, `!=` and `in` alike. `if` needs a boolean condition and two branches of one type,
both checked though only one runs. `cat` takes texts, an outcome counting as one; `string` takes a
number, a boolean or a reference; `in` never takes a reference. A list field appears only as
`count`'s or `sum`'s `over`, and `item` reads that list's declared element fields: the check passes
the list down as the evaluator passes the element.

**The evaluator** (fail closed). `evaluate(expression, values)` takes a parsed expression and a
mapping from field name to value. It raises `ExpressionError` when:

- a field is missing;
- a value has the wrong runtime type (the evaluator checks the values, and doesn't rely on the
  check having run). It takes the values as `Mapping[str, object]`, because the case file is data
  from outside, and refuses one it can't read at all, such as a binary float (found in slice 2,
  by mypy);
- it divides by zero;
- it meets an object it has no case for, such as a raw dict.

`and` and `or` evaluate every operand before combining, so an error is never hidden. `if` is the
one exception, deliberately: it evaluates only the branch its condition chooses, or
`if exists(x) then x else 0` could never guard a missing value (slice 6; the type check still
checks both branches). A JSON `null` in the case file is no value, for `var` and `exists` alike. A
condition returns `True`, returns `False`, or raises: there is no `holds`.

**`count` and `sum`** (slice 7). The list field holds records (mappings); anything else is an
error naming what it holds. Every element is looked at, with no early exit, and `where` must be a
boolean for each. `sum`'s `value` is read only for the elements `where` chose, as `if` reads only
its branch, and adds through the same decimal128 context as `+`. `item` reads the current element
with the same checks as `var`, and an error names it: `item.risk has no value (element 2 of
items)`. Where `item` may appear is checked once after parsing: the recursive `parse` accepts it
anywhere, and `parse_expression` walks the tree and refuses an `item` outside `count` and `sum`.
Threading an "inside" flag through every recursive call would have touched each line of the
parser; the walk is six lines, and later checks (types, provenance) walk the same tree.

**The renderer** (choice 9). One line, with parentheses only where precedence needs them:

- precedence from loosest to tightest: `or`, `and`, `not`, comparisons and `in`, `+ -`, `* /`;
- functions render as calls: `cat(…)`, `string(…)`, `exists(…)`, `count(…)`, `sum(…)`;
- `if` renders as `if … then … else …`;
- texts render in double quotes, with JSON escapes.

The renderer is for reading only. Nothing parses its output.

## Plans

Shape only (choice 7). `parse_plan(data)` returns a `Plan` or raises `PlanInvalid` with one
message per problem and its path, dispatching on each state's key as the prototype does.

```json
{
  "plan": "refund-pay",
  "version": 1,
  "display": {"title": "Refund the customer"},
  "fields": {"order_id": {"type": "reference", "system": "orders"}, "amount": {"type": "number"}},
  "initial": "pay",
  "states": {
    "pay": {
      "activity": "payments.refund@1",
      "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
      "on": {"done": "paid", "declined": "failed"}
    },
    "paid": {"final": "succeeded"},
    "failed": {"final": "failed"}
  }
}
```

- **The plan:** `plan` (kebab-case), `version` (≥ 1), `display.title` (presentation, D5),
  `fields` (field types, as above), `initial`, `states`.
- **An activity state:** `activity` (a `name@N` reference), `inputs` (name to expression), `on`.
- **A wait state:** `wait: {"outcomes": [...], "timeout": "48h"}`, `on`. It waits for one of a
  closed list of outcomes (D9), not the prototype's untyped signals.
- **A final state:** `final: "succeeded"` or `"failed"`.
- **A transition:** an event name mapped to a state id, or to a list of
  `{"when": expression, "target": state}`. At runtime (layer 5) the first `when` that holds wins,
  and none holding is an error.

An activity's events are `done` and the outcomes its contract declares. There is no `error`
event, unlike the prototype: an undeclared failure after the retries needs a person (D17), and is
never a transition the plan takes on its own.

Not in this layer:
- the prototype's `assign`, `resultAs` and per-state retry, since retries live in the contract
  (D17);
- references (does `initial`, each target or each activity exist, do `on` keys match the
  activity's outcomes, are the expressions well typed at their state) and reachability: layer 3;
- running a plan: layer 5.

## Seams the tests use

- `parse_expression(data) -> Expression`, raising `ExpressionInvalid`.
- `check(expression, fields) -> FieldType`, raising `ExpressionInvalid`.
- `evaluate(expression, values) -> value`, raising `ExpressionError`.
- `render(expression) -> str`.
- `parse_plan(data) -> Plan`, raising `PlanInvalid`.
- `load_definition` and `run_case` from the tracer. The quickstart's three tests stay green.
- The guide's tables: each "Stored / Reads as" row parses and renders as shown, and each refusal
  row raises the message shown.

## Slices, in order

1. Negative: `{"now": []}` and `{"map": …}` raise `ExpressionInvalid` with the one message. Then
   literals and `var` parse; a `float` and `null` are refused.
2. Negative: evaluating a missing field raises; evaluating a raw dict (an operator the evaluator
   doesn't know) raises. Then `var` returns the value.
3. Comparisons: a text compared with a number raises at runtime; `True` is not a number. Then
   `==`, `!=`, `>`, `>=`, `<`, `<=`.
4. Negative: `false and <missing field>` raises (every operand is evaluated). Then `and`, `or`,
   `!`.
5. Negative: `{"/": [x, 0]}` raises. Then `+`, `-`, `*`, `/`, with
   `{"==": [{"+": [0.1, 0.2]}, 0.3]}` true and `1 / 3` to 34 digits.
6. `if`, `in`, `cat`, `string`, `exists`, each with its negative (an `if` chain, `in` on a
   string, `cat` of a number).
7. `count`, `sum`, `item` (negative: `item` outside them).
8. The check: a misspelled outcome, a text compared with a number, an undeclared field, `if`
   branches of different types.
9. `render`, and the guide's tables run as a test.
10. Negative: malformed plans (a state with two kinds or none, a bad reference or duration, an
    unknown field, no title, a wait with no outcomes). Then the example plan parses.
11. The tracer switches over: `refund.json` renamed, `evaluate` and `holds` deleted, the
    regression test (an approval `when` of `{"now": []}` stops the case instead of paying), and
    the quickstart stays green.

## Done when

The tests, mypy and ruff pass, the quickstart's tests are green, no `# TRACER: … layer 2` comment
is left, and the guide matches the code.
