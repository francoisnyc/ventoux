# Layer 12: releases and changing open cases

Status: research done, 2026-10-22 (`docs/layers/12-research.md`: Temporal's SDK at `c4de91d` and
docs at `82ac5bd`, Flowable's engine at `f6017e3`, the `chartering` prototype at `197d519`); layer 12
explained, split into five parts, and 12a's choices put with a recommendation each, the same day.
Answered "all as recommended", 2026-10-22: choices 1 to 16. The warm-up (learning question 11) was
put and not answered, so it stays open, asked again at 12a's walk-through. D50 and the releases
guide written before building 12a; 12a built, slices 0–5, and its Promises table checked
against the tests, the same day (see 12a, "Decided while building").

## Warm-up: learning question 11, behaviour vs wording

> A step drafts a customer letter through `letters.draft@1`, with the opening sentence passed as a
> literal input: `"intro": "'Dear customer, we are pleased to confirm…'"`. Marketing wants
> "pleased" changed to "happy". Release or no release, and why? What would you change in the
> definition so that wording like this becomes presentation next time, without weakening any
> guarantee?

Open, never answered yet, and it is 12a's own question. Answer from memory first; it is recorded
in `docs/LEARNING.md` with the discussion.

## What this layer is for

Until now a definition is a file someone hands the engine, and an open case runs whatever was
handed it when it opened. Layer 12 makes definitions published things, and lets open cases
depend on them:

- **Publish:** a package (a case definition and the plans it uses) gets an immutable, numbered
  release, identified by a digest of its behaviour (brief, D5). Wording lives in `display` blocks
  and isn't behaviour: changing it makes no release.
- **Activate:** in each environment, new cases start on the release activated there, once the
  environment's workers are shown to serve every contract it needs, with the same hashes.
- **Migrate:** an open case moves to a newer release only by a change request, previewed and
  approved by someone else. Cases not migrated finish on the release they started on.

A small example. The refund package is released as `refund` 1 and activated in production; 40
refunds are open. Marketing rewords "Refund the customer" to "Send the refund": the digest doesn't
move, so the tool records *release 1, wording 2*, and every open refund shows the new title at
once. Then a team adds a fraud check that `pay` requires: the digest moves, CI records `refund` 2.
Nothing changes in production until someone activates 2; then new refunds start on it, and the 40
open ones still run 1. Ana proposes migrating them; the preview says 38 can move and 2 can't (their
`pay` is running and the new release renamed its output); Bob approves; 38 cases record "migrated
from refund 1 to refund 2 by ana, approved by bob", and from then on `pay` waits for the fraud
check in each.

Two different things can change under an open case, and layer 12 treats them apart:

- **Its definition** (the release): only by a migration, a person's act, said in the history.
- **The engine** (Ventoux's own code deciding differently): the checkpoint lists seven paths where
  today's code already decides a recorded history differently from the code that recorded it. A
  case must say which engine version decides it, and that must never change by itself either.

## The split

Layer 12 lands as five pull requests, each with its section here, its own Promises table and its
own tutor review, as layers 8 to 11 did:

| PR | What it builds | Curriculum negative test |
|---|---|---|
| **12a: the release tool** | a package; its behaviour digest (a hash method with a version, design question 16); the next release number; the immutable release record; a wording-only change detected and recorded as a wording revision; `ventoux release` | a change outside `display` reported as wording-only |
| **12b: which release a case runs, and which engine** | a case opens on a release and records it; it replays on that release's definition and plans, never the latest; the engine version stored with each case; the checkpoint's seven paths; a wording revision read at once by open cases' views | — (its own: a case opened on release 1 decides on release 1 after 2 is released) |
| **12c: change requests** | one mechanism, propose, approve, apply, generalising 9c's forget: case-file edits and the lapses they cause (D25, D47), skipping a failed run (D17), forget as one kind of it (D32) | — (its own: a self-approved edit, a self-approved skip) |
| **12d: migrations** | a migration as a kind of change request: names mapped (steps, milestones, fields, rules, timers, events), a preview per case and across a cohort, running steps finishing under their old release, timers, approvals and events in flight, moving an engine version, graduating a strict workflow to a loose case (D2) | a self-approved migration; an unmapped rename that running work depends on |
| **12e: activation** | worker manifests, the environment registry, `ventoux activate` (bindings, served contract hashes, live pollers), a workflow type that may not move under open cases while its task queue may (D29), retiring a release | activating a release whose activities no worker serves; activation refused when a served contract's hash differs |

**Why this order.** 12a needs nothing at runtime and gives every later part its record. 12b needs
the record: a case opens on one. 12c is the mechanism 12d is one use of, and 12c's edits are
smaller, so its rules (who is excluded, what lapses, what the history says) are settled on them
first. 12e last: activation reads the release record (12a) and the bindings open cases recorded
(12b), and retiring needs to know which cases are open on a release; it doesn't need change
requests, so it could move before 12c if you'd rather see a release reach a worker sooner.

### Where each point in the brief lands

- **The release tool** (12a): package, behaviour digest, next release number, the immutable
  record, and a wording-only change detected and *recorded* at once. Open cases *reading* the new
  wording at once needs a case to know its release: 12b.
- **Which release a case runs** (12b). Today a case's definition is in its start
  (`CaseStart.definition`), so its history holds it and replay already reads that, never the
  latest. Its plans are not: the case workflow reads them from the worker's class
  (`CaseWorkflow.plans`, `temporal/cases.py`), so a plan changed under the same reference would
  reach an open case's next plan step. 12b carries the whole release (its number, its digest, the
  case and its plans) in the start, so the history holds everything the case decides on.
