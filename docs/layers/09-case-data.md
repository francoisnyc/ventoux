# Layer 9: case data

Status: split into four parts and the eighteen choices agreed in the session, 2026-10-10 (all as
proposed); 9a's note and its nine drafting points confirmed the same day; 9a built, slices 0–7;
Promises checked against the tests, 2026-10-10; the tutor review's fix built test-first,
2026-10-11. 9b's choices agreed in the session, 2026-10-13 (all as proposed, with the key
provider sealing and opening); 9b built, slices 0–8; Promises checked against the tests,
2026-10-13; the tutor review's fix built test-first, 2026-10-14. 9c's choices agreed in the
session, 2026-10-14 (all as proposed, with `forgetting` added: `while_open` and `never`); 9c
built, slices 0–10; Promises checked against the tests, 2026-10-15; the tutor review's two fixes
built test-first, 2026-10-15. 9d's choices agreed in the session, 2026-10-15 (all as proposed);
its note drafted the same day, and its four drafting points confirmed.

## What this layer is for

Until now every field of a case file is plain data, seen by anyone and kept in Temporal's history
for good. Layer 9 makes the case file what the brief says it is (brief, D8): **references** to
records other systems own, typed by system; **decision facts**, each seen only by the roles that
may see it; **sensitive facts**, encrypted with a key per case so they can be forgotten; and
facts that know **when they were obtained**, so a step can refuse to run on stale ones.

It lands as four pull requests, each with its section in this note, its own Promises table and its
own tutor review:

| PR | Builds | Dependency |
|---|---|---|
| **9a** | systems in the catalog; reference inputs on contracts, checked at runtime; resolvers; visibility by role and the filtered view; approvers who can't see a value | none |
| **9b** | sensitive fields; the key provider; the payload codec; no sensitive value in plain text anywhere | `cryptography` |
| **9c** | `forget`: proposed, approved by someone else, closes the case, destroys its key | none new |
| **9d** | time as event data; when each fact was obtained; `max_age` and refreshing; ages on the approval sheet | none |

The `chartering` prototype has nothing for case data (curriculum, layer 9); no file of it is drawn
on.

Agreed in the session, for the later parts (each is detailed in its own section when it starts):
sensitive values are wrapped in the state (`Sensitive`, shown as `‹sensitive›`) and each travels
in its own part of a payload, which the codec encrypts with the case's key, found from the
workflow ID Temporal gives the codec; a key is made when the case starts and never made again;
forgetting is its own small workflow, `<case ID>/forget`, needing a role registered to forget and
two different people, closing an open case as `forgotten`, then destroying the key through a
registered activity; time reaches `decide` as data on each event (whole seconds since the epoch;
`datetime` stays banned in `core` and `case`), stamped on Temporal from `workflow.now()`; a stale
fact is refreshed only from a read-only step, otherwise the case needs attention. The curriculum's
"export" is read as Temporal's history export; the audit export comes after layer 15. The guide's
sensitive example is a `national_id`, a text: D20 has no date type.

---

## 9a. References and who sees what

User-facing description, written first: `docs/guides/case-data.md` ("The three kinds of field",
"References", "Who sees what"); `docs/guides/activities.md` ("Reference inputs", "Systems and
resolvers", new refusal rows, `letters.draft@3`); `docs/guides/cases.md` (approvers see what they
approve, `view` and `shown` in tests and on Temporal). Decision: brief D30 (drafted with this note).

### What this part is for

A reference today is a text with a system name beside it, and nothing reads the name: an activity
expecting a customer ID takes a policy ID without a word, and every field is seen by everyone. 9a
makes the system name a promise contracts can ask for, shows referenced records through resolvers
on behalf of the person looking, and filters the case file by role before anyone sees it.

### Decided in the session

