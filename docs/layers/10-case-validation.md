# Layer 10: case validation

Status: the split into four parts and 10a's six choices agreed in the session, 2026-10-15 (all as
proposed); 10a's note drafted the same day; 10a built, slices 0–6; Promises checked against the
tests, 2026-10-15; the tutor review's three fixes built test-first, 2026-10-15. 10b's choices and
its four runtime fixes agreed in the session, 2026-10-15 (all as proposed); 10b's note drafted the
same day.

## What this layer is for

Until now a case definition gets only a shape check (`parse_case`). Everything that needs the
catalog, or a view of the whole definition, is found when the case runs, one event at a time, and
reaches an operator with a customer waiting. Layer 10 adds `validate_case(case, catalog)`, which
reads the whole definition before any case opens and reports to the author, each problem as
layer 3's `Issue(path, code, message)`, now an error or a warning.

User-facing description, written first: `docs/guides/cases.md`, "What `ventoux check` proves
about a case". Decision: brief D34 (drafted with this note).

The `chartering` prototype is not checked out in this session; `docs/README-draft.md` shows its
deadlocked claim in the old vocabulary (fragments, `closable`), which the guide rewrites in
today's.

## The split

Layer 10 lands as four pull requests, each with its section in this note, its own Promises table
and its own tutor review, as layers 8 and 9 did:

| PR | Checks | Codes |
|---|---|---|
| **10a: structure** | `Issue` gains its severity; the `validate_case` seam; what a case can ever reach (the fixpoint); deadlocks, steps that never run, closing | `DEADLOCK`, `NEVER_RUNS`, `CLOSES_AT_OPENING`, `NEVER_CLOSES`; warnings `CLOSE_UNREACHABLE`, `UNREACHABLE_MILESTONE` |
| **10b: what each step calls** | the contract exists; a step and its contract are the same kind (8d, decided while drafting, 4); inputs; roles, labels and systems registered; expressions type-checked over the case's values (fields, outcomes as closed lists, outputs from contracts); a high-risk step with no approval (brief, D11), and approval roles that may approve its risk | `UNKNOWN_CONTRACT`, `WRONG_KIND`, `UNKNOWN_INPUT`, `MISSING_INPUT`, `ENGINE_INPUT`, `UNKNOWN_ROLE`, `UNKNOWN_SOURCE`, `UNKNOWN_SYSTEM`, `EXPRESSION_INVALID`, `APPROVAL_REQUIRED`, `APPROVAL_ROLE` |
| **10c: data flow** | input policies over the case file's sources, into plan steps too (the curriculum's layer 8 negative test: an undeclared workflow output can't reach `trusted_only`); a reference input given the wrong system, a text or a computed value (brief, D30); a sensitive value into a workflow step (brief, D31); approvers who can't see what they approve (brief, D16) | `INPUT_POLICY`, `REFERENCE`, `SENSITIVE_TO_WORKFLOW`; warning `APPROVER_CANT_SEE` |
| **10d: teaching warnings** | activity outcomes no step reads (8b, carried to layer 10; brief, D9, D17); `max_age` on a fact nothing can fetch again, or whose read can never pass the refresh gate (brief, D33); a value read without requiring the step that sets it (brief, D9; design question 14) | warnings |

Why this order: 10a carries the curriculum's negative test and the fixpoint, needs the catalog
only for roles, and sets the seam and the error/warning rule the others reuse. 10b comes before
10c because provenance needs expressions that read only known values (`provenance` raises
`NoSources` on a field nobody declared). The codes of 10b–10d are proposals, decided in their own
sessions.

## Decided in the session, for the whole layer

1. **Four parts, as above.** Only 10a is built in this pull request.
2. **Provenance is computed in one pass; the fixpoint is what a case can reach.** Every writer of
   a case-file value tags it with sources that don't depend on what it read: an output with its
   contract's source, "never one the activity sends back" (brief, D29); a form value with
   `person:…` (brief, D9); an outcome with its contract or person; the opening with the opener
   (`write_outputs` and `answer_task` in `case/runtime.py`). So a field's static sources are the
   union of what its writers stamp, which one pass computes exactly. The curriculum's fixpoint
   came from the prototype, where a fragment's `update` computed fields from its result and from
   other fields, so taint flowed through steps; D29 cut that chain at every step boundary. A
   fixpoint over sources returns when a field is computed from other fields: layer 11's "update
   the case file", or design question 17 if it adds a condition's sources to what it gates.
