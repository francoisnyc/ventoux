# Layer 10: case validation

Status: the split into four parts and 10a's six choices agreed in the session, 2026-10-15 (all as
proposed); 10a's note drafted the same day; 10a built, slices 0–6; Promises checked against the
tests, 2026-10-15; the tutor review's three fixes built test-first, 2026-10-15. 10b's choices and
its four runtime fixes agreed in the session, 2026-10-15 (all as proposed); 10b's note drafted the
same day; 10b built, slices 0–6; Promises checked against the tests, 2026-10-15. 10c's choices and
its two runtime fixes agreed in the session, 2026-10-16 (all as proposed); 10c's note drafted the
same day; 10c built, slices 1–6; Promises checked against the tests, 2026-10-16. 10d's choices
agreed in the session, 2026-10-16 (all as proposed; the quickstart's choice, a); 10d's note
drafted the same day.

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
- `case/registered.py` (new, while building): the roles, labels and systems a case names.
- Runtime fixes: `case/runtime.py` (G1, in admission, a proposal and a retry; G3),
  `core/before_activity.py` (G2), `case/visibility.py` and its callers (`answers.py`,
  `memory.py`, `temporal/cases.py`) (G5).
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
- Two notes carried to layer 12 (from the tutor review): a case failed by G1 can't be retried
  (the same check refuses the retry) and, without a close reason an operator holds, waits for a
  change request; and on Temporal, a running case that skipped such a step under the old code
  (its `when` read as false) would replay differently under the new code.
- No new dependency.

### Decided while building

- **Reading the plans with the runtime's reader paid off at once** (slice 1): a plan supplied
  under another reference and one that can't be read are both `UNKNOWN_PLAN`, with the runtime's
  own words; only a plan not supplied at all adds what to do. The Temporal test runs two such
  plans on the driver and compares the step's failure with the issue.
- **Layer 5 had pinned G2's old behaviour** (slice 2): `test_the_engines_key_replaces_any_a_plan_
  gives` asserted the silent replacement. Renamed `test_a_key_a_plan_gives_is_refused`, asserting
  the refusal; layer 5's note is amended, saying when, not rewritten.
- **Two issues for one misspelt input:** `amout` is both an input the contract doesn't take and
  `amount` missing, as layer 3 says for plans. They are two facts, each with its own fix-up, so
  both are kept.
- **A step whose contract or plan is missing gets nothing else** (slices 2 and 4): not its input
  names, not its inputs' expressions, not an expression elsewhere reading its outcome or outputs,
  not an approval issue. Its `when` is still checked: it reads nothing the missing contract gives.
- **10a's tests met `UNKNOWN_ROLE`** (slice 3): `staying_open` closes on a role written `supprt`
  on purpose. That role really can never close the case, so the two assertions expecting no issue
  now expect it. `NEVER_CLOSES` names the roles (`none of its close reasons' roles (supprt) is
  registered`) and suppresses `UNKNOWN_ROLE` for them.
- **G1 changed three earlier tests' messages, not their outcomes** (slice 4): a step reading an
  output its contract doesn't declare (`pay.email`) now fails before any value is read, saying so;
  and the case-data guide's "computed value" was `cat` of a reference, which doesn't type-check
  (`cat` joins texts), so it now is `cat` of `string(customer_id)`, still a computed value, still
  refused by the reference check as the guide says.
- **The runtime's check reads the whole step at once,** before freshness, the condition and the
  approval: the first expression that doesn't check names where it is (`pay.when can't be read:
  …`, `pay.inputs.amount can't be read: …`). Asked again in each admission round; it reads only
  the definition and the catalog, so it is deterministic on replay.
- **Tests that passed at once, each seen failing on a deliberate break:** the one-cause tests
  (slices 2 and 4: a contract kept for a missing step, no skip for it), the Temporal comparison
  (validation checking only that a plan's reference is there), the proposal and retry checks
  (each removed in turn), the guide's table (one word of a row changed).

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`V` is `tests/test_case_validation.py`, `T` is `tests/test_temporal_case.py`, `I` is
`tests/test_interpreter.py`. Checked against the tests, 2026-10-15: every test named here exists,
and every test 10b added to `V` is named here (10a's table names the rest).

| Promise | Test |
|---|---|
| Two `closes_when` milestones both required: the fix names only its requires; removing one from `closes_when` still leaves the step after the close | V `test_a_step_after_a_close_on_two_milestones_never_runs` |
| A milestone a waited-for step requires is said so, not said reached by it; each step it comes through says what it requires and reaches | V `test_a_milestone_a_waited_for_step_requires_is_said_so`, `test_what_a_step_waits_for_is_followed_through_the_steps_it_requires` |
| A contract nobody registered is `UNKNOWN_CONTRACT`, the catalog's message; the step fails when run | V `test_a_contract_nobody_registered_is_refused` |
| A step and its contract of different kinds is `WRONG_KIND`; the step fails | V `test_a_step_and_its_contract_are_the_same_kind` |
| No plans given means none: a plan step is `UNKNOWN_PLAN`; given as the runtime is, it is found; the step fails without it | V `test_a_plan_nobody_supplied_is_refused` |
| A plan supplied under another reference, or unreadable, is `UNKNOWN_PLAN` in the runtime's words; in memory and on Temporal the step fails the same | V `test_a_plan_the_runtime_would_not_run_is_refused`; T `test_case_validation_says_what_the_driver_does_with_its_plans` |
| An input the contract doesn't take, and one it needs, are refused; the run refuses them | V `test_an_input_the_contract_does_not_take_is_refused`, `test_an_input_the_contract_needs_is_given` |
| The key is the engine's: `ENGINE_INPUT`; the runtime refuses it in a case and in a plan, never overwriting it (G2) | V `test_the_engine_fills_the_key`; I `test_a_key_a_plan_gives_is_refused` |
| A plan step gives exactly the fields its plan takes at its start, never one a wait sets; the run refuses the same | V `test_a_plan_step_gives_the_fields_its_plan_takes_at_its_start` |
| A role nobody registered is `UNKNOWN_ROLE` wherever the case names it, and answers, approves and sees nothing when run (G5) | V `test_a_role_nobody_registered_answers_nothing`, `test_a_role_nobody_registered_approves_nothing`, `test_a_role_nobody_registered_sees_nothing` |
| A role a structural issue names isn't repeated: proposed_by (`NEVER_RUNS`), close reasons (`NEVER_CLOSES`, which names them) | V `test_a_role_nobody_registered_is_said_once`, `test_a_case_nobody_can_close_is_refused` |
| A label nobody registered is `UNKNOWN_SOURCE`, and the case doesn't open (G3) | V `test_a_label_nobody_registered_is_refused` |
| A system nobody registered is `UNKNOWN_SYSTEM`, and the case doesn't open | V `test_a_system_nobody_registered_is_refused` |
| A misspelt outcome is `EXPRESSION_INVALID`, the guide's output word for word; run, the step fails saying why, never reading false (G1) | V `test_a_misspelt_outcome_is_refused` |
| A case reads only its values: a field nobody declared, an approval nothing writes | V `test_a_case_reads_only_its_values` |
| Outcomes are closed lists: an activity's `done` and its contract's, a workflow's `done`, a plan's `done` or `failed`; outputs have their contract's types | V `test_outcomes_and_outputs_have_their_contracts_types`, `test_a_plan_steps_outcome_is_done_or_failed` |
| A condition gives a boolean; an input's expression is type-checked; the run fails each | V `test_a_condition_gives_true_or_false`, `test_an_input_reads_only_the_cases_values` |
| The runtime checks a step's expressions in a proposal and a retry too | V `test_a_proposal_or_a_retry_never_reads_a_misspelt_outcome` |
| One cause, one issue: a missing contract's inputs, approval and what reads its outcome aren't said again | V `test_a_step_whose_contract_is_missing_has_one_issue`, `test_what_a_missing_contract_would_give_is_said_once`, `test_an_approvals_roles_may_approve_its_steps_risk` |
| A high-risk step without an approval is `APPROVAL_REQUIRED`, and the run stops it; a conditional approval is enough | V `test_a_high_risk_step_has_an_approval` |
| A registered role that may not approve the step's risk is `APPROVAL_ROLE`, and its approval is refused | V `test_an_approvals_roles_may_approve_its_steps_risk` |
| A message quotes a literal only when it is the mistake; never a title or reason | V `test_a_message_quotes_only_the_literal_that_is_wrong`, `test_no_message_quotes_a_value` |
| The guide says what the code does: its example output, its table (every code, each message and kind) | V `test_a_misspelt_outcome_is_refused`, `test_the_guide_lists_every_code_for_what_steps_call`, `test_the_guides_table_of_calls_is_what_validate_case_says` |
| `case` imports no Temporal or LLM code, and reads no clock or I/O, in the new modules too | `tests/test_layers.py`, unchanged |

---

## 10c. Data flow: where each value comes from, and whether it may go there

User-facing description, written first: `docs/guides/cases.md`, "Where each value comes from".
Decision: brief D36 (drafted with this note).

### What this part is for

10b reads what each step calls. 10c follows each value a step reads to where it goes. Today all
of it is found only when the step runs, and probes with `run_case` (2026-10-16) found worse:

| Definition | The runtime today |
|---|---|
| plan step `settle` given `amount` from a field declared `untrusted:customer` | the plan starts, its own approval is asked and given, and only then its `pay` stops on `trusted_only` |
| `settle` given `order_id` as `cat("x", string(order_id))`, its plan field a reference to `orders` | **paid**: the plan's reference check trusts its field's declared type, and nothing checks what the case gave it |
| `settle` given `amount` as `string(approved_amount)` | **paid**: Pydantic turns the text into a decimal |
| `pay` given `"amount": "40"` (carried from 10b) | **paid 40**, for the same reason |
| `settle` given the literal `40` | refused when the plan starts: `amount comes with no sources` |

### Decided in the session

Agreed 2026-10-16, all as proposed.

1. **The codes:** `REFERENCE`, `INPUT_POLICY`, `INPUT_TYPE`, `NO_SOURCES`,
   `SENSITIVE_TO_WORKFLOW` (errors); `APPROVER_CANT_SEE` (warning). `INPUT_TYPE` and
   `NO_SOURCES` are new beside the split's table; `OPENER_DECIDES` (warning) was named while
   drafting the guide, for the one input whose fate depends on who opens the case (below).
2. **`APPROVER_CANT_SEE` is a warning, never an error.** `unseen` judges an approval with every
   role the person holds (`may_see(…, answer.roles, …)`), so a team lead who also holds `fraud`
   may approve a step reading a field only `fraud` sees. Whether anyone holds both is what the
   check can't know (brief, D34). The only value nobody could ever see is one whose `visible_to`
   names only unregistered roles, already `UNKNOWN_ROLE`. The refusal at answer time stays.
3. **Two runtime gaps closed** (brief, D36), each on nothing validation did (brief, D34):
   - **G6, the lax conversion.** `checked_inputs` validates an activity's or workflow's inputs
     strictly, in cases and in plans: a value is never converted, so `"40"` is refused where a
     decimal is taken. Probed first: lax Pydantic turns `"40"` into `Decimal(40)`, `"yes"` and
     `Decimal(1)` into `True`, `True` into the `int` 1; strict refuses each, and refuses
     `Decimal(3)` for an `int` (a whole number given as a decimal). Every contract input in the
     repository is `str` or `Decimal`, and the whole suite passed with `strict=True` (1005 tests).
   - **G7, a plan's fields at its start.** `refuse_to_start` checks each field the case gives
     against the plan field's type, and a reference field takes only a reference to its system,
     read as it is, as a contract's reference input does (brief, D30: "in cases and in plans").
4. **A plan field given only literals stays refused at runtime;** validation says so first
   (`NO_SOURCES`). A literal has no source, and D28 gives a plan field the sources of what it read.
5. **One data-flow issue per input:** the first the runtime would meet. Activity and workflow
   steps: reference, policy, type, then sensitive (a workflow step), the order of `checked_inputs`
   and `schedule`. Plan steps: reference and type, then no sources (the plan's start), then policy
   (inside the plan). An input already refused for its expression, or whose step's contract or
   plan is missing (10b), gets none.
6. **D36,** drafted with this note.

### Provenance in one pass

Every writer stamps what it writes with sources that don't depend on what it read (brief, D34),
so a field's static sources are the union of its writers' stamps, plus the field's mark:

| Writer | Static source | The runtime records |
|---|---|---|
| the opening | the opener (below) | `system:opener`, or `person:<who>` |
| a task's form and its outcome | `person:answering <task>`, layer 4's stand-in | `person:ana` |
| an activity's or a workflow's outcome | `system:<contract>` | the same |
| a plan step's outcome | `system:<plan>` | the same |
| an output | its contract's source, or `untrusted:undeclared` (brief, D29) | the same |
| a field declared `untrusted:<label>` | the label, added to every writer's stamp | the same (`marked`) |

An input's sources are the union over every field it reads (`provenance`, conditions and both
branches of an `if` included), as the runtime computes them. The stand-ins differ from what the
runtime records only in *which* person and *who* opens. `trusted_only` takes any person and any
system; `only_from` refuses any person and takes `system:opener` only if it names `opener`.
Untrusted sources never vary. So the check runs each policy twice, once with the case opened by a
system and once by a person:

- refused both times: **`INPUT_POLICY`**, an error, and a proof;
- refused only when a person opens it (an `only_from` naming `opener`): **`OPENER_DECIDES`**, a
  warning: whether it runs depends on who opens the case, which the check can't know;
- passed both times: nothing.

Messages name the opening's source **the opener**, never a person. **A source the check can't
know fails closed:** one that is neither trusted nor declared untrusted is refused by
`trusted_only`, as at runtime; a field with no known sources (`NoSources`) can't occur after 10b
(every value an expression may read has a writer), and if it does, `validate_case` raises, never
returning "no issues".

### Plan steps

A plan field's runtime sources are the case expression's sources, plus the plan's own mark
(`interpreter.run`). The check gives each plan field the case expression's static sources and
runs the plan's layer 4 policy check with them, in place of `case`. A field a wait in the plan
sets stays `person:answering <wait>`. The plan's own marks are left out: a plan refusing its own
untrusted field is the plan's issue, given by `validate` where plans are published (layer 3), not
the case's. The issue sits at the case's `steps.<s>.inputs.<field>`, what the case's author can
change, and its message starts with the plan and its state: `refund-order@1, in its state pay:
payments.refund@2 takes amount only from …`. `validate(plan, catalog)` is unchanged; the
policy check gains a seam that takes the fields' sources.

### The checks

| Code | At | Given when | The runtime |
|---|---|---|---|
| `REFERENCE` | `steps.<s>.inputs.<i>` | a contract's reference input, or a plan's reference field, is given anything but a reference field of its system read as it is | `checked_inputs` (`not_a_reference_to`), or the plan's start (G7): the step fails |
| `INPUT_POLICY` | `steps.<s>.inputs.<i>` | a policy refuses the value's sources whoever opens the case | `checked_inputs`, in the case or inside the plan: the step fails |
| `OPENER_DECIDES` (warning) | `steps.<s>.inputs.<i>` | a policy refuses them only when a person opens the case | the same, for a case a person opens |
| `INPUT_TYPE` | `steps.<s>.inputs.<i>` | the expression's type isn't the input's: a number for `Decimal`, a string, outcome or reference for `str`, a boolean for `bool`; a plan field's own type. A contract input of any other type is never given exactly by a case (it holds decimals, texts and booleans) | strict validation (G6), or the plan's start (G7): the step fails |
| `NO_SOURCES` | `steps.<s>.inputs.<i>` | a plan field is given an expression reading no field | the plan's start: the step fails |
| `SENSITIVE_TO_WORKFLOW` | `steps.<s>.inputs.<i>` | a workflow step's input reads a field declared sensitive | `refuse_sensitive_inputs`: the step fails |
| `APPROVER_CANT_SEE` (warning) | `steps.<s>.approval.roles` | a registered role on the approval, held alone, can't see a value the step reads (its inputs, its `when`, the approval's `when`); one issue per role and value (revised while building, slice 5) | an answer from a person who can't see one is refused (`unseen`) |

**References follow the runtime:** an output is never a reference field, even one its contract
types as a reference (`not_a_reference_to` reads the case's declared fields). In practice
`APPROVER_CANT_SEE` comes only from a field narrowed by `visible_to`: approval roles are among the
roles a case names, which see every value not narrowed.

No message quotes a value from a case file (brief, D35): they name fields, types, sources and
roles. Sources are the stand-ins, never a person's name.

### Where the code goes

- `case/flow.py` (new): the case's static sources, and 10c's checks, one function per code.
- `core/validate.py`: `refused_inputs`, the policy check over the fields' sources it is given (a
  seam for plan steps); `core/policy.py`: `refusal` may name a source as a message says it.
- `case/validate.py`: adds `flow`'s issues, in the order the runtime meets them.
- Runtime: `core/before_activity.py` (G6; `given_as_reference`, split out of
  `not_a_reference_to`), `core/interpreter.py`'s `refuse_to_start` (G7's type half);
  `case/runtime.py`'s `start_plan`, `case/state.py`'s `StartPlan.references`,
  `case/plan_step.py`'s `wrong_references`, asked by both drivers (`testing.py`,
  `temporal/cases.py`) (G7's reference half; revised while building, slice 3).
- Tests: `tests/test_case_validation.py`; G6 and G7 beside their earlier tests
  (`test_interpreter.py`, `test_plan_step.py`, `test_temporal_case.py`).

### Seams the tests use

- `parse_case`, then `validate_case(case, catalog, plans=…)`; an issue's `path`, `code`,
  `message`, `severity`.
- `run_case(…, plans=…, plan_answers=…)` for every proof: the same definition, refused or failed
  as the issue says; its history's `amount from …` for the one-pass promise.
- `run_plan` (from `testing`) for G6 inside a plan, beside layer 5's tests.
- The guide: its example output and its third table are what `validate_case` says.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

1. **Sources in one pass, `INPUT_POLICY` on activity and workflow steps.** Negative: the guide's
   lesser-of-two refund (`INPUT_POLICY`, and the run fails the same). Then an output with no
   declared source, an outcome read by `only_from`, a value computed from several fields compared
   with what the run records; `OPENER_DECIDES`.
2. **Into plan steps.** Negative: the estimate through `refund-order@1`, refused at the case's
   input; the run stops inside the plan. A plan's own mark isn't the case's issue.
3. **References.** `REFERENCE` for activity steps; G7's reference half, and `REFERENCE` for plan
   steps (the fabricated order ID, paid today, then refused).
4. **Types.** G6 (`"40"` refused, in a case and in a plan); G7's type half; `INPUT_TYPE`;
   `NO_SOURCES`.
5. **Sensitive values and approvers.** `SENSITIVE_TO_WORKFLOW`, `APPROVER_CANT_SEE`, each with
   its run.
6. **One cause, one issue; the guide and the promises.**

### Decided while building

- **A source the check doesn't recognise can't come from a definition** (slice 1). A field's mark
  is `untrusted:<label>` (`parse_case`), and an output's source `system:` or `untrusted:`
  (registration, brief, D29), so nothing a case writes gives one. `trusted_only` refusing it is
  layer 4's, tested there; the note's promise for it leaves the table, as the check can't be shown
  meeting it through the seam.
- **`OPENER_DECIDES` needs a contract taking `only_from("opener")`;** the tests register their
  own, `ledger.record@1`, and the guide's row names it. The warning's proof runs the same case
  twice: opened by a system, the amount is recorded; opened by Ana, it is refused.
- **One pass gave what the run records at once** (slice 1): the first test's code already stamped
  outputs. Seen failing with every output stamped `system:kyc`, then restored.

- **A case step's `only_from` refusal had a plan's advice** (slice 1): `core.validate`'s
  `what_to_do` tells a plan's author to give the input in a case step. A case's check has its
  own: `use a value opener gave`. Found reading the code, fixed test-first.
- **A plan step's check is `validate`'s policy check with the case's sources** (slice 2):
  `core.validate.refused_inputs(plan, catalog, sources)` is the new seam, `validate` unchanged.
  A person opening refuses whatever a system opening does, and more, so the check walks the
  refusals when a person opens it and asks which also hold when a system does. "The plan's own
  mark is the plan's issue" passed at once; seen failing with the marks added back.

- **G7's reference half is checked by the case, not the plan** (slice 3). A plan's field
  arrives as `Sourced(value, sources)`: the plan can't tell a `crm` reference from a text, and
  `decide` doesn't hold the plans (the drivers read them). So `start_plan` says, for each field,
  what it gives (`given_as_reference`, split out of `not_a_reference_to`, which now uses it), on
  `StartPlan.references`; both drivers ask `plan_step.wrong_references` before the plan starts,
  as they ask `supplied`. Validation reads the same function. The type half stays the plan's
  (`refuse_to_start`, slice 4): a value's type is in the value.
- **G7 met an earlier test's fixture** (slice 3): `test_fresh_facts.needing` gave
  `refund-order@1`'s `orders` reference a case field declared as a text. The fixture now declares
  it a reference to orders, as an order ID is; the test's subject (a plan step's outcome isn't
  fetched again) is unchanged.
