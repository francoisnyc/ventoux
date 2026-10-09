# Layer 7: people in the loop

Status: design agreed in the session, 2026-10-08 (all five choices as recommended; the history
shows only the role that counted; a field a wait sets is never given at the start); built, slices
0–8; Promises checked against the tests, 2026-10-08.

## What this layer is for

Until now `by` on an answer is only a name: anyone may answer any wait with an outcome it offers,
and an approval is any wait whose outcomes happen to be `approve` and `reject`. Layer 7 makes the
engine check **who** answers: the person has a role the wait allows; for an approval, that role
may approve the activity's risk, the person isn't excluded because their own answer feeds the
step, and the step still runs with the values the approval saw. Anything else is refused,
recorded, and the wait goes on.

User-facing description, written first: `docs/guides/plans.md`, "Approvals" and "People in the
loop"; `docs/QUICKSTART.md`, "Test it" (`people=`) and "When Ventoux says no" (Sam reviewing,
then approving). Decisions: brief D22 (design question 12) and D23 (design question 13).

No prototype file is drawn on in this layer (agreed in the session).

## Decided in the session

1. **First, the two fixes from the layer 6 review** (curriculum, layer 7 "First"). The waiting
   line names its entry: `waiting at approve_refund#1 for approve or reject, at most 48h`, so a
   refusal naming an entry (`approve_refund#1 is closed`) reads clearly beside it, even when one
   wait leads straight into another. And `test_a_run_without_its_answer_reports_waiting` also
   asserts `waiting_at == "approve_refund#1"`, the half of its promise it didn't test.
2. **Roles come with each answer** (brief, D22). The trusted caller states who answered and their
   roles (brief, D19); the engine looks nobody up, so `core` stays free of I/O and a replay
   decides as the first run did. Roles are registered in the catalog with the highest risk each
   may approve: `register_role("support")` approves nothing, `register_role("support-lead",
   approves="high")`. Every wait and approval names its roles; there is no "anyone" default.
   Tests play the API: `run_plan(..., people=...)` and `run_case(..., people=...)`; a person not
   listed has no roles. This replaces the tracer's fixed `PEOPLE`.
3. **An approval is its own state** (brief, D23):
   `{"approval": {"of": "pay", "roles": ["support-lead"], "timeout": "48h"}, "on": {...}}`. Its
   outcomes are `approve` and `reject`, never written. `of` names the activity state it guards,
   and `approve` must lead there. `APPROVAL_REQUIRED` and `APPROVAL_REUSED` count only approval
   states.
4. **A plain wait may offer an outcome named `approve`;** it approves nothing. `APPROVAL_OUTCOMES`
   is retired: a high-risk activity behind such a wait is still refused by `APPROVAL_REQUIRED`.
5. **A lapsed approval stops the step;** the engine never sends the run back to an approval on its
   own. Stopping is the fail-closed choice: a person decides what happens next (brief, D17).
6. **`count=2` (several approvers) is deferred** to the `four_eyes` pattern (layer 11).

## How it works

### Answers carry a person, their roles and a form