1. **Systems are registered in the catalog,** like source labels: `register_system("crm")`. A
   case field referencing a system nobody registered is refused when the case opens (`parse_case`
   doesn't know the catalog; the opening does).
2. **A contract input may require a reference by system:** `Annotated[str, reference("crm")]`,
   written into the input's JSON Schema as `x-reference`, so only contracts that declare one
   change their hash. At runtime, before a step is scheduled, that input takes only a reference
   field of that system, read as it is (`{"var": "customer_id"}`); another system's reference, a
   text field or a computed value fails the step. The static check is case validation's
   (layer 10).
3. **Resolvers live in `ventoux.tooling`:** a function per system, `resolve(reference, viewer)`,
   registered by the platform team, called on the viewer's behalf. Showing a record on an open
   case is recorded by a `shown` event, as a line without content: `ana was shown customer_id
   (crm cus-7)`. A closed case has no workflow to record into: the API's own access log covers it
   (deployment, after v1.0).
4. **Visibility by role,** filtered on the server: anyone holding a role the case names sees a
   field, unless its `visible_to` narrows it; outcomes and outputs follow the default. A pure
   `case_view(definition, state, roles)` in `case`; on Temporal a `view` query takes the viewer's
   roles and filters inside the worker.
5. **Approvers who can't see a value the step reads are refused at their answer,** with what they
   can't see. D16's static warning stays with case validation (layer 10); this check depends on
   nothing it does.

### Decided while drafting, confirmed in the session

Each is a choice the agreed design left open, written as the rule we confirmed.

1. **The development catalog gains systems and roles:** the systems `crm`, `documents`, `orders`
   and `policies` (the quickstart's `order_id` names `orders`, so its opening needs it), and the
   roles `adjuster` and `fraud` for the guide's claim. Tests with a catalog of their own register
   the systems their cases name.
2. **`letters.draft@3` is a new development contract,** the guide's, word for word: `customer`, a
   trusted `crm` reference, and `template`. It fetches the address itself (brief, D8, "fetch close
   to use"). `@2` stays: it takes an address, not a reference, so `@3` is a different input, not
   `@2` made stricter, and the layer 4 injection tests read `@2`. A new entry in
   `contracts.lock.json`; no existing hash changes.
3. **The reference check lives in `core`** (`checked_inputs`), so a plan's activity state gets it
   too: a plan field declared `"type": "reference", "system": "crm"` is a `crm` reference. The
   check is given each field's system; a reference input fed anything but a plain `var` of a field
   of that system is refused, with the field's type in the message.
4. **A plan's reference fields are checked when its run starts,** as a case's are at its
   opening: a system nobody registered refuses the run (`RunRefused`).
5. **"A role the case names"** is every role in the definition: a task's `roles`, an approval's,
   `proposed_by`, a close reason's, and every `visible_to`. Operating roles are registered, not
   named by a case, so an operator sees the report, not the case file. *Corrected in the tutor
   review:* the report then held values, quoted in refusals and failures; now it quotes none
   (see "From the tutor review").
   A viewer holding none of them sees every field hidden.
6. **The view:** `CaseView` with `values` (only what the viewer may see: declared fields, outcomes
   `assess.outcome` and outputs `lookup.status`), `sources` for each, `hidden` (each hidden
   field, and the roles that would see it), and `lines`, one per declared field in the
   definition's order: `Estimated damage: 1200, from system:opener`, `Fraud score: hidden (needs
   fraud)`, `Estimated damage: not set`. A value is shown as the history shows one.
7. **The approver's sight is checked for both outcomes,** after D23's checks (the entry is open,
   the outcome is offered, the person has one of its roles, the role may approve the risk) and
   before "someone else": a person who can't see the values can't judge them either way. The
   refusal names the first field, in name order, they can't see, and every role that would see
   it: `lee can't see approved_amount, which pay reads: it needs support`.
8. **`shown` is an event,** `Shown(field, by, roles)`: a script's `shown(field, who)`, a signal on
   Temporal. It is refused if the field isn't a reference, the person's roles can't see it, or
   the case is closed; on Temporal a refusal is recorded and the case waits on, as every refusal
   is (8c). It changes nothing but the history: no step starts because of it.
9. **`Resolvers.show(view, field, viewer)`** reads the reference from the viewer's filtered view,
   so a hidden field has nothing to resolve; refuses a field that isn't a reference, and a system
   with no resolver; and returns what the resolver gives, unchanged. It doesn't record: the caller
   sends `shown`. Ventoux hiding parts of what a resolver returns ("hide more", D16) is not built:
   nothing yet says which parts. Resolvers are plain functions; the API, when it comes, decides
   whether they become `async`.

### How it works

**References into inputs.** `checked_inputs` gains the case's (or plan's) field systems. For
each input whose contract field carries `reference(system)`, the expression must be `{"var":
name}`, and `name` a reference field of that system; otherwise `InputRefused` with D30's message.
It runs before the input policies, so the step fails before anything else is read.

**Visibility.** `case/visibility.py` answers one question, "may these roles see this field?": a
field with `visible_to` is seen by those roles; any other field, outcome or output by any role
the case names. `case_view` builds the view from it; `answers.py` asks it for every field the
step reads (`fields_read` of its inputs, its `when` and the approval's `when`, as D11's
exclusions read them) before an approval is accepted.

**Shown.** `decide` handles `Shown`: checks it, appends the line, admits nothing new.

### Where the code goes

- `core/references.py`: `reference()`, the `x-reference` it writes, `references(contract)` (each
  input's system).
- `core/catalog.py`: `register_system`, `systems`; a contract's references name registered
  systems, on `str` fields.
- `core/before_activity.py`: the reference check, given each field's system.
- `core/interpreter.py`: passes the plan's field systems; refuses a run whose reference names an
  unregistered system.
- `case/definition.py`: `visible_to` on `CaseField`; `roles_named(case)`.
- `case/visibility.py` (new): `may_see`, `CaseView`, `case_view`.
- `case/state.py`: `Shown`.
- `case/runtime.py`: the opening's system check; `Shown`; field systems into `checked_inputs`.
- `case/answers.py`: the approver's sight.
- `testing.py`: `CaseRun.view`, the `shown` script item, the development catalog's systems and
  roles, `letters.draft@3` and its fake.
- `temporal/cases.py`: the `view` query and `shown` signal; the client's `view` and `shown`.
- `tooling/resolvers.py` (new): `Viewer`, `Resolvers`.
- `contracts.lock.json`: `letters.draft@3`.

### Not in 9a

- Sensitive fields, keys and the codec (9b); forgetting (9c); fresh facts (9d).
- Reference outputs (an output field carrying `reference(...)`) and reference fields of a `plan`
  step's inputs crossing into the plan with their system: nothing needs them yet.
- The static checks: references reaching the right systems, approvers who can't see (layer 10).
- Ventoux hiding parts of a resolver's answer; `async` resolvers and the API that calls them.
- No new dependency.

### Seams the tests use

- `catalog.register_system`, `catalog.register`, `contract_hash` and the lock check.
- `run_case(..., catalog=)` and what it reports, `CaseRun.view(roles=)`, the script's `shown`;
  `run_plan` for a plan's reference input.
- `Resolvers`, `Viewer`, `Resolvers.show`.
- On Temporal's test server: `start_case`, `view`, `shown`, `answer`, `report`; the `Replayer`.
- The guides' examples, run as written, and each new row of their refusal tables.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Systems in the catalog.** Negative: `register_system("CRM")`; a contract referencing an
   unregistered system; `reference()` on a `Decimal`. Then every recorded hash is unchanged,
   declaring a reference changes the hash, and `letters.draft@3` is registered and recorded.
1. **References at the opening.** Negative: a case, and a plan run, whose reference names an
   unregistered system are refused. Then the quickstart and every existing test pass with the
   development catalog's systems.
2. **References into inputs.** Negative (the curriculum's): a `policies` reference given to
   `letters.draft@3`'s `crm` input fails the step; so do a text field and a `cat`; and in a plan.
   Then the guide's `deny` step runs.
3. **The view.** Negative (the curriculum's): a field hidden from a role is absent from that
   role's view; a viewer with no role on the case sees every field hidden. Then the guide's view,
   lines as written; outcomes and outputs visible by default.
4. **Approvers who can't see.** Negative: an approval, and a rejection, by someone who can't see
   a value the step reads are refused. Then someone who sees it approves, and the step runs once.
5. **Shown and resolvers.** Negative: `shown` of a hidden field, of a field that isn't a
   reference, on a closed case; `Resolvers.show` of a hidden field, of a system with no
   resolver; `Resolvers.register` of an unregistered system. Then the line is recorded, and the
   resolver is called with the viewer.
6. **On Temporal.** Negative: a refused `shown` and a refused approval are recorded, and the case
   waits on. Then `view` gives the same view as in memory, and a case history with a `shown`
   replays.
7. **The guides and the promises.**

### Decided while building

- **The plans guide's `UNKNOWN_ROLE` message lists two more roles** (slice 0): the development
  catalog's `adjuster` and `fraud` are in every list of registered roles. The guide and its test
  changed with it.
- **The first hash test passed for the wrong reason** (slice 0): its three input models had three
  class names, which the hash covers, so they hashed apart with or without `x-reference`. They
  now share one name, and the test failed until the reference reached the schema.
- **Two workflow-step fixtures named a system `customers`** (slice 1), which nothing registers; a
  customer's record is the CRM's, so they name `crm`.
- **The reference refusal doesn't name the step** (slice 2): `checked_inputs` doesn't know it,
  and the needs-attention line adds it: `deny#1: letters.draft@3 takes customer as a reference to
  crm, and is given policy_id, a reference to policies`. Types are said as everywhere else (`a
  reference to policies`, `a number`); an outcome or output `is not a reference`; a literal is `a
  value written in the definition`, anything else `a computed value`. The guide says so.
- **`start` and `schedule` take the case** (slice 2), to give `checked_inputs` its fields' types.
- **The approver's check reads conditions by `is not None`** (slice 4, found rereading it): a
  first version kept a condition only if it was truthy, which would have skipped a literal
  `false`.
- **`shown` is also refused for a field the case doesn't have, one not set, and a person not
  written as an identifier** (slice 5), as every event from a person is; `Resolvers.show` refuses
  an unset reference too.
- **`CaseView` gains `systems`** (slice 5): the system of each reference field the viewer may see,
  which `Resolvers.show` reads, so it needs nothing from the definition.
- **A view's sources are sorted tuples, and its values `Any`** (slice 6): the exact converter has
  no JSON form for a set, and Temporal reads a query's result back to its type hints, which it
  can't do for `object`.
- **The tests read the claim from the case data guide's JSON block** (slice 7), so the guide and
  the tests can't drift.

### From the tutor review

- **Refusals and failures quoted values, so the history leaked hidden fields.** With
  `approved_amount` seen only by `support`, Ana answering it as the text `4,812.50` was refused
  with `approved_amount is a number, and the answer gives '4,812.50'`. On Temporal a refusal is a
  history line, and `report` returns the history unfiltered, so Lee, who may not see the amount,
  read it there. The same was true of the opening's type check, 8d's output check, a condition
  that gives anything but true or false, and every expression error that showed a value
  (`` `>` compares numbers, and it was given a string: '…' ``, `division by zero in amount /
  items (250 / 0)`). In 9b, a national ID typed with spaces would have landed in the history in
  plain text.
- **The fix, added to D30:** a refusal or failure names the field and the kind of value it was
  given, never the value: `approved_amount is a number, and the answer gives a string`.
  `a_kind(value)` says it (`a number`, `a string`, `a boolean`, `a binary float`, `a list`), in
  the field types' own words, which is why it says `a string` where the review's example said
  `a text`. Division by zero names the fields only. The `shown` line keeps its reference, as D16
  asks; a sensitive reference is 9b's to encrypt. Layer 2's promise that division by zero names
  "the fields and the values" is replaced: its test now expects the fields alone. The guides,
  and 34 tests that expected a quoted value, say the kind instead.
- **Both negative tests were written first and seen failing:** the review's scenario (the
  refusal quoted `'4,812.50'`), and a sweep over a condition giving a number and four expression
  errors on a field only `fraud` may see (each quoted `4812.77` or the hidden note), with the
  opening's refusal beside them.
- **Carried to 9b:** an activity's own error message (`payments.refund@2 failed: <what it
  said>`) is external text recorded as it came, and may carry sensitive data. 9b decides how it
  is handled.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
Drafted before building, with the tests named in advance; checked against the real tests before
the pull request is opened (every test named exists, and asserts what its row claims). `K` is
`tests/test_catalog.py`, `I` `tests/test_interpreter.py`, `C` `tests/test_case.py`, `D`
`tests/test_case_data.py` (new), `TD` `tests/test_temporal_case_data.py` (new).

Seen failing before their code: every rule on a reference input and `register_system` (accepted,
or no such method); the hash test, once its models shared a name; both openings with an unknown
system (accepted); every wrong value into a reference input, in a case and in a plan (accepted,
the activity called); the view (no `visible_to`, then no view); both of Lee's answers (accepted);
every refused `shown`, and `Resolvers.show` of what the view doesn't show (recorded, crashed or
resolved); the view on Temporal (a set refused by the converter); a refused `shown` on Temporal
(the case hung on it). Passed when written, their code having come with an earlier test: the
refused approval on Temporal (8c already recorded `AnswerRefused`), and the guides' examples and
refusal rows (written after the code).

| Promise | Test |
|---|---|
| A system is registered with a lowercase name | K `test_a_system_is_registered_by_name` |
| A contract's reference names a registered system, also on a copy at registration; it is a text, of one system, also on a copy | K `test_a_reference_input_names_a_registered_system`, `test_every_rule_refuses_a_contract_that_breaks_it`, `test_every_rule_runs_again_when_a_copy_is_registered` (`a reference is a text`, `a reference names one system`) |
| Declaring a reference changes a contract's hash; contracts without one hash as before, and every recorded hash is unchanged | K `test_declaring_a_reference_changes_the_hash`, `test_every_development_contract_matches_its_recorded_hash` |
| The guide's letter is the development `letters.draft@3` | K `test_the_guides_letter_is_the_development_one` |
| A case, or a plan run, whose reference names an unregistered system is refused | D `test_a_reference_to_an_unregistered_system_is_refused`; I `test_a_plan_reference_to_an_unregistered_system_is_refused` |
| A reference input takes only a reference field of its system, read as it is: another system's reference, a field of another type, an outcome, a computed value or a literal fails the step before the activity is called, in a case and in a plan | D `test_a_reference_goes_only_where_its_system_is_expected`; I `test_a_plan_gives_a_reference_input_only_its_system` |
| A reference of the right system goes in, and the guide's `deny` step runs | D `test_a_reference_of_its_system_goes_in`, `test_the_guides_examples_run_as_written` |
| A field hidden from a role is absent from that role's view, and said hidden with the roles that would see it | D `test_a_hidden_field_is_absent_from_the_view` |
| Fields, outcomes and outputs are visible to anyone with a role the case names; a viewer with none sees every field hidden | D `test_what_a_role_on_the_case_sees` |
| The view's lines are the guide's, a field not given reads `not set` | D `test_the_view_reads_as_the_guide_says`, `test_the_guides_examples_run_as_written` |
| An approval or a rejection by someone who can't see a value the step reads is refused, naming it; someone who sees it approves, and the step runs once | D `test_an_approver_must_see_what_they_approve`, `test_an_approver_who_sees_it_approves` |
| `shown` records a line with the system and reference, never the record, and changes nothing else; it is refused for a hidden field, a field that isn't a reference or isn't the case's, and a closed case | D `test_showing_a_record_is_recorded_without_its_content`, `test_shown_is_refused_when_it_cannot_be_true` |
| A resolver is called with the viewer, and only for a reference their view shows; a system with no resolver, or an unregistered one, is refused | D `test_a_resolver_is_asked_on_behalf_of_the_viewer`, `test_a_resolver_shows_only_what_the_view_shows`, `test_a_resolver_is_registered_for_a_registered_system`, `test_the_guides_resolver_example_runs_as_written` |
| On Temporal the view is the same as in memory, filtered in the worker; a refused `shown` or approval is recorded and the case waits on; a history with `shown` replays | TD `test_the_view_on_temporal_is_the_view_in_memory`, `test_refusals_are_recorded_and_the_case_waits`, `test_a_case_history_with_shown_replays` |
| A refusal or failure names the field and the kind of value given, never the value: in a form, the opening, a condition, an expression's error and an output (tutor review) | D `test_a_refusal_names_the_type_never_the_value`, `test_no_failure_quotes_a_hidden_value`, `test_no_opening_refusal_quotes_a_value`; C `test_an_output_the_case_file_cannot_hold_fails_the_step` |
| The guides' refusal rows are what the engine says | K `test_the_guides_refusals_are_what_the_catalog_says` (its new rows); C `test_the_guides_refusals_are_what_the_engine_says` (its new row); D `test_the_guides_refusals_are_what_the_engine_says`, `test_every_refusal_in_the_guide_is_tested` |

---

## 9b. Sensitive fields, keys and the codec

User-facing description, written first: `docs/guides/case-data.md` ("Sensitive data", "On
Temporal: encrypted with the case's key", its refusal table, a common question, design note 10);
`docs/guides/cases.md` and `docs/guides/plans.md` (connecting with `data_converter(keys)`, IDs
without `/`, an activity's message shown as `‹sensitive›`). Decision: brief D31 (drafted with this
note).

### What this part is for

9a hides a field from the view, but anyone with access to the Temporal namespace still reads it in
the history (brief, D16). 9b makes a declared sensitive value unreadable everywhere outside the
worker: encrypted with a key per case, so that 9c can forget a person by destroying one key
(brief, D15).

A small example. The claim declares `national_id`, sensitive, seen by `claims-sensitive`. Ana's
form gives `1 85 05 78 006 084 36`.

- In the state it is `Sensitive("1 85 …")`, whose `str` and `repr` are `‹sensitive›`, so any
  line, message or traceback that formats it writes the placeholder.
- Crossing Temporal, the converter writes `{"‹sensitive›": 0}` in its place and the value's JSON
  as the payload's part `sensitive/0`; the codec encrypts that part with the case's key. The rest
  of the payload (the entry, the outcome, who answered) stays readable.
- Inside the worker the codec decrypts the part and the converter rebuilds `Sensitive(...)`: the
  form's type check, a `when` and a contract's input check read the real value.

### Agreed earlier, checked against `temporalio` 1.34.0

1. **Wrapped in the state, shown as `‹sensitive›`.** SDK-independent. One finding shapes the
   split: the payload converter runs inside the workflow sandbox, the codec's `encode` and
   `decode` are `async` and run outside it. So the converter only splits a value into parts
   (deterministic), and only the codec fetches keys and encrypts.
2. **Each value in its own part, encrypted with the case's key, found from the workflow ID.**
   The codec implements `WithSerializationContext`. Read in the SDK's source: the start,
   signals, queries, the result and continue-as-new get `WorkflowSerializationContext` with the
   case's ID, on the client, the worker and the `Replayer` (the same `_WorkflowWorker` path);
   activity inputs, results and failures get `ActivitySerializationContext`, whose `workflow_id`
   is the case's, on both sides; a child workflow's payloads get the **child's** ID,
   `claim-7/collect#1`. So the key is found from the ID's part before the first `/`, and a case
   ID may not hold one. `encode_common_attributes` applies at every level of a failure's cause
   chain, and the codec walks every cause.
3. **A key is made when the case starts, never again.** SDK-independent: `start_case` asks the
   key provider, then starts the workflow.

### Decided in the session

1. **The dependency: `cryptography`,** for AES-256-GCM, authenticated: a damaged or misplaced
   ciphertext fails to decrypt instead of decoding to something else. The case's ID is the
   associated data, binding each part to its case. Alternatives weighed: the standard library
   has no authenticated cipher (building one from `hmac` and `hashlib` is home-made
   cryptography); PyNaCl is sound but less common. Confirmed after the alternatives were weighed
   again: also PyCryptodome, calling `openssl`, and letting the key provider encrypt. Agreed
   with it: **the key provider seals and opens; it never hands out a key.** `seal(case, data,
   part)` and `open(case, data, part)`, so a key never leaves the provider, which is how Vault's
   transit engine and a cloud KMS already work (brief, D15: keys kept outside Temporal). The codec holds no cryptography: it only finds the parts and hands
   them to the provider. `cryptography` is used in one place, the development provider
   `FileKeys`. A remote provider would be asked once per part; a data key per case, cached
   ("envelope encryption"), is the production adapter's to build, after v1.0.
2. **`answer` encrypts every form value:** the client doesn't know which fields are sensitive. The
   case keeps wrapped only the values of sensitive fields. Cost: a non-sensitive form value is
   encrypted in its signal event, and nowhere else. The same for a plan's `answer`.
3. **An activity's own error message is always sensitive** (9a's question): Ventoux can't know
   what it says, and a Pydantic error on a contract's input quotes the input. The case records
   `pay#1: payments.refund@2 failed: ‹sensitive›` and keeps nothing more; so does a plan, a
   workflow step's failure, and D28's "failed after the close was requested". In Temporal every
   failure's message and stack trace, whoever raised it, crosses as sensitive parts (a failure
   converter on `encode_common_attributes`). Operators read it with the key, through a codec
   server (deployment, after v1.0); forgetting the case (9c) makes it unreadable too. This
   replaces layer 6's promise that a step stops "with its own message".
4. **A workflow step can't be given a sensitive value:** its worker is another team's and doesn't
   hold the key. The step fails before it starts. **Sensitive outputs are not in 9b:** no
   contract can declare one, so an activity's output is plain, as today.
5. **A case ID, and a standalone plan run's ID, has no `/`; a key is made once.** `start_plan`
   makes its run's key too, since its failures are encrypted. If the start fails after the key
   was made, the ID is spent.
6. **A sensitive field must list `visible_to`** (brief, D16). The view's `lines` show
   `‹sensitive›` to everyone; `values` carries the wrapped value to the roles it lists only.
7. **A plain value for a sensitive field is refused at `decide`,** at the opening and in a form:
   it has already been seen in plain text, so the case says so loudly. This depends on nothing
   the client did; in memory `run_case` wraps at its boundary, as the client does.
8. **Where it goes:** `KeyProvider` and the development `FileKeys` in `ventoux.tooling.keys`; the
   codec and the failure converter in `ventoux.temporal`; D31 in the brief.
9. **Cases started before 9b** have no key. Their payloads have no parts, so they replay
   untouched; an activity failing in one would stop with "there is no key", since its failure is
   encrypted. No such case exists outside tests: accepted.

### How it works

**`Sensitive`** (`core/sensitive.py`): a frozen dataclass holding `value`, with `‹sensitive›` as
its text. `core`, because plans hold it too. `unwrapped(values)` gives the plain values;
`reads_sensitive(expression, values)` says whether an expression reads a wrapped value.

**In the case.** The opening and a form wrap the values of sensitive fields, unwrap the others,
and refuse an unwrapped value for a sensitive field. `checked_inputs` evaluates on unwrapped
values, then wraps each input whose expression read a wrapped one; it is in `core`, so plans get
the same rule. A `workflow` step's input reading one fails the step. Conditions and approvals'
`when` read unwrapped values. `case_view` writes values through `str`, so a sensitive line reads
`‹sensitive›`; a `shown` line likewise. In a plan, a field given a sensitive value stays
sensitive for the run; a plan's form values are kept plain, since a field a form sets is never
given at the start.

**Crossing Temporal.** `ExactJSON` writes a `Sensitive` as `{"‹sensitive›": n}` and its value's
exact JSON as the metadata entry `sensitive/<n>`; it reads them back the same way, and refuses an
`encrypted/<n>` part (the payload wasn't decoded) and a dict of its own with the key
`‹sensitive›`. The codec turns each `sensitive/<n>` into `encrypted/<n>`, sealed by the key
provider for the case, and back by opening it. A payload with
no part passes untouched, with no key asked for. The failure converter extends Temporal's
`DefaultFailureConverter(encode_common_attributes=True)`, writing the message and stack trace as
`Sensitive`. `data_converter(keys)` puts the three together; `require_codec` refuses a client or
worker without it, as `require_exact_numbers` does.

**Keys.** `KeyProvider`: `create(case)` makes the case's key and refuses a case that had one;
`seal(case, data, part)` encrypts, `open(case, data, part)` decrypts, each refusing a case with no
key. `FileKeys(path)` keeps 256-bit keys in a JSON file (development only) and seals with
AES-256-GCM: a fresh 12-byte nonce, and the case's ID and the part's name as associated data, so
a part moved to another case or place fails to open.
`start_case` and `start_plan` refuse an ID with `/`, then create the key, then start.

**The activity side.** `as_activity` unwraps its inputs before calling the implementation, so
the contract's own check and the implementation see plain values.

### Where the code goes

- `core/sensitive.py` (new): `Sensitive`, `unwrapped`, `reads_sensitive`.
- `core/before_activity.py`: inputs reading a sensitive value are wrapped.
- `core/interpreter.py`: a plan's fields given wrapped stay wrapped; an activity's failure reads
  `‹sensitive›`.
- `case/definition.py`: `sensitive` on `CaseField`, needing `visible_to`.
- `case/runtime.py`, `case/answers.py`: wrapping at the opening and in forms, the plain-value
  refusal, the workflow step refusal.
- `case/visibility.py`: `values` keep the wrapper.
- `case/memory.py`, `testing.py`: `run_case` and `run_plan` wrap at their boundary; an
  activity's failure reads `‹sensitive›`.
- `tooling/keys.py` (new): `KeyProvider`, `FileKeys`, the only user of `cryptography`.
- `temporal/converter.py`: parts; `data_converter(keys)`, `require_codec`.
- `temporal/codec.py` (new): the codec and the failure converter.
- `temporal/cases.py`, `client.py`, `workflow.py`, `activities.py`, `worker.py`: keys at the
  start, IDs without `/`, form values wrapped, messages shown `‹sensitive›`, inputs unwrapped.
- `pyproject.toml`, `uv.lock`: `cryptography`.

### Not in 9b

- Forgetting and destroying a key (9c); fresh facts (9d).
- Sensitive outputs declared by a contract; a production key provider (Vault, KMS) and a codec
  server for the Temporal UI (after v1.0); the audit export (after layer 15).
- The static check that a sensitive value can't reach a workflow step (case validation, layer
  10); this runtime refusal depends on nothing it does.

### Seams the tests use

- `parse_case`; `run_case(...)` and `CaseRun.view(roles=)`, `run_plan`, their histories.
- `Sensitive`; `FileKeys` (`create`, `seal`, `open`).
- `data_converter(keys)` and its `encode`, `decode`, `encode_failure`, `decode_failure`, given a
  serialization context, for the converter and codec on their own.
- On Temporal's test server: `start_case`, `answer`, `view`, `report`, `start_plan`; the
  workflow handle's `fetch_history()` (events as stored, still encoded) for the raw bytes; the
  `Replayer`.
- The guides' examples, run as written, and each new row of their refusal tables.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Declaring a sensitive field.** Negative: a sensitive field without `visible_to` is refused;
   `str` and `repr` of a `Sensitive` give `‹sensitive›`. Then the guide's view: the line reads
   `‹sensitive›`, the value goes to `claims-sensitive` only.
1. **At the opening and in forms.** Negative: an unwrapped value for a sensitive field, at the
   opening and in a form, is refused; a form value of the wrong type is refused without quoting
   it. Then a form wraps it, and a wrapped value for a field that isn't sensitive is unwrapped.
2. **Into steps.** Negative: a sensitive value given to a workflow step fails the step. Then an
   input reading it (`var` and `cat`) is wrapped, the activity gets the plain value, a condition
   reads it, a plan step's field carries it, and a `shown` line of a sensitive reference reads
   `‹sensitive›`.
3. **An activity's own message.** Negative: an activity failing with a message that quotes the
   value, in a case and in a plan: the history reads `failed: ‹sensitive›`. Layer 6's and 8's
   tests that expected the message change with it.
4. **Keys.** Negative: a second `create` for a case, `seal` or `open` for a case without a key,
   a sealed part opened for another case or part, and an ID with `/` at `start_case` and
   `start_plan` are refused. Then a part sealed is opened back, and its bytes hold no plain text.
5. **The converter and the codec.** Negative: a client without the codec is refused; a part with
   no key, with no workflow ID, or damaged is refused, never passed on; a payload whose parts
   weren't decoded is refused by the converter. Then a value written and read back is the same
   `Sensitive`, its part's bytes hold no plain text, a child's ID finds its case's key, and a
   payload without parts is untouched.
6. **No plain text in history** (the curriculum's negative test). A planted `national_id`, sought
   in the raw bytes of fetched histories and their JSON export: at the opening, in a form refused
   for its type, across a continue-as-new (both runs), into a child plan (the parent's events and
   the child's whole history), and in an activity's failure quoting it. Each seen failing on
   today's converter first. Then `view` gives the value to `claims-sensitive` on Temporal.
7. **Replay.** Negative: a history replayed with a key provider missing its key fails. Then it
   replays with the key, and a history written before 9b (no parts) replays with the codec.
8. **The guides and the promises.**

### Decided while building

- **A plan never keeps a form's value wrapped** (slice 2). The note said a form writing a plan
  field given a sensitive value would wrap it; a plan refuses a field both given at the start
  and set by a form, so that can't happen. A plan's form values are kept plain; its fields given
  wrapped stay wrapped.
- **The helpers about what an expression reads live in `core/sensitive_inputs.py`** (slice 2):
  in `core/sensitive.py` they made a circular import with the evaluator, which unwraps a value
  as it reads it.
- **An approval's digest of a sensitive input is wrapped too** (slice 2, found rereading
  `inputs_digest`): it crosses continue-as-new, and the digest of a national ID is reversed by
  trying every one. A new promise below.
- **The development catalog registers `claims-sensitive`** (slice 2), the guide's role, as 9a
  registered `adjuster` and `fraud`; the plans guide's `UNKNOWN_ROLE` list gains it.
- **An activity's message is wrapped where the message is made** (slice 3): `f"... failed:
  {Sensitive(said)}"` reads `‹sensitive›`, in memory, the interpreter and both workflows. Nine
  tests and the cases guide expected the message; they expect the placeholder.
- **A second case under a used ID is refused by the key provider first** (slice 5): `a key was
  already made for refund-1`, before Temporal's own refusal; 8c's test expects it.
- **The sandbox made two `Sensitive` classes** (slice 5). Temporal's workflow sandbox imports a
  module defining workflows afresh; `ventoux.testing` imports `core` and `case` at its top, so
  their fresh copies were used in the workflow while the converter, built outside, made the
  outside class: `plain()` didn't recognise it, and an answer was refused as `a Sensitive`.
  Workers and replays now run with `SANDBOX` (`ventoux.temporal.worker`), passing `ventoux.core`,
  `ventoux.case`, `ventoux.tooling` and `cryptography` through: one copy, whichever module
  imports them first, as a deployment's own catalog module would too. `cryptography` is compiled
  code, which can't be imported twice.
- **Tests get fresh keys per test server** (slice 5): `development_converter()` in
  `ventoux.testing`, since tests reuse IDs and a key is never made twice. A replay test gives the
  recording's converter to the `Replayer`. `DATA_CONVERTER` is replaced by `data_converter(keys)`.
- **The contract test's run has an ID without `/` and its key** (slice 5), when its client seals
  with Ventoux's codec: its failures are sealed too.
- **Activities on Temporal got the wrapper** (slice 6, found by the curriculum's test: a
  failing lookup quoted `‹sensitive›`, so planting unsealed failures went unnoticed).
  `as_activity` unwraps, as the note said it would; the test checks the code got the ID.
- **A query asked as a case continues as new can go unanswered** (slice 6), as the cases guide
  says: the tests ask again.
- **The guide's refusal rows about keys and clients are checked on Temporal** (slice 8), with the
  other rows, in `TS`.

### From the tutor review

- **The worker's log printed sensitive values.** The history was clean, but Temporal's SDK logs a
  failed activity's exception and traceback (`Completing activity as failed … ApplicationError:
  no record for 1 85 05 78 006 084 36`) before the failure converter seals it, and a failed
  workflow task the same way. Worker logs go to a log pipeline many people read.
- **The fix:** `case_worker` and `plan_worker` install a filter (`temporal/logs.py`) on each of
  Temporal's worker loggers (`temporalio.activity`, `temporalio.workflow` and the three
  `temporalio.worker` modules that log an exception; a logger's filter sees only its own
  records, so each is named). It keeps the record, with the exception's type in place of the
  exception: `Completing activity as failed (…) (ApplicationError)`. Added to D31, with the rule
  that an activity's own logging is its author's, for the deployment guide.
- **Both negative tests were written first and seen failing:** the curriculum's leak test now
  also searches the captured log records, formatted with their tracebacks (it found the ID in
  `Completing activity as failed`); and each of Temporal's worker loggers, given an exception
  quoting the ID once a worker is made (seen failing with the filter's install removed).
- **Optional, taken:** the case's line names the type of what the activity raised: `failed with
  ConnectionError: ‹sensitive›`. `ActivityFailed` moved to `core` to carry it from the plan
  workflow; a child workflow failing because its own activity did reads `ActivityError`. Seventeen
  tests and three guides expect the type now.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
Drafted before building, with the tests named in advance; checked against the real tests before
the pull request is opened (every test named exists, and asserts what its row claims). `S` is
`tests/test_sensitive.py` (new), `TS` `tests/test_temporal_sensitive.py` (new), `I`
`tests/test_interpreter.py`, `TC` `tests/test_temporal_case.py`.

Seen failing before their code: the `visible_to` rule (`sensitive` not a field), the view's line
(the value in plain text), both plain-value refusals (accepted), a form kept unwrapped, the
workflow step, an input read as it is or computed, a condition, a plan step's field and the
digest (each failing on the evaluator not reading a wrapped value), a plan's note kept wrapped,
both activity messages (each quoted the ID), the key provider (no module, then the key's
`key()` method public), the converter and codec (no `data_converter`), the activity's plain
value on Temporal (it got the wrapper). The curriculum's test, written after the codec, was seen
failing twice by planting: a codec that seals nothing (the ID in the opening's bytes), and
failures left unsealed (the ID in the lookup's failure). Passed when written, their code having
come with an earlier test: the refused answer naming its kind, the `shown` line (a wrapped value
writes `‹sensitive›`), the view on Temporal, a client without the codec, IDs with `/`, both
replay tests, and the guide's example and refusal rows.

| Promise | Test |
|---|---|
| A sensitive field must list `visible_to` | S `test_a_sensitive_field_names_who_sees_it` |
| A sensitive value's text is `‹sensitive›`, in `str` and `repr` | S `test_a_sensitive_value_never_prints` |
| The view gives a sensitive value to the roles its field lists only; its line reads `‹sensitive›` for everyone | S `test_who_sees_a_sensitive_value`, `test_the_guides_examples_run_as_written` |
| An unwrapped value for a sensitive field is refused, at the opening and in a form | S `test_a_plain_sensitive_value_is_refused` |
| A form value of the wrong type for a sensitive field is refused naming its kind, never its value | S `test_a_refused_sensitive_answer_names_only_its_kind` |
| A form wraps a sensitive field's value and unwraps any other field's | S `test_a_form_keeps_wrapped_only_sensitive_values` |
| An input reading a sensitive value is wrapped; the activity's code gets the plain value, in memory and on Temporal; a condition reads it | S `test_an_input_from_a_sensitive_value_stays_sensitive`; I `test_a_plan_input_from_a_sensitive_value_stays_sensitive`; TS `test_no_sensitive_value_in_plain_text_in_history` |
| A plan step's field read from a sensitive value carries it into the plan; a plan keeps its form values plain | S `test_a_plan_step_carries_a_sensitive_value`; I `test_a_plan_input_from_a_sensitive_value_stays_sensitive` |
| An approval's digest of a sensitive input is itself sensitive | S `test_an_approval_of_a_sensitive_input_keeps_its_digest_sensitive` |
| A sensitive value given to a workflow step fails the step before it starts | S `test_a_workflow_step_is_never_given_a_sensitive_value` |
| A `shown` line for a sensitive reference reads `‹sensitive›` | S `test_showing_a_sensitive_reference_writes_no_reference` |
| An activity's own message is never recorded, in a case or a plan; the type of what it raised is (tutor review) | S `test_an_activitys_message_is_never_recorded`; I `test_a_plan_records_no_activity_message`, `test_an_activity_failure_stops_the_step` |
| A key is made once per case and never leaves the provider; a case without one can't seal or open; a part opens only for its case and place; a second case under a used ID is refused | TS `test_a_key_is_made_once`, `test_a_part_opens_only_where_it_was_sealed`; TC `test_a_case_id_opens_one_case` |
| A case or plan run ID with `/` is refused | TS `test_an_id_with_a_slash_is_refused` |
| A client or worker without the codec is refused | TS `test_a_client_without_the_codec_is_refused` |
| Each sensitive value crosses in its own part, encrypted with its case's key (a child uses its case's), and comes back the same; the rest stays readable | TS `test_a_sensitive_value_crosses_encrypted`, `test_a_child_uses_its_cases_key` |
| A part the codec can't encrypt or decrypt (no key, no workflow ID, damaged, not decoded) is an error, never plain text; data can't forge the converter's marker | TS `test_the_codec_fails_closed` |
| A payload without parts passes untouched, without a key | TS `test_a_payload_without_parts_needs_no_key` |
| Every failure's message and stack trace crosses as sensitive parts | TS `test_a_failure_crosses_encrypted` |
| No sensitive value is in plain text in a case's history or its export: opening, refused form, continue-as-new, child plan, activity failure; nor in the worker's log (tutor review) | TS `test_no_sensitive_value_in_plain_text_in_history` |
| Each of Temporal's worker loggers keeps only a failed activity's or workflow task's exception type, never its message or traceback, once a worker is made (tutor review) | TS `test_the_workers_log_keeps_only_an_exceptions_type` |
| On Temporal the view gives the value to the roles its field lists | TS `test_the_view_on_temporal_decrypts_for_who_may_see` |
| A history replays with its key, fails without it, and one written before 9b replays with the codec | TS `test_replay_needs_the_key`, `test_a_history_from_before_9b_replays` |
| The guides' refusal rows are what the engine says | TS `test_the_guides_refusals_are_what_the_engine_says`, `test_every_refusal_in_the_guide_is_tested` |

---

## 9c. Forgetting a case

User-facing description, written first: `docs/guides/case-data.md` ("Forgetting a person", its
refusal table, design note 4). Decision: brief D32 (drafted with this note).

### What this part is for

9b encrypted every sensitive value with a key per case so that a person could be forgotten by
destroying one key (brief, D15). 9c destroys it: on a request two people agree, at the one moment
it is safe, and leaving everything else readable for the audit.

A small example. Claim `claim-7` is open; `pay#1` is running. Pia (`privacy`) proposes forgetting
it; Olu (`privacy`) approves. The case begins closing as `forgotten`: the open review is
cancelled, `pay#1` finishes and is flagged (`pay completed after the close was requested`), and
the case closes. Only then is the key destroyed. Afterwards `report` reads the case's closing
report, `view` is refused, and the history holds ciphertext where the national ID was.

### Agreed earlier

From the session that split layer 9 (top of this note): forgetting is its own small workflow,
`<case ID>/forget`; it needs a role registered to forget, and two different people; it closes an
open case as `forgotten`; it then destroys the key through a registered activity.

### Decided in the session

1. **Roles:** `register_role("privacy", forgets=True)`, like `operates=True` (brief, D26). The
   proposer and the approver both hold a role registered to forget, and are different people;
   the development catalog registers `privacy`.
2. **A closed case can be forgotten,** keeping its own close reason, **unless its definition keeps
   its records:** `"forgetting": "allowed" | "while_open" | "never"`, `allowed` by default. Both
   stricter settings are available (books and records need `while_open`); no deployment-wide
   default for now.
3. **`reject` is an answer,** ending the request; without it a request nobody approves waits
   forever.
4. **The key provider gains `destroy(case)` and `state(case)`** (`kept`, `destroyed` or
   `never made`). `FileKeys` keeps a mark for a destroyed key, so `create` refuses the ID forever.
5. **Destroying is a Temporal activity the worker registers,** not a catalog contract: no
   definition may call it, so no case author can forget.
6. **Twice, and a case that never existed, are refused before anyone approves,** from the key
   provider: it holds after Temporal has dropped old workflows, and a refused or rejected request
   can be proposed again (the request's ID reuse policy allows a new run once one has ended).
7. **9b's gap** (an exception nobody retrieves in a case workflow's task is logged with the task's
   repr, which the log filter can't scrub) gets the last slice: shown first, closed if cheap,
   otherwise noted here. *Closed in slice 9.*

### How it works

**The request, `<case ID>/forget`.** A workflow of its own, so the key is destroyed outside the
case: inside it, the case's next workflow task could need a replay, and replay needs the key
(brief, D15). Its ID starts with the case's, so the codec reads it as the case's; none of its
payloads has a sensitive part, so it never asks for the key, and its history stays readable after
the key is gone. In order:

1. **Proposed.** `propose_forget(client, case, by, roles)` starts it. The proposer is checked
   (an identifier, a role registered to forget); refused, the request ends `refused`.
2. **Looked up,** by an activity, before anyone approves: the key's state (`never made`:
   `there is no case …`; `destroyed`: `… was already forgotten`), whether the case's workflow is
   running or closed, and its definition's `forgetting` (read from the case's first event while
   the key exists). `never` is refused here, and `while_open` if the case is already closed.
3. **Answered.** `answer_forget(request, "approve" | "reject", by, roles)`, a signal. An approval
   by the proposer, or by someone without a role to forget, is refused, recorded, and the request
   waits on, as every refusal on Temporal is (8c). A rejection ends it `rejected`.
4. **The case asked to close.** A signal to the case: `ForgetApproved(proposed_by, proposer_roles,
   approved_by, approver_roles)`. The case's `decide` checks it again, depending on nothing the
   request checked: both identifiers, two different people, both roles registered to forget, and
   `forgetting` isn't `never`. An open case begins closing (brief, D10): `cancelled review#1: the
   case is being forgotten`, then `closed: forgotten`. A case already closing (closed by a person)
   records the request and closes with its own reason. If the signal finds the case's workflow
   already ended, the request records `claim-7 was already closed`, and refuses if its
   definition says `while_open` (it closed before the approval landed).
5. **Waited for.** An activity waits until the case's workflow has *ended* and returns the report
   it returned. A signal back from the case would not do: after sending it, the case still has a
   workflow task to complete, which a replay would need the key for.
6. **Destroyed.** An activity calls the key provider's `destroy`; it refuses while the case's
   workflow is still running (fail closed, a second guard on the order) and is retried until it
   succeeds, as a system being down is (brief, D17). Destroying a destroyed key does nothing, so a
   retried attempt is safe.
7. **Recorded.** The request ends `forgotten`; `forget_report(request)` gives its status and lines:
   who proposed and approved, each refusal, the case's closing line and flags, the key destroyed.

**Reading a forgotten case.** The client's `report` asks the key provider first and, for a
destroyed key, returns the case's workflow result: the `CaseReport` it returned when it closed,
which holds lines and placeholders, no sensitive part, so no key. `view` is refused (`… was
forgotten: its case file can't be read`). Anything else that replays the history (a query sent
another way, the `Replayer`) reaches the codec, whose provider refuses: `the key of claim-7 was
destroyed when it was forgotten`. The failure sent back can't be sealed either; slice 0 found
that the SDK then sends the codec's own error in its place (`Failed encoding completion: …`), so
the operator reads the provider's message, which names only the case.

