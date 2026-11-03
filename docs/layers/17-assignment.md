# Layer 17: Task assignment

Status: 2026-11-03, agreed; 17a's seams next. This note starts from `main` at `ebf81b8`, with
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

## Seams and tests (curriculum step 4)

To agree after the choices are answered.

## Decided while building

Nothing yet.

## Promises

Written as each part is built.