`Answer` gains `roles` (what the caller states) and `form` (the values an outcome sets, or none).
On Temporal the signal's `Sent` carries both, so they are in history; `answer(run, wait, outcome,
by, roles, form=None)` sends them. In memory a scripted answer is `(state, outcome, who)` or
`(state, outcome, who, form)`, and `people` gives `who` their roles.

### One check for every answer, in order

The interpreter's `why_not` becomes the one place an answer is judged, the same for a wait and an
approval. The first check that fails is the refusal, recorded as `Refused`, and the wait goes on:

1. **The entry is open** (layer 6, on Temporal; a script answers by state).
2. **The outcome is offered.** A wait's closed list (brief, D9); an approval's is `approve` or
   `reject`, so `aprove` is refused, never read as "not approved". `timeout` comes only from the
   timer, as before.
3. **The person has one of the state's roles,** among the roles the catalog registered. A role
   the catalog doesn't know counts for nothing (fail closed).
4. **The form fits the outcome:** exactly the fields its `sets` names, no more, no fewer, each of
   its declared type (a number is an exact `Decimal`, never a float or a bool). An outcome that
   sets nothing takes no form.
5. **For an approval, the role may approve the risk:** some role the person has, and the approval
   lists, is registered to approve at least the activity's risk (`low` < `medium` < `high`).
6. **For an approval, the person is not excluded** (brief, D11): `person:<who>` is not in the
   provenance of `of`'s inputs, nor of the condition on the approval's `approve` transition. The
   refusal names the field: `ana set approved_amount, which pay uses, so cannot approve it`. (The
   person who opened the case is excluded too; a plan has no opener, so that comes in layer 8.)

An accepted answer is recorded as `<who> answered <outcome> as <role>`, with
`, setting <fields>` when it carries a form. The role shown is the one that counted: the first,
in alphabetical order, of the person's roles that let them answer (for an approval, that may also
approve the risk). The waiting line names the roles too: `waiting at review#1 for accept or reject
by support`, and for an approval `waiting at approve_refund#1 for approve or reject of pay by
support-lead`.

### Where a form's fields land, until the case file exists

A plan has had no way to bind a value. Now a wait's outcome may **set declared plan fields**:
`"wait": {"outcomes": [...], "roles": [...], "sets": {"accept": ["approved_amount"]}}`. An
accepted form writes each value into the run's fields, tagged `person:<who>` (brief, D9, D12),
replacing any value from an earlier pass (the latest answer, brief D9). A field some wait sets is
**not given at the start**: the run refuses it ("approved_amount is set by a person in review,
never given at the start"). Reading it before anyone has set it is a missing field, an error that
stops the step (fail closed). In layer 8 these become case-file fields; the plan keeps no form
data of its own.

The validator checks `sets`: an outcome the wait offers (`UNKNOWN_EVENT`), and a field the plan
declares (`UNKNOWN_FIELD`). For the input-policy check a field a person sets has the source
`person:answering <wait>`: a person, trusted, though nobody knows who until they answer. So
`trusted_only` passes and `only_from` doesn't (no system gave it).

### Approvals are tied to the values they saw

When an approval is accepted, the interpreter evaluates `of`'s inputs with the current fields and
keeps the digest of their values (SHA-256 of canonical JSON, numbers as exact text marked apart
from texts; the standard library, as the contract hash uses), as **the open approval of `of`**.
The run keeps it, not the history: on Temporal it is computed again on replay from the same
recorded answers. If `of`'s inputs can't be read yet (a field nobody has set), the step stops:
an approval of values nobody has seen approves nothing. When the run enters an activity state:

- **with an open approval for it,** the inputs are evaluated again and their digest compared. The
  same: the approval is **spent** and the activity is scheduled. Different: the approval has
  **lapsed**, and the step stops: `the inputs of pay changed since sam approved them: a new
  approval is needed`.
- **high risk with no open approval,** the step stops: `payments.refund@2 is high risk, and nobody
  approved this run of pay`. `validate` proves this can't happen in a checked plan; the runtime
  check depends on nothing it did, as the input-policy check doesn't (learning question 34).
- **otherwise** it runs as before.

One approval unlocks one run of one step: answers name their entry (layer 6), the approval is
spent when the step is scheduled, and it holds only for the inputs it saw.

**In a checked plan, the digest never fires.** `APPROVAL_TARGET` makes `approve` lead straight to
`of`, so nothing can change an input in between. The digest is a check that depends on nothing
`validate` did, like the input-policy check (learning question 34); its tests use plans
`validate` refuses. It matters more in layer 8, where a change request can edit the case file
between an approval and its step.

### The tracer's case runner

Its approval code is `TRACER: layer 7`, so it is replaced here, not in layer 8. It calls the same
checks from `core`, on the case's own shapes. `run_case` takes `people`, a misspelled approval
outcome is refused, a team lead's `reject` means `pay` doesn't run and the case closes, and the
quickstart's acceptance tests stay green. The rest of the runner stays tracer code until layer 8.

### Where the code goes

- `core/roles.py`: the role registry's rules and "may this person answer, may this role approve
  this risk".
- `core/form.py`: a form against the declared types of the fields an outcome sets.
- `core/approval.py`: who is excluded, and the digest of a step's inputs.
- `core/person.py`: how a person's identifier is written (tutor review).
- `core/plan.py`: `roles` and `sets` on a wait, the approval state.
- `core/catalog.py` (`register_role`), `core/validate.py`, `core/interpreter.py`,
  `core/history.py`, `temporal/workflow.py` and `client.py`, `testing.py`, `case/runner.py`.

## Not in this layer

- Several approvers (`count=2`, the `four_eyes` pattern; layer 11).
- The case opener's exclusion, case-file fields, and approvals with `when` on case steps beyond
  the tracer (layer 8).
- Fields hidden from a role, and approvers who can't see a field they approve (layer 9).
- Signed approvals (after v1.0, brief D19).
- Claiming and reassigning tasks (after layer 15).

## Seams the tests use

- `Catalog.register_role(name, approves=None)` and its refusals.
- `parse_plan` (shape: roles required, the approval state) and `validate(plan, catalog)` (issues).
- `run_plan(data, fields, answers, people=...)`: `PlanRun.status`, `.reason`, `.history` lines.
- On Temporal: `start_plan`, `answer(run, wait, outcome, by, roles, form=None)`, `report`,
  `result()`, and the `Replayer`.
- `run_case(definition, file, answers, people=...)` and `AnswerRefused`.
- The guide's examples, run as written.

## Slices, in order

0. **The two fixes.** Negative: the guide's history expects `waiting at approve_refund#1 …`, and
   fails on today's line. Then the waiting test asserts `waiting_at`.
