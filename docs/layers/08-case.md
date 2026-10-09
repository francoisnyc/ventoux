# Layer 8: the case layer

Status: split and 8a's seven choices agreed in the session, 2026-10-09; the eleven points
decided while drafting confirmed the same day; 8a built, slices 0–6; Promises checked against the
tests, 2026-10-09.

## What this layer is for

Until now a case is the tracer's crude walk: `sequence` read in order, one answer looked up per
step, a key that names no run. Layer 8 makes the case real: a **case file**, **milestones** and
**steps**, with no position (brief, idea 4). After every event the engine works out which steps
may start (**admission**), and a case closes when nothing is left to do (brief, D10). Every
`# TRACER:` line ends here, and the quickstart's acceptance tests stay green throughout.

It is the largest layer, so it lands as four pull requests, each with its section in this note,
its own Promises table and its own tutor review:

| PR | Builds |
|---|---|
| **8a** | the case definition; the runtime, in memory; admission, proposals, parallel steps; the case file and forms; approvals in a case; what a waiting case reports; closing when nothing is pending |
| **8b** | closing overrides and closing by a person; failed steps needing attention, and operator actions; activity outcomes |
| **8c** | cases on Temporal: the case workflow, signals, `plan` steps (in memory and as child workflows), keys across runs, continue-as-new (design question 18) |
| **8d** | `workflow` steps: workflow contracts, bindings; output provenance on activity and workflow contracts, and outputs into the case file; a contract test |

`plan` steps moved from 8b to 8c, and outputs into the case file from 8b to 8d, when 8b was agreed
(see 8b, choices 1 and 2).

The `chartering` prototype is not checked out in this session; no file of it is drawn on in 8a.

---

## 8a. The case definition and the runtime, in memory

User-facing description, written first: `docs/guides/cases.md` (new); `docs/QUICKSTART.md`,
"Test it" (a case waiting for its review) and "Change it" (`requires=[review]`). Decisions:
brief D24 (design question 14) and D25.

### Decided in the session

1. **The runtime is a decision function, with drivers around it.** `decide(definition, state,
   event)` returns the new state and the commands to carry out (schedule this activity). It reads
   no clock, no randomness and no I/O, so it runs the same in memory and, in 8c, inside a
   Temporal workflow. The in-memory driver carries out each command at once with the fakes and
   feeds back the result as an event.
2. **Milestones before rules.** A step declares `reaches`: on the step, reached when it completes;
   on a task's outcome, reached when it is answered with it. Never undone. Rules (layer 11) will
   reach milestones too.
3. **`requires` and `sequence`.** `requires` names milestones, or steps whose latest run is done,
   in one namespace (a milestone named like a step is refused). `sequence` expands to `requires`
   on each step after the first. A person may propose a step; admission accepts it or refuses it.
4. **What a waiting case reports** (brief, D24): `waiting_for` lists open tasks and approvals in
   the order they opened, `review by support`, `approval of pay by support-lead`.
5. **The opener** (brief, D11, D25): `run_case(..., opened_by="ana")`, stated by the trusted
   caller and written as an identifier. The opening values are tagged `person:ana`, and Ana
   approves no step of that case. Without it, a system opened the case: `system:opener`.
6. **Forms land in the case file:** an outcome's `sets` names case-file fields; values are read by
   the field's declared type; the latest answer wins; a field a task sets is never given at the
   opening; the field's declared mark stays.
7. **An open approval follows the case file** (brief, D25). It is asked when the step is about to
   start; it is withdrawn when the step stops being admitted or a value the step reads changes, and
   asked again with a new entry; an answer to the withdrawn entry is refused.

### Decided while drafting, confirmed in the session

Each is a choice the agreed design left open, written as the rule we confirmed.

1. **Titles live in `display` blocks** (brief, D5), as in plans: `"display": {"title": ...}` on the
   case, each field, step and outcome; an approval's reason is `"display": {"reason": ...}`.
   `examples/refund/refund.json` moves its `title`s there; nothing else in it changes.
2. **A step starts by itself, unless `"automatic": false`.** The quickstart's section 7 step has no
   sequence and must still start when the review is rejected, so starting by itself is the
   default, as D2's structured workflows want. A step that doesn't start by itself names
   `proposed_by` (who may propose it), or it could never run: refused when read.
3. **`when` is read only once `requires` are met, and a missing field there stops the case.**
   Reading `review.outcome` before the review is done is a missing field: an error, never
   "false" (fail closed). So the quickstart's section 7 step gains `requires=[review]` (done in
   the docs). Treating "not set yet" as "not yet" would be the permissive default the
   non-negotiables forbid.
4. **A step starts by itself at most once.** A `repeatable` step runs again only when proposed
   (it names `proposed_by`); starting itself again would loop forever.
5. **A step requirement is met while the step's latest run is done.** Proposing `review` again
   makes `pay` unadmitted until `review#2` is answered, which is what withdraws its open approval.
   A milestone, once reached, stays met.
6. **Entries.** A step run is `review#1`, `pay#1`; an approval is `pay.approval#1`, counted per
   step over the case. A script answers `"pay"` (its open approval) or names an entry.