3. **Errors and warnings are one list:** `Issue` gains `severity`, `"error"` or `"warning"`,
   `"error"` when not said, so a check that forgets it refuses (fail closed). Plan validation
   (layers 3 and 4) is unchanged: every issue it gives is an error.
4. **10a's codes and severities,** as in the split's table.
5. **`ventoux check` is layer 14's,** with the builder: the quickstart's command reads the Python
   file, writes `build/*.json` and maps errors to source lines, and it needs a decision on where
   the deployment's catalog is found. Layer 10 gives it its engine, `validate_case`. **Design
   question 17 stays with layer 11:** layer 10's checks look at what a step is given, not whether
   it runs, so neither answer changes them; deciding it beside the update action, which needs the
   same fixpoint, keeps one decision in one place.
6. **D34,** drafted with this note: errors and warnings, structure proven and values not, the
   runtime on its own.

Found while reading, before the session: a `max_age` naming a field its step doesn't read is
already refused when the definition is read (9d, slice 1), so 10d keeps only what needs the
catalog; and a case's expressions aren't type-checked at all today (plans' are, layer 3), so a
misspelt outcome in a case's `when` is silently false, though the quickstart promises
`ventoux check` catches it: 10b's `EXPRESSION_INVALID`.

---

## 10a. Structure: deadlocks, steps that never run, closing

User-facing description, written first: `docs/guides/cases.md`, "What `ventoux check` proves
about a case" (the claim, its deadlock, what the check can't see, the table of codes). It is the
guide's last section: the guide's tests find its code blocks by position, so a section in the
middle would move them.

### What this part is for

A case has no position: steps start when their `requires` are met, and the runtime asks again
after every event. Nothing stops a definition whose requirements can never be met: the deadlocked
claim (`assess` requiring `paid`, which only `pay` reaches, and `pay` requiring `assessed`) runs
its first step and closes, `closed: nothing left to do`, with nobody told why. 10a proves, by
reading the definition, which steps can never run and whether the case can close, and says so to
the author before any case opens.

### What a case can ever reach: the fixpoint

The set of what can happen: steps that can complete, milestones that can be reached.

```
can = {}
repeat:
    for each step not in can, in the definition's order:
        if it can start, and every one of its requirements is in can,
        and its requirements don't include every milestone closes_when names:
            add the step, the milestones it reaches, and every milestone its outcomes reach
until a round adds nothing
```

- **Its requirements** are `requirements(case)` (`case/sequence.py`): its own `requires` and the
  step before it in `sequence`, as the runtime reads them.
- **It can start** if it starts by itself, or one of its `proposed_by` roles is registered: a
  role nobody registered counts for nothing (brief, D22).
- **Every `when` may be true, every outcome may happen,** so a task adds what each of its
  outcomes reaches. That only adds to `can`, so a step left out is left out on every path.
- **Once every `closes_when` milestone is reached, nothing new starts** (8b, and since the tutor
  review even while a failed run holds the close; brief, D34). So a step that waits for all of
  them can never run: one requiring them, or requiring steps that surely reach them, directly or
  through the steps those require, or coming after such a step in `sequence`. A step surely
  reaches a milestone when every completion of it does: a task's own `reaches`, a workflow step's,
  an activity's whose contract declares no outcomes. A run done with a declared outcome
  (`declined`) is done for `requires` but reaches nothing, and a plan may end `failed`.

**Why a fixpoint.** A step can run if what it requires can be reached, and running it reaches
more. Steps have no order to follow (a case has no position), and requirements may point forward,
backward or in a circle, so one pass in any fixed order can miss what a later step makes possible.
The claim with its steps written `pay`, `assess`, `check`: one pass finds `pay` (needs `assessed`)
and `assess` (needs `checked`) not yet possible, then adds `check`, and would say two steps never
run. Repeating: round 2 adds `assess` and `assessed`, round 3 `pay` and `paid`, round 4 nothing.
The runtime does the same on real values: `decide` admits steps until nothing more starts.

**Why it terminates** (the same argument as `reach`, learning question 33): a round only adds to
`can`, never removes; `can` holds only the definition's steps and milestones, a finite list; so
each round either adds at least one name or adds none and stops. At most (steps + milestones)
rounds, and one more to see nothing changed.

**Why start from nothing.** Starting from "everything can happen" and crossing out what can't
would keep `assess` and `pay` in: each would justify the other, and the deadlock would pass. The
least set, grown from nothing, holds only what some order of events really reaches.

**Which way it errs.** A safety check (an approval on every path, layer 3) assumes the worst path
exists, so it may refuse a definition that would be fine. This one assumes every condition may be
true, so it reports only what can never happen: every "can never run" is a proof. A step that only
data keeps from running passes, and lets nothing unsafe run.

### The checks

Steps left out of `can` are **dead**. For each, the first of its requirements not in `can`, in
`requires` order, says what it waits on: a dead step it requires, or the dead steps that reach a
milestone it requires (every step reaching a milestone outside `can` is dead).

- **`DEADLOCK`** (error), at `steps.<step>.requires`: dead steps that wait on each other. One issue
  per group of steps that wait on each other, at the first in the definition's order, naming the
  shortest circle through it: `assess and pay wait on each other: assess requires paid, which only
  pay reaches; pay requires assessed, which only assess reaches: remove one of these
  requirements`. A step requiring itself is a circle of one. Steps in the group get no other
  issue.
- **`NEVER_RUNS`** (error), at `steps.<step>.requires` (or `steps.<step>.proposed_by`): any other
  dead step, saying why, one reason:
  - `approve can never run: it requires reviewed, which no step reaches: reach reviewed from a
    step, or remove the requirement`;
  - `notify can never run: it requires assessed, which only assess reaches, and assess can never
    run: fix assess first` (or `it requires assess, which can never run`);
  - `thank can never run: it requires paid, and claim closes once paid is reached, before thank
    could start: remove paid from its requires, or from closes_when`; through a step it waits
    for, `thank can never run: it runs only after draft, which reaches sent, and letter closes
    once sent is reached, before thank could start: run thank before draft, or remove sent from
    closes_when`;
  - `recheck can never run: it starts only when proposed, and none of its proposed_by roles
    (supprt) is registered: name a registered role`.
- **`CLOSES_AT_OPENING`** (error), at `steps`: the case doesn't stay open, and no step starts by
  itself with nothing required. When it opens nothing is pending, so it closes at once and every
  proposal is refused. Given when some step the structure lets run is kept out by it; a step
  already dead for its own reason keeps its own issue, and if every step is, they say why
  (revised while building, slice 3).
- **`NEVER_CLOSES`** (error), at `close_reasons`: the case stays open, no close reason names a
  registered role, and `closes_when`, which closes a case that stays open too (8b), is empty or
  can never be met, so nobody could ever close it. (`stays_open` with no close reason at all is
  already refused by `parse_case`.) An error, refining D10's "warns" (brief, D34).
- **`CLOSE_UNREACHABLE`** (warning), at `closes_when`: a milestone it names isn't in `can`. A
  warning, as D10 asks: the case still closes when nothing is left to do, or, if it stays open,
  by a person, and the message says which. Every such milestone is named in one issue.
- **`UNREACHABLE_MILESTONE`** (warning), at `milestones.<name>`: no step or outcome reaches it.
  Not given for a milestone a step requires (its `NEVER_RUNS` says it) or `closes_when` names
  (`CLOSE_UNREACHABLE` says it): one cause, one issue.

D10's other examples of a case that never closes, "a step that can always be restarted, a timer
that re-arms itself", can't be written yet: a step starts by itself at most once and runs again
only when proposed, and timers come with rules (layer 11).

No message quotes a value: these read only names.

### Errors, warnings, and the runtime on its own

- **An error** is proven wrong for every case of the definition, or can't be read: whatever
  publishes definitions refuses it (CI now; `ventoux check` and releases, layers 14 and 12).
- **A warning** may be meant, or depends on what the check can't know: accepted, and shown. It
  lets a definition through, never a run.
- **The runtime depends on nothing validation did:** no flag says "validated"; `parse_case`,
  `run_case` and the Temporal client don't call `validate_case`; every runtime refusal and its
  tests stay. A case that skips validation runs exactly as before: the deadlocked claim closes
  with nothing left to do.
- **Fail closed:** `validate_case` given anything but a parsed definition raises `TypeError`, as
  `validate` does for plans, never returning "no issues".

### Where the code goes

- `core/validate.py`: `Issue` gains `severity`.
- `case/reach.py` (new): what a case can ever reach (the fixpoint), and what each dead step waits
  on. Reuses `core/graph.py`'s searches for the shortest circle if they fit without bending
  `Arrow`'s meaning; otherwise a small search of its own.
- `case/validate.py` (new): `validate_case`, the checks above, their messages.
- `tests/test_case_validation.py` (new); the cases guide's claim and table run in it.

### Not in 10a

- Everything in 10b–10d, including `UNKNOWN_ROLE` for each misspelt role (10a only counts an
  unregistered role for nothing, as the runtime does).
- Value-dependent deadlocks: a `when` no data satisfies.
- Rules, timers and what keeps a case open because of them (layer 11); `ventoux check` (layer 14).
- No new dependency.

### Seams the tests use

- `parse_case(data)`, then `validate_case(case, catalog) -> list[Issue]`, from
  `ventoux.case.validate`; an issue's `path`, `code`, `message` and `severity`.
- `testing.CATALOG`; a `Catalog` of the test's own for the role cases.
- `run_case`, once: the deadlocked claim runs without validation and closes with nothing left to
  do.
- The guide: its claim has no issues; its deadlocked claim gives the issues shown; each row of its
  table is what `validate_case` says.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The seam.** Negative: `validate_case` of a dict raises `TypeError`. An `Issue` built without
   a severity is an error. Then the guide's claim, and the quickstart's `refund.json`, have no
   issues.
1. **Steps that never run.** Negative: a step requiring a milestone nothing reaches
   (`NEVER_RUNS`). Then the single-pass trap: the claim with its steps written in reverse order
   has no issues (seen failing with one pass instead of the loop).
2. **The curriculum's negative test.** Negative: the deadlocked claim gives the guide's
   `DEADLOCK`, once, for both steps. Then a step requiring itself; a circle made by `sequence`
   and a `requires` pointing back; a step waiting on a deadlocked one gets `NEVER_RUNS` naming it.
3. **Closing.** Negative: a step requiring every `closes_when` milestone; a proposed step none of
   whose roles is registered; a case where nothing starts by itself (`CLOSES_AT_OPENING`), alone
   and beside a step dead for its own reason; a case that stays open with no close reason naming
   a registered role.
4. **Warnings.** Negative: an unreachable `closes_when` milestone, a milestone nothing reaches,
   each a warning; neither given for a milestone already named by another issue.
5. **The runtime on its own.** The deadlocked claim, run without validation, closes with nothing
   left to do and pays nothing; no runtime test changes.
6. **The guide and the promises:** the guide's examples and table run as written; this table
   checked against the tests.

### Decided while building

- **One pass gives a set that contradicts its own rule** (slice 1). Built first as one pass in
  the written order, the claim with its steps reversed left `assess` out though everything it
  requires (`checked`) was in by the end of the pass, and finding what it waits on crashed
  (`StopIteration`). That is the fixpoint's defining property, missing: once a round adds
  nothing, no step outside the set has all its requirements inside. `never_run` relies on it.
- **Fail closed before it is refined** (slice 1): every dead step is reported from the start; a
  cause slice 1 doesn't name yet gets a plain line, which slices 2 and 3 replace.
- **A requirement `sequence` wrote is said so** (slice 2): `pay comes after assess in sequence`,
  not `pay requires assess`, since nothing on `pay` says it. The circle search follows only each
  dead step's first unmet requirement, the one its message names, so a step blocked first by a
  milestone nothing reaches is `NEVER_RUNS` for that, even if a later requirement also closes a
  circle: one cause, one issue.
- **Two of slice 2's tests passed at once** (slice 2): a step requiring itself is a circle of one
  for the same search, and the `sequence` wording was written with the deadlock code, ahead of its
  test. Each was seen failing on a deliberate break (the one-step wording, the `sequence` branch),
  then restored. The slice's plain fallback line is gone: every dead step now says which of three
  causes it has (a step that can never run, a milestone nothing reaches, or only dead steps reach).
- **A dead step may have every requirement met** (slice 3): kept out by the close (it requires
  every `closes_when` milestone) or because nobody may propose it. Built against slice 2's code,
  the `closes_when` test crashed where `never_run` assumed an unmet requirement; now each dead step
  is asked its cause in order: nobody may start it (at `proposed_by`), a requirement that can't be
  met, then the close. Such a step waits on no other step, so it is never in a circle.
- **`CLOSES_AT_OPENING` alone would have hidden causes** (slice 3). The note said it would be the
  only issue. But slice 2's step requiring itself also leaves nothing to start at opening, where
  `DEADLOCK` is the cause and closing at once its consequence; and a case with one proposed step
  and one automatic step requiring what nothing reaches closes at once *and* needs the second
  fixed. So it is given when a step the structure lets run is kept out by it, beside the other
  issues. Its second test passed at once (the rule was written first) and was seen failing with
  the rule broken to "only when every step could run".
- **`CLOSE_UNREACHABLE` says how the case closes instead** (slice 4): "it closes when nothing is
  left to do" is false for a case that stays open, where only a person closes it; and the first
  version named only the first unreachable milestone, so an author would fix one and meet the
  next. A negative test for each.
- **"One cause, one issue" for milestones was seen failing on a deliberate break** (slice 4): its
  assertions sat after the first, which failed first, so they never ran red; with the exclusions
  removed, a milestone a step requires was warned about twice.
- **The runtime on its own passed at once** (slice 5), as expected: it describes what the runtime
  already does. It was seen failing when pointed at the sound claim, which runs on to the
  assessment instead of closing. No driver calls `validate_case` (only `case/validate.py` names
  it), and no earlier test changed in this layer.
- **The Promises check found four branches written ahead of any test** (slice 6): a milestone two
  dead steps reach ("which only assess and reassess reach", "they can never run"), a circle of
  three, and `NEVER_RUNS` after a close on two milestones. Each got a test, passing at once, and
  each was seen failing on a deliberate break of its branch.
- **The guide's output, table and kinds are run** (slice 6): its printed output is compared word
  for word, line breaks aside; each table row is made to happen, with its message and its kind.
  Changing one word of the output or of a row, or one row's kind, fails a test.
- **"No message quotes a value" is tested on what a definition writes** (slice 6): validation sees
  no case file, so the values it could leak are titles, an approval's reason and literals in a
  `when`. Every example definition is given marked ones, and no message repeats them; seen failing
  with a message made to quote a milestone's title.

### From the tutor review

Three checks disagreed with what `run_case` does; each was fixed test-first.

- **`NEVER_CLOSES` refused a case that closes.** `closes_when` closes a case that stays open too,
  so the probe (paid reachable, no registered close role) closed on `paid`. Now it is given only
  when `closes_when` is empty or can never be met.
- **A step after the close could run.** A failed run holds `closes_when` (brief, D26), and
  admission went on: the probe's `thank`, requiring `paid`, started while `lookup#1` waited for an
  operator, so its `NEVER_RUNS` wasn't a proof. Fixed in the engine, as agreed: once every
  `closes_when` milestone is reached, admission starts only a retried run; a proposal is refused,
  saying why; an approval given meanwhile starts nothing; the retry still closes the case.
  Recorded in D34 as adding to D10 and D26.
- **A step after the close through what it requires passed unseen.** `thank` requiring `draft`,
  which reaches `sent`, or coming after it in `sequence`, never runs, and the check was silent.
  Now a step's requirements imply what its required steps surely reach, transitively.
- **The review's own probe for this was not a proof** (found while building the fix). The review
  said a run that is done reaches its step's milestones "whatever its outcome", but `complete`
  reaches them only on `done`: with `requires: ["pay"]` and a declined refund, `pay#1` is done,
  `paid` isn't reached, and `thank` starts. Built as written, the check would have refused a case
  that runs, item 1's flaw again. So only milestones every completion reaches count, the
  `requires: [pay]` probe gets no issue (a test runs the declined refund and sees `thank`
  start), and the letter case, whose `letters.draft@3` declares no outcomes, carries the
  `requires` and `sequence` forms.
- **Transitivity matters only with several `closes_when` milestones** (found while building): a
  middle step that requires the closing step waits for the close itself, so it never runs and the
  last step says it waits on it. Its test closes on two milestones, the middle step reaching one.
  The message names every step it waits for, and gives a fix naming one change only when that
  change would let the step run.
- **Two suggestions taken:** D34 says it refines D10's "warns about cases that can never close";
  the guide says `ventoux check` arrives with layer 14 and `validate_case` works now.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`V` is `tests/test_case_validation.py`, `C` is `tests/test_case.py`. Checked against the tests,
2026-10-15: every test named here exists, and every test in `V` is named here.

| Promise | Test |
|---|---|
| `validate_case` refuses anything but a parsed definition, never returning "no issues" | V `test_only_a_parsed_case_is_validated` |
| An issue that says no severity is an error | V `test_an_issue_is_an_error_unless_it_says_otherwise` |
| A sound case has no issues: the guide's claim, the quickstart's refund | V `test_the_guides_claim_has_no_issues`, `test_the_quickstart_refund_has_no_issues` |
| The order steps are written in changes nothing (the fixpoint, not one pass) | V `test_the_order_of_the_steps_does_not_matter` |
| Any outcome of a task may happen: what any of them reaches can be reached | V `test_the_guides_claim_has_no_issues` (`pay` requires `assessed`, which only `accept` reaches) |
| A step requiring a milestone nothing reaches never runs | V `test_a_step_requiring_what_nothing_reaches_never_runs` |
| Steps that wait on each other are one `DEADLOCK`, naming the circle, with no other issue for them; the guide's message word for word | V `test_the_deadlocked_claim_is_refused`, `test_a_step_requiring_itself_is_deadlocked`, `test_sequence_and_requires_can_deadlock`, `test_three_steps_can_wait_on_each_other` |
| A step waiting on a dead step never runs, saying which, every dead step reaching its milestone named | V `test_a_step_waiting_on_a_deadlock_never_runs`, `test_a_milestone_two_dead_steps_reach_names_both` |
| A step requiring every `closes_when` milestone never runs, however many there are | V `test_a_step_after_the_close_never_runs`, `test_a_step_after_a_close_on_two_milestones_never_runs` |
| A step waiting, through a step it requires or `sequence`, for every `closes_when` milestone never runs; the message names the step reaching the close; the run agrees | V `test_a_step_after_the_close_through_a_step_it_requires_never_runs`, `test_a_step_after_the_close_through_sequence_never_runs` |
| What a step waits for is followed through the steps it requires; both the milestones it requires and the steps it waits for are said | V `test_what_a_step_waits_for_is_followed_through_the_steps_it_requires` |
| A step after one that may end otherwise (a declared outcome) is not refused, since it can run | V `test_a_step_after_a_step_that_may_end_otherwise_can_run` |
| The engine: once every `closes_when` milestone is reached, nothing new starts while a failed run holds the close; a proposal is refused saying why; an approval given meanwhile starts nothing; the retried run closes the case | C `test_nothing_new_starts_while_a_failed_run_holds_the_close`, `test_a_proposal_while_the_close_is_held_is_refused`, `test_an_approval_answered_while_the_close_is_held_starts_nothing`, `test_the_failed_run_retried_closes_the_case` |
| A case where nothing starts by itself is refused once; a step dead for its own reason keeps its own issue beside it | V `test_a_case_that_closes_at_opening_is_refused`, `test_closing_at_opening_is_said_beside_a_step_dead_for_its_own_reason` |
| A case that stays open is refused only if no registered role may close it and `closes_when` is empty or can never be met; accepted with a registered role, or a reachable `closes_when` | V `test_a_case_nobody_can_close_is_refused` |
| A step only roles nobody registered may propose never runs | V `test_a_step_nobody_may_propose_never_runs` |
| An unreachable `closes_when` milestone and a milestone nothing reaches are warnings, never repeated beside another issue | V `test_an_unreachable_close_is_a_warning`, `test_a_milestone_nothing_reaches_is_a_warning` |
| `CLOSE_UNREACHABLE` says how the case closes instead, and names every unreachable milestone | V `test_an_unreachable_close_says_how_the_case_closes_instead`, `test_every_unreachable_close_milestone_is_named` |
| No message quotes a value | V `test_no_message_quotes_a_value` |
| The runtime depends on nothing validation did: the deadlocked claim runs and closes, paying nothing | V `test_an_unchecked_deadlock_still_runs_safely`; every runtime test, unchanged |
| The guide says what the code does: its claims, its printed output, and its table (every code, each example's message and kind) | V `test_the_guides_claim_has_no_issues`, `test_the_deadlocked_claim_is_refused`, `test_the_guide_lists_every_code`, `test_the_guides_table_is_what_validate_case_says` |
| `case` imports no Temporal or LLM code, in the new modules too | `tests/test_layers.py`, unchanged |

---

## 10b. What each step calls

User-facing description, written first: `docs/guides/cases.md`, "What each step calls". Decision:
brief D35 (drafted with this note).

### What this part is for

10a reads a case's structure. 10b reads what each step calls, against the catalog and the plans
the deployment supplies: today every such mistake is found only when the step is reached, with a
customer waiting, and one isn't found at all. The quickstart's refund with `"aprove"` in `pay`'s
`when`: Ana approves, the condition is false, and the case closes, `closed: nothing left to do`,
the refund never paid and nobody told.

### The checks

| Code | At | Given when |
|---|---|---|
| `UNKNOWN_CONTRACT` | `steps.<s>.activity` or `.workflow` | the catalog holds no contract under the reference (the catalog's own message) |
| `WRONG_KIND` | the same | the contract is of the other kind (the catalog's own message) |
| `UNKNOWN_PLAN` | `steps.<s>.plan` | the plan isn't among the plans given, can't be read, or is supplied under another reference (`supplied`, the runtime's reader) |
| `UNKNOWN_INPUT` | `steps.<s>.inputs.<i>` | the contract takes no such input (the key aside); a plan takes no such field, or a wait of the plan sets it |
| `MISSING_INPUT` | `steps.<s>.inputs` | a required input of the contract (the key aside), or a field the plan takes at its start, isn't given |
| `ENGINE_INPUT` | `steps.<s>.inputs.<key>` | the step gives the contract's idempotency key |
| `UNKNOWN_ROLE` | `steps.<s>.roles`, `.approval.roles`, `.proposed_by`, `close_reasons.<r>.roles`, `fields.<f>.visible_to` | a role the catalog doesn't hold |
| `UNKNOWN_SOURCE` | `fields.<f>.source` | `untrusted:<label>` with a label nobody registered |
| `UNKNOWN_SYSTEM` | `fields.<f>` | a reference, or a reference in a list's records, names a system nobody registered |
| `EXPRESSION_INVALID` | `steps.<s>.when`, `.approval.when`, `.inputs.<i>` | layer 3's `check` refuses it over the case's types; a condition doesn't give a boolean |
| `APPROVAL_REQUIRED` | `steps.<s>` | the contract is high risk and the step has no approval |
| `APPROVAL_ROLE` | `steps.<s>.approval.roles` | a registered role on the approval may not approve the contract's risk |

**The case's types**, what `check` is given: each field with its declared type; `<task>.outcome`
as the task's outcomes; `<activity>.outcome` as `done` and its contract's outcomes;
`<workflow>.outcome` as `done`; `<plan>.outcome` as `done` or `failed`; `<step>.<output>` for
each output its contract declares, a decimal as a number, a text as a string (a reference to its
system when it says so), a boolean as a boolean. Registration refuses any other output type
(brief, D29); one that got through anyway is left out, so reading it is an error (fail closed).
Nothing writes `pay.approval` (D11's example), so reading it is an error too.

### An error is a proof

Each code was read against what `run_case` does with the same definition (10a's review: two
errors didn't hold for every case). A test for each code runs it and sees the refusal:

| Code | The runtime |
|---|---|
| `UNKNOWN_CONTRACT`, `WRONG_KIND` | `called` raises `NotInCatalog`: the step fails |
| `UNKNOWN_PLAN` | `supplied` refuses it: the step fails, in memory and on Temporal |
| `UNKNOWN_INPUT`, `MISSING_INPUT` | `checked_inputs` (activity, workflow) or the plan's `refuse_to_start` refuses: the step fails |
| `UNKNOWN_ROLE` | the role counts for nothing (`role_that_counts`): an answer, a proposal or a close relying on it is refused |
| `UNKNOWN_SYSTEM` | `refuse_to_open` refuses the case |
| `EXPRESSION_INVALID`, a field nobody declared, a wrong type, a condition that isn't a boolean | evaluating it fails the step |
| `APPROVAL_REQUIRED` | `schedule` stops the step: `is high risk, and pay has no approval` |
| `APPROVAL_ROLE` | the approval answered with that role is refused (`risk_refusal`) |

**Four gaps, closed in the runtime** (agreed in the session; brief, D35). Probes with `run_case`
showed the runtime letting each through:

- **G1, a misspelt outcome reads as false.** The runtime now type-checks a step's expressions
  (its `when`, its approval's `when`, its inputs) over the same types before reading them, in
  admission, a proposal and a retry; one that doesn't check fails the step (or refuses the
  proposal or retry) with the check's message. The types are computed by one function both use,
  `case/types.py`, from the definition and the catalog: the runtime depends on nothing
  validation did (brief, D34).
- **G2, an input named after the idempotency key was overwritten,** and the history said
  `idempotency_key from the case`. `checked_inputs` now refuses it, for plans too.
- **G3, a field declared with an unregistered label opened and ran.** `refuse_to_open` now
  refuses it, beside an unregistered system (brief, D12, D30).
- **G5, an unregistered role saw a field.** `may_see` counted any role a case names, registered
  or not, so a person stated with `supprt` saw a field `visible_to: [supprt]`. Now only a
  registered role gives sight, as only a registered role answers (brief, D22).

Found while probing, left to 10c: `"amount": "40"` (a text) paid a refund of 40, since the
contract's Pydantic model turns a text into a decimal. Checking an input's type against its
contract belongs with 10c's reference inputs; the lax conversion goes with it.

### Plan steps

A case references a plan, never defines one (brief, D28). `validate_case(case, catalog,
plans=…)` takes the deployment's plans exactly as `run_case(plans=…)` and
`CaseWorkflow.plans` do, stored data by reference, and reads each with `supplied`, the runtime's
reader, so the check and the runtime can't disagree about which plan a step runs. No `plans`
means none: a plan step then gets `UNKNOWN_PLAN`. What it checks of a plan step: the plan is
supplied and readable; each input names a field the plan takes at its start (a field a wait sets
is the person's, never given); every such field is given; each input's expression checks over the
case's types. Not checked: the plan itself (layer 3's `validate`, where plans are published), and
an input's type against the plan field's (10c, with activity inputs').

### Values in messages

10a: no message quotes a value. A misspelt outcome is easier to fix if the message names it, and
layer 3's `check` already does (`has no outcome "aprove"`). Decided: a message may quote a
literal of the definition when that literal is what is wrong. It is text the author wrote,
already in the definition. Titles, an approval's reason and anything from a case file are never
quoted (brief, D35).

### One cause, one issue

- A step whose contract or plan is missing or of the wrong kind gets that one issue: no input,
  approval or approval-role issues for it, and no `EXPRESSION_INVALID` for an expression reading
  its outcome or outputs. Safe, because the error already refuses the definition.
- An input whose expression is refused isn't checked further.
- An unregistered role a structural issue already names isn't repeated: a step only roles nobody
  registered may propose (`NEVER_RUNS`), and close reasons none of whose roles is registered
  (`NEVER_CLOSES`, whose message now names them too).

### Two message fixes carried from 10a

- **Two `closes_when` milestones, both required:** the advice was "remove one of them from its
  requires, or from closes_when", but removing one from `closes_when` leaves the step requiring
  the other, which still closes the case. Now: "remove one of them from its requires".
- **A milestone a waited-for step requires was said to be reached by it:** `notify`, requiring
  `paid` and reaching `notified`, was "notify, which reaches paid and notified". What a step waits
  for now keeps whether each milestone is required or reached by the step it comes through.

### Where the code goes

- `case/types.py` (new): the case's types, for validation and the runtime.
- `case/calls.py` (new): 10b's checks, one function per row of the table.
- `case/validate.py`: `validate_case` takes `plans`, and adds `calls`' issues.
- Runtime fixes: `case/admission.py` or `case/runtime.py` (G1), `core/before_activity.py` (G2),
  `case/runtime.py` (G3), `case/visibility.py` and its callers (G5).
- Tests: `tests/test_case_validation.py`; each runtime fix beside its earlier tests.

### Seams the tests use

- `parse_case(data)`, then `validate_case(case, catalog, plans=…)`; an issue's `path`, `code`,
  `message` and `severity`.
- `run_case(..., plans=…, catalog=…, activities=…)` for every proof; the Temporal test driver for
  `UNKNOWN_PLAN`, where the driver reads the plans itself.
- The guide: its example output and its table of 10b's codes are what `validate_case` says.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The two message fixes** (10a's, first commit).
1. **The contract or plan:** `UNKNOWN_CONTRACT`, `WRONG_KIND`, `UNKNOWN_PLAN`, each with its run.
2. **Inputs:** `UNKNOWN_INPUT`, `MISSING_INPUT`, `ENGINE_INPUT`, for activity, workflow and plan
   steps; G2.
3. **Registered names:** `UNKNOWN_ROLE`, `UNKNOWN_SOURCE`, `UNKNOWN_SYSTEM`; G3, G5.
4. **Expressions:** the case's types, `EXPRESSION_INVALID`; G1.
5. **Approvals:** `APPROVAL_REQUIRED`, `APPROVAL_ROLE`.
6. **The guide and the promises.**

### Not in 10b

- Input types against the contract or the plan's fields, and the lax conversion (10c).
- Input policies, references and sensitive values (10c); teaching warnings (10d).
- No new dependency.
