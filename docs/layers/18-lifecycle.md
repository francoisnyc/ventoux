# Layer 18: Case lifecycle: required steps, repeated steps, child cases

Status: 2026-11-05, choices A to C and 1 to 11 agreed; 18a's seams agreed; 18a slices 1 and 2
built and reviewed; choice 12 proposed (from the tutor's review). This note starts from `main` at `f1e8512`, with
layers 0 to 17 merged. The warm-up was asked and recorded (learning question 37). The guide was
written first (curriculum step 2): `docs/guides/cases.md`, "Required steps", "Repeated steps: one
run per item" and "Child cases", describes the layer as if it worked. Writing it showed four places
where my first picks were wrong; the recommendations below correct them, and the guide changes
with the answers (listed at the end).

**Answered 2026-11-04.** Choices A to C and 1 to 11 as recommended. D72 is written before 18a is
built, with dated amendments under D10, D24 and D52. Choices 12 to 28 stay sketches, settled when
their parts start; the guide's 18b to 18d sections change with them then.

Prior art: `chartering/src/temporal/case-workflow.ts`. Each admitted fragment runs as a child
workflow named `<case ID>/<fragment>-<n>`, the counter carried across continue-as-new. A promise
per child resolves once Temporal says it started, and every signal to a child awaits it first
("never signal a child before it exists"). A close is parked while any child runs. The case
continues as new only when no child is running. Ventoux takes the naming and the "signal only once
started" rule. It differs on the last two points: a child case may run for weeks, so its parent
can't wait for it to continue as new (D27, as amended by D48). Instead the child reports its end
by a signal to the parent's workflow ID. And a close stops children through D40's one place
instead of waiting for them in a queue.

## Warm-up: learning question 37, what the audit keeps after forgetting

Recorded in `docs/LEARNING.md`, entry 37. Asked to be told. It leads into 18d: a child case given
a sensitive value must be under a key that forgetting the parent reaches (D15, D32).

## What this layer is for

**"Nothing left to do" has only ever meant "nothing under way".** Pending work (D10) is what has
started and not ended: a running step, an open entry, a set timer, a failed run. Work that should
happen but hasn't started keeps nothing open. So a case whose last obligation is proposed by a
person closes the moment everything else ends, with that obligation never done. Neither
`closes_when` (it only closes early) nor `stays_open` (it never closes by itself) says "this must
be done before the case may close by itself". A **required** step says it.

**A step run once per item** of a list in the case file. The design turns on naming. A run's name
is in its idempotency key (D17, D27), so it must never shift when the list is reordered or grows.
And it is in every history line, which never quotes a value (D30), so it can't be the item's value
either.

**A child case** is a whole case started from a step: its own case file, release, people and
lifecycle. When it ends it reports to its parent, by a signal, so the parent need not wait for it
to continue as new. Everything the parent's lifecycle does (close, stop, migrate, continue as new,
forget) must say what it does to a running child. And whatever a child says on its way back is a
value with sources, never a write into the parent.

## The split

| PR | What it builds | Its negative test |
|---|---|---|
| **18a: required steps** | `required` on a step; "nothing left to do" counting it; `waiting_for` listing what is owed; `closes_when` held by it; a skip of its failed run refused; `ventoux check`'s proof that each can be done; the diff, the case map, the builder. | **curriculum:** a required step that no rule or person can ever start is refused at validation. Also: `required` with a `when`; a skip of a required step's failed run. |
| **18b: repeated steps** | `for_each` on an activity or task step; one run per item, numbered by the engine, matched by its key; `each.<field>`; `requires` over all runs; what an edit of the list does to open runs; migration renames. | **curriculum:** a step repeated over a field that isn't a list is refused. Also: a key that isn't a text field of the items; a list whose items repeat a key fails the step at runtime. |
| **18c: child cases, in the engine** | `kind: "case"`; the child's opening from the parent's file, with sources; its end report as the step's outputs; close and stop reaching the child through D40's one place; the in-memory run. | **curriculum:** a child case of a definition not active (here: not supplied) is refused before it starts. Also: a child case whose definition has a case step of its own; inputs that aren't the child's opening fields. |
| **18d: child cases on Temporal** | The child as a workflow `<case ID>/<entry>`, signalled only once started; its end reported by a signal to the parent's workflow ID; the parent continuing as new while it runs; the registry asked before it starts; the shared key; forgetting. | **curriculum:** a child of a release not active in the environment is refused before it starts. Also: an end report for an entry that isn't a running child is recorded and ignored. |

