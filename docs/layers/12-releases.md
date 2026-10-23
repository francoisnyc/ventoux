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
D51, its amendment lines (D5, D27, D28, D50) and the guides' parts written before building; 12b
built, slices 0–7, and its Promises table checked against the tests, the same day (see 12b,
"Decided while building").

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

### Decided while building

- **An answer's wording goes at the end of its line,** as its other parts do: `ana answered
  review#1 approve as support, setting approved_amount, as worded in refund 1, wording 2`
  (choice 26 wrote `ana answered review#1: approve, …`, which isn't how an answer's line reads).
- **A draft refuses an answer naming a wording revision** (slice 6): its line would claim a
  wording nothing can check. Refused and recorded, as every refusal on Temporal is.
- **The worded view is its own query,** `worded_view`, answering a refusal as data, as the sheet
  does: a failure's message is sealed (D31), and the reader must learn why. `view(case, roles)`
  with no wording is the query it was.
- **A case checks its start in every run,** not only the first: a run continued as new checks the
  release it carries again before it reads its state. It costs a digest per run, and depends on
  nothing the previous run did.
- **`FolderStore.get(name, release, wording=1)`,** for the guide's example, refusing a release that
  has no record.
- **Two tests had to be made to bite** (slices 4 and 6): the crossing test first started its plan
  step before any switch, so a release left out of `switch` went unseen; its `settle` is now
  proposed after a switch, on the worker that switches after every event, and the case stays open
  until closed. And the wording refusal had no case where only the digest differs: a revision
  claiming `refund 1` with release 2's behaviour is now refused by its digest alone.
- **A test that starts a case's workflow by hand makes its key first,** as `start_case` does: the
  case's failure is sealed with it (D31), and without it the refusal hung, unsealable.
- **The guide's opening line was wrong:** the engine writes `with amount and order_id`.
- **Each test was seen failing on a deliberate break:** the version check skipped; a deployment's
  plans used; the digest check skipped (at the opening, and for a wording); the release left out
  of `switch`; the draft checks skipped (a wording, an answer); the wording left off a line; an
  older record not recomputed; a stray file in the releases folder skipped; a revert reworded.

### From the tutor review

Built test-first, 2026-10-23.

- **A continued run that can't read its start waits for code** (the request, first part). Every
  run of a released case checks its digest again; on a run that continued as new, a release that
  no longer gives it, from a change to the models method 1 reads, failed the case for good
  (`CaseRefused`, non-retryable), its decisions already made. Now that raises `StartUnread`: the
  workflow task fails, and Temporal retries it until code that reads the start is deployed, as
  for an unknown engine version (D17). At the opening, refusing stays. **`CaseInvalid` on a
  continued run gets the same treatment, here:** a definition that read when the case opened and
  doesn't now is the same kind of thing, a change of code, and it was on `main` already. Tested
  the tutor's way: workers taken in turn, the second giving another digest; the case stays
  running with a failed workflow task, and the third, giving the digest again, lets it go on. The
  test's workers cache no workflow: a cached run's tasks go to its stopped worker's own queue for
  a while, which made the next worker wait.
- **Method 1 pinned** (the request, second part): `tests/digests/method-1.json` keeps method 1's
  digest of every example definition, the example package, and `tests/digests/every-shape`, a
  package written to use what the examples don't (workflow and wait steps, every operator, list
  and outcome fields, sensitive and `visible_to` fields, `forgetting`, `max_age`, a plan with a
  timed wait and approval). It passes validation, so the release tool would release it. One test
  fails if any digest changes, saying a new method is a decision of its own; another fails unless
  every field of every model a case or plan can hold is written, other than at its default, in
  some pinned package, so a model added later must be pinned too. The example package's pin is
  the guide's `89420f53b3d3`.
- **A wording refusal is a field of the sheet's answer** (optional point): `SheetAnswer` gains
  `wording_refused`, as `ViewAnswer` answers a refusal on its own; the client no longer reads the
  start of a message.
- **A plan's own sheet reads the plan as its run started** (optional point): said in D51 and the
  releases guide, a known limit.
- **D51 gains two bullets,** marked as added in the tutor review, before it is merged.
- **Each new test was seen failing on a deliberate break:** the old refusal kept on continued runs
  (both continued-run tests), a key added to the canonical behaviour (the pinned digests), the
  every-shape package left out (the shapes), the sheet's field ignored by the client.

### Promises

`C` is `tests/test_temporal_case_release.py`, `E` is `tests/test_engine.py` (new), `R` is
`tests/test_releases.py`, `D` is `tests/test_digests.py` (new, from the tutor review). Checked
against the tests, 2026-10-23: every test named here exists, and every test `C`, `E` and `D` hold,
and every test 12b added to `R`, is named here.

