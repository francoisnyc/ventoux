# Layer 18: Case lifecycle: required steps, repeated steps, child cases

Status: 2026-11-07, 18a to 18c merged (#86, #87, #88: D72, D73, D74); 18d, child cases on
Temporal (D75), next. This note starts from `main` at `f1e8512`, with layers 0 to 17 merged. The warm-up was asked and recorded
(learning question 37). The guide was written first (curriculum step 2): `docs/guides/cases.md`,
"Required steps", "Repeated steps: one run per item" and "Child cases", describes the layer as if it
worked. Writing it showed four places where my first picks were wrong; the recommendations below
correct them, and the guide changes with the answers (listed at the end).

**Answered 2026-11-04.** Choices A to C and 1 to 11 as recommended. D72 is written before 18a is
built, with dated amendments under D10, D24 and D52. Choices 13 to 29 (numbered 12 to 28 until
choice 12 was added) stay sketches, settled when their parts start; the guide's 18b to 18d sections
change with them then.

**Answered 2026-11-05.** Choice 10 is corrected to (a): the diff reads `required` as not
proven either way. Choice 12 is (a), with its two readings. D72 says so, in place, since it
isn't merged.

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
    case does more before it closes by itself), off **looser**, the reverse of `automatic` and
    `repeatable`, which turned on are looser (13b; corrected 2026-11-05, from the tutor's review).
    The case map's closing line says it: "closes when nothing is left to do and confirm is done".
    The builder takes `required=True`. The JSON Schema follows from Pydantic. *Recommended: all in
    18a*, since a key the diff doesn't know would be a change it can't classify.

    **Corrected 2026-11-05, from the tutor's review of #86: answered (a).** D55 says
    stricter means the new version lets through strictly less, whatever a case holds. Turned on,
    `required` also takes what the other version refuses:
    - after the review is rejected, `propose("confirm", "ana")` is taken when `confirm` is
      required, and refused when it isn't (`the case is closed: nothing starts`);
    - under a held close, the owed step starts after every `closes_when` milestone is reached,
      where the other version starts nothing.

    So neither direction is a proof. Layer 13 judged `closes_when` and `stays_open` not proven for
    the same reason (`docs/layers/13-diff.md`, choice 27: closing is neither a permission nor its
    absence).
    - (a) **Not proven, both ways,** with a witness for each direction: a run each version takes
      and the other refuses. The diff says the change and leaves the verdict to a person, as for
      `closes_when`; D72's bullet changes in place, since D72 isn't merged; "required" leaves the
      closed list of comparisons.
    - (b) Keep stricter on, looser off, as built.

    *Recommended (the tutor's, and mine): (a).* A verdict is a proof for every case (D55), and
    this one fails on the run above. *Answered 2026-11-05: (a).* D72's bullet is changed in
    place.

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
      Two readings, settled 2026-11-05 from the tutor's review:
      - **"No rule starts it" is proven from the definition, never guessed** (D37): no rule in the
        definition starts the step. A rule whose moment has passed still counts, so the case says
        `confirm, required, started by a rule`: optimistic, but a person can close it. The other
        reading (guessing that a rule will never fire) could send a case to attention while a
        rule could still start the step.
      - **Under a held close, "a requirement isn't met" reads "isn't met, and nothing is on its
        way to meet it"**, as `ended_requirement` reads it: a requirement open, running, failed or
        retried is on its way, and the owed step waits for it. Tested: `closes_when` reached
        with `review` still open; the case closes once `review` and `confirm` are done.
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

### For 18b: repeated steps (answered 2026-11-05: as recommended; D73)

**What 18b is for.** One step, a run per item of a list in the case file, each run given its item.
Writing the guide and reading the code showed three things the sketch didn't say: no case can hold
a list value today (the type check fails closed on lists, so the opening refuses one); a high-risk
contract needs an approval on its step, and the case keeps one open approval per step, never per
run; and a proposal or a rule's start names a step, never an item. So 18b decides how a list value
is given, and keeps a repeated step simple: it starts by itself, a run per item, with no approval.

13. **The shape:** `"for_each": {"over": "<list field>", "key": "<text field of its items>"}`, on
    an activity or a task step. Not a plan, workflow or wait step, nor a child case, in this layer
    (deliberate limit, D48). *Recommended.*

14. **How runs are named:** (c), by an item number the engine gives each key the first time it
    sees it: `refund_line.1#1`. Items are matched by key, named by number, so reordering changes no
    number, a removed key's number is never given again, and no name quotes a value (D30). The
    key-to-number map is state, per step: it crosses continue-as-new and follows a migration's
    renames of the step. A key must be a non-sensitive text field present and distinct in every
    item; otherwise the step fails, needing attention. *Recommended* (unchanged from the sketch).

15. **How a run reads its item:** `{"var": "each.<field>"}`; `each` is reserved, refused as the
    name of a field, step, milestone or event, and refused outside a repeated step's `inputs`
    and its task's outcomes' readers (it has no item there). *Recommended.*

16. **Provenance:** every value of an item carries the list field's sources (D12). *Recommended.*

17. **Reading a repeated step from outside it:** `requires` met when every item's latest run is
    done, at once for an empty list, the history saying so; its `outcome` and outputs refused at
    validation. *Recommended.*

18. **A required repeated step** owes a done run for every item (D72). *Recommended.*

19. **When the list changes**, by every route: the opening gives it (items numbered in order); a
    rule never sets it and an event never carries it (D41, D42, D48, unchanged); a migration renames
    the step and the list field, the numbers moving with the step; continue-as-new carries the
    numbers. An edit: choice 31. *Recommended.*

20. **A bound:** a list holds at most 100 items, refused at the opening above that, saying the
    limit: so one decision starts at most 100 runs of a step (D39). A fixed number in the engine,
    a deliberate limit (D48); a definition or platform setting would be a later decision.
    *Recommended.*

30. **A list value, checked where it is given.** A list is a JSON array of records; each record
    has exactly the list's declared fields, each of its exact type, as any field's value is
    checked (numbers exact, never floats; D20). Anything else is refused, naming the type, never
    the value (D30). Given only at the opening in 18b. *Alternative:* also in a person's form
    answer; not needed by anything in 18b. *Recommended:* the opening only.

31. **An edit of a list a step repeats over (D52).**
    - (a) Allowed: an added key starts its run; a removed key's open run is stopped as a rule's
      stop would be, a running activity finishing, flagged; a changed item keeps a done run done
      and re-asks an open task. Useful, but each of these is a route with its own tests.
    - (b) **Refused, saying so:** `lines is the list refund_line repeats over, so it is never
      edited: close the case and open it again with the list corrected`. A list no step repeats
      over may be edited as any field. A deliberate limit (D48); (a) stays a door.

    *Recommended: (b).* It keeps 18b's routes few, and nothing in this layer needs (a).

32. **Approvals: a repeated step has none in 18b.** A high-risk contract needs an approval (D11),
    so it can't be repeated: `ventoux check` says so (`payments.refund@2 is high risk, and
    refund_line is repeated, so it can have no approval: repeat a low-risk step, or pay once`).
    *Alternative:* an approval per run, which changes the case's open approvals from one per step
    to one per run, and with it what D25, D47, D69 to D71 key by step: a part of its own. The
    guide's example then repeats a task and a low-risk draft, not the payment. *Recommended:* none
    in 18b, a deliberate limit (D48).

33. **How a repeated step starts:** by itself, once admitted, a run for each item that has none.
    Not `proposed_by`, not `repeatable`, and no rule starts it: a proposal or a start names a step,
    never an item, so each is refused at validation, saying so. A rule may stop it: every open run
    of it is stopped (D40). An operator retries a failed run by its entry (`refund_line.1#1`, D26).
    *Recommended.*

34. **No new engine version (D51):** no definition readable before holds `for_each`, and no case
    could hold a list value. *Recommended.*

**One part, one pull request (18b),** in slices: the list value at the opening; the shape and its
validation; the runs, named and given their items; reading from outside and required; the routes
(edit refused, migration, stop, retry, continue-as-new); the diff, the case map, the builder.

### Seams and tests for 18b (curriculum step 4, proposed)

The tests use only what a caller uses today; no test reads how the item numbers are stored.

1. **The definition:** `for_each` on a task or activity step, read by `parse_case`; what can't
   be repeated is refused when read (`CaseInvalid`).
2. **The opening:** `run_case(..., file={..., "lines": [...]})`, a list given as data; a list
   that doesn't fit is refused (`CaseRefused`).
3. **The runs, in what a run reports:** `history` (`scheduled draft_line.1#1: …, key
   memory/draft_line.1#1`), `waiting_for` (an open repeated task reads `inspect_line.1 by
   support`: its number, never its value), `needs_attention`, `closed`. An answer names its entry:
   `("inspect_line.1#1", "received", "ana")`; a retry, `retry("draft_line.1#1", "omar")`.
4. **`validate_case`:** the issues, by code and message.
5. **An edit:** `edit("lines", …)` refused with `ChangeRefused`.
6. **On Temporal:** `CaseReport`, and a case continuing as new with repeated runs open.
7. **The diff, the case map, the builder, the schema,** as in 18a.

**The refusals and lines, word for word:**

| Situation | What is said |
|---|---|
| `for_each` over a field that isn't a list | `steps.draft_line.for_each: order_id is a reference, not a list: a step repeats over a list field` |
| a key that isn't a text field of the items | `steps.draft_line.for_each: amount is not a text field of lines: a key is a text field every item has` |
| a repeated plan, workflow or wait step | `steps.settle: a plan step is never repeated: repeat a task or an activity` |
| a repeated step proposed, repeatable, or started by a rule | `steps.draft_line: a repeated step starts by itself, a run per item: drop proposed_by` (`repeatable`; `the rule start_letters starts it`) |
| an approval on a repeated step | `steps.draft_line.approval: a repeated step has no approval yet` |
| a high-risk contract repeated (`ventoux check`, error) | `payments.refund@2 is high risk, and refund_line is repeated, so it can have no approval: repeat a low-risk step, or pay once` |
| `each` read outside a repeated step | `steps.notify.inputs.amount: each is read only in a repeated step` |
| `each` as a name | `fields.each: each is the name a repeated step reads its item by: name it otherwise` |
| a repeated step's outcome or output read elsewhere | `steps.notify.when: inspect_line.outcome: a repeated step has no one outcome` |
| the opening gives a list that doesn't fit | `lines is a list of records with sku (a text) and amount (a number), and the opening gives …` (the type, never the value), and `lines holds at most 100 items, and the opening gives 101` |
| items repeat a key, or lack one (the step fails) | `draft_line can't run: two items of lines have the same sku: each item's key is its own` (`an item of lines has no sku`) |
| an edit of a list a step repeats over | `lines is the list draft_line repeats over, so it is never edited: close the case and open it again with the list corrected` |
| an empty list | `draft_line: lines has no items, so it has no runs` |

**The tests, in the order I'd write them,** each failing first (the negative first):

1. **(negative, curriculum)** `for_each` over a field that isn't a list is refused when read.
2. **(negative)** The list value at the opening: wrong shapes, wrong types, over 100, all refused.
3. The guide's example, run as written: two drafts, numbered, their keys.
4. Reordering the list at a later opening gives the same names; an added key gets the next number.
5. **(negative)** The other shapes refused when read: key, kinds, proposals, repeatable, rule
   starts, approval, `each` misread or misnamed, outcome read; the high-risk error at the check.
6. A repeated task: entries numbered, answered by entry, `waiting_for` naming numbers.
7. `requires` over a repeated step, an empty list, a required repeated step owing each item.
8. **(negative)** Items that repeat or lack a key fail the step.
9. Provenance: an untrusted list makes each item untrusted; a trusted-only input refuses it.
10. The routes: an edit refused; a rule's stop stops every open run; a retry by entry; a
    migration renaming the step keeps the numbers; continue-as-new on Temporal; replay.
11. The diff, the case map, the builder, the schema, the digest pin.

### Choice 35: a repeated step's `when` on an untrusted list (from the tutor's review of #87)

D48: untrusted data may keep something from happening, but never silently. A repeated step's `when`
reads its item, and its item carries the list's sources. With `lines` from `untrusted:customer` and
`draft_line` drafted only `when each.amount > 30`, neither the check nor the close says anything
today: `KEPT_FROM_STARTING` finds no source for `each.amount`, and the close's line skips a step
that has any run, and can't read `each`.

- (a) **Say it.** The check reads `each.<field>` as its list (as `as_listed` already does for input
  policies), so `KEPT_FROM_STARTING` warns. The close names each item kept, by number, never by
  value: `draft_line.2 not started: its condition reads each.amount, from untrusted:customer, and
  is false`.
- (b) **Refuse it,** a deliberate limit (D48): a repeated step's `when` that reads `each` over a
  list declared untrusted is refused when read, saying so.

*Answered 2026-11-06: (a).* *Recommended: (a).* A condition per line is the guide's own example, a
list a customer typed is the common case, and (a) is what D48 already asks of every other step; most
of the work exists (`as_listed`, `say_kept_from_starting`).

### Decided while building 18b

- **The list value comes first:** no case could hold a list, so `fits` learned one, and the
  in-memory run passes a list's whole numbers on as exact decimals, as the API does.
- **Agreed while building:** a form never sets a list and a list is never sensitive (slice 1);
  `reaches`, `sets`, `max_age` and `assign` refused on a repeated step (slice 3).
- **A plan, workflow or wait step with `for_each`** gets the format's usual `not a field here`,
  not a message of its own: those kinds have no such field.
- **`order_id is a reference to orders, not a list`:** the type said as `a_type` says it, more
  precise than the wording proposed.
- **Test 4 (reordering) is moot:** within a case the list never changes; its promise, that a run
  keeps its name and key, is the retry test's.
- **A repeated run's outcome and outputs aren't written under its step's name;** nothing reads
  them (they are refused), and each run would overwrite the last.
- **Done is asked in one place, `step_done`:** the requirement check and what is owed ask it; for
  a repeated step, every item's latest run is done, and the step's numbers say which items.
- **Two bugs found by the tests and fixed:** an edit of a list crashed while reading it as one
  value; validation crashed (`KeyError: 'each.amount'`) when an item reached a contract's input.
  Validation now reads `each.<field>` as its list for provenance, per step.
- **A step whose items share a key isn't retried:** the list never changes.
- **From the tutor's review of #87:** a migration whose target repeats a numbered step over
  another list, by another key, or not at all, is refused (`renumbered`, in `depending`): every
  item would run again under new idempotency keys. And `owing.py` reads a repeated step per item:
  on its way while any item's latest run is under way; stranded only when an item's latest run
  ended undone, since an item's run starts at most once.
- **The numbers are always written when the state crosses continue-as-new,** so the guard that
  every field of the state crosses covers them. A Temporal run can't tell a lost map (the same
  list renumbers the same way), so a read-back test pins it.

## Promises (18b)

Each claim the note, D73 and the guide's "Repeated steps" make, and the test that would fail if it
weren't true. Tests without a file are in `tests/test_repeated.py`. Each was watched failing first
or, for a pin of behaviour already built, catching a mutation.

| Promise | Test |
|---|---|
| A step repeated over a field that isn't a list is refused when read (the curriculum's negative test) | `test_a_step_repeated_over_a_field_that_isnt_a_list_is_refused` |
| A list fits when it holds at most 100 records, each with exactly the declared fields of their types; anything else is refused at the opening, naming the shape and the kind, never a value | `test_a_list_that_fits_is_given_at_the_opening`, `test_a_list_that_doesnt_fit_is_refused_at_the_opening` (six cases) |
| What can't be repeated is refused when read: a key that isn't a text field; proposed, repeatable, not automatic or started by a rule; an approval; `each` misread or used as a name; a repeated step's outcome read; a form setting a list; a sensitive list | `test_what_cant_be_repeated_is_refused_when_read` (eleven cases) |
| A plan, workflow or wait step has no `for_each` | `test_a_plan_workflow_or_wait_step_has_no_for_each` |
| What assumes one run per step is refused on a repeated one: reaches, sets, max_age, assign | `test_what_a_repeated_step_cant_do_yet_is_refused` (five cases) |
| A run per item, named by its key's number, keyed by that name; an open task reads its number, never its value | `test_each_item_gets_its_run_named_by_its_keys_number`, the guide's example in `test_case.py::test_the_guides_examples_run_as_written` |
| A repeated task is answered by its entry, and its outcome isn't written under its step's name | `test_a_repeated_task_is_answered_by_its_entry_and_sets_nothing_under_its_name` |
| Validation and the runtime read `each.<field>` with its item's types | `test_validation_reads_each_with_its_items_types` |
| A repeated step's `when` is read for each run with its item | `test_a_repeated_steps_condition_is_read_for_each_run_with_its_item` |
| On an untrusted list, a repeated step's `when` keeping a run from starting is never silent: the check warns, the close names each item kept by number (choice 35) | `test_the_check_warns_that_an_untrusted_item_may_keep_a_run_from_starting`, `test_the_close_says_each_item_an_untrusted_condition_kept_from_starting` |
| `requires` over a repeated step waits for every item; an empty list meets it at once, saying so | `test_requires_over_a_repeated_step_waits_for_every_item`, `test_an_empty_list_meets_a_requirement_at_once_and_says_so` |
| A required repeated step owes every item | `test_a_required_repeated_step_owes_every_item` |
| A required repeated step is read per item: on its way while any item's run is; stranded only when an item's run ended undone | `test_a_required_repeated_step_with_an_item_to_retry_isnt_stranded`, `test_a_required_repeated_step_with_an_item_open_isnt_stranded`, `test_a_required_repeated_step_with_an_item_stopped_is_stranded` |
| A migration never renumbers a repeated step's items: a target with another list or key is refused once the step has numbers | `test_a_migration_changing_a_repeated_steps_key_once_it_has_numbers_is_refused` |
| Items that share a key fail the step, and its retry is refused | `test_items_that_share_a_key_fail_the_step`, `test_a_step_whose_items_share_a_key_isnt_retried` |
| Each item carries the list's sources, at run time and at the check | `test_each_item_carries_the_lists_sources`, `test_the_check_reads_an_items_sources_as_its_lists` |
| A repeated high-risk contract is an error at the check, saying why | `test_a_repeated_high_risk_contract_is_an_error_at_the_check` |
| The diff reads a step made repeated as not proven | `test_the_diff_reads_a_step_made_repeated_as_not_proven` |
| The case map says a step runs once per item | `test_the_case_map_says_a_step_runs_once_per_item` |
| The builder writes `ForEach`, the same JSON | `test_the_builder_writes_the_guides_returned_order`, `test_builder_coverage.py` |
| The JSON Schema has the key; no earlier digest changes; a pinned package writes it | `test_schema.py::test_the_committed_schemas_are_what_the_models_say`, `test_digests.py` (the `repeated` package) |
| No new engine version: every recorded history replays | the replay tests over `tests/histories` |