**Why this order.** 18a changes only what "done" means, and every later part leans on it (a
required repeated step, a required child). 18b adds a new shape of run but no new kind of step.
Child cases are the largest part, and Temporal brings risks of its own (parent close policy,
continue-as-new, signals), so they are split: 18c settles the meaning in the deterministic engine,
where every route can be tested quickly, and 18d puts it on Temporal. As in layer 17, the choices
for 18b to 18d are sketched here and settled when their parts start.

### Where each point of the curriculum's layer 18 lands

1. **Required work, and what "nothing left to do" means then:** 18a, choices 1 to 11.
2. **A step run once per item, each run given its item:** 18b, choices 13 to 20.
3. **A child case, with its own file, release and lifecycle:** 18c and 18d, choices 21 to 29.
4. **How its parent hears that it ended (a signal, D27 and D48):** 18d, choices 27 and 28.

## Design questions for you

Each answer becomes a decision in the brief, from D72 on, added and never rewriting an earlier one.
A correction to a merged decision is a dated amendment under it.

### For the whole layer

A. **The split:** 18a, 18b, 18c, 18d, as in the table, one pull request each. Branches
   `layer-18a-required`, `layer-18b-repeated`, `layer-18c-child-cases`, `layer-18d-child-temporal`.
   The warm-up, the guide and this note sit on `layer-18a-lifecycle`, which I'd rename to
   `layer-18a-required`. *Alternative:* three parts, child cases in one. *Recommended: four.*

B. **Decisions: one per part,** D72 (18a), D73 (18b), D74 (18c), D75 (18d), each written before its
   part is built and saying what it adds to which earlier decisions. Amendments go under D10, D24,
   D27, D37, D40, D48 and D52 where they change what those say. *Recommended.*

C. **No new dependency.** *Recommended.*

### For 18a: required steps

1. **What makes a step required.** `"required": true`, on a step of any kind (task, activity,
   workflow, wait, plan; a child case in 18c). Left out of the definition's digest when false, as
   `cancellable` is, so every existing release keeps its digest. *Recommended.*

2. **What "done" means for it.** Its **latest** run is `done`, with any outcome: a declined
   refund, a task answered `reject`, a plan's `failed`. That is how `requires` reads a step already,
   and a business failure is an outcome someone handles (D17), not undone work. *Alternative:*
   name the outcomes that count. *Recommended:* any outcome. A stricter "done well" is a
   `closes_when` milestone.

3. **A required step with a `when`.**
   - (a) **Refused.** A required step is owed in every case. A step owed only sometimes is started
     by a rule, or proposed, and isn't required. Fails closed, and the meaning stays one sentence.
   - (b) "Owed once its condition holds". But a condition read false never becomes true by itself,
     so the case would have to decide when to stop waiting.

   *Recommended: (a).* Refused at validation: `steps.confirm: a required step is owed in every
   case, so it has no when: start it from a rule, or drop required`.

4. **A run that ended without being done** (stopped by a rule, D40, `cancelled`; its approval
   rejected, `rejected`): the step is owed still, and the case waits for another run. An automatic
   step starts itself at most once (D40), so another run comes only from a proposal or a rule.
   *Recommended.*

5. **A failed run** needs attention as before (D17): retried, or the case closed with a reason. A
   **skip** (D52) of a required step's failed run:
   - (a) **refused**, saying so: `confirm is required, so its run is never skipped: retry it, or
     close the case with a reason`. The obligation ends only by doing it, or by a person closing
     the case, who takes responsibility for it.
   - (b) allowed, the skip discharging the requirement, since two people agreed.

   *Recommended: (a).* A skip leaves the case going on as if the run were not needed. A required
   step is exactly one that is. A close with a reason still ends it, explicitly.