- **The Temporal comparison passed at once** (slice 3), the driver's check written first; seen
  failing with it removed (the child started).

- **G7's type half met five earlier tests** (slice 4), all in `tests/test_interpreter.py`.
  Three gave a plan's number field an `int` (`sourced(250, …)`), now `Decimal(250)`, as the case
  file holds numbers. One gave a reference field a number to reach the contract's refusal; it now
  writes the number in the plan's input, which still reaches it. Two (one of them the plans
  guide's example) gave the text `"250"` to a number field so a condition couldn't be read; the
  plan now doesn't start. Their subject, a condition that can't be evaluated stops the run, still
  matters for a plan run unchecked, so they declare `amount` a text, which `validate` refuses and
  the runtime meets on its own (learning question 34); the plans guide says so, and lists the
  type among what refuses a run's start. No assertion was loosened.
- **G7 found a bug of its own making** (slice 4): the new branch named its type `declared`, which
  `refuse_to_start` already used for the list of fields, so an undeclared field's message listed
  `type='number'`. Caught by layer 5's test; renamed.
- **A list can't be given to a plan,** as it can't be given at a case's opening: `fits` fails
  closed on a type it doesn't know (a list, for now). No plan in the repository has a list field;
  `INPUT_TYPE` says the same, as a proof. Lists given across the boundary wait for a layer that
  needs them.