**What stays readable** (the curriculum's "check yourself"). Without any key: the case's closing
report; the forget request's whole history; in the case's history, every payload's data as
stored (the definition, each answer's entry, outcome, person and roles, each activity's inputs
and outputs that weren't sensitive), with `{"‹sensitive›": n}` where a sensitive value was.
Unreadable for good: every sensitive value; every form value in an answer's signal (D31 seals
them all, since the client can't tell which are sensitive); every failure's message and stack
trace. Staff identifiers stay: they are what the audit is for; forgetting is about the case's
subject, through its sensitive fields.

**How it fits layer 12.** `forget` is the first change request: proposed, approved by someone
else, applied. Layer 12 builds the general mechanism (case-file edits, migrations). 9c keeps the
shape it will reuse: a small workflow per request, the rule "registered roles, two different
people, the proposer doesn't approve" as a pure function in `case`, and an *apply* step, here
"close, wait for the case to end, destroy the key". A release migration changing `forgetting` on
an open case is layer 12's question.

### Where the code goes

- `core/catalog.py`, `core/roles.py`: `register_role(..., forgets=True)`, `forgetters`.
- `case/definition.py`: `forgetting` on the definition.
- `case/forgetting.py` (new): the checks on a proposal and an answer; the case's check of
  `ForgetApproved`.
- `case/state.py`, `case/runtime.py`, `case/closing.py`: `ForgetApproved`, closing as `forgotten`.
- `case/memory.py`, `testing.py`: a script's `forget(proposed_by, approved_by)`; `privacy` in the
  development catalog; a development forget workflow.
- `tooling/keys.py`: `destroy`, `state`, the destroyed mark, the forgotten message.
- `temporal/forget.py` (new): `ForgetWorkflow`, its activities, `propose_forget`,
  `answer_forget`, `forget_report`.
- `temporal/cases.py`: the `forget` signal; `report` and `view` of a forgotten case.
- `temporal/worker.py`: `case_worker` registers the forget workflow and its activities.

### Not in 9c

- Forgetting a standalone plan run (it has its own key; nothing asks for it yet).
- A production key provider's `destroy` (Vault, KMS: a KMS deletes a key after a waiting period;
  the deployment guide says so, after v1.0); the audit export (after layer 15); a codec server.
- A deployment-wide default for `forgetting`; forgetting a member of staff.
- Change requests in general (layer 12).
- No new dependency.

### Seams the tests use

- `catalog.register_role(..., forgets=True)`; `parse_case`.
- `run_case(...)` with the script's `forget`, and what it reports; `FileKeys` (`create`, `seal`,
  `open`, `destroy`, `state`).
