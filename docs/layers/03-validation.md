# Layer 3: static validation

Status: draft, 2026-10-05. Part 1 (the refactor and the catalog fixes) is up for agreement; part 2
(the validator) is written after part 1 is merged into this branch and agreed separately.

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
- `register` stores `ActivityContract.model_validate(contract)`, never the object it was given
  unchecked. With the config alone, nothing would call validation at all.

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

**3. Decision references are real.** A test reads every `.py` file under `src/`. Every decision
cited (`D` and a number, as a whole word) must:

- be written in the form `(brief, Dn` (so the reader knows where to look);
- be a heading `### Dn.` in `docs/BRIEF.md`;
- not be marked superseded in that heading (D3 is: cite D20).

A bare `D5` fails, so a citation can't slip past the check by its form. Today that means
`catalog.py` (moved anyway) and four comments in `case/runner.py` (D9, D10, D11), rewritten
there.

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

To be written and agreed after part 1. One question to settle first: how a plan expresses an
approval. Layer 2's plans have none, and D11 puts an approval on the step, with roles.

## Promises

Each claim part 1 makes about behaviour, and the test that fails if it isn't true. `C` is
`tests/test_catalog.py`, `R` the new reference test (file to be named in slice 7).

| Promise | Test |
|---|---|
| The split changes no behaviour | every existing test, no body changed |
| No contract's hash changes | C `test_every_development_contract_matches_its_recorded_hash` |
| The guide's example runs as written, from `ventoux.core.contract` | C `test_the_guides_example_is_the_development_refund_contract` |
| Every rule in the table refuses its example when a contract is built | C the rule table, built (slice 6) |
| `register` refuses a copy that breaks any rule in the table, nested parts included | C the rule table, registered (slices 5 and 6) |
| Every catalog refusal says what is wrong, then what to do | C the guide's refusal table run as a test (slice 4) |
| Every decision cited in `src/` is in the form `(brief, Dn`, exists, and isn't superseded | R (slice 7) |
| `core` imports no Temporal or LLM code, in the new modules too | `tests/test_layers.py`, unchanged |