- **An `int` input passed at once** (slice 4), its branch written with the first; seen failing
  with `int` read as a number.

- **`APPROVER_CANT_SEE` is one issue per role and value, not per role** (slice 5). One value may
  be seen through either of two roles (`fraud or audit`), and two values may need two different
  roles: one message naming several values could say neither exactly. Its proof runs both ways:
  Lee holding `support-lead` alone is refused; holding `fraud` too, the claim is paid.

- **The Promises check found two claims without a test** (slice 6): "an outcome from its
  contract" (a wrong trusted stamp would pass `trusted_only` unseen, so its test reads an
  outcome where only `only_from("kyc")` tells `system:kyc.check@1` from `system:kyc`), and "or
  whose plan is missing". Both got tests, passing at once; the first was seen failing with
  outcomes stamped by their contract's system. The no-quoted-value promise names the new test it
  is, not the earlier one it said it would extend.
- **One cause, one issue, and the guide's table passed at once** (slice 6): seen failing with the
  policy check made to ignore earlier issues (`REFERENCE` and `INPUT_POLICY` both given), and
  with one word of a row changed.
- **A plan step refused at its start gets no in-plan issue** (slice 6), as the runtime never
  starts the plan: one cause, one issue holds per step for plans, not only per input.

### Not in 10c