1. **Roles in the catalog.** Negative: a role that isn't written as a label, and an `approves`
   that isn't a risk, are refused. Then `roles` lists them in order with what each may approve.
2. **Every wait names its roles.** Negative: a wait without roles is refused by `parse_plan`; a
   role nobody registered is `UNKNOWN_ROLE`; an answer from a person without the wait's role, or
   with only a role the catalog doesn't know, is refused and the wait goes on. Then the right role
   is taken, and the history says `as support-lead`.
3. **Forms.** Negative: a form missing a field, with an extra one, or with a wrong type (a text,
   a float) is refused; `sets` naming an undeclared field or an outcome the wait doesn't offer is
   an issue; a run given a field a wait sets is refused to start. Then the value lands tagged
   `person:ana`, and the input check sees it.
4. **The approval state.** Negative: an approval whose `approve` leads elsewhere, or whose `of`
   isn't an activity, is `APPROVAL_TARGET`; a plain wait offering `approve` before a high-risk
   activity is `APPROVAL_REQUIRED`; a misspelled `aprove` is refused at runtime. Then `reject`
   takes the plan where `on.reject` says, and the guide's plan runs.
5. **Who may approve.** Negative: an approval listing a role that may not approve the risk is
   `APPROVAL_ROLE`, and refused at runtime too; a self-approval (Ana sets `approved_amount`, then
   approves) is refused; a person whose answer feeds the `approve` condition is refused. Then Sam
   approves.
6. **The digest.** Negative: an approval lapses when an input changes before the step runs (an
   amendment between the approval and `pay`, in a plan `validate` refuses); a high-risk activity
   reached with no approval, in a plan never validated, stops. Then a spent approval doesn't
   carry over to a second pass.
7. **On Temporal.** Negative: an answer without the role is refused on Temporal as in memory.
   Then roles and forms cross in the signal, the guide's runs give the same history as in memory,
   and the history replays.
8. **The tracer's runner.** Negative: a misspelled approval outcome is refused; a rejected approval
   closes the case without paying. Then `run_case(people=...)`, and the quickstart's tests stay
   green.

## Decided while building

- **The check every answer passes is one function,** `judge`, in the note's order; an approval's
  own checks (`judge_approval`) come last. Written first as one loop, it grew hard to read once
  approvals added two checks.
- **An approval of something that isn't an activity the catalog holds is refused at runtime**
  (`paid can't be approved: paid is not an activity state`), in a plan `validate` would refuse
  with `APPROVAL_TARGET`. Fail closed: it approves nothing.
