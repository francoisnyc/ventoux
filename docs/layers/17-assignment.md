# Layer 17: Task assignment

Status: 2026-11-03, agreed; 17a built, its promises checked. This note starts from `main` at `ebf81b8`, with
layers 0 to 16 merged. The warm-up was asked and recorded (learning question 14). The guide was
written first (curriculum step 2): `docs/guides/cases.md`, "Who is asked: claiming and assigning
tasks", describes the layer as if it worked, with the recommendations below. If a choice is
answered otherwise, the guide changes with it.

**Answered 2026-11-03.** Choices A to C and 1 to 12 as recommended. D69 is written before 17a is
built; D70 and D71 before their parts.

Prior art: `chartering/src/case/worklist.ts`. Its `workFor` hides a `respond` item whose
`assignee` is someone else, beside the role filter. There the assignee is a fixed string in the
definition's `work` section, and it only filters the list: nothing refuses another person's answer.
Ventoux takes the idea of a list derived from the case's state, never stored apart from it. It
differs on both of those points: an assignee is an event, and (choice 1) a held entry is answered
only by its holder.

## Warm-up: learning question 14, the quickstart's approvals

Recorded in `docs/LEARNING.md`, entry 14. Nothing came back this time, even after a hint for each
part, and the answer was given in full. It leads straight into this layer: the exclusions decide
who *may* answer, and assignment decides who is *asked* to.

## What this layer is for

**Two questions about every open entry.** Who **may** answer it: its roles (D9), plus, for an
approval, the exclusions (D11, D25, D47) and "sees what they approve" (D30). That is a check,
made on every answer. Who is **asked** to: its **assignee**, one person or nobody. An entry nobody
holds is in its roles' **queue**.

**An assignment narrows, never widens.** It follows the brief's rule that policies get stricter
downstream, never looser. An assignment may make the set of people who may answer smaller (only
the holder). It never makes it larger: being asked grants nothing. So assigning `pay`'s approval
to Ana, who set `approved_amount`, can't let her approve it, and is refused on the spot.

**Claiming, giving back, assigning and reassigning are events in the case's history,** sent by the
trusted caller with the person's roles (D19, D22), like an answer. Replay sees the same
assignments, and the engine never looks anyone up.

## The split

| PR | What it builds | Its negative test |
|---|---|---|
| **17a: claiming** | The holder of an open entry; `claim` and `give_back`, each a message checked and recorded; a held entry answered only by its holder; what happens to the holder when the entry is withdrawn, asked again, answered, stopped or closed; `assignees` in the in-memory run and on Temporal; carried across continue-as-new. | **curriculum:** a claim by someone without the task's role is refused. Also: a claim of an entry someone holds; a claim by someone an approval excludes; an answer by someone other than the holder; a give-back by someone other than the holder. |
| **17b: assigning** | A role registered to assign (`assigns=True`); `assign(entry, to, by)`, for an entry held or not; refusals for the assigner and the assignee. | **curriculum:** a reassignment by someone not allowed to assign is refused. Also: an assignment to someone an approval excludes. |
| **17c: assignment rules** | `assign` on a task step in the definition, evaluated when each entry is asked; validation; the case map and rules sheet; the semantic diff; the builder; the JSON Schema. | **curriculum:** an assignment rule that can only pick people who can't answer the task is refused at validation (`ASSIGNS_EXCLUDED`). Also: a rule naming an unknown step, or a step that isn't a task. |

**Why this order.** 17a builds the state and the one rule everything else depends on (only the
holder answers). 17b adds a second way to set the holder, and the one new kind of role. 17c sets
it from the definition, which reaches validation, the diff and the plain forms. The choices for
17b and 17c are sketched here and settled when their parts start, as in layer 16.

### Where each point of the curriculum's layer 17 lands

1. **Who may answer, and who is asked to:** "What this layer is for"; choices 1 and 2.
2. **A role's queue:** choice 2 (an entry nobody holds).
3. **Claiming, assigning, reassigning as events in history:** choices 3, 4 and 9.
4. **Assignment by rule, in the definition, checked like any rule:** 17c, choices 10 to 12.
5. **The case report showing who holds each task:** choice 9.

## Design questions for you

Each answer becomes a decision in the brief, from D69 on, added and never rewriting an earlier one.
Where my recommendation is marked, the guide already follows it.

### For the whole layer

A. **The split:** 17a, 17b, 17c, as in the table, one pull request each. The branches are
   `layer-17a-claims`, `layer-17b-assigning` and `layer-17c-rules`; the warm-up and the guide
   already sit on `layer-17a-assignment`, which I'd rename to `layer-17a-claims`. *Recommended.*

B. **Decisions: one per part,** D69 (17a), D70 (17b), D71 (17c), each written before its part is
   built. Each says what it adds to the earlier ones ("Adds to D9, D22, D24, D25, whose text is
   kept"). *Recommended.*

C. **No new dependency.** *Recommended.*

### For 17a: claiming

1. **Is an assignment a permission?**
   - (a) **No. It narrows only: a held entry is answered only by its holder.** An answer from
     anyone else is refused, saying who holds it and how to free it. Two people never work the same
     task, and "asked" means something. The cost: an away holder blocks the entry until someone
     gives it back or reassigns it. Nothing is skipped automatically, so that is consistent with the
     non-negotiables, but it is real.
   - (b) **No. It is routing only, as in the prototype.** Anyone who may answer still may. It never
     blocks, but an assignment is then only a hint.
   - (c) **Yes, it grants.** Ruled out by "stricter downstream, never looser".

   *Recommended: (a).* Either way, being assigned never grants: every check an answer passes, it
   still passes.

2. **Who may claim, and when.** A claim is checked like an answer to that entry, as far as the
   engine can tell at the claim: the entry is open; the person is written as an identifier (D22);
   they have one of its roles; for an approval, the role may approve the risk, they see what the
   step reads (D30), and no exclusion applies (D11, D25, D47). Refused too: a claim of an entry
   someone holds, and a claim by the holder, which would change nothing. Each refusal is recorded
   and names no value (D30). *Recommended.*
   - **An approval with `count` above 1** needs several people on one entry (D47), so one holder
     can't answer it all. Options: (i) such an entry can't be held, so it stays in the queue and a
     claim is refused saying why; (ii) holding is per approver, so up to `count` holders. *Recommended:
     (i).* It is simpler, and (ii) is a shape of its own.
   - **A plan's waits** (a plan step's own tasks, D28) are not entries of the case. *Recommended:*
     they can't be held in layer 17. A claim of one is refused as an unknown entry.

