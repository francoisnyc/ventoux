# Layer 2: plan schema and expressions

Status: built, 2026-10-04 (the ten design choices agreed in the session; slices 1–11 done); tutor
review items 1–6 done 2026-10-05.

## What this layer is for

Two kinds of data the engine reads and never executes. A **plan** is a state machine written as
data, so later layers can prove things about it by reading it (layer 3). An **expression** is a
JSON tree using only D20's operators: it is parsed, checked against declared field types,
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

An expression is nested at most 32 levels deep, counting each JSON object as a level; deeper is
refused with a message naming the limit, measured before parsing and without recursion, so even
thousands of levels give that refusal and not Python's `RecursionError` (tutor review, item 5).

A list literal is allowed only as the second argument of `in`, and holds at least one literal
value, all of one type (decided in slice 6: list fields hold records for `count` and `sum`, so
`in` never reads one).

**One clear parse error** (choice 2). The sketch's union of operator models gave 38 errors for
`{"now": []}`. A validator runs first, before any union matching. It checks that the value is a
literal or an object with one key, and that the key is an operator. If not, it raises
`ExpressionInvalid` with the one message the guide shows. After that, Pydantic validates only the
named operator's model, so a bad argument gets one error from that model too.

**Numbers** (choices 3 and 4). Every number is a `Decimal`. The parser refuses a Python `float`,
which means the JSON was read without `parse_float=Decimal` and `0.1` has already lost precision:
it says so, and doesn't convert. It keeps `true` a boolean, never the number 1 (Python's `True` is
an `int`), so the check and the evaluator refuse it wherever a number goes.