7. **In 8a, anything that stops a step raises from `run_case`,** as the tracer does: `InputRefused`
   (an input check), `StepStopped` (a condition that can't be read). 8b turns these into "needs
   attention", with operator actions (brief, D17).
8. **The definition and the opening are checked before anything runs.** Two regression tests from
   earlier reviews keep their promise and are refused earlier: the approval reading `{"now": []}`
   is refused when the definition is read (`CaseInvalid`, naming `now`), no longer when the
   expression is first evaluated; and an `order_id` given as a number is refused at the opening
   (`order_id is a reference, and the opening gives 1001`), before any input check. Both tests
   change only the exception they expect, said in their commit.
9. **In memory, a case's key is `memory/pay#1`:** the case and the step run, as a plan's in
   memory. On Temporal (8c) the case is its workflow ID, which survives continue-as-new.
10. **An activity's output is recorded in the history, not written to the case file.** Writing
    outputs to fields, with the contract's output provenance, comes with activity outcomes (8b)
    and `workflow` steps (8d).
11. **The lapse of a given approval has no case test in 8a.** Its approval is spent in the same
    decision that schedules its step, so nothing in 8a can change the case file in between; the
    test driver would need an edit event of its own, built ahead of change requests. The runtime
    calls `core`'s check anyway, which layer 7 tests; the case test comes with change requests
    (layer 12). This revises what I said in the session ("a test-only edit event").

### How it works

**State.** A case's state is its case file (each field's value and sources), the milestones
reached, its step runs (each `open`, `running` or `done`, with the task's outcome), its open
approvals (the entry, the step, and the digest of what the step reads when asked), who opened
it, and its history lines. Nothing in it says where the case is.

**Events and commands.** Events: `Opened`, `Answered` (an entry, an outcome, who, their roles, a
form), `Proposed` (a step, who, their roles) and `Completed` (a step run, its output). Commands:
`Schedule` (a step run, its contract, its checked inputs, its key). `decide` handles one event,
then admits steps until nothing more starts, and returns.

**Admission, after every event,** for each step in the definition's order:
- skip it if it is running, or if it ran and doesn't start by itself again;
- skip it if its `requires` aren't met;
- read its `when` (a missing field stops the case);
- a task opens its entry; an activity with an approval whose `when` holds asks for it (unless an
  open one still holds); otherwise the activity's inputs are checked (layer 5's check before an
  activity) and it is scheduled.

Then every open approval is checked: its step still admitted, and the digest of what it reads
unchanged; if not, it is withdrawn with the reason, and admission asks again.

**Answers** are judged in D23's order, with `core`'s checks: written as an identifier; the entry
is open; the outcome is offered; the person has a role the step or approval names; the form fits.
For an approval: the role may approve the activity's risk; the person is someone else (their
answer doesn't flow into the step's inputs or `when`); and the person didn't open the case. An
accepted *approve* is spent at once: the activity is scheduled with the inputs it saw. A
*reject* closes the entry, and the step doesn't run.

**Closing.** After `decide`, a case with no open task, no open approval and no running step is
closed (brief, D10).

### Where the code goes

- `case/definition.py`: the case definition's shape, `parse_case`, `CaseInvalid`.
- `case/sequence.py`: the `sequence` shorthand, expanded.
- `case/state.py`: a case's state, its events and commands.
- `case/admission.py`: may this step start now; a proposal's refusal.
- `case/answers.py`: judging an answer to a task or an approval, with `core`'s checks.
- `case/approvals.py`: asking for an approval, following the case file, the lapse check.
- `case/runtime.py`: `decide`.
- `case/memory.py`: the in-memory driver; replaces `case/runner.py`, which is removed.
- `core/approval.py`: the digest takes a step's inputs, not only a plan's activity state.
- `testing.py`: `run_case(..., opened_by=None)`, `propose`, reading a script's numbers as the
  API does (a whole number exactly, a float refused).
- `examples/refund/refund.json`: titles into `display` blocks.

### Not in 8a

- Closing overrides (`closes_when`, `stays_open`), closing by a person, the *closing* state (8b).
- Failed steps, needs attention, operator actions; activity outcomes; outputs into the case file;
  `plan` steps (8b).
- Cases on Temporal, keys across runs, continue-as-new (8c); `workflow` steps (8d).
- Change requests and their lapse test (layer 12); rules and timers (layer 11); case validation,
  provenance through the case file and deadlocks (layer 10); hidden and sensitive fields (layer 9).

### Seams the tests use

- `parse_case(data)` and `CaseInvalid`.
- `run_case(definition, file, answers, people, opened_by=None)`, its script items (answer tuples,
  `propose(step, who)`), and what it reports: `CaseRun.closed`, `.reached(step)`, `.waiting_for`,
  `.history`; the refusals it raises: `AnswerRefused`, `ProposalRefused`, `CaseRefused` (the
  opening), `InputRefused`, `StepStopped`.
- The guide's examples, run as written, and each row of its refusal table.

`decide` is the seam 8c's workflow uses; 8a's tests reach it only through `run_case`.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The case definition.** Negative: a step without a title; a kind that isn't one; `sequence`
   or `requires` naming nothing; a milestone named like a step; a step that doesn't start by
   itself with nobody to propose it; `{"now": []}`. Then `refund.json` (titles in `display`)
   is read. Removes `testing.py`'s TRACER.
1. **The runtime replaces the tracer's walk.** Negative: a refund nobody has answered waits for
   `review by support` and stays open (the tracer crashes). Then every quickstart test passes on
   `decide` and the driver, approvals included with layer 7's checks; `case/runner.py` and its
   TRACERs go.
2. **The case file.** Negative: the opening gives a field a person sets, a field the case doesn't
   declare, a number for a reference, a float; a form's float. Then opening values are tagged
   `system:opener`, a form's `person:ana`, a declared mark is kept, and the latest answer wins.
   Removes the `case_value` TRACER.
3. **Requires, proposals, milestones.** Negative: a proposal whose requirements aren't met; by
   someone without `proposed_by`'s role; of a step that starts by itself; of a step already
   running; a step that started by itself doesn't start again; a `when` reading an unset field
   stops the case. Then a proposed step runs, a milestone is reached and admits what requires it.