- **An input reading a field nobody has set stops the step with a message,** found in slice 3:
  the input-policy check asked for the field's sources first, and `NoSources` crashed the run.
  The check before an activity now turns it into `… can't be evaluated: approved_amount has no
  known sources`.
- **`run_case` and `answer` take people and roles with no default.** A default would be a
  directory again, or nobody; the caller always says.
- **The tracer's `case_value` stays tracer code,** retargeted to layer 8: the quickstart answers
  with whole numbers, and a case's forms are read by declared types with the case file.
- **The guide's examples are run:** the "People in the loop" example as written, and each row of
  its refusal table.

## From the tutor review

- **A rejection was outvoted by an earlier approval.** `approvals[of]` was set on `approve` and
  spent only when `of` ran, so a plan that asked again (in a plan `validate` refuses) paid the
  refund on Sam's approval from `approve_refund#1` after Lee rejected at `#2`. Now entering an
  approval state withdraws any open approval of its `of` (brief, D23).
- **A form dropped the plan's declared mark.** A field declared `untrusted:customer` and set by
  a review reached `payments.refund@2`'s `trusted_only` amount, statically and at runtime. Now a
  form's value keeps the mark, as a start field does: `person:<who>` (statically
  `person:answering <wait>`) plus the declared source. A mark adds distrust, never removes it.
- **One person, two spellings.** `"Sam"` approved what `sam` set, and `"person:sam"` became the
  source `person:person:sam`. D22 now says how an identifier is written, and any other spelling
  is refused at the answer, before any other check, in plans and in the tracer's runner.
- **Optional, carried:** when a person's answer feeds the `approve` condition (or a case step's
  `when`), the refusal says `… which decides whether pay runs`, not `… which pay uses`.

Each negative test was written first and seen failing with the old code.

## Promises