| Promise | Test |
|---|---|
| Histories recorded before 12b replay: paid, waiting, continued as new, a plan step | C `test_histories_from_before_12b_replay` |
| A package with an older release's behaviour and other wording is refused; with that release's wording back, it is the same as that release; the guide shows the refusal | R `test_a_revert_with_new_wording_is_refused`, `test_the_guide_says_what_a_revert_with_new_wording_gets` |
| A plan field's source changed is named `fields.<name>.source` | R `test_a_plan_fields_source_is_named_as_written` |
| Every record is read again, not only the latest; any other file in a releases folder refuses the run | R `test_every_record_is_read_again_not_only_the_latest`, `test_a_stray_file_in_the_releases_folder_refuses_the_run` |
| A release with no record isn't found, saying so | R `test_a_release_not_recorded_isnt_found` |
| A state carried before 12b reads as engine 1 | E `test_a_state_from_before_12b_is_engine_1` |
| An engine version the code doesn't know is refused, never read as an older one; on Temporal the workflow task fails and the case waits | E `test_an_unknown_engine_version_is_refused`, C `test_an_unknown_engine_version_waits_for_its_code` |
| The opening asks the newest version first, takes the first yes, and means 1 when none says yes; with one version it asks nothing | E `test_the_opening_asks_the_newest_version_first`, `test_one_version_asks_nothing` |
| A case opened on a release says its release and engine, in its report and its first line, with no marker written; a draft's history is as before | C `test_a_case_opens_on_its_release`, `test_a_draft_is_as_before` |
| A start that isn't its release's package is refused, nothing decided | C `test_a_start_that_isnt_its_release_is_refused` |
| The release and engine version cross continue-as-new, and a plan step started after a switch runs the release's plan on a worker that supplies none | C `test_the_release_and_engine_cross_continue_as_new` |
| A released case runs its release's plans, never the deployment's changed one | C `test_a_released_case_runs_its_releases_plans` |
| The view and the sheet show a wording revision of the case's release; without one, its own; nothing decided or recorded changes | C `test_new_wording_is_read_when_shown` |
| A wording of another release, one claiming the release with another digest, or any wording for a draft, is refused | C `test_wording_of_another_release_is_refused` |
| An answer's line says which wording its person read; a draft refuses an answer naming one | C `test_an_answer_says_which_wording_it_saw` |
| The cases guide's release example is what the engine records | C `test_the_guides_release_example_runs_as_written` |
| On a run that continued as new, a release that no longer gives its digest, or a definition that no longer reads, fails the workflow task and the case waits, running; code that reads it again lets it go on; at the opening, refusing stays | C `test_a_continued_run_whose_digest_changed_waits_for_its_code`, `test_a_continued_run_whose_definition_no_longer_reads_waits_for_its_code`, `test_a_start_that_isnt_its_release_is_refused` |
| Method 1 gives the digests it pinned, for packages that between them write every field of the format | D `test_method_1_gives_the_digests_it_pinned`, `test_the_pinned_packages_use_every_shape` |
| `case` reads no clock or I/O and imports no Temporal, in the new module too | `tests/test_layers.py`, unchanged |

## 12c. Change requests