## Routes checked before the pull request (18b)

| Route | What it does | Test |
|---|---|---|
| an answer | completes one item's task run, by its entry | `test_a_repeated_task_is_answered_by_its_entry_and_sets_nothing_under_its_name` |
| an edit (D52) | of a list a step repeats over, refused | `test_an_edit_of_a_list_a_step_repeats_over_is_refused` |
| a migration (D53) | renames the step's numbers with its runs; an open run keeps its entry and number; a target changing a numbered step's list or key is refused | `test_a_migration_renaming_a_repeated_step_keeps_its_items`, `test_a_migration_changing_a_repeated_steps_key_once_it_has_numbers_is_refused` |
| an event | never carries a list (D41, unchanged) | `test_events.py::test_an_event_carries_no_list` |
| a rule | never starts a repeated step, never sets a list; its stop stops every open run | `test_what_cant_be_repeated_is_refused_when_read`, `test_set.py::test_a_list_field_is_never_set`, `test_a_rules_stop_stops_every_open_run_of_a_repeated_step` |
| the opening | gives the list, checked; the items numbered in order | the two opening tests, `test_each_item_gets_its_run_named_by_its_keys_number` |
| a plan | a plan step is never repeated | `test_a_plan_workflow_or_wait_step_has_no_for_each` |
| a close or a stop (D40) | a close cancels each open run as any; a stop stops every open run; a person's close names what was owed | `test_a_required_repeated_step_owes_every_item`, the stop test |
| a retry (D26) | by entry, the same run with its key, per item; refused for items sharing a key | `test_a_failed_run_is_retried_by_its_entry_with_its_own_key`, `test_a_step_whose_items_share_a_key_isnt_retried` |
| continue-as-new | each run's number and each step's numbers cross | `test_a_repeated_cases_state_reads_back_as_it_was`, `test_a_repeated_steps_items_cross_continue_as_new` |

