# Layer 10: case validation

Status: the split into four parts and 10a's six choices agreed in the session, 2026-10-15 (all as
proposed); 10a's note drafted the same day.

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
- **`closes_when` is checked before admission** (8b), so once all its milestones are reached the
  case is closing and nothing starts: a step requiring all of them can never run.

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
    could start: remove paid from its requires, or from closes_when`;
  - `recheck can never run: it starts only when proposed, and none of its proposed_by roles
    (supprt) is registered: name a registered role`.
- **`CLOSES_AT_OPENING`** (error), at `steps`: the case doesn't stay open, and no step starts by
  itself with nothing required. When it opens nothing is pending, so it closes at once and every
  proposal is refused. Every step is then dead for that one reason, so this is the only issue
  given (one cause, one issue).
- **`NEVER_CLOSES`** (error), at `close_reasons`: the case stays open, and no close reason names
  a registered role, so nobody could ever close it. (`stays_open` with no close reason at all is
  already refused by `parse_case`.)
- **`CLOSE_UNREACHABLE`** (warning), at `closes_when`: a milestone it names isn't in `can`. A
  warning, as D10 asks: the case still closes when nothing is left to do.
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
3. **Closing.** Negative: a step requiring every `closes_when` milestone; a case where nothing
   starts by itself (`CLOSES_AT_OPENING`, and nothing else); a case that stays open with no close
   reason naming a registered role; a proposed step none of whose roles is registered.
4. **Warnings.** Negative: an unreachable `closes_when` milestone, a milestone nothing reaches,
   each a warning; neither given for a milestone already named by another issue.
5. **The runtime on its own.** The deadlocked claim, run without validation, closes with nothing
   left to do and pays nothing; no runtime test changes.
6. **The guide and the promises:** the guide's examples and table run as written; this table
   checked against the tests.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`V` is `tests/test_case_validation.py`. Test names are planned; the table is checked against the
tests before the pull request.

| Promise | Test |
|---|---|
| `validate_case` refuses anything but a parsed definition, never returning "no issues" | V `test_only_a_parsed_case_is_validated` |
| An issue that says no severity is an error | V `test_an_issue_is_an_error_unless_it_says_otherwise` |
| A sound case has no issues: the guide's claim, the quickstart's refund | V `test_the_guides_claim_has_no_issues`, `test_the_quickstart_refund_has_no_issues` |
| The order steps are written in changes nothing (the fixpoint, not one pass) | V `test_the_order_of_the_steps_does_not_matter` |
| A step requiring a milestone nothing reaches never runs | V `test_a_step_requiring_what_nothing_reaches_never_runs` |
| Steps that wait on each other are one `DEADLOCK`, naming the circle, with no other issue for them; the guide's message word for word | V `test_the_deadlocked_claim_is_refused`, `test_a_step_requiring_itself_is_deadlocked`, `test_sequence_and_requires_can_deadlock` |
| A step waiting on a dead step never runs, saying which | V `test_a_step_waiting_on_a_deadlock_never_runs` |
| A step requiring every `closes_when` milestone never runs | V `test_a_step_after_the_close_never_runs` |
| A case where nothing starts by itself is refused once, with nothing else | V `test_a_case_that_closes_at_opening_is_refused` |
| A case that stays open must be closable by a registered role | V `test_a_case_nobody_can_close_is_refused` |
| A step only roles nobody registered may propose never runs | V `test_a_step_nobody_may_propose_never_runs` |
| An unreachable `closes_when` milestone and a milestone nothing reaches are warnings, never repeated beside another issue | V `test_an_unreachable_close_is_a_warning`, `test_a_milestone_nothing_reaches_is_a_warning` |
| No message quotes a value | V `test_no_message_quotes_a_value` |
| The runtime depends on nothing validation did: the deadlocked claim runs and closes, paying nothing | V `test_an_unchecked_deadlock_still_runs_safely`; every runtime test, unchanged |
| The guide says what the code does: its claims and its table | V `test_the_guides_claim_has_no_issues`, `test_the_deadlocked_claim_is_refused`, `test_the_guides_table_is_what_validate_case_says` |
| `case` imports no Temporal or LLM code, in the new modules too | `tests/test_layers.py`, unchanged |
