# Fix: a contract's promise is written by Ventoux, never by pydantic

A fix, not a layer: no warm-up, and nothing new for a person to use. Found in 20c, by the
package's fresh install (`docs/layers/20-deployment.md`, "Decided while building 20c"); bounded
there for the time being (brief, D82); made independent here, in its own pull request, stacked on
20c's.

Status: two designs put, 2026-11-10 (a new hash method 2, or method 1 written by Ventoux itself);
the second chosen. Choices below put, each with a recommendation; answered "1 to 7, all as
recommended", the same day. The seams are choice 6's: `contract_schema(model)`, making a contract,
and `contract_hash`. D83 and the dated line on D82 written before building. Built test-first, the
same day, and the Promises table checked against the tests (see "Decided while building").

## The bug

A contract's hash covers its promise (`promise_of` in `core/promise.py`): everything but its
wording, its input and output models as JSON Schema. That JSON Schema is pydantic's own
rendering, `model_json_schema()`, and pydantic changes it between minor versions. For
`ledger.post@1`'s input `amount: Annotated[Decimal, only_from("opener")]`, 2.13.5 writes

```json
"amount": {"anyOf": [{"type": "number"},
                     {"pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$", "type": "string"}],
           "title": "Amount",
           "x-input-policies": [{"kind": "only_from", "systems": ["opener"]}]}
```

and 2.14.3 writes the same without the `pattern`. (20c's note says 2.14 adds it; run under both,
it is the other way round: 2.13 writes it, 2.14 drops it.) So under 2.14, `kyc.check@1`,
`ledger.post@1` and `payments.refund@2` hash differently though nothing about them changed: the
lock check fails, the registry refuses their workers (brief, D54), two workers on different
pydantic versions disagree, and `ventoux conformance --unchanged` fails, since
`conformance/catalogs/development.json` embeds the promises.

Nothing else hashed depends on it: a package's behaviour digest reads `model_dump`, plain values,
never a JSON Schema. And the published definition schemas (`ventoux schema --unchanged`) come out
the same under 2.14.3.

## The design, with a small example

The hash stays what it is; what it reads stops being pydantic's. Ventoux writes a contract model's
JSON Schema itself, from its fields, for exactly the field shapes a contract may have, and writes
it as pydantic 2.13 did. So every hash recorded so far, in `contracts.lock.json`, in release
records and in worker manifests, is still the hash the code computes, and no future pydantic can
move it.

```python
class LedgerInput(BaseModel):
    amount: Annotated[Decimal, only_from("opener")]

contract_schema(LedgerInput)   # the JSON above, pattern included, whatever pydantic is installed
```

A contract's fields are already a closed list (inputs: `Decimal`, `str`, `bool` or a `Literal` of
texts, each possibly optional; outputs: `Decimal`, `str`, `bool` or `date`; marks: input policies,
a reference, an output's source). A model the writer can't describe exactly is refused when the
contract is made: never written some other way, never left to pydantic (fail closed).

Set aside: a new hash method 2, a description Ventoux designs (`{"type": "decimal", "required":
true, ...}`, no titles, no class name). Cleaner, but it migrates the lockfile, the CI rule that a
recorded hash never changes, release records and worker manifests, and keeps method-1 code that
only pydantic 2.13 can run faithfully. It changes what a promise covers, which is a decision of its
own; this fix only stops depending on pydantic. Method 2 stays open for that decision.

## Choices

Answer by number.

1. **One writer, `contract_schema(model)`, in its own file `core/contract_schema.py`.** It returns
   the model's JSON Schema as plain JSON values. `promise_of` uses it for `input` and `output`, in
   place of `model_json_schema()`; so do `ventoux promises`, the conformance catalog and the
   authoring loop, which all read `promise_of`. The semantic diff (`case/diff.py`), which reads
   `model_json_schema()` too, uses it as well, so what it says can't change with pydantic either.
   *Recommended.*

