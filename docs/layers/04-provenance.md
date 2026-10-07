# Layer 4: provenance and input policies

Status: design agreed in the session, 2026-10-07; built, slices 1–8.

## What this layer is for

Every value carries where it came from: its **provenance**, a set of **sources** (brief, D12). An
expression's value carries the sources of every field it reads. An **input policy** on an
activity's input says which sources it accepts; `validate` refuses a plan in which an input could
get a value its policy refuses. A content filter judges what a value says; a policy only asks where
it came from, so no wording gets an untrusted value past it.

User-facing description, written first: `docs/guides/activities.md` (writing a policy, registering
labels) and `docs/guides/plans.md` ("Where values come from", and two new rows in the table of
issues).

Drawn on: the prototype's `src/core/provenance.ts` (sources as `kind:name` texts, an expression's
sources as the union of what it reads, a literal adding nothing, `noUntrusted` and `onlySources`
with "no provenance" refused by the second); `docs/design.md` §5; `examples/injection-attempt.json`
and `reply-to-sender.json`. Ours differs: no `trusted:` prefix (a source's trust follows from its
origin, D12), labels registered in the catalog, the policy written on the input field, no
`readsAll` (D20 has no `var` of the whole data), and no "strict mode" for conditions (design
question 17).

## Decided in the session

1. **"Input policy", `INPUT_POLICY`** (design question 10, now brief D21). "Sink" appears once, in
   the activities guide.
2. **A policy is written on the input field it guards:** `amount: Annotated[Decimal,
   trusted_only()]`. It appears in the input's JSON Schema, so the contract hash covers it with no
   change to how the hash is computed: a contract without policies keeps its hash.
3. **Two kinds, a closed list:** `trusted_only()` and `only_from("payments", …)`. Adding one is a
   decision recorded in the brief (D21). A policy class the engine doesn't know is refused.
4. **Contracts that gain a policy get a new version.** `payments.refund@2` (`order_id`, `amount`:
   trusted only) and `letters.draft@2` (`to_customer`: trusted only) replace `@1` in the
   development catalog: a `@1` without the policy, left beside it, would let a plan step around
   it. `contracts.lock.json` gains the two `@2` hashes; the `@1` lines stay, as the record of what
   `@1` promised. The quickstart and guides name `@2`.