Arithmetic uses one module-level context, passed explicitly (`CONTEXT.add(a, b)`,
`CONTEXT.divide(a, b)`), never `getcontext()`. It is decimal128 in full: 34 digits, rounding half
to even, exponents within ±6144, and overflow trapped and turned into an `ExpressionError` (found
in slice 5: Python's default range returned `1E+12000`). A number must be finite, in a literal
and in the case file: `Infinity > 100` is true, so an infinite amount would pass a threshold. And
it must fit decimal128 exactly, in a literal and in the case file: `1E+999999`, `1E-7000` and a
35-digit number are refused, since the TypeScript evaluator couldn't hold them and the two would
disagree (tutor review, item 6).
Division by zero names the fields and the values (`division by zero in amount / items (250 / 0)`):
the fields tell a developer where to look, the values an operator what happened (decided after
slice 9, once the renderer existed). `string` of a number is the
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

**The renderer** (choice 9). One line in FEEL style, the expression language of DMN and Camunda 8
(brief, D20, added after slice 11 in the tutor review): `==` reads as `=`, and `!` as `not(...)`.
Parentheses only where precedence needs them:

- precedence from loosest to tightest: `if`, `or`, `and`, comparisons and `in`, `+ -`,
  `* /`; a child that binds no tighter than its parent is bracketed, so the line shows exactly
  what is stored (`(amount - fee) - 1` is not `amount - (fee - 1)`), and an `and` inside an `or`
  is always bracketed, though precedence wouldn't need it: `a and b or c` is easy to misread
  (slice 9);
- functions render as calls: `not(…)`, `cat(…)`, `string(…)`, `exists(…)`, `count(…)`, `sum(…)`;
  `not(a and b)` needs no other brackets;
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
  `{"when": expression, "target": state}`.

What slice 10 settled. Names have one shape each, and a message showing it: a plan
`refund-pay`, a state `await_approval`, an event `approve`, a duration `48h`, and an activity
reference in the catalog's own pattern (`REFERENCE`), so a plan can only name what the catalog could
register. A bare state name in `on` is shorthand for one transition with no condition, and is
stored as that list. Expressions go through `parse_expression`, so a plan reports the same
messages (`states.pay.inputs.amount: `now` is not an operator…`). Field types are told apart by
their `type`. `PlanInvalid` lists every problem, one line each, with its path in the plan;
Pydantic's own markers (the kind it picked, `[key]`) are left out of the path.

Not in this layer:
- an activity's events are `done` and the outcomes its contract declares, with no `error` event,
  unlike the prototype: an undeclared failure after the retries needs a person (D17), never a
  transition the plan takes on its own. Layer 2 reads any event name; layer 3 refuses an `on` key
  that isn't `done` or a declared outcome;
- at runtime the first `when` that holds wins, and none holding is an error: layer 5;
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

## Promises

Each claim this note makes about behaviour, and the test that fails if it isn't true. `E` is
`tests/test_expressions.py`, `P` is `tests/test_plan.py`, `Q` is `tests/test_quickstart.py`.

| Promise | Test |
|---|---|
| An unknown operator (`now`, `map`) is refused with one message listing the operators, at any depth | E `test_an_unknown_operator_is_refused_with_one_message`, `test_an_unknown_operator_inside_another_is_refused` |
| An object holds exactly one operator | E `test_an_object_holds_exactly_one_operator` |
| `var` names one field: no default, never the whole case file | E `test_var_names_one_field_with_no_default` |
| JsonLogic's looser shapes are refused: `if` chains, unary `-`, three-argument `<`, a bare `!`, `in` on a text | E `test_a_comparison_takes_two_arguments`, `test_logic_operators_take_their_number_of_arguments`, `test_arithmetic_takes_its_number_of_arguments`, `test_if_in_cat_string_exists_take_their_shape` |
| `null` is not a literal; a list is an expression only as `in`'s list, non-empty, literal, of one type | E `test_null_is_not_a_value`, `test_a_list_is_not_an_expression`, `test_if_in_cat_string_exists_take_their_shape` |
| An expression nests at most 32 levels; deeper (even 3,000) is refused, never a `RecursionError` | E `test_an_expression_nested_too_deep_is_refused`, `test_an_expression_32_levels_deep_parses` |
| Numbers are decimals; a `float` is refused, not converted; `true` stays a boolean | E `test_a_field_and_literals_parse`, `test_a_float_is_refused_because_it_has_already_lost_precision` |
| A number must be finite and fit decimal128, in a literal and in the case file | E `test_a_number_is_finite`, `test_a_literal_outside_decimal128_is_refused`, `test_a_case_file_value_outside_decimal128_is_an_error` |
| `0.1 + 0.2 == 0.3`; 34 digits, half to even, whatever the global context | E `test_numbers_are_exact_decimals`, `test_a_division_keeps_34_significant_digits_whatever_the_global_context`, `test_arithmetic_rounds_half_to_even` |
| Overflow and division by zero are errors; division by zero names the fields and the values (the values dropped in the tutor review of layer 9a: docs/layers/09-case-data.md) | E `test_a_result_too_large_for_decimal128_is_an_error`, `test_division_by_zero_is_an_error` |
| A missing field, `null`, or a value no expression can read is an error, never `false` | E `test_a_field_with_no_value_is_an_error_not_false`, `test_a_value_an_expression_cannot_read_is_an_error`, `test_exists_says_whether_a_field_has_a_value` |
| The evaluator refuses what it doesn't know (a raw dict) | E `test_an_operator_the_evaluator_does_not_know_is_an_error_not_false` |
| No coercion: ordering and arithmetic take numbers, `==` the same type, `cat` texts | E `test_comparing_a_text_with_a_number_is_an_error`, `test_equality_never_coerces`, `test_arithmetic_never_coerces`, `test_cat_joins_texts_only`, `test_in_looks_for_a_value_of_the_list_type` |
| Nothing is truthy: `and`, `or`, `!`, `if` and `where` take booleans | E `test_nothing_is_truthy`, `test_an_if_condition_is_a_boolean`, `test_where_is_a_condition` |
| `and` and `or` evaluate every part, so an error is never hidden | E `test_and_or_evaluate_every_part_so_an_error_is_never_hidden` |
| `if` evaluates only its chosen branch; `sum` reads `value` only for chosen elements | E `test_if_evaluates_only_the_branch_its_condition_chooses`, `test_sum_reads_value_only_for_the_elements_where_chose` |
| `string` keeps a number's own digits | E `test_string_writes_a_value_as_text` |
| `count` and `sum` read a list of records; errors name the element; `item` only inside them | E `test_count_reads_a_list_of_records`, `test_an_element_missing_a_field_is_an_error`, `test_item_is_refused_outside_count_and_sum`, `test_count_sum_and_item_are_checked` |
| The check names the path; a misspelled outcome, a text against a number, an undeclared field, mixed `if` branches are rejected before anything runs | E `test_a_misspelled_outcome_is_rejected_before_anything_runs`, `test_a_text_compared_with_a_number_is_rejected`, `test_an_undeclared_field_is_rejected`, `test_an_if_is_checked_on_both_branches` |
| The check: a reference only against the same system; `in` never takes a reference; a list field only as `over`; an outcome counts as text for `cat` | E `test_a_reference_compares_only_with_the_same_system`, `test_in_exists_and_lists_are_checked`, `test_logic_arithmetic_and_text_are_checked`, `test_check_gives_the_type` |
| The rendering is FEEL-style, bracketed exactly where the stored tree needs it, `and` inside `or` always | E `test_render_each_operator`, `test_render_brackets_only_what_needs_it`, `test_render_literals_and_fields` |
| The renderer refuses what it doesn't know | E `test_render_refuses_what_it_does_not_know` |
| The guide's tables say what the code does | E `test_the_guide_reads_as_the_renderer_renders`, `test_the_guide_refuses_as_the_check_refuses`; P `test_the_guides_plan_state_parses` |
| A state is exactly one kind | P `test_a_state_is_exactly_one_kind` |
| A malformed plan is refused with every problem listed, one line each with its path | P `test_a_malformed_plan_is_rejected`, `test_every_problem_is_listed` |
| A plan's expressions report the same messages; a bare state name is one transition with no condition | P `test_a_malformed_plan_is_rejected`, `test_the_example_plan_parses`, `test_a_wait_state_with_conditional_transitions_parses` |
| A definition is read with exact decimals | Q `test_a_definition_is_read_with_exact_decimals` |
| An approval the engine can't evaluate (`{"now": []}`) stops the case instead of paying | Q `test_an_approval_the_engine_cannot_evaluate_stops_the_case` |
| The quickstart's acceptance tests stay green | Q the first eight tests, `test_an_undeclared_outcome_is_refused` to `test_answering_a_task_needs_its_role` |