2. **What it writes, shape by shape, as 2.13.5 wrote it** (each checked against 2.13.5's own
   output, choice 6):

   | Field | Written |
   |---|---|
   | the model | `{"properties": {...}, "required": [...], "title": <class name>, "type": "object"}`; `required` left out when nothing is; `description` the class's own docstring, cleaned as `inspect.cleandoc` does, when it has one (never inherited) |
   | every field | `"title"`: its name, `_` as spaces, each word capitalised (`address_2nd` → `Address 2Nd`) |
   | `str` | `"type": "string"` |
   | `bool` | `"type": "boolean"` |
   | `Decimal` | `"anyOf": [{"type": "number"}, {"pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$", "type": "string"}]` |
   | `date` | `"format": "date", "type": "string"` |
   | `Literal["x"]` | `"const": "x", "type": "string"` |
   | `Literal["a", "b"]` | `"enum": ["a", "b"], "type": "string"` |
   | `T \| None` | `"anyOf": [<T's schema>, {"type": "null"}]`, the title outside it; with `= None`, `"default": null` |
   | input policies | `"x-input-policies": [...]`, as each policy writes itself today |
   | a reference | `"x-reference": <system>` |
   | an output's source | `"x-source": <source>` |

   Fields in the order the class declares them, `required` in that order too (the hash sorts keys,
   never lists). *Recommended.*

3. **What it refuses, when the contract is made.** A contract whose input or output model holds
   anything else is refused, like any other bad contract (`ValueError` from a validator on
   `Contract`), its message saying which model and field, what it holds, and what a contract's field
   may be: a field with a default other than `= None`, a `default_factory`, an alias, a title, a
   description, examples, `json_schema_extra`, a constraint (`Field(gt=0)`, `annotated_types`), any
   `Annotated` metadata that isn't one of Ventoux's three marks, or a model that sets any
   `model_config`. No contract in the repository, the guides or the examples has any of these.
   *Recommended.* Set aside: writing descriptions and constraints too (each is more of pydantic's
   rendering to freeze; a team that needs one asks, and it is a decision).

4. **The hash method stays 1, and what it is is written down:** method 1 is the SHA-256 of the
   promise written canonically, its models written by `contract_schema`, which gives what pydantic
   2.13 wrote for every contract it accepts. No hash, record, lockfile entry or committed file
   changes. *Recommended.*

5. **pydantic's bound is raised to the next major, `>=2.13.5,<3`, and the lock moves to 2.14.3,**
   so CI runs the version that broke the hashes, and the package job's fresh install the newest one.
   20c's test pinning the bound to the installed minor is replaced by this fix's tests (choice 6).
   *Recommended.* Set aside: no upper bound (a major version may change the API, not just the
   rendering); keeping the lock on 2.13.5 (nothing would run the version that broke it).

6. **The tests, each seen failing first, negative ones first:**
   - a contract whose input field has `Field(description="…")` is refused, saying the model, the
     field, what it holds and what a field may be; then a default other than `None`, a constraint,
     an unknown `Annotated` mark, and a `model_config`, each refused the same way;
   - `contract_schema` of a set of models covering every row of choice 2 equals what pydantic
     2.13.5 wrote for them, recorded once under 2.13.5 into `tests/rendering-2.13.json` and
     committed: so the check holds whatever pydantic is installed later;
   - a contract's hash doesn't read pydantic's rendering: with `model_json_schema` made to give
     2.13's form, then 2.14's (the pattern dropped), then to raise, every development contract
     still hashes as `contracts.lock.json` records;
   - unchanged and still passing: every development contract matches its recorded hash, and
     `ventoux conformance --unchanged` (now under 2.14.3).

   *Recommended.*

