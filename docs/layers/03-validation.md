# Layer 3: static validation

Status: part 1 (the refactor and the catalog fixes) agreed and built, 2026-10-05, slices 1–7;
part 2 (the validator) agreed and built, 2026-10-05, slices 1–9.

## What this layer is for

Layer 2 made plans and expressions data. Layer 3 proves things about a definition by reading it,
before anything runs: references exist, every state is reachable, every expression is well typed
at its state, and every high-risk activity sits behind an approval on every path. The validator
returns every issue at once, each as `(path, code, message)`.

It opens with a refactor, so the two files it builds on are easy to read first.

## Part 1: the refactor

### Rules for the move

- **A pure move.** No logic changes. Every existing test passes, and no test body changes: only
  `tests/test_catalog.py`'s import block, in its own commit, so the diff shows nothing else moved.
- **The contract hashes don't move.** `contracts.lock.json` is untouched: the hash reads the
  contract's fields and schemas, never the module it lives in.
- **The layer boundary still holds.** The new modules are under `core`, so the boundary test
  checks them as before.

### `core/expressions.py` becomes a package

The arrows run one way: every module below imports `model`; besides that, only `evaluate`
imports `render`, to name the fields in a division-by-zero message (`amount / items`). Nothing
imports `parse`, `check` or `evaluate` except `__init__`.

