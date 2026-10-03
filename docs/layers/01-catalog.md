# Layer 1: activities and the catalog

Status: agreed, 2026-10-03.

## What this layer is for

Definitions only *reference* capabilities (`payments.refund@1`); the platform team defines what a
reference promises, in a contract registered in the catalog (brief: idea 2, D5, D17; design
question 15 for the name). The tracer calls `activities["payments.refund@1"]`, a plain dictionary
with no contract; this layer replaces that. User-facing description: `docs/guides/activities.md`.

Drawn on: the prototype's `src/core/registry.ts` (contracts only, refuse a reused reference, list
other versions in errors) and `src/activities/catalog.ts` (contracts written as data next to their
schemas). Ours adds retries and timeouts, idempotency and failure outcomes, and fails closed on a
lookup instead of returning `undefined`.

## First: ban relative imports

`from ..temporal import worker` reaches `ast` as module `temporal` (level 2), and `from .. import
temporal` as no module at all, so layer 0's boundary test misses both. Two fixes:

- ruff's `TID252` with `ban-relative-imports = "all"`: every import names its layer;
- the boundary test reports any relative import as forbidden, so it never skips an import it can't
  read (fail closed).

## The contract

`ActivityContract`, a frozen Pydantic model with `extra="forbid"`:

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | dotted lowercase, `payments.refund` |
| `version` | `int`, at least 1 | the reference is `name@version` |
| `input`, `output` | Pydantic model classes | hashed and published as JSON Schema |
| `risk` | `low`, `medium`, `high` | |
| `effect` | `read`, `compute`, `write`, `notify` | |
| `timeouts` | `start_to_close`, `schedule_to_start` (seconds, > 0) | both required |
| `retry` | `maximum_attempts`, `initial_interval`, `backoff_coefficient` | required |
| `idempotency_key` | input field name, or `None` | required unless `read` or `compute` |
| `outcomes` | list of names | business failures (D17) |
| `display` | `title`, `description`, `outcomes` (name to title) | presentation, outside the hash |

Refused at construction: a side-effecting contract without `idempotency_key`; a key that isn't an
input field; display titles that don't match the outcomes exactly. A field the model doesn't know
(`queue=…`) is refused by `extra="forbid"`, with a message pointing at deployment bindings.

Output provenance and input policies belong to the contract too (D12), but come in layer 4.

## The catalog

`Catalog` holds contracts only, never implementations, so `core` holds no code that does I/O.

- `register(contract)`: identical content again is a no-op; different content under the same
  reference raises `ContractConflict`.
- `get(reference)`: returns the contract, or raises `NotInCatalog`, naming the versions that do
  exist; a malformed reference (`payments.refund`, `payments.refund@1.0`) raises it too, saying the
  shape is `name@N`. Never `None`: a caller can't forget to check.

## The hash

`contract_hash(contract)`: SHA-256 of the contract's canonical JSON (sorted keys, no whitespace),
with the schemas as JSON Schema and `display` left out. `check_hashes(catalog, recorded)` returns
the problems: a changed hash ("register it as `@2`") and an unrecorded contract (with the line to
add). A test runs it on the development catalog against `contracts.lock.json` at the repository
root, so CI needs no new step. Recorded contracts no longer in the catalog (retirement) are layer
12's.

## Files

- `src/ventoux/core/catalog.py`: the contract, the catalog, the hash and the check.
- `src/ventoux/testing.py`: the three development activities (contracts and fake implementations)
  and the development catalog, replacing the two `# TRACER: … layer 1` lines. The runner looks each
  activity up in the catalog before calling it, so an unknown activity stops the case. Checking
  inputs against the contract stays with the interpreter (layer 5), marked `# TRACER: layer 5`.
- `contracts.lock.json`, `tests/test_catalog.py`, `tests/test_layers.py` (relative imports),
  `pyproject.toml` (`TID252`).

## Seams the tests use

- `ruff check` on a snippet under `src/` (run from pytest with `python -m ruff`).
- `forbidden_imports(layer, source)` from layer 0.
- `ActivityContract(...)`, `Catalog.register`, `Catalog.get`, `contract_hash`, `check_hashes`.
- `run_case` from the tracer, unchanged; the quickstart's three tests stay green.
- The guide's Python example runs in a test, so it can't drift from the code.

## Slices, in order

1. Negative: a relative import under `src/` fails `ruff check`.
2. Negative: the boundary test reports `from ..temporal import worker` and `from .. import x`.
3. Negative: `get` of an unknown name, an unknown version (listing what exists), a malformed
   reference. Then register and get.
4. Negative: a different contract under a reused reference is refused; the same one is a no-op.
5. Negative: a `write` contract without an idempotency key; a key that isn't an input field; a
   `queue` field; a name or version that no reference could match (`Payments Refund`, version 0),
   which could be registered but never looked up (found in slice 3).
6. Negative: `check_hashes` reports a changed contract and an unrecorded one; a `display` change
   leaves the hash alone.
7. The development activities and `contracts.lock.json`; the runner looks activities up in the
   catalog (negative: a definition naming `payments.refund@2` is refused); the guide's example
   runs.

## Done when

The tests, mypy and ruff pass, the quickstart's tests are green, no `# TRACER: … layer 1` comment
is left, and the guide matches the code.
