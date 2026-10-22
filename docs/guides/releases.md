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

## What the tool says

Paths and names, never values: `behaviour changed at steps.settle.when`. The semantic diff (layer
13) will say what a change means; until then, the paths are the release notes.