- Teaching warnings (10d), among them D9's approval whose condition reads none of its step's
  fields.
- Untrusted values steering a condition (design question 17, layer 11).
- No new dependency.

### From the tutor review

One finding, fixed test-first as agreed with the user.

- **`INPUT_TYPE`'s "which no value of a case ever is" wasn't a proof.** `taken` read only
  `Decimal`, `str` and `bool`, and called every other input type unfillable; but strict Pydantic
  accepts a `Literal` given one of its texts (the probe's `priority: Literal["low", "high"]`
  given `"high"` was refused by the check and run by the engine), a `float` given a decimal
  (which the activity's model then turns into a binary float, against "never converted"), `Any`,
  `str | Decimal` and `list[Decimal]`. Two fixes:
  - **Registration holds inputs to the case's types** (brief, D36, adding to D29): a `Decimal`, a
    `str`, a `bool` or a `Literal` of texts, each possibly optional (`core/contract.py`'s
    `held_input`, used by registration and by the check). Every contract input in the repository
    already fit. The activities guide says what an input may be, and its table of refusals has
    the `float` row. The check's "no value fits" branch can't be reached through a catalog,
    which checks every contract again when registered; it stays an error, worded as such.
  - **The check knows the `Literal`:** an outcome all of whose outcomes are among its texts
    fits; a text field, a reference, or an outcome with others may fit or not, so no issue; a
    text written in the definition outside the set is `INPUT_TYPE` naming it (brief, D35); a
    number or a boolean is `INPUT_TYPE`. Each with its run. The branch naming the text was seen
    failing with it removed; the outcome and boolean rules, tested in a second pass, passed at
    once and were each seen failing on a deliberate break.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`V` is `tests/test_case_validation.py`, `P` `tests/test_plan_step.py`, `T`
`tests/test_temporal_case.py`, `I` `tests/test_interpreter.py`, `C` `tests/test_catalog.py`. Checked against the tests,
2026-10-16: every test named here exists, and every test 10c added is named here.

| Promise | Test |
|---|---|
| A value from a source an input's policy refuses is `INPUT_POLICY`, the guide's message word for word; run, the step fails with the same reason | V `test_an_untrusted_value_is_refused_where_only_trusted_ones_go` |
| One pass gives what the runtime records: a value computed from several fields, an output with its contract's source or `untrusted:undeclared`, an outcome from its contract | V `test_one_pass_gives_the_sources_the_run_records`, `test_an_outcome_comes_from_its_contract_not_its_system` |
| A refusal that depends on who opens the case is a warning, `OPENER_DECIDES`; one that holds for any opener is an error | V `test_who_opens_the_case_decides_only_a_warning` |
| A plan step's fields carry the case's sources into the plan: refused at the case's input before the plan runs; run, the plan stops; the plan's own marks are the plan's issue; a field a wait sets is a person's | V `test_a_plan_step_carries_the_cases_sources_into_its_plan`, `test_a_plans_own_mark_is_the_plans_issue` |
| A reference input given another system's reference, a text or a computed value is `REFERENCE`, in activity and plan steps; run, the step fails, in memory and on Temporal (G7: the made-up order ID is no longer paid) | V `test_a_reference_goes_only_where_its_system_is_expected`, `test_a_plan_steps_reference_field_takes_a_reference_of_its_system`; P `test_a_plan_field_takes_only_a_reference_to_its_system`; T `test_a_plan_field_takes_only_a_reference_of_its_system_on_temporal` |
| An input of another type than it takes is `INPUT_TYPE`; run, it is refused, never converted (G6), in a case and in a plan | V `test_an_input_is_given_the_type_it_takes`; I `test_an_input_is_never_converted` |
| A contract input no value of a case is (an `int`, a `float`) is refused at registration, saying what to use instead | V `test_an_input_no_value_of_a_case_fits_is_refused_at_registration`; C `test_the_guides_refusals_are_what_the_catalog_says` (its `float` row) |
| A `Literal` input takes one of its texts: no issue, and the activity is called; another text is `INPUT_TYPE` naming it, a number is `INPUT_TYPE`, and the run fails each; a text field may fit, so no issue | V `test_a_literal_input_takes_one_of_its_texts` |
| An outcome all of whose outcomes are among a `Literal`'s texts fits, and runs; one with others depends on the answer, so no issue; a boolean is `INPUT_TYPE`, and the run fails | V `test_an_outcome_or_a_boolean_given_to_a_literal_input` |
| A plan's fields are checked against their types when it starts (G7) | I `test_a_plan_field_takes_a_value_of_its_type` |
| A plan field given only literals is `NO_SOURCES`; run, the plan doesn't start | V `test_a_plan_field_given_only_literals_has_no_sources` |
| A sensitive value given to a workflow step is `SENSITIVE_TO_WORKFLOW`; run, the step fails | V `test_a_workflow_step_is_never_given_a_sensitive_value` |
| An approval role that can't see what its step reads is `APPROVER_CANT_SEE`, a warning; run, its holder alone is refused, and a person also holding a role that sees it approves | V `test_an_approver_who_cannot_see_is_warned` |
| One data-flow issue per input, the first the runtime meets; none for an input already refused, or whose contract or plan is missing | V `test_an_input_has_one_data_flow_issue` |
| No message quotes a value: no title, no literal; sources are stand-ins, never who opens the case | V `test_no_data_flow_message_quotes_a_value` |
| The guide says what the code does: its example output and its third table | V `test_the_guide_lists_every_code_for_data_flow`, `test_the_guides_table_of_data_flow_is_what_validate_case_says` |
| `case` imports no Temporal or LLM code, and reads no clock or I/O, in the new module too | `tests/test_layers.py`, unchanged |

---

## 10d. Teaching warnings

User-facing description, written first: `docs/guides/cases.md`, "What the check warns about".
Decision: brief D37 (drafted with this note).

### What this part is for

10a–10c report errors, proven for every case. 10d reports what a definition may mean but that
surprises its author when a case runs. Each warning describes something `run_case` really does
with the same definition; probed 2026-10-16:

| Definition | The runtime today |
|---|---|
| the quickstart, the provider declines | `pay#1 gave declined`, `closed: nothing left to do`: nobody is told |
| the case-data guide's `refund_fresh`, review rejected | `pay#1 failed: pay's approval condition … approved_amount has no value`: needs attention instead of closing |
| `refund_fresh`, the lookup gives `not_found` | `pay#1 failed: pay's condition … check_order.status has no value` |

The last two are a guide example called correct: the third warning found it before it was built.

### Decided in the session

Agreed 2026-10-16, all as proposed.

1. **The codes:** `OUTCOME_UNREAD`, `MAY_BE_UNSET`, `NEVER_REFRESHED`, `APPROVAL_ELSEWHERE`
   (warnings); `SET_AFTER` (an error: the part of `MAY_BE_UNSET` that holds for every case,
   brief, D34). New beside the split's table, which said only "warnings".
2. **An unread outcome is checked one outcome at a time,** on activity steps (each outcome the
   contract declares) and plan steps (`failed`). It is read when a condition can tell it from
   `done`: it compares the step's outcome with it or with `done` (`==`, `!=`, `in`); reading the
   outcome any other way reads them all, so the check never guesses. One issue per step names
   every unread outcome. **Tasks get none:** a `reject` that does nothing is how a "no" is
   written, and the person who chose it knows; D17's surprise is a system's answer nobody hears.
   Workflow steps end only `done`. An unread outcome that leaves an output another step reads is
   said by that step's `MAY_BE_UNSET` instead: then the step fails, and someone hears.
3. **The quickstart changes (choice a):** the refund gains the cases guide's `call_customer`
   (`when pay.outcome == "declined"`, for `support`), and the guide's claim the same (for
   `adjuster`), so neither warns. The quickstart's "closes after the payment, or after a rejected
   review" gains its third case.
