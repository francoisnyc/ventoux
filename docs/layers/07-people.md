# Layer 7: people in the loop

Status: design agreed in the session, 2026-10-08 (all five choices as recommended; the history
shows only the role that counted; a field a wait sets is never given at the start).

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
`, setting <fields>` when it carries a form. The role shown is the first, in order, of those that
let the person answer.

### Where a form's fields land, until the case file exists

A plan has had no way to bind a value. Now a wait's outcome may **set declared plan fields**:
`"wait": {"outcomes": [...], "roles": [...], "sets": {"accept": ["approved_amount"]}}`. An
accepted form writes each value into the run's fields, tagged `person:<who>` (brief, D9, D12),
replacing any value from an earlier pass (the latest answer, brief D9). A field some wait sets is
**not given at the start**: the run refuses it ("approved_amount is set by a person in review,
never given at the start"). Reading it before anyone has set it is a missing field, an error that
stops the step (fail closed). In layer 8 these become case-file fields; the plan keeps no form
data of its own.

The validator checks `sets`: an outcome the wait offers, and a field the plan declares
(`UNKNOWN_FIELD`). For the input-policy check a field a person sets has the source `person`,
trusted, so `trusted_only` passes and `only_from` doesn't (no system gave it).

### Approvals are tied to the values they saw

When an approval is accepted, the interpreter evaluates `of`'s inputs with the current fields and
records the digest of their values (SHA-256 of canonical JSON, numbers as exact text; the
standard library, as the contract hash uses), as **the open approval of `of`**. When the run
enters an activity state:

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
6. **The digest.** Negative: an approval lapses when an input changes before the step runs (a
   loop sets `approved_amount` again); a high-risk activity reached with no approval, in a plan
   never validated, stops. Then a spent approval doesn't carry over to a second pass.
7. **On Temporal.** Negative: an answer without the role is refused on Temporal as in memory.
   Then roles and forms cross in the signal, the guide's runs give the same history as in memory,
   and the history replays.
8. **The tracer's runner.** Negative: a misspelled approval outcome is refused; a rejected approval
   closes the case without paying. Then `run_case(people=...)`, and the quickstart's tests stay
   green.

## Promises

Each claim this note makes about behaviour, and the test that would fail if it weren't true.
Filled in as the slices land; a promise with no test gets one, or leaves the note.

| Promise | Test |
|---|---|
| The waiting line names its entry; a waiting run reports `waiting_at` | |
| A role must be written as a label, and `approves` must be a risk | |
| A wait or approval without roles is refused; a role nobody registered is `UNKNOWN_ROLE` | |
| An answer from a person without the state's role, or with only an unregistered one, is refused and the wait goes on | |
| A form missing a field, with an extra one, or with a wrong type is refused | |
| `sets` naming an undeclared field or an unoffered outcome is an issue | |
| A field a wait sets is not given at the start; reading it before it is set stops the step | |
| A form's values are tagged with who answered, and the input check sees that source | |
| A plain wait offering `approve` approves nothing (`APPROVAL_REQUIRED` still holds) | |
| An approval's `approve` must lead to `of`, an activity state (`APPROVAL_TARGET`) | |
| A misspelled approval outcome is refused, never read as "not approved" | |
| A rejection takes `reject`; the approved activity doesn't run | |
| An approval role that may not approve the risk is `APPROVAL_ROLE`, and refused at runtime | |
| A person whose answer flows into the step's inputs or the `approve` condition cannot approve it | |
| An approval lapses when an input changes before the step runs, and the step stops | |
| A high-risk activity with no open approval stops, even in an unvalidated plan | |
| An approval is spent when its step is scheduled: a second pass needs a new one | |
| On Temporal, roles and forms cross in the signal, the same checks run, and the history replays | |
| In the tracer's runner, a misspelled approval is refused and a rejection closes the case without paying | |
| A condition reading a misspelled outcome is rejected (curriculum; layer 2's check) | |
