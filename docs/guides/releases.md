# Releases: publishing a package

For the platform team, who run releases, and for the workflow developers whose changes become
them. Decision: brief D50 (adding to D5). What comes next (a case opening on a release,
activating one in an environment, migrating open cases) is layer 12's later parts.

## A package, and its release

A **package** is one folder: a case definition and the plans its plan steps run.

```
examples/packages/refund/
  case.json                 the case definition
  plans/
    refund-order.json       each plan a plan step names, one per file
```

A plan is known by its own `plan` and `version` (`refund-order@1`), whatever its file is called.
The folder holds exactly the plans the case names: a plan a step names that is missing, a plan no
step names, the same plan twice, or any other file is refused, and nothing is released.

A **release** is an immutable, numbered version of a package. Nobody numbers it by hand: on merge,
CI runs `ventoux release` on each package, which compares it with the package's latest release
and does one of three things:

- **the behaviour changed:** a new release, the next number, and its record;
- **only the wording changed:** no release; a *wording revision* of the current release, which
  applies to open cases at once;
- **nothing changed:** nothing is written.

## Behaviour and wording

Everything that can change what the engine does or decides is **behaviour**. Titles, descriptions
and approval reasons are **wording**, and live in `display` blocks. The tool decides which is
which by computing the package's **behaviour digest**, a hash of everything outside `display`,
read as the engine reads it:

- a `display` block is wording wherever the format puts one; a case-file field that happens to be
  *called* `display` is behaviour like any other field;
- a literal you pass to an activity is behaviour, even if it reads like wording: changing
  `"intro": "Dear customer, we are pleased…"` makes a release. To make such a text wording, take it
  out of the step's inputs;
- order matters where the engine reads it in order: steps, and rules (rules on one moment act in
  the order written). Reordering them is a release;
- whitespace, the order of keys inside an object, and writing out a value that is already the
  default (`"stays_open": false`) change nothing.

When the tool can't tell, it releases: a release nobody needed costs a migration; wording that
was really behaviour would reach every open case unreviewed.

## Running it

```
$ ventoux release examples/packages/refund --releases releases --commit 4f2a9c1
refund 1 released: digest 89420f53b3d3 (method 1)
```

A title reworded (`steps.settle.display.title`, "Settle the refund" to "Pay the refund"):

```
$ ventoux release examples/packages/refund --releases releases --commit 7b0e311
refund 1, wording 2: steps.settle.display.title changed; no release
```

The plan's approval given 72 hours instead of 48 (`"timeout": "72h"`):

```
$ ventoux release examples/packages/refund --releases releases --commit c90d4e2
refund 2 released: digest dfdac910acbb (method 1); behaviour changed at plans.refund-order@1.states.approve_refund.approval.timeout
```

The commit is given by CI; the tool never reads git. It exits with:

| Exit | When |
|---|---|
| 0 | it released, recorded a wording revision, or had nothing to do |
| 1 | the package, or a record, is refused: each problem is printed |
| 2 | something can't be read (a folder, a file that isn't JSON) |

## Only a package that passes is released

The tool checks each plan (as `ventoux check` does for plans) and the case against the catalog
before anything else. An error refuses the release, printing each issue with its path; a warning
is printed and the release goes on. Until `ventoux check` comes with the builder, the catalog is
the development one.

## The release record

Each release is a file, `releases/<package>/<n>.json`, written once and never again:

- the package's name (its case's `case`), its number, and its digest, with the hash method that
  made it: `{"method": 1, "sha256": "…"}`;
- the commit;
- every contract it needs, its plans' included, each with its hash: what activation will check
  the environment's workers serve;
- the package as written, so a case can later be started from the record alone;
- what changed since the release before: the paths, behaviour and wording apart.

A wording revision is `releases/<package>/<n>.wording-<k>.json`, numbered from 2 (the release is
its own first wording), with the package as written and the paths whose wording changed.

Run the tool twice on the same merge and the second run has nothing to do. A record that already
exists is never written over: the same bytes again are accepted, anything else is refused.

**One digest, one release.** If a merge brings a package back to the behaviour of an earlier
release (a revert), no new number is made: `same behaviour as refund 1; nothing released`. Rolling
back is activating that release.

**Only the latest release takes new wording.** A revert must bring back the earlier release's
wording too, as `git revert` does. A package with an earlier release's behaviour and other wording
is refused (exit 1):

```
same behaviour as refund 1, other wording: rewording an older release reaches its open cases; bring back its wording
```

The usual way there is a behaviour reverted while the newer release's titles stay, titles written
for steps the older release's cases don't have; and open cases read new wording at once (below).

**The hash method has a version.** Every digest and contract hash records its method. Before
comparing, the tool reads every record of the package again and recomputes its digest from the
package it stored, so a later change of method is never mistaken for a change of behaviour. A
record made by a method it doesn't know, or whose digest its own package doesn't give, is refused,
and so is the run.

**A package's releases folder holds its records and nothing else.** Any other file there, or a
record under another record's name, refuses the run: the tool never guesses which file is which
release.

## Open cases and new wording

A case runs the release it opened on, to the end (the cases guide, "A case runs its release").
Wording is the one thing that reaches it later: when a person reads the case, the view and the
approval sheet are given the latest wording revision of the case's release, and its titles are
the ones shown. Nothing the case decides changes, and nothing is recorded, since reading a case is
a query. A revision is used only if it is of the case's own release, with that release's digest;
any other is refused. An answer can say which wording its person read (`wording=2`), and its
history line says so: `… as worded in refund 1, wording 2`.