4. **How a guard is seen** (design question 14). A value is surely set where a step reads it if
   it is given at the opening (assumed: otherwise every case would warn); or the step waits for
   its writer (its requirements, through the steps it requires and `sequence`) and every way the
   writer ends sets it (a task all of whose outcomes set the field; an activity declaring no
   outcomes, for its outputs; any step, for its outcome); or the step requires a milestone only
   setting completions reach; or a guard says so. The step's `when` is read first (`admit`), so
   what it implies guards the approval's `when` and the inputs: an `and`'s parts, an `if`'s
   condition and branch when its other branch is `false`, an outcome compared `==` or `in` with
   outcomes that set the field, the writer's outcome `== "done"` for its outputs, `exists`.
   Inside one expression only an `if` guards its branch: `and` and `or` evaluate every part on
   purpose (brief, D20), so `{"and": [review approved, approved_amount > 100]}` still fails on a
   rejected review. A read the check can't see guarded warns: a warning errs towards saying.
5. **`SET_AFTER` is an error, kept narrow:** every writer of the value waits for the reading
   step, the read isn't guarded, and the step can't be proposed. Then it fails every time it
   starts, and a retry too: its writers wait for it to be *done*. A step that can be proposed gets
   `MAY_BE_UNSET`: a later run may read the value.
