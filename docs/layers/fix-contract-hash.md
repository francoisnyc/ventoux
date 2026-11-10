# Fix: a contract's hash, independent of pydantic

A fix, not a layer: no warm-up. Found in 20c (`docs/layers/20-deployment.md`, "Decided while
building 20c"), where the package's fresh install resolved pydantic 2.14.3 and three contracts
hashed differently; 20c bounded pydantic below 2.14 (D82) and left this fix for later. Branch
`fix-contract-hash`, from `layer-20c-package` (it lifts that bound and relies on the `package`
job); its pull request opens once #97 is merged, rebased onto `main`.

Status: 2026-11-10, the design agreed (option B, both choices as recommended); D83 written; the
seams and tests below proposed.

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
   (`test_contract.py`, parametrized).
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