**State keyed by a step's name:** each repeated step's key-to-number map. It follows a migration's
rename, tested; it crosses continue-as-new, tested.

### For 18c and 18d: child cases (18c's answered 2026-11-07: as recommended; D74. 18d's sketched)

Checked against the code before asking, as 18b's were. What the code already gives:

- **The opening check:** `runtime.py` refuses an opening field that a person's form or a rule
  sets, or of the wrong type. A child's inputs are an opening, so the same check judges them.
- **A plan's inputs:** `calls.py`'s `plan_input_issues` checks each plan step's inputs against
  the fields the plan takes at its start. A case step's inputs are checked the same way, against
  the child's opening.
- **The package:** `releases.py` reads `case.json` and `plans/`, nothing else (D50). A pinned
  child needs a place in it.
- **Close reasons are declared** (`close_reasons`), so the values `repair.outcome` may take are
  known when the parent is validated: `done`, or one of the child's reasons.
- **`waiting_for`** lists open entries (D24); a running plan step adds none of its own waits.
- **The codec** takes a case's key from its workflow ID's first part (`case_of`), so a child
  `claim-7/repair#1` is already sealed under `claim-7`'s key: 18d's choice 24.

**The split.** 18c is the engine, in memory: the step's shape, the package, validation, opening
the child, its report, every parent route, the diff, the case map, the builder, the schema and the
digest. 18d is Temporal: the child as its own workflow, its end signal, its parent close policy,
the registry asked for its release, the shared key, forgetting and continue-as-new. 18c's in-memory
child stands in for all of that the way `plan_runner` stands in for a plan's child workflow.
*Recommended.*