6. **`NEVER_REFRESHED`:** a `max_age` fact from the opening, a person, a `write`, `notify` or
   `compute` activity, a workflow or a plan step, or a read whose step's approval has no `when`
   (a refresh never asks for one, brief, D33). A conditional approval or a `when` depends on
   data: no warning. A warning, not an error: the step needs attention only when the fact is
   stale, which depends on time.
7. **`APPROVAL_ELSEWHERE`:** an approval with a `when` that reads none of the fields its step's
   inputs read (brief, D9). An approval with no `when` guards everything.
8. **No runtime change.** The warnings describe what the runtime does; `refund_fresh` is fixed in
   the guide (`pay`'s `when` guarded with an `if`), and its tests read it from there. No new
   dependency. D37, drafted with this note.

### The checks

| Code | At | Given when | The runtime |
|---|---|---|---|
| `OUTCOME_UNREAD` (warning) | `steps.<s>` | an activity's declared outcome, or a plan step's `failed`, that no condition tells from `done` | the step is done with it, reaches nothing, and the case goes on; with nothing else to do it closes |
| `MAY_BE_UNSET` (warning) | `steps.<s>.when`, `.approval.when`, `.inputs.<i>`: where it is first read, in the runtime's order | a value read that isn't surely set there | reading a value nobody set fails the step: it needs attention |
| `SET_AFTER` | the same | every writer waits for the step, unguarded, and the step can't be proposed | the step fails every time it starts |
| `NEVER_REFRESHED` (warning) | `steps.<s>.max_age.<f>` | the fact can never be fetched again | when stale, the step needs attention (`refresh_stale`) |
| `APPROVAL_ELSEWHERE` (warning) | `steps.<s>.approval.when` | the approval's `when` reads none of the fields the step's inputs read | the approval isn't asked when the neighbouring value is low, whatever the step sends |

One value read in several places of a step gets one issue. A step already refused by an error
gets no 10d issue, nor does a value whose writer has one: one cause, one issue. No message quotes
a value from a case file, nor a literal of the definition (no literal is ever the mistake here);
they name steps, fields, outcomes and effects (brief, D35).

### Where the code goes

- `case/warnings.py` (new): what surely sets a value, and 10d's checks, one function per code.
- `case/validate.py`: adds them, after every error, skipping steps and values an error names.
- Tests: `tests/test_case_validation.py`; the quickstart's `call_customer` in `test_quickstart.py`.
- Examples: `examples/refund/refund.json`, the quickstart, the cases guide's refund and claim, the
  case-data guide's `refund_fresh`.

### Seams the tests use

- `parse_case`, then `validate_case(case, catalog, plans=…)`; an issue's `path`, `code`,
  `message`, `severity`.
- `run_case(…)` for each warning's surprise, on the same definition.
- The guides: their examples give the issues shown, their table is what `validate_case` says, and
  every example definition in the repository and the guides is run through `validate_case`.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The examples.** The quickstart and the guide's claim gain `call_customer`; fixtures built
   from the refund that replace `pay` leave it out; `refund_fresh` guarded; the guide's deadlock
   output names `call_customer`. Negative: the quickstart's declined refund now calls the
   customer instead of closing.
1. **`OUTCOME_UNREAD`.** Negative: the quickstart without `call_customer`, and its run closing with
   nobody told. Then one outcome at a time, `!=` and `in`, `done`, a plan's `failed`, no task.
2. **`MAY_BE_UNSET`.** Negative: `pay` without its `when`, and the run failing. Then each way a
   value is surely set, `and` that doesn't guard, an output whose writer may end otherwise, a
   writer not waited for; the old `refund_fresh` gives two, its runs fail.
3. **`SET_AFTER`.** Negative: `notify` before `pay`, failing every time; proposed, a warning.
4. **`NEVER_REFRESHED`.** Negative: `max_age` on `approved_amount`, and the run needing attention;
   then each source, and the read behind an approval.
5. **`APPROVAL_ELSEWHERE`.** Negative: the approval on `amount`, and 5000 paid unasked.
6. **One cause, one issue; every example; the guide and the promises.**

### Decided while building

- **Slice 0's negative test was seen failing on the old refund** (written after the docs, which
  had already changed `refund.json`): with the old file the declined refund closed, `waiting_for`
  empty; with the new one it waits for `call_customer by support`.