A plan step's own approval, asked inside the plan's child workflow, shows the plan as its run
started: a new wording of the release's plans reaches the next run of the plan, never one already
running.

**Method 1 is pinned.** Every open case recomputes its release's digest each time it continues as
new, so method 1 must give the same digest for ever. Ventoux's tests pin it for packages that
between them use every shape of the format; a change to the engine that would change a digest
fails there first. A new method would be method 2, recorded as a decision of its own.

## Moving open cases to a later release

A case runs its release to the end, unless it is **migrated**: moved, open, to another release
(brief, D53). A migration is a change request, as an edit is (the cases guide, "Changing an open
case"): one person proposes it, someone else approves it, and the case checks it again when it
applies it. Both hold a role your platform team registered to migrate:

```python
catalog.register_role("platform", migrates=True)
```

Say `refund 3` adds a fraud check, which the payment now requires, and renames two names: the step
`pay` is now `payment`, and the field `approved_amount` is `amount_approved`. A migration says each
rename, by name, never by position; a name it doesn't rename keeps its own:

```json
{"steps": {"pay": "payment"}, "fields": {"approved_amount": "amount_approved"}}
```

In a test, `migrate` proposes it, and the approver answers its entry:

```python
moved = run_case(refund, file={"order_id": "ord-1", "amount": 250},
                 answers=[("review", "approve", "ana", {"approved_amount": 250}),
                          migrate(refund_3, renames, "pia"),
                          ("case.change#1", "approve", "lee")],
                 people=PEOPLE, release=refund_1)
assert moved.waiting_for == ["fraud_check by fraud"]
```

```
pia proposed case.change#1: migrate to refund 3, to be approved by platform
lee answered case.change#1 approve as platform
applied case.change#1: migrated from refund 1, engine 2 to refund 3, engine 2, proposed by pia, approved by lee
withdrew pay.approval#1: refund 3 changed pay
renamed step pay to payment
renamed field approved_amount to amount_approved
started fraud_check#1: waiting for clear by fraud
```

What Ana answered is the same value under its new name, still hers; the approval Sam would have
given approved the payment as it was, so it is withdrawn and asked again once the fraud check is
done.

**Refused, never terminated.** Anything the case holds under a name the target lacks, unmapped,
refuses the migration, every problem said at once with what to map or wait for:

- a run of a step, whatever its state: `pay#1 is running, and refund 3 has no step pay: map it, or
  migrate after it finishes`;
- a milestone reached, never undone: `paid is reached, and refund 2 has no milestone paid: map it,
  since a milestone reached is never undone`;
- a value: `note holds a value, and refund 2 has no field note: map it`; and the target must hold
  it as it is, never converted: `note is a string in refund 1, and note is a number in refund 2:
  values are never converted`. So must what a finished run gave (its outcome, its outputs) and
  what an event carried;
- nothing loosens: `note is sensitive in refund 1, and note isn't in refund 2: a migration never
  loosens it`.

**Running work finishes under what it started with.** A running payment keeps its entry and its
key; if the target's step calls another contract, the migration waits for it: `pay#1 is running on
payments.refund@2, and refund 2's pay calls orders.lookup@1: migrate after it finishes`. A running
plan finishes on its plan: plans don't migrate. An open task stays open, answered as the target
says.

**What else follows the target:** an approval stays only if its step is the same, word for word;
a timer keeps its due time if its rule waits on the same moment for the same age, is measured
again from when it was set if the age changed (firing right away if that time has passed), and is
cancelled, saying so, if its rule is gone; a pending edit follows its field's new name; an event
sent under a name the target renamed is refused. Then the case decides as the target: a step it
adds may start at once, as the fraud check does.

**The engine version moves too, forward only.** The request carries the version the proposer's
code was built with; a case refuses one it doesn't know, or one older than its own. A migration
may move the engine alone, keeping the release: `migrated from refund 1, engine 1 to refund 1,
engine 2`.

**Preview first.** On Temporal, `preview_migrations` asks each case you give it what the migration
would do, with no effect on any of them; then each case gets its own request:

```python
seen = await preview_migrations(client, RefundCases, ["refund-A-1001", "refund-A-1002"],
                                refund_3, renames)
for id, preview in seen.items():
    if not preview.refused:
        await propose_migration(case_handle(client, RefundCases, id), refund_3, renames,
                                "pia", ["platform"])
```

Each case is in the answer, with the lines its history would gain or every problem refusing it; a
case that isn't one, or was forgotten, is in it too, saying so. The cohort is the IDs you give:
finding every open case of a release comes with the environment registry (layer 12e), since
Temporal's test server can't list workflows. The case checks that the target's package gives its
digest; that it is the store's release is your API's to vouch for, as it reads it from the store,
until the registry lets the case check it itself.

**Graduating a strict workflow.** A strict workflow is a case whose steps each require the one
before and start by themselves (a `sequence`); loosening it is a release like any other, and open
cases move to it by a migration, since a case has no position (brief, D2). Half-way through the
payment, a refund can be moved to a release where support calls the customer at any time and the
letter is drafted only if asked for.

## What the tool says

Paths and names, never values: `behaviour changed at steps.settle.when`. The semantic diff (layer
13) will say what a change means; until then, the paths are the release notes.