Each claim this note makes about behaviour, and the test that would fail if it weren't true. `P`
is `tests/test_people.py`, `I` `tests/test_interpreter.py`, `T` `tests/test_temporal.py`, `V`
`tests/test_validate.py`, `Q` `tests/test_quickstart.py`, `E` `tests/test_expressions.py`. Every
negative test was seen failing before its code, except: the approval of inputs that can't be read
yet (written with slice 6's code; seen failing by removing the approval's recording), the
approval of something that is no activity (written with slice 5's code), and the tracer runner's
two negatives, which first failed on `people=` and were then run against the runner before slice
8, where both reproduced the tracer review's bugs.

| Promise | Test |
|---|---|
| The waiting line names its entry and roles; a waiting run reports `waiting_at` | I `test_a_run_without_its_answer_waits`; T `test_a_run_without_its_answer_reports_waiting` |
| A role must be written as a label, and `approves` must be a risk; the catalog lists its roles | P `test_a_role_is_written_as_a_label`, `test_a_role_approves_up_to_a_risk_or_nothing`, `test_the_catalog_lists_its_roles_with_what_each_may_approve` |
| A wait or approval without roles is refused; a role nobody registered is `UNKNOWN_ROLE` | P `test_a_wait_without_roles_is_refused`, `test_an_approval_without_roles_is_refused`, `test_a_role_nobody_registered_is_an_issue` |
| An answer from a person without the state's role, with no roles, or with only an unregistered one, is refused and the wait goes on | P `test_an_answer_from_someone_without_the_role_is_refused_and_the_wait_goes_on` |
| The history records the role that counted | P `test_the_role_that_counted_is_the_one_recorded` |
| A form missing a field, with an extra one, or with a wrong type (a text, a float, a boolean) is refused; an outcome that sets nothing takes no form | P `test_a_form_that_does_not_fit_its_outcome_is_refused` |
| `sets` naming an undeclared field or an unoffered outcome is an issue | P `test_sets_names_an_outcome_the_wait_offers_and_a_declared_field` |
| A field a wait sets is not given at the start; reading it before it is set stops the step | P `test_a_field_a_person_sets_is_never_given_at_the_start`, `test_reading_a_field_before_anyone_sets_it_stops_the_step` |
| A form's values are tagged with who answered, and the input check sees that source | P `test_a_forms_values_land_tagged_with_who_answered` |
| Statically, a field a person sets is trusted (`trusted_only` passes) and from no system (`only_from` refuses) | P `test_a_field_a_person_sets_is_trusted_but_from_no_system` |
| A plain wait offering `approve` approves nothing (`APPROVAL_REQUIRED` still holds) | P `test_a_wait_offering_approve_approves_nothing` |
| An approval's `approve` must lead to `of`, an activity state (`APPROVAL_TARGET`); its events are `approve`, `reject` and its timeout | P `test_an_approval_approves_the_activity_its_approve_leads_to`; V `test_an_approval_gives_approve_reject_and_its_timeout_only` |
| At runtime, an approval of something that is no activity approves nothing | P `test_an_approval_of_something_that_is_no_activity_approves_nothing` |
| A misspelled approval outcome is refused, never read as "not approved" | P `test_a_misspelled_approval_is_refused_never_read_as_not_approved` |
| A rejection takes `reject`; the approved activity doesn't run | P `test_a_rejection_takes_reject_and_the_activity_does_not_run` |
| An approval role that may not approve the risk is `APPROVAL_ROLE`, and refused at runtime | P `test_an_approval_role_that_may_not_approve_the_risk_is_an_issue`, `test_an_approval_from_a_role_that_may_not_approve_the_risk_is_refused` |
| A person whose answer flows into the step's inputs, or the `approve` condition, cannot approve it | P `test_a_person_whose_answer_flows_into_the_step_cannot_approve_it`, `test_a_person_whose_answer_decides_the_approval_cannot_give_it` |
| An approval lapses when an input changes before the step runs, up or down, and the step stops; unchanged, it holds | P `test_an_approval_lapses_when_an_input_changes_before_the_step_runs` (300 and 40), `test_an_approval_holds_when_its_inputs_are_unchanged` |
| An approval of inputs that can't be read yet stops the step | P `test_an_approval_of_inputs_that_cannot_be_read_yet_stops_the_step` |
| A high-risk activity with no open approval stops, even in an unvalidated plan | P `test_a_high_risk_activity_nobody_approved_stops_even_unvalidated` |
| An approval is spent when its step is scheduled: a second pass needs a new one | P `test_an_approval_is_spent_when_its_step_is_scheduled` |
| On Temporal, roles and forms cross in the signal, the same checks run, the history matches memory's, and it replays | T `test_an_answer_without_the_role_is_refused_on_temporal_as_in_memory`, `test_a_form_crosses_in_the_signal_and_the_history_replays`, `test_the_guides_run_gives_the_same_history_as_in_memory` |
| In the tracer's runner, a misspelled approval is refused and a rejection closes the case without paying; roles and "someone else" are checked as in a plan | Q `test_a_misspelled_approval_is_refused_never_read_as_not_approved`, `test_a_rejected_approval_closes_the_case_without_paying`, `test_the_reviewer_cannot_approve_the_payment`, `test_approving_needs_the_approval_role`, `test_answering_a_task_needs_its_role` |
| A condition reading a misspelled outcome is rejected (curriculum; layer 2's check) | E `test_a_misspelled_outcome_is_rejected_before_anything_runs` |
| Asking for an approval again withdraws any open approval of its `of`: a rejection is never outvoted (tutor review) | P `test_asking_again_withdraws_an_open_approval_so_a_rejection_is_never_outvoted` |
| A form's value keeps the plan's declared mark, in `validate` and at runtime (tutor review) | P `test_a_form_keeps_the_plans_mark_in_validate`, `test_a_form_keeps_the_plans_mark_at_runtime` |
| A person's identifier is written one way; any other spelling is refused and the wait goes on; a lowercase email is one (tutor review) | P `test_a_person_spelled_any_other_way_is_refused_and_the_wait_goes_on` (`Sam`, ` sam`, `person:sam`), `test_an_identifier_may_be_a_lowercase_email`; Q `test_a_person_spelled_another_way_is_refused` |
| The guide's examples and refusals are what the engine says | P `test_the_guides_people_example_runs_as_written`, `test_the_guides_refusals_are_what_the_engine_says`, `test_every_refusal_in_the_guide_is_tested`; V `test_the_guides_messages_are_what_validate_says`; I `test_the_guides_history` |
