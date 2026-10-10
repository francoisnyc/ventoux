# Layer 9: case data

Status: split into four parts and the eighteen choices agreed in the session, 2026-10-10 (all as
proposed); 9a's design note drafted, waiting for agreement.

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

### Decided while drafting, for you to confirm

Each is a choice the agreed design left open, written as the rule I propose.

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
   named by a case, so an operator sees the report (which holds no values), not the case file.
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

### Promises

Each claim this section makes about behaviour, and the test that will fail if it isn't true.
Drafted before building, with the tests named in advance; checked against the real tests before
the pull request is opened. `K` is `tests/test_catalog.py`, `I` `tests/test_interpreter.py`, `D`
`tests/test_case_data.py` (new), `TD` `tests/test_temporal_case_data.py` (new).

| Promise | Test |
|---|---|
| A system is registered with a lowercase name; a contract's reference names a registered system, on a `str` field, also on a copy at registration | K `test_a_system_is_registered_by_name`, `test_a_reference_input_names_a_registered_system` |
| Declaring a reference changes a contract's hash; contracts without one hash as before | K `test_every_development_contract_matches_its_recorded_hash`, `test_declaring_a_reference_changes_the_hash` |
| A case, or a plan run, whose reference names an unregistered system is refused | D `test_a_reference_to_an_unregistered_system_is_refused`; I `test_a_plan_reference_to_an_unregistered_system_is_refused` |
| A reference input takes only a reference field of its system, read as it is: another system's reference, a text field or a computed value fails the step, in a case and in a plan | D `test_a_reference_goes_only_where_its_system_is_expected`; I `test_a_plan_gives_a_reference_input_only_its_system` |
| The guide's `deny` step gives the customer's reference to `letters.draft@3` | D `test_the_guides_examples_run_as_written` |
| A field hidden from a role is absent from that role's view, and said hidden with the roles that would see it | D `test_a_hidden_field_is_absent_from_the_view` |
| Fields, outcomes and outputs are visible to anyone with a role the case names; a viewer with none sees every field hidden | D `test_what_a_role_on_the_case_sees` |
| The view's lines are the guide's | D `test_the_guides_examples_run_as_written` |
| An approval or a rejection by someone who can't see a value the step reads is refused, naming it; someone who sees it approves, and the step runs once | D `test_an_approver_must_see_what_they_approve` |
| `shown` records a line with the system and reference, never the record; it is refused for a hidden field, a field that isn't a reference, and a closed case | D `test_showing_a_record_is_recorded_without_its_content`, `test_shown_is_refused_when_it_cannot_be_true` |
| A resolver is called with the viewer, and only for a reference their view shows; a system with no resolver, or an unregistered one, is refused | D `test_a_resolver_is_asked_on_behalf_of_the_viewer`, `test_a_resolver_shows_only_what_the_view_shows` |
| On Temporal the view is the same as in memory, filtered in the worker; a refused `shown` or approval is recorded and the case waits on; a history with `shown` replays | TD `test_the_view_on_temporal_is_the_view_in_memory`, `test_refusals_are_recorded_and_the_case_waits`, `test_a_case_history_with_shown_replays` |
| The guides' refusal rows are what the engine says | K `test_the_guides_refusals_are_what_the_catalog_says` (its new rows); D `test_the_guides_refusals_are_what_the_engine_says` |