- **Which engine** (12b): see "The behaviour version" below; the seven paths each land there.
- **Change requests** (12c): edits and their lapses (D25's "a lapse from a change request stops the
  step", every approval on an entry at once, D47); skipping a failed run, never automatic (D17);
  forgetting, made general (D32: 9c already built it as "a small workflow per request, the
  rule, an apply step", so 12c generalises it rather than starting again).
- **Migrations** (12d): everything the brief lists, migrating as one more kind of change request.
- **Worker manifests, the registry, `ventoux activate`, retiring** (12e).

### The behaviour version: how a case knows which engine decides it

The options the checkpoint named, against the research:

- **(a) Temporal's patching, per change, in the driver** (`workflow.patched("d49")`). A patch is
  answered once per run and memoised (research 1.2, 1.3): a case open before a fix keeps the old
  path until its next continue-as-new, then takes the fix, at a point an event count chose. That
  is a change of behaviour nobody approved and no line of history says. And each change is
  another call in the driver, passed in.
- **(b) Worker versioning, cases pinned** (research 2). Pinning keeps the old build polling for as
  long as a case is open (months), or moves a case at a switch (2.5), as (a) does. It answers
  "which code replays this history", which D5 already gives it for implementation changes; it
  doesn't say which rules decided.
- **(c) The engine version as data in the case, recommended.** A case's state holds
  `engine: <n>`, the version of Ventoux's deciding code it opened under. `decide` reads it like any
  other value, so `core` and `case` stay free of Temporal and of any clock; where a later version
  decides a path differently, the code keeps both branches, chosen by `state.engine`. It is set
  once, when the case opens, crosses continue-as-new with the rest of the state (D27), and
  changes only by a migration, approved and said (12d). On Temporal the driver asks it once, at
  the opening, with Temporal's patching used as a recorder only: the newest version first
  (`patched("ventoux-engine-2")`, then `"ventoux-engine-1"`, research 1.5), so a new case records
  the current version and a replayed one reads what it recorded. In memory, `run_case` takes it
  (the latest by default). This is the shape the SDK uses for its own logic changes (research
  1.7). Old branches follow Temporal's lifecycle (1.6): kept while any open case is on that
  version, then removed, with a replay test over the open cases first.

With (c), case workflows run auto-upgrade under worker versioning (research 2.4: a case outlives
any build), and D5's "workflow code relies on Temporal's worker versioning" stays true for
implementation changes, the deployment's to configure.

**The seven paths** from the checkpoint ("Layer 12's own"): 10b's G1, 11b's three, the untrusted
moment (D43), the retry rejected, D49, D46's expansions, and the hash method. Each was merged
before any case could record an engine version, and nothing runs in production before v1.0
(11b's note). So I'd recommend: **engine version 1 is the engine as merged when 12b starts**; a
history recorded before it (no version recorded) replays as version 1 where it decided the same,
and where it didn't, Temporal refuses it and the case waits (D17), as each of those notes said:
their fixtures stay as the proof, and 12b adds fixtures recorded before layer 12 that must replay.
From 12b on, every engine change that decides a recorded path differently is a new version with
its old branch kept: D46's "an expansion is part of the format" becomes "a changed expansion is a
new engine version", and the same for an operator (D20) or a moment (D38). The hash method is not
an engine version: it versions digests and hashes in records, and is 12a's (choice 13).

### Change requests (12c, sketched here so the split can be judged)

- **One shape:** proposed by a person, approved or rejected by another, applied by the case as an
  event its `decide` checks again, depending on nothing the request checked (D34's rule, as 9c's
  `ForgetApproved` does). Each request is its own small workflow, as forget is (`<case
  ID>/forget`), its kinds: edit, skip, forget, migrate.
- **Never self-approved. Excluded from approving a change request, at least:** the person who
  proposed it, and the person who opened the case (D11, D25: the opener approves none of its
  steps, and a change request decides as much as a step's run). Each kind may add to the list
  (for a skip, whoever proposed the failed run, D25); none may remove from it. Both proposer and
  approver hold a role the platform team registered for that kind, as `forgets=True` does (D32).
- **What an edit carries as its source:** `person:<proposer>`, the person who wrote the value
  (D12), with the field's declared mark added as for every writer (`untrusted:<label>` stays),
  never the old value's sources re-stamped, nor the approver's. The approver is recorded beside
  it. Both are excluded from approving any step that reads the value (D11: whoever's answer flows
  into a step's inputs; the approver decided it too). An edit never makes untrusted data trusted
  by re-tagging it (research 5, the prototype's edit does).
- **What lapses:** an edit changing a value an open or given approval saw lapses every approval on
  that entry at once (D47), and stops the step (D25); the history says so.
- **Nothing quotes a value:** `ana proposed an edit of approved_amount`, never the old or new
  value (D30).

### Migrations (12d, sketched)

- **Names, not positions** (D2, D5; research 4.1). A name the new release declares the same way is
  the same thing; a rename is written in the request, for steps, milestones, fields, rules,
  timers and events; nothing is matched by position or by title.
- **Refused, never terminated** (research 4.2, the opposite of Flowable): a name gone from the new
  release, unmapped, that something depends on: a running or failed run, an open task or
  approval, a set timer, a waiting start, a reached milestone (D48: reached once, never undone), a
  value in the case file. The curriculum's negative test.
- **Running work finishes** (D10; research 5.3): a running step finishes under its old release, its
  result landing under the mapped names; a running plan finishes on its plan (D28; why plans
  don't migrate, research 5.7).
- **The preview is the same pure check as the apply,** over one case's state or a cohort's, and
  says everything the migration would do; the apply checks again (research 4.7, where Flowable
  doesn't).
- **Timers, approvals and events in flight:** a set timer whose rule keeps its name, moment and
  age keeps its due time; otherwise it is cancelled, said, and nothing is set retroactively; an
  open or given approval whose step reads anything the migration changes lapses (D11, D25); an
  event already decided stays decided; the case reads every condition again after (research 4.6).
- **Untrusted data never decides** (D38, D49): values keep their sources through a migration, never
  re-stamped; a new release reading them is checked as any release is.
- **Graduating** a strict workflow (a `sequence`) to a looser case (D2) is a migration like any
  other: the story test is the curriculum's.

## The curriculum's negative tests, placed

| Negative test | Lands in |
|---|---|
| A change outside `display` reported as wording-only | 12a (this note's Promises) |
| A self-approved migration | 12d (12c refuses self-approval for every kind first) |
| An unmapped rename that running work depends on | 12d |
| Activating a release whose activities no worker serves | 12e |
| Activation refused when a served contract's hash differs | 12e |

## Choices for the whole layer

Answer by number. "Recommended" is what I'd do; set-aside options are said.

1. **The split:** 12a to 12e as in the table, in that order. *Recommended.* Set aside: activation
   before change requests (possible, said above; I'd keep migrations' mechanism next to 12b,
   whose engine version a migration moves).
2. **The behaviour version is data in the case** (option c above): `engine: <n>` set once at the
   opening, read by `decide`, crossing continue-as-new, moved only by a migration. *Recommended.*
   Set aside: (a) Temporal's patching per change (the run memoises its answer and takes a fix at
   its next switch, silently); (b) pinning case workflows to builds (keeps old builds for months;
   it stays the deployment's tool for implementation changes, D5).
3. **The seven paths:** engine version 1 is the engine as merged when 12b starts; no old branch is
   kept for paths merged before it (nothing runs in production before v1.0); their fixtures stay
   as proof, and 12b adds fixtures recorded before layer 12 that must replay. From then on, a
   changed path, expansion (D46), operator (D20) or moment (D38) that decides a recorded history
   differently is a new engine version. *Recommended.*
4. **Change requests' exclusions and an edit's source,** as sketched: never approved by the
   proposer or the case's opener; an edit's source is `person:<proposer>`, its field's mark kept;
   proposer and approver both excluded from approving steps reading it. *Recommended,* decided in
   detail in 12c.
5. **Migrations refuse, never terminate,** as sketched. *Recommended,* decided in detail in 12d.

## 12a. The release tool

User-facing description, written first once you agree: `docs/guides/releases.md` (new; the
platform team's and the workflow developer's). Decision: brief D50, drafted with the guide.

### What this part is for

On merge, CI runs `ventoux release` on each package. It works out what changed since the
package's latest release:

- **behaviour** (anything outside `display`): a new release, the next number, an immutable record;
- **wording only** (`display` and nothing else): no release; a wording revision of the current
  release, recorded at once;
- **nothing:** nothing written.

It never asks a person what the change is: it is computed, and fails closed. Getting it wrong one
way makes a spurious release, which costs a migration nobody needed. Getting it wrong the other
way reports a change of behaviour as wording, which reaches every open case at once, unreviewed
as behaviour, unmigrated, unactivated. So every doubt is a release.

The example, with the refund package:

```
$ ventoux release examples/packages/refund --releases releases --commit 4f2a9c1
refund 1 released: digest 9d1c…e07a (method 1)
$ # a title reworded
$ ventoux release examples/packages/refund --releases releases --commit 7b0e311
refund 1, wording 2: steps.pay.display.title changed; no release
$ # pay's approval threshold raised from 100 to 150
$ ventoux release examples/packages/refund --releases releases --commit c90d4e2
refund 2 released: digest 51aa…3f90 (method 1); behaviour changed at steps.pay.approval.when
```

### Choices for 12a

6. **What a package is.** One folder: `case.json` (one case definition) and `plans/`, holding each
   plan the case's plan steps name, one per file, each identified by its own `plan` and `version`
   (`refund-order@1`), the file's name free. Refused, with nothing written: a plan a step names
   that the folder lacks; a plan nobody names (shipped, never run: fail closed, as D28 refuses a
   plan supplied under another reference); two files holding the same plan; anything else in the
   folder. Plan references keep their `@n` (D28 unchanged): inside a package, `refund-order@1` is
   simply the plan's name, so D5's "references inside a package carry no versions" is met
   without a format change. A shared plan library as its own package stays after v1.0.
   *Recommended.* Set aside: references without versions inside a package (a format change for
   every plan step, for nothing a case needs yet).

7. **The behaviour digest reads the package as the engine reads it.** The case and each plan are
   parsed (`parse_case`, `parse_plan`), then written out canonically and hashed with SHA-256:
   - **`display` is left out by its type, never by its key's name.** Every `Display` and
     `ApprovalDisplay` in the schema is dropped; a case-file field *named* `display` (allowed:
     `[a-z][a-z0-9_]*`) is behaviour like any other. Matching on the key would let a field's type
     change pass as wording: the curriculum's negative test, in its sharpest form.
   - **Values at their defaults are left out,** so writing `"stays_open": false` changes nothing,
     and a key a later decision adds, at its default, changes no existing package's digest.
   - **Maps keep their written order;** an object's keys are sorted. Steps and rules are maps whose
     order is behaviour (rules on one moment act in the order written, D38; steps are admitted in
     order), so reordering them is a release, never wording, and never ignored.
   - **Numbers as the engine holds them:** `100` and `100.0` parse to different decimals, so they
     digest differently, and that is a (spurious, harmless) release. Whitespace and an object's
     key order change nothing.
   *Recommended.* Set aside: hashing the JSON as written minus every `display` key (a field named
   `display`, and every reformatting, both go wrong, one of them unsafely).

8. **Only a package that passes is released.** Each plan is checked (`validate`, layer 3) and the
   case (`validate_case`, layer 10) against the catalog; any error refuses the release, saying the
   issues; warnings are printed and the release goes on (D34: "a warning lets a definition
   through"). The catalog is the development one, as `ventoux simulate`'s is (doors row 36): the
   deployment's catalog comes with `ventoux check` (layer 14). *Recommended.* Set aside: releasing
   anything that parses (a release no case could open safely).

9. **Numbers.** A package's first release is 1; a digest new to the package is the latest + 1. A
   digest equal to an existing release makes no release: `same behaviour as refund 2; nothing
   released` (a revert merged is a rollback, which is activating 2, 12e), or a wording revision
   of it (choice 11). One digest, one release, as the brief's glossary says ("identified by its
   behaviour digest"). *Recommended.* Set aside: a new number for a reverted digest (two releases
   that are one behaviour, and two places to activate it from).

10. **The immutable record.** `releases/<package>/<n>.json`, holding:
    - the package's name (its case's `case`), its number, its digest with its method
      (`{"method": 1, "sha256": "…"}`), and the commit CI passes;
    - every contract it needs (activities and workflows, its plans' included), each with its hash
      from the catalog (`{"payments.refund@2": {"method": 1, "sha256": "…"}}`), which 12e's
      activation checks against what workers serve;
    - the package as written, case and plans, so 12b can start cases from the record alone,
      and the next run of the tool can recompute its digest (choice 12);
    - what changed since the release before: the paths, behaviour and wording apart (choice 14).

    A record is written once: a file that exists is never written again, except with the same
    bytes (a CI job run twice says `refund 2 already released`); different content is refused,
    naming the file. Records are read through a small store interface with one implementation, a
    folder; a production store (a bucket, or 12e's registry) waits until something needs it, as
    the key provider's production adapter did (D15). *Recommended.*

11. **A wording-only change** is a package whose digest equals its latest release's while what is
    written differs: recorded at once as `releases/<package>/<n>.wording-<k>.json` (the package
    as written, the commit, the `display` paths that changed), never a new number. *Recorded* is
    12a's half; open cases reading it at once is 12b's, once a case knows its release. Its
    negative tests are the curriculum's: a change outside `display` never reported as wording,
    each shape tried (a literal input, rules reordered, a field named `display`, a plan's
    transition). *Recommended.*

    That makes the warm-up's answer concrete: a literal input (`"intro": "…pleased…"`) is
    behaviour (D5: "literal values passed to activities are behaviour"), so the tool releases;
    making it wording takes the text out of the inputs.

12. **The hash method has a version** (design question 16, "to decide by layer 12"). Every digest
    and contract hash the tool writes carries `method: 1`. Comparing a package with its latest
    release recomputes the release's digest from its stored package under the current method,
    so a method change never reads as a behaviour change; a record whose method the tool doesn't
    know is refused, saying so, never compared (fail closed). `contracts.lock.json` keeps its
    shape: a hash there with no method is method 1, said in the hash check's module; changing the
    method later is its own decision. *Recommended.* Set aside: a method field in the lockfile now
    (a format change to layer 1's file, which nothing needs until a second method exists).

13. **Design question 16's other half, "should a hash failure say what changed?"** The release
    tool says which paths changed (choice 14), from the stored package. For contracts, the
    lockfile keeps hashes only, and a readable diff of a contract stays with the semantic diff
    (layer 13), which reads the catalog. *Recommended:* design question 16 then reads "decided"
    in the brief, pointing to D50 and layer 13.

14. **Release notes, until layer 13:** the paths that changed, behaviour and wording apart
    (`steps.pay.approval.when`), never the values: a definition's literals aren't case-file
    values, but a path is what a reviewer needs, and the semantic diff (layer 13) is what will
    say what it means. *Recommended.*

15. **The command.** `ventoux release FOLDER --releases DIR --commit SHA`: the commit is given by
    CI, never read from git (the tool does no I/O beyond the files it is pointed at). Exit 0 for
    released, wording recorded, already released, or nothing to do; 1 for a refused package or
    record; 2 for what can't be read, as `ventoux simulate`'s codes. *Recommended.*

16. **Where it is recorded:** a new decision, D50 ("Releases: a package's behaviour digest, its
    number and its immutable record"), with dated amendment lines on D5 (choices 6, 9, 12) and
    design question 16 (choices 12, 13); D5's text stays. The guide `docs/guides/releases.md`
    written first, its example run by a test. No new dependency (`hashlib`, `json` and `pathlib`
    are the standard library's). *Recommended.*

### How it works

- `case/releases.py` (pure, no I/O): `Package` (the case and its plans, parsed, and as written);
  `package(case, plans)`, refusing a missing, unused or doubled plan; `behaviour(package)`, the
  canonical data with `display` left out by type; `digest(package)`; `changed(old, new)`;
  `next_release(package, records)`, which says what to do: release `n`, wording revision `k` of `n`,
  already released, or nothing. It reads no clock (a record's time is the commit's, given) and
  imports no Temporal.
- `tooling/releases.py`: reading a package folder; the folder store (`records(package)`, `write`,
  written once); `release(folder, store, commit, catalog)`, the validation of choice 8, then
  `next_release`, then the write.
- `tooling/cli.py`: the `release` command beside `simulate`.
- `examples/packages/refund/`: the guide's package (the quickstart's refund, and a plan step's
  package from the cases guide).

### Not in 12a

- A case opening on a release, reading its wording at once, and the engine version (12b).
- Change requests (12c), migrations (12d), activation and retiring (12e).
- The semantic diff and real release notes (layer 13); `ventoux check` and the deployment's
  catalog (layer 14).
- Nothing on Temporal: 12a changes no workflow, so no replay fixture is needed; 12b records the
  ones before layer 12, before it changes anything.
- No new dependency.

### Seams the tests use

- `package(case_data, plans_data)`, `digest(package)`, `next_release(package, records)`,
  `changed(old, new)`: what the tool decides, in memory.
- `release(folder, store, commit, catalog)` with a folder store under pytest's `tmp_path`: what
  it writes and refuses.
- `main(["release", …])`: what the command prints and exits with.
- The guide's example, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The digest, and the curriculum's negative test first:** the refund's literal input changed
   (the warm-up's letter, on `letters.draft@2`, since `@1` is retired) is not wording-only; then rules reordered, a field
   named `display` retyped, an explicit default (no change), a title (wording).
1. **Packages:** a missing plan, an unused plan, the same plan twice, a stray file, each refused; a
   plan's transition changed is behaviour.
2. **Numbers and the record:** 1 first; latest + 1; a digest already released makes nothing; a
   record never written over; a package with errors not released; the contracts and their hashes
   in the record.
3. **Wording revisions:** recorded at once, numbered, with their paths; nothing released.
4. **The method:** recorded with every hash; a release recomputed under the current method; an
   unknown method refused.
5. **The command and the guide:** exit codes; the guide's example run as written; D50.

### Decided while building

- **A field's `type` was dropped at its default** (slice 0, found writing the digest): `"type":
  "number"` is the default of the number shape's one field, so leaving defaults out made a number
  field and a text field digest alike, a behaviour change read as nothing. A field that names
  its object's shape (a `Literal`) is now always kept; `test_a_fields_type_changed_is_a_release`
  and the field named `display` both fail without it. D50 says so.
- **Paths read as the JSON writes them** (slice 0): the model keeps a field's type under
  `declared`, the JSON beside its `display`, so a retyped field is `fields.amount.type`.
- **Slice 0 built `package` and `next_release` with the digest,** so slices 1 and 2's tests passed
  at once; each was seen failing on a deliberate break: plans not checked for use or doubles,
  stray files allowed, a record written over, validation skipped, warnings refusing, only the
  latest release compared, plan contracts left out of the record. Slice 3's (the first wording
  read as the latest, the revision always 2) and slice 4's (no recompute, the method unchecked,
  the place unchecked) the same.
- **A wording revision is read against the wording people see now** (slice 3): putting a title back
  as it was is a new revision, since people read the one between.
- **A record out of place in the store is refused** (slice 4): a file whose record says another
  number would be compared as the wrong release.
- **The command prints a digest's first 12 hex characters;** the record keeps all 64.
- **The lockfile's hashes are method 1,** said in `core/hash_check.py` (choice 12).

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`R` is `tests/test_releases.py` (new). Drafted before building; checked against the tests,
2026-10-22: every test named here exists, and every test in `R` is named here.

| Promise | Test |
|---|---|
| A literal input changed is a release, never wording-only | R `test_a_literal_input_changed_is_a_release` |
| Rules reordered are a release, never wording-only; steps reordered too | R `test_rules_reordered_are_a_release`, `test_steps_reordered_are_a_release` |
| `display` is found by its type: a case-file field named `display` changed is a release | R `test_a_field_named_display_is_behaviour` |
| A field's `type` is kept even at its default: a number field made a text is a release | R `test_a_fields_type_changed_is_a_release` |
| A plan's transition changed is a release of its package | R `test_a_plans_change_is_a_release_of_its_package` |
| A title, a description, an outcome's title and an approval's reason changed are wording only: no new number, a wording revision naming the paths | R `test_a_title_changed_is_wording_only`, `test_an_approval_reason_changed_is_wording_only` |
| Whitespace, an object's key order and a value written at its default change no digest | R `test_reformatting_changes_no_digest`, `test_an_explicit_default_changes_no_digest` |
| A package names exactly the plans its steps run: missing, unused, doubled or a stray file refused, nothing written | R `test_a_missing_plan_is_refused`, `test_a_plan_nobody_runs_is_refused`, `test_a_plan_given_twice_is_refused`, `test_a_stray_file_is_refused` |
| A package with a validation error is not released, saying the issues; a warning doesn't stop it | R `test_a_package_with_an_error_is_not_released`, `test_a_warning_lets_a_release_through` |
| The first release is 1; a new digest is the latest + 1 | R `test_releases_are_numbered_from_1` |
| A wording revision is numbered from 2, recorded at once, read against the wording people see now; a release after it is numbered on | R `test_wording_revisions_are_numbered_and_recorded_at_once` |
| A digest already released makes no new release, naming it | R `test_a_digest_already_released_makes_none` |
| The same package again writes nothing | R `test_the_same_package_again_writes_nothing` |
| A record is written once: the same bytes again are accepted, different ones refused naming the file | R `test_a_record_is_never_written_over` |
| The record holds the package as written, its contracts with their hashes, the commit and the changed paths | R `test_the_record_holds_what_activation_needs` |
| Every digest and hash records its method; a release is compared by recomputing its digest from its stored package, a record whose package doesn't give its digest refused; an unknown method is refused; a record out of place in the store is refused | R `test_every_hash_records_its_method`, `test_a_release_is_compared_by_recomputing_its_digest`, `test_a_record_of_an_unknown_method_is_refused`, `test_a_record_out_of_place_is_refused` |
| No message quotes a value from the package, only paths and names | R `test_the_tool_names_paths_never_values` |
| The command exits 0, 1 or 2 as the guide says, and prints what it did | R `test_the_command_says_what_it_did` |
| The guide's example runs as written | R `test_the_guides_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new module too | `tests/test_layers.py`, unchanged |

## 12b. A case's release, and its engine version

Status: drafted 2026-10-22, from `main` at `b734098` (12a merged, #42); the histories from
before 12b recorded and replayed first (slice 0). Answered "all as recommended" the same day:
choices 17 to 28, 27 as (b). The warm-up (learning question 38) put and not answered, left open.
D51, its amendment lines (D5, D27, D28, D50) and the guides' parts written before building.

User-facing description, written first once you agree: `docs/guides/cases.md`, "Running a case on
Temporal" ("A case runs its release"), and `docs/guides/releases.md` ("Open cases and new
wording"). Decision: brief D51, drafted with them.

### Warm-up: learning question 38, stale facts, and why replay decides the same way

> Sam approves a refund on day 3. Ana's review set `approved_amount` on day 0, and
> `check_order.status` came from an order lookup on day 0. `pay` needs both at most a day old.
> a) What happens to each fact, and why are they treated differently? b) On Temporal the worker
> restarts and replays the case. Why does it decide the same way, given that "3 days old"
> depends on time?

Open; last asked at 11g's warm-up. It is 12b's question too: a case's release and its engine
version are what replay must read from history, as it reads each event's time. Answer from memory
first. (Question 11 stays open for the walk-through at the end of layer 12.)

### What this part is for

12a gives a package a release and a record. Nothing yet runs on one: a case opens on a definition
handed to it, and nothing says which release or which engine decides it. 12b makes a case open on
a release, keep it to the end, and say which engine version decides it.

A small example. `refund` 1 is released and a case `refund-7` opens on it. Its history begins
`opened on refund 1, engine 1`. A week later `refund` 2 is released, and the deployment also
changes the `refund-order@1` plan it supplies to drafts. `refund-7`'s plan step starts the next
day: it runs `refund 1`'s `refund-order@1`, from its own start, never the deployment's, never
release 2's. Marketing rewords a title: `refund 1, wording 2` is recorded (12a), and the next time
Ana opens `refund-7` she reads the new title, while every decision stays exactly what it was.

### What the code does today

Read on `main` at `b734098`, before drafting:

- **The definition is in the case's history already.** `CaseStart.definition` is the workflow's
  input, and `switch` passes it on at each continue-as-new (`temporal/cases.py`), so replay reads
  the definition the case opened with, never a later one. 12b only has to say which release it
  is, and check it.
- **Its plans are not.** A plan step reads `CaseWorkflow.plans`, a class attribute of the worker
  (`run_plan`, `supplied`, `wrong_references`). A deployment that changes `refund-order@1` reaches
  every open case's next plan step, and the case's own checks read the changed plan.
- **Wording is read inside the workflow,** by two queries: the view's field titles
  (`case_view`, `case/visibility.py`) and the approval sheet's (`sheet_of`). Nothing that decides
  reads `display` (12a's checks found none).
- **No engine version exists anywhere.** `decide(case, catalog, state, event)` has one behaviour.

### Choices for 12b

Numbered on from 12a's. Answer by number.

17. **A case opens on a release.** `start_case` takes a release record (from the store, 12a) or,
    as today, a definition, which makes a draft (choice 20). `CaseStart` gains `release`: the
    package's name, the release's number, its digest (method and SHA-256), and its plans as
    stored data, by reference; `definition` stays, holding the release's case. `switch` carries
    `release` across continue-as-new as it carries `definition`. *Recommended.* Set aside: a
    second start function (two ways in, one of them a draft by omission).

18. **The workflow checks what it was given,** depending on nothing the client did (D34's rule):
    at the opening it recomputes the digest from the definition and plans in its start, and a
    case whose package doesn't give the release's digest, or whose digest names a method this
    code doesn't know, is refused at once, as an unreadable definition is (`CaseRefused`, the
    workflow fails, nothing is decided): `refund-7 can't open on refund 1: what it was given
    isn't refund 1's package`. *Recommended.* Set aside: trusting the client's start (a record
    edited in the store, or a client bug, would open a case on behaviour nobody released).

19. **A released case runs its release's plans, and only those.** `run_plan` and the case's plan
    checks read the plans in its start; the worker's `CaseWorkflow.plans` serve drafts only. The
    plan's child workflow already carries its plan in its own start (`PlanStart`, D28), so its
    history holds it. The negative test: the deployment supplies a changed `refund-order@1`, and
    a case opened on `refund` 1 still runs `refund` 1's. *Recommended.*

20. **A case with no release is a draft,** as every case before 12b is, and runs as it does
    today; its report says `draft`. D5's "drafts never run in production" needs to know which
    environment is production: 12e's registry, where activation refuses a draft. *Recommended.*
    Set aside: refusing drafts in 12b (every test and the development worker run drafts, and
    nothing yet tells production apart).

21. **The engine version is in the case's state** (layer choice 2): `CaseState.engine`, a whole
    number, set when the case opens and never by itself after; it crosses continue-as-new with
    the state (`carried.py`), and `decide` reads it like any value, so `core` and `case` stay free
    of Temporal and clocks. A state carried before 12b has no `engine` and reads as 1 (layer
    choice 3). A version this code doesn't know, newer than its own, stops the workflow task
    (`state_from_data` raises), and the case waits for code that knows it (D17): never read as
    an older one. With one version, `decide` has no branch yet. *Recommended.*

22. **How the driver learns the version at the opening:** a pure function in `case`,
    `opening_engine(known, asked)`: the versions this code knows, newest first, each above 1
    asked through `asked` (on Temporal, `workflow.patched("ventoux-engine-<n>")`, research 1.5);
    the first that says yes is the case's version, and none means 1. Asked once, at the opening,
    before the first decision: a run that starts from a carried state reads its version from the
    state, never asks. So Temporal's patching only records the answer, and its memoising (research
    1.3) can't move a case. **With version 1 alone, nothing is asked and no marker is written:**
    a case opened under 12b has a history of the same shape as one opened before. Unit-tested now
    with a pretend chain (2, then 1); version 2's own Temporal test comes with version 2. In
    memory, `run_case` opens at the code's version. *Recommended.* Set aside: the client stating it
    (it doesn't know which code the worker runs); a marker for version 1 now (a command in every
    new history, for nothing).

23. **The seven paths, and what version 1 is** (layer choice 3): version 1 is the engine as merged
    at `b734098`, 12b's own changes included, since 12b changes nothing a recorded history
    decides (slice 0's fixtures prove it). No old branch is kept for paths merged before; their
    fixtures stay as their proof. From 12b on, a change that decides a recorded path differently
    is version *n*+1: its old branch kept behind `state.engine`, a fixture recorded under version
    *n* that must replay, and a line in the brief. A changed pattern expansion (D46), operator
    (D20) or moment (D38) is such a change. Recorded in D51. *Recommended.*

24. **What a case says about it.** The report gains `release` (`refund 1`, or `draft`) and
    `engine`; a released case's history begins `opened on refund 1, engine 1`, before its opening
    line; a draft's history is as today, so every earlier test's history stands. *Recommended.*

25. **Wording reaches open cases when it is shown, never by changing the case.** The view and the
    approval sheet take, optionally, a wording revision: the package as written of `refund 1,
    wording k`. The workflow uses its `display` only if it names the case's release and gives its
    digest; any other is refused, saying so (fail closed), and never falls back silently. A query
    is read-only and never recorded (Temporal), so wording can't change a decision or a replay.
    Who passes it: the caller (the API, and here the client functions' callers) reads the latest
    revision from the release store (12a). *Recommended.* Set aside: a signal sending each
    revision to every open case of its release (it needs the list of open cases per release,
    which 12e's registry brings, and a history line per revision per case); rendering titles
    outside the workflow (the view is filtered inside it, D30).

26. **Which wording a person saw** (D5: "the audit log records which wording a person saw"). An
    answer may carry the wording revision its sheet showed (`wording=2`), stated by the trusted
    caller like its roles (D22), and recorded on its history line: `ana answered review#1:
    approve, as worded in refund 1, wording 2`. Without it the line is as today. *Recommended.*
    Set aside: leaving the audit to the inbox (after layer 15): D5 asks it of the audit log.

27. **A revert that brings new wording** (the tutor's review of #42, first point). Release 1,
    release 2, then a merge back to release 1's behaviour with a new title: 12a records `refund
    1, wording 2`, and once choice 25 is built, every open case on release 1 reads it at once.
    The likely way to get there is a behaviour revert that keeps release 2's titles, written for
    release 2's behaviour (`Pay after the fraud check`), now shown on cases that have no fraud
    check. Three options, each with its test and a line in the releases guide:
    - **(a)** keep D50 as written: a wording revision of the older release, the tool saying so
      (`refund 1 isn't the latest release: its open cases read this wording at once`);
    - **(b)** refuse: a package whose behaviour is an older release's and whose wording isn't
      that release's latest is refused (exit 1): `same behaviour as refund 1, other wording:
      rewording an older release reaches its open cases; bring back its wording`. Only the latest
      release takes wording revisions;
    - **(c)** (b), plus an explicit opt-in to reword an older release on purpose (a typo fixed in
      release 1's open cases while 2 is the latest).
    *Recommended: (b).* Refusing now keeps (c) open as a later loosening; (a) can't be taken back
    once open cases have read such wording. The limit: an older release's typo can't be fixed
    until (c) is decided. An amendment line on D50.

Two points from the same review are fixes, not choices, as you said; they land in 12b's first
slice:

- **A plan field's source is named as the JSON writes it:** `plans.refund-order@1.fields.amount.source`,
  not the model's `sources.amount`, as 12a did for a case field's `type`.
- **The releases guide says what the tool checks:** every record is read again and its digest
  recomputed, not only the latest's; and any other file in a package's releases folder refuses
  the run.

28. **Where it is recorded.** D51 ("A case runs the release it opened on, and says its engine
    version"), with dated amendment lines on D5 (drafts, choice 20; wording read when shown,
    choices 25–26), D27 (what crosses, choices 17, 21), D28 (a released case's plans, choice 19)
    and D50 (choice 27). The guides' parts written first, their examples run by tests. No new
    dependency. *Recommended.*

### Seams the tests use

- `start_case(client, workflow, record_or_definition, file, id, queue, opened_by)`; `report(case)`:
  `release`, `engine`, `history`; `view(case, roles, wording)`, `approval_sheet(…, wording)`;
  `answer(…, wording=…)`.
- `opening_engine(known, asked)`; `state_as_data`, `state_from_data` (`engine`).
- `run_case(...)`: the engine version in memory.
- The releases tool (`next_release`, `ventoux release`) for choice 27 and the path fix.
- The Temporal test server, and the `Replayer` on slice 0's fixtures and the earlier ones.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The histories from before 12b, recorded and replayed** (built: `tests/histories/before_12b_*`,
   `tests/test_temporal_case_release.py`, recorded under `main` at `b734098`).
1. **The tutor's points:** a plan field's source path; the guide's two lines; choice 27 (a revert
   with new wording refused, or recorded, as decided).
2. **The engine version in the state:** carried and read back; a state from before 12b reads as 1;
   an unknown version stops the task.
3. **`opening_engine`:** the chain, newest first; nothing asked with one version.
4. **Opening on a release:** `CaseStart.release`, crossing continue-as-new; a package that doesn't
   give its digest refused; the report and the opening line; a draft as before.
5. **Plans from the release:** the deployment's changed plan never reaches a released case.
6. **Wording when shown:** the view and the sheet with a revision; another release's refused; an
   answer's wording on its line.
7. **The guides, D51, and every fixture replaying,** slice 0's and the earlier layers'.

### Promises (draft)

`C` is `tests/test_temporal_case_release.py`, `E` is `tests/test_engine.py` (new), `R` is
`tests/test_releases.py`. Each test is named here before it is written; the table is checked
against the tests before the pull request.

| Promise | Test |
|---|---|
| Histories recorded before 12b replay: paid, waiting, continued as new, a plan step | C `test_histories_from_before_12b_replay` |
| A revert with new wording is refused (or recorded and said, per choice 27); the guide says which | R `test_a_revert_with_new_wording_is_refused` |
| A plan field's source changed is named `fields.<name>.source` | R `test_a_plan_fields_source_is_named_as_written` |
| A state carried before 12b reads as engine 1; the engine version crosses continue-as-new | E `test_a_state_from_before_12b_is_engine_1`, C `test_the_engine_version_crosses_continue_as_new` |
| An engine version the code doesn't know stops the workflow task, never read as an older one | E `test_an_unknown_engine_version_is_refused` |
| `opening_engine` asks newest first, takes the first yes, and means 1 when none says yes; with one version it asks nothing | E `test_the_opening_asks_the_newest_version_first`, `test_one_version_asks_nothing` |
| A case opened on a release records it, with its engine, in the report and its first line; a draft's history is as before | C `test_a_case_opens_on_its_release`, `test_a_draft_is_as_before` |
| A start whose package doesn't give its release's digest is refused, nothing decided | C `test_a_start_that_isnt_its_release_is_refused` |
| A released case runs its release's plans, never the deployment's changed one | C `test_a_released_case_runs_its_releases_plans` |
| The view and the sheet read a wording revision of the case's release; another release's is refused; a decision never changes | C `test_new_wording_is_read_when_shown`, `test_wording_of_another_release_is_refused` |
| An answer's wording is recorded on its line | C `test_an_answer_says_which_wording_it_saw` |
| The guides' examples run as written | C `test_the_guides_release_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new module too | `tests/test_layers.py`, unchanged |
