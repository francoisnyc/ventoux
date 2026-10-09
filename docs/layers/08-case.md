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
| **8b** | closing overrides and closing by a person; failed steps needing attention, and operator actions; activity outcomes; `plan` steps, in memory |
| **8c** | cases on Temporal: the case workflow, signals, `plan` steps as child workflows, keys across runs, continue-as-new (design question 18) |
| **8d** | `workflow` steps: workflow contracts, bindings, output provenance, a contract test |

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
