# Fix: a contract's hash, independent of pydantic

**Set aside, 2026-11-10:** the same fix was made in #98 (`docs/layers/fix-contract-rendering.md`),
which goes ahead instead; this branch has no pull request and won't merge. Kept for its record:
it differs in keeping a field's description in the promise, allowing a `bool` or text default,
and leaving pydantic unbounded with the lock on 2.13.5.

A fix, not a layer: no warm-up. Found in 20c (`docs/layers/20-deployment.md`, "Decided while
building 20c"), where the package's fresh install resolved pydantic 2.14.3 and three contracts
hashed differently; 20c bounded pydantic below 2.14 (D82) and left this fix for later. Branch
`fix-contract-hash`, from `layer-20c-package` (it lifts that bound and relies on the `package`
job); its pull request opens once #97 is merged, rebased onto `main`.

Status: 2026-11-10, the design agreed (option B, both choices as recommended); D83 written; the
seams and tests agreed and built.

## The cause

`promise_of` (`src/ventoux/core/promise.py`) makes a contract's input and output schemas with
pydantic's `model_json_schema()`, and the hash is the SHA-256 of that promise (method 1, D5). So
the hash changes whenever pydantic changes how it writes something down, though the promise
didn't change. Checked on `layer-20c-package`, every development contract's promise under 2.13.5
and 2.14.3, leaf by leaf (`promise_changes`):

```
kyc.check@1        output.properties.risk_score.anyOf: [number, {pattern: …, type: string}] -> [number, {type: string}]
ledger.post@1      input.properties.amount.anyOf:      the same
payments.refund@2  input.properties.amount.anyOf:      the same
```

One difference only: 2.13 adds a `pattern` to a decimal's string form, and 2.14 drops it. The
conformance catalog file (`src/ventoux/conformance/catalogs/development.json`) is written through
`promise_of`, so it differed too; `case/diff.py` makes its own copy of the promise the same way.

## The design (D83)

A contract's field is already one of a closed set (D20, D36): an input a `Decimal`, a `str`, a
`bool` or a `Literal` of texts, an output a `Decimal`, a `str`, a `bool` or a `date`, each possibly
optional. Ventoux's own meaning comes from its own markers (a `Policy`, a reference's system, an
output's source). So **Ventoux writes each field's description itself**, from its type and its
markers, never asking pydantic, and writes it **exactly as pydantic 2.13.5 did**: every hash
recorded so far (the locks, the release records, the recorded histories, the conformance file)
stays valid, and the method stays 1.

What 2.13.5 wrote, and so what Ventoux writes (probed on the locked environment):

| Field | Written |
|---|---|
| `str` | `{"type": "string", "title": T}` |
| `bool` | `{"type": "boolean", "title": T}` |
| `Decimal` | `{"anyOf": [{"type": "number"}, {"pattern": P, "type": "string"}], "title": T}`, P the decimal pattern |
| `date` | `{"format": "date", "type": "string", "title": T}` |
| `Literal["x"]` | `{"const": "x", "type": "string", "title": T}` |
| `Literal["x", "y"]` | `{"enum": ["x", "y"], "type": "string", "title": T}` |
| optional `X` | `{"anyOf": [X's forms…, {"type": "null"}], "title": T}`: a decimal's two forms flattened in |
| a default | `"default": V`, for `None`, a `bool` or a text |
| a description | `"description": D`, from `Field(description=…)` |
| Ventoux's markers | `x-input-policies`, `x-reference`, `x-source`, as their hooks write them today |
| the model | `{"properties": …, "required": [in field order], "title": class name, "type": "object"}`, and `"description"` from its docstring, cleaned as pydantic cleans it |

T is the field's name as pydantic titles it (`risk_score` → `Risk Score`).

**Refused when the catalog is built (fail closed):** anything on a contract's field or model that
Ventoux doesn't describe, since the hash would then cover a rule the engine neither writes down
nor enforces:
- a constraint (`Field(ge=0)`, `max_length`, `pattern`, …: pydantic writes `ge=0` as
  `"minimum": 0.0`, a binary float in a promise about exact decimals);
- any other metadata that isn't one of Ventoux's markers; `Field(title=…, examples=…,
  json_schema_extra=…, alias=…)`; a model's `json_schema_extra` or `title`;
- a default other than `None`, a `bool` or a text (a `Decimal` or a `date` default).

No catalog in the repository uses any of them. Each refusal says what is wrong, then what to do.

**Prose stays in the promise:** a model's docstring and a field's description are hashed, as
before (design question 16 already says a docstring edit changes the hash). Whether prose belongs
in a promise at all, when `display` doesn't, is left open: a decision of its own.

**The bound is lifted:** `pydantic>=2.13.5`, with no upper bound, D82 amended. The `package` job's
fresh install, resolving the newest pydantic, is the live proof.

## Seams and tests (proposed)

| Seam | What it is |
|---|---|
| `described(model) -> dict` (`core/described.py`) | the JSON Schema Ventoux writes for a contract's input or output model, as 2.13.5 wrote it |
| `promise_of(contract)` | unchanged, its schemas now `described(…)`'s |
| `Contract` | refuses, when a catalog is built, what `described` doesn't describe |
| `case/diff.py` | its copy of the promise from `described`, too |

**The tests, in order** (each watched failing first):
1. Negative first: a contract whose field carries a constraint (`ge`, `max_length`, `pattern`),
   other metadata, a `Field(title=…)` or a `json_schema_extra`, or a `Decimal` default, is
   refused when built, naming the contract and the field and saying what to do
   (`tests/test_described.py`, beside the contract field rules in
   `test_case_validation.py`).
2. `described` writes every allowed shape as pydantic 2.13.5 did: each shape in the table above
   (each type, optional or not, with and without a default, a description, each marker, a
   docstring), compared with a committed file recorded under 2.13.5
   (`tests/described/pydantic-2.13.5.json`), never with the pydantic installed.
3. `promise_of` never asks pydantic for a schema: `BaseModel.model_json_schema` made to raise,
   every development contract's promise is still made.
4. Every development contract hashes as recorded: the promises and hashes recorded under 2.13.5
   (`tests/described/development-promises.json`), equal byte for byte; the conformance catalog
   file unchanged (`ventoux conformance --unchanged`).
5. `case/diff.py`'s promise comes from `described`: the same patch as test 3, a package diff still
   made.
6. The bound is lifted: pydantic's requirement has no upper bound (20c's bound test replaced), and
   the package job's install is unbounded.