7. **Where it is recorded:**
   - a new decision, **D83**, "A contract's promise is written by Ventoux": the writer, what it
     refuses, method 1 as written down in choice 4, and the bound raised; method 2 set aside;
   - a dated line on D82: the bound is raised by D83; and the 20c finding's direction corrected
     (2.13 writes the pattern, 2.14 drops it);
   - a dated line under 20c's "Decided while building" with the same correction;
   - the activities guide: what a contract's field may be, and what is refused; the release guide's
     "Before raising a dependency's bound" rewritten (contracts no longer hash from pydantic's
     rendering); the changelog's line; `pyproject.toml`'s comment;
   - this note, with its Promises table, checked both ways before the pull request.

   *Recommended.*

## Decided while building

- **The marks' pydantic hooks are gone.** Once `promise_of` and the semantic diff read
  `contract_schema`, nothing in Ventoux asks pydantic to render a contract's model, and each mark's
  `__get_pydantic_json_schema__` (on `Policy`, `Reference`, `OutputSource`) said "the published
  schema, which the contract hash covers", no longer true. The writer writes each mark itself.
- **What is refused, a little wider than choice 3 listed:** pydantic also writes or names a field
  by a validation or serialization alias, a title generator, a deprecation and a discriminator, so
  those are refused too. A type the writer doesn't know (a `float`, `str | bool`, a nested model)
  is refused by the writer on its own as well: the contract's earlier checks refuse each first,
  but `contract_schema` never guesses either.
- **A refusal ends with what to do and its reason:** `... has a constraint or mark Ventoux doesn't
  know: a contract's field is its type, its marks (a policy, a reference, a source) and, if it is
  optional, `= None`. Remove it (brief, D83).` The guide's table of refusals gains the
  constraint's row, `Field(gt=0)`, tested as every row is.
- **pydantic 2.14 types `create_model` more strictly:** mypy refused one call in
  `tests/test_diff.py` with an `Annotated` field; written as a plain class, under the same name.
- **The package job, run by hand:** the wheel, installed fresh, passes `ventoux version`,
  `schema --unchanged` and `conformance --unchanged` under 2.14.3 (what failed in 20c) and under
  2.13.5.
- **One Temporal test failed once in the full run** (`test_forgetting_waits_for_a_workflow_step`,
  under load); it passes alone, with and without this change, and in the next full run.

## Promises

Each claim this note makes, and the test that fails if it isn't true. Each new test was seen
failing first, for its reason: accepted before the refusals, pydantic's rendering read before the
writer; the unknown types by taking the writer's refusals out.

| Promise | Test |
|---|---|
| A contract model holding a description, a default other than `None`, a `default_factory`, an alias, a title, examples, `json_schema_extra`, a constraint, an unknown mark or a `model_config` is refused when the contract is made, saying which field and what may be, input or output | `tests/test_contract_schema.py`: `test_a_field_with_a_description_is_refused_when_the_contract_is_made`, `test_anything_else_pydantic_would_write_is_refused`, `test_an_output_is_refused_the_same_way`; the guide's row, `tests/test_catalog.py::test_the_guides_refusals_are_what_the_catalog_says` |
| The writer refuses a type it doesn't know (fail closed) | `test_a_type_the_writer_doesnt_know_is_refused` |
| `contract_schema` writes each shape of choice 2 as pydantic 2.13.5 did | `test_each_shape_is_written_as_pydantic_2_13_wrote_it`, against `tests/rendering-2.13.json` |
| A contract's hash doesn't depend on pydantic's rendering: 2.13's, 2.14's, or none read | `test_a_contracts_hash_doesnt_depend_on_pydantics_rendering` |
| The semantic diff doesn't read pydantic's rendering | `tests/test_diff.py::test_a_contracts_differences_dont_read_pydantics_rendering` |
| No hash recorded so far changes | `tests/test_catalog.py::test_every_development_contract_matches_its_recorded_hash`, and the hash test above, both against `contracts.lock.json` unchanged |
| The conformance catalog file doesn't change with pydantic | `ventoux conformance --unchanged`, in CI under 2.14.3 and in the package job's fresh install; `development.json` unchanged |
| pydantic is bounded below its next major only | `tests/test_package.py::test_pydantic_is_bounded_below_its_next_major_only` |