Status: drafted 2026-10-23, from `main` at `5801ca0` (12b merged, #43); the histories from
before 12c recorded and replayed first (slice 0). Answered "all as recommended" the same day:
choices 29 to 41. The warm-up (learning question 37's follow-up) put and not answered, left open.
Built the same day, slices 0 to 7; see "Decided while building" and the Promises table.

User-facing description, written first once you agree: `docs/guides/cases.md`, "Changing an open
case". Decision: brief D52, drafted with it.

### Warm-up: learning question 37's follow-up, what the audit keeps after forgetting

> A regulator asks why claim-7 was denied. After forgetting, which of their questions can you
> still answer, and which not?

Open since 9c. Forgetting is the first change request, and 12c makes it one of several. Answer
from memory first.

### What this part is for

Until now, the only ways a person changes an open case are the ones its definition offers:
answering a task, proposing a step, retrying a failed run, closing it with a declared reason.
Some changes are none of these:

- **a fact is wrong** (Ana typed 2500 for 250), and the step that reads it hasn't run;
- **a failed run can't succeed** (the payment provider closed the account) and nothing else should
  happen in its place, but the case must not close as if it had;
- **the customer asks to be forgotten** (9c built that one);
- **the rules changed**, and an open case should follow them (12d).

D17 says nothing is skipped automatically; D25 that a lapse can only come from a change request;
D32 that forgetting is the first change request and layer 12 makes the mechanism general. 12c
builds that mechanism: a person proposes, a second person approves, and the case applies it,
checking it again against the case as it is then.

A small example. Refund `refund-7` waits for Sam's approval of `pay` at 2500. Ana, who answered the
review, sees she typed 2500 for 250. She proposes an edit; Lee (`support-lead`) approves it. The
history says:

```
ana proposed change#1: edit approved_amount, approved by support-lead
lee approved change#1 as support-lead
applied change#1: approved_amount edited by ana, approved by lee
withdrew pay.approval#1: approved_amount changed
asked pay.approval#2: approval of pay by support-lead
```

Sam's approval of the old value is gone with its entry, and the step asks again on the new value.
Neither 2500 nor 250 appears anywhere in the history.

### What the code does today

Read on `main` at `5801ca0`, before drafting:

- **Forgetting is a request with its own workflow,** `<case ID>/forget` (`temporal/forget.py`): it
  checks the proposer's and approver's roles and that they differ, then signals the case, whose
  `forget` (`case/forgetting.py`) checks both again, depending on nothing the request did. **It
  excludes only the proposer;** the case's opener may approve forgetting it, unlike any of its
  steps (D25).
- **An approval already follows the case file** (`case/approvals.py`, `follow`): when a value a
  step reads changes, its open entry is withdrawn, every approval on it at once (D47), and a given
  approval lapses, the step asked again. So an edit needs no new lapse code, only a value that
  changes.
- **D25's "a lapse from a change request stops the step"** is `lapsed`, which stops a step whose
  inputs changed between the decision that gave its approval and the start: today nothing can come
  between them.
- **A run records who may not approve it** (`StepRun.excluded`: the people its `when`, its inputs
  and its starting rule read, D11, D39), and a failed run has no way out but a retry or a close
  (D26).
- **Answers name an entry** (`review#1`, `pay.approval#1`), and the inbox decides them in order.

### Choices for 12c

Numbered on from 12b's. Answer by number.

29. **Where a request lives: in the case's own workflow.** A request is an entry of the case,
    `change#1`, `change#2`, numbered by the case, proposed by a signal and answered like any entry
    (`answer(case, "change#1", "approve", …)`); its state, pending until answered, is the case's,
    so it crosses continue-as-new with the rest (D27), and the case's history tells the whole
    story. **Forget keeps its own workflow,** since a closed case can be forgotten (its workflow
    has ended, nothing to signal) and the key is destroyed only after the case's workflow ends,
    outside it (brief, D32); it shares the rules (choices 31–33) through the same module.
    *Recommended.* Set aside: a workflow per request, as forget has (the case's
    history would show only the apply, and a pending request would be another workflow to find);
    moving forget into the case (its request's history must outlive the key, 9c).

30. **One lifecycle, kinds as data.** proposed → (approved → applied | not applied) | rejected |
    cancelled. A request names its kind and what it changes: `edit` (a field and its new value),
    `skip` (a failed run), and, in 12d, `migrate` (a release and its mapping). Each kind is three
    pure functions in `case`: what it refuses when proposed, who it excludes from approving, and
    what it does when applied; the lifecycle around them is one, so 12d adds a kind without
    touching it. *Recommended.*

31. **Who may propose and approve: a role registered for the kind,** as forgetting is (D32):
    `register_role(..., edits=True)` for an edit (new); for a skip, an operating role
    (`operates=True`, D26: operators act on failed steps, D17); `forgets=True` for forgetting, as
    today; `migrates=True` in 12d. Proposer and approver each hold one, stated with their message
    (D22), and are people, never a system (an identifier, checked as for an answer). One approver;
    a count on requests is set aside until a kind needs it (D47's shape would fit). *Recommended.*

32. **Never approved by the proposer or the case's opener, and what else D11 and D25 exclude.**
    Excluded from approving a request, whatever its kind: the person who proposed it, and the
    person who opened the case (D25: the opener approves none of its steps, and a change decides as
    much as a step's run). And, by kind:
    - **an edit:** also each person whose answer gave the field its current value (D11: whoever's
      answer flows in): the edit overrules them;
    - **a skip:** also everyone excluded from approving the failed run (its `excluded`: the people
      its `when`, its inputs and its starting rule read, D11, D39), whoever proposed it (D25), and
      whoever approved it (D47's approvers): skipping decides that run's fate as approving it did.

    Refused, recorded, and the request waits on, as a refused approval does. **The curriculum's
    negative test lands here:** a self-approved edit and a self-approved skip, each refused,
    saying who proposed it. *Recommended.*

33. **Forgetting gets the same exclusions, as engine version 2.** Adding the opener to forget's
    exclusions changes what a recorded history decides (an opener who approved a forget would now
    be refused), so D51 makes it the next engine version: `KNOWN = (2, 1)`, a case opened under 12c
    records version 2 at its opening (one patch marker in its history, D51's chain), and a case
    opened before keeps 9c's rule, its old branch kept behind `state.engine`. Its fixture: a
    forget approved by the opener, recorded under `main`, still replays. The first real use of
    D51. *Recommended.* Set aside: leaving forget with the proposer alone excluded (two rules for
    the same act of approving a change, and the weaker one for erasure).

34. **Checked when proposed, and again when applied, against the case as it is then.** A proposal
    is refused at once, recorded and nothing pending, if: the case is closed or closing; the field
    isn't a declared case-file field (an outcome or an output is a record of what happened, never
    edited); the value isn't the field's type (as an answer's form, strictly, G6); a sensitive
    value comes unsealed (D31); the value is the one the field already holds (choice 37); the run
    to skip isn't its step's latest run, or isn't failed. When the approval comes, every check runs
    again on the case then, and one more: **what the request was proposed against hasn't
    changed** (the field's value, kept as a digest, never the value; the run still failed). If it
    has, the request isn't applied, saying why (`change#1 not applied: approved_amount changed since
    it was proposed: propose it again`): the approver judged a correction of a value that is gone.
    Depending on nothing the proposal's check did (D34). *Recommended.*

35. **What applying an edit does.** The field takes the value, obtained at the event's time by no
    run (D33). Then the case decides as after any change of value: open approvals reading it are
    withdrawn, every approval on the entry at once (D47); a given approval lapses, and its step is
    asked again. **Asked again, never needing attention:** D25's "a lapse from a change request
    stops the step" is kept as "the step doesn't start on that approval", and an amendment line
    says so, as D33 did for a refresh: the change was approved by a second person, so a new
    approval on the new value is the next step, not an operator. A running step keeps the inputs it
    started with (D10). No rule fires on it (D42: there is no "field set" moment). *Recommended.*

36. **What applying a skip does.** The failed run ends `skipped`: neither done nor failed, as a
    stopped run is `cancelled` (D40). So `requires` doesn't count it as done, it reaches nothing,
    gives no outcome or output, fires nothing, and its timers end with it (D44); its step may run
    again only as any step may (repeatable, proposed). A close it held completes (D34), and a case
    with nothing else pending closes. Set aside: skipping as `done` (steps requiring it would run on
    a result that never was).

37. **What an edited value carries as its source, and never making untrusted data trusted.** Its
    sources are `person:<proposer>` and `person:<approver>`, both of whom decided it, so D11
    excludes both from approving any step that reads it, by its sources alone. A field declared
    untrusted keeps its mark (`untrusted:customer` is added to every writer's stamp, as today). An
    edit never carries the old value's sources, and never re-stamps the old value: an edit to the
    value the field already holds is refused when proposed and when applied (`approved_amount
    already holds that value: an edit changes it`), since its only effect would be to make an
    untrusted value read as a person's (the prototype's laundering, research 5). A new value is a
    person's decision, where untrusted influence ends (D43). *Recommended.*

38. **What the history says,** at each step, naming people, roles, fields, runs and requests,
    never a value:
    - proposed: `ana proposed change#1: edit approved_amount, approved by support-lead`;
      `omar proposed change#2: skip pay#1, approved by operations`;
    - refused: `refused sam's answer approve to change#1: ana proposed change#1, so cannot approve
      it`, and the same shapes for the opener and the other exclusions;
    - rejected: `lee rejected change#1 as support-lead`;
    - applied: `applied change#1: approved_amount edited by ana, approved by lee`, then the
      lines its effects bring (`withdrew …`, `lapsed …`, `asked …`); `applied change#2: pay#1
      skipped by omar, approved by olu`, then `pay#1 skipped`;
    - not applied: `change#1 not applied: …: propose it again`;
    - cancelled: `cancelled change#1: the case is closing`.

    `waiting_for` shows a pending request as `approval of change#1 (edit approved_amount) by
    support-lead`, the same to everyone. *Recommended.*

39. **A pending request is not pending work** (D10): it doesn't keep the case open, as listening
    doesn't (D41). When the case begins closing, each pending request is cancelled, saying so,
    except a skip of the run that holds the close (D34): that is the one request a held close
    takes, and the way out D17 promises. *Recommended.* Set aside: a request holding the case open
    (an edit nobody answers would keep a finished case open for ever).

40. **On Temporal.** Proposing is a signal, `propose_change`, as answering is; requests are decided
    in the order history records them, one at a time. Pending requests are in the state, so they
    cross continue-as-new (a state carried before 12c has none); an edit's sensitive value crosses
    sealed, as an answer's form does (D31). **Edits and skips are new events on new paths,** so no
    recorded history decides differently and they need no engine version (D51); forgetting's
    exclusions do (choice 33). Fixtures: histories recorded before 12c replay, recorded first;
    a pending request crossing continue-as-new; and choice 33's forget. *Recommended.*

41. **Where it is recorded:** D52 ("Change requests: one mechanism, proposed, approved by someone
    else, checked again and applied"), with dated amendment lines on D11, D17, D25, D26, D32 and
    D51. The cases guide's "Changing an open case" written first, its example run by a test. No
    new dependency. *Recommended.*

### The negative tests

| Negative test | Where |
|---|---|
| A self-approved change (the curriculum's) | an edit and a skip, each refused, recorded, the request waiting on |
| The case's opener approving a change | refused, for an edit, a skip, and a forget on a case opened under 12c |
| An edit that would launder an untrusted value | the same value refused, proposed and applied |
| An edit approved after its field changed | not applied, saying so |
| A skip of a run that no longer failed (retried meanwhile) | not applied |
| An edit of an outcome or an output | refused when proposed |

### Seams the tests use

- `run_case(...)` with a script's `edit(field, value, by)` and `skip(run, by)`, and answers to
  `case.change#n`; `history`, `waiting_for`, `needs_attention`, `closed`, `state`.
- `parse_case`, `decide` (for what a script can't send: a value in plain text, a later run beside
  a failed one), and the catalog's `register_role(..., edits=True)`.
- On Temporal: `propose_change(case, kind, target, value, by, roles)`, `answer(case,
  "case.change#1", …)`, `report`, the `Replayer` on fixtures recorded before 12c, and a forget
  request (`propose_forget`, `answer_forget`).
- The guide's examples, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Histories recorded before 12c,** replayed: a case with an approval given, one that continued
   as new, a forget approved by someone who isn't the opener, and, for choice 33, one approved by
   the opener.
1. **The lifecycle, in memory:** a request proposed, refused when self-approved, rejected, applied;
   the case's opener excluded.
2. **Edits:** the checks when proposed and applied; the value's sources; the lapses; the laundering
   refusal; outcomes and outputs refused.
3. **Skips:** the exclusions from the run; `skipped` and what it means for `requires`, the close
   it held, its timers.
4. **Pending requests and the close:** cancelled, except the skip a held close takes.
5. **On Temporal:** signals, continue-as-new, sealed values, the fixtures.
6. **Forgetting under the same rules:** engine version 2, its marker, the old branch.
7. **The guide, D52, the Promises table checked.**

### Decided while building

- **Requests are `case.change#1`, not `change#1`:** a name is `[a-z][a-z0-9_]*`, so a step may be
  named `change`, and its runs would share the entries. A dot no name holds keeps them apart, as
  `pay.approval#1` does. Reserving `change` instead would refuse a definition that reads today,
  which on a continued run is a change of behaviour (D51).
- **The lines, as built:** a proposal says `to be approved by support or support-lead` (choice 38
  wrote `approved by`, which reads as done); an approval's line is an answer's, `lee answered
  case.change#1 approve as support-lead`, as for an approval; a rejection adds `case.change#1 not
  applied: lee rejected it`. Skipping adds no line beyond `applied case.change#1: pay#1 skipped by
  omar, approved by olga`.
- **Nobody proposes or approves an edit of a field hidden from them** (D30: an approver judges
  what they see), which the choices didn't list; and **an edit of a field that holds no value
  yet is refused:** it would give a first value no step asked for.
- **An approval spent on a failed run lapses with the edit.** It stays with the run for its retry
  (D26), so `follow` never sees it, and the retry would stop on it for ever (`the inputs of pay
  changed since sam approved them`), keeping it each time. The edit lapses it (`lapsed
  pay.approval#1: approved_amount changed`), and the retry asks again: choice 35's "asked again,
  never needing attention", for the one approval the existing code didn't follow.
- **The request to forget asks who opened the case,** when someone approves, from the case's
  start (a new activity, `ventoux.forget.opener`, behind the patch `ventoux-forget-opener`, so
  the request recorded in slice 0 replays). Without it, a request whose approval the case
  refuses would wait for the case to end, then destroy its key when it closed for any other
  reason. It refuses anyone if who opened the case can't be told. So a request proposed now
  refuses the opener on an engine 1 case too; the case's engine 1 branch decides only histories
  approved before.
- **Every new case writes the marker `ventoux-engine-2`,** a draft included: the engine decides
  drafts too. 12b's tests that said no marker is written now say this one is; the version they
  call unknown is 3.
- **A held close takes edits too:** they start nothing. Choice 39's exception is the held close
  (open, its milestones reached); a close that has begun cancels the failed run itself, and with
  it any skip of it. A case closing with nothing left to do cancels its pending requests too:
  `cancelled case.change#1: nothing left to do`.
- **Not built:** skipping a failed rule's firing. It holds a close as a failed run does, and is
  retried, or the case closed (D38); a kind for it is one more function when it is needed.
- **The guide's Temporal example passes `Decimal("250")`:** written `250`, it was refused (`the
  edit gives an int`) when the test ran it, as numbers are exact decimals (D20).
- **The development catalog lets `support` and `support-lead` edit,** so the guide's Ana proposes
  and Lee approves.

### Promises

Checked against the tests before the pull request. `Q` is `tests/test_change_requests.py`, `T` is
`tests/test_temporal_change_requests.py`, both new. Each test was seen failing for the right
reason, or, where the seam already held the rule, the rule was taken out and its test seen
failing.

| Promise | Test |
|---|---|
| A change is never approved by its proposer, nor by the case's opener | Q `test_a_self_approved_change_is_refused`, `test_a_self_approved_skip_is_refused`, `test_the_opener_approves_no_change`, `test_a_skip_excludes_who_the_run_excluded` |
| A kind, an outcome or a role the engine doesn't know is refused | Q `test_what_a_request_doesnt_know_is_refused` |
| A rejected request changes nothing, and is closed | Q `test_a_rejected_change_changes_nothing` |
| An edit excludes whoever's answer gave the field its value, and anyone it is hidden from | Q `test_an_edit_excludes_the_values_writer`, `test_an_edit_is_judged_by_people_who_see_it` |
| A skip excludes whoever the failed run excluded, proposed or approved, and whoever's answer flows into it | Q `test_a_skip_excludes_who_the_run_excluded` |
| A request is checked when proposed and again when applied, against the case then | Q `test_a_proposal_is_checked_when_made`, `test_an_edit_whose_field_changed_is_not_applied`, `test_only_a_failed_latest_run_is_skipped`, `test_a_skip_of_a_run_retried_meanwhile_is_not_applied` |
| An edited value's sources are its proposer and approver, so neither approves a step reading it; a declared untrusted mark stays | Q `test_an_edited_value_is_its_deciders` |
| An edit to the value already held is refused, proposed and applied, so an untrusted value is never made a person's | Q `test_an_edit_never_launders_a_value` |
| An outcome or an output is never edited | Q `test_a_record_of_what_happened_is_never_edited` |
| A sensitive field's new value is sealed, refused in plain text, and in no history | Q `test_a_sensitive_value_is_edited_sealed`, T `test_a_sensitive_edit_crosses_sealed` |
| An edit withdraws open approvals that saw the old value, every approval on the entry, and lapses an approval spent on a failed run; the step is asked again | Q `test_an_edit_withdraws_and_lapses_what_saw_the_old_value` |
| A skipped run is neither done nor failed: `requires` doesn't count it, it gives nothing, its timers end | Q `test_a_skipped_run_is_neither_done_nor_failed`, `test_a_skipped_runs_timers_end_with_it` |
| A held close takes a skip of the run holding it, and completes | Q `test_a_skip_lets_a_held_close_complete` |
| A pending request doesn't hold the case open, and is cancelled when it closes | Q `test_a_pending_request_is_cancelled_by_the_close` |
| The history says each step, naming no value | Q `test_the_history_names_no_value` |
| On Temporal, a refused proposal or approval is recorded and the request waits on | T `test_refused_changes_are_recorded_and_the_case_waits_on` |
| On Temporal, a pending request crosses continue-as-new and replays; histories recorded before 12c replay | T `test_a_pending_request_crosses_continue_as_new`, `test_histories_from_before_12c_replay` |
| From engine 2 the case refuses its opener's forget; a case opened at engine 1 keeps 9c's rule, and its history replays | Q `test_forget_excludes_the_opener_from_engine_2`, T `test_the_case_refuses_its_openers_forget_from_engine_2`, `test_histories_from_before_12c_replay` |
| The request to forget refuses the opener's approval, or anyone's if who opened the case can't be told | T `test_a_request_to_forget_refuses_the_opener`; `tests/test_temporal_forget.py` `test_the_guides_refusals_are_what_the_engine_says` |
| New cases open at engine 2, with its marker; version 3 is unknown | `tests/test_temporal_case_release.py` `test_a_case_opens_on_its_release`, `test_a_draft_is_as_before`; `tests/test_engine.py` `test_an_unknown_engine_version_is_refused` |
| The guide's examples run as written | Q `test_the_guides_change_example_runs_as_written`, T `test_the_guides_temporal_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new module too | `tests/test_layers.py`, unchanged |

## 12d. Migrations

Status: drafted 2026-10-23, from `main` at `66e2cff` (12c merged, #44); the histories from
before 12d recorded and replayed first (slice 0). Answered the same day: choices 42 to 59, all as
recommended, with three changes, written into choices 43, 45, 55 and 57 below, each marked
*Changed in the answers*. The warm-up (learning question 34's follow-up) put and not answered,
left open. Built the same day, slices 0 to 10; see "Decided while building" and the Promises
table.

User-facing description, written first once you agree: `docs/guides/releases.md`, "Moving open
cases to a later release", and the cases guide's "Changing an open case" gaining its third kind.
Decision: brief D53, drafted with it.

### Warm-up: learning question 34's follow-up, why keep the static check

> If the runtime check catches everything with the real sources, why keep the static one at all?

Open since layer 5; "who hears of it" hasn't come back yet. It is 12d's question too: a
migration is previewed before anyone approves it, and checked again when it is applied. Answer
from memory first.

### What this part is for

A case runs the release it opened on, to the end (12b). Sometimes the business can't wait for the
end: a fraud check is now required before every payout, and three hundred refunds are open on
`refund 1`. 12d moves an open case to a later release, as one more kind of 12c's change request:
someone proposes it, someone else approves it, the case checks it again and applies it.

A small example. `refund 2` adds `fraud_check`, which `pay` now requires, renames the field
`approved_amount` to `amount_approved`, and chases a review after 3 days instead of 2. Refund
`refund-7` is on `refund 1`, its review answered, `pay.approval#1` open. Pia proposes the
migration with its mapping, `{"fields": {"approved_amount": "amount_approved"}}`; Lee approves it:

```
pia proposed case.change#1: migrate to refund 2, to be approved by platform
lee answered case.change#1 approve as platform
applied case.change#1: migrated from refund 1 to refund 2, engine 2, proposed by pia, approved by lee
renamed field approved_amount to amount_approved
withdrew pay.approval#1: refund 2 changed pay
started fraud_check#1: …
```

Nothing Ana answered is lost, nothing is quoted, and a payment waiting for its approval now waits
for the fraud check too. Had `pay#1` been running on `payments.refund@2` while `refund 2` called
`@3`, the migration would be refused, saying to migrate after it finishes: never terminated.

### What the code does today

Read on `main` at `66e2cff`, before drafting:

- **A case's definition lives outside its state:** the workflow keeps it, with the release and its
  plans (`CaseWorkflow.case`, `release`, `its_plans`), and `switch` carries them across
  continue-as-new in the start (D27, D51). `decide` takes the definition as its first argument, so
  nothing in the state can change it.
- **A run's entry and its step are apart** (`StepRun.entry`, `StepRun.step`): the entry names the
  run's key (`refund-7/…/pay#1`), and the next entry counts the step's runs. So a step can be
  renamed while its run keeps its entry and its key.
- **Everything else the state holds is by name:** values by field (`pay.outcome` for an outcome,
  `pay.refund_id` for an output, `cancelled.note` for a payload), milestones, approvals and their
  counts by step, proposers, timers by rule and the moment they were set on, firings by rule,
  arrivals by event, change requests by target.
- **12c's change requests** (`case/requests.py`) are one lifecycle with kinds as data; each kind is
  what it refuses when proposed, who it excludes, and what applying it does. `migrates=True` was
  left for 12d.
- **The engine version** is set once at the opening, from patch markers (12b). A run memoises a
  patch's answer, so a marker can't be asked a second time in a run.

### Choices for 12d

Numbered on from 12c's. Answer by number.

42. **A migration is one more kind of change request, `migrate`,** with 12c's lifecycle: an entry
    `case.change#n`, answered approve or reject, checked again when applied, cancelled if the case
    closes first. Proposed and approved by a role registered for it, `register_role(...,
    migrates=True)`, never by a system or a rule. Excluded from approving it, as from every change:
    its proposer and the case's opener (D52). **The curriculum's negative test: a self-approved
    migration, refused,** saying who proposed it. *Recommended.* Set aside: a request approved
    once for a cohort (below, choice 55).

43. **What a request carries, and what the case checks of it.** The target release as its record
    gives it (name, number, digest, case and plans), the mapping (choice 44), and the engine
    version to move to (choice 53). The case refuses it, at once and again when applying, if: the
    case is closing or closed; the target's package doesn't give the digest it comes with (D51),
    or is another package's (`claim 3` for a refund); a contract or plan it names isn't in
    the worker's catalog; it moves neither the release nor the engine. A draft may migrate to a
    release (its line says `from draft`); a migration back to an earlier release is a migration
    like any other. *Recommended.* *Changed in the answers:* the case checks that **the target's
    package gives its digest, not that the digest is the store's release:** a request comes
    through the trusted API, built from the release store (D19), and 12e's environment registry is
    where the case can check the release itself. D53 says so.

44. **The mapping, by names, never positions** (D2, D5; research 4.1). Data, one section per kind
    of name: `steps`, `milestones`, `fields`, `rules`, `events`, each `{"old": "new"}`. A name not
    in the mapping keeps its name. Timers are named by their rule and the moment they were set on,
    so they follow the `rules`, `steps` and `milestones` sections. Refused: a section it doesn't
    know; an old name the case's release doesn't declare; a new name the target doesn't declare,
    or declares as another kind; two old names mapped to one. No condition, no expression, nothing
    evaluated. *Recommended.*

45. **What refuses a migration: a name something depends on, gone from the target and unmapped.**
    **The curriculum's negative test:** `refund 2` renames `pay` to `payment`, the mapping doesn't
    say so, and `pay#1` is running: refused, `pay#1 is running, and refund 2 has no step pay: map
    it, or migrate after it finishes`. What depends on a name:
    - a step: any run of it, in any status, since its outcome and outputs are in the case file;
    - a milestone: reached, since a milestone is never undone (D48);
    - a field: a value in the case file, of the same type in the target (a value never converted);
    - a rule: a failed firing waiting for a person, or a start it asked for not yet taken up;
    - an event: a wait open for it, or a value it carried;
    - and nothing loosens on the way: a field holding a value may not lose `sensitive`, widen
      `visible_to`, or change its type (stricter is taken, never looser).
    - *Changed in the answers:* **what a finished run or an arrival recorded must be what the
      target can hold.** A done run's outcome is one the target's step declares (a task's
      outcomes, its contract's, or a plan's `done` and `failed`); its outputs are the target
      contract's, same names and types; an event's carried payload is declared by the target's
      event, same names and types. Values are never converted.
    Each problem is said, with what to map or what to wait for, all of them at once. *Recommended.*
    Set aside: dropping a name and its values on request (the prototype's `null`): a value a
    person gave would go, and its provenance with it.

46. **Running work finishes under what it started with** (D10; research 5.3). A running run keeps
    its entry and its key; its result lands under the mapped names. Refused unless its step, in
    the target, is the same kind calling the same contract (or plan): a result checked against
    another contract than the one that ran would be wrong (`pay#1 is running payments.refund@2,
    and refund 2's pay calls payments.refund@3: migrate after it finishes`). A running plan
    finishes on the plan in its start (D28): plans don't migrate. *Recommended.*

47. **Open tasks, waits and failed runs stay, under the target's rules.** An open task's step
    stays a task: it is answered as the target says (its outcomes, roles, the fields it sets); a
    wait stays a wait for its mapped event; a failed run's step calls the same contract, since its
    retry is the same run with the same key (D26), and it is retried, skipped or the case closed,
    as before. A step that changed kind under an open or failed run is refused. *Recommended.*

48. **Approvals: kept only if what they approved is unchanged.** An open approval, one given and
    not yet spent, and one spent on a failed run stay if the step, names mapped, is the same
    behaviour in the target (its method 1 digest, D50); otherwise each is withdrawn or lapses,
    every approval on its entry at once (D47), saying so (`withdrew pay.approval#1: refund 2
    changed pay`), and admission asks again under the target. *Recommended.* Set aside: comparing
    only what the approval read (a changed approval rule, more approvers, would then keep an
    approval the target asks differently).

49. **Timers.** A timer whose rule keeps its name (mapped), its moment and its age keeps its due
    time. One whose rule changed its age is measured again from when it was set (`since` plus the
    new age); if that has passed, it fires right after the migration, stamped with the
    migration's time, saying so: a timer never fires in the past. One whose rule is gone, or now
    waits on another moment, is cancelled, saying so; nothing is set for a moment that came
    before the migration. *Recommended.* Set aside: refusing any change to a set timer (an SLA
    change is a common reason to migrate); keeping the old due time silently (the prototype's).

50. **Pending change requests and events in flight.** A pending edit follows the field mapping
    (its target renamed), a pending skip keeps its run's entry, and both are checked again when
    applied, as always; another pending migration, proposed against the old release, isn't
    applied when approved (`the case moved to refund 2 since it was proposed: propose it again`).
    An event is decided under the release current when its turn comes: one the target renamed,
    sent under its old name, is refused and recorded, as any undeclared event (D41); the preview
    names the events a target renames, for their senders. *Recommended.*

51. **After the migration, the case decides again, under the target.** Admission reads every
    condition again (research 4.6), so a step the target adds may start, and one it now requires
    waits; a `closes_when` reached closes the case, or holds the close (D34). A migration isn't a
    moment for rules (D38's moments stay as they are): no rule fires because of it. *Recommended.*

52. **Values keep their sources, never re-stamped** (D43; research 5.3). A mark the target
    declares on a field is added to its value's sources, as every writer's is (D12); a mark the
    target drops stays on values already written. So a migration never makes untrusted data
    trusted. *Recommended.*

53. **The engine version a migration moves to is data in the request** (D51). Its proposer's
    client sends the version it was built with (`ENGINE`); the case refuses one its code doesn't
    know, or one older than its own (the engine never goes back), and records it, so a replay
    reads it from the history. A migration may move the engine alone, keeping the release: how an
    open case adopts a later engine. *Recommended.* Set aside: asking patch markers at the
    migration (a run memoises a marker's answer from the opening, so a migration in that run
    couldn't move the engine).

54. **What the history says,** naming people, roles, releases, engine versions, names and entries,
    never a value: the request's lines as 12c's (`pia proposed case.change#1: migrate to refund
    2, to be approved by platform`); when applied, `applied case.change#1: migrated from refund 1
    to refund 2, engine 2, proposed by pia, approved by lee` (or `engine 1 to engine 2`), then one
    line for each thing it did: a name renamed, an approval withdrawn or lapsed, a timer kept on a
    new due time, fired late or cancelled. When not applied, why, all at once. The report's
    `release` and `engine` read the new ones. *Recommended.*

55. **A preview, case by case and across a cohort, with no side effect.** One pure function does
    the migration's decision on a copy of a case's state; the preview returns what it would say
    (the lines of choice 54, or every refusal), and the apply runs it again on the case as it is
    then, depending on nothing the preview said (D34). On Temporal the preview is a query (read,
    never recorded); a client function previews every case it is given, and lists the open cases
    of a workflow type through Temporal's visibility; each case is in the result, with what it
    would get or why not, a case it can't read included: none skipped silently (research 5.4).
    *Changed in the answers:* the cohort is **the case IDs it is given.** Temporal's time-skipping
    test server doesn't implement `ListWorkflowExecutions` (the tutor checked), so finding the
    open cases of a release comes with 12e's environment registry; the note and the guide say so.
    Each case then gets its own request, approved on its own: the approver's one decision is sent
    as one answer per case, each case checking it for itself. *Recommended.* Set aside: one
    request for the cohort (the cases would trust what another workflow checked).

56. **Graduating a strict workflow to a looser case lands in 12d** (D2), as the guide's story, with
    nothing new in the engine: `refund 1` is a `sequence` (each step requires the one before and
    starts by itself); `refund 2` lets support propose `call_customer` at any time and makes the
    letter optional. A case half-way through `refund 1` migrates, and what it may do next is the
    target's. *Recommended.*

57. **On Temporal.** Applying a migration gives the driver one more command, `UseRelease`: its
    definition, release and plans replace the workflow's, and cross every continue-as-new in the
    start; a running plan child keeps its own. A pending migration crosses continue-as-new in the
    state, its target with it. Histories recorded before 12d replay, recorded first; a migrated
    case's history replays; a migration request pending across a switch is applied in a later run.
    Not a new engine version: a migration is a new event on a new path (D51). *Recommended.*
    *Changed in the answers:* as in 43, the case checks the target's package gives its digest; the
    release itself is the trusted API's to vouch for until 12e.

58. **From #44's review: a case that closes without reaching its `closes_when` says so.** Its close
    line names what it didn't reach: `closed: nothing left to do; paid not reached`. A line, not a
    decision, so no engine version: replay compares what the case does, not what its history
    says. A skip is the usual way there, and 12d makes it likelier (a migrated case may drop a
    step). *Recommended,* as a slice of its own.

59. **Where it is recorded:** D53 ("Migrations: one more change request, by names, refused never
    terminated, previewed"), with dated amendment lines on D2, D5, D44, D51 and D52; the releases
    guide's "Moving open cases to a later release" and the cases guide's third kind written first,
    their examples run by tests. No new dependency. *Recommended.*

### The negative tests

| Negative test | Where |
|---|---|
| A self-approved migration (the curriculum's) | refused, recorded, the request waiting on |
| An unmapped rename that running work depends on (the curriculum's) | refused, proposed and applied, saying what to map |
| A reached milestone, a value, a failed run, an open task the target lacks | refused, each said |
| A running run whose step calls another contract in the target | refused: migrate after it finishes |
| A target whose package doesn't give its digest, another package's, or naming a contract the worker lacks | refused |
| A done run's outcome or outputs, or an event's payload, the target can't hold (from the answers) | refused: values are never converted |
| An engine version the case doesn't know, or older than its own | refused |
| A mapping naming what doesn't exist, or two names to one | refused |
| A field that would lose `sensitive` or widen `visible_to` | refused |
| A preview with a side effect | none: the preview leaves the case's history as it was |

### Seams the tests use

- `run_case(...)` with a script's `migrate(record, mapping, by)`, `release=` to open on a release
  and `engine=` for its version; answers to `case.change#n`; `release_of(definition, number,
  plans)` to release a definition in memory; `history`, `waiting_for`, `timers`, `state`.
- `preview_migration(case, catalog, state, migration, at)` and `migration_of(record, mapping,
  engine)`, pure; `decide`, for a state a script can't reach (an approval given and waiting).
- On Temporal: `propose_migration(case, record, mapping, by, roles)`,
  `preview_migrations(client, workflow, ids, record, mapping)`, `report`, the `Replayer` on
  fixtures recorded before 12d.
- The guides' examples, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Histories recorded before 12d,** replayed: a released refund waiting for its approval, one
   that continued as new, a pending edit across a switch.
1. **The kind:** a migration proposed, refused when self-approved, applied on a target with
   nothing renamed; the target checked; the engine moved.
2. **The mapping and what depends on names:** renames, and every refusal of choice 45.
3. **Running work, open tasks, waits and failed runs.**
4. **Approvals and timers.**
5. **Pending requests, events, and deciding again after.**
6. **The preview, in memory.**
7. **On Temporal:** `UseRelease`, continue-as-new, the preview query and the cohort, the fixtures.
8. **Graduating a strict workflow.**
9. **#44's close line.**
10. **The guides, D53, the Promises table checked.**

### Decided while building

- **What waits on a step refuses its removal too:** an approval asked or given, a person's
  proposal, a rule's start (choice 45 listed runs; these wait on the step as much). A gone
  step's runs are said once, by its latest run.
- **`visible_to`: only what a field declares may not widen.** A field with none is seen by every
  role its case names (D30), so `refund 2` adding a fraud check for the `fraud` role widened
  every such field, and refused every migration that adds a role. A field declaring
  `visible_to` may not drop it or add a role; one declaring none follows the target.
- **An approval's step is compared word for word, what it requires included:** a `sequence` says
  a step's requirements outside it, so the comparison reads them too; a renamed step, or one
  reading a renamed field, is changed, and its approval withdrawn (never kept on a guess).
- **A pending edit's digest names its field** (12c's): across a rename, one still on the value it
  was proposed against has its digest taken again under the new name; one whose field changed
  meanwhile keeps its old digest, and isn't applied. 12c's formula is unchanged, so edits pending
  when 12d is deployed are read as before.
- **One applied line:** `applied case.change#1: migrated from refund 1, engine 2 to refund 3,
  engine 2, proposed by pia, approved by lee`, the same whether the release, the engine or both
  move (choice 54 had two forms). A refusal names a run's state as people say it: `pay#1 failed`,
  `pay#1 is running`, `pay#1 was skipped`.
- **The preview decides as the apply does,** through the end of `decide`, factored out as
  `decide_again`, so it says what the case does after (the fraud check starting, a close); its
  first line is `from refund 1, engine 2 to refund 3, engine 2`, since nobody has proposed it
  yet. It lives in the runtime, beside `decide`. A closed case's preview is refused.
- **`decide` gives a command, `UseRelease`,** once a migration is applied: the rest of that
  decision is the target's, and the driver (in memory and on Temporal) decides with the target
  from then on. The case workflow keeps its definition as data for the next run's start, and its
  loop reads the definition it has now, never the one it opened with.
- **A timer moved into the past is due at the migration's time,** so it fires right after it,
  stamped then. Its test caught the moment compared the wrong way round (the old one is renamed
  into the target's names, never the target's into the old).
- **`sent_by` moves next to the declared event** (`case/definition.py`), so a migration can say a
  wait's sender without importing the runtime.
- **The development catalog registers `platform` to migrate.** The listings of the registered
  roles that two tests and two guides' tables quote now name it.
- **Graduating needed nothing new in the engine:** its story test passed as written, which is
  D2's claim.

### Promises

Checked against the tests before the pull request. `Q` is `tests/test_migrations.py`, `T` is
`tests/test_temporal_migrations.py`, both new. Each test was seen failing for the right reason,
or, where the code was written with the seam, the rule was taken out and its test seen failing.

| Promise | Test |
|---|---|
| A migration is never approved by its proposer (the curriculum's), nor by the case's opener (12c) | Q `test_a_self_approved_migration_is_refused` |
| A migration moves the release and engine, and the case decides as the target from then on | Q `test_a_migration_moves_the_case` |
| A target is checked: a role that may migrate, the same package, a package giving its digest, contracts in the catalog, something to move | Q `test_a_target_is_checked` |
| The engine moves forward only, as data; it may move alone | Q `test_a_target_is_checked`, `test_the_engine_moves_forward_only` |
| Names map by name, never position; a run keeps its entry and key; a bad mapping is refused | Q `test_names_map_by_name`, `test_a_bad_mapping_is_refused` |
| An unmapped rename that running work depends on is refused, proposed and applied (the curriculum's) | Q `test_an_unmapped_rename_running_work_depends_on_is_refused` |
| What depends on a name refuses: a milestone, a value, an outcome, an output, a payload, a failed rule, what waits on a step; values never converted; nothing loosens | Q `test_what_depends_on_a_name_refuses`, `test_what_waits_on_a_step_refuses_its_removal` |
| Running work finishes under what it started with, or the migration waits for it; plans don't migrate | Q `test_running_work_finishes_on_its_contract`, `test_a_running_plan_finishes_on_its_plan` |
| Open tasks and waits stay, under the target's rules and lines | Q `test_open_and_failed_runs_stay`, `test_an_open_wait_stays_on_its_event` |
| Approvals stay only if their step is unchanged; every approval on an entry goes at once; spent and given ones lapse | Q `test_changed_steps_lose_their_approvals`, `test_a_given_approval_lapses_with_its_step` |
| Timers keep, move or cancel, saying so, never firing in the past; they follow renamed moments | Q `test_timers_across_a_migration`, `test_a_timer_follows_its_renamed_milestone` |
| Pending edits follow their field; a migration against a left release isn't applied; events decide under the current release | Q `test_pending_requests_and_events_across_a_migration` |
| The case decides again after; no rule fires on the migration | Q `test_the_case_decides_again_under_the_target` |
| Values keep their sources; a target's mark is added, never removed | Q `test_values_keep_their_sources` |
| The history says each step, naming no value | Q `test_a_migrations_history_names_no_value` |
| The preview says what the apply would do, with no side effect; a cohort preview names every case given | Q `test_the_preview_is_the_apply_without_effect`, T `test_a_cohort_preview_names_every_case` |
| On Temporal, a migrated case runs the target across continue-as-new, and replays; histories from before 12d replay | T `test_a_migrated_case_runs_its_new_release`, `test_histories_from_before_12d_replay` |
| A strict workflow graduates to a looser case | Q `test_a_strict_workflow_graduates` |
| A case closing without its `closes_when` says which it didn't reach (#44's review) | Q `test_a_close_names_what_it_didnt_reach` |
| The guides' examples run as written | Q `test_the_guides_migration_example_runs_as_written`, T `test_the_guides_cohort_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new module too | `tests/test_layers.py`, unchanged |