**Never here:** a new hash method, a change to any recorded hash, publishing.

## Decided while building

- **The recordings are made by a script, once, under the version they name:**
  `scripts/record_described.py` refuses to run under any pydantic but 2.13.5. It records pydantic's
  schema of every shape (`tests/described_shapes.py`) and every development contract's promise and
  hash, made with the old `promise_of` before it changed: `ledger.post@1` hashed
  `9afced75…` there, as it does in the locked environment.
- **The development recording is independent only as first made:** run again now, the script
  writes what `promise_of`, and so `described`, gives, which test 4 shows is the same. The shapes'
  recording stays independent: it is pydantic's own.
- **The markers' pydantic hooks stay,** their comments corrected: nothing in the product asks
  pydantic for a contract's schema any more, but the recording script does, and without the hooks
  a re-recording would silently drop the `x-` keys.
- **`case/diff.py` imports `described` as `schema_of`:** it has a `described` of its own, for
  policies.
- **The constraint in `Field(pattern=…)` is pydantic's `_PydanticGeneralMetadata`,** and the
  refusal names it so: it says the metadata's kind, as for `Ge` or `MaxLen`.
- **The live proof:** the wheel, installed fresh with the bound lifted, resolved pydantic 2.14.3;
  `ventoux version`, `schema --unchanged` and `conformance --unchanged` passed from `/tmp`, and
  none of the nine development contracts hashed otherwise than under 2.13.5.

## Not in this fix

- **The definition format's public schemas** (`ventoux schema`, `tooling/schema.py`) are still
  written by pydantic, through its own generator. A new pydantic could change them; `ventoux
  schema --unchanged` would then fail, saying where, and they would be written again. Nothing is
  hashed from them, so nothing is refused.
- **Whether prose belongs in a promise** (a docstring, a field's description), left open.

## Promises

Each claim D83 and this note make, and the test that would fail if it weren't true
(`tests/test_described.py` unless named). Each was watched failing: before its code was written,
or with its branch switched off when the code came first.

| Promise | Test |
|---|---|
| What Ventoux doesn't describe is refused when the contract is made: a constraint, a title, an alias, examples, `json_schema_extra`, a `Decimal` default, a model's title or `json_schema_extra`, on an input or an output | `test_what_ventoux_doesnt_describe_is_refused_when_the_contract_is_made` |
| Every shape a contract's field may take is written as pydantic 2.13.5 wrote it | `test_every_shape_is_written_as_pydantic_2_13_5_wrote_it` |
| A promise never asks pydantic for a schema | `test_a_promise_never_asks_pydantic_for_a_schema` |
| Every development contract's promise and hash is as recorded under 2.13.5 | `test_every_development_contract_hashes_as_recorded_under_pydantic_2_13_5` |
| A package diff never asks pydantic for a schema | `test_a_package_diff_never_asks_pydantic_for_a_schema` |
| pydantic is not bounded | `test_package.py::test_pydantic_is_not_bounded_since_no_hash_depends_on_its_rendering` |
| No contract the repository has is refused | every test that makes a contract, unchanged and passing |