#### 18c: in the engine

21. **The shape:** `{"kind": "case", "case": "repair@3", "inputs": {...}}`, named with its
    release, as a plan is (`refund-order@1`). It takes what a plan step takes (`requires`, `when`,
    `required`, `reaches`, `proposed_by`, `repeatable`, `max_age`) and, like one, no `approval`
    (the child's own steps carry theirs, D28) and no `for_each` (a deliberate limit, D48: one child
    per run). A repeatable case step proposed again opens a second child, `repair#2`.
    *Recommended.*

22. **Which release the child runs** (D51, D54).
    - (a) **Pinned by the parent's release:** the parent's package names `repair@3`, and its digest
      covers what `repair 3` does. Activating the parent checks `repair 3` is active in the
      environment; the child asks the registry again as it opens, as any case does (18d).
    - (b) The release of `repair` active when the child opens. The parent's behaviour would then
      change without a release of its own, and its diff could never show it.

    *Recommended: (a).* What a release does is what it says, and a new garage process reaches
    claims by a claim release the diff shows. In memory, `run_case` is given the child definitions
    by name and release (`cases=`), as it is given plans.

36. **Where the pinned child sits in the package** (adds to D50).
    - (a) **`cases/repair@3/`, the child's own package** (its `case.json` and `plans/`), read as
      the parent's is. The parent's digest covers the child's. Validation reads the child from
      there. Activating the parent checks that the environment's `repair 3` has that same digest,
      so the copy can't say something the released `repair 3` doesn't.
    - (b) Only the reference; validation and the digest read `repair 3` from the release store.
      Then `ventoux check` needs the store, and a package isn't checkable on its own.

    *Recommended: (a),* as plans are: one folder is the whole of what a release does. A child
    named twice, a child nobody names, or a child folder that isn't a package is refused.

23. **What the child is given.** Its opening fields, from the parent's case file, each with its
    sources (D28): a budget an adjuster set is still `person:ana` in the child. The child is
    **opened by the parent case**, recorded as such (`opened by claim-7`), never by a person, so
    nobody is "the opener" of the child. The parent's exclusions cross: the parent's opener and the
    step's proposer approve nothing in the child (D25, D28). Validation checks each input against
    the child's opening, as `plan_input_issues` checks a plan's: a field the child has, given at
    its opening (not set by its forms or rules), of its type. A field the child takes and the step
    doesn't give is simply not given, as at any opening. *Recommended.*