5. **A plan field with no `source` is the case's to vouch for.** Its static source is `case`: it
   passes `trusted_only` (the runtime check, layer 5, sees the real sources before the activity
   runs) and never passes `only_from` (the plan can't tell which system it came from). A literal
   has no source: it passes `trusted_only` and never passes `only_from`.
6. **Labels live in the catalog,** registered by the platform team (`register_label`). A field's
   `source` must be `untrusted:<label>`: `trusted:…` and any other form are refused by
   `parse_plan` (shape); a label nobody registered is an issue from `validate`
   (`UNKNOWN_SOURCE`, it needs the catalog).
7. **Not in this layer:** output provenance on contracts (plans can't read an activity's output;
   the case runtime binds outputs, layer 8); untrusted values steering a condition (design
   question 17).

## The sources

A source is a text, `origin:name`:

| Source | Origin | Trusted? | Where it appears |
|---|---|---|---|
| `system:<name>` | a system: the one that opened the case, or an activity's output | yes | at runtime |
| `person:<who>` | a person's answer to a task or approval | yes | at runtime |
| `untrusted:<label>` | declared on a field by a developer | no | statically, and at runtime |
| `case` | a plan field with no `source`: given by the case, its origin not visible to the plan | yes, here | statically only |

A literal has no source. A value's provenance is a set of sources; it is trusted when every source
is.

**Fail closed:** a text that is none of these forms (`trusted:portal`, `llm`) is a source the
engine doesn't recognise, and every policy refuses it.

## Propagation

`provenance(expression, sources)` gives an expression's sources: the union of the sources of every
field it reads, through every operator (`cat`, `if`, `sum` with its `where` and `item`, …). It reads
only which fields the expression names, never their values, so the same function serves the static
check (sources from the declarations) and the runtime (sources carried with the values, layer 5).

`if` carries the sources of its condition too: which branch is taken depends on it. Over-approximate,
as layer 3 is: the check may refuse a plan that would be fine, never accept one that isn't.

**Fail closed:** a field with no entry in `sources` raises an error, never counts as "no sources".

## The policies

```python
class Policy:  # one class per kind, in a closed list
    def refuses(self, sources: frozenset[str]) -> str | None: ...  # why not, or None
    def describe(self) -> str: ...  # "only from a system or a person, never from untrusted data"
```

| Kind | Refuses | `describe()` |
|---|---|---|
| `trusted_only()` | any `untrusted:` source, and any source it doesn't recognise | only from a system or a person, never from untrusted data |
| `only_from("payments")` | no source at all, or any source but `system:payments` | only from payments |

`only_from()` naming no system is refused when it is written. The contract reads its input's
policies from each field (`Annotated` metadata that is a `Policy`; `contract.policies(input)`); a
`Policy` subclass the engine doesn't know makes the contract invalid. Every policy on a field
applies.

## The checks

In `parse_plan`: a field's `source` is `untrusted:` and a lowercase label. `trusted:…` gets its own
message: "a field can be declared untrusted, never trusted: trust comes from a contract the
platform team owns, or a person's answer".

In `validate`, two new codes:

- **`UNKNOWN_SOURCE`** at `fields.<name>.source`: the label isn't registered. The message lists the
  registered labels.
- **`INPUT_POLICY`** at `states.<state>.inputs.<input>`: for each input whose contract field has a
  policy, the input expression's sources are computed from the fields' sources; each policy that
  refuses them gives one issue: `<ref> takes <input> <describe()>, and this value comes from
  <field> (<source>), …: <what to do>`. It names only the fields whose sources are refused; a
  literal is named as "a value written in the plan".

An input that already has an issue (`EXPRESSION_INVALID`, `UNKNOWN_INPUT`), or an activity not in
the catalog, gets no `INPUT_POLICY`: one cause, one issue. A field with an unregistered label still
counts as untrusted for `INPUT_POLICY`, since `untrusted:` is what was declared.

## The tracer's provenance

`case/runner.py` carries `set_by`, "a crude stand-in for provenance tags (layer 4)". It goes: the
runner keeps each value's sources instead (`system:opener` for the case file it opened with,
`person:<who>` for an answer), and the approval's "someone else" (brief, D11) becomes the people
among the sources of the step's inputs and condition, through `provenance`. The runner still checks
no input policy at runtime: that is the interpreter's (layer 5), and the runner is replaced at
layer 8. The quickstart's three tests stay green, and its self-approval refusal with them.

## Decided while building