6. **`closes_when` with a required step not done.**
   - (a) **The close is held,** as by a failed run (D26). Nothing new starts but the owed step, and
     the case closes once it is done.
   - (b) `closes_when` wins, and its last line says `confirm not done`.
   - (c) Validation proves the milestones are reached only after the required steps are done.

   *Recommended: (a).* `closes_when` means "close early", and a requirement means "not before
   this". The stricter one wins. (c) is a proof we can't always make.

7. **A person's close** is never held: declared reasons work as ever (D10). The last line names
   what was owed: `closed: duplicate, by ana; confirm not done`. A close by forgetting (D32) the
   same. *Recommended.*

8. **What the case says while it owes** (adds to D24). `waiting_for` lists each owed step not
   running, after the open entries, saying who can start it:
   - proposed: `confirm, required, proposed by support`;
   - started only by a rule: `confirm, required, started by a rule`;
   - waiting for a requirement: `confirm, required, after review` (shown only once nothing
     else is pending, since before then the case isn't waiting on it).

   *Alternative:* a separate `owed` list, as `timers` is apart. *Recommended:* in `waiting_for`.
   It is work waiting on people, which is what D24 lists, and a case that waits must say on what.

9. **What `ventoux check` proves** (D34, D37: only what holds for every case is an error).
   - **Error:** a required step that can never start, from `can_happen` (layer 10's fixpoint):
     nothing can ever start it in any case. `REQUIRED_NEVER_STARTS`. *Corrected while choosing
     the seams, agreed 2026-11-04: this is `NEVER_RUNS`, as for any step that can never run, one
     cause, one issue.*
   - **Error:** `required` with `when` (choice 3).
   - **Warning, not an error:** a required step that a rule may stop, or whose approval may reject,
     and that could then never run again (not repeatable, or nobody proposes it and no rule starts
     it). The rule may never fire, so this doesn't hold for every case. `REQUIRED_MAY_STRAND`,
     shown with its run. *Correcting the guide, which says "refused".*

   *Recommended.*

10. **The diff, the case map, the builder, the schema.** Turning `required` on is **stricter** (the
    case does more before it closes by itself), off **looser**, as `automatic` and `repeatable` are
    read (13b). The case map's closing line says it: "closes when nothing is left to do and confirm
    is done". The builder takes `required=True`. The JSON Schema follows from Pydantic. *Recommended:
    all in 18a*, since a key the diff doesn't know would be a change it can't classify.

11. **Engine version: none new** (D51). A history recorded before has no definition with
    `required`, so every recorded path decides as before. Confirmed by replaying a 17c history.
    *Recommended.*

12. **An owed step that can no longer start** (from the tutor's review of 18a at `9739039`).
    The guide's refund with `confirm` requiring `pay`: Ana approves 250, Sam rejects `pay`'s
    approval. `pay` isn't repeatable, so it never runs again, and `confirm` can never start. Yet
    today `waiting_for` says `confirm, required, proposed by support`, `needs_attention` is empty,
    validation says nothing, and the proposal is refused (`confirm requires pay, which hasn't
    completed`). Choice 6(a) builds the same trap: with `closes_when` reached, "nothing new starts
    but the owed step", so an owed step whose requirement hasn't run never starts.
    - (a) **It needs attention, naming why;** only a person's close ends it. An owed step needs
      attention when nothing can start it again: it can't start itself (an automatic step starts
      at most once), nobody may propose it again and no rule starts it; or a step it requires
      ended without completing and can't run again, by the same test; or, under a held close, a
      requirement isn't met, since nothing else starts. The line: `confirm: required, and it can't
      start: confirm requires pay, which hasn't completed: close the case with a reason`,
      `ended_requirement`'s words with the way out. It leaves `waiting_for`, as a failed run is in
      `needs_attention` and not `waiting_for` (D24). `REQUIRED_MAY_STRAND` also warns about a
      required step whose requirement may end and can't run again, and one whose requirements
      may be unmet when every `closes_when` milestone is reached.
    - (b) **Under a held close, the owed step's unmet requirements start too.** It frees the held
      close, but it starts work no rule or person asked for (a payment, with its side effect),
      against "nothing new starts" (D10), and it can't help a requirement that ended and can't run
      again, which still needs (a).

    *Recommended: (a).* It fails closed: a case that can't finish its obligation says so to a
    person, and nothing starts that nobody asked for. A requirement that can still run (`pay`
    repeatable and proposed) isn't stranded: the case waits, saying `confirm, required, after
    pay`. This also settles what the line says when nothing can start the step again, the
    question left open after slice 2.

**Routes for 18a**, each handled or refused with a test, checked before its pull request:

| Route | What it does to "owed" |
|---|---|
| an answer | completes a task run: done, owed no more |
| an edit (D52) | can't change `required` (not a value); a skip of a required run is refused (choice 5) |
| a migration (D53) | the target's `required` applies; owed is worked out from the definition and the runs, never stored, so a rename of the step needs nothing more; a test proves it |
| an event | completes a wait step's run |
| a rule | `stop` makes it owed again; `start` may run it |
| the opening | a step required that nothing can start is refused at validation, before any case opens |
| a plan | a plan step may be required; the plan's own steps can't be |
| a close or a stop (D40) | a person's close is never held (choice 7); a stop makes it owed again (choice 4) |
| a retry (D26) | a retry that completes makes it done |
| continue-as-new | nothing new is stored, so nothing new crosses |

### For 18b: repeated steps (sketched; settled when it starts)

13. **The shape:** `"for_each": {"over": "<list field>", "key": "<text field of its items>"}`, on
    an activity or a task step. Not a plan, workflow or wait step, nor a child case, in this layer
    (deliberate limit, D48). *Recommended.*

14. **How runs are named.**
    - (a) by position: `refund_line#1`, `#2`. An edit that adds a line in front gives position 1
      to another line, and a retry sends one line's idempotency key with another's amount.
      **Ruled out.**
    - (b) by the key's value: `refund_line[A12]#1`. Stable, but the name is in every history line
      and workflow ID, which never quote a value (D30), and the key may be sensitive or untrusted.
    - (c) **by an item number the engine gives each key the first time it sees it:**
      `refund_line.1#1`, `refund_line.2#1`. Items are matched by their key, so reordering changes no
      number. A removed key's number is never given again. The numbers are state, carried across
      continue-as-new, and quote nothing.

    *Recommended: (c).* *Correcting the guide, which uses (b).* A key must be a non-sensitive text
    field, and a list whose items repeat a key or lack one fails the step, which needs attention.

15. **How a run reads its item:** `{"var": "each.amount"}`. Not `item`, which `sum` and `count`
    already use for their own element. A repeated step whose expression sums another list would
    then have two meanings for one word. `each` becomes a reserved name, refused for a step,
    field, milestone or event. *Correcting the guide.* *Recommended.*

16. **Provenance:** an item's values carry the list field's sources (D12). A list a customer typed
    is untrusted in every run. *Recommended.*

17. **Reading a repeated step from outside it.** `requires: ["refund_line"]` is met when every
    item's latest run is done, and at once for an empty list (the history says so). `refund_line.outcome`
    and its outputs are refused at validation: several runs have no one outcome. Reading how many
    were declined would need an operator, which is a decision of its own (D20), not made here.
    *Recommended.*

18. **A required repeated step** owes a done run for every item in the list now. *Recommended.*

19. **When the list changes**, by every route:
    - **an edit (D52):** an added key starts its run (automatic) or can be proposed. A removed
      key's open run is stopped, as a rule's stop is (D40); a running one finishes, flagged. A
      changed item (same key, other values): an open task entry is withdrawn and asked again, as
      any entry whose values changed (D25); a running activity finishes on what it started with; a
      done run stays done, and its step may be proposed again if repeatable.
    - **a rule:** never sets a list (D42, D48), and stays refused.
    - **a migration (D53):** renames of the step, the list field and the key field are followed,
      and the item numbers move with the step's name. 17c's review found state keyed by a step's
      name that didn't follow a rename, so this gets its own test.
    - **the opening:** the list's items get numbers in order.
    - **continue-as-new:** the numbers cross with the runs.

    *Recommended.* Each gets a test.

20. **A bound:** a decision starts at most one run per item, so the list's length bounds it (D39).
    A list over a limit the platform team sets fails the step, needing attention. *Recommended*,
    with the limit settled in 18b.

### For 18c and 18d: child cases (sketched; settled when they start)

21. **The shape:** `{"kind": "case", "case": "repair@3", "inputs": {...}}`. A child case is named
    with its release, as a plan is (`refund-order@1`). It may be required. It has no approval of
    its own: the child's own steps carry theirs, as a plan's do (D28). *Recommended.*

22. **Which release the child runs** (D51, D54).
    - (a) **pinned by the parent's release:** `repair@3` is in the parent's package, so in its
      digest. Activating the parent checks `repair 3` is active in the environment. The child asks
      the registry as it opens, as any case does. A retired or deactivated release refuses it
      before it starts, and the step fails, needing attention.
    - (b) the release of `repair` active when the child starts. The parent's behaviour would then
      change without a release of its own.

    *Recommended: (a).* What a release does is what it says. A new garage process is released by
    releasing the claim too, and the diff shows it. *Correcting the guide, which says (b).* In
    memory, `run_case` is given the child definitions by name and number.

23. **What the child is given.** Its opening fields, from the parent's case file, each with its
    sources (D28): a budget a person approved is still that person's in the child. The parent's
    exclusions cross: the parent's opener, and the step's proposer, approve nothing in the child
    (D25, D28). The child is **opened by the parent case**, recorded as such, never by a person.
    Validation checks each input is a field the child's definition takes at the opening, of its
    type. *Recommended.*

24. **Sensitive values and keys** (D15, D31, D32).
    - (a) **The child is under its parent's key.** The codec already takes a case's key from its
      workflow ID's first part (`case_of("claim-7/repair#1") == "claim-7"`). Sensitive inputs
      cross sealed, never opened. Forgetting the parent forgets its children with the same act. A
      child can't be forgotten alone (the request is refused, naming the parent). The stricter
      `forgetting` of the two applies to both: a child that keeps its records keeps the family's.
    - (b) Its own key. Every sensitive input is opened and sealed again in the codec. Forgetting
      must then find and destroy every child's key, and a missed child keeps the person.

    *Recommended: (a).* It is one subject, so one key. And the forgetting can't miss a child.
    *Correcting the guide.*

25. **What the end report may carry** (adds to D29). How the child closed (`done`, or the reason a
    person closed it with), the milestones it reached, and the fields its definition declares in
    `reports`. Each value carries the sources it had in the child, never re-stamped, plus
    `case:repair` naming where it came from. A sensitive field stays sealed under the shared key.
    The values land as the step's outputs (`repair.cost`), never in the parent's own fields: the
    parent reads them as it reads any output. A report carries nothing else. *Recommended.*

26. **A child that needs attention** is the child's: retried by its operators, there. The parent's
    step is running, and the parent waits. A failure to **start** the child (definition not active,
    inputs refused) is the parent's step failing, retried by the parent's operator. The retry
    starts the child under the same ID, and refuses to start a second child if one of that ID has
    run. *Recommended.*

27. **What the parent's lifecycle does to running children:**
    - **closes, or a rule stops the step:** through D40's one place, the child is closed with a
      reason naming its parent (`closed by its parent: duplicate, by ana`). Its tasks are
      cancelled, its activities finish, and the parent waits for it to end. A close never waits
      for a person (D48). Signalled only once started (the prototype's rule).
    - **migrates:** the child keeps its own release. The parent's target must start the same
      `repair@3` from that step, or the migration waits for the child (D53, "running work
      finishes under what it started with").
    - **continues as new:** doesn't wait for the child (adds to D27, closing D48's note). The
      child's end signal is addressed to the workflow ID, so it reaches the latest run. To verify on
      Temporal's test server: a child started with the default parent close policy is terminated
      when its parent's run continues as new, so children are started with `ABANDON`, and the
      parent stops them itself.
    - **is forgotten:** choice 24.

    *Recommended.*

28. **The end signal:** carries the entry, the child's workflow ID and its report. One for an entry
    that isn't a running child of this case, or sent twice, is recorded and changes nothing. It is
    sent by the child's own workflow as its last act, never by a client. *Recommended.*

29. **One level only** (deliberate limit, adds to D48): a child case's definition has no case step
    of its own, refused when the parent is validated. That bounds what one close must reach, and
    rules out a case starting itself. *Recommended.*

### What changes in the guide, if answered as recommended

- "Required steps": the "a rule can stop confirm" check becomes a warning (choice 9).
- "Repeated steps": runs named `refund_line.1#1` (choice 14); items read as `each.amount` (choice
  15); "with no items, at once" stays.
- "Child cases": `"case": "repair@3"`, pinned (choice 22); the child under its parent's key, and
  forgetting refused for a child alone (choice 24); the report's sources gain `case:repair`
  (choice 25).

## Seams and tests for 18a (curriculum step 4)

The tests use only what a caller of the engine uses today: the definition as JSON, the script
`run_case` plays, what a run and a report say, `validate_case`, the diff, the case map, the
builder and the published schema. No test reads how "owed" is worked out.

### The seams

1. **One key in the definition:** `"required": true` on any step, read by `parse_case`. A
   required step with `when` is refused when read, as any malformed definition is.
2. **`run_case` and what it reports:** `waiting_for`, `closed`, `status`, `history`. The script
   steps that exist are enough: `propose`, `retry`, `skip`, `close`, `forget`, `edit`, `migrate`,
   `send`, `later`, `finish`. **No new event, script step or signal.**
3. **On Temporal:** `CaseReport.waiting_for` and `CaseReport.closed`, as today.
4. **`validate_case(case, catalog)`:** the issues it returns, by code and message.
5. **`diff(before, after, catalog)`:** the change at `steps.<name>.required` and its verdict.
6. **`case_map(package, catalog)`:** its closing line.
7. **The builder:** `required=True` on each step method, giving the same JSON as written by hand.
8. **The published schema** (`ventoux schema`) and **`digest`:** an existing release's digest is
   unchanged.

**Found while choosing the seams.** The curriculum's negative test ("a required step that no rule
or person can ever start is refused at validation") is already an error for *every* step:
`NEVER_RUNS`, from layer 10's fixpoint. So once the key is read, that test passes with no new
check. I'd keep `NEVER_RUNS` as its only issue (one cause, one issue) and drop the
`REQUIRED_NEVER_STARTS` code D72 names (D72 is not merged, so it is corrected in this pull
request, under "Decided while building"). The test is still written first, and it fails today
for a different reason: `required` is an unknown key (`Extra inputs are not permitted`). I'll
show that failure, then the one line that reads the key, then the test passing on `NEVER_RUNS`.

### The refusals and lines, word for word (proposed)

| Situation | What is said |
|---|---|
| `required` with `when`, when read | `steps.confirm: a required step is owed in every case, so it has no when: start it from a rule, or drop required` |
| a skip of a required step's failed run, proposed or approved | `confirm is required, so its run is never skipped: retry it, or close the case with a reason` |
| owed, proposed by a role | `waiting_for`: `confirm, required, proposed by support` |
| owed, started only by a rule | `waiting_for`: `confirm, required, started by a rule` |
| owed, its requirements not met, nothing else pending | `waiting_for`: `confirm, required, after review` |
| a person's close with something owed | last line: `closed: duplicate, by ana; confirm not done` |
| `closes_when` held by an owed step, a proposal of another | `paid is reached, so the case closes once confirm is done, or a person closes it: nothing new starts but confirm` |
| the warning `REQUIRED_MAY_STRAND` | `steps.confirm: a rule may stop confirm, and it is required, so it might never run again: make it repeatable and proposed_by a role, or start it from a rule` (and `its approval may be rejected` in place of the rule, for that case) |

### The tests, in the order I'd write them

Each one written failing first, and watched failing for the right reason. Each responds to what
the last one taught, so the list may change on the way.

1. **(negative, curriculum)** A required step that nothing can ever start is refused at
   validation, `NEVER_RUNS`. Fails first on the unknown key, as said above.
2. **(negative)** `required` with `when` is refused when read.
3. The guide's example, run as written: a rejected refund stays open, `waiting_for ==
   ["confirm, required, proposed by support"]`; proposed and answered, it closes.
4. Done with any outcome: a required `pay` that is declined meets its requirement.
5. **(negative)** A run a rule stopped leaves the step owed; so does a rejected approval.
6. **(negative)** A skip of a required step's failed run is refused, at the proposal and at the
   approval; the retry that completes closes the case.
7. `closes_when` held by an owed step: a proposal of another step refused; the owed step still
   starts; the case closes once it is done.
8. A person's close is never held, and names what was owed; a close by forgetting too.
9. `waiting_for`'s other two forms: started by a rule; after its requirements.
10. **(warning)** `REQUIRED_MAY_STRAND`, for a stop and for an approval; none when the step is
    repeatable and proposed.
11. The diff: on is stricter, off is looser. The case map's line. The builder's JSON. The schema
    has the key. A recorded release's digest is unchanged.
12. A migration renaming a required step: still owed under its new name, done if its run was. A
    migration whose target makes a done step required: nothing owed.
13. **On Temporal:** `CaseReport.waiting_for` lists the owed step; it crosses continue-as-new.
14. **Replay:** every recorded history in `tests/histories` still replays, which is what "no new
    engine version" claims.

**The routes, each handled or refused, with its test:** an answer (3), an edit (6: the skip is a
change request; an edit of a field changes nothing owed, asserted in 3's variant), a migration
(12), an event (a required wait step completed by its event, in 9), a rule (5, 9), the opening (1,
2), a plan (4, with a plan step's `failed`), a close or a stop (5, 8), a retry (6),
continue-as-new (13).

## Decided while building 18a (so far)

- **`NEVER_RUNS` is the curriculum's refusal** (choice 9, corrected): its path is
  `steps.confirm.requires`, where the requirement nothing reaches is.
- **The builder came with slice 1,** not at test 11: a guard refuses a key no example writes. The
  example is `examples/builder/required.py`, in the builder guide; its test passed first time, the
  guard being the test that failed.
- **A new pinned package, `tests/digests/required`,** writes `required` on every kind of step;
  every digest pinned before is unchanged, which is the promise that an existing release keeps its
  digest.
- **The guide's blocks are read by position,** so "Required steps" sits at the end of the cases
  guide, and the 18b and 18c sections wait below until their parts. 17c's tests read their block
  from their own section, so a section added after it moves nothing.
- **A skip's check reads the step directly:** a guard "if the step is known" would have let a
  skip through for an unknown step, a permissive default; a migration never leaves a run without
  its step.
- **Every reader takes `owed.waiting_for`** (from the tutor's review): the in-memory run, the story's
  end (which counts what is owed as pending, so it never says "nothing pending" of a case that
  owes), the advisor's view, and Temporal's report. `waiting_at` keeps only the open entries' names:
  an owed step, listed after them, has no entry yet.
- **Pins added from the tutor's review,** each watched catching its mutation: only the latest run
  counts (a done run run again and stopped is owed again); an owed step with its run open is said
  once; a skip proposed before its step became required (release 1 to 2) isn't applied, at the
  approval.

## Guide drafts for 18b and 18c, kept here until their parts are built

Written in step 2 as if they worked. The guide's examples are run by its tests, so these sections
can't sit in the guide before their parts exist; each moves back when its part starts, corrected
by its answers (see "What changes in the guide, if answered as recommended").

> ## Repeated steps: one run per item
>
> A **repeated step** runs once for each item of a list in the case file, each run given its item.
> Here an order is refunded line by line:
>
> ```json
> "fields": {
>   "lines": {"type": "list", "display": {"title": "Order lines"},
>             "fields": {"sku": {"type": "string"}, "amount": {"type": "number"}}}
> },
> "steps": {
>   "refund_line": {
>     "kind": "activity",
>     "display": {"title": "Refund one line"},
>     "activity": "payments.refund@2",
>     "for_each": {"over": "lines", "key": "sku"},
>     "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "item.amount"}}
>   }
> }
> ```
>
> `item` is the run's own item, read as `item.<field>`, as `sum` and `count` read theirs. Each run
> is named by its item's **key**, the field `key` names: `refund_line[A12]#1`, `refund_line[B7]#1`.
> The name goes into the run's idempotency key (brief, D17), so reordering the list, or adding a
> line in front, never gives a payment another line's key. A list whose items repeat a key, or lack
> one, fails the step, which needs attention: nothing guesses which line is which.
>
> ```python
> lines = [{"sku": "A12", "amount": 40}, {"sku": "B7", "amount": 25}]
> run = run_case(order_refund, file={"order_id": "ord-1", "lines": lines}, answers=[],
>                people=PEOPLE)
> assert run.history[:2] == [
>     "started refund_line[A12]#1: payments.refund@2 (amount from system:opener, order_id from system:opener)",
>     "started refund_line[B7]#1: payments.refund@2 (amount from system:opener, order_id from system:opener)",
> ]
> ```
>
> An item's values come from the list they are in, with its sources: a list a customer typed is
> still untrusted in each run.
>
> - **`requires: ["refund_line"]`** is met once every item's run is done; with no items, at once.
>   `refund_line.outcome` isn't read: with several runs, there is no one outcome.
> - **A required repeated step** owes a done run for each item.
> - **When the list changes,** by an edit (see "Changing an open case"): an added item starts its
>   run; a removed item's open run is stopped, as a rule's stop would stop it, and a running one
>   finishes, flagged; an item whose values changed keeps a done run done, and its open run is
>   stopped and starts again with its new values. A rule never sets a list.
> - `ventoux check` refuses `for_each` over a field that isn't a list: `steps.refund_line.for_each:
>   order_id is a reference, not a list: a step repeats over a list field`, and a key that isn't a
>   text field of the list's items.
>
> ## Child cases
>
> A **child case** is a whole case started from a step of another: its own case file, release,
> people and lifecycle, and when it ends, a report to its parent. Use one where work has a life of
> its own: a claim sends the vehicle to a garage, whose repair is assigned, chased and closed by
> other people, over weeks.
>
> ```json
> "repair": {
>   "kind": "case",
>   "display": {"title": "Repair the vehicle"},
>   "case": "repair",
>   "requires": ["assess"],
>   "inputs": {"vehicle": {"var": "vehicle"}, "budget": {"var": "approved_amount"}}
> }
> ```
>
> Its `inputs` are the child's opening, read from the parent's case file with their sources, as a
> plan step's are (brief, D28): a budget a person approved is still that person's in the child. A
> sensitive value is given encrypted under the child's own key, never in plain text, and the child
> lists who may see it as its own definition says.
>
> **Which release.** The child opens on the release of `repair` active in the parent's environment,
> asked of the environment's registry before it starts (the releases guide, "A case in an
> environment"). A definition not active there is refused before anything starts, and the step
> needs attention: `repair#1 failed: repair has no active release in production: activate one, then
> retry repair#1`.
>
> **What the parent hears.** The child runs as its own workflow, `claim-7/repair#1`, and the parent
> waits for it, as for any running step. When it closes, it reports to the parent by a signal: how
> it closed, the milestones it reached, and the fields its definition declares in `reports`, each
> with the sources it had in the child. The step is then done, and the parent reads
> `repair.outcome` (`done`, or the reason a person closed it with) and `repair.cost`:
>
> ```
> started repair#1: case repair 3 (budget from person:ana, vehicle from system:opener), run claim-7/repair#1
> repair#1 done: repair closed, nothing left to do, giving cost from person:garage-lee
> ```
>
> - **A child that needs attention** is the child's: its operators retry it there. The parent waits.
> - **When the parent closes, or a rule stops the step,** the child is closed too, saying why
>   (`closed by its parent: duplicate, by ana`): its tasks are cancelled, its running activities
>   finish, and the parent closes once the child has ended. A close never waits for a person.
> - **A parent that continues as new** doesn't wait for its children: their report reaches it by
>   its workflow ID.
> - **A parent that migrates** leaves its children on their own release.
> - **Forgetting the parent** forgets each child too, under one request; a child whose definition
>   keeps its records (`"forgetting": "never"`) refuses it.