- On Temporal's test server: `start_case`, `answer`, `close`, `report`, `view`; `propose_forget`,
  `answer_forget`, `forget_report`; the case handle's `fetch_history()` and `query`; the
  `Replayer`; captured log records.
- The guide's example, run as written, and each row of its refusal table.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **What Temporal does without a key, today.** A closed case whose key is removed by hand: a
   query on it, and a replay, are expected to fail with the provider's message and leave the
   worker running. Seen as it is first; what it shows decides the codec's part of slice 6. And a
   signal from one workflow to another that has ended: how it fails.
1. **Keys.** Negative: `destroy` of a key never made; `seal`, `open` and `create` after
   `destroy`. Then `state` reads each state, and `destroy` twice does nothing.
2. **Roles and the definition.** Negative: `forgetting` given anything but its three values;
   `forgets` on a role that isn't registered. Then `allowed` by default.
3. **In memory.** Negative (the curriculum's): forgetting approved by its proposer is refused;
   so is a proposer or approver without a role to forget, and a case that says `never`. Then an
   open case closes as `forgotten`, its tasks cancelled, a running activity finishing and flagged.
4. **The request on Temporal.** Negative: a proposal by a role that can't forget ends `refused`;
   the proposer's approval and one without the role are recorded, and the request waits on; a
   case never made and one already forgotten are refused before anyone answers. Then `reject`
   ends it, and an approval closes the case and destroys the key.
5. **Order.** Negative: the key is still there while an activity, a child plan, or a workflow
   step of the case runs, and `destroy` refuses while the case's workflow runs. Then it is
   destroyed once the case's workflow has ended, and what finished after the close is flagged.
6. **Closed cases and records.** Negative: a closed case that says `while_open`, and any case
   that says `never`, are refused, nothing destroyed. Then a closed `allowed` case is forgotten
   and keeps its close reason, and the ID can't open a case again.
7. **Reading a forgotten case.** Negative: `view` is refused; a query and a replay fail with the
   forgotten message, never plain text, and the worker answers the next case. Then `report`
   reads the closing report.
8. **The audit after forgetting** (the curriculum's "check yourself"). What stays and what goes,
   as "How it works" lists it, sought in the fetched history, its JSON export and the reports.
9. **9b's gap.** An exception raised in a case workflow's task, quoting a value: shown in the log
   first; then closed if cheap, or noted.
10. **The guides and the promises.**

### Decided while building

- **Reading a case without its key already fails cleanly** (slice 0). With a closed claim's key
  taken out of the key file by hand: its workflow result (the closing report) reads without a
  key; a `report` query fails at once with `Failed encoding completion: there is no key for
  claim-7, so its sensitive values can't be read or written`. The workflow task fails on the
  codec's refusal; the SDK then can't seal that failure (no key), and sends the codec's error in
  its place, never what the failure said. The worker's log reads `Failed handling activation …
  (KeyRefused)`, the type only, and the worker answers the next case; a `Replayer` fails with the
  same message. So the codec needs no change for a forgotten case: slice 7 checks the message
  once `destroy` gives its own. The SDK also retried the query's task once, with no workflow ID
  given to the codec (`a sensitive part has no case …`): failed closed, no text, nothing to fix.
  Both tests passed when written: they measure what Temporal does, and were seen failing with the
  key left in place (the query answered).
- **Temporal can't tell a case that ended from one that never existed** (slice 0): a signal from
  the request to either fails with `Unable to signal external workflow because it was not found`.
  So the key provider's `state`, looked up before anyone answers, is what tells them apart,
  as step 2 planned.
- **The provider's new method is `state`, not `key_state`** (slice 1). 9b's test that the key
  never leaves the provider refuses any public method starting with `key` or `get`; that guard is
  worth more than the name. `keys.state("claim-7")` gives `kept`, `destroyed` or `never made`.
- **A destroyed key leaves a mark** (slice 1): the key file holds `null` for the case, so `create`
  refuses the ID forever and `state` says `destroyed`. A missing key and a destroyed one say
  different things: `there is no key for …` and `the key of … was destroyed when it was
  forgotten: …`. The first version read both as `None` and said `destroyed` for a case with no
  key; 9b's `test_a_key_is_made_once` caught it.
- **`FileKeys` forgets by rewriting its file** (slice 1): the key's text is gone from it, but a
  copy of the old file (a backup, a disk block) may keep it. Development only, as it always was;
  a production provider's destruction is its own (deployment guide, after v1.0).
- **`forgetting` is refused in Pydantic's words** (slice 2): `forgetting: Input should be
  'allowed', 'while_open' or 'never'`, as a contract's `risk` already is (activities guide). A
  missing setting is `allowed`; `true`, `null` or a misspelling is refused, never read as one.
- **`forgets` is registered with the role, so it can't name an unregistered one** (slice 2): the
  slice's planned negative ("`forgets` on a role that isn't registered") can't be written. The
  negatives are a catalog where no role forgets until one is registered to, and a role name that
  isn't a label. A forgetting role approves no risk by itself.
- **The case's checks, in order** (slice 3): each person written as an identifier (`Pia` and
  `pia` would otherwise be two people, and one person could approve their own request); the case
  not closed; its definition not `never`; the proposer's role, then the approver's; then two
  different people. Messages name the case by its ID, the part of the case's name before its
  first run's (`memory` in memory). An approved request is recorded with the role that counted
  for each: `forgetting approved by olu as privacy, proposed by pia as privacy`.
- **A closed case refuses the event** (slice 3), as `shown` does: `the case is closed: nothing
  records it any more`. On Temporal it never arrives (the case's workflow has ended); the
  request handles a closed case itself (slice 6).
- **The development catalog registers `privacy`** (slice 3), the guide's role; the plans guide's
  `UNKNOWN_ROLE` list gains it, as it gained 9b's.
- **Citations are written one by one** (slice 3): `(brief, D15) (brief, D32)`, as the decisions
  test reads them; a first `(brief, D15, D32)` was refused by it.
- **`case_worker` takes the request's workflow as `forget=`** (slice 4), optional: given it, the
  worker also serves `<case ID>/forget` and its activities. A deployment subclasses
  `ForgetWorkflow` to name its catalog, as it subclasses `CaseWorkflow`; `DevelopmentForget` is
  the development one. The existing callers stay as they were.
- **The request's activities are methods of `ForgetActivities(client)`** (slice 4): the key
  provider comes from the client's codec (`keys_of`), and the case's workflow from the client.
  `key_state` reads the key; `case_ended` waits for the case's workflow result, saying it is
  alive every ten seconds, and returns the case's closing report; `destroy_key` destroys it.
  The request records the case's last line and its flags from that report.
- **A rejection needs a role registered to forget, and may come from the proposer** (slice 4): it
  changes nothing, so withdrawing one's own request is allowed. An approval needs the role and
  someone else. An answer other than `approve` or `reject` is refused and recorded.
- **What the request records:** `pia proposed forgetting claim-7, as privacy`, `approved by olu,
  as privacy`, `claim-7 asked to close as forgotten` (or `claim-7 was already closed`), `claim-7
  ended: closed: forgotten`, each flag, `the key of claim-7 was destroyed`. A refused proposal
  is one line, `refused pia's proposal: …`, and the request ends `refused`.
- **Two ways a request could wait for ever, noted** (slice 4): a case that refuses the approved
  request (`never`, checked by the request itself in slice 6) stays open, and the request waits
  for it to end; a case whose workflow *failed* rather than closed makes `case_ended` fail, and
  Temporal retries it. Both fail closed (nothing is destroyed). The second is a case that could
  not open; it is left as it is, since such a case holds no decision to keep. *Corrected in the
  tutor review:* that case still holds the national ID its opening sent, sealed with its key; it
  is forgotten now (see "From the tutor review").
- **`destroy_key` refuses while the case's workflow runs** (slice 5), whoever asks: `claim-7 is
  still running: its key is destroyed once its workflow has ended`, and Temporal retries it. It
  asks Temporal for the case's latest run; a case Temporal no longer remembers counts as ended,
  since nothing of it can still run.
- **The order, tested three ways** (slice 5): forgotten while a payment runs, while a plan step's
  lookup runs in its child, and while a workflow step (the KYC team's check) runs. Each time the
  case is `closing`, the request `closing the case` and the key `kept`; once the work is
  released, the case closes as `forgotten` (flagged for what finished after the close) and only
  then is the key destroyed. The three tests passed when written, the order coming with
  slice 4's wait for the case's workflow to end; each was seen failing with that wait and the
  guard removed (the key destroyed while the work ran). The workflow step's test sits beside
  8d's, in `tests/test_temporal_workflow_step.py` (`WS`), where the KYC team's worker runs.
- **A first version of the payment test passed for the wrong reason** (slice 5): its review form
  gave `40` as a Python `int`, which the case refuses, so the payment never ran and the case had
  nothing in flight when it was forgotten. The test now asserts the payment ran before the
  request is made.
- **The request reads the case's definition before anyone answers** (slice 6): one activity,
  `look_up`, gives the key's state, whether the case's workflow runs, and its definition's
  `forgetting`, read from the start of the case's latest run (each run carries the definition),
  decoded as the case's with its key. It replaces slice 4's `key_state`.
- **A definition that can't be read is refused** (slice 6), fail closed: `claim-6's definition
  can't be read: Temporal holds no history of it, so whether it keeps its records is unknown`.
  It happens when a case's start failed after its key was made (the ID is spent, brief, D31), or
  once Temporal has dropped a closed case's history: Temporal's retention, not the records', then
  decides. Erasing such a case needs the key provider's own tools, outside Ventoux.
- **The race is refused after the approval** (slice 6): a `while_open` case open when proposed
  and closed by itself before the approval reached it is refused once the signal finds it ended:
  `refused: claim-9 closed before forgetting was approved, …`, and nothing is destroyed. The
  guide's refusal table gains this row and the unreadable definition's.
- **Slice 4's first gap closes** (slice 6): the request refuses `never` before anyone answers, so
  the case never receives a request it refuses. Only a definition changed while the request
  waits could still do it, and changing a running case's definition is layer 12's.
- **Seen failing:** `never` first (the request waited for an answer, until the time-skipping
  server timed it out); the other three refusals were written with it, so each was seen failing
  by removing its check (two waited, the race forgot the case). A closed case being forgotten and
  a forgotten ID opening no case passed when written: their code came with slices 4 and 1.
- **`report` of a closed case reads its result** (slice 7), for every closed case, forgotten or
  not: the report the case returned when it closed, which holds no sensitive part, so it needs
  no key and no replay. A running case is asked by query, as before. The cases guide says so.
  Slice 0's measuring test now sends its query directly (`case.query(...)`), since `report`
  no longer queries a closed case.
- **`view` tells a forgotten case by the provider's own words** (slice 7): a handle holds no key
  provider the client can ask, so `view` reads the query's failure, and when it carries the
  provider's `was destroyed when it was forgotten` (`FORGOTTEN`, in `tooling/keys.py`) it says
  `claim-7 was forgotten: its case file can't be read` instead. Any other failure is raised as
  it came.
- **What an operator sees** (slice 7, tested with a key a request destroyed): `report` gives the
  closing report; `view` is refused as above; a query sent another way fails at once with
  `Failed encoding completion: the key of claim-7 was destroyed when it was forgotten: …`; a
  replay fails with the same message; the worker answers the next case; no log record holds the
  national ID. The view's refusal was seen failing first (Temporal's raw query failure came
  through); `report` changed with it; the query, the replay and the worker passed when written,
  as slice 0 had measured.
- **The audit after forgetting, read as Temporal stores it** (slice 8, the curriculum's "check
  yourself"), on 9b's richest case (a national ID at the opening, a tax ID in Ana's form, a
  lookup failing with a message quoting the ID, a child plan, several runs), forgotten by Pia and
  Olu. *Gone:* neither ID in any history's raw bytes or JSON export (the case's runs, the child's,
  the request's); the opening, and the lookup's failure (`Encoded failure`, its text only in the
  sealed part), no longer open: `the key of claim-7 was destroyed when it was forgotten`.
  *Kept, with no key:* the definition (`"case": "claim"`, its rules), each answer's entry,
  outcome, person and roles (`assess#1`, `accept`, `ana`, `adjuster`), with the form's tax ID a
  placeholder; the approved request, both people and their roles; a value that wasn't sensitive
  where the case carried it (`estimated_damage` 1200, in the next run's start); the case's
  closing report; and the request's history, which replays with a converter holding no key.
  Staff identifiers stay. It passed when written, measuring what 9b and slices 4–7 built; it was
  seen failing with `destroy_key` destroying nothing (the opening still opened).
- **9b's gap was worse than a log line, and is closed** (slice 9). Shown first with a case
  workflow whose `run_activity` raises a `ValueError` quoting the national ID, standing for an
  engine bug: the exception stayed in its task, the case stayed `RUNNING` for ever with the
  step scheduled and never back (an engine bug lost, where D17 says it must block), and at the
  worker's shutdown Temporal's SDK logged `Task exception was never retrieved` with the task's
  repr, quoting the exception's text, which the filter can't scrub (it keeps the message).
  The fix, a few lines in `temporal/cases.py`: every task beside the loop runs through
  `beside`, which keeps an exception it raises; the loop raises it, so the workflow task fails
  (Temporal retries it until fixed code is deployed) and the log reads `Failed activation on
  workflow ventoux.case … (ValueError)`, the type only. The test waits for that record, sees
  the case held where the bug struck (its last event a started workflow task, still running),
  and finds the ID in neither the log nor the history; it was seen failing on the old code (the
  task completed and the case went on).
- **Temporal doesn't write `WorkflowTaskFailed` at once** (slice 9): the first version of that
  test waited for the event and never saw it, though the worker had failed the task; the history
  ends with the task started. The test reads the worker's log record and the history's last
  event instead.
- **The guide's example was written before the code, and was wrong in three places** (slice 10):
  `propose_forget` takes the deployment's request workflow and a task queue; the guide didn't
  show the request's subclass or the worker's `forget=`; and it didn't say who may reject. It
  now shows each, and its example runs as written: the role registered on a fresh catalog, the
  subclass checked, the guide's own `case_worker` line serving the `claims` queue, and its
  request forgetting a closed claim. The subclass runs through `exec` given a module name:
  without one, Temporal's check that `run` is defined on the class fails.
- **The guide's refusal rows are compared with the code that says them** (slice 10): the role,
  approval and lookup checks and `closed_first` (the race's message, moved into a function so
  a test can read it) are pure; the destroyed key's message comes from `FileKeys`; the view's
  refusal from Temporal. A row edited by a word was seen failing.
- **Promises checked against the tests** (slice 10): every test named exists and asserts its
  row. Four claims had no test and gained one: an open approval cancelled when the case is
  forgotten; a rejection refused without the role, and accepted from the proposer; a new
  request accepted after a rejection; an answer other than `approve` or `reject` (already
  tested, now in the table). All passed when written: their code came with earlier slices.

### From the tutor review

- **A case that ended without a result kept its key.** `case_ended` waited on the case's
  workflow result, which a case refused at its opening, terminated by an operator (brief, D19),
  failed or timed out doesn't have: the activity failed, Temporal retried it for ever, and the
  request sat at `closing the case` with the key kept. A refused opening had already sent its
  national ID, sealed with that key. Slice 4 had noted the failed case and left it, wrongly.
- **The fix:** `case_ended` asks Temporal until the case's latest run no longer runs, however it
  ended (`describe`, as `destroy_key`'s guard does, a little less often each time, saying it is
  alive), reads the returned report only if the case completed, and otherwise records how it
  ended: `claim-7 ended: failed`, `claim-8 ended: terminated`. Then the key goes.
- **`report()` could hang while a case continued as new,** which turned CI red
  (`test_a_switch_waits_while_a_workflow_runs`, 3 in 30 runs here). 8c's note told API writers
  to ask with a short timeout and again; `report()` itself didn't, and slice 7's `describe`
  before the query shifted the timing onto the switch.
- **The fix:** `report()` asks each question with a two-second `rpc_timeout`, asks again up to ten
  times, then raises `CaseUnanswered`. The SDK says a client's own timeout as `CANCELLED`
  ("Timeout expired"), not `DEADLINE_EXCEEDED`: a first version caught only the second and
  still failed 1 run in 30. The cases guide says `report` asks again, and that a query of one's
  own should too.
- **All negative tests were written first and seen failing:** both endings (the request never
  reached `destroy_key`, and the test timed out); the switch test, 3 failures in 30 runs before
  the fix, 60 passes in 60 after; and a new test where nothing serves the case's queue, which
  hung on the old `report()` and now raises `CaseUnanswered` after its tries.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
Drafted before building, with the tests named in advance; checked against the real tests before
the pull request is opened. `F` is `tests/test_forget.py` (new), `TF`
`tests/test_temporal_forget.py` (new), `K` `tests/test_catalog.py`, `WS`
`tests/test_temporal_workflow_step.py`.

| Promise | Test |
|---|---|
| A role may be registered to forget; none forgets unless registered to; it approves no risk by that | K `test_a_role_may_be_registered_to_forget` |
| `forgetting` is `allowed`, `while_open` or `never`, `allowed` by default; anything else is refused | F `test_a_definition_says_whether_it_may_be_forgotten` |
| A key can be destroyed, and its text is gone from the provider; a destroyed key never seals, opens or is made again, saying the case was forgotten; a key never made can't be destroyed | F `test_a_destroyed_key_is_gone_for_good` |
| The provider says whether a case's key is kept, destroyed or never made, after Temporal has dropped the case; destroying it again does nothing | F `test_a_keys_state_tells_which_case_it_is` |
| Forgetting approved by its proposer is refused (the curriculum's negative test), in memory and on Temporal, where it is recorded and the request waits on; so is an answer other than `approve` or `reject` | F `test_the_proposer_cannot_approve_forgetting`; TF `test_refused_answers_are_recorded_and_the_request_waits` |
| A proposer or approver without a role registered to forget is refused | F `test_forgetting_needs_a_role_registered_to_forget`; TF `test_a_proposal_without_the_role_is_refused`, `test_refused_answers_are_recorded_and_the_request_waits` |
| The case checks the approval itself, depending on nothing the request checked: identifiers, a closed case, `never` | F `test_the_case_checks_forgetting_itself` |
| An approved request closes an open case as `forgotten`: open tasks and approvals cancelled, running work finishing, what completes after the close flagged; a case already closing keeps its reason | F `test_forgetting_closes_an_open_case`; TF `test_forgetting_an_open_case` |
| A rejection needs a role registered to forget and may come from the proposer; a rejected request ends, nothing is closed or destroyed, and a new request may be proposed | TF `test_a_rejected_request_changes_nothing` |
| The key is destroyed only once the case's workflow has ended: never while an activity, child plan or workflow step of it runs; `destroy` refuses while it runs | TF `test_the_key_goes_only_after_the_case_has_ended`, `test_the_key_goes_only_after_a_child_plan_has_ended`, `test_destroy_refuses_while_the_case_runs`; WS `test_forgetting_waits_for_a_workflow_step` |
| A case never made, and a case already forgotten, are refused before anyone answers | TF `test_forgetting_needs_a_case_with_a_key` |
| A closed case can be forgotten and keeps its close reason, unless its definition says `while_open` (also when it closed before the approval); `never` is always refused; a definition that can't be read is refused; nothing is destroyed when refused | TF `test_forgetting_a_closed_case`, `test_a_case_that_keeps_its_records` |
| A forgotten case's ID never opens a case again | TF `test_a_forgotten_id_opens_no_case` |
| After forgetting, `report` reads the closing report, `view` is refused, and a query or replay fails with the forgotten message, never plain text; the worker carries on | TF `test_reading_a_forgotten_case` |
| After forgetting, the history, its export and the reports keep every decision, who made it and as what, the definition, the values that weren't sensitive where they were used, and the closing report; every sensitive value, form value in an answer and failure message is unreadable; the request's own history replays without a key | TF `test_what_the_audit_keeps_after_forgetting` |
| A case that ended without a result (refused at its opening, terminated by an operator) is forgotten all the same: the request records how it ended, and the key is destroyed (tutor review) | TF `test_forgetting_a_case_that_ended_without_a_result` |
| `report` never hangs: each question has a short timeout and is asked again a bounded number of times, then it says the case didn't answer (tutor review) | TF `test_a_report_never_hangs`; WS `test_a_switch_waits_while_a_workflow_runs` |
| An exception raised in a case workflow's task fails its workflow task, holding the case until fixed code is deployed; the log keeps its type, never its text (9b's gap) | TF `test_an_engine_bug_in_a_task_blocks_the_case` |
| The guide's example runs as written, and its refusal rows are what the engine says | TF `test_the_guides_forget_example_runs_as_written`, `test_the_guides_refusals_are_what_the_engine_says`, `test_every_refusal_in_the_guide_is_tested` |

---

## 9d. Fresh facts

User-facing description, written first: `docs/guides/case-data.md` ("Fresh facts", its refusal
table, design note 5). Decision: brief D33 (drafted with this note), adding to D18 and D25.

### What this part is for

A case file is a snapshot: `check_order.status` is "delivered" *as of when the order was looked
up*. Three weeks later a refund can go out on an order returned last week, and nothing in the
case says the status is old. 9d gives every fact the time it was obtained, lets a step say how
fresh the facts it uses must be, and refreshes a stale fact before the step runs, or asks a
person when it can't (brief, D18).

A small example. On day 0, `check_order#1` (`orders.lookup@1`, effect `read`) gives
`check_order.status`, obtained at day 0 by `check_order#1`. `pay` reads it in its `when` and says
`"max_age": {"check_order.status": "1d"}`. On day 3 the review is approved: that event is decided
at day 3, so the fact is 3 days old. `pay` doesn't start; `check_order#2` runs, with its own
entry and key, and gives "returned". `pay`'s condition is checked again on the new value, and
the refund never runs.

### Agreed earlier

From the session that split layer 9 (top of this note): time reaches `decide` as data on each
event, as whole seconds since the epoch, and `datetime` stays banned in `core` and `case`; on
Temporal it is stamped from `workflow.now()`; a stale fact is refreshed only from a read-only
step, otherwise the case needs attention; approval sheets show the age of each fact.

### Decided in the session

All as proposed, 2026-10-15.

1. **Time on each event:** every event type gets a required `at: int`, seconds since the epoch,
   with no default. The engine never supplies a time. In memory the script gives it: `run_case`
   starts at `ventoux.testing.START` unless given `at=`, and `later("3d")` moves time on; a
   result fed back by the driver carries the time of the event that started its run. On
   Temporal each event is stamped as it enters the inbox, `int(workflow.now().timestamp())`.
2. **Where it is kept:** `state.obtained[field] = Obtained(at, run)`, beside `state.sources`, for
   every value written: the opening, a form's fields, a task's outcome, an activity's or a
   workflow's outcome and outputs, a plan step's outcome. `run` is the step run that gave it
   (`check_order#1`), or None for the opening and for people.
3. **`max_age`'s shape:** on activity, workflow and plan steps, `{"<field>": "<age>"}`. An age is
   a whole positive number and a unit, `m`, `h` or `d`, read by a small named function into
   seconds. Refused when the definition is read: an unknown unit, zero, and a field the step
   doesn't read (its inputs, its `when`, its approval's `when`).
4. **When it is checked:** in admission, once `requires` are met, before the step's `when`, its
   approval's `when`, asking for the approval and starting. Stale means `at − obtained > max_age`.
   A fact the step needs fresh with no recorded time stops the step (fail closed).
5. **What is refreshed:** only an output or outcome of an activity step whose contract's effect is
   `read`. A fact from the opening, a person, an activity whose effect is `write`, `notify` or
   `compute`, a workflow step or a plan step makes the step fail: the case needs attention
   (brief, D17). `compute`: run again on the same inputs it gives the same answer, so its age is
   its inputs' age, and re-running it gains nothing.
6. **A refresh is a new run:** `check_order#2`, its own entry and key (brief, D17), checked as
   every run is: its requirements, its inputs' sources, its own `max_age`. Its output and outcome
   replace the old ones, with fresh sources and a fresh time. The step that needed the fact
   waits (pending work, brief, D10). If the refresh fails, or gives an outcome other than `done`
   (so no output is written, brief, D29), the fact is still stale and the step that needed it
   fails, saying so: never a second refresh for the same need, so never a loop.
7. **Approvals:** an open approval follows the case file as before (brief, D25): withdrawn if
   the refresh changes what it saw, standing if not. A given approval not yet spent records what
   it saw, as an open one does (`seen`, beside D11's digest); a refresh that changes any of it
   lapses the approval, recorded with the reason, and the step goes through admission again: its
   condition re-checked, a new approval asked if one is still needed. A lapse from a change
   request (layer 12) still stops the step.
8. **Ages for people:** `CaseView.obtained` gives each visible value's time; a hidden field's time
   is absent with it. `approval_sheet(entry, roles, at)` lists each fact an open approval depends
   on, `check_order.status: delivered, obtained 3 days ago`. The caller gives `at`: a sheet is
   read, never decided on, so the reader's clock is safe; on Temporal the client reads the API's
   clock when none is given, outside `core` and `case`.
9. **Sensitive facts:** a contract has no sensitive output (brief, D31), so a refreshed value is
   never sensitive; a stale sensitive fact came from the opening or a person, so the step needs
   attention, and the message names the field, never the value. A refresh whose inputs read a
   sensitive field gets it wrapped, as any run does. A time obtained is plain data.
10. **Not in 9d:** the source's own as-of time (a contract change, and nothing needs it yet);
    timers (layer 11); case validation of `max_age` (layer 10). No new dependency.

### Decided while drafting, confirmed in the session

- **A workflow step whose contract is `read` (`kyc.check@1`) isn't refreshed.** Choice 5 was
  proposed on the belief that workflow contracts declare no effect; they do. D18's rule ("if that
  step is read-only") would allow it. Kept out as agreed: a workflow belongs to another team and
  may take minutes (its `timeout` is 600 s for `kyc.check@1`), so re-running it unasked is a
  bigger step than a lookup.
- **A running refresh doesn't undo its step's earlier run.** While `check_order#2` runs,
  `check_order` still counts as done for `requires`. Otherwise every refresh would withdraw the
  open approvals of every step requiring `check_order` ("check_order started again", brief, D25),
  even when the new value turns out the same, breaking "a refresh that changes nothing leaves it
  standing". Only what the refresh changes counts.
- **One refresh at a time per step.** A step whose stale fact is already being refreshed waits
  for it; two steps needing the same fact share one refresh.
- **State carried from before 9d has no times.** A case that continues as new from a run built
  before 9d carries no `obtained`; its facts have no known age, so a step needing one fresh stops
  (choice 4). Replay is unaffected: stamping adds no command, so histories written before 9d
  replay as they are.

### How it works

**Time.** `decide(case, catalog, state, event)` reads `event.at` and nothing else for time;
an `at` that isn't a whole number (a float, a `Decimal`, a boolean) is refused before anything
changes, on nothing a type checker did. Each value `decide` writes gets `Obtained(event.at,
run)`. The in-memory driver passes the current time on to the events it feeds back; on Temporal
the workflow stamps each event as it enters the inbox, so an answer decided later keeps the time
it arrived. Temporal's workflow time comes from history, so a replay stamps the same times.

**Freshness, in admission.** For each step whose `requires` are met, before anything else is
read: each field in its `max_age` is looked up in `state.obtained`. All fresh: admission goes on
as before. One stale:

1. It came from a run of an activity step whose contract's effect is `read`, and no refresh of
   it was made for this need yet: a new run of that step is scheduled, recorded as
   `refreshing check_order.status for pay: obtained 3 days ago, at most 1 day`, and the step
   waits.
2. A refresh for it already ran and the fact is still stale: the step fails, saying why.
3. Anything else: the step fails, saying where the fact came from and why it can't be fetched
   again.

When the refresh completes, its output lands as any output does (brief, D29), with
`Obtained(at, "check_order#2")`; `follow` withdraws open approvals whose values changed, a given
approval whose values changed lapses, and admission runs again with the new value.

**Ages.** `ago(seconds)` gives the largest whole unit, rounded down: `less than a minute`,
`12 minutes`, `5 hours`, `3 days`, `3 weeks`. The sheet's line for each fact the approval's step
reads is `<title or name>: <value as read>, obtained <age> ago`, `‹sensitive›` for a sensitive
value, `hidden (needs …)` for one the reader can't see. History lines say an age the same way;
none quotes a value.

**Continue-as-new.** `state.obtained` crosses with the rest of the state (brief, D27), each time
written as a JSON integer and read back as an `int`: the exact-number converter reads JSON
numbers as decimals, so the reader converts each one back, and a test checks the times come back
equal and of type `int`.

### Where the code goes

- `case/definition.py`: `max_age` on activity, workflow and plan steps, and its checks.
- `case/freshness.py` (new): an age read from `"1d"`; whether a step's facts are fresh; what to
  do with a stale one; `ago`.
- `case/state.py`: `at` on every event; `Obtained`; `state.obtained`; `seen` on `GivenApproval`;
  a step run's `refreshes` (which step's need it serves).
- `case/runtime.py`, `case/approvals.py`, `case/admission.py`: times written with each value;
  the freshness check in admission; a given approval lapsing on a refresh; a refresh not undoing
  `requires`.
- `case/visibility.py`: `CaseView.obtained`; `approval_sheet`.
- `case/memory.py`, `testing.py`: times in the driver; `START`, `DAY`, `later`, `run_case(at=)`,
  `CaseRun.approval_sheet`.
- `temporal/cases.py`, `temporal/carried.py`: stamping from `workflow.now()`; the `approval_sheet`
  query and client function; `obtained` crossing continue-as-new.

### Seams the tests use

- `parse_case`; `decide` (for an event's time).
- `run_case(..., at=)` with `later(...)`, and what it reports: `history`, `needs_attention`,
  `waiting_for`, `reached`, `view(roles).obtained`, `approval_sheet(entry, roles, at)`.
- On Temporal's time-skipping test server: `start_case`, `answer`, `report`, `view`,
  `approval_sheet`; the environment's `sleep` to let time pass; `fetch_history()` and the
  `Replayer`; a case made to continue as new.
- The guide's examples, run as written, and each row of its refusal table.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Time on events.** Negative: an event whose `at` isn't a whole number is refused and changes
   nothing. Then each value written records its time and run: opening, form, outcome, output.
   The quickstart's acceptance tests stay green.
1. **`max_age`'s shape.** Negative: an unknown unit, zero, a field the step doesn't read, and
   `max_age` on a task, each refused with its line. Then a well-formed one reads into seconds.
2. **The curriculum's negative test.** A step whose `max_age` fact is stale doesn't run before
   the fact is refreshed: `check_order#2` is scheduled, with its own key, and the step runs on
   the fresh value. A fresh fact refreshes nothing.
3. **A refresh that changes the condition:** the step no longer runs, and the case closes.
4. **Facts that can't be refreshed.** From a person, from the opening, from a `write` step, from
   `compute`, from a workflow step and from a plan step: each needs attention, with its line; a
   retry checks again.
5. **A refresh that refreshes nothing:** it fails, or gives `not_found`: the step needs
   attention, and nothing loops. A fact with no time stops the step. A running refresh doesn't
   undo `requires`, and two needs share one refresh.
6. **Approvals.** An approval is asked only on fresh facts. A given approval: a refresh that
   changes nothing leaves it standing and the step runs; one that changes a value it saw lapses
   it, and a new one is asked. An open approval of another step: unchanged, it stands while the
   refresh runs; changed, it is withdrawn.
7. **Sensitive facts and ages.** A stale sensitive fact needs attention and its line quotes no
   value; a refresh's sensitive input is wrapped; `view.obtained` and the approval sheet, hidden
   facts absent, `ago`'s units.
8. **On Temporal.** Times stamped from workflow time: a case left three days on the test server
   refreshes before paying; its history replays with the same decisions; a case that continues
   as new keeps its times exactly; a refusal is recorded and the case waits on; the sheet's
   query.
9. **The guide and the promises:** the guide's examples and refusal rows run as written.

### Decided while building

- **Times cross continue-as-new from slice 0, not slice 8** (slice 0). 8c's test that every
  field of the state crosses failed as soon as `obtained` existed, as it should: a field left
  out would vanish at every switch. Each time is written as a JSON integer and read back as an
  `int`, refused if it isn't whole (the converter reads numbers as decimals). Slice 8 still runs
  a real switch on Temporal.
- **A given approval that can't be spent no longer holds the case open** (slice 6): before the
  lapse, a refresh that made `pay`'s condition false left Sam's approval in `given` for ever,
  and the case never closed. Now it lapses, and the case closes with nothing paid.
- **A lapse says "when refreshed" only when it was** (slice 6): a given approval now waits while
  its refresh runs, so a person's answer can also come between (Ana sends the review back and
  approves 300). That lapses it too, and is asked again, but the line says only what changed:
  `lapsed pay.approval#1: approved_amount changed`. Before 9d nothing could come between, as a
  given approval was spent in the decision that gave it (brief, D25).
- **Three of slice 6's tests passed at once** (slice 6): asking only on fresh facts follows from
  slice 2's order, and an open approval was already withdrawn by layer 8's `follow`. Kept as
  guards; the new wording's test was seen failing on the old wording.
- **One refresh per need, remembered by fact** (slice 5): `state.refreshing` holds, for each
  fact being fetched again, the run fetching it. If that run has landed and the fact still
  isn't its, it gave nothing fresh: the step needs attention, saying what the run gave. The
  first test hung for ever, the loop this prevents. A retry of the step that needed the fact
  clears what has landed, so a person's retry may fetch it again; a refresh still on its way is
  kept, and shared.
- **A failed refresh is a failed run** (slice 5): it needs attention itself, and a step requiring
  the refreshed step waits on it (its latest run failed), so one operator retry of the refresh
  is all it takes. Only a step that reads the fact without requiring its step fails too.
- **A refresh is marked on its run** (slice 5): `refresh` on the step run, so `requires` looks
  past it while it runs, and both it and `state.refreshing` cross continue-as-new.
- **Each source says why it can't be fetched again** (slice 4): the opening and a person ("it came
  from…, so it can't be fetched again"), a `write` or `notify` step ("has side effects"), a
  `compute` step ("running it again gives nothing new"), a workflow or a plan step ("isn't run
  again unasked"). A fact the case's opener gave counts as a person's. The plan case's test
  answers the plan's own approval, or its step would still be running when the fact is read.
- **Slice 3's test passed at once** (slice 3): slice 2's code already checks the condition again,
  since admission runs again after the refresh lands. So it was seen failing on a deliberate
  break instead: with the step not waiting for its refresh, `pay` is scheduled on the stale value
  and the test fails. Code restored, test kept as the guide's example run as written.
- **Fail closed before it is refined** (slice 2): a stale fact that can't be fetched again
  already stops its step, with one line for every source; slice 4 tests each source and gives
  each its own reason. Never a slice where a stale fact is trusted.
- **A step waits while its refresh runs** (slice 2), without scheduling another: a step that
  reads a fact without requiring the step that gave it would otherwise be admitted again in the
  same decision and refresh it again. Slice 5 tests two steps sharing one refresh.
- **An age is kept as written** (slice 1): `"1d"` stays a text in the definition, checked when it
  is read, and turned into seconds where it is used, so a definition reads back as it was
  stored. The runtime reads it again with the same function, on nothing parsing did.
- **The guide's refusal row named the wrong field** (slice 1): `pay` reads `order_id` (an
  input), so the example of a field it doesn't read is `amount`. The test caught it.
- **The in-memory driver's `Finish` carries its time** (slice 0), and the script's `finish(entry)`
  is a script item like `later`: the driver makes the event at the script's time.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
Drafted before building, with the tests named in advance; checked against the real tests before
the pull request is opened. `FF` is `tests/test_fresh_facts.py` (new), `TFF`
`tests/test_temporal_fresh_facts.py` (new), `Q` `tests/test_quickstart.py`.

| Promise | Test |
|---|---|
| Time reaches `decide` only on events; an event whose time isn't a whole number of seconds is refused and changes nothing | FF `test_an_event_says_when_it_happened` |
| Every value written records when it was obtained and which run obtained it: opening, form, outcome, output | FF `test_every_fact_knows_when_it_was_obtained` |
| `max_age` takes `m`, `h` or `d`, a whole positive number, only on activity, workflow and plan steps, only for fields the step reads; anything else is refused when the definition is read | FF `test_max_age_is_checked_when_the_definition_is_read` |
| A step whose `max_age` fact is stale doesn't run before the fact is refreshed (the curriculum's negative test); the refresh is a new run with its own entry and key, and its output replaces the old with fresh sources and time; a fresh fact refreshes nothing | FF `test_a_stale_fact_is_refreshed_before_the_step_runs` |
| After a refresh the step's condition is checked again: a changed value stops the step | FF `test_a_refresh_that_changes_the_condition_stops_the_step` |
| The age is checked before the condition, the approval's condition, asking for the approval and starting | FF `test_freshness_is_checked_before_anything_else` |
| A stale fact from a person, the opening, a `write`, `notify` or `compute` step, a workflow step or a plan step makes the step need attention, with where it came from; a retry checks again | FF `test_a_fact_that_cant_be_fetched_again_needs_attention` |
| A refresh that gives no fresh value makes the step need attention; one that fails needs attention itself, a step requiring it waits and runs once it is retried, and a step only reading its fact needs attention: never a second refresh for the same need | FF `test_a_refresh_without_a_fresh_value_needs_attention`, `test_a_failed_refresh_needs_attention_and_is_retried`, `test_a_failed_refresh_is_never_made_again_for_the_same_need` |
| A fact needed fresh with no time obtained stops the step (fail closed) | FF `test_a_fact_with_no_time_stops_the_step` |
| A running refresh doesn't undo its step for `requires`; two steps needing the same fact share one refresh | FF `test_a_running_refresh_undoes_nothing_it_doesnt_change` |
| A refresh that changes nothing leaves an open or a given approval standing; an approval is asked only on fresh facts | FF `test_an_unchanged_refresh_leaves_approvals_standing`, `test_a_running_refresh_undoes_nothing_it_doesnt_change`, `test_an_approval_is_asked_only_on_fresh_facts` |
| A refresh that changes a value an open approval read withdraws it; one that changes a value a given approval saw lapses it, and the step is checked again, a new approval asked if still needed, or none if the step no longer runs, and the case closes | FF `test_a_changed_refresh_withdraws_another_steps_open_approval`, `test_a_changed_refresh_lapses_a_given_approval`, `test_a_changed_refresh_that_stops_the_step_lapses_its_approval` |
| A lapse says it came from a refresh only when every changed value did | FF `test_a_lapse_says_when_refreshed_only_when_it_was` |
| A stale sensitive fact needs attention, and no line quotes it; a refresh's sensitive input stays wrapped; a time obtained isn't sensitive | FF `test_sensitive_facts_and_their_times` |
| The view gives each visible value's time, a hidden field's not; the approval sheet gives each fact's age, read at the time the caller gives | FF `test_people_see_when_each_fact_was_obtained` |
| No message quotes a value: refresh, staleness and lapse lines name fields and ages | FF `test_freshness_lines_quote_no_value` |
| On Temporal time comes from workflow time: a case left three days refreshes before the step runs | TFF `test_a_case_left_waiting_refreshes_before_paying` |
| A case's history replays to the same decisions, refreshes included | TFF `test_a_case_with_a_refresh_replays` |
| Times cross continue-as-new exactly, as whole numbers | TFF `test_times_cross_continue_as_new_exactly` |
| On Temporal a stale fact that can't be fetched again is recorded, and the case waits for a person (needs attention); a sheet for an approval that isn't open is refused | TFF `test_a_stale_answer_on_temporal_needs_attention` |
| The quickstart's acceptance tests stay green | Q (all) |
| The guide's examples run as written, and its refusal rows are what the engine says | FF `test_the_guides_fresh_facts_examples_run_as_written`, `test_the_guides_freshness_refusals_are_what_the_engine_says` |