- **A policy writes itself into its field's JSON Schema** (`"x-input-policies": [{"kind":
  "trusted_only"}]`), through Pydantic's `__get_pydantic_json_schema__` hook on `Annotated`
  metadata. That is how the contract hash covers it with no change to how the hash is computed
  (slice 3: before, adding a policy left the hash unchanged, equal to `payments.refund@1`'s).
- **The kind check is `type(policy) in KINDS`**, not `isinstance`: a subclass of a known kind is
  a kind of its own. The rule joins layer 3's rule table, so it runs on building and on
  registering a copy.
- **A plan keeps each field's source beside its type, not on it:** `plan.fields` holds the types,
  `plan.sources` the declared sources. A source on the type would make an untrusted `string`
  unequal to a `string`, and layer 2's `check` compares types with `==`. The author still writes
  the source on the field; a before-validator moves it, and errors still point at
  `fields.<name>.source`. A top-level `sources` written by the author is refused: one place to
  write it.
- **A declared source is `untrusted:` and a label, nothing else:** `system:payments` and
  `person:ana` are refused as well as `trusted:portal`, since only the engine records a system or
  a person (brief, D12). `is_label` (lowercase, digits, `-`) is shared by `parse_plan` and
  `register_label`.
- **Labels are checked twice, by two people:** `register_label` refuses a malformed label at once
  (the platform team's code); `validate` gives `UNKNOWN_SOURCE` for an unregistered one (the
  developer's plan, in the list of issues). A misspelt label is still untrusted for
  `INPUT_POLICY`.
- **The walk is written out operator by operator,** like `render`: a first, generic version
  missed `exists`, `count` and `sum`, and each failed open (slice 2). An operator added to the
  brief raises in it until someone says what it reads.
- **"One cause, one issue" also keeps `validate` from crashing:** asked for the sources of an
  expression that reads an undeclared field, `provenance` raises `NoSources` (slice 6).
- **The tracer's walk had a hole:** it found a field only inside `{"var": …}`, so a reviewer whose
  answer decided whether `pay` ran (through `exists`) could approve it. The runner now asks
  `provenance` (slice 7), with a quickstart test for that case.

## Files

- `src/ventoux/core/policy.py`: `Policy`, `TrustedOnly`, `OnlyFrom`, `trusted_only`, `only_from`.
- `src/ventoux/core/provenance.py`: what a source is (`trusted`), and `provenance`.
- `src/ventoux/core/contract.py`: reading each input's policies; refusing a kind it doesn't know.
- `src/ventoux/core/catalog.py`: `register_label`, `labels`.
- `src/ventoux/core/plan.py`: a field's `source`.
- `src/ventoux/core/validate.py`: `UNKNOWN_SOURCE` and `INPUT_POLICY`.
- `src/ventoux/testing.py`, `examples/refund/refund.json`, `contracts.lock.json`: the `@2`
  contracts and the development labels.
- `src/ventoux/case/runner.py`: sources instead of `set_by`.
- Tests: `tests/test_policy.py`, `tests/test_provenance.py`, and new tests in `test_catalog.py`,
  `test_plan.py`, `test_validate.py` and `test_quickstart.py`.

## Seams the tests use

- `trusted_only()`, `only_from(...)`, and a policy's `refuses(sources)` and `describe()`.
- `provenance(expression, sources)` on a parsed expression.
- `ActivityContract(...)` with an input carrying policies; `contract_hash`; `Catalog.register`,
  `register_label`.
- `parse_plan(data)`, then `validate(plan, catalog) -> list[Issue]`.
- `run_case` (the quickstart's tests).
- The guides: the activities guide's contract and refusals, the plans guide's examples and table.

## Slices, in order

1. **Policies.** Negative: `trusted_only` refuses `untrusted:llm`, and a source it doesn't
   recognise (`trusted:portal`). Negative: `only_from("payments")` refuses no source at all, and
   `system:crm`; `only_from()` is refused. Then each accepts what it should.
2. **Propagation.** Negative: a field with no sources entry raises. Then a literal has none; `cat`,
   `if` (its condition included) and `sum` with `where` and `item` carry every field read.
3. **Contracts carry policies.** Negative: a `Policy` subclass the engine doesn't know is refused.
   Then: a policy changes the hash, and a contract without one keeps its recorded hash. Then the
   development catalog moves to `@2`, the lockfile gains their hashes, and the activities guide's
   example and refusals run (existing tests' `@1` messages change in their own commit).
4. **A field's source.** Negative: `trusted:portal`, and `llm` with no origin, refused by
   `parse_plan`. Then `untrusted:llm` is read.
5. **Labels.** Negative: `register_label("LLM")` refused; `untrusted:lml` gives `UNKNOWN_SOURCE`.
   Then the development labels pass.
6. **Input policies.** Negative: the guide's injection plan gives `INPUT_POLICY`; so does the same
   value through `cat`. Negative: `only_from` refuses a plan field and a literal. Then
   `customer_email` passes, and an input with `EXPRESSION_INVALID` gets no `INPUT_POLICY` too.
7. **The tracer.** `set_by` replaced by sources; the quickstart's tests, the self-approval
   refusal included, still pass.
8. **The guides run:** the plans guide's injection example and its table's two new rows.

## Promises

Each claim this note makes about behaviour, and the test that fails if it isn't true; checked
against the code before the pull request. `P` is `tests/test_policy.py`, `Pr`
`tests/test_provenance.py`, `C` `tests/test_catalog.py`, `L` `tests/test_plan.py`, `V`
`tests/test_validate.py`, `Q` `tests/test_quickstart.py`.

| Promise | Test |
|---|---|
| `trusted_only` refuses any untrusted source, and any source it doesn't recognise | P `test_trusted_only_refuses_untrusted_data`, `test_a_source_the_engine_does_not_know_is_refused` |
| `trusted_only` accepts a system, a person, the case and a literal | P `test_trusted_only_accepts_a_system_a_person_and_the_definition` |
| `only_from` refuses a value from no system, from another system, from a person or the case; it names at least one system | P `test_only_from_refuses_a_value_from_no_system`, `test_only_from_refuses_another_system`, `test_only_from_refuses_a_person_and_the_case`, `test_only_from_names_a_system` |
| Each policy reads as its sentence | P `test_each_policy_reads_as_one_sentence` |
| An expression carries the sources of every field it reads, through every operator, `if`'s condition included; a literal adds none | Pr `test_a_literal_has_no_sources`, `test_every_field_read_is_a_source` |
| A field with no known sources, or something that isn't an expression, is an error, never "no sources" | Pr `test_a_field_without_sources_is_an_error`, `test_something_that_is_not_an_expression_is_an_error` |
| A policy kind the engine doesn't know makes the contract invalid, built or registered as a copy | C `test_a_policy_kind_the_engine_does_not_know_is_refused`, `test_every_rule_refuses_a_contract_that_breaks_it`, `test_every_rule_runs_again_when_a_copy_is_registered` |
| A policy is part of the hash; a contract without one keeps its hash | C `test_a_policy_changes_the_hash`, `test_every_development_contract_matches_its_recorded_hash` |
| The development catalog doesn't serve the retired `@1` versions | C `test_a_version_without_the_policy_is_not_served` |
| The activities guide's contract and refusals are what the code does | C `test_the_guides_example_is_the_development_refund_contract`, `test_the_guides_refusals_are_what_the_catalog_says` |
| A field can be declared untrusted, never trusted; any other form is refused; a source is written on its field only | L `test_a_field_can_be_declared_untrusted_never_trusted`, `test_a_source_has_an_origin_and_a_label`, `test_a_source_is_written_on_its_field` |
| An untrusted field keeps its type for the expression check | L `test_an_untrusted_field_keeps_its_type_and_its_source` |
| A label must be lowercase to be registered, and registered to be used | C `test_the_guides_refusals_are_what_the_catalog_says` (its `register_label("LLM")` row); V `test_a_source_label_must_be_registered`, `test_a_registered_label_is_accepted` |
| An input never gets a value whose sources its policy refuses, however the expression wraps it, whatever the label | V `test_the_guides_injection_plan_is_refused`, `test_an_expression_does_not_clean_an_untrusted_value`, `test_a_misspelt_label_is_still_untrusted` |
| Every policy on an input applies | V `test_every_policy_on_an_input_applies` |
| A plan field passes `trusted_only`; a plan field and a literal never pass `only_from` | V `test_a_plan_field_is_the_cases_to_vouch_for`, `test_only_from_is_never_met_inside_a_plan` |
| One cause, one issue: an input already refused gets no `INPUT_POLICY` | V `test_an_input_already_refused_gets_no_input_policy_issue` |
| The plans guide says what the code does: the injection example, its safe variant, and the table | V `test_the_guides_injection_plan_is_refused`, `test_the_guides_safe_variant_passes`, `test_the_guide_lists_every_issue_code`, `test_the_guides_messages_are_what_validate_says` |
| The tracer's approvals exclude whoever's answer the step uses, through any operator | Q `test_the_reviewer_cannot_approve_the_payment`, `test_whoever_decides_whether_the_step_runs_cannot_approve_it` |

Not this layer's promise, though the plans guide states it: the engine checks a value's real
sources again before an activity runs. That is the interpreter's (layer 5), whose curriculum
negative test is exactly this.