4. **Parallel steps.** Negative: none of its own (the guards are slice 3's). Two steps with
   nothing required open together, `waiting_for` lists both, and the case closes after both.
5. **Approvals in a case.** Negative: the opener approving is refused; an answer to a withdrawn
   approval is refused; a rework that lowers the amount to 50 needs no approval. Then the
   rework's new entry is approved and pays 900, once.
6. **The guide and the promises.** The guide's examples run as written; each refusal row has a
   test; this table is checked against the tests.

### Decided while building

- **Fields need not all be given at the opening.** A plan's run must be given every field; a case
  may be filled later (activity outputs, from 8b). Reading a field nobody has given stops the
  case, as any missing value does.
- **A rejected approval records the step's run as not run:** `pay#1 won't run: sam rejected
  pay.approval#1`. The step has had its once, so it doesn't start by itself again; a repeatable
  step can be proposed again.
- **An open approval keeps the values its step reads, not a digest of them,** so a withdrawal
  names what changed: `withdrew pay.approval#1: approved_amount changed`.
- **The opener is checked before "someone else".** Lee opened the case, so Lee's values feed
  `pay` too; the refusal says the broader reason: `lee opened the case, so cannot approve its
  steps`.
- **A high-risk step with no `approval` stops at runtime:** `payments.refund@2 is high risk, and
  pay has no approval`. A runtime check that depends on nothing case validation (layer 10) will
  do, as a plan's does (learning question 34). A step whose approval's `when` is false runs
  without one: the definition says when approval is needed.
- **A proposal is refused when its condition can't be read,** when the case is closed, when its
  person isn't written as an identifier, or when it names no step. Fail closed: nothing starts.
- **The scheduled line names the idempotency key:** `…, key memory/pay#1`; an activity's output
  is recorded by its fields' names (`pay#1 done, giving refund_id`), not their values.
- **Answers and approvals move to their own files** (`case/answers.py`, `case/approvals.py`),
  once slice 5 made the runtime long.

### From the tutor review

- **The person who proposed a step could approve it.** Sam, a team lead, proposed a goodwill
  refund (high risk, approved by `support-lead`) and approved it himself. A proposal decides that
  the step runs, so its proposer is excluded like anyone whose answer decides it (brief, D11),
  and the curriculum asks for "approvals by someone other than the proposer". Now the case keeps
  who proposed each step's coming run, until it runs or is rejected, and their approval is
  refused: `sam proposed goodwill, so cannot approve it`. Added to D25, which this PR introduces.
  In memory the refusal raises from `run_case`, as every refusal does in 8a; on Temporal (8c) a
  refused answer is recorded and the case waits on.
- **Carried to 8b:** a case whose steps all need proposing closes the moment it opens (nothing is
  pending, brief D10), so every proposal is then refused; `stays_open` is the answer, and the
  guide will warn about it. And a declined refund surfaces as a bare `Outcome` from `run_case`:
  activity outcomes and "needs attention" are 8b's.
- **Carried to 8b, from the walk-through:** `decide`'s docstring promises that a refused event
  "changes nothing", and it deep-copies the state so that a refusal or a stop part-way through
  leaves the caller's state as it was. No test checks it: every 8a test goes through `run_case`,
  which stops at the first refusal. 8b gives it a test (a state, an event `decide` refuses or
  stops on after changing its copy, and the state passed in unchanged), or the promise leaves
  the docstring. It matters most in 8c, where a refused answer is recorded and the case runs on.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`C` is `tests/test_case.py`, `Q` `tests/test_quickstart.py`. Every negative test was seen failing
before its code, except these, which passed when written because earlier code already did it,
and were then seen failing with that code removed: a step starting by itself once and an unset
condition stopping the case (slice 1's admission), steps admitted together (slice 1), the closed
case, a misspelled proposer and a proposal's unreadable condition (written in slice 6, after the
code). The guide's refusal rows passed when written.

| Promise | Test |
|---|---|
| The quickstart's refund, with its titles in `display` blocks, is read | C `test_the_quickstarts_refund_is_read` |
| A case, field, step, outcome or approval without a title is refused when read; a title is never empty | C `test_everything_people_read_has_a_title`, `test_a_title_is_never_empty` |
| An unknown kind, a `sequence` or `requires` naming nothing, a milestone named like a step, an undeclared milestone or field are refused | C `test_a_definition_that_names_nothing_is_refused` |
| A step that doesn't start by itself, or is repeatable, names who may propose it | C `test_a_step_nobody_can_start_is_refused` |
| An expression the engine doesn't know is refused when the definition is read | C `test_an_expression_the_engine_does_not_know_is_refused_when_read`; Q `test_an_approval_the_engine_cannot_evaluate_stops_the_case` |
| A case waiting for a task reports it in `waiting_for` and stays open (brief, D24) | C `test_a_case_waiting_for_its_review_says_so` |
| A case with an open approval doesn't close | Q `test_large_refund_waits_for_a_team_lead` |
| A case closes when nothing is left to do, and then takes no more answers | Q `test_small_refund_needs_no_team_lead`, `test_rejected_review_closes_without_paying`, `test_a_rejected_approval_closes_the_case_without_paying`; C `test_a_closed_case_takes_no_more_answers` |
| The opening gives only declared fields, of their types, and never one a person sets | C `test_the_opening_gives_the_declared_fields_of_their_types`; Q `test_an_input_that_does_not_fit_is_refused_before_the_refund` |
| Opening values come from `system:opener`, or the person who opened the case, written one way | C `test_opening_values_say_who_gave_them` |
| A float is refused, in the opening and in a form | C `test_a_float_is_refused_never_guessed` |
| A form's value keeps a declared mark, and the input check sees it | C `test_a_forms_values_land_in_the_case_file` |
| The latest answer is the one read | C `test_a_rework_below_the_threshold_needs_no_approval` |
| A proposal is refused if its step is unknown, starts by itself, is running, ran and isn't repeatable, its role is missing, its requirements aren't met, or its condition is false or can't be read; its person is written one way | C `test_a_proposal_is_checked_against_admission`, `test_a_proposal_whose_condition_is_false_is_refused`, `test_a_proposal_whose_condition_cannot_be_read_is_refused`, `test_a_proposal_names_its_person_one_way` |
| A proposed step runs | C `test_a_proposed_step_runs`, `test_the_guides_proposed_step_runs` |
| A step starts by itself at most once | C `test_a_step_starts_by_itself_once` |
| A `when` reading a field nobody has set stops the case, never reads as false | C `test_a_condition_on_an_unset_field_stops_the_case` |
| A milestone is reached by a task's outcome or a step's completion, and admits what requires it | C `test_a_milestone_admits_what_requires_it` |
| Steps admitted together open together; the case waits for all of them | C `test_steps_admitted_together_run_together` |
| The person who opened the case cannot approve its steps | C `test_the_opener_cannot_approve` |
| The person who proposed a step's run cannot approve it; the case waits, and someone else's approval runs it once (tutor review) | C `test_the_person_who_proposed_a_step_cannot_approve_it` |
| An open approval is withdrawn when a step it requires starts again, or a value it reads changes; an answer to it is refused with the reason; a new entry is asked | C `test_an_open_approval_follows_the_case_file`, `test_an_open_approval_is_withdrawn_when_a_value_it_reads_changes` |
| After a withdrawal, an approval is asked again only if still needed | C `test_a_rework_below_the_threshold_needs_no_approval` |
| An approval unlocks one run, scheduled with a key naming the case and the step run | C `test_an_approval_unlocks_one_run_with_its_own_key` |
| A high-risk step with no approval stops before it is scheduled | C `test_a_high_risk_step_with_no_approval_stops` |
| Every check from layers 5 and 7 still holds in a case: roles, outcomes, forms, someone else, input policies, spellings | Q (the file's other tests) |
| The guide's refund is the quickstart's; its examples, histories and refusals are what the engine says | C `test_the_guides_refund_is_the_quickstarts`, `test_the_guides_examples_run_as_written`, `test_the_guides_histories_are_what_the_engine_records`, `test_the_guides_refusals_are_what_the_engine_says`, `test_every_refusal_in_the_guide_is_tested` |

Not promised in 8a, and why: the lapse of a given approval (no case test until change requests,
layer 12; see point 11 above).

---

## 8b. Closing, failures and activity outcomes, in memory

Status: design agreed in the session, 2026-10-09 (all ten choices as proposed); built, slices
0–7; Promises checked against the tests, 2026-10-09.

User-facing description, written first: `docs/guides/cases.md`, "When a system says no", "When
something breaks", "Closing a case", and the testing section. Decision: brief D26.

### What this part is for

8a's runtime knows only the happy path, and anything else raises out of `run_case`. 8b gives a
case the three other ways it goes: a system says no (a declared outcome, brief D17), something
breaks (a failed step that needs attention, D17), and someone decides it's over (closing, D10).
Each becomes state the case reports and waits on, as 8c needs: on Temporal a case with a problem
must sit there for a person, not crash.

### Decided in the session

1. **`plan` steps move to 8c.** A plan waiting on people suspends mid-run; the interpreter is
   `async`, and `case` may not import `asyncio` (layer 6's boundary test), so neither `decide` nor
   the in-memory driver can host one. On Temporal a plan step is a child workflow, which suspends
   by nature (8c); in memory, `testing.py` hosts it with `asyncio.run`, as `run_plan` does.
2. **Outputs into the case file move to 8d.** Their provenance is declared per output field by a
   contract (brief, D12), which contracts don't do yet; adding it changes every contract's hash
   (brief, D5), and 8d needs the same for workflow contracts. One decision, made once.
3. **An activity's outcome is a case-file value:** `pay.outcome` is `done` or a declared outcome,
   tagged `system:<the contract's reference>`, trusted, since the contract owns the list. An
   outcome the contract doesn't declare fails the step (fail closed). A step's milestones are
   reached only when it is done with `done`.
4. **What fails, and what it does.** An activity's error, an undeclared outcome, an output its
   contract doesn't declare, a refused input, a condition that can't be read and a lapsed
   approval each make the step's run **failed**, with the reason. The case **needs attention**:
   `needs_attention` lists `pay#1: <reason>`, a failed run is pending work, and other steps go on.
   Refused answers, proposals, retries, closes and openings still raise: they are the caller's
   mistakes, not the case's. 8a's tests expecting `InputRefused` or `StepStopped` now assert
   `needs_attention`; their promises are unchanged.
5. **Who operates** (brief, D26): `register_role("operations", operates=True)`, in the catalog.
6. **A retry is the same step run, with the same key** (brief, D26). It checks the step again
   (requirements, condition, inputs); an approval spent on the run holds only if its inputs are
   unchanged. No skip: that is a change request (layer 12).
7. **Closing by a person** uses close reasons declared on the case with their roles;
   `close(reason, who)` in a script. An operator closes the same way, through a reason that
   lists their role.
8. **Closing, then closed.** Closing cancels open tasks, approvals and failed runs, each recorded
   with why; refuses new answers, proposals and retries; lets running activities finish. A run
   that completes while closing **flags** the case. In memory, `run_case(..., held=["pay"])` keeps
   `pay`'s runs running until the script says `finish("pay#1")`.
9. **`closes_when` and `stays_open`** (brief, D10): `closes_when` closes the case once all its
   milestones are reached; `stays_open` means only a person closes it. A case that stays open
   must declare a close reason, or nobody could ever close it.
10. **`decide` becomes a seam for tests now,** for the item carried from 8a: an event, accepted or
    refused, never changes the state passed in.

### How it works

**Events** gain `Failed` (a step run and the reason), `Retried` (a run, who, their roles) and
`CloseAsked` (a reason, who, their roles); `Completed` carries the outcome (`done` or declared).
The driver turns what an activity does into events: a return is `Completed`, `Outcome(name)` is
`Completed` with that outcome, any other exception is `Failed`. Checking the outcome against the
contract, and the output against its model, is `decide`'s, so it runs the same on Temporal.

**A step run** may now be `failed` (with its reason), `retrying` or `cancelled`. Where 8a raised
(`StepStopped`, `InputRefused`, an activity the catalog lacks, a lapse), admission records a
failed run instead, and goes on with the other steps.

**A case** is `open`, `closing` or `closed`. Admission runs only while it is open. Closing begins
when a person closes it with a reason, or when every milestone in `closes_when` is reached; it
cancels what waits, and the case is closed once nothing runs. A case that `stays_open` never
closes by itself.

### Where the code goes

- `case/definition.py`: `close_reasons`, `closes_when`, `stays_open`.
- `case/state.py`: the new events, run statuses and the case's phase.
- `case/runtime.py`: outcomes, failures, retries, closing.
- `case/closing.py`: whether a case closes, and closing it.
- `case/memory.py`: activities' outcomes and errors as events; `held` and `finish`.
- `core/catalog.py`: `register_role(..., operates=True)`, `operators`.
- `testing.py`: `retry`, `close`, `finish`, `activities=`, `held=`; `Outcome`.

### Not in 8b

- `plan` steps (8c); outputs into the case file and output provenance (8d).
- Retries with Temporal's retry policy and timeouts (8c); in memory an activity's error is a
  failure after its retries.
- Skipping a failed step, and the lapse test (change requests, layer 12).
- Rules and timers, and what they keep open (layer 11).

### Seams the tests use

- `run_case(..., activities=, held=)`, script items `retry`, `close`, `finish`; `CaseRun.status`,
  `.closed`, `.needs_attention`, `.flags`, `.waiting_for`, `.history`; the refusals `RetryRefused`
  and `CloseRefused`.
- `parse_case` for the new keys.
- `decide(case, catalog, state, event)`, for the one test that a state passed in never changes.
- The guide's examples, run as written, and each new row of its refusal table.

### Slices, in order

0. **`decide` never changes the state passed in** (carried from 8a). Negative: an accepted answer
   changes the caller's state if `decide` works on it in place (seen by removing the copy).
1. **Activity outcomes.** Negative: an outcome the contract doesn't declare fails the step. Then a
   declined refund is done with `declined`, a step reacts, and `paid` isn't reached.
2. **Needs attention.** Negative: an activity's error, a refused input and an unreadable
   condition no longer raise; the case reports them and stays open; nothing is skipped. Then
   another step goes on.
3. **Retry.** Negative: a retry by a role that doesn't operate, of a run that hasn't failed, are
   refused. Then the retry runs with the same key, and the case closes.
4. **Close by reason.** Negative: an undeclared reason, a person without the reason's role.
   Then open tasks and approvals are cancelled, saying why, and the case closes.
5. **Closing.** Negative: an answer or a proposal while closing is refused. Then a held activity
   finishes, the case closes after it and is flagged.
6. **`closes_when` and `stays_open`.** Negative: a case that stays open with no close reason is
   refused when read; `closes_when` naming no milestone is refused. Then a proposed-steps case
   stays open, and `closes_when` closes when its milestone is reached.
7. **The guide and the promises.**

### Decided while building

- **Slices 1 and 2 swapped:** an undeclared outcome "fails the step", so failing came first.
- **An activity that fails while the case is closing is cancelled, and flags the case,** rather
  than needing attention: nobody retries a step in a case that is closing. A declared outcome
  that arrives while closing flags it too, like a completion.
- **A retry or a close is refused unless the case is open:** `the case is closing: nothing
  starts`, `the case is closing: it can't be closed again`.
- **`closes_when` is checked before admission,** so nothing starts only to be cancelled.
- **The in-memory driver became a small class,** holding the runs that `held` keeps running.
- **Tests outside the case suite followed:** the catalog's test for an activity it lacks reports
  needs attention (missed in slice 1, when only the case tests were run, and fixed after slice
  3); `UNKNOWN_ROLE`'s list of roles includes `operations`, in a plans test and the plans guide.
- **8a's promises that a condition on an unset field "stops the case", and that a high-risk step
  with no approval "stops", still hold:** the step stops, now as a failed run the case reports.

### From the tutor review

- **`closes_when` silently cancelled a failed step.** A parallel letter failed, then `paid` was
  reached: the failed run was cancelled and the case closed, with no flag and nothing needing
  attention. Had the failure come a moment after `paid`, the case would have been flagged: the
  order of events decided whether anyone heard of it. A failed run is the one kind of pending
  work that must wait for a person (brief, D17). Now `closes_when` doesn't close the case while a
  run needs attention; it closes once the run is retried to completion, or a person closes it
  with a reason. Added to D26, which this PR introduces.
- **Carried to layer 10 (optional):** a declared outcome no step reacts to ends quietly (a
  declined refund closes as `closed: nothing left to do`). Right for a case, but D9's planned
  warning about "outcomes no rule reads" should cover activity outcomes too.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`C` is `tests/test_case.py`, `K` `tests/test_catalog.py`. Every negative test was seen failing
before its code, except: slice 0's, seen failing with `decide`'s copy removed; and two written
after their code, in slice 7, seen failing with their check removed (a closing case closed or
retried again, a declared outcome while closing).

| Promise | Test |
|---|---|
| `decide` never changes the state passed in, for an accepted or a refused event (carried from 8a) | C `test_decide_never_changes_the_state_passed_in` |
| An activity's error fails its step: the case needs attention, stays open, and nothing is skipped | C `test_a_failed_step_needs_attention_and_keeps_the_case_open` |
| Other steps go on while one needs attention | C `test_other_steps_go_on_while_one_needs_attention` |
| A refused input, an unreadable condition, an activity the catalog lacks and a high-risk step with no approval fail the step, never raise | C `test_a_forms_values_land_in_the_case_file`, `test_a_condition_on_an_unset_field_stops_the_case`, `test_a_high_risk_step_with_no_approval_stops`; K `test_a_definition_naming_an_activity_not_in_the_catalog_stops_the_case` |
| An outcome the contract doesn't declare, or an output it doesn't describe, fails the step | C `test_an_outcome_the_contract_does_not_declare_fails_the_step`, `test_an_output_the_contract_does_not_declare_fails_the_step` |
| A declared outcome is a case-file value a step reacts to; milestones are reached only on `done` | C `test_a_declined_refund_is_an_outcome_a_step_reacts_to` |
| An outcome is tagged with the contract that declares it | C `test_an_outcome_is_tagged_with_the_contract_that_declares_it` |
| Only an operating role retries, and only a failed run | C `test_only_an_operating_role_retries`, `test_only_a_failed_run_is_retried` |
| A retry is the same run, with the same key, and the case can then close | C `test_a_retry_is_the_same_run_with_the_same_key` |
| An approval spent on a run holds for its retry | C `test_an_approval_spent_on_the_run_holds_for_its_retry` |
| A retry checks the step again: its condition is read again, and refused if false | C `test_a_retry_checks_the_step_again` |
| An undeclared close reason, or a person without its role, is refused | C `test_an_undeclared_close_reason_is_refused`, `test_a_close_reason_names_who_may_use_it` |
| Closing cancels open tasks, approvals and failed runs, saying why; a closed case takes no answer | C `test_closing_cancels_what_waits_saying_why`, `test_an_operator_closes_a_case_that_needs_attention` |
| While closing, nothing waits and nothing starts; a closing case is not closed or retried again | C `test_while_closing_nothing_waits_and_nothing_starts`, `test_a_closing_case_is_not_closed_or_retried_again` |
| A running activity finishes; the case closes after it, flagged | C `test_a_running_activity_finishes_and_the_closed_case_is_flagged`, `test_a_declared_outcome_while_closing_flags_the_case` |
| An activity failing while closing flags the case and needs no attention | C `test_an_activity_failing_while_closing_flags_the_case` |
| A case that stays open must declare a close reason; `closes_when` names milestones | C `test_a_case_that_stays_open_names_how_to_close_it` |
| A case that stays open closes only when a person closes it (carried from the 8a review) | C `test_a_case_of_proposed_steps_stays_open_until_a_person_closes_it` |
| `closes_when` closes the case once its milestones are reached, cancelling what waits | C `test_closes_when_closes_the_case_once_its_milestones_are_reached` |
| `closes_when` never cancels a step that needs attention: the case waits, and closes once it is retried (tutor review) | C `test_closes_when_waits_while_a_step_needs_attention` |
| The guide's new examples, histories and refusal rows are what the engine says | C `test_the_guides_examples_run_as_written`, `test_the_guides_histories_are_what_the_engine_records`, `test_the_guides_refusals_are_what_the_engine_says`, `test_every_refusal_in_the_guide_is_tested` |

---

## 8c. Cases on Temporal

Status: the seven choices agreed in the session, 2026-10-09 (all as proposed); the six points
decided while drafting confirmed the same day; slices 0–4 built.

User-facing description, written first: `docs/guides/cases.md`, "Plan steps" and "Running a case
on Temporal". Decisions: brief D27 (design question 18) and D28.

### What this part is for

8a and 8b made `decide` the whole case runtime, reading no clock, randomness or I/O, and gave it a
driver that runs in memory. 8c gives it a second driver: a Temporal workflow, one per case, for as
long as the case lives. Answers, proposals, retries and closes arrive as signals; activities run
with their contracts' retry policies and timeouts; a `plan` step runs as a child workflow; and a
case that outlives one run's history continues as new, keeping its keys.

Drawn on: our own layer 6 (`temporal/workflow.py`, `client.py`, `worker.py`), not the prototype
(not checked out in this session). Checked by hand on the test server before writing this note:
`workflow.info().first_execution_run_id` is the same in three runs joined by continue-as-new, and
a handle from `start_workflow` is pinned to the first run, so signals after a switch must address
the workflow ID alone.

### Decided in the session

1. **One inbox, one event at a time.** Signal handlers and the results of activities and child
   plans only append an event to an inbox. The main loop takes the next event, calls `decide`,
   starts what it asks for, and loops. The inbox keeps arrival order, which history records, so
   "the entry open when it arrives" means: open in the state the earlier events left. The opening
   is the workflow's input (the definition as data, the first values, who opened it). A refused
   opening (`CaseRefused`, `CaseInvalid`) fails the workflow at once, as `RunRefused` does in
   layer 6; any other exception is a bug, which fails only the workflow task, retried by Temporal
   until fixed code is deployed (brief, D17).
2. **On Temporal an answer names its entry, and anything refused is recorded.** A signal answers
   `review#1` or `pay.approval#1`, never a step's name: after a rework, a late click on `review`
   would answer `review#2`, which its sender never saw (layer 6's double click). The in-memory
   script still answers by step; the rule is the signal's. A refused answer, proposal, retry or
   close becomes one history line, `refused <who>'s <what>: <reason>`, and the case waits on as
   if it hadn't come; `decide` leaves the state as it was (8b, slice 0). The runtime's refusal of
   an entry that isn't open splits in two, as layer 6's: `review#1 is closed` for an entry that
   has been open, `review#1 isn't open` for one that hasn't.
3. **Keys across runs** (brief, D27): `<workflow ID>/<first run ID>/<entry>`. The entry counts
   come from the case's step runs, which cross over, so a key never repeats. The client opens a
   case refusing a duplicate ID, and the first run ID keeps two cases apart if Temporal has
   forgotten a closed one. A reset keeps the first run ID (Temporal's documentation), so it sends
   the same keys again; not promised here, since the test server can't reset.
4. **Retry policy and timeouts from the contract,** through the same code as plans (layer 6): an
   error after the retries is `Failed` with the activity's own message, and the case needs
   attention; a declared outcome is `Completed` with it, never retried. A case making a contract
   stricter (brief, D17) is not on 8c's Build line: not in 8c.
5. **Plan steps** (brief, D28): `kind: "plan"`, a plan reference, `inputs` over the case file.
   The deployment supplies plans by reference; one it lacks fails the step. On Temporal, a child
   workflow `<case ID>/<entry>`, whose run the case names, so its keys are
   `<case key>/<entry>/<state>#<n>`; a retry starts it again under the same ID and keys. Succeeded
   is `done`; a failed final state is the outcome `failed`; stopped fails the step. The case's
   opener and the step's proposer cross into the plan as people who approve nothing in it: an
   optional `excluded` parameter on `interpret` (a small `core` change). The plan's waits are
   answered on the child; the case reports the step as running. In memory, `testing.py` runs the
   plan with `asyncio.run` (8b, choice 1), answered from `plan_answers`; a plan left waiting
   keeps the step running. No approval of a whole plan (D14) until layer 15.
6. **Continue-as-new** (brief, D27): after `events_per_run` events decided in one run (a count on
   the workflow class, lowered in tests), or when Temporal suggests it, and only at a quiet point:
   the inbox empty, nothing running, every signal handler finished. The whole `CaseState` crosses,
   with the definition; nothing crosses as a queue. The state is written to data and read back by
   `ventoux.temporal` (the exact converter refuses sets, and a `frozenset` of sources is one).
7. **Replay:** a recorded case history replays with the same code, and fails with code changed to
   ask for something else first.

### How it works

**The workflow.** `CaseWorkflow` holds the code; a deployment subclasses it to name its `catalog`
and `plans` (shown in the guide), as with `PlanWorkflow`. `drive(start)` parses the definition,
decides `Opened`, then loops: wait until the inbox has an event, decide it, carry out its commands.
A `Schedule` becomes `workflow.start_activity` with the contract's options, its result turned into
`Completed` or `Failed` and appended to the inbox when it arrives. A `StartPlan` becomes
`workflow.start_child_workflow` of the deployment's plan workflow, with a `PlanStart` naming the run
and who is excluded; its `RunReport` becomes `Completed` (`done` or `failed`) or `Failed` (stopped).
The loop ends when the case is closed, returning a `CaseReport`.

**Signals:** `answer(Sent)` (entry, outcome, by, roles, form), `propose`, `retry`, `close`, each
appending its event. A bare step name in an answer is refused by the signal, before `decide`.
**Query:** `report` gives `CaseReport`: `status`, `waiting_for`, `waiting_at` (the open entries),
`needs_attention`, `flags`, `history`.

**`case` gains** the plan step and its command: `PlanStep` in the definition, `StartPlan` (entry,
plan reference, fields with sources, run name, excluded people) from `decide`, and `Completed`
read for a plan step as `done` or `failed`. `case` still imports nothing from Temporal.

**Continue-as-new.** Before waiting on the inbox, the loop checks: count reached or Temporal
suggests it, inbox empty, nothing running, handlers finished. Then `workflow.continue_as_new` with
a `CaseStart` carrying the state as data. The new run decides nothing on starting: it reads the
state back and waits on the inbox. Temporal fails the switch if a signal arrived meanwhile, and the
old run decides it first.

### Where the code goes

- `case/definition.py`: `PlanStep` (`kind: "plan"`, `plan`, `inputs`; no `approval`).
- `case/state.py`: `StartPlan`; the command type becomes `Schedule | StartPlan`.
- `case/runtime.py`: starting a plan step; its result; `is closed` and `isn't open`.
- `case/memory.py`: carries `StartPlan` with a plan runner it is given.
- `core/interpreter.py`: `excluded`, the people who approve nothing in this run, and why.
- `testing.py`: `run_case(..., plans=, plan_answers=)`, the plan runner (`asyncio.run`); the
  development case workflow.
- `temporal/options.py`: a contract's retry policy and timeouts, for both workflows (moved from
  `workflow.py`).
- `temporal/cases.py`: `CaseWorkflow`, `CaseStart`, `CaseReport`, the signals' shapes, and the
  client (`start_case`, `answer`, `propose`, `retry`, `close`, `report`).
- `temporal/carried.py`: a case's state written to data and read back.
- `temporal/workflow.py`: `PlanStart` gains the run name and the excluded people, both optional.
- `temporal/worker.py`: `case_worker`.

### Not in 8c

- Outputs into the case file, and `workflow` steps (8d).
- A case making a contract's retry policy or timeouts stricter (brief, D17): no layer names it
  yet; to be placed with releases (layer 12).
- A plan step's waits in the case's `waiting_for` (brief, D28): needs the child to tell its
  parent.
- Approving a whole plan, "Approve this plan" (brief, D14): layer 15.
- Resets, tested: the time-skipping test server can't reset a workflow.
- No new dependency.

### Seams the tests use

- `run_case(..., plans=, plan_answers=)` and what it reports, for plan steps in memory.
- `case_worker`, `start_case`, `answer`, `propose`, `retry`, `close`, `report` and the case's
  `result()`, against Temporal's time-skipping test server; `CaseReport`'s fields.
- The plans client's `answer` and `report`, on a plan step's child.
- Temporal's `Replayer`, on a case's history.
- The guide's examples: in memory, run as written; on Temporal, the same history as in memory.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Closed or not open.** Negative: after a rework, an answer to `review#1` says
   `review#1 is closed`, and one to `review#3` says `review#3 isn't open`.
1. **Plan steps, in memory.** Negative: a plan step with an `approval`, or naming no plan, is
   refused when read; a plan the deployment lacks fails the step; a plan that stops fails the
   step; the case's opener approving inside the plan is refused. Then the guide's plan step runs,
   with keys `memory/settle#1/pay#1`, and a failed final state gives `settle.outcome == "failed"`.
2. **A case runs as a workflow.** Negative: a refused opening fails the workflow at once; a
   second case with the same ID is refused. Then the guide's refund, answered by entry, closes
   with the same history as in memory, keys apart; a waiting case reports `waiting_for` and
   `waiting_at`.
3. **Signals and refusals.** Negative: a double click, an answer before its entry opens, an
   answer naming a step, a refused proposal, retry and close: each recorded, and the case waits
   on. Then a proposal and a close by reason, accepted.
4. **Activities.** Negative: an activity failing past its contract's attempts makes the case need
   attention; a declared outcome isn't retried. Then a retried activity, and an operator's retry,
   send the same key, `refund-1/<first run ID>/pay#1`.
5. **Plan steps as child workflows.** Negative: the case's opener approving inside the child is
   refused; a stopped plan fails the step. Then the child `refund-1/settle#1` waits, is answered
   on the child, and the step is done; its keys are `refund-1/<first run ID>/settle#1/pay#1`.
6. **Continue-as-new.** Negative: an entry count never restarts: after a switch, a rework is
   `review#2` and its key is new; a state carried over keeps exact numbers and sources. Then an
   entry open before the switch is answered after it by the same name; a switch waits while an
   activity runs; the case's history reads as one, across runs.
7. **Replay.** Negative: a case's history replayed with changed code fails. Then it replays with
   the same code, a continued case's last run included.
8. **The guide and the promises.**

### Decided while building

- **Plan steps have their own test file,** `tests/test_plan_step.py` (`P` below):
  `tests/test_case.py` is past 1,300 lines.
- **A plan supplied under another reference fails the step** (slice 1, found while building the
  runner): a deployment mapping `refund-order@1` to a plan that is really `refund-order@2` would
  run something the case doesn't name. Fail closed: `refund-order@1 is supplied as
  refund-order@2: supply the plan it names`. The same check comes to Temporal in slice 5.
- **The test for exclusions inside a plan uses the proposer, not the opener.** Sam opening the
  case and approving inside the plan was already refused by layer 7's provenance check: his
  opening values feed the plan's `pay`. The proposer's values feed nothing, so only D25's rule
  stops him; that test failed for the right reason (Sam's refund paid) before `excluded` existed.
  A case of proposed steps needs `stays_open` (8a's carried catch), so the test declares it.
- **`run_plan`'s scripted wait moved to `scripted` in `testing.py`,** shared by plan runs and plan
  steps, rather than copied.
- **The case workflow and its client share one file,** `temporal/cases.py`, as the note planned;
  the activity options moved to `temporal/options.py`, and `PlanWorkflow` uses them too
  (slice 2). Until slice 5, a plan step reaching the case workflow is a bug, not a refusal: it
  fails the workflow task, which waits for the code.
- **An activity's failure reads as in memory:** `payments.refund@2 failed: <what it said>`, so
  the two drivers record the same line.
- **The client addresses a case by its ID alone** (`case_handle`), from the first call on, not
  only after a switch: `start_case` returns such a handle.
- **A request's signals share one shape,** `CaseRequest` (what, by, roles): a proposal names a
  step, a retry a run, a close a reason (slice 3). An answer keeps its own, `CaseAnswer`.
- **An answer naming a step is refused in the loop, not in the signal handler,** so its line
  lands in the history in arrival order, like every other refusal; its example names the entry
  open for that step, if any (`such as review#1`).
- **A test of a step that needs attention moves time on itself** (slice 4). Temporal's
  time-skipping server skips time only while a client waits on a workflow's result; a plan
  stops, so layer 6's test waited on it, but a case that needs attention never ends. Those tests
  call the test environment's `sleep` between reports, past the contract's backoff.
- **The outcome of a plan step is tagged with the plan:** `settle.outcome` from
  `system:refund-order@1`, as an activity's is tagged with its contract (choice 5 in drafting).

### Promises

Each claim this section makes about behaviour, and the test that will fail if it isn't true.
Drafted before building, with the tests named in advance; checked against the real tests before
the pull request is opened. `C` is `tests/test_case.py`, `P` `tests/test_plan_step.py`, `TC`
`tests/test_temporal_case.py`. Seen failing before their code: every negative test so far, except
three that passed when written, the code already there, and were seen failing with it removed: a
stopped plan failing the step (the runner's `stopped` branch), inputs keeping their sources (the
sources laundered to `system:opener`), and a plan ending done or failed (the check removed). The
plan the deployment lacks first failed on the missing `plans=` seam. On Temporal: a refused
opening was seen hanging until the test's bound with its conversion removed, and a second case
opening under the same ID with Temporal's default reuse policy. A double click, before the
refusals were recorded, left the case stuck (its workflow task failing) until the test's bound;
an early click then passed as written, on slice 0's wording and the same recording; refused
proposals, retries and closes passed as written too, and were seen stuck with only
`AnswerRefused` recorded. Slice 4's activity code came with slice 2, so its tests passed as
written; seen failing with Temporal's default retry policy in place of the contract's (the
payment retried forever, never needing attention), and with the declared-outcome branch removed
(the declined refund never completed).

| Promise | Test |
|---|---|
| An answer to an entry that has been open says it is closed; one that hasn't, that it isn't open | C `test_an_entry_is_closed_or_not_open` |
| A plan step has no approval and names a plan, or is refused when read | P `test_a_plan_step_is_read_with_its_shape_checked` |
| A plan the deployment lacks, one supplied under another reference, or a plan that stops, fails the step: the case needs attention | P `test_a_plan_the_deployment_lacks_fails_the_step`, `test_a_plan_supplied_under_another_reference_fails_the_step`, `test_a_plan_that_stops_fails_the_step` |
| A plan's fields carry the sources of what they read from the case file, and the plan's checks refuse by them | P `test_a_plan_steps_inputs_keep_their_sources` |
| A plan that succeeds makes the step done; a failed final state is the outcome `failed`; a plan waiting keeps the step running | P `test_how_a_plan_ends_is_how_its_step_ends` |
| A plan step ends done or failed, and nothing else | P `test_a_plan_ends_done_or_failed_and_nothing_else` |
| The case's opener and the step's proposer approve nothing inside a plan step | P `test_who_may_not_approve_crosses_into_the_plan`; TC `test_the_opener_cannot_approve_inside_a_child_plan` |
| A plan step's keys are the step run's, then the plan's own | P `test_a_plan_steps_keys_name_its_step_run`; TC `test_a_child_plans_keys_name_the_case` |
| A refused opening fails the case workflow at once | TC `test_a_refused_opening_fails_at_once` |
| A second case with the same ID is refused | TC `test_a_case_id_opens_one_case` |
| On Temporal a case makes the same decisions and history as in memory, its keys naming the case and its first run | TC `test_the_guides_case_gives_the_same_history_as_in_memory` |
| A waiting case reports what it waits for, and the entries open for an answer | TC `test_a_waiting_case_reports_its_open_entries` |
| An answer counts only for the entry open when it arrives: a double click and an early click are refused, recorded, and the case waits on | TC `test_a_double_click_is_refused_and_recorded`, `test_an_answer_before_its_entry_opens_is_refused` |
| An answer naming a step, not an entry, is refused and recorded | TC `test_an_answer_names_its_entry` |
| A refused proposal, retry or close is recorded, and the case waits on | TC `test_a_refused_request_is_recorded_and_the_case_waits_on` |
| An activity is retried as its contract says; past its retries, the case needs attention | TC `test_an_activity_failing_past_its_retries_needs_attention` |
| A declared outcome is never retried | TC `test_a_declared_outcome_is_never_retried` |
| A retried activity, and an operator's retry, send the same key | TC `test_every_attempt_and_a_retry_send_the_same_key` |
| A plan step runs as a child workflow named by its step run, answered on the child | TC `test_a_plan_step_runs_as_a_child_workflow` |
| A stopped child plan fails its step; a retry starts it again with the same keys | TC `test_a_stopped_child_plan_is_retried_with_the_same_keys` |
| An entry count never restarts across continue-as-new, so a key never repeats | TC `test_entry_counts_cross_continue_as_new` |
| The state carried over keeps exact numbers and every value's sources | TC `test_a_carried_state_reads_back_as_it_was` |
| An entry open before a switch is answered after it by the same name | TC `test_an_open_entry_survives_the_switch` |
| A case switches only when nothing runs | TC `test_a_switch_waits_while_an_activity_runs` |
| A case's history replays with the same code, and fails with changed code | TC `test_a_case_history_replays`, `test_a_case_history_replayed_with_changed_code_fails` |
| The guide's examples are what the engine does | C `test_the_guides_examples_run_as_written`, `test_the_guides_plan_step_runs_as_written`; TC `test_the_guides_case_gives_the_same_history_as_in_memory` |
| Not ours to test: a signal arriving while a switch is committed fails the switch, and the old run decides it first (Temporal's behaviour) | none of its own; the nearest check, an answer around a switch counted once, is `test_an_open_entry_survives_the_switch` |
