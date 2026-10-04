# Spike: existing standards for plans and expressions

Status: draft for review, 2026-10-04. Research, not product code: nothing in `src/` changes, and the
brief is not edited until the recommendations are agreed.

## The questions

1. **Plans.** Should Ventoux adopt Serverless Workflow 1.0 (the CNCF standard, run on Temporal by
   Zigflow) for plans, offer import/export later, or keep its own format?
2. **Expressions** (design question 11). Keep the JSONata subset of D3, or switch to CEL or to
   structured JSON (an expression tree stored as JSON)?

**Examples** (from the `chartering` prototype, read-only): the `claim-pay` plan
(`examples/cases/insurance-claim/charters/claim-pay.json`) and the small claim case
(`examples/cases/insurance-claim/case.json`, release 1). Each is written in the shape Ventoux
intends (steps, task outcomes with forms, one *when / if / then* rule, approvals from provenance),
as `examples/refund/refund.json` does; the prototype's shape is mentioned only where it matters.

**How we judged.** Gates first, from the non-negotiables: fail closed (a missing field or an
unknown operator is an error, never `false`), deterministic, nothing executed from a definition.
Then design question 11's criteria: readability for people, parsing, typing, provenance analysis,
model output constrained by a JSON Schema, exact diffs, Python support.

## Sources and versions

Every claim below cites one of these, or an experiment in [`spike-dsl/`](spike-dsl/), whose output
is committed next to it (`*.out.txt`).