37. **Sensitive values, in the engine** (D15, D31; the keys are 18d's, choice 24).
    - (a) **A sensitive value enters the child only into a sensitive field, and a report carries
      no sensitive field, for now** (deliberate limits, D48). A view can hide more than its source,
      never less: a sensitive parent value given to a plain child field would be shown to anyone
      who reads the child. Refused at validation, saying which.
    - (b) Let them cross both ways, each marked sensitive where it lands.

    *Recommended: (a).* Inputs are where the risk is now; a sensitive report is its own door.

25. **What the end report carries** (adds to D29). The child's definition declares `reports`: a
    list of its own fields, each non-sensitive (choice 37) and not a list (an output is an exact
    value, D29). When the child closes, the step is done; `repair.outcome` is `done` or the close
    reason a person used, and each reported field present at the close lands as `repair.<field>`.
    Each value keeps the sources it had in the child, plus `case:repair`, saying where it came from.
    Nothing lands in the parent's own fields; the parent reads the report as it reads any output.
    `repair.outcome` is type-checked against `done` and the child's close reasons. *Recommended.*

38. **A reported field the child never set.**
    - (a) **It is absent in the parent:** whatever reads it fails, as reading any missing field
      does (fail closed). The history line names the fields that came back. `ventoux check` warns
      where a reader of `repair.cost` can run with the child closed by a reason that may leave it
      unset, as it warns `MAY_BE_UNSET` elsewhere.
    - (b) The step fails, needing attention. But the child is closed, so no retry could help, and
      only a person's close would end it.

    *Recommended: (a).* A repair closed as a duplicate has no cost; the parent branches on
    `repair.outcome` before reading it.

39. **The milestones the child reached** are said in the step's history line (`reaching fixed`),
    never readable by the parent: a list value would be a new kind of read, and a child can report
    any fact the parent needs as a field. A deliberate limit (D48). *Recommended.*

40. **What the parent waits for while the child runs** (adds to D24). The parent's `waiting_for`
    has one line for the running child: `repair#1: case repair, open`. The child's own tasks and
    approvals are the child's, listed in its own report: the people who may see the parent may not
    see the child (D22, D30). A child is pending work, so the parent never closes under it by
    itself. *Recommended.*

26. **A child that needs attention** is the child's: its operators retry it there, and the parent
    waits. A failure to **start** it (a release not active, inputs refused at its opening) is the
    parent's step failing, retried by the parent's operator, under the same entry; a retry never
    opens a second child once one has opened. *Recommended.*

27. **What the parent's routes do to a running child** (in memory; Temporal's half is 18d's):
    - **closes, or a rule stops the step:** through D40's one place, the child is closed, saying
      why (`closed by its parent: duplicate, by ana`; `closed by its parent: stopped by
      withdraw#1`). Its tasks and approvals are cancelled, its running activities finish, and the
      parent closes once the child has ended. A close never waits for a person (D48). The child's
      report then changes nothing in the parent.
    - **migrates:** the child keeps its release. The target must start the same `repair@3` from the
      step (renamed or not), or the migration waits for the child to end (D53). The record of which
      child each run opened follows a rename of the step.
    - **edits a field given to the child** (D52): the child keeps what it was given; an edit never
      reaches a child.
    - **skips:** only a step that failed to start, as any failed run.
    - **events and rules:** reach the parent only; a rule may start a case step or stop it.

    *Recommended.*

29. **One level only** (deliberate limit, adds to D48): a child's definition has no case step of
    its own, refused when the parent is validated. That bounds what one close must reach, and rules
    out a case starting itself. *Recommended.*

41. **No new engine version** (D51): no definition readable before has a case step. *Recommended.*

#### 18d: on Temporal (sketched; settled when 18d starts)

24. **The child is under its parent's key.** The codec already takes a case's key from its
    workflow ID's first part. Sensitive inputs cross sealed. Forgetting the parent forgets its
    children with the same act. A child can't be forgotten alone (refused, naming the parent). The
    stricter `forgetting` of the two applies to both.

27, Temporal's half. **Continue-as-new** doesn't wait for a child (adds to D27, closing D48's
    note): its end comes by a signal to the parent's workflow ID. Children are started with
    `ABANDON` (to verify: the default close policy terminates a child when its parent's run
    continues as new), and the parent closes them itself.

28. **The end signal** carries the entry, the child's workflow ID and its report. One for an entry
    that isn't a running child of this case, or sent twice, is recorded and changes nothing. It is
    sent by the child's workflow as its last act, never by a client.

### Seams and tests for 18c (curriculum step 4, proposed)

The tests use only what a caller uses today, plus three additions (`cases`, `case_answers`,
`CaseRun.children`). No test reads how a running child is stored.

1. **The definition:** a step `{"kind": "case", "case": "repair@3", "inputs": {...}}`, and a
   case's `"reports": [...]`, read by `parse_case`. What a case step can't be (`approval`,
   `for_each`) is refused when read (`CaseInvalid`).
2. **`run_case(..., cases=, case_answers=)`:**
   - `cases` gives the child definitions as stored data, by reference (`{"repair@3": repair}`),
     as `plans` gives plans. A child's plan steps find their plans in the same `plans`. The name
     before `@` must be the child's `case`; the number is the release's, checked at activation
     (18d), so in memory it is only a name.
   - `case_answers` gives each child its own script, by step or by entry (`"repair"`, or
     `"repair#2"` for a repeatable step's second child), in the same form as `answers`: answers,
     `retry`, `close`, `finish` and the rest. A child plays its script when it opens, to its end or
     its first unanswered entry, as a plan step's runner does.
   - People, the catalog, the fakes and the clock are the parent's.
3. **What a run reports:** the parent's `history`, `waiting_for` (`repair#1: case repair, open`),
   `needs_attention`, `closed`; and **`CaseRun.children`**, each child's own `CaseRun` by entry
   (`run.children["repair#1"].history`), so a test reads what the child did without its internals.
4. **`validate_case(case, catalog, plans=..., cases=...)`:** the issues, by code and message. No
   cases means none: a case step's child is then missing (fail closed), as a plan's is.
5. **The package:** `read_package` reads `cases/<reference>/` as a package; `Package.cases` holds
   each child's `Package`, by reference. The digest covers them.
6. **A change request:** `edit` and `skip` and `migrate`, as today; refused with `ChangeRefused`.
7. **The diff, the case map, the builder (`case.child_case(...)`, and `reports=` on `Case`), the
   schema, the digest pin,** as in 18a and 18b.

**The refusals and lines, word for word (proposed):**

| Situation | What is said |
|---|---|
| a child case named but not supplied (`validate_case`, error `UNKNOWN_CASE`) | `steps.repair.case: repair@3 isn't supplied: add it to the package's cases/` |
| the reference's name isn't the child's, or it can't be read | `steps.repair.case: repair@3 is supplied as garage-repair: supply the case it names` (`repair@3 can't be read: display: required`), as for a plan |
| an input the child doesn't take at its opening (`UNKNOWN_INPUT`) | `steps.repair.inputs.cost: repair@3 takes no input cost: its task fix sets it; its inputs are budget, vehicle` (`its rule size_up sets it`; `repair@3 has no input mileage: …`), as for a plan |
| an input of another type (`INPUT_TYPE`) | `steps.repair.inputs.budget: repair@3 takes budget as a number, and is given a string: give it a number`, as for a plan |
| a sensitive value into a plain field (`SENSITIVE_TO_CHILD`) | `steps.repair.inputs.owner: owner is sensitive, and repair@3's owner isn't: a child keeps a sensitive value sensitive` |
| an approval on a case step (when read) | `steps.repair: a case step has no approval: its child's steps ask for their own` |
| `for_each` on a case step (when read) | `steps.repair.for_each: not a field here` (18b's line for a plan step) |
| a child with a case step of its own (`NESTED_CASE`) | `steps.repair.case: repair@3 has a case step, order_parts: a child case opens no case of its own` |
| `reports` naming a field the case lacks (when read) | `reports.cost: repair has no field cost: a report lists the case's own fields` |
| a sensitive or list field reported (when read) | `reports.owner: owner is sensitive, and a report carries no sensitive field yet` (`lines is a list, and a report carries no list`) |
| `repair.outcome` compared with what it can't be | `steps.pay_garage.when: repair.outcome is done or one of repair's close reasons (duplicate, written_off), never fixed` |
| the child opened | `started repair#1: case repair@3 (vehicle from system:opener; budget from person:ana), run memory/repair#1`; the child's first line, `opened by claim-7, from repair#1, with budget and vehicle` |
| the child closed | `repair#1 done: repair closed, nothing left to do, reaching fixed; reporting cost` (or `repair closed: duplicate, by lee; reporting nothing`) |
| the child's opening refused (the step fails) | in `needs_attention`: `repair#1: repair@3 refused its opening: budget is declared untrusted:robots, a label nobody registered`; the operator fixes the cause and retries the same entry |
| the parent closes, or a rule stops the step | in the child: `closed by its parent: duplicate, by ana` (`closed by its parent: stopped by withdraw#1`); in the parent: `repair#1 cancelled: the case is closing` |
| a migration whose target opens another child | refused until it ends (D53's "waits"): `repair#1 is running on repair@3, and claim 2's repair opens repair@4: migrate after it finishes` |
| the package | `cases/repair@3 isn't a package: a child case is a folder holding case.json`; `cases/repair@4 is named by no step` |
| a package's plans disagree | `plans/refund-order@1 differs between claim and cases/repair@3: one reference is one plan` |

**The tests, in the order I'd write them,** each failing first (the negative first):

1. **(negative, curriculum)** A child case that isn't supplied is refused at validation.
2. **(negative)** The shapes refused when read: an approval, `for_each`, `reports` naming a field
   that isn't there, a sensitive or list field reported.
3. **(negative)** The inputs refused at validation: unknown, set by the child's form or rule, of
   another type, sensitive into a plain field; the child with a case step of its own.
4. The guide's example, run as written: the child opens with its sources, plays its script, closes,
   and `pay_garage` reads `repair.cost` from `person:lee, case:repair`.
5. The child unfinished: the step runs, `waiting_for` has one line, the parent stays open.
6. The report: `repair.outcome` as a close reason; a reported field never set is absent, and a
   reader fails; the `MAY_BE_UNSET` warning; the outcome type-checked.
7. Who approves in the child: the parent's opener and the step's proposer refused there; the child
   opened by the parent, never a person.
8. **(negative)** The child's opening refused: the parent's step fails, a retry opens it once the
   cause is gone, and never a second child.
9. The routes: the parent's close and a rule's stop close the child, saying why; an edit leaves the
   child's values; a migration keeping `repair@3` (renamed) and one changing it (waits); a skip of
   a failed opening; a required case step; a repeatable one opening `repair#2`.
10. The package: `cases/` read, refused shapes, the digest covering the child, plans that disagree.
11. The diff, the case map, the builder, the schema, the digest pin.

### Decided while building 18c

- **`case:<child>` is a trusted origin** (asked in slice 4, answered (a); added to D74): it records
  the route a value came by, and its other sources decide its trust. `only_from` still refuses it.
- **The static check follows a report through the child** (asked in slice 4, answered (a)): each
  reported field's sources are the child's own, each opening field marked by where the parent gave
  it, written as one more computed write in the parent, so `always` and the warnings read it. The
  children reach every check that works out sources (`writers.py`, `flow.py`, `warnings.py`).
- **The parent holds its pinned children in its state** (`cases`, given at the opening, carried
  across continue-as-new, replaced by a migration's target): the engine reads a child's outcomes
  and reported types from them at runtime, without a new argument to `decide`.
- **A bug found and fixed:** an input under a policy, reading what a missing contract would give,
  crashed `validate_case` (`KeyError`). An input reading a missing step's value is now said once,
  by that step's issue (`blind_inputs`), for a missing contract, plan or child alike.
- **A second, found by the Temporal test:** a case whose start gives no children crashed the
  workflow task when a case step started, and Temporal retries a crashed task for ever. The engine
  now fails the step: `repair@3 isn't a child this case holds: its start gives the children its
  release pins`. That is what a case step does on Temporal until 18d passes the children.
- **Wordings that follow the engine's existing lines,** not the ones proposed: the plan's input
  refusals (`repair@3 takes no input cost: …`, `… give it a number`); `with budget and vehicle`;
  `the inputs of pay_garage can't be read: repair.cost has no value`; the owed line for a stopped
  required child; the opening refusal said in `needs_attention`. The child's closed line is
  `closed: by its parent: …`, since every closed line starts `closed:`.
- **A migration that would change a running child's release is refused**, saying `migrate after it
  finishes`, as for a running plan: D53 refuses rather than waits.
- **The child's `waiting_for` line comes after the parent's own entries** (added to D74): kept in
  its true place it would sit among the entries a close cancels and a migration renames.
- **Exclusions cross by the child's state** (`excluded`, carried), read by `why_excluded` beside
  the child's own opener, so an assigner can't move a child's approval to an excluded person.
- **A child's plan steps run on the parent's plans**, one reference being one plan; a package
  refuses a reference that means two plans.
- **The digest writes `cases` only for a package with children,** so every digest made before is
  unchanged, as a default is left out (D50). A record written now holds an empty `cases`.
- **The registry's checks are 18d's** (said in D74): activating the parent with the child's
  release, and the child asking as it opens. In memory, `repair@3` is only a name.
- **In memory, a child plays its script when it opens,** and carries on from its own state when its
  parent closes it. A child that finishes later, after its parent moved on, is 18d's: its end comes
  by a signal.

- **From the tutor's review of #88:** who closed a child decided its outcome, so a child closed
  by a person gives `person:<closer>, case:repair` (its ending event carries who closed it, as
  data; `done` stays `case:repair`), and the closer approves nothing that outcome decides, as a
  task's answerer. At the check, a child with close reasons gives its outcome a person stand-in.
  And the check reads a child's input policies with the sources the parent gives its opening
  (`child_policy_issues`), refusing at the parent's input before any case opens; what the child
  refuses on its own stays its own release check's. Not followed yet, carried: the child's
  conditions and rules, read with those sources (`UNTRUSTED_TRIGGER`, a steered start), and, from
  the review, whether a person answering a wait inside a plan should be excluded from what the
  plan's outcome decides; and the diff's `excluded`, which reads where a step's values may come
  from without the case's children, so finds no one through a child's report.
- **From the tutor's second review of #88:** a child refusal said at the parent's input follows
  the child's rules back to the opening field (`opening_fields`); one that traces to no input (a
  start the opening steered) is said at the case step, never dropped. A bug found on the way: a
  child's reference field refused every input; it now takes a reference to its system, read as
  it is, as a plan's field does.

## Promises (18c)

Each claim the note, D74 and the guide's "Child cases" make, and the test that would fail if it
weren't true. Tests without a file are in `tests/test_child_cases.py`. Each was watched failing
first or, for a pin of behaviour already built, catching a mutation.

| Promise | Test |
|---|---|
| A child nobody supplied is refused at validation (the curriculum's negative test) | `test_a_child_case_that_isnt_supplied_is_refused` |
| A case step has no approval, and is never repeated | `test_a_case_step_has_no_approval`, `test_a_case_step_is_never_repeated` |
| A report lists the case's own fields, none sensitive, none a list | `test_a_report_carries_only_the_cases_own_plain_values` (three cases) |
| A child is given only its opening: nothing its forms or rules set, nothing it lacks, each of its type | `test_a_child_is_given_only_what_it_takes_at_its_opening`, `test_a_child_is_never_given_what_its_rules_set`, `test_a_child_is_given_each_input_of_its_type` |
| A sensitive value enters a child only into a sensitive field | `test_a_sensitive_value_enters_a_child_only_into_a_sensitive_field` |
| One level only: a child opens no case, in validation and in the package | `test_a_child_opens_no_case_of_its_own`, `test_a_child_that_pins_children_of_its_own_is_refused` |
| A child supplied under another name, or unreadable, is refused | `test_a_child_supplied_under_another_name_or_unreadable_is_refused` |
| The child opens with its sources, plays, closes, and reports as the step's outputs, each with `case:<child>` | `test_the_guides_child_case_runs_as_written`, and in `test_case.py` |
| An untrusted value given to a child comes back untrusted, at the check | `test_a_value_a_child_was_given_comes_back_with_where_it_came_from` |
| A child's opening keeps its parent's sources at runtime, and the check reads its input policies with them, refusing at the parent's input | `test_a_childs_opening_keeps_the_sources_its_parent_gave_it`, `test_the_check_reads_a_childs_opening_with_the_sources_its_parent_gives` |
| Who closed a child with a reason decided its outcome, and approves nothing it decides; `done` is the child's alone | `test_who_closed_the_child_decided_its_outcome_so_approves_nothing_it_feeds` |
| A child refusal is said at the parent's input that feeds it, through the child's rules (their values and their conditions), or at the case step: never dropped | `test_a_childs_refusal_through_its_rules_is_said_at_the_parents_input`, `test_a_childs_refusal_through_a_rules_condition_is_said_at_the_parents_input`, `test_a_childs_refusal_that_traces_to_no_input_is_said_at_the_case_step` |
| A child's reference field takes a reference to its system, read as it is: never a text, another system's, or a computed one | `test_a_child_takes_a_reference_only_as_a_reference_of_its_system_read_as_it_is`, `test_a_childs_reference_refuses_another_system_and_a_computed_reference` (two cases) |
| Who closed a child, its reason, its children and its exclusions cross continue-as-new | `test_a_childs_state_crosses_continue_as_new` |
| `case:` is trusted, and never read as a system | `test_a_reported_value_passes_trusted_only_and_never_reads_as_from_a_system` |
| An open child keeps its step running, in one line of `waiting_for`, after the parent's own entries | `test_an_open_child_keeps_its_step_running_and_its_parent_waiting`, `test_an_open_childs_line_comes_after_the_parents_own_open_entries` |
| The outcome is `done` or a close reason, type-checked; a report carries nothing else, and the parent never reads the child's milestones | `test_a_child_closed_by_a_person_reports_its_reason_as_the_outcome`, `test_a_childs_outcome_is_done_or_one_of_its_close_reasons`, `test_a_report_carries_nothing_its_child_doesnt_report` |
| A reported field never set is absent: its reader fails, and the check warns | `test_a_reported_field_the_child_never_set_fails_whatever_reads_it`, `test_the_check_warns_where_a_reported_field_may_be_unset` |
| The parent's opener and the step's proposer approve nothing in the child; nobody is its opener | `test_the_parents_opener_approves_nothing_in_the_child`, `test_who_proposed_the_case_step_approves_nothing_in_the_child` |
| A refused opening fails the step; a retry opens the same entry, never a second child | `test_a_refused_opening_fails_the_step_and_a_retry_opens_no_second_child`, `test_a_child_that_opened_is_never_opened_again_by_a_retry` |
| A child the case doesn't hold fails the step, here and on Temporal | `test_on_temporal_a_case_step_fails_closed_until_child_cases_run_there` |
| The parent's close and a rule's stop close the child, saying why; its report changes nothing | `test_a_parent_that_closes_closes_its_child_saying_why`, `test_a_rule_that_stops_the_step_closes_its_child_and_the_parent_goes_on` |
| An edit and an event never reach a child | `test_an_edit_never_reaches_a_child`, `test_an_event_reaches_the_parent_only` |
| A failed opening may be skipped by operators; a required case step is done once its child closes, owed if stopped; a repeatable one opens another child | `test_a_failed_opening_may_be_skipped_by_operators_like_any_failed_run`, `test_a_required_case_step_is_done_once_its_child_closes_and_owed_if_stopped`, `test_a_repeatable_case_step_proposed_again_opens_another_child` |
| The package holds each child, and refuses children that don't fit, and a plan reference meaning two plans | `test_a_package_holds_each_child_it_pins_as_a_package_of_its_own`, `test_a_package_whose_children_dont_fit_its_case_steps_is_refused`, `test_a_plan_reference_meaning_two_plans_in_one_package_is_refused` |
| The digest covers what children do, not their wording; no earlier digest changes | `test_the_parents_digest_covers_what_its_children_do`, `test_digests.py` (the `children` package) |
| A record keeps its children and reads back as the same package | `test_a_release_record_keeps_its_children_and_reads_back_as_the_same_package` |
| A migration keeping the child's release (renamed) keeps the open child; one changing it is refused until it ends | `test_a_migration_renaming_the_case_step_keeps_its_open_child`, `test_a_migration_opening_another_release_from_the_step_is_refused_until_it_ends` |
| The release check checks each child and gives the parent its children | `test_the_release_check_checks_each_child_and_gives_the_parent_its_children` |
| A child's plan step finds its plan beside its parent's | `test_a_childs_plan_step_finds_its_plan_beside_its_parents` |
| The diff reads inside each child with its verdict; a child added or removed is said whole | `test_the_diff_says_what_changes_inside_a_child_with_the_childs_verdict` |
| The case map reads the step and maps each child | `test_the_case_map_reads_the_case_step_and_maps_each_child` |
| The builder writes `child_case` and `reports`, the same JSON, the child in its package | `test_the_builder_writes_the_guides_claim_and_its_child`, `test_builder_coverage.py`, `test_builder_guide.py` |
| The JSON Schema has the keys | `test_schema.py::test_the_committed_schemas_are_what_the_models_say` |
| No new engine version: every recorded history replays | the replay tests over `tests/histories` |

## Routes checked before the pull request (18c)

| Route | What it does | Test |
|---|---|---|
| an answer | the child's own entries are answered in the child, by its script; the parent's are its own | `test_the_guides_child_case_runs_as_written`, the approval tests |
| an edit (D52) | changes the parent only; the child keeps its opening | `test_an_edit_never_reaches_a_child` |
| a migration (D53) | keeps an open child under a renamed step; refused while the target opens another release | the two migration tests |
| an event | reaches the parent only | `test_an_event_reaches_the_parent_only` |
| a rule | may start a case step or stop it; a stop closes the child | `test_a_rule_that_stops_the_step_closes_its_child_and_the_parent_goes_on` |
| the opening | the child's checked; a refusal fails the step; a child not held fails it | the refused-opening test, the Temporal test |
| a plan | a child's plan step runs on the parent's plans | `test_a_childs_plan_step_finds_its_plan_beside_its_parents` |
| a close or a stop (D40) | closes the child through `ask_to_stop`, saying why; the parent waits for its end | the close and stop tests |
| a retry (D26) | of a failed opening only, the same entry; refused for an open child | the two retry tests |
| continue-as-new | `cases`, `closed_as` and `excluded` cross; an earlier state reads them empty | `test_temporal_case.py::test_a_carried_state_reads_back_as_it_was` (the guard that every field crosses) |

**State keyed by a step's name:** none new. Which child a run opened is the run itself (its entry,
`repair#1`), which a migration renames with the step, tested.

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
15. **(choice 12)** An owed step that can't start needs attention, with the line, and leaves
    `waiting_for`: its requirement ended and can't run again (the tutor's run: `pay`'s approval
    rejected); nothing can start it again. Not stranded: a requirement that can still run
    (`confirm, required, after pay`); a rule in the definition that starts it, its moment passed.
16. **(choice 12, held close)** `closes_when` reached with `review` open: `confirm` waits for it,
    and the case closes once `review` and `confirm` are done; with `review` ended and unable to
    run again, `confirm` needs attention.

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
- **Every reader takes `owed.waiting_for`** (from the tutor's review): the in-memory run, the
  story's end (which counts what is owed as pending, so it never says "nothing pending" of a case
  that owes), the advisor's view, and Temporal's report. `waiting_at` keeps only the open entries'
  names: an owed step, listed after them, has no entry yet.
- **Pins added from the tutor's review,** each watched catching its mutation: only the latest run
  counts (a done run run again and stopped is owed again); an owed step with its run open is said
  once; a skip proposed before its step became required (release 1 to 2) isn't applied, at the
  approval.

- **Choice 12, as built.** `case/owing.py` says how a case that owes reports it: `waiting_for`
  or `needs_attention`. It is apart from `owed.py` because it reads the held close, which
  `closing.py` keeps, and `closing.py` reads `owed`. Under a held close no rule acts (D34), so an
  owed step only a rule starts is stranded there: `confirm is started only by a rule, and no rule
  acts while the close is held`. A requirement unmet but able to run again reads `after pay`,
  ahead of "proposed by", since the proposal would be refused until it is met. A closing or
  closed case waits for nothing it owes (found while building test 7: a closed case listed
  `confirm`).
- **A close names what was owed** for every close by a reason, forgetting included: `closed:
  forgotten; confirm not done`.

- **`REQUIRED_MAY_STRAND`, as built** (`case/stranding.py`), one issue per step, the first of: the
  step may end (a rule's stop, its approval) and can't run again; a step it requires may; a step
  it requires may not be done when a `closes_when` milestone is reached. "Done before" is proven
  only when no rule reaches the milestone and every step reaching it requires the step, directly
  or through its requirements: doubt warns. A milestone requirement is not followed, so it warns
  too, the safe side for a warning.

- **What is on its way under a held close** (from the tutor's review at `603a254`): a
  requirement whose run is under way; a milestone a step under way will reach; a step owed itself
  and not stranded, asked recursively, a step already asked on the way counting as stranded so a
  circle ends. The warning's `closes_when` branch skips a requirement that is required itself, or
  that starts itself at the opening and nothing can end undone.
- **A milestone an owed step will reach is on its way too** (from the tutor's review of #86): a
  step reaching it counts if its run is under way, or if it is owed and able, under the same
  guard against a circle.
- **A repeatable step nobody can start again is refused when read,** so `runs_again`'s "proposed
  or started by a rule" never meets one in a check; a test pins the refusal.

## Promises (18a)

Each claim the note, D72 and the guide's "Required steps" make, and the test that would fail
if it weren't true. Tests without a file are in `tests/test_required.py`. Each new test was
watched failing first, or, for a pin of behaviour already right, catching a mutation.

| Promise | Test |
|---|---|
| `required: true` is read on a step of any kind; false leaves every pinned digest as it was | `test_digests.py::test_method_1_gives_the_digests_it_pinned`, `test_digests.py::test_the_pinned_packages_use_every_shape` (the `required` package) |
| A required step nothing can ever start is refused at validation (`NEVER_RUNS`) | `test_a_required_step_nothing_can_ever_start_is_refused_at_validation` |
| A required step with a `when` is refused when read | `test_a_required_step_with_a_condition_is_refused_when_read` |
| A case that owes stays open, and `waiting_for` says what and who may start it | `test_a_case_that_owes_a_required_step_stays_open_and_says_so` |
| Done is done with any outcome: declined, rejected, a plan's `failed` | `test_a_required_step_done_with_any_outcome_is_no_longer_owed`, `test_a_required_plan_step_ending_failed_is_done` |
| Only the latest run counts | `test_only_the_latest_run_of_a_required_step_counts` |
| A run a rule stopped, or whose approval was rejected, leaves the step owed | `test_a_required_step_a_rule_stopped_is_owed_still`, `test_a_required_step_whose_approval_was_rejected_is_owed_still` |
| A skip of a required step's failed run is refused, at the proposal and at the approval | `test_a_skip_of_a_required_steps_failed_run_is_refused`, `test_a_skip_proposed_before_its_step_became_required_is_not_applied` |
| A retry that completes does the step, and the case closes | `test_a_skip_of_a_required_steps_failed_run_is_refused` (its second half) |
| `closes_when` waits for what is owed; only the owed step starts meanwhile, and a proposal of another says what the close waits for | `test_closes_when_waits_for_an_owed_step` |
| A person's close is never held, nor a close by forgetting, and its last line names what was owed | `test_a_persons_close_is_never_held_and_names_what_was_owed`, `test_a_close_by_forgetting_is_never_held_and_names_what_was_owed` |
| A closing or closed case waits for nothing it owes | `test_a_persons_close_is_never_held_and_names_what_was_owed` (`waiting_for == []`) |
| An owed step with its run open is said once, by its entry | `test_an_owed_step_with_its_run_open_is_said_once`, `test_a_required_wait_is_done_by_its_event` |
| `waiting_for`'s forms: proposed by, started by a rule, after a requirement (only once nothing else is pending) | `test_a_case_that_owes_a_required_step_stays_open_and_says_so`, `test_an_owed_step_a_rule_starts_waits_for_the_rule`, `test_an_owed_step_whose_requirement_can_still_run_waits_for_it`, `test_under_a_held_close_an_owed_step_waits_for_a_requirement_on_its_way` |
| Every reader says the same: the run, the story's end, the advisor, Temporal's report | `test_a_case_that_owes_a_required_step_stays_open_and_says_so`, `test_a_story_ends_saying_what_the_case_owes`, `test_the_advisor_is_shown_what_the_case_owes`, `test_the_report_on_temporal_says_what_the_case_owes` |
| An owed step that can't start needs attention, named, and leaves `waiting_for`: its requirement can't run again; it can't run again | `test_an_owed_step_whose_requirement_cant_run_again_needs_attention`, `test_an_owed_step_that_cant_run_again_needs_attention` |
| "No rule starts it" is proven from the definition: a rule that may never fire still counts | `test_an_owed_step_a_rule_starts_waits_for_the_rule` |
| Under a held close, a requirement is on its way if its run is, if a step under way reaches it (a milestone), or if it is owed and can start; otherwise the owed step needs attention | `test_under_a_held_close_an_owed_step_waits_for_a_requirement_on_its_way`, `test_under_a_held_close_a_milestone_an_open_task_will_reach_is_on_its_way`, `test_under_a_held_close_a_requirement_itself_owed_is_on_its_way`, `test_under_a_held_close_an_owed_step_whose_requirement_cant_start_needs_attention` |
| Under a held close an automatic owed step starts by itself once its requirement completes; one only a rule starts needs attention | `test_under_a_held_close_an_automatic_owed_step_starts_once_its_requirement_completes`, `test_under_a_held_close_an_owed_step_only_a_rule_starts_needs_attention` |
| A circle of owed requirements ends, each needing attention | `test_a_circle_of_owed_requirements_under_a_held_close_needs_attention_and_ends` |
| `REQUIRED_MAY_STRAND` warns, never refuses, in each of its forms; none when the step can run again | the four `..._is_warned` tests and `test_a_required_step_that_can_run_again_is_not_warned` |
| The warning's proof: a milestone a rule reaches is never proven; it reads through requirements; a step required itself, or starting at the opening, is on its way | `test_a_closes_when_milestone_a_rule_reaches_is_never_proven_after_a_requirement`, `test_done_before_is_read_through_what_a_step_requires`, `test_under_a_held_close_a_requirement_itself_owed_is_on_its_way` (its last line), `test_a_required_step_whose_requirement_may_be_unmet_once_the_case_may_close_is_warned` |
| One cause, one issue: a step an error refuses isn't also warned about | `test_a_required_step_an_error_refuses_is_not_also_warned_about` |
| A repeatable step nobody can start again is refused when read | `test_a_repeatable_step_nobody_can_start_again_is_refused_when_read` |
| The diff: not proven either way, each way with its witness (choice 10, corrected) | `test_the_diff_reads_required_as_not_proven_either_way`, `test_turned_on_required_takes_a_proposal_the_other_refuses`, `test_turned_off_required_takes_a_close_the_other_holds` |
| The case map says what is owed, on the step and in how the case closes | `test_the_case_map_says_what_the_case_owes` |
| The builder writes `required=True`, the same JSON | `test_the_builder_writes_the_guides_required_step`, `test_builder_coverage.py::test_the_builder_writes_every_key_of_the_format` |
| The JSON Schema has the key | `test_schema.py::test_the_committed_schemas_are_what_the_models_say` |
| A migration's renames are followed; its target decides what is required | `test_a_migration_renaming_a_required_step_keeps_it_owed_under_its_new_name`, `test_a_migration_renaming_a_done_required_step_owes_nothing`, `test_a_migration_making_a_done_step_required_owes_nothing` |
| An edit changes nothing owed | `test_an_edit_changes_nothing_the_case_owes` |
| An event completes a required wait | `test_a_required_wait_is_done_by_its_event` |
| What is owed crosses continue-as-new on Temporal | `test_what_is_owed_crosses_continue_as_new` |
| No new engine version: every recorded history replays | the replay tests over `tests/histories` (`-k replay`, 34 tests) |

## Routes checked before the pull request (18a)

Every route by which what is owed can be set or changed, each handled or refused, with its test:

| Route | What it does | Test |
|---|---|---|
| an answer | completes a task run: done, owed no more | `test_a_case_that_owes_a_required_step_stays_open_and_says_so` |
| an edit (D52) | changes nothing owed; a skip of a required run is refused | `test_an_edit_changes_nothing_the_case_owes`, the two skip tests |
| a migration (D53) | renames followed; the target decides what is required | `test_a_migration_renaming_a_required_step_keeps_it_owed_under_its_new_name`, `test_a_migration_renaming_a_done_required_step_owes_nothing`, `test_a_migration_making_a_done_step_required_owes_nothing` |
| an event | completes a required wait | `test_a_required_wait_is_done_by_its_event` |
| a rule | a stop leaves it owed; a start may run it; none acts under a held close | `test_a_required_step_a_rule_stopped_is_owed_still`, `test_an_owed_step_a_rule_starts_waits_for_the_rule`, `test_under_a_held_close_an_owed_step_only_a_rule_starts_needs_attention` |
| the opening | what nothing can start is refused before any case opens | `test_a_required_step_nothing_can_ever_start_is_refused_at_validation`, `test_a_required_step_with_a_condition_is_refused_when_read` |
| a plan | a required plan step ending `failed` is done | `test_a_required_plan_step_ending_failed_is_done` |
| a close or a stop (D40) | a person's close, and forgetting's, never held; a stop leaves it owed | the two close tests; `test_a_required_step_a_rule_stopped_is_owed_still` |
| a retry (D26) | the retry that completes does it | `test_a_skip_of_a_required_steps_failed_run_is_refused` |
| continue-as-new | owed is worked out from the runs, which cross | `test_what_is_owed_crosses_continue_as_new` |

**State keyed by a step's name:** none is stored. What is owed is worked out from the definition
and the runs, which a migration renames, so the rename test is the check 17c's review asked for.

## Guide drafts

Each part's guide section was drafted here and moved back into the guide at that part's step 2,
corrected by its answers (see "What changes in the guide, if answered as recommended"): 18b's at
18b's step 2, 18c's at 18c's step 2.