- **Fixtures built from the refund that replace `pay` with a plan step leave `call_customer`
  out** (`test_plan_step`, `test_temporal_case`, `test_case_validation`'s `settled`): they test
  plan mechanics. The guide's plan step is an example, so `call_customer` moves with it, said in
  the guide's prose (its blocks are found by position): it requires `settle` and runs when
  `settle.outcome` is `failed`.
- **The claim's `call_customer` is a real extra issue wherever `pay` can never run:** 10a's
  tests now expect its `NEVER_RUNS` (`call_customer can never run: it requires pay, which can
  never run: fix pay first`), and the guide's deadlock output shows it. No message changed.
- **The guarded `refund_fresh` changes the approval sheet:** it lists every fact the approval
  depends on, and `pay`'s `when` now reads `check_order.outcome` and `review.outcome` too, so
  two lines more. Right: Sam approves on those facts as well.
- **On Temporal the declined refund now waits for `call_customer`,** so its test answers it,
  after waiting for the entry (an answer sent before the decline lands names no open entry).

### Not in 10d

- A guard the check doesn't recognise is warned about, never proven (data decides).
- Rules and timers (layer 11), `ventoux check` (layer 14).
- No runtime change, no new dependency.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`V` is `tests/test_case_validation.py`, `Q` `tests/test_quickstart.py`. Drafted with the note; each
test is named as it is written, and the table checked against the tests before the pull request.

| Promise | Test |
|---|---|
| The quickstart and the guides' examples give no 10d issue; the quickstart's declined refund calls the customer | to be named in slice 0 and 6 |
| A declared outcome no condition tells from `done` is `OUTCOME_UNREAD`; run, the case closes with nobody told | slice 1 |
| Outcomes are checked one at a time; `==`, `!=` and `in` with the outcome or `done` read it; a plan's `failed` too; a task's never | slice 1 |
| A value read before it is surely set is `MAY_BE_UNSET`; run, the step fails | slice 2 |
| Requirements, milestones, the `when`, `if` and `exists` guard; `and` and `or` don't | slice 2 |
| A value only a later step sets, read unguarded by a step that can't be proposed, is `SET_AFTER`; run, it fails every time; proposed, it is a warning | slice 3 |
| A `max_age` on a fact that can't be fetched again is `NEVER_REFRESHED`; run stale, the step needs attention; a read behind an unconditional approval too | slice 4 |
| An approval reading none of its step's input fields is `APPROVAL_ELSEWHERE`; run, the neighbouring value lets a large refund through unasked | slice 5 |
| One cause, one issue: no 10d issue beside an error on the step or the value's writer; one per value per step | slice 6 |
| No message quotes a value or a literal | slice 6 |
| The guide says what the code does: its outputs and its table | slice 6 |
| `case` imports no Temporal or LLM code, and reads no clock or I/O | `tests/test_layers.py`, unchanged |