| Module | Holds |
|---|---|
| `expressions/model.py` | what an expression is: `OPERATORS`, the decimal128 `CONTEXT` and `fits_decimal128`, `Value` and `Expression`, one model per operator, the field types, `ExpressionInvalid` and `ExpressionError`, and `kind` (a value's type name, which parse, check and evaluate all use) |
| `expressions/parse.py` | JSON to an expression: `parse_expression`, the depth limit, the `item` walk, `in`'s list |
| `expressions/check.py` | `check`: an expression's type against the declared fields |
| `expressions/evaluate.py` | `evaluate`: an expression's value against the case file, failing closed; `Element`, the list record `item` reads |
| `expressions/render.py` | `render`: one line in FEEL style, such as `review.outcome = "approve" and amount > 100` |
| `expressions/__init__.py` | re-exports the public names, listed in `__all__` |

Five modules, not the curriculum's four: "what an expression is" and "turning JSON into one" are
two jobs, and together they would be about 540 lines. `plan.py`, `runner.py`,
`test_expressions.py` and `test_plan.py` keep importing from `ventoux.core.expressions`.

### `core/catalog.py` becomes four modules

| Module | Holds |
|---|---|
| `core/contract.py` | `ActivityContract` and its parts (`Timeouts`, `RetryPolicy`, `Display`), the reference pattern, and what a contract refuses |
| `core/contract_hash.py` | `contract_hash`: what a contract promises, as a SHA-256 |
| `core/catalog.py` | `Catalog` (`register`, `get`), `NotInCatalog`, `ContractConflict` |
| `core/hash_check.py` | `check_hashes`: what CI reports against `contracts.lock.json` |

Four, not the curriculum's three: `Catalog.register` needs `contract_hash`, and `check_hashes`
needs `Catalog`, so putting the hash and the CI check in one file makes an import cycle. Splitting
off `hash_check.py` makes a line, `contract` ← `contract_hash` ← `catalog` ← `hash_check`, with no
`TYPE_CHECKING` import hiding the cycle.

Readability, as agreed in the tutor session:

- a one-line comment on each field saying what it means;
- a short comment on each Pydantic idiom the first time a file uses it (`model_config`,
  `Field(gt=0)`, `@model_validator(mode="before")` and `mode="after"`, `model_validate`);
- the reference pattern explained: a named function, `is_reference(text)`, with the regular
  expression's parts described in its comment;
- every message in one shape, what is wrong and then what to do. Three messages gain their "what
  to do" (the guide's table shows them): a key that isn't an input field names the input's fields;
  outcomes without matching titles say "give each outcome exactly one title in
  `display.outcomes`"; an unknown version in `get` says "use a registered version, or register
  this one first" (or, when no version is registered, "register its contract first, or check the
  name"). Pydantic's own messages for one field (`Input should be greater than 0`) stay as
  Pydantic writes them;
- decisions cited as "(brief, Dn)", stating the rule in plain words first.

The guide's example now imports from `ventoux.core.contract`. That is what the user sees of the
split, and the guide's test runs it, so it fails until the split is done.

### Three fixes

**1. `register` checks every contract again.** `model_copy(update=...)` builds a new object and
runs no checks (learning question 31), so a copy with risk `"hihg"` and a `write` with no
idempotency key was accepted into the catalog. Two parts, both needed:

- the shared config gets `revalidate_instances="always"`, so that validating a contract also
  re-checks the parts it holds (a copied `Timeouts` with a bad value);
- `register` calls `ActivityContract.model_validate(contract)` before storing it. With the config
  alone, nothing would call validation at all (slice 5 showed it: both tests still failed). It
  stores the object it was given, now checked and frozen, so `get` still returns that same object
  (an existing test caught the re-checked copy being stored instead).

**2. Every rule is running.** Each rule a contract enforces, with an example it refuses:

| Rule | Refused example |
|---|---|
| a field the contract doesn't know | `queue="payments"` |
| a field a part doesn't know | `Timeouts(heartbeat=5, …)` |
| a name or version no reference could match | `name="Payments Refund"`, `version=0` |
| a side effect needs an idempotency key | `effect="write"`, `idempotency_key=None` |
| the key is an input field | `idempotency_key="request_id"` |
| outcomes and display titles match | `outcomes=["declined"]`, no title |
| timeouts, intervals and attempts above 0 | `maximum_attempts=0` |
| a backoff of at least 1 | `backoff_coefficient=0.5` |
| risk and effect from their lists | `risk="hihg"`, `effect="delete"` |

One parametrized test runs this table twice for each row: building the contract, and registering
a valid contract copied with the row's change. If a rule's decorator is lost, or `register`
stops checking, its row fails. The test checks behaviour, not Pydantic's list of validators.
Checked in slice 6 by breaking the code on purpose: without `outcomes_have_titles`'s decorator,
exactly its two rows fail; without the check in `register`, exactly the 14 registered rows fail.

**3. Decision references are real.** A test reads every `.py` file under `src/`. Every decision
cited (`D` and a number, as a whole word) must:

- be written in the form `(brief, Dn` (so the reader knows where to look);
- be a heading `### Dn.` in `docs/BRIEF.md`;
- not be marked superseded in that heading (D3 is: cite D20).

A bare `D5` fails, so a citation can't slip past the check by its form. Today that means
`catalog.py` (moved anyway) and four comments in `case/runner.py` (D9, D10, D11), rewritten
there. Slice 7 found a fifth: the expressions package's docstring, `(layer 2; brief, D20)`,
which names its source but not in the form; rewritten rather than loosening the check. The check
lives in the test file, as layer 0's boundary check does: it reads files, so it isn't product code.

### Seams the tests use

- Everything the existing tests use, unchanged.
- `ActivityContract(...)`, `ActivityContract.model_copy(update=...)`, `Catalog.register`.
- The source files under `src/` and `docs/BRIEF.md`, read as text.
- The guide's example, run by its existing test.

### Slices, in order

1. The guide imports from `ventoux.core.contract`: its test fails (no such module). Split
   `catalog.py` into its four modules, change `test_catalog.py`'s imports only; everything green.
2. Split `expressions.py` into its package; everything green, no test changed.
3. Readability in the catalog modules: field comments, Pydantic comments, `is_reference`.
4. Negative: the messages that gain "what to do" (the guide's table, in a test); then the
   messages.
5. Negative: a copy with `risk="hihg"` registers. Then `revalidate_instances` and
   `model_validate` in `register`.
6. The rule table, built and registered, row by row.
7. Negative: a bare `D10` in a source file fails the reference check, and so does a cited D3.
   Then the check, and `runner.py`'s comments rewritten.

## Part 2: the validator

`parse_plan` (layer 2) checks a plan's shape; `validate` checks its meaning, by reading the plan
as a graph: the states are its nodes, the transitions in each `on` its arrows. User-facing
description: `docs/guides/plans.md`, written first.

Drawn on: the prototype's `src/core/validate.ts` (issues as `{path, code, message}`, reachability
forward from the start and backward from the finals, an approval as a wait's approve transition,
"approval required" and "approval reused" as reachability over the arrows that aren't approvals).
Ours drops its `ERROR` event (an undeclared failure needs a person, D17), its `resultAs` and
`assign` (layer 2 left them out), and its default-transition rules (none holding is an error at
run time, layer 5); it adds the engine's idempotency key and the reserved `approve` and `timeout`.

### Decided in the session

1. **An approval is a wait plus an outcome**, as in the prototype: no new kind of state. The
   outcome `approve` is reserved: a wait offering it is an approval, and must offer exactly
   `approve` and `reject` (brief, D11). Only an approval's `approve` transitions count as
   approving. The trade-off, accepted: the validator infers an approval from a name, so a wait
   meant for something else that offers `approve` would approve what follows it; the exact pair
   and the reserved word (the guide says to use `accept` or `confirm`) narrow that.
2. **Plans are strict:** every path to a high-risk activity passes an approval. A condition is a
   fork the validator can't see through, so a plan can't skip the approval for small amounts; a
   case step's `approval.when` (brief, D11) is layer 8's question. Plans are what an AI may draft
   (brief, D13 and D14), and there the approval stops a model's mistake.
3. **Roles wait for layer 7**, which adds them to the approval wait, with the check "no approval
   without roles on a high-risk step" (brief, D11).
4. **The seam is `validate(plan, catalog) -> list[Issue]`** on a parsed `Plan`. Shape problems
   stay `PlanInvalid`; meaning problems are issues. One list for both is the AI loop's need
   (layer 15).
5. **A wait's timeout is the event `timeout`**, handled exactly when the wait declares a
   `timeout`; no outcome may be named `timeout`.
6. **Document first:** `docs/guides/plans.md`, its first section being what `ventoux check`
   proves.

### The issue

`Issue(path, code, message)`, a frozen dataclass. `path` is where in the plan, in layer 2's style
(`states.pay.inputs.amount`, `states.check_order.on.done[1]`, `initial`). `code` is one of the
codes below. `message` says what is wrong, then what to do. The issues come in the plan's order:
states as written, then the graph checks.

### The checks

What each state is checked for:

- **Every target is a state** (`UNKNOWN_TARGET`), and `initial` too.
- **An activity state:**
  - its activity is in the catalog (`UNKNOWN_ACTIVITY`, with `Catalog.get`'s message, which names
    the versions that exist);
  - its inputs are the contract's input fields (`UNKNOWN_INPUT`), every required field is given
    (`MISSING_INPUT`), and the idempotency key field is never given: the engine fills it
    (`ENGINE_INPUT`), so it isn't required either;
  - its `on` handles exactly `done` and each outcome the contract declares (`UNKNOWN_EVENT`,
    `MISSING_EVENT`): an unhandled `declined` would leave the plan with nowhere to go.
- **A wait state:**
  - its `on` handles exactly its outcomes, plus `timeout` if it declares one (`UNKNOWN_EVENT`,
    `MISSING_EVENT`);
  - no outcome is named `timeout` (`RESERVED_OUTCOME`);
  - a wait offering `approve` offers exactly `approve` and `reject` (`APPROVAL_OUTCOMES`).
- **Every expression** goes through layer 2's `check` against the plan's `fields`
  (`EXPRESSION_INVALID`, with the check's message and its path inside the expression): each
  input, and each transition's `when`, which must give a boolean. A plan can't bind new values,
  so the fields are the same at every state.

Then the graph, built from the transitions whose target is a state:

- **Reachable** (`UNREACHABLE_STATE`): every state can be reached from `initial`.
- **Can end** (`NO_PATH_TO_FINAL`): from every state, some final state can be reached (searched
  backwards from the finals).
- **Approval required** (`APPROVAL_REQUIRED`): follow every arrow from `initial` except an
  approval's `approve`; a high-risk activity reached that way can run unapproved. The message
  names the shortest such path (`check_order → pay`).
- **Approval reused** (`APPROVAL_REUSED`): from each high-risk activity, follow every arrow except
  an approval's `approve`; another high-risk activity reached that way, or the same one in a loop,
  would run on the same approval (brief, D11: one approval unlocks one run).

An activity the catalog doesn't hold has no risk to read. It is already an issue
(`UNKNOWN_ACTIVITY`), so the plan is refused, and the approval checks don't add a second one
for it.

**Fail closed:** `validate` given anything but a parsed `Plan` raises `TypeError`, never returns
an empty list as if the plan were fine.

Decided while building (slices 6 to 9):

- If `initial` isn't a state, the graph checks don't run: with no start, every state would be
  "unreachable", burying the one real problem.
- An unreachable state gets only `UNREACHABLE_STATE`, not also `NO_PATH_TO_FINAL`: one cause, one
  issue. A state whose every way out is broken gets `NO_PATH_TO_FINAL` as well as the broken
  targets, since that is true and is what a reader of the plan needs to know.
- A wait offering `approve` with other outcomes is `APPROVAL_OUTCOMES` and approves nothing, so the
  activity behind it is also `APPROVAL_REQUIRED` (fail closed).
- The guide's table was checked by breaking it: a changed word, and an unknown code, each fail.

Not in this layer: whether an input's type matches the contract's (the contract's schema would
need mapping to field types; layer 5 checks inputs when the step runs); a transition listed after
one with no `when`, which can never be taken (not on the agreed list); provenance and sink
policies (layer 4); roles (layer 7).

### Files

- `src/ventoux/core/validate.py`: `Issue`, `validate`, the checks of each state against its
  contract, and the approval rules.
- `src/ventoux/core/graph.py`: the plan as a graph (`Arrow`, `arrows`) and the searches along it
  (`reach`, `shortest_path`). Moved out of `validate.py` after slice 8, when it held two ideas, as a
  pure move with no test changed.
- `tests/test_validate.py`; the plans guide's example and table run in it.

### Seams the tests use

- `parse_plan(data)` (layer 2), then `validate(plan, catalog) -> list[Issue]`.
- `testing.CATALOG`, the development catalog: `orders.lookup@1` (low), `payments.refund@1`
  (high), `letters.draft@1` (low).
- The guide: its example plan has no issues; each table row's message is what `validate` says.

### Slices, in order

1. Negative: `validate` of something that isn't a parsed plan raises. Negative: an unknown
   `initial` and an unknown target. Then the guide's example plan has no issues.
2. Negative: an activity not in the catalog.
3. Negative: an unknown input, a missing one, the idempotency key set by the plan.
4. Negative: an activity's unknown event and unhandled outcome; a wait's; `timeout` without a
   declared timeout, and a declared timeout not handled; an outcome named `timeout`.
5. Negative: an undeclared field in an input; a `when` that gives a number.
6. Negative: an unreachable state; a state from which the plan can't end.
7. Negative: `approve` offered with `edit`. Negative: the guide's fork, `APPROVAL_REQUIRED`
   naming `check_order → pay`. Then the guide's example passes.
8. Negative: two high-risk activities after one approval; a loop back to the same one.
9. A plan with several problems lists them all; the guide's table runs as a test.

## Promises

Each claim part 1 makes about behaviour, and the test that fails if it isn't true. `C` is
`tests/test_catalog.py`, `R` is `tests/test_decisions.py`.

| Promise | Test |
|---|---|
| The split changes no behaviour | every existing test, no body changed |
| No contract's hash changes | C `test_every_development_contract_matches_its_recorded_hash` |
| The guide's example runs as written, from `ventoux.core.contract` | C `test_the_guides_example_is_the_development_refund_contract` |
| Every rule in the table refuses its example when a contract is built | C `test_every_rule_refuses_a_contract_that_breaks_it` |
| `register` refuses a copy that breaks any rule in the table, nested parts included | C `test_every_rule_runs_again_when_a_copy_is_registered`, `test_a_copy_that_breaks_the_rules_is_refused_at_registration`, `test_a_copy_with_a_broken_part_is_refused_at_registration` |
| Every catalog refusal says what is wrong, then what to do, word for word as the guide shows | C `test_the_guides_refusals_are_what_the_catalog_says` |
| Every decision cited in `src/` is in the form `(brief, Dn`, exists, and isn't superseded | R `test_every_decision_cited_in_src_is_in_the_brief_and_current` |
| A bare, superseded or unknown decision is refused with what to write instead | R `test_a_bare_decision_is_refused`, `test_a_superseded_decision_is_refused`, `test_a_decision_the_brief_does_not_have_is_refused`, `test_a_decision_cited_with_its_source_is_accepted` |
| `get` returns the very contract registered | C `test_a_registered_contract_is_found_by_its_reference` |
| `core` imports no Temporal or LLM code, in the new modules too | `tests/test_layers.py`, unchanged |

Part 2's promises; `V` is `tests/test_validate.py`.

| Promise | Test |
|---|---|
| `validate` refuses anything but a parsed plan, never returning "no issues" for it | V `test_only_a_parsed_plan_is_validated` |
| `initial` and every target name a state, a target in a list found by its position | V `test_initial_must_be_a_state`, `test_every_target_must_be_a_state`, `test_a_target_in_a_list_is_found_by_its_position` |
| Every activity is in the catalog, with the catalog's message | V `test_every_activity_is_in_the_catalog` |
| Inputs are the contract's fields, the required ones given, the idempotency key never | V `test_an_input_the_contract_does_not_take_is_refused`, `test_an_input_the_contract_needs_must_be_given`, `test_the_idempotency_key_is_filled_by_the_engine_never_by_a_plan` |
| An activity handles exactly `done` and its declared outcomes; a wait exactly its outcomes and `timeout` if declared; no outcome is named `timeout` | V `test_an_activity_never_gives_an_event_its_contract_does_not_declare`, `test_every_outcome_an_activity_declares_is_handled`, `test_a_wait_never_gives_an_outcome_it_does_not_offer`, `test_every_outcome_a_wait_offers_is_handled`, `test_a_wait_without_a_timeout_never_times_out`, `test_a_wait_with_a_timeout_handles_it`, `test_no_outcome_is_named_timeout` |
| Every input and condition passes the expression check, the path inside it kept; a condition gives a boolean | V `test_an_input_reads_only_declared_fields`, `test_a_condition_gives_a_boolean`, `test_a_condition_is_checked_inside_too` |
| Every state is reachable, and from every state the plan can end | V `test_every_state_is_reachable`, `test_from_every_state_the_plan_can_end` |
| A wait offering `approve` offers exactly `approve` and `reject`, and otherwise approves nothing | V `test_an_approval_offers_exactly_approve_and_reject` |
| No high-risk activity is reachable without passing an approval's `approve`, and the message names the shortest path; a low-risk one needs none | V `test_a_high_risk_activity_is_never_reached_without_an_approval`, `test_a_low_risk_activity_needs_no_approval` |
| One approval unlocks one high-risk run: no second one, and no loop back, without a new approval | V `test_one_approval_unlocks_one_high_risk_run`, `test_a_loop_back_to_a_high_risk_activity_needs_a_new_approval`, `test_a_loop_through_the_approval_is_approved_each_time` |
| Every problem is listed, not only the first | V `test_every_problem_is_listed_not_only_the_first` |
| The plans guide says what the code does: its example has no issues, its fork gives the message shown, its table lists every code with `validate`'s own message | V `test_the_guides_example_has_no_issues`, `test_a_high_risk_activity_is_never_reached_without_an_approval`, `test_the_guide_lists_every_issue_code`, `test_the_guides_messages_are_what_validate_says` |