3. **Giving back.** Only the holder may give an entry back, and it returns to the queue.
   *Recommended.* (17b lets an assigner move it, to someone or back to the queue: choice 7.)

4. **What happens to the holder on every route that touches an open entry.** This is the list I'll
   check before each pull request:
   - **Answered** (by the holder): the entry ends, and with it the assignment.
   - **Withdrawn and asked again** (D25: a value the step reads changed, by an answer, an edit
     (D52), a rule's `set` or a refresh; the step stopped being admitted): the new entry keeps the
     old one's holder, saying so, if they could still answer it; otherwise it goes to the queue,
     saying why (choice 5). *Alternative:* the new entry always starts in the queue. That is
     simpler, but someone who took the work loses it whenever an amount is corrected.
   - **A task answered again** (a repeatable task, a new run): a new entry. A new run is new work,
     so it starts in the queue, unless 17c's rule says otherwise.
   - **Stopped** by a rule (D40), **cancelled** by a close (D10): the assignment ends with the entry.
     The holder sees why, as D10 says.
   - **A lapse** (D11, D23) is of a given approval, not an open entry: nothing is held.
   - **Continue-as-new** (D27): the holders of open entries are part of the case's state, so they
     cross it. A state carried from before this layer has no holders.
   - **A migration** (D53): open entries cross by name, and their holders with them.
   - **An edit (D52)** can't set a holder: a holder is not a field. A change request of a new kind
     is not needed, since 17b's assign already moves it.
   - **The opening** sets no holder (17c's rules may).
   - **An event from outside** sets no holder.
   - **Replay of an older history:** it has no claims, so it decides as before. *Recommended:* no
     new engine version (D51), since nothing recorded decides differently. I'll confirm this with
     a replay test of a 16c history.

5. **Who loses the entry, and when.** The engine learns roles only when a person acts (D22), so it
   can't see that a holder lost a role.
   - **Lost role:** the holder's answer is refused for lack of the role, as anyone's is, and the
     entry stays theirs. Someone who assigns (17b) reassigns it. *Alternative:* a refused answer
     from the holder for lack of the role returns the entry to the queue. *Recommended:* stays,
     since a refusal shouldn't change state, and a typo in a role list shouldn't free work.
   - **Excluded by an approval's rules:** an open entry's exclusions don't change while it is open,
     because anything that would change them withdraws it (D25). So exclusion is checked at the
     claim, and again when a re-asked entry would carry the holder over.

6. **What the report and the history show** (17a's half; 17b adds the assigning lines).
   - History lines: `lee claimed review#1 as support`, `lee gave back review#1`,
     `pay.approval#2 kept for sam`, `pay.approval#2 back in its queue: <reason>`. Refusals are
     recorded as they are today. No line quotes a value (D30).
   - `assignees`: each held entry and its holder, on `CaseRun` and Temporal's `CaseReport`.
   - `waiting_for` unchanged (D24, D47: the same to everyone, naming nobody). *Alternative:* add
     `, held by lee`. *Recommended:* unchanged; `assignees` already says it.
   - The approval sheet gains nothing in 17a.

### For 17b: assigning (sketched; settled when it starts)

7. **Who may assign.** A role the platform team registers, `register_role(..., assigns=True)`, like
   `operates` and `edits` (D26, D52), so no case names its assigners. An assigner may give an entry,
   held or not, to someone, or back to the queue. An assigner may assign to themselves.
   *Alternative:* each task names its assigning roles in the definition. *Recommended:* the
   registered role.

8. **What is checked of the assignee.** The engine knows the assigner's roles (stated with their
   message), not the assignee's.
   - (a) **The Ventoux API states the assignee's roles with the assignment** (D22 extended),
     recorded, and the assignee is checked like a claim (choice 2).
   - (b) **Only what needs no roles is checked** (the exclusions from provenance, the opener, the
     proposer), and a role is found missing only at the answer.

   *Recommended: (a).* It is the same trusted-caller rule, and it refuses earlier.

### For 17c: assignment rules (sketched; settled when it starts)

9. **Where a rule is written, and when it runs.** `assign` on a task step, evaluated when each
   entry is asked, on the case as it is then. *Alternative:* a new `then` of the rules (D38).
   *Recommended:* on the step, since it has no moment of its own: it is part of asking.

10. **What a rule may read, and its provenance.**
    - (a) **Only people the case already knows:** `{"to": "opener"}`, `{"to": "answered", "step":
      …}` (who last answered that task). No identifier is typed into a definition, and no field's
      value picks anyone. The holder's source is the act that made them the pick.
    - (b) **Also a field** (`account_manager`), with its provenance: an untrusted value picks
      nobody, as untrusted data never decides (D38).

    *Recommended: (a) for v1.0,* with (b) recorded as a deliberate limit. A field holding a person
    would need a person type of its own, which is a layer of its own.

11. **What validation refuses.** `ASSIGNS_EXCLUDED`: a rule that can only pick someone who can never
    answer (whoever answered a task whose answer feeds the step, or the opener, for an approval).
    Refused too: an unknown step, a step that isn't a task, and an approval with `count` above 1
    (choice 2). A rule whose pick finds nobody at runtime puts the entry in its queue, saying why,
    never an error that stops the case.

12. **The diff and the plain forms.** Under choice 1(a), an added `assign` narrows who may answer,
    so it reads as stricter, a removed one as looser, and a changed one as a doubt, so looser (D55).
    The case map and the rules sheet read it aloud: "assigned to whoever answered the review".

## Seams and tests for 17a (curriculum step 4)

The tests use only what a caller of the engine uses today: the events `decide` takes, the
script `run_case` plays, what a run and a report say, and the Temporal signals. No test reads
how the holder is stored.

### The seams

1. **Two events into `decide`** (`ventoux.case.state`, beside `Answered` and `Retried`):
   `Claimed(entry, by, roles, at=…)` and `GivenBack(entry, by, roles, at=…)`. A refused one raises
   **`ClaimRefused`** (`ventoux.case`), with the reason as its message, as `AnswerRefused` is
   raised for an answer today.
2. **Two script steps for `run_case`** (`ventoux.testing`, beside `retry` and `finish`):
   `claim("review#1", "lee")` and `give_back("review#1", "lee")`. The test plays the API: the
   person's roles come from `people`, as for an answer (D22).
3. **`run.assignees`** on `CaseRun`, and **`CaseReport.assignees`** on Temporal: a `dict` from each
   held entry to its holder, in the order the entries opened (`{"review#1": "lee"}`). An entry in
   its queue is absent.
4. **The history lines,** asserted as text, as every layer does:
   - `lee claimed review#1 as support`
   - `lee gave back review#1`
   - `pay.approval#2 kept for sam`
   - `pay.approval#2 back in its queue: <the reason an answer would be refused>`
   - on Temporal, a refusal: `refused lee's claim of review#1: <reason>`, and
     `refused lee's give-back of review#1: <reason>`, as `asked()` names other requests.
5. **Two Temporal signals** on the case workflow, `claim` and `give_back`, each taking the
   existing `CaseRequest(what=entry, by=…, roles=[…])`, as `retry` does. A refusal is recorded and
   the case waits on (`REFUSALS` gains `ClaimRefused`).

### The refusals, word for word (proposed)

| Situation | Message |
|---|---|
| no role the entry names | `omar may not claim review#1: it needs support, and omar is operations` (the wording `no_role` already gives an answer, with `claim` for `answer`) |
| someone holds it | `lee holds review#1; ask someone who assigns to reassign it` |
| the holder claims again | `lee already holds review#1` |
| an approval excludes them | `ana may not claim pay.approval#1: ` + the exclusion an answer gets (`ana set approved_amount, which pay uses, so cannot approve it`) |
| they can't see what the step reads | `lee may not claim pay.approval#1: ` + D30's refusal |
| `count` above 1 | `pay.approval#1 needs 2 people, so nobody can hold it` |
| an entry that isn't open, or isn't the case's (a plan's wait) | the refusal an answer to it gets today |
| an identifier spelled otherwise | the refusal an answer gets today (D22) |
| an answer from someone else | `lee holds review#1: ask lee to give it back, or someone who assigns to reassign it` |
| a give-back by someone else | `ana doesn't hold review#1; lee does` (or `nobody holds review#1`) |

### The tests, in the order I'd write them

Each one is written failing first and watched failing for the right reason. Each responds to what
the last one taught, so the list may change on the way.

1. **(negative, curriculum)** A claim by someone without the task's role is refused, and nothing
   changes: `run.assignees == {}`.
2. A claim by someone with the role: `assignees == {"review#1": "lee"}`, the history line, and
   `waiting_for` unchanged (the guide's first example, run as written).
3. **(negative)** An answer by anyone but the holder is refused, even with the role; the holder's
   answer is taken, and the assignment ends with the entry.
4. **(negative)** A claim of an entry someone holds; a claim by the holder.
5. **(negative)** A give-back by someone else; the holder's give-back returns it to the queue, and
   then anyone with the role may claim or answer it.
6. **(negative)** Claims of an approval: by someone it excludes (the person whose answer set a
   value, the opener, the proposer); by someone who can't see what the step reads; by a role that
   can't approve the risk; of an approval with `count: 2`.
7. **(negative)** A claim of an entry not open (answered, withdrawn), of a plan step's wait, of an
   entry that doesn't exist, and with an identifier spelled otherwise (`Lee`).
8. Asked again (D25): the holder is kept on the new entry; and the guide's Sam example, where the
   new values exclude him, sends it back to the queue with the reason.
9. A new run of a repeatable task starts in its queue.
10. A stop by a rule and a close end the assignment; the holder's later answer is refused as for
    any closed entry.
11. A holder who lost the role: their answer is refused for the role, and they still hold the
    entry.
12. **On Temporal:** the `claim` and `give_back` signals; `CaseReport.assignees`; a refused claim
    recorded and the case waiting on; holders crossing continue-as-new.
13. A migration (D53) keeps the holder of an entry it carries.
14. **Replay:** every recorded history in `tests/histories` still replays (the existing replay
    tests, unchanged), which is what "no new engine version" claims.

**The routes, each handled or refused, with its test:** an answer (3, 10), an edit (8, since an
edit withdraws an approval it changes), a migration (13), an event (an event sets no holder; it may
withdraw an approval, 8), a rule (8 through a `set`, 10 through a stop), the opening (2: nothing
held at the start), a plan (7), continue-as-new (12).

## Decided while building 17a

1. **A claim's refusal reuses the answer's words.** For a task, `omar may not claim review#1:
   review#1 is answered by support, and omar has operations` (the seams table proposed `it needs
   support, and omar is operations`; `no_role`'s wording is kept, so a claim and an answer can't
   say it two ways). For an approval, the claim is judged by `judge_approval` itself, as that
   person's *approve*, so every exclusion an answer meets (provenance, the opener, the proposer,
   the rule's readers, a retried run's first start, sight, risk) refuses a claim with the same
   reason. A test checks that the two refusals are the same text.
2. **What isn't an open task or approval refuses a claim as an answer to it is refused**, in the
   same words, as a `ClaimRefused`: an entry closed, withdrawn, never opened or unknown; a wait
   for an event (the wording is now one function for both); a plan step's run; a misspelled
   identifier; a case no longer open. **A change request** can't be held either (`case.change#1 is
   a change request: nobody holds one`): it is approved by someone else, whoever they are (D52).
3. **The holder ends with its entry in one place.** Nine places close an entry. Rather than touch
   each, a sweep at the end of every decision drops the holder of any entry no longer waiting.
   Tests 3, 9 and 10 fail with the sweep switched off.
4. **A holder keeps the roles they claimed with,** and when (`Holder(by, roles, at)`), so a
   re-asked approval can be judged as their answer would be. The roles are the ones stated then
   (D22); their answer is checked again with the roles they state then.
5. **A withdrawn approval's holder is kept for its step** (`kept`, by step) until the step's next
   entry is asked, since the two can be different decisions (sent back, then reviewed again). A
   stop or a close doesn't keep it: only `withdraw` does. If the step is never asked again, the
   kept holder stays in the state, read by nothing.
6. **A migration re-judges every holder against the new release,** and sends back to its queue,
   saying why, an entry its holder couldn't answer there (the release names other roles, say).
   Choice 4 said holders cross with their entries; this is what "cross" means. A kept holder
   follows a renamed step. Found while writing test 13: without the rename, the holder was lost.
7. **`assignees` lists every holder,** those of open entries in the order they opened, then any
   left on an entry no longer open, so a holder left behind would show in the report rather than
   hide. One function serves the in-memory run and Temporal's report.
8. **The guide's section is at the end of the cases guide.** Many tests read the guide's blocks by
   position; a section in the middle shifted them all. "What a waiting case reports" points to it.
   The section uses the guide's people (Lee leads the team, so Ana claims the review).

## Promises (17a)

Each claim the note, D69 and the guide's 17a part make about behaviour, and the test that fails if
it isn't true. Tests in `tests/test_claims.py` unless named otherwise. Four tests passed when
first written, the code an earlier test drove already covering them; each was checked by switching
that code off and watching the test fail (marked *mutation-checked*).

| Promise | The test that would fail |
|---|---|
| A claim by someone without the task's role is refused, in the answer's words (curriculum) | `test_a_claim_without_the_tasks_role_is_refused` |
| A claim makes its person the holder; `assignees` says so; `waiting_for` is unchanged and names nobody; the history says `ana claimed review#1 as support` | `test_a_claim_makes_its_person_the_holder`, and the guide's block in `test_case.py::test_the_guides_examples_run_as_written` |
| While someone holds an entry, only they answer it; anyone else is refused, saying who holds it and how to free it | `test_only_the_holder_answers_a_held_entry` |
| The holder's answer ends the entry, and the assignment with it | `test_only_the_holder_answers_a_held_entry` |
| One holder at a time: a claim of a held entry is refused, and so is the holder claiming again | `test_a_held_entry_is_not_claimed_again` |
| Only the holder gives an entry back; nobody gives back what nobody holds | `test_only_the_holder_gives_an_entry_back` |
| An entry given back is in its queue: anyone with the role answers it; the history says `ana gave back review#1` | `test_an_entry_given_back_is_in_its_queue_again` |
| Being asked grants nothing: a claim of an approval is refused to whomever it excludes (the guide's example) | `test_a_claim_of_an_approval_is_refused_to_whom_it_excludes` |
| A claim of an approval is refused exactly as that person's approval would be: provenance, the opener, sight (D30) | `test_a_claim_of_an_approval_is_refused_as_its_answer_would_be` |
| Someone who may approve a step may hold its approval | `test_a_claim_of_an_approval_by_who_may_approve_it_is_taken` |
| An approval with `count` above 1 can't be held | `test_an_approval_needing_several_people_cant_be_held` |
| What can't be answered can't be claimed, refused in the same words: an entry answered, never opened or unknown; a misspelled identifier; a wait for an event; a plan step's run | `test_what_cant_be_answered_cant_be_claimed` |
| A change request can't be held | `test_a_change_request_isnt_held` |
| Nothing is claimed once the case is closed | `test_nothing_is_claimed_once_the_case_is_closed` |
| An approval withdrawn and asked again keeps its holder if they could still answer it, saying so | `test_an_approval_asked_again_keeps_its_holder` (*mutation-checked*, with the next) |
| … and goes to its queue, saying why, if the new values exclude them (the guide's example) | `test_an_approval_asked_again_goes_to_its_queue_if_its_holder_cant_approve_it` |
| An edit (D52) that withdraws a held approval keeps its holder for the new entry | `test_an_edit_that_withdraws_a_held_approval_keeps_its_holder` (*mutation-checked*) |
| A new run of a task is new work and starts in its queue | `test_a_new_run_of_a_task_starts_in_its_queue` (*mutation-checked*) |
| A stop ends the assignment; the holder's late answer is refused as closed | `test_a_stop_ends_the_assignment_with_its_entry` (*mutation-checked*) |
| A close ends the assignment | `test_a_close_ends_the_assignment_with_its_entry` (*mutation-checked*) |
| A holder who lost the role is refused at their answer, and still holds the entry | `test_a_holder_who_lost_the_role_is_refused_and_still_holds_it` |
| A held entry crosses a migration (D53) | `test_a_held_entry_crosses_a_migration` |
| A migration sends an entry to its queue, saying why, if its holder couldn't answer it on the new release | `test_a_migration_sends_an_entry_to_its_queue_if_its_holder_cant_answer_it_there` |
| A withdrawn approval's holder follows its step's new name | `test_a_withdrawn_approvals_holder_follows_its_steps_new_name` (*mutation-checked*) |
| Holders, and kept holders, cross continue-as-new as data, and still act after it; a state from before 17a holds nothing | `test_holders_and_kept_holders_cross_as_data_and_a_state_from_before_has_none` (*mutation-checked*), and `test_temporal_case.py::test_a_carried_state_reads_back_as_it_was` (every state field crosses) |
| On Temporal, claiming and giving back are signals; a refused claim or answer is recorded and the case waits on; `CaseReport.assignees` says who holds what, across a switch | `test_temporal_claims.py::test_claims_are_signals_recorded_and_carried_across_continue_as_new` |
| No refusal or history line quotes a value | every refusal and history line the tests above check is asserted whole (`match="^…$"` or `==`), and each names people, roles, fields and entries only |
| No new engine version: every history recorded before replays as it did | the replay tests of earlier layers, unchanged (`test_temporal_approvals.py::test_histories_from_before_11h2_replay` and the other `before_*` histories), all passing |

**Not promised by 17a, and left to its part:** assigning and reassigning, and the `assigns` role
(17b, D70); assignment rules, `ASSIGNS_EXCLUDED`, the diff and the plain forms (17c, D71). The
guide already describes them; their tests come with their parts.

# 17b: assigning

Status: 2026-11-03, agreed; 17b built, its promises checked. Starts from `main` at `23ddacc`, with 17a merged
(#83). The warm-up was asked and recorded (learning question 36). The guide was written first:
`docs/guides/cases.md`, "Assigning, reassigning, returning to the queue", with the recommendations
below.

**Answered 2026-11-03.** Choices 13 to 20 as recommended; 7 and 8 as agreed with 17a. D70 is
written before 17b is built.

## What 17b is for

17a lets a person take work (a claim) and let it go (a give-back); only the holder does either. So
an entry whose holder never acts can't be freed: the tutor's review of 17a, watched for 17b. 17b
adds the **assigner**: someone whose role assigns moves an entry between people, without its
holder, and never answers it. Three acts, one of them new in kind:

| Act | Before | After |
|---|---|---|
| **assign** | in the queue | held by the person named |
| **reassign** | held by Ana | held by Sam |
| **return to the queue** | held by Ana | nobody holds it |

Like a claim, each is a message from the trusted caller (D19, D22) with no field for a value: it
changes whose list an entry is on, never what its step does (learning question 36).

## Choices for 17b

Choices 7 and 8 were sketched with 17a and agreed then; they are restated here as they stand.
Each answer goes into **D70**, written before 17b is built.

7. **Who may assign** (agreed). A role the platform team registers, `register_role(...,
   assigns=True)`, like `operates` and `edits` (D26, D52), so no case names its assigners. A role
   the catalog doesn't mark as assigning may not assign, whoever states it (fail closed).

8. **What is checked of the assignee** (agreed). The Ventoux API states the assignee's roles with
   the assignment, as it states the assigner's (D22); both are recorded. The assignee is checked
   exactly as a claim is (D69): the same `role_to_hold`, so for an approval the same
   `judge_approval`.

13. **Returning an entry to its queue, without its holder.** This frees the entry the tutor
    watched. As its own act, `unassign(entry, by)`, an `Unassigned` event; or as `assign(entry,
    None, by)`. *Recommended:* its own act. "Assign to nobody" reads oddly, and its checks differ
    (there's no assignee to judge).

14. **Nobody chooses their own judge.** Assigning grants nothing, but an assigner picks *who* is
    asked. Sam set `approved_amount`, so he may never approve `pay`; handing `pay`'s approval to a
    colleague he expects to approve it would let him choose who judges his own decision, the
    influence D11's "someone else" exists to prevent.
    - (a) **Whoever may not approve a step may not move its approval**: assign, reassign or
      return it. Judged as their own approval would be (`judge_approval`), so every exclusion
      applies: provenance, the opener, the proposer, a rule's readers, and so on.
    - (b) The same, for assigning and reassigning only; returning to the queue picks nobody.
    - (c) No rule: the approver is still checked at the answer, so a friendly approver is still
      "someone else".

    *Recommended: (a).* Returning to the queue picks nobody, but it can also take the approval
    from an approver about to reject, again and again. One rule is easier to explain and to
    test. **What it doesn't need:** the assigner having the approval's role or the risk or the
    sight. Lee may assign an approval she couldn't answer herself; only the exclusions that make
    someone a party to the decision apply. So the check is the exclusions part of
    `judge_approval`, not all of it. *To decide with it:* tasks are not judgements of anyone's
    decision, so this applies to approvals only.

15. **What the assigner needs on the entry itself.** Nothing else: not the task's role (Lee
    moves the review, which needs `support`), not sight of what the step reads (she sees whose
    list it is on, never a value). *Recommended.*

16. **Assigning to yourself.** Allowed, and checked as a claim: if the assigner could answer
    the entry, it is the same as claiming it; if not, it is refused as any assignment to someone
    who couldn't answer. *Recommended:* no rule of its own; its history line says `assigned …
    to lee`, like any assignment.

17. **What is refused, beside 14:** an assigner without an assigning role; an assignee who
    couldn't answer the entry; an assignment to the entry's current holder (it changes nothing);
    a return of an entry nobody holds; anything that can't be held (D69: an approval needing
    several people, a plan's wait, a change request, an entry not open); a misspelled identifier,
    the assigner's or the assignee's (D22). *Recommended.* Each refusal names people, roles and
    entries, never a value (D30).

18. **What the history shows.** `lee assigned review#1 to sam as support-lead`; when someone held
    it, `…, from ana`; `lee returned review#1 to its queue as support-lead, from ana`. On
    Temporal, a refusal reads `refused lee's assignment of review#1: …` and `refused lee's return
    of review#1: …`. *Recommended:* naming the previous holder, since whoever reads the history
    sees why the work moved and from whom.

19. **What the holder records.** The assignee becomes the holder with the roles the API stated
    for them, and when, `Holder(sam, {support}, at)`, as a claim records the claimant's. So
    everything 17a does with a holder (a re-asked approval, a migration, continue-as-new) works
    unchanged. Who assigned them isn't kept in the state; the history says it. *Recommended.*

20. **Temporal and the engine version.** Two signals, `assign` and `unassign`, beside `claim`
    and `give_back`; `assign` takes the assignee and their roles too, so a message of its own
    (`CaseAssignment`). No new engine version: no history recorded before holds an assignment.
    *Recommended.*

## The split

One pull request, `layer-17b-assigning`. Its negative test, from the curriculum: a reassignment
by someone not allowed to assign is refused. Also: an assignment to someone who couldn't answer;
an excluded person moving an approval (choice 14).

## Seams and tests for 17b (curriculum step 4)

As for 17a, the tests use only what a caller of the engine uses: the events `decide` takes, the
script `run_case` plays, what a run and a report say, and the Temporal signals.

### The seams

1. **The catalog:** `register_role(..., assigns=True)`, and `catalog.assigners`, the roles that
   assign, in order, beside `editors` and `operators`. The development catalog's `support-lead`
   assigns.
2. **Two events into `decide`** (`ventoux.case.state`, beside `Claimed` and `GivenBack`):
   `Assigned(entry, to, to_roles, by, roles, at=…)` and `Unassigned(entry, by, roles, at=…)`. A
   refused one raises the existing `ClaimRefused`, as a refused claim or give-back does: one
   exception for everything about who holds an entry.
3. **Two script steps for `run_case`** (`ventoux.testing`): `assign("review#1", "sam",
   by="lee")` and `unassign("review#1", by="lee")`. The test plays the API: both people's roles
   come from `people` (D22).
4. **What a run and a report say:** `assignees`, unchanged from 17a; the history lines, asserted
   as text:
   - `lee assigned review#1 to sam as support-lead`, and `…, from ana` when Ana held it;
   - `lee returned review#1 to its queue as support-lead, from ana`;
   - on Temporal, `refused lee's assignment of review#1: <reason>` and `refused lee's return of
     review#1: <reason>`.
5. **Two Temporal signals,** `assign` taking a new `CaseAssignment(entry, to, to_roles, by,
   roles)`, and `unassign` taking the existing `CaseRequest`; with client functions of the same
   names, beside `claim` and `give_back`.

### The refusals, word for word (proposed)

| Situation | Message |
|---|---|
| no role that assigns | `ana may not assign review#1: assigning is done by support-lead, and ana has support` (the shape every missing role uses, D52's `no_role`) |
| the assignee couldn't answer | `lee may not assign review#1 to omar: review#1 is answered by support, and omar has operations` (the claim's reason, D69) |
| the assignee already holds it | `sam already holds review#1` |
| the assigner can't approve the step (choice 14) | `sam may not assign pay.approval#1: sam set approved_amount, which pay uses, so cannot approve it` (the exclusion an answer gets) |
| unassign of an entry nobody holds | `nobody holds review#1` |
| anything that can't be held, a misspelled identifier | the refusal a claim gets today (D69) |

`assign`, `reassign` and `unassign` share the wording `may not assign` for the assigner's own
checks: they are one power.

### The tests, in the order I'd write them

1. **(negative, curriculum)** A reassignment by someone not allowed to assign is refused: Ana
   holds the review; Sam, without the role, can't move it; nothing changes.
2. Lee reassigns it to Sam, without Ana: `assignees == {"review#1": "sam"}`, the history line
   with `, from ana`; Sam's answer is taken, Ana's refused. The guide's story, run as written.
3. Lee assigns an entry nobody holds, and assigns one to herself where she could answer it.
4. **(negative)** An assignment to someone who couldn't answer, with the claim's reason; to the
   current holder.
5. **(negative)** An unassign by someone not allowed to assign; of an entry nobody holds. Then
   the tutor's case: Ana never acts, Lee unassigns, the entry is in its queue, and Sam answers it.
6. **(negative, choice 14)** Sam, who set `approved_amount` and has `support-lead`, may not
   assign, reassign or unassign `pay`'s approval; he may assign the review. The check is the
   exclusions only: Lee may assign an approval of a step whose risk her role couldn't approve,
   if any such shape exists in the fixtures, else her lack of sight of a field.
7. **(negative)** What can't be held can't be assigned (an approval needing several people, an
   entry not open, a change request, a plan's run), and misspelled identifiers, the assigner's
   and the assignee's, in the claim's words.
8. An assigned holder is treated as a claimed one: a re-asked approval keeps them, or sends it
   to its queue (D69); they cross continue-as-new.
9. **On Temporal:** the `assign` and `unassign` signals; a refused one recorded and the case
   waiting on.
10. **Replay:** every history recorded before still replays.

**The routes by which a holder is set or changed, after 17b:** 17a's routes, unchanged, plus the
two new acts (tests 1 to 7); an assigned holder then goes every route a claimed one goes (test 8).

## Decided while building 17b

1. **The curriculum's negative test uses Omar, not Sam.** In the guide's cast Sam has
   `support-lead`, which assigns, so Omar (`operations`) plays the person not allowed to.
2. **An approval's exclusions are one function, `why_excluded`** (`src/ventoux/case/answers.py`),
   lifted out of `judge_approval` with no change in behaviour (its own commit; every test stayed
   green). An answer runs it with the role, risk and sight checks; an assigner runs it alone
   (choice 14). So "someone else" is written once, and the two can't drift apart.
3. **The assignee's identifier is checked too,** where the assigner's is (`entry_to_hold`). Found
   by test 7: an assignment to `Sam` was taken, and "someone else" compares identifiers exactly.
4. **One refusal for a missing role, in the house wording:** `ana may not assign review#1:
   assigning is done by support-lead, and ana has support`, as an edit's or a migration's is.
   The guide's draft said "support doesn't assign"; it now says this.
5. **Assigning is its own file,** `src/ventoux/case/assigning.py`, beside `claims.py`, which it
   uses: one idea per file. An assignment's assignee is judged by 17a's `role_to_hold`.
6. **One test is not mutation-checked:** "an assigner needs only to be someone else". It guards
   a design the code never had (judging the assigner by the whole approval). The mutation that
   would show it failing needs the catalog inside the check, which imports it in a circle; the
   check calls `why_excluded` and nothing else, which the code shows.

## Promises (17b)

Each claim D70 and the guide's 17b part make about behaviour, and the test that fails if it isn't
true. Tests in `tests/test_assigning.py` unless named otherwise. Tests that passed when first
written were checked by switching off the code they guard and watching them fail
(*mutation-checked*); two couldn't be, and say why.

| Promise | The test that would fail |
|---|---|
| A reassignment by someone not allowed to assign is refused, in the house wording (curriculum) | `test_a_reassignment_by_someone_not_allowed_to_assign_is_refused` |
| A role nobody registered assigns nothing, whoever states it | `test_a_role_nobody_registered_assigns_nothing` (not mutation-checked: only a registered role can be among the assigners, so there is no separate code to switch off) |
| An assigner reassigns a held entry without its holder; the history names the previous holder; the old holder's answer is then refused, the new one's taken (the guide's story, run from the guide) | `test_an_assigner_reassigns_a_held_entry_without_its_holder`, and `test_case.py::test_the_guides_examples_run_as_written` |
| The assigner needs nothing else on the entry: Lee moves a review she can't answer | `test_an_assigner_reassigns_a_held_entry_without_its_holder` |
| An assigner assigns an entry nobody holds, and may assign to themselves when they could answer | `test_an_assigner_assigns_an_entry_nobody_holds_and_may_assign_it_to_themselves` (*mutation-checked*) |
| The assignee is checked as a claim is: someone who couldn't answer is refused, in the claim's words, the assigner included | `test_an_assignment_is_refused_to_whoever_couldnt_answer_or_already_holds` |
| An assignment to the entry's holder is refused | the same test |
| An unassign is refused without a role that assigns, and of an entry nobody holds | `test_an_unassign_is_refused_to_whoever_cant_assign_and_of_what_nobody_holds` |
| An entry whose holder never acts can always be freed: returned to its queue without its holder, then answered by anyone with the role (the tutor's case) | `test_an_entry_whose_holder_never_acts_is_returned_to_its_queue` (*mutation-checked*) |
| … an approval too, by an assigner who is someone else | `test_an_approval_is_returned_to_its_queue_by_an_assigner_who_is_someone_else` (*mutation-checked*) |
| Nobody chooses their own judge: whoever set what a step reads may not assign, reassign or unassign its approval | `test_nobody_moves_the_approval_of_their_own_decision` |
| … nor whoever opened the case | `test_the_opener_moves_no_approval_of_the_case` |
| … and it applies to approvals only: an excluded person still assigns a task | `test_an_excluded_assigner_still_assigns_what_isnt_their_decision` |
| An assigner is judged by the exclusions alone, never the approval's role, risk or sight | `test_an_assigner_needs_only_to_be_someone_else_not_to_approve_it` (not mutation-checked: see "Decided while building 17b", point 6) |
| What can't be claimed can't be assigned, refused in the claim's words: an entry closed or unknown, a wait for an event, a plan's run, a change request | `test_what_cant_be_claimed_cant_be_assigned` |
| An approval needing several people can't be assigned | `test_an_approval_needing_several_people_cant_be_assigned` |
| Both identifiers are written one way, the assignee's as the assigner's | `test_both_identifiers_are_written_one_way` |
| An assigned holder is a holder like any other, with the roles the API stated for them: kept when their approval is asked again | `test_an_assigned_holder_is_kept_when_their_approval_is_asked_again` (*mutation-checked*) |
| On Temporal, `assign` and `unassign` are signals; a refused one is recorded and the case waits on; an assigned holder crosses continue-as-new | `test_temporal_claims.py::test_assigning_on_temporal_is_signalled_recorded_and_carried` |
| No refusal or history line quotes a value | every refusal and line the tests above check is asserted whole, and each names people, roles and entries only |
| No new engine version: every history recorded before replays as it did | the replay tests of earlier layers, unchanged, all passing |

# 17c: assignment rules

Status: 2026-11-04, agreed; seams next. Starts from `main` at `605f9a3`, with 17a (#83) and
17b (#84) merged. The warm-up was asked and recorded (learning question 41). The guide was written
first: `docs/guides/cases.md`, "Assignment rules", with the recommendations below.

**Answered 2026-11-04.** Choices 9, 11, 12 and 21 to 26 as recommended; 10 as agreed with 17a.
D71 is written before 17c is built.

## What 17c is for

17a and 17b let people set an entry's holder. 17c lets the **definition** set one, when each entry
opens: `"assign": {"to": "answered", "step": "review"}`, *asked of whoever answered the review*.
A rule picks only people the case already knows (choice 10, agreed), so every person it can pick
was named by the trusted caller, and untrusted data never routes work. It narrows who may answer
(D69), so the semantic diff judges it, and validation refuses one that can only pick someone who
can never answer.

## Choices for 17c

Choices 9 to 12 were sketched with 17a. 10 was agreed then and stands; 9, 11 and 12 are settled
here, 9 changed by what step 1 found. Each answer goes into **D71**, written before 17c is built.

9. **Where `assign` is written** (*changed from the sketch*). On a task step, and inside an
   approval: `"approval": {"roles": [...], "assign": {...}}`. The sketch said a task step only, but
   an approval isn't a task step, and the curriculum's negative test is about approvals (choice
   11). Evaluated when each entry opens, on the case as it is then; it has no moment of its own.
   *Recommended.*

10. **What a rule may read** (agreed). `{"to": "opener"}` and `{"to": "answered", "step": …}`;
    no identifier typed, no field. A field holding a person stays a deliberate limit.

21. **Which answerer `answered` picks.** The latest answer's person, as `outcome` reads the latest
    answer (D9). *Recommended.* The alternative, the first, would pick someone whose answer no
    longer counts.

22. **When the rule finds nobody, or someone who couldn't answer.** The entry is in its queue,
    saying why (`follow_up#1 in its queue: its rule found nobody: review hasn't been answered`;
    `…: <the reason their claim would be refused>`). Never an error that stops the case.
    *Recommended.*

23. **How the pick is judged, and recorded.** As a claim is (17a's `role_to_hold`), with the
    roles the picked person stated when they acted: the opener's with the opening, the answerer's
    with their answer. They become the holder with those roles. The history says `follow_up#1
    assigned to ana by its rule`. *Recommended.* *Needed for it:* the case keeps who answered each
    task last, with their roles, and the opener's roles. Today it keeps neither: a small addition
    to the state, carried across continue-as-new, absent from older states (then the rule finds
    nobody, failing closed).

24. **A re-asked approval with a rule and a kept holder.** The kept holder (D69) stays, and the
    rule picks only when nobody is kept: a person's claim or an assigner's choice outranks the
    definition's default. *Recommended.*

11. **What validation refuses and warns about.** Errors only where proven for every case (D37):
    - `ASSIGNS_EXCLUDED` (error), on an approval only: a rule picking the opener, who approves
      nothing (D11); or whoever answered a task the step's approval always excludes, as the diff
      already proves it (`excluded_every_time`: a task, not repeatable, whose outcome the step's
      inputs or `when` read). The refund's `pay` reads `review.outcome` in its `when`, so `pay`'s
      approval asked of whoever answered the review is refused. *The curriculum's negative test.*
    - `ASSIGNS_MAY_BE_EXCLUDED` (warning): whoever answered a task the approval *may* exclude
      (`excluded`: their answer can reach what the step reads), but not in every case.
    - `ASSIGNS_SEVERAL` (error): a rule on an approval whose `count` is above 1 (D47).
    - `MAY_ASSIGN_NOBODY` (warning): `answered` naming a task the step doesn't require, directly or
      through its requirements, so it may not have been answered when the entry opens.
    - Refused when the definition is read: an unknown `to`; `answered` without a step, or naming a
      step that isn't a task, or one that doesn't exist; `opener` with a step.
    - On a task, a role mismatch can't be proven (D22): never refused, found when the entry opens.
    *Recommended.*

12. **The diff and the plain forms.** An added `assign` narrows who may answer: stricter. Removed:
    looser. Changed: a doubt, so looser (D55). The case map and the rules sheet read it aloud:
    "asked of whoever answered the review", "asked of whoever opened the case". *Recommended.*

25. **The builder and the JSON Schema.** `Assign.answered(review)` and `Assign.opener()`, a small
    frozen dataclass like `Approval`; `assign=` on `task(...)` and on `Approval`. The JSON Schema
    is generated from the models, so it publishes the shape (D60), and `ventoux schema` is
    regenerated. *Recommended.*

26. **The engine version.** No definition readable before holds `assign`, so no history decides
    differently: no new version (as D66 to D68 did). The key is behaviour, so the digest covers it
    (D50). *Recommended.*

## The split

One pull request, `layer-17c-rules`. Its negative test, from the curriculum: an assignment rule
that can only pick people who can't answer the task is refused at validation (`ASSIGNS_EXCLUDED`).

## Seams and tests for 17c (curriculum step 4)

17c reaches more of the engine than 17a or 17b, so each place gets the seam its existing tests
already use. No test reads how a pick is stored.

### The seams

1. **The definition:** `parse_case(definition)`, accepting `assign` on a task step and inside an
   approval, and raising `CaseInvalid` with its path for a malformed rule (`steps.follow_up.assign:
   …`), as every read-time refusal does.
2. **The runtime:** `run_case`, unchanged. The pick shows in `run.assignees` and the history
   (`follow_up#1 assigned to ana by its rule`, `follow_up#1 in its queue: …`); on Temporal, in
   `CaseReport`. What the case keeps to pick from (the latest answerer of each task, the opener's
   roles) is state, crossing continue-as-new; tested through `state_as_data` / `state_from_data`,
   as 17a's holders are.
3. **Validation:** `validate_case(case, catalog)` returns `Issue`s; the tests assert `code`, `path`,
   whether it is an error or a warning, and the message whole: `ASSIGNS_EXCLUDED`,
   `ASSIGNS_SEVERAL`, `ASSIGNS_MAY_BE_EXCLUDED`, `MAY_ASSIGN_NOBODY`.
4. **The diff:** `diff(before, after, catalog)` gives `Change`s; the tests assert the path
   (`steps.follow_up.assign`, `steps.pay.approval.assign`), the verdict and `said`.
5. **The plain forms:** `case_map(package, catalog)` and `plain(diff, before, after, catalog)`, as
   text: the step's sentence gains "asked of whoever answered review" / "asked of whoever opened
   the case".
6. **The builder:** `Assign.answered(task)`, `Assign.opener()`, `assign=` on `Case.task(...)` and on
   `Approval`; the test writes the guide's follow-up with the builder and compares the JSON, as
   the builder's tests do.
7. **The JSON Schema:** `case_schema()`; `ventoux schema --unchanged` passes once the committed
   schema is regenerated; a wrong `assign` shape is refused by both the schema and the parser
   (`tests/test_schema.py`'s fixed set).

### The tests, in the order I'd write them

1. **(negative, curriculum)** `pay`'s approval asked of whoever answered the review is refused at
   validation: `ASSIGNS_EXCLUDED`, at `steps.pay.approval.assign`, with the guide's message. So is
   one asking the opener.
2. **(negative)** Malformed rules are refused when read: an unknown `to`; `answered` with no step,
   an unknown step, or a step that isn't a task; `opener` with a step.
3. **(negative)** `ASSIGNS_SEVERAL`: a rule on an approval needing two people.
4. The guide's follow-up runs: Ana answers the review; `follow_up#1` is hers, `follow_up#1 assigned
   to ana by its rule`. The guide's JSON block is the definition the test runs.
5. A rule that finds nobody, or someone who couldn't answer, leaves the entry in its queue, saying
   why; a rule asking the opener, when a system opened the case, finds nobody.
6. `answered` picks the latest answer's person, on a repeatable task.
7. An approval's rule picks someone it doesn't exclude; when the approval is asked again, a kept
   holder outranks the rule; with nobody kept, the rule picks again.
8. The warnings: `ASSIGNS_MAY_BE_EXCLUDED` (whoever answered a task whose answer *may* reach what
   the step reads), and `MAY_ASSIGN_NOBODY` (a task the step doesn't require).
9. What the case keeps to pick from crosses continue-as-new; a state from before has none, so a
   rule finds nobody.
10. The diff: added, stricter; removed, looser; changed, looser.
11. The plain forms: the case map's sentence, and the plain diff's before and after.
12. The builder writes the guide's follow-up as its JSON; the JSON Schema accepts it, and refuses a
    wrong shape, as the parser does.
13. **Replay:** every history recorded before still replays.

**The routes by which a rule sets a holder:** an entry opening, whatever opened it (the opening's
rules, a person's proposal, a rule's start, a retry's re-ask of an approval, a re-asked approval);
each goes through one of the two places an entry opens: a task's run in `start`, an approval in
`ask` (`runtime.py`, `approvals.py`). Tests 4 and 5 drive the first, test 7 the second. 17a's and 17b's
routes are unchanged.