| Source | Version read |
|---|---|
| [Serverless Workflow specification](https://github.com/serverlessworkflow/specification/tree/v1.0.3): `dsl.md`, `dsl-reference.md`, `schema/workflow.yaml` | v1.0.3 (2026-01-12), the latest release |
| [Serverless Workflow Python SDK](https://github.com/serverlessworkflow/sdk-python) | `main` at ab7b6d4 (2025-11-04); PyPI `serverlessworkflow-sdk` 1.0.0 (2022-04-12) |
| [Zigflow](https://github.com/zigflow/zigflow): README and `docs/` | v0.16.0 (2026-09-27), `main` at 4a20538 |
| [jq](https://jqlang.github.io/jq/manual/), SW's default expression language | jq 1.7 |
| [JSONata](https://github.com/jsonata-js/jsonata) docs and reference implementation | 2.2.2, `master` at 98f23c5 |
| [jsonata-python](https://github.com/rayokota/jsonata-python) | 0.7.0 (2026-07-05) |
| [CEL language definition](https://github.com/google/cel-spec/blob/40a3c90/doc/langdef.md) | `master` at 40a3c90 (2026-09-16) |
| [cel-python](https://github.com/cloud-custodian/cel-python) (`celpy`, pure Python) | 0.5.0 (2026-01-31) |
| [cel-expr-python](https://github.com/cel-expr/cel-python) (Google's wrapper of the C++ implementation) | 0.1.3 (2026-06-25); first release 2026-02-13 |
| Prototype: `chartering/src/core/expr.ts` | 197d519 |

Experiments ran on Python 3.12 with pydantic 2.13.5, jsonschema 4.26.0 and pyyaml 6.0.3, in a
throwaway environment (`uv run --no-project --with …`; each script's docstring has its command).
None of these libraries was added to `pyproject.toml` or `uv.lock`.

## Part A: Serverless Workflow 1.0 for plans

Both examples are written out and validate against the official 1.0.3 schema:
[`claim-pay.sw.yaml`](spike-dsl/claim-pay.sw.yaml) and
[`claim-case.sw.yaml`](spike-dsl/claim-case.sw.yaml) (`check_sw.py`). Comments marked GAP say
what the standard cannot express.

### The `claim-pay` plan

**What fits.** The plan is a short flow, which is what the standard is for: `call` takes any
function name that isn't a built-in protocol, so `call: claims.pay@1` validates (schema,
`CallFunction`); `try`/`catch` with a reusable retry policy covers the retries; `listen` with a
`timeout` covers the 48-hour wait; `switch` and `raise` cover the branches and the failed end;
inputs have a JSON Schema.

**What is missing.**
- *Approvals.* There is no human task. An approval is an event the workflow listens for; who may
  send it, and that it must be someone other than the proposer (D11), is outside the format. So is
  the check that every path to `claims.pay@1` passes an approval (layer 3's `APPROVAL_REQUIRED`):
  nothing in the language says which tasks are approvals.
- *Provenance and input policies.* No value carries where it came from, and no task input can say
  which sources may reach it (D12). The only place for them is the free-form `metadata` map, with
  no semantics: every guarantee would live in our validator, on top of a language that doesn't
  know about it.
- *Catalog semantics.* A name like `claims.pay@1` is accepted, but nothing says it must resolve to
  a registered contract. In the standard, a custom function *is a task definition*, and the spec's
  own example is a `run.script` in JavaScript ([dsl.md, "Creating a Custom
  Function"](https://github.com/serverlessworkflow/specification/blob/v1.0.3/dsl.md#creating-a-custom-function)).
  The capability is defined, not referenced (brief, idea 2).

**What we would have to forbid.** `run` with `container`, `script` (`js`, `python`) or `shell`;
`call` to `http`, `grpc`, `openapi`, `asyncapi`, `a2a` or `mcp` endpoints; catalogs and custom
functions fetched from URLs; `evaluate.mode: loose`, where "if the evaluation fails, it results in
a string with the expression as its content"
([dsl-reference.md, Evaluate](https://github.com/serverlessworkflow/specification/blob/v1.0.3/dsl-reference.md#evaluate));
`listen.to.any: []`, which "listens to all incoming events"; and most of jq (below). Experiment:
a workflow that runs a shell command, a Python script and posts `$context` to any URL is **valid**
against the schema (`check_sw.out.txt`). The standard is safe by restriction at best, never by
construction, which learning question 6 already ruled out for a runtime AI.

### The claim case

The standard models a flow: a position in a list of tasks, with `then` jumps. A case has no
position (brief, idea 4). The closest translation, a `fork` of long-running branches, validates
but loses most of the case:
- milestones, steps that become available when rules allow (`request_documents` is repeatable,
  any time before the assessment), and closing when nothing is left to do (D10). The
  customer-message branch never ends, so the case never closes; the SLA branch can't see that the
  other branch reached `assessed`, so it can't stop;
- task outcomes with forms and roles (D9), approvals (D11), references (D16), declared events
  with trust (an LLM's extracted facts are exported into `$context` like any other value);
- releases, change requests and migration of open cases (D5).

### Expressions in the standard

"All runtimes **must** support the default runtime expression language, which is jq"
([dsl.md, Runtime Expressions](https://github.com/serverlessworkflow/specification/blob/v1.0.3/dsl.md#runtime-expressions)).
jq reads a missing field as `null`, and `null > 1000` is `false`: the approval condition
`if .payout > 1000 then "approval needed" else "no approval" end` answers `"no approval"` when the
payout is unknown. jq also has `now` and `$ENV` (`jq-checks.out.txt`). Runtime expression
arguments include `$secrets` and descriptors with start times. Fail closed and determinism would
both have to be added by us.

### Zigflow and the Python SDK

- **Zigflow** compiles workflows to Temporal (Go). It describes its schema as "a deliberate subset"
  of the standard (`docs/docs/dsl/schema.md`), and also adds to it: its own quickstart workflow
  fails the official schema (`taskQueue` and `workflowType` in `document`, no `namespace` or
  `name`; `check_sw.out.txt`). Putting the task queue in the definition mixes *what* with *where*
  (D5, design question 15). Its expressions add `uuid`, `timestamp` and `$env`, safe on replay only
  "inside a `set` task", which wraps them in a Temporal side effect: determinism by convention,
  documented under "Common mistakes" (`docs/docs/concepts/data-and-expressions.md`). It also
  supports `run` with containers, shell and scripts.
- **No Python SDK for 1.0.** The SDK's README says it "conforms to the Serverless Workflow
  specification v0.8"; its last PyPI release is from 2022. Adopting 1.0 in Python means writing
  our own models for the schema.

### Recommendation A: keep our own format

Don't adopt Serverless Workflow for plans, and don't offer import. Every guarantee that makes a
plan safe for an AI to draft (approval on every path, provenance and input policies, references
to contracts only, no code, fail-closed expressions) would sit outside the standard, so a file
that is valid Serverless Workflow would tell us nothing about whether it is safe. Import would
mean accepting a large language and then refusing most of it. **Export** stays possible later for
an automated plan with no approvals (a sequence of calls and waits), if a team asks for it; it
needs no design decision now. Worth borrowing: errors as RFC 7807 Problem Details with a type URI,
as the standard does, when we design runtime errors (layer 5).

## Part B: expressions

### The claim case in three forms

Run by `expressions.py` against a sample case file, with all four engines agreeing
(`expressions.out.txt`, section 1). Fields are read by name from the case file, as in
`refund.json`. The prototype's `result.signal.name = 'ASSESSED' ? result.signal.payload.amount : 0`
has no counterpart: with D9, the `approve` outcome of `assess` sets `payout` through its form.

| Where | JSONata subset | CEL | Structured JSON |
|---|---|---|---|
| `pay`: when | `assess.outcome = "approve" and payout > 0` | `assess.outcome == "approve" && payout > 0.0` | `{"and": [{"=": [{"field": "assess.outcome"}, "approve"]}, {">": [{"field": "payout"}, 0]}]}` |
| `pay`: approval when | `payout > 1000` | `payout > 1000.0` | `{">": [{"field": "payout"}, 1000]}` |
| `deny`: when | `assess.outcome = "deny"` | `assess.outcome == "deny"` | `{"=": [{"field": "assess.outcome"}, "deny"]}` |
| rule `documents_arrived`: if | `event.count > 0` | `event.count > 0` | `{">": [{"field": "event.count"}, 0]}` |
| `pay`: input `amount` | `payout` | `payout` | `{"field": "payout"}` |
| `deny`: input `subject` | `"Claim " & claim_id & ": decision"` | `"Claim " + claim_id + ": decision"` | `{"concat": ["Claim ", {"field": "claim_id"}, ": decision"]}` |
| `intake`: update | `result.facts.estimated_damage` | `result.facts.estimated_damage` | `{"field": "result.facts.estimated_damage"}` |
| rule `customer_wrote`: update | `event.text` | `event.text` | `{"field": "event.text"}` |
| question 7 (not in the case) | `$sum(items[risk = "high"].amount) > 10000` | none in the standard library | `{">": [{"sum": {"over": …, "where": …, "value": …}}, 10000]}` |

Two things the table shows. Inputs and updates are almost all **plain field paths** (3 of 4),
so the language matters most for conditions. And CEL's `1000.0` is not a typo: with `payout` declared `double`, `payout > 1000` fails the type
check, because "comparisons require strict type equality at type-check time"
([langdef.md, Comparison Operators](https://github.com/google/cel-spec/blob/40a3c90/doc/langdef.md#comparison-operators)).

### Findings, criterion by criterion

**Fail closed** (gate). The approval condition when `payout` has no value yet (section 2):

| | `payout > 1000` | `… ? "approval needed" : "no approval"` | `payout > 1000 or estimated_damage > 5000` |
|---|---|---|---|
| JSONata (reference JS and jsonata-python) | `undefined` | `"no approval"` | `false` |
| CEL (both libraries) | error | error | error |
| Structured sketch | error | error | error |

JSONata does this by design: "No errors are thrown as a result of non-existing data in the input
document" ([docs/simple.md](https://github.com/jsonata-js/jsonata/blob/master/docs/simple.md)).
A string built from a missing value silently drops it (`"Pay " & $string(payout)` gives
`"Pay  on CLM-7"`). The prototype inherits this: its `holds()` turns the result into
`Boolean(...)` (`chartering/src/case/runtime.ts:243`), so an approval condition on a missing field
reads as "no approval needed", the same fail-open the tracer review found for an unknown operator.
(In the claim case `pay`'s own condition, `payout > 0`, is false too, so nothing is paid; the
approval is not what stops it.) CEL
fails closed: "an unbound variable evaluates to an error" (langdef.md, Evaluation). Two CEL
subtleties: `&&` and `||` may *absorb* an error when the other side decides the result ("if that
evaluation produces a runtime error, it will be ignored", Logical Operators), which is sound logic
but means an error can disappear; and cel-expr-python *returns* an error as a value, whose
`.value()` is a non-empty, truthy string, rather than raising. The structured sketch evaluates
every operand of `and`/`or`, so an error is never hidden.

**Determinism** (gate). JSONata has `$now`, `$millis` and `$random`; jq has `now`; Zigflow adds
`uuid`. CEL's standard library has no clock or randomness, and the language is "side-effect-free"
and "terminating" (langdef.md, Overview). Structured JSON has only the operators we define, so a
non-deterministic function cannot be written, not merely refused.

**Parsing and enforcing the subset.** Section 3, each candidate checked before anything runs:

| Rejected before running? | JSONata (our walk of the AST) | celpy (parse only) | cel-expr-python (type checker) | Structured (Pydantic + type check) |
|---|---|---|---|---|
| `$now()` / `now()` | yes | no | yes | yes (unknown operator) |
| `$map` / `items.map(…)` | yes | no | no; yes with `exclude_macros` | yes |
| variable binding | yes | no | yes | yes |
| misspelled outcome `"aprove"` | no | no | no | **yes** |
| `payout > "1000"` | no | no | yes | yes |
| misspelled field `payot` | yes (field list) | no | yes | yes |

- JSONata: the subset check walks jsonata-python's **internal** AST (`Jsonata(...).ast`, symbols
  with `type`, `lhs`, `steps`…), which is not a documented API. The prototype's equivalent is 265
  lines (`src/core/expr.ts`), including a guard against catastrophic regular expressions and an
  evaluation-step counter. One library bug found: comparing a string with a number raises
  Python's `IndexError` (a broken message template) instead of JSONata's `T2009` error.
- CEL: cel-expr-python's checker is strong, and the language can be narrowed by configuration
  (`stdlib.exclude_macros`, `exclude_functions`; its `cel_env_test.py`), though the error for an
  excluded macro is confusing ("undeclared reference to 'i'"). It exposes no syntax tree.
  cel-python exposes a parse tree but, by its README, has no type checker ("Rather than try to
  pre-check types, we'll rely on Python's implementation").
- Structured: no parser; Pydantic validates the shape. Cost found: an unknown operator yields 38
  union errors; the real version needs one clear message ("`now` is not an operator; …"), as the
  brief requires of every validator error.

**Typing.** Only structured JSON caught the misspelled outcome, because its checker knows
`assess.outcome` is a closed list (`approve`, `deny`; D9). CEL has no enumerated strings, so
`assess.outcome == "aprove"` type-checks; JSONata has no static types at all. CEL's types also leak
an `int`/`double` distinction to authors (`1000.0`), where the case file has one `number`.

**Provenance analysis** (which fields does it read?). Section 4: all three give the right fields
for the claim case, at very different cost. Structured: a 15-line walk over our own models.
JSONata: a walk of the internal AST. CEL: cel-expr-python has no API for it, so a second parser
(celpy) is needed; its tree is the concrete grammar (`expr → conditionalor → … → member_dot`), and
our walker needed two fixes before nested paths came out right.

**Model output constrained by a JSON Schema** (layer 15). For JSONata or CEL the schema can only
say `{"type": "string"}`: a model's expression is checked after it is produced. The structured
form has a schema generated from its Pydantic models (18 definitions, recursive through `$ref`);
`{"now": []}` is invalid against it before anything else runs (section 6). Whether a given
provider's constrained decoding accepts recursive schemas is to check in layer 15.

**Exact diffs and the release digest** (D5). `payout > 1000`, `payout>1000` and `(payout > 1000)`
mean the same and hash differently (section 5): a string form needs parsing and re-printing before
the release digest or the semantic diff can use it. Structured JSON, serialised canonically as
layer 1 already does for contracts, has one form, and a diff names the node that changed.

**Readability for people.** Raw strings read better; raw structured JSON is clumsy (see the
table). But design question 11 notes few people read the stored form: developers read the builder
(layer 14), analysts the plain-language rendering, reviewers the semantic diff. A one-line text
rendering is a small printer, with no parser (`structured.render`, which printed the readable
column of `expressions.out.txt`).

**Python support.** jsonata-python is a complete, maintained port, but we use only its evaluator
and must work around its fail-open semantics. CEL's best Python checker is a 0.1.x wrapper of C++,
first released in February 2026; the pure-Python one has no checker. Structured JSON needs no
library: the sketch's parser is Pydantic, its evaluator about 100 lines (`structured.py`). The
other side of that: we own the language, so we must keep it small, and the inbox (TypeScript, D4)
needs a port of the evaluator, checked by the conformance suite.

### Recommendation B: store expressions as structured JSON

Switch D3's stored form from JSONata strings to **structured JSON**, the middle path of design
question 11: people write readable code, the stored JSON is structured.
- **Written by** the Python builder (`payout > 1000` with typed field objects, layer 14) and, at
  runtime, by models constrained by the published JSON Schema (layer 15). No text syntax is
  parsed in v1.
- **Read as** a one-line rendering in diffs and reviews, and plain language for analysts.
- **The operators** are D3's list, kept short: field paths, literals, comparisons, `and`/`or`/`not`,
  `+ - * /`, `if`, `concat` and `string`, `exists`, `count`, `sum` with a simple `where`. Anything
  else is a compute activity (learning question 7).
- **Checked** against the case's declared field types, outcomes as closed lists; evaluated by a
  small evaluator that treats a missing field, a wrong type or an unknown operator as an error,
  and evaluates every operand of `and`/`or`.
- **Taken from CEL:** strict types checked before running, and errors instead of defaults. **Not
  taken:** its separate `int` and `double`, and error absorption by `&&` and `||`.

Why not keep JSONata: it fails open by design, has no types, includes non-deterministic functions,
and the subset check depends on an undocumented AST. Why not CEL: the best fit on the gates, but
in Python its checker is young and exposes no tree (so provenance needs a second parser), it can't
catch a misspelled outcome, its numeric types leak to authors, and a model's output is still a
string to check after the fact.

**If agreed, what changes** (in the PR that follows the review, not this one): D3 and design
question 11 in the brief, the D4 stack (no `jsonata-python`), the expressions line of `CLAUDE.md`'s
non-negotiables, and layer 2 in the curriculum ("JSONata" becomes the structured form; the
negative test `$now()` becomes "an unknown operator is rejected with a clear message"). The
tracer's minimal form (`=`, `>`, `field`) is already structured, so layer 2 grows it rather than
replacing it.

## Check yourself

> Which of our guarantees could not be expressed as a restriction of the standard, and why?
