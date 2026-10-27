# Layer 13: the semantic diff

Status: 2026-10-24. Prior art read (the `chartering` prototype at `81389b3`, its `main`);
layer 13 explained, split into five parts, and 13a's choices put with a recommendation each.
Answered "all as recommended", the same day: choices 1 to 18. D55 and the releases guide's
section "What changed: the diff" written before building 13a; 13a built, slices 0–6, and its
Promises table checked against the tests, the same day (see 13a, "Decided while building"). In a
second answer, the same day: 1 to 18 as recommended, with one addition to 13 and 14, a contract's
output sources judged in 13a too (choice 14a), built as slice 7; and no research note on `cdk
diff` and the others, since the analogy only supports choice 3 and nothing depends on it.
Layer 12's walk-through and check-yourself are deferred, by the user's choice, and aren't part of
this layer.

## Warm-up: learning question 40, arrival is a fact, content is not

> "Arrival is a fact, content is not": give an example.

Open since layer 11's check-yourself (2026-10-21), and not asked during layer 12. Answer from
memory first. Last time these didn't come back: the sender check that makes an arrival a fact,
that content may still start steps and set fields (it informs), and the line validation draws
(`UNTRUSTED_TRIGGER`). The answer and the discussion are recorded in `docs/LEARNING.md`.

It is relevant here: a diff that says "looser" about who may send an event, or about a field's
`untrusted:` mark, relies on exactly that line.

Answered 2026-10-24: "the arrival is a fact, the content of the email is not." The principle
came back; the example, the sender check and "informs, never decides" didn't. They were
discussed and recorded, and the question stays open.

## Prior art: what the prototype has, and what it means for Ventoux

The curriculum names two references in `francoisnyc/chartering`. The default branch this
environment cloned first was a stale one (`197d519`), which lacks the second; both are read here
from `main` (`81389b3`).

**`src/authoring/render.ts`, the approval sheet with "will never do".** `renderApproval(charter,
registry)` builds a Markdown sheet from the plan and the registry alone: what it reads, what it
writes, what needs approval, what it will never do, and a Mermaid diagram. Its "will never do"
lines are:

- use any capability other than the N it lists ("Charters cannot define new ones");
- call each registry entry the plan doesn't use, listed by name;
- send messages on its own, if no capability's name matches `/send/i`;
- for each input policy of each capability it uses: "let untrusted data influence `ref` input
  `field`", or "take it from anywhere but …";
- run code, fetch URLs, or use the clock or randomness.

What this means for Ventoux:

1. **Every line is derived, never written by an author.** Ventoux keeps that: the sheet and the
   diff are pure functions of the definitions and the catalog, as a reading is (brief, D45).
2. **Two kinds of "never" are mixed together.** "No code, no clock, no new capabilities" holds for
   *every* definition, because of the engine. "Never gives `amount` untrusted data" holds for
   *this* definition, because of its contracts. Ventoux says engine-wide guarantees once, above
   the sheet (as `EVERY_RULE` does for readings), and keeps per-definition lines for what the
   definition proves. A diff can only change the second kind.
3. **"Send messages on its own" is a guess based on a name** (`/send/i`): a capability called
   `mail.deliver` would pass it. That is not a proof. Ventoux reads the contract's declared
   `effect` (`notify`), never a name, or else says nothing.
4. **Listing every capability that isn't used gets long as the catalog grows.** Ventoux says
   "calls only these contracts", a closed list, which is the same proof in fewer lines.
5. **It reads no run.** It is given no data, so it can't quote any. Ventoux's diff is given no
   case file either: that is where the "no value from a case" line is drawn (choice 9).
6. **Policies come from the registry, per capability**, as Ventoux's come from the catalog (brief,
   D21). So the diff needs the catalog, and a step that moves from `payments.refund@2` to `@3`
   changes its policies without changing a word of the case.

**`thoughts/qrspi/2026-10-01-01/`: a task and research questions, never answered.** The folder
holds `task.md` and `questions.md` only: no research, design or plan was written, and the
prototype has no diff. What it gives Ventoux:

- **The task, as stated:** report what changed in effect, not in the JSON text (admission rules,
  approvals, sink policies, the provenance of case-file fields, and what each version will never
  do), from the CLI and in CI, so that the output can be posted on pull requests.
- **The reason:** a workflow tool fails when nobody can tell what changed between process
  versions. And the diff is the review step for definitions a builder *generates* (layer 14), so
  its output must stay readable even when nobody wrote the JSON by hand. This is the curriculum's
  check-yourself: a JSON diff of generated output is noise.
- **Question 7, prior art outside the repository** (`cdk diff`, `pulumi preview`, `terraform plan`,
  `bpmn-js-differ`), was never researched. From what is known of them, not checked again here:
  they compare resources by identity, not by position, and mark each change added, removed or
  modified. `cdk diff` also lists IAM and security-group changes in a table of their own, and
  `cdk deploy --require-approval broadening` stops for a person only when a change *broadens*
  security. That is the same idea as this layer's "looser", and it supports making "looser" a
  verdict rather than a reviewer's impression. If you want this checked against their
  documentation, it can be a short research note before 13b.
- **Questions 1 to 6** asked what validation computes that a diff could reuse. In Ventoux that is
  already answered by layers 10 to 12: `seen_by` (who sees a field), the policies on each contract
  input, the readings (D45), and 12a's `changed` (the paths where the digest moves).

## What this layer is for

Layer 12 made definitions released things. Its release notes are paths:
`behaviour changed at steps.pay.activity`. That is honest, but a reviewer still has to work out
what the path means. Layer 13 says what each change *does*, and whether it loosens a guard.

A small example. A pull request changes one character in the refund case:

```diff
-      "activity": "payments.refund@2",
+      "activity": "payments.refund@3",
```

The JSON diff shows a version bump. The catalog shows what it means: `@2` takes `amount` "only
from a system or a person, never from untrusted data", while `@3` takes it from anywhere. The
semantic diff says:

```
refund: 1 behaviour change, 1 looser
looser   steps.pay.activity: payments.refund@2 -> payments.refund@3
         input amount: was "only from a system or a person, never from untrusted data";
         now takes any value (no input policy)
```

A second change the JSON diff hides: adding a task for a new role, `auditor`. Nothing about
fields changes in the JSON. But a field that declares no `visible_to` is seen by every role the
case names (brief, D53), so `auditor` now sees `amount`, `approved_amount` and every step's
outcome and outputs. The diff says that on each field, as looser.

## The split

Layer 13 lands as five pull requests, each with its own section here, its own Promises table and
its own tutor review, as layers 11 and 12 did:

| PR | What it builds | Curriculum negative test |
|---|---|---|
| **13a: the change list, by effect** | `diff(before, after, catalog)`: every behaviour change between two packages, said in the developer form by path, each with a verdict (stricter, looser, or not proven). Judged in 13a: the guards on data (input policies, `untrusted:` marks, a contract's output sources, `sensitive`, who sees a field). Every other change is said and left unproven. `ventoux diff OLD NEW` | a change that loosens an input policy is reported as looser, never hidden; and (added in the answers) an output made a system's is reported as looser |
| **13b: guards on people and runs** | verdicts for approvals (whether there is one, who, how many, when), requirements and conditions, who proposes, answers, sends or closes, `automatic`, `repeatable`, `max_age`, close reasons, forgetting, and a plan's approval states | — (its own: an approval's count lowered is looser) |
| **13c: the plain-language form, the case map and the rules sheet** | the diff said in readings (D45): each changed rule, step, approval and field as its sentence before and after; the generated case map (what a case can do) and the "will never do" sheet, per package | — (its own: a "never" line said only where it is proven) |
| **13d: release notes and a contract's diff** | release notes generated from the diff, behaviour and wording apart, replacing 12a's paths (D50); a contract's readable diff (design question 16): `retry.maximum_attempts: 5 -> 9` | — |
| **13e: the CI step** | on each pull request, per package: whether merging it creates a release, a wording revision or nothing (12a's digest, base against head), and the diff, in the job summary | — |

**Why this order.** 13a is the one source every other part renders, so it comes first. It also
carries the curriculum's negative test. Input policies are where a package can loosen something
without anyone noticing: a contract version is one character. 13b adds the remaining verdicts to
the same list. Until then those changes read "not proven", which is safe (choice 4). 13c needs
the verdicts to put the right words around a reading. 13d's notes are the diff, written into the
record. 13e only runs what exists.

### Where each point lands

- **A diff by effect, of two packages (a case and its plans):** 13a, the list and its developer
  form; 13c, the plain-language form built on the readings (D45).
- **What it compares:** every behaviour path is covered from 13a, because a change the diff
  doesn't judge is still said (choice 5). Judged in 13a: input policies and sources (the
  `untrusted:` marks on fields, payload fields and a plan's fields), what is sensitive, and who
  sees what. Judged in 13b: steps and when they start, approvals (who, how many, when), who
  answers, proposes, sends and closes, timers' freshness (`max_age`), close reasons and
  forgetting. Timers' ages, events, milestones, rules and plans' transitions are said, with the
  definition's literals, and left unproven (choice 3).
- **Stricter or looser, for each change:** 13a defines the verdicts and judges data guards; 13b
  judges people and runs.
- **The curriculum's negative test:** 13a.
- **The case map and the rules sheet:** 13c.
- **Release notes:** 13d.
- **A contract's readable diff:** 13d.
- **The CI step:** 13e, in the job summary (choice 7).
- **Renames:** 13a (choice 6).

## Choices for the whole layer

Answer by number. "Recommended" is what I'd do; options set aside are said.

1. **The split:** 13a to 13e as in the table, in that order. *Recommended.* Set aside: one part
   per form (the developer form whole, then the plain-language form whole). That would make the
   first pull request judge every guard at once, about twenty kinds, each with its witness
   (choice 3).

2. **One diff, several renderings.** `diff` returns data: a list of changes, each with its path,
   its verdict, and what it said before and after. The developer form, the plain-language form
   (13c), the release notes (13d) and the CI summary (13e) all render that one list. So a verdict
   is computed in one place, and no rendering can judge differently from another.
   *Recommended.* Set aside: a text diff per form, where each form would have to prove its own
   verdicts.

3. **Three verdicts, and a verdict only where it is proven.**
   - **looser:** the new version's guard lets through strictly more than the old one did, whatever
     the case holds. For example, an input policy that accepts every set of sources the old one
     accepted, and more.
   - **stricter:** the reverse, strictly less.
   - **not proven:** anything else. The two guards are incomparable (`only_from("payments")`
     replaced by `only_from("billing")`), the change is to something that isn't a guard (a rule's
     action, a timer's age, a milestone added), or the comparison isn't one the diff knows.

   A verdict is claimed only from a closed list of comparisons the diff knows, one per kind of
   guard, as D21's policy kinds and D45's clauses are closed lists. Each comparison has a
   **witness**: a test that runs a case where the old version refuses what the new one lets
   through, for looser, and the reverse for stricter. A coverage test checks that the witnesses
   cover the list. A new kind of guard can't then be judged without a run that shows the
   judgement. *Recommended.* Set aside: judging expressions (`amount > 100` replaced by
   `amount > 150`). Comparing two conditions in general is not decidable, and a special case
   for thresholds would be a second evaluator. Such a change reads "not proven", with both
   expressions shown.

4. **Every doubt reads as looser.** "Not proven" is never "unchanged" and never "stricter". In
   every summary, count and CI line, it is grouped with "looser" ("2 may loosen: 1 looser, 1 not
   proven") and listed before "stricter". Its own line still says only what changed, so it claims
   nothing it can't prove. A comparison the diff can't make (a contract missing from the catalog,
   a policy kind it doesn't know) refuses the whole diff: the diff fails closed, never quietly
   leaving out what it can't read. *Recommended.*

   **What counts as loosening**, across the layer:
   - **13a:** an input policy that accepts more (a policy removed, `only_from` widened, `only_from`
     replaced by `trusted_only`); an `untrusted:` mark removed from a field, a payload field or a
     plan's field; a contract's output made a system's where it was untrusted or undeclared
     (choice 14a, added in the answers); `sensitive` removed; a field seen by more roles (its `visible_to` widened or
     removed, or a new role named anywhere in the case, which then sees every field without a
     `visible_to`, every outcome and every output).
   - **13b:** an approval removed, its `count` lowered, its roles widened, or a `when` added to it
     (asked on fewer runs); a requirement removed or a step's `when` removed; `proposed_by`, a
     task's `roles` or an event's sending roles widened; `automatic` turned on or `repeatable`
     added; a `max_age` lengthened or removed; a close reason added or its roles widened;
     `forgetting` moved towards `allowed`; a plan's approval state removed or its roles widened.
   - In each case the reverse is stricter, and any other change to the same guard is not proven.

5. **The diff never says less than the digest.** Every path where 12a's `changed` sees a behaviour
   change is covered by at least one change in the diff. The diff is empty exactly when the
   behaviour digests are equal: a contract reference names one immutable contract (D5), so the
   digest already covers what the catalog adds. A change outside the closed list of comparisons
   is still listed: at its path, not proven, with the definition's literals before and after. So
   a part of the format the diff wasn't taught about can't pass in silence. *Recommended.*

6. **Renames are left as they are: one entry removed, one added.** A migration's mapping (D53) is
   data in a change request against an open case, made after releases exist. It isn't in either
   package, so the diff has nothing to read it from, and guessing a rename would be a claim the
   diff can't prove. What the diff *can* prove, it says: when an added step, field, milestone,
   rule or event has exactly the behaviour of a removed one of the same kind, the added line says
   "behaves as the removed `pay` did: open cases need a migration mapping `pay` to `settle`
   (brief, D53)". *Recommended.* Set aside: giving the diff a mapping. That is possible later,
   for a migration's preview, where a mapping exists, but release notes can't have one.

7. **The CI step uses the job summary** (`$GITHUB_STEP_SUMMARY`, Markdown that GitHub shows on the
   run's page). It needs no permission beyond the default read token, no third-party action and
   no new dependency, and it works on pull requests from forks. A comment would need the
   `pull-requests: write` permission, so either a third-party action or the `gh` CLI on the
   runner. It would fail on forks, whose tokens are read-only, and it repeats itself on each
   push unless it edits its own comment. Both would ask you first. Whether a release follows is
   12a's digest of the base branch's package against the head's: a new release, a wording
   revision, or nothing. That needs no release store, so no records are read in CI. The base is
   read from a second checkout of the base commit. *Recommended:* the job summary; a comment set
   aside unless you want it.

8. **A contract's readable diff (design question 16)** lands in 13d. A contract's canonical
   promise (what `contract_hash` hashes: schemas, policies, risk, effect, retry, timeouts,
   outcomes) is compared field by field: `retry.maximum_attempts: 5 -> 9`. A contract's values are
   written by the platform team, never by a case, so they are shown. It serves two cases:
   - a step that moves from `@2` to `@3`, where both are in the catalog (D5);
   - the hash check's failure, "`payments.refund@2` changed without a new version". There the old
     promise isn't in the lockfile, which keeps hashes only (D50). The CI step already checks out
     the base commit, so it computes the base's promise with the base's own code.

   *Recommended*, decided in detail in 13d. Set aside: storing each promise in
   `contracts.lock.json`. That changes a file layer 12 decided keeps its shape.

9. **No value from a case file, ever; literals written in a definition may be shown.** The diff's
   only inputs are the two packages and the catalog. It is never given a case file, so it can't
   quote one, as with a reading (D45). What it shows comes from what an author or the platform
   team wrote: names, roles, contract references, durations, counts, an expression's constants
   through the expression renderer, a literal input to an activity, and a contract's promise.
   The line is: **written in the definition or the catalog may be shown; held by a case, never**.
   A wording change shows its text before and after, since that is definition wording too.
   *Recommended.*

10. **Pure and deterministic.** `diff` reads no clock, no randomness and no I/O, imports no
    Temporal, and gives the same list in the same order every time. The order: the case before its
    plans (plans by reference). Within the case, the sections in the order the format writes them
    (fields, milestones, steps, sequence, rules, events, close reasons, then the case's own keys),
    each map in the new version's written order, and an entry the new version removed at its old
    position. Derived changes, such as who sees a field because a new role was added, come under
    the field, naming what caused them. *Recommended.*

11. **Where it is recorded:** a new decision, **D55** ("The semantic diff: changes by effect, a
    verdict only where proven, every doubt read as looser"). Dated amendment lines go on D5 (the
    release notes, from 13d), D21 (the diff's "stricter or looser?" built for input policies) and
    D50 (the paths replaced, from 13d). The text of each stays. The guide is
    `docs/guides/releases.md`, with a new section, "What changed: the diff", written before
    building, its example run by a test. *Recommended.*

## 13a. The change list, by effect

User-facing description, written first once you agree: a section of `docs/guides/releases.md`,
for workflow developers reading a pull request and the platform team reading a release.

### What this part is for

`diff(before, after, catalog)` returns every behaviour change between two packages, each with:

- **its path**, as the JSON writes it (`steps.pay.activity`, `fields.amount.visible_to`);
- **its verdict:** `looser`, `stricter` or `not proven` (choice 3);
- **what it says:** before and after, in the definition's own terms. For example, the policies of
  a contract's input, the roles that see a field, or an expression as the renderer writes it;
- **why, for a derived change:** the change it follows from (`fields.amount: seen by auditor too,
  because steps.audit names auditor`).

Wording changes are listed apart, by path, before and after, never as behaviour. They come from
12a's `wording`.

13a judges the **guards on data**: what may flow where, and who may see it.

- **An input policy** of each input a step (or a plan's activity state) gives its contract,
  compared between the contract the old version calls and the one the new version calls. For
  example, `pay` moving from `payments.refund@2` to `@3`, or the same input now given to another
  contract.
- **An `untrusted:` mark** on a case field, an event's payload field, or a plan's field (its
  `sources`).
- **An output's source,** as the contract a step (or a plan's activity state) calls declares it,
  compared when the step moves to another contract (choice 14a, added in the answers).
- **`sensitive`** on a case field.
- **Who sees** each field, and the outcomes and outputs, as `seen_by` computes it: the declared
  `visible_to`, or every role the case names.

Everything else is said at its path, not proven, with literals before and after. 13b judges more
of these.

```
$ ventoux diff refund-before/ refund-after/
refund: 3 behaviour changes; 2 may loosen (1 looser, 1 not proven), 1 stricter; 1 wording change
looser      steps.pay.activity: payments.refund@2 -> payments.refund@3
            input amount: was "only from a system or a person, never from untrusted data";
            now takes any value (no input policy)
not proven  steps.pay.approval.when: amount > 100 -> amount > 150
stricter    fields.note.source: none -> untrusted:customer
wording     steps.pay.display.title: "Refund the customer" -> "Send the refund"
```

(The exact layout is settled with the guide. The verdicts, paths and order are what the tests
pin.)

### What the code does today

- `case/releases.py` (12a): `changed(before, after)` gives the behaviour and wording paths,
  `wording(package)` the wording by path, and `behaviour_digest` the digest. 13a reuses
  `changed` as its completeness check (choice 5), never as its output.
- `case/visibility.py` (9a): `roles_named(case)` and `seen_by(case, name)`. 13a compares
  `seen_by` across the two versions for each field, and `roles_named` for outcomes and outputs.
- `core/contract.py`: `policies(field)` on a contract. `core/policy.py`: the two kinds,
  `TrustedOnly` and `OnlyFrom`, a closed list (`KINDS`).
- `core/expressions`: `render`, the one-line renderer readings use (D45).
- `tooling/releases.py`: `read_package(folder)`, which `ventoux diff` reuses to read both
  folders.

### Choices for 13a

12. **Comparing input policies exactly.** With the closed list of two kinds, what an input accepts
    is a set that can be computed: with no policy, any sources; with `trusted_only`, any sources
    that are all trusted; with `only_from(S1)`, `only_from(S2)` and so on, a non-empty set of
    sources, all systems in the intersection of the Si (every policy on an input applies, D21).
    One set inside the other gives the verdict; neither gives "not proven". The comparison is a
    public function next to the kinds, `core/policy.py`'s `compared(old, new)`, so a third kind
    can't be added without it: an unknown kind refuses the diff, never reads as "the same".
    *Recommended.*

13. **A contract change is judged per input, and the rest is said.** When a step calls another
    contract, each input it gives is judged by choice 12. An input that exists in only one of the
    two contracts is said and not proven. Any other difference between the two contracts (risk,
    effect, outcomes, retry) is said in one line, "its contract also differs: risk, retry", not
    proven. The readable contract diff comes in 13d. A contract the catalog doesn't hold refuses
    the diff, naming it (fail closed). *Recommended.*

14. **An `untrusted:` mark:** removed is looser (values written there no longer carry the
    distrust that a `trusted_only` or `only_from` input refuses); added is stricter; a label
    changed (`customer` to `llm`) is not proven. No policy reads labels today, but "today" isn't a
    proof for every later kind. *Recommended.*

14a. **A contract's output sources, judged beside the marks** (D29). *Added in the answers,
    2026-10-24, to choices 13 and 14.* When a step moves to another contract, each output both
    contracts give is compared by the source each declares, an undeclared one being
    `untrusted:undeclared`: from untrusted to a system is looser (a case may now decide on it:
    a rule reaching a milestone on it acts); the reverse is stricter; one system for another,
    or one label for another, is not proven. An output only one of them gives is said, not
    proven. Its witness: a rule reaching `delivered` on `lookup.status` acts on nothing while
    `orders.lookup@1` leaves `status` undeclared, and reaches it on `orders.lookup@2`, whose
    `status` comes from `system:orders`. An output's source is taken out of "its contract also
    differs", as an input's policies are.

15. **`sensitive`:** removed is looser (the value is no longer wrapped and may be given to a
    workflow step, D31, D36); added is stricter. *Recommended.*

16. **Who sees a field: compare `seen_by` across the two versions, never `visible_to` as
    written.** That is what makes the hidden case visible: a new role named anywhere (a task's
    `roles`, a close reason, an event's sender) widens every field without a `visible_to`, and
    the diff says so on each field, and once for "every outcome and output", naming the change
    that caused it. Roles added and none removed is looser; removed and none added is stricter;
    both is not proven. *Recommended.*

17. **The command:** `ventoux diff OLD NEW`, two package folders read as `ventoux release` reads
    them, against the development catalog (as `ventoux release` and `ventoux simulate` do, until
    `ventoux check` brings the deployment's, layer 14). It prints the developer form. Exit 0 when
    it compared, whatever it found: a looser change is the reviewer's to judge, not a failure.
    Exit 1 when a package or the diff is refused, and 2 when a file can't be read, matching
    `ventoux release`. *Recommended.* Set aside: failing on "looser" (reviewers approve legitimate
    loosenings every day; a red check they learn to ignore protects nothing).

18. **Witnesses for 13a's four comparisons** (five with 14a's)**:** a run with `run_case` where the old version refuses
    and the new one lets through:
    - input policy: a value from `untrusted:customer` refused by `@2`'s `amount`, taken by `@3`'s;
    - `untrusted:` mark: the same value, refused while the field carried the mark, taken once it
      doesn't;
    - `sensitive`: refused to a workflow step while sensitive, given once not;
    - who sees: the field absent from `auditor`'s view, then present;
    - an output's source (14a): a rule reaching a milestone on it acts on nothing, then acts.

    A coverage test checks that the four cover 13a's list of comparisons. *Recommended.*

### Not in 13a

- Verdicts on approvals, requirements, conditions, proposers, answerers, senders, close reasons,
  `max_age`, `automatic`, `repeatable`, forgetting, and a plan's approval states (13b). Until
  then they read "not proven", which counts as looser.
- Readings in the diff, the case map and the "will never do" sheet (13c).
- Release notes in the record, and a contract's readable diff (13d). `ventoux release` still
  writes 12a's paths.
- The CI step (13e).
- Nothing at runtime: no workflow changes, so no replay fixture. No new engine version. No new
  dependency.

### Seams the tests use

- `diff(before, after, catalog)` returning the change list, with packages built by 12a's
  `package(case_text, plans_texts)` and a catalog built in the test (a `payments.refund@3`
  without a policy lives in the test, not in the development catalog).
- `compared(old, new)` in `core/policy.py`: the comparison of two lists of policies (choice 12).
- `str(change)` and the developer form, as printed.
- `main(["diff", OLD, NEW])`: what the command prints and exits with.
- `run_case`, for the witnesses.
- The guide's example, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The curriculum's negative test first:** `pay` moved from `@2` to a `@3` without `trusted_only`
   on `amount` is reported looser, at `steps.pay.activity`, naming the input and both policies.
   Then `compared` for each pair of kinds; a contract missing from the catalog refuses the diff;
   an unknown policy kind refuses it.
1. **Completeness:** every path `changed` sees is covered, and a change the diff doesn't judge
   (a rule's action) is said, not proven, with its literals. The same digest gives no change.
   Wording is listed apart.
2. **Marks and `sensitive`:** removed is looser, added is stricter, a relabel is not proven. This
   covers case fields, payload fields and a plan's fields.
3. **Who sees:** `visible_to` widened, narrowed or removed; a new role through a new step, said
   on each field and once for outcomes and outputs (the JSON-hidden case).
4. **Renames and order:** a removed and added step with the same behaviour says so; the order of
   choice 10.
5. **Witnesses and coverage:** the four runs, and the coverage test.
6. **The command, the guide and D55:** exit codes; the guide's example as written; the amendment
   lines.
7. **Output sources** (choice 14a, added in the answers), its negative test first: `lookup` moved
   from `orders.lookup@1` to `@2`, whose `status` comes from the orders system, is reported looser;
   then the reverse, one system for another, an output only one contract gives, and the witness.

### Decided while building

- **A value set where there was none read as an entry added** (slice 1, found by the summary's
  test): the walk took `None` for "this version has no such entry", so `source: none ->
  untrusted:customer` said "added" and was never judged. An entry one version lacks is now its
  own marker, never `None`.
- **Wording inside an entry added or removed is part of that change** (slice 1): a new step listed
  each of its titles as a wording change, and its empty descriptions too. They are left out of the
  wording list, and an empty description reads as none, written out or not.
- **A comparison is named only where it proves the verdict** (slice 3): readers both added and
  removed said "not proven" while naming `readers`, and so did two `only_from` neither wider nor
  narrower. A `Change` now refuses, when it is made, looser or stricter without a comparison on the
  list, and not proven with one; the walk can't claim a verdict the witnesses don't cover.
- **An untrusted amount asks for the payment's approval even under 100** (slice 5, the input
  policy's witness): its condition reads the untrusted value, and untrusted data can't remove an
  approval (brief, D38). The witness has a team lead approve it, so the refusal it shows is the
  input policy's, checked by its message, never a run that merely didn't finish.
- **Naming a role in one field's `visible_to` names it in the case** (slice 5): it then sees every
  field without one. The readers' witness widens `amount` to `support-lead`, already named, so the
  diff has one change to show.
- **A contract's input class name is part of its promise** (slice 0): two test contracts whose
  inputs were classes of different names differed in their JSON Schema's title, so "its contract
  also differs: input" was right. The tests build each input as `RefundInput`; design question 16's
  own example of a change nobody sees, and 13d's to show.
- **The guide's first example calls a `payments.refund@3` the development catalog doesn't hold**:
  its test runs the command with a catalog that holds it, as written otherwise.
- **The walk was written whole in slice 0,** so later slices' tests passed at once; each was seen
  failing on a deliberate break (the mark removed or added not judged, the payload pattern left
  out, readers compared as written, the outcome line left out, removed entries appended, plans
  skipped, the comparison check removed, the command's refusal exiting 0). Comparing whole entries
  before walking them is a guard the section check already gives, so breaking it alone fails
  nothing; it stays, cheap and safe.
- **`ventoux diff`'s refusals:** a package that isn't one names its folder, as `ventoux release`
  does; a diff refused names both folders and why.

- **`orders.lookup@1` and `@2` name their output classes differently** (slice 7): so besides
  the looser output, the diff says, truthfully, "its contract also differs: output". The
  witnesses check the changes a comparison judged, and let a not-proven change stand beside them.
- **The readers' witness asks `support-lead`, not `auditor`** (slice 5, said above): choice 18's
  `auditor` would have been named by the field itself.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`D` is `tests/test_diff.py` (new). Drafted before building; checked against the tests,
2026-10-24: every test named here exists, and every test in `D` is named here.

| Promise | Test |
|---|---|
| A step moved to a contract whose input policy accepts more is reported looser, at the step's path, naming the input and both policies: never hidden (the curriculum's negative test) | D `test_an_input_policy_loosened_is_reported_looser` |
| A policy that accepts less is stricter; two policies neither wider nor narrower are not proven | D `test_an_input_policy_tightened_is_stricter`, `test_policies_neither_wider_nor_narrower_are_not_proven` |
| `compared` orders every pair of the two kinds exactly, and refuses a kind it doesn't know; so does the diff | D `test_policies_are_compared_exactly`, `test_a_policy_kind_the_diff_doesnt_know_is_refused` |
| A contract the catalog doesn't hold refuses the diff, naming it | D `test_a_contract_missing_from_the_catalog_refuses_the_diff` |
| An input or an output in only one of the two contracts, or another difference between them, is said and not proven | D `test_other_contract_differences_are_said_not_proven` |
| A looser or stricter verdict names a comparison on the closed list; not proven names none | D `test_a_verdict_names_its_comparison` |
| An `untrusted:` mark removed is looser, added is stricter, relabelled is not proven, on case fields, payload fields and a plan's fields | D `test_an_untrusted_mark_removed_is_looser`, `test_an_untrusted_mark_added_is_stricter`, `test_a_relabelled_mark_is_not_proven`, `test_marks_on_payloads_and_plans_are_judged` |
| A step moved to a contract whose output comes from a system where it was untrusted (or undeclared) is reported looser, naming the output and both sources; the reverse is stricter; one system for another is not proven (choice 14a, added in the answers: a negative test of its own) | D `test_an_output_source_made_a_system_is_looser`, `test_an_output_source_made_untrusted_is_stricter`, `test_one_system_for_another_is_not_proven` |
| `sensitive` removed is looser; added is stricter | D `test_sensitive_removed_is_looser`, `test_sensitive_added_is_stricter` |
| Who sees a field is compared as `seen_by` computes it: widened looser, narrowed stricter, both not proven | D `test_visible_to_widened_is_looser`, `test_visible_to_narrowed_is_stricter`, `test_readers_both_added_and_removed_are_not_proven` |
| A new role named anywhere is said on every field without `visible_to`, and on outcomes and outputs, naming the change that caused it (a change the JSON diff hides) | D `test_a_new_role_sees_every_unnarrowed_field` |
| A change outside the comparisons is said at its path, not proven, with the definition's literals before and after | D `test_a_change_the_diff_doesnt_judge_is_said_not_proven` |
| Every behaviour path 12a's `changed` sees is covered by a change, over fifteen kinds of edit | D `test_the_diff_says_everything_the_digest_sees` |
| The same behaviour digest gives no change: reformatting, a default written out and wording alone included | D `test_the_same_behaviour_has_no_changes` |
| Wording is listed apart, before and after, never as behaviour; nothing changed says so | D `test_wording_is_listed_apart` |
| An added or removed entry's wording is part of that change, not listed apart | D `test_an_added_entrys_wording_is_part_of_it` |
| "Not proven" is counted with looser in the summary, as what may loosen, before stricter | D `test_not_proven_counts_with_looser` |
| A renamed step is one removed and one added, the added one saying it behaves as the removed one did and that a migration must map it | D `test_a_renamed_step_is_removed_and_added` |
| Changes come in the order of choice 10, the same every time | D `test_changes_come_in_the_packages_order` |
| The diff is given only the two packages and the catalog: no case file to quote from | D `test_the_diff_reads_only_packages_and_the_catalog` |
| Each looser and stricter comparison has a witness run, the pair read both ways, and the witnesses cover the list | D `test_each_comparison_has_a_witness`, `test_the_witnesses_cover_every_comparison` |
| The command exits 0 when it compared, a looser change included, 1 when refused, 2 when unreadable, and prints the developer form | D `test_the_command_says_the_diff` |
| The guide's examples run as written | D `test_the_guides_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new module too | `tests/test_layers.py`, unchanged |

## 13b. Guards on people and runs

Status: choices drafted 2026-10-24, from `main` at `3888f95` (13a merged as #47). Answered "all
as recommended", the same day: choices 19 to 32. D55's amendment, D11's and D47's lines and the
releases guide's verdicts written before building 13b.

### Warm-up: learning question 14, quickstart approvals

> In the quickstart, the reviewer approves a 250 refund. Which person can approve the payment, and
> who can't? What does the case wait for at that moment, and what would a test assert?

Open since the tracer bullet. The exclusion and the test's three assertions are what didn't come
back last time. Answer from memory first. It is 13b's question: "who may approve" is more than the
roles an approval names (choice 23).

Answered 2026-10-24, after a reminder of what the exclusion is: "Sam can approve; Ana can't, she
set approved_amount." The exclusion and its reason came back; the opener, what the case waits for,
and the test's three assertions didn't. Discussed and recorded; the question stays open.

### What this part is for

13a judges what may flow where, and who may see it. 13b judges **who may act, and when a step
may run**: approvals, requirements and conditions, who proposes, answers, sends and closes,
freshness, forgetting, and a plan's approval and wait states. Until now each of these reads "not
proven", which counts as what may loosen; 13b replaces that with a proof wherever one exists.

The curriculum's own negative test lands here: **an approval's count lowered is looser.** In the
JSON it is `"count": 2` becoming `"count": 1`, one character. The diff says:

```
looser     steps.pay.approval.count: 2 -> 1 (one person approves pay, where two had to)
```

And one the JSON hides: `pay` no longer reads `approved_amount`, so Ana, who set it in `review`,
is no longer excluded from approving `pay`. The JSON shows an input changed; the diff also says who
may now approve:

```
not proven steps.pay.inputs.amount: approved_amount -> amount
looser     steps.pay.approval: whoever answers review is no longer excluded from approving pay
```

### What the code does today

- `case/diff.py` (13a): `COMPARISONS`, each with a witness in `tests/test_diff.py`; `judged`
  routes a leaf to its comparison by its path's pattern. 13b adds patterns and comparisons, and
  `Change` already refuses a verdict whose comparison isn't on the list.
- `case/sequence.py`: `requirements(case)`, each step's `requires` with `sequence` folded in.
- `core/approval.py`: `approver_role`, the roles an approval lists that the catalog lets approve
  the contract's risk (`core/roles.py`'s `may_approve`).
- `case/writers.py`: where each value could come from, read from the definition alone (10c);
  `case_sources` gives, for a field, the people who could write it (`person:answering review`).
- The exclusions themselves (D11, D25, D26, D39, D42, D47) are the engine's, the same for every
  definition; only what a step *reads* is the definition's.

### Choices for 13b

Each judged comparison is added to `COMPARISONS` with a witness run (choice 3): one version refuses
what the other lets through, and the pair read the other way proves the reverse.

19. **What "looser" claims where a condition is added or removed.** A condition can't be
    compared (choice 3), but its presence can: an approval with no `when` is asked on every run,
    so adding one asks it on no more runs than before, and on fewer wherever it is false. That is
    a proof for every case, though not of *strictly* more: a `when` true for every case changes
    nothing. So 13b's verdicts on presence say exactly that: **looser: lets through everything the
    old version did, and more wherever the condition is false**, with the condition shown. The
    witness is a case where it is false. *Recommended.* Set aside: deciding whether a condition
    can be false (a second evaluator, choice 3), or leaving presence not proven (the curriculum
    asks for approvals "asked on fewer runs" to be said).

20. **An approval: there or not, and when.** On a step:
    - added: stricter (every run it covers waits for a person); removed: looser;
    - `when` added: looser (asked on fewer runs, choice 19); removed: stricter; changed: not
      proven, both shown;
    - the curriculum's negative test is choice 21's.

    *Recommended.* An untrusted `when` asks anyway (D38), so adding one never asks on more runs:
    the verdict holds.

21. **An approval's count:** lowered is looser, raised is stricter (D47: distinct people, each
    "someone else", one rejection rejecting the entry). Said with what it means: `2 -> 1 (one
    person approves pay, where two had to)`. Witness: with `count: 2`, one team lead's *approve*
    leaves `pay` waiting (`1 of 2 given`); with `count: 1` it starts. **The curriculum's negative
    test for 13b.** *Recommended.*

22. **Roles, compared as the case reads them.** For every list of roles (an approval's, a task's
    who answers, `proposed_by`, an event's sending roles, a close reason's, a plan's wait and
    approval): the roles both versions name compared as sets, **widened looser, narrowed stricter,
    replaced (some added, some removed) not proven**. "As the case reads them": a role the catalog
    doesn't register gives nobody anything (D22), so it counts for nothing; one the catalog
    registers is compared by name. *Recommended.*

23. **Who may approve is more than the names.** Three things beyond the roles listed:
    - **the role must be allowed the contract's risk** (`approves="high"` on `register_role`): the
      approvers are the listed roles that may approve the step's contract's risk, as
      `approver_role` reads them. So adding `support`, which approves no risk, to `pay`'s roles
      changes nothing, and is said so (not judged as looser); and a step moved to a contract of
      higher risk may lose approvers: stricter, said under the approval;
    - **the count** (choice 21);
    - **who is excluded:** every person whose answer flows into the step's inputs or its `when`,
      the opener, the proposer, and the others D11, D25, D39 and D47 list. The rules are the
      engine's, but which answers flow in is the definition's: a step that stops reading a field a
      task sets no longer excludes whoever answers that task. Computed from what the step reads
      (`writers`), as the tasks whose answers can reach it: fewer looser, more stricter, both not
      proven. Said as a derived change under the approval, naming what caused it, as 13a's readers
      do. Witness: Ana, who answered `review`, is refused as an approver of `pay` while `pay` reads
      `approved_amount`, and accepted once it doesn't.

    *Recommended.* Set aside: comparing exclusions only by the roles (misses the hidden one above).

24. **When a step may run: requirements.** Compared as `requirements(case)` gives them, `requires`
    with `sequence` folded in: fewer looser (it may start with less done), more stricter, replaced
    not proven. A `sequence` changed is then said on each step it changes, and the `sequence` line
    itself stays, not proven. *Recommended.*

25. **A step's `when`:** added stricter (it runs on no more cases), removed looser, changed not
    proven (choice 19's wording, the other way round). *Recommended.*

26. **`automatic`, `repeatable` and `proposed_by`:**
    - `automatic` on: looser (it starts by itself once admitted, with nobody proposing it); off:
      stricter;
    - `repeatable` added: looser (it may run again, when proposed); removed: stricter;
    - `proposed_by` widened or narrowed as choice 22.

    *Recommended.*

27. **Who answers, sends and closes** (choice 22's comparison, each its own witness):
    - a task's `roles`;
    - an event's sender: its roles compared as choice 22; its `system` replaced, or roles
      replaced by a system or the reverse, not proven;
    - close reasons: one added looser (a new way for people to close the case), removed stricter,
      its roles as choice 22. `closes_when` and `stays_open` stay not proven: closing by
      milestones is neither a permission nor its absence.

    *Recommended.*

28. **Freshness (`max_age`),** per fact a step reads: shorter stricter, longer looser; a fact newly
    required fresh stricter, no longer required looser. Ages compared as durations (`2d` is longer
    than `12h`), never as text. *Recommended.*

29. **Forgetting, ordered `never` < `while_open` < `allowed`:** toward `allowed` looser (a person
    may erase more), toward `never` stricter. Witness: forgetting a closed case refused under
    `while_open`, accepted under `allowed`. *Recommended.*

30. **A plan's approval and wait states, as their own case.** A plan has no `count`, no `when` on
    its approval, and its path is its transitions (D49), so:
    - **which activity states are approved:** an activity state no approval state approves any
      more (`of`) is looser, newly approved stricter. Whether every path to it passes the approval
      is a path property layer 3 checks; the diff compares the approvals' targets only, and says
      so;
    - an approval state's roles, and a wait's, as choices 22 and 23 (the risk check applies to a
      plan's approval too);
    - a timeout added, removed or changed: not proven (what it does is a transition).

    *Recommended.*

31. **An output's source on a plan's activity state is said, never judged** (found in the review
    of #47). A plan keeps no activity's outputs: its fields come from the case and from answers,
    and a plan step gives no outputs (D28). So "looser" there claims a widening no case can meet.
    It is said, not proven, with why: `output status: was untrusted:undeclared; now system:orders
    (a plan keeps no activity's outputs)`. *Recommended.* Set aside: skipping it (the change would
    then be said nowhere, since output sources are taken out of "its contract also differs").
    13a's test of a plan's contract moved gains the line; no witness is removed (13a's output
    witness is a case's step).

32. **Where it is recorded:** D55 gains a dated amendment line naming 13b's comparisons and choice
    19's wording; D47 and D11 an amendment line each for what the diff says of them. The releases
    guide's "What changed: the diff" section gets 13b's verdicts and the count example, run by its
    test. No new dependency. *Recommended.*

### Not in 13b

- Readings in the diff, the case map and the "will never do" sheet (13c); release notes and a
  contract's readable diff (13d); the CI step (13e).
- Comparing conditions or expressions (choice 3, kept).
- Nothing at runtime: no workflow changes, no new engine version.

### Seams the tests use

- `diff(before, after, catalog)`, as in 13a, with packages built by `package`; catalogs built in
  the tests where a role (`finance`, `clerk`) or a contract (`payments.refund@8`, medium risk)
  is needed.
- `run_case` and its scripts (`propose`, `send`, `close`, `later`, `plan_answers`) for the
  witnesses; `lookup_refusal` (`temporal/forget.py`) for forgetting's.
- `main(["diff", …])` through the guide's example.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The curriculum's negative test first:** a count lowered is looser; then raised, an approval
   added or removed, an approval's `when` added, removed or changed; their witnesses.
1. **Roles,** as the catalog registers them: who answers, proposes, sends and closes; who may
   approve, as the contract's risk allows.
2. **Exclusions:** a step that stops reading an answer lets its people approve.
3. **When a step may run:** requirements with `sequence` folded in, a step's `when`, `automatic`,
   `repeatable`.
4. **Close reasons, senders, freshness, forgetting.**
5. **A plan's approval and wait states,** and an output's source on a plan's state (choice 31).
6. **The guide's example, the Promises.**

### Decided while building

- **An approval removed from a high-risk step is not looser** (slice 0, found by its witness): a
  high-risk step with no approval never runs, as the runtime refuses it (D11), so the version
  without one lets nothing more through. Neither removed nor added is judged there; the line says
  why: `payments.refund@2 is high risk: without an approval, pay never runs`. A plan's high-risk
  activity likewise (slice 5): the interpreter stops a plan at it. Choice 20's "removed: looser"
  holds for a step of low or medium risk, which the witness uses (`orders.lookup@1`).
- **13a counted a role nobody registered as seeing every field** (slice 1): `roles_named` names
  it, and `seen_by` with it, but a role the catalog doesn't register gives sight of nothing
  (D22, `may_see`). Who sees a field is now compared among registered roles, as choice 22 says
  of every list of roles.
- **A refused plan answer doesn't raise:** the plan waits on. The plan witnesses run the same
  script on both versions, so only the roles differ: the plan step waits in one and is done in
  the other.
- **The in-memory plan runner read the development catalog,** whatever catalog `run_case` was
  given (found by the plan approvers' witness, whose `finance` role only a test's catalog
  registers). `run_case` said its catalog "replaces the development catalog"; its plan runner now
  reads it too. No other test depended on it.
- **A plan's approval roles are compared on their own leaf only:** a plan's activity moved to a
  contract of another risk is said (13a, not proven), never re-judged for who may approve it, as a
  case's step is. Not proven reads as looser, so nothing is claimed that doesn't hold; a known
  limit, for 13c's readings to say.
- **What a change is moved to `case/changes.py`, 13b's guards to `case/guards.py`,** so
  `case/diff.py` stays the walk and 13a's guards on data. The CLI and the tests import `Change`,
  `DiffRefused` and `COMPARISONS` from `changes`.
- **The 12e activation test that failed once in the tutor review of #47 failed once again,** in
  slice 5's full run (`test_activate_refuses_a_release_no_worker_serves`), and passed alone three
  times and in its file. Its message was not kept that run; the next full runs keep their output
  (see the pull request). Not this layer's code, and not fixed here.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`P` is `tests/test_diff_people.py` (new); `D` is 13a's `tests/test_diff.py`. Checked against the
tests, 2026-10-24: every test named here exists, and every test in `P` is named here, or in 13c's
table for what 13c added. Two rows were changed by 13c (choices 46 and 50), each marked.

| Promise | Test |
|---|---|
| An approval's count lowered is looser, said as how many people approve (the curriculum's negative test); raised is stricter | P `test_an_approvals_count_lowered_is_looser`, `test_an_approvals_count_raised_is_stricter` |
| An approval removed is looser and added stricter, on a step that may run without one | P `test_an_approval_removed_is_looser`, `test_an_approval_added_is_stricter` |
| On a high-risk step, an approval removed is not proven, saying the step never runs without one; a plan's high-risk activity likewise | P `test_a_high_risk_steps_approval_removed_is_not_proven`, `test_a_plans_high_risk_approval_removed_is_not_proven` |
| An approval's `when` added is looser, said as asked on no more runs and on fewer wherever it is false; removed stricter; changed not proven | P `test_an_approvals_condition_added_is_looser`, `test_an_approvals_condition_removed_is_stricter`, `test_an_approvals_condition_changed_is_not_proven` |
| Roles widened are looser, narrowed stricter, replaced not proven: who answers, proposes, sends and closes | P `test_roles_widened_are_looser`, `test_roles_narrowed_are_stricter`, `test_roles_replaced_are_not_proven` |
| A role nobody registered counts for nothing, said so, and sees nothing | P `test_a_role_nobody_registered_counts_for_nothing` |
| Who may approve is the listed roles allowed the contract's risk: a role that may not changes no approver; a step moved to a lower risk gains approvers, a higher one loses them | P `test_a_role_that_may_not_approve_the_risk_changes_no_approver`, `test_a_step_moved_to_a_lower_risk_gains_approvers` |
| A step that stops reading an answer lets whoever gives it approve: looser (a change the JSON diff hides); both added and removed: not proven. *Changed in 13c (choice 46):* looser only where nobody joins who may be excluded; a step that starts reading a form's field is not proven, never stricter | P `test_a_step_that_stops_reading_an_answer_excludes_nobody_for_it`, `test_a_step_that_starts_reading_a_forms_field_is_not_proven_stricter`, `test_exclusions_both_added_and_removed_are_not_proven` |
| Requirements, `sequence` folded in: fewer looser, more stricter, replaced not proven; a sequence changed is said on each step it changes | P `test_a_requirement_removed_is_looser`, `test_a_requirement_added_is_stricter`, `test_a_requirement_replaced_is_not_proven`, `test_a_sequence_is_said_on_each_step_it_changes` |
| A step's `when` removed is looser, said as running on no fewer cases; added stricter | P `test_a_steps_condition_removed_is_looser`, `test_a_steps_condition_added_is_stricter` |
| `automatic` and `repeatable` turned on are looser, off stricter | P `test_automatic_turned_on_is_looser`, `test_repeatable_added_is_looser_and_removed_stricter` |
| A close reason added is looser, removed stricter; a renamed one is said as a rename | P `test_a_close_reason_added_is_looser`, `test_a_close_reason_renamed_is_not_judged` |
| An event's sender replaced, system for roles, is not proven | P `test_an_events_sender_replaced_is_not_proven` |
| Forgetting is ordered never < while_open < allowed | P `test_forgetting_is_ordered` |
| `max_age` compared as a duration: longer or no longer required looser, shorter or newly required stricter, the same age written otherwise not proven | P `test_a_fact_allowed_older_is_looser`, `test_a_fact_no_longer_required_fresh_is_looser` |
| A plan's activity no longer approved is looser, newly approved stricter; its approval roles as its risk allows; its wait roles as roles; its timeouts not proven (*changed in 13c, choice 50:* the same duration written otherwise is no verdict) | P `test_a_plans_approval_removed_is_looser`, `test_a_plans_approvers_are_compared_as_its_risk_allows`, `test_a_plans_wait_roles_widened_are_looser`, `test_a_plans_timeout_is_not_proven` |
| An output's source on a plan's activity state is said, never judged (from the review of #47) | P `test_an_output_source_on_a_plans_state_is_said_never_judged` |
| Each of 13b's comparisons has a witness run, the pair read both ways, and the witnesses of 13a and 13b together cover the list | P `test_each_comparison_has_a_witness`; D `test_the_witnesses_cover_every_comparison` |
| 13a's promises still hold, `forgetting` now judged in its order test | D, every test |
| The guide's count example runs as written | D `test_the_guides_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new modules too | `tests/test_layers.py`, unchanged |

## 13c. The plain-language form, the case map and the "will never do" sheet

Status: choices drafted 2026-10-24, from `main` at `43dea32` (13b merged as #48). Answered "all
as recommended", the same day: choices 33 to 44. D56, and D45's and D55's amendment lines, written
before building 13c.

### Warm-up: learning question 36, the model picks the step, never the values

> What does "the model picks the step, never the values" mean in code? Using 8a: if a step
> advisor (layer 15) suggested the next step, which seam would its suggestion go through, what
> would the engine still check, and where could a value it made up never get in?

Open since layer 8; last asked at 11e's warm-up. Answer from memory first. It is 13c's question in
another form: the sheet and the readings say only what the definition proves, and quote nothing a
case holds.

Asked to be told, 2026-10-24; answered briefly and recorded. The question stays open.

### What this part is for

13a and 13b made one change list, each change with a verdict that is a proof. 13c says it in
words a business reviewer reads, and adds two sheets of one package:

- **the plain-language diff:** each changed step, approval, rule, field, event or close reason
  read before and after, as D45 reads rules, with the verdict's words around it;
- **the case map:** what a case of this package can do, every entry read, in the format's order;
- **the "will never do" sheet:** what no case of this package will ever do, each line a proof
  from a check that already proves it, with a witness.

A small example, the four-eyes refund back to one team lead, in the plain form:

```
## refund: what changes

### pay
Before: pay calls payments.refund@2 (high risk, it writes) once review is done, if
review.outcome = "approve". Two people approve it, each a support-lead, when
approved_amount > 10000.
After: … One support-lead approves it, when approved_amount > 10000.
- **Looser:** one person approves pay, where two had to.
```

And the start of the refund's sheet:

```
## refund will never

- call anything but payments.refund@2 (high risk, it writes).
- give payments.refund@2 its amount or its order_id from untrusted data.
- let anyone but support or support-lead see amount.
- let whoever answers review approve pay.
```

### What the code does today

- `case/reading.py` (11g, D45): `read_rule`, `read_patterns` and their fine print: rules only,
  never given a case file, failing closed on a shape it doesn't know, each clause with a witness.
- `case/diff.py`, `case/guards.py`, `case/changes.py` (13a, 13b): the change list, each change's
  path, verdict, `said` and comparison; nothing in words yet beyond `said`.
- `case/visibility.py`: `seen_by`, `roles_named`; `core/policy.py`: each policy's `describe()`;
  `case/guards.py`: `excluded` (whose answers reach a step), `allowed` (who may approve a risk).
- No reading of a step, a field, an event, a close reason or a plan exists yet.

### Choices for 13c

33. **The plain form renders the one change list, never judges again** (choice 2). It walks
    `diff`'s changes in their order, groups them by the entry they are about (a step, a rule, a
    field, an event, a close reason, a plan state), and prints per entry its reading before and
    after, then each change's verdict in words. The verdict and its reason come only from the
    `Change`: the renderer has no comparison of its own. A test checks that every verdict word in
    the plain form is its change's. *Recommended.* Set aside: reading both versions and saying
    what differs from the sentences (a second judgement, and a second place to be wrong).

34. **The verdict's words, one per verdict, the same everywhere:**
    - looser: **"Looser:"** and the change's `said` as a sentence;
    - stricter: **"Stricter:"** likewise;
    - not proven: **"Changed, not proven either way (read it as possibly looser):"**, so a doubt
      reads as looser in words too (choice 4);
    - written otherwise, the same decisions (choice 38): **"Written otherwise, the same
      decisions:"**.

    Wording changes are listed apart, last, as in the developer form. *Recommended.*

35. **Readings for every kind of entry, beside the rules' (D45's rules kept):** in
    `case/reading.py`, with the same rules as a rule's reading: names, not titles; conditions as
    the expression renderer writes them; never given a case file; a shape the reader doesn't know
    is refused, never left out. New readings:
    - **a step:** what it is (a task for who answers, a call of a contract with its risk and
      declared effect, a plan, a wait for an event), when it may start (what it requires, its
      `when`, `automatic` or proposed by whom, `repeatable`), its approval (who, how many, when),
      what it reaches, how old its facts may be;
    - **a field:** its type, who sees it (as the case computes it), `sensitive`, its `untrusted:`
      mark;
    - **an event:** who sends it, what it carries, each payload field's mark;
    - **a close reason:** who may close the case with it; and the case's own closing
      (`closes_when`, `stays_open`) and `forgetting`;
    - **a plan:** each state in its written order: what each activity state calls, each approval
      state's roles and timeout, each wait's roles and outcomes.

    *Recommended.* Set aside: one sentence per change from its `said` alone (it can't say what an
    entry added or removed does).

36. **The fine print readings already have, kept; new fine print only where a new reading needs
    it, each with a witness** (D45's rule): an approval with a `when` on a high-risk step runs
    unapproved where the condition is false (the quickstart's small refund); an approval's count
    is distinct people, one rejection rejecting it (D47); a step proposed by a role is never
    approved by its proposer (D25). *Recommended.*

37. **The known limit from 13b, said in the readings.** Where a plan's activity state moves to
    another contract and an approval state approves it, the plain form adds under that state:
    "who may approve it in the plan was compared by its roles, not again for
    payments.refund@3's risk: read its approval's roles above". It is a sentence about what the
    diff did, true of every case; the change itself stays not proven. *Recommended.* Set aside:
    re-judging it now (a 13b comparison, to be decided as one, with its witness).

38. **Written otherwise, the same decisions (from the review of #48)**: a fourth kind of line,
    beside the verdicts, never counted as "may loosen". Only where the diff *proves* the two
    versions decide the same for every case, though the digest moves. Checked against the code
    for this note:
    - **a `max_age` of the same duration** (`2d` and `48h`): every decision compares seconds, so
      both decide the same. The history still words the age as written ("needs it at most 2 days
      old", "at most 48 hours old", `freshness.as_said`), so the line says that too: `written
      otherwise, the same decisions: the history says 48 hours where it said 2 days`;
    - **not requirements written in another order,** which I had first put here: a refused retry
      or proposal names the first unmet requirement, and what steered a run is recorded in that
      order (`runtime.py`), so the order is read. It stays not proven.

    These lines go in a list of their own (`Diff.rewritten`), as wording does, so nothing can
    mistake one for a verdict; `Change` keeps its three verdicts. The summary says `1 written
    otherwise`. "Never less than the digest" (choice 5) still holds: every path the digest sees is
    a change or a rewriting. A `visible_to` written to name the same roles as today stays not
    proven: it narrows who a role added later would see. *Recommended.*

39. **The case map: every entry of the package, read, in the format's order.** Its fields, then
    its steps, rules (patterns with their expansions, D46), events, close reasons, then how it
    closes and whether it may be forgotten, then each plan. Nothing judged and nothing derived
    beyond what the readings say. *Recommended.* Set aside: a diagram (Mermaid, as the prototype
    drew; a second renderer of requirements, worth its own decision later).

40. **The "will never do" sheet: engine-wide guarantees said once, above it.** Each is a rule
    of the engine for every definition, said as its decision, with a test that already proves
    it named in the Promises:
    - it runs nothing written in the definition as code; its conditions read no clock, randomness
      or outside data (D20);
    - it calls nothing but the contracts the catalog holds; a definition names them, never
      defines one (D5, D17);
    - untrusted data never reaches a milestone or stops a step (D38);
    - nobody approves a step their own answer feeds, nor one they proposed, nor one in a case they
      opened (D11, D25);
    - one approval unlocks one run of one step (D11);
    - a failed step is never skipped by itself: it waits for a person (D17);
    - a sensitive value is never given to a workflow step, nor written out (D31).

    *Recommended.* Set aside: "drafts, never sends" (a non-negotiable for how activities are
    written, not something the engine checks; said nowhere until it is a check).

41. **Per-package lines, only where proven for every case, each from a check that already proves
    it, each with a witness.** Offered:
    - **calls only:** the contracts the package's steps and plans call, each with its risk and
      declared effect ("calls nothing but payments.refund@2 (high risk, it writes) and
      orders.lookup@1 (low risk, it reads)"). Proof: the engine calls only what a step or state
      names (D5). Witness: a run's history names no other contract;
    - **changes the world only through:** the contracts whose *declared* effect is `write` or
      `notify`, said as declared ("by what its contracts declare, it changes the world only
      through payments.refund@2"); none: "by what its contracts declare, it only reads and
      computes". From the contract's `effect`, never a name (the prototype's `/send/i` was a
      guess). Witness: the declaration itself, the contract test (D6), said so;
    - **input policies, with their sources:** for each call, each input with a policy: "never
      gives payments.refund@2 its amount from untrusted data", "… its account from anything but
      payments". Proof: the runtime refuses every such value (D21, layer 5). Witness: 13a's
      input-policy witness;
    - **who sees what:** for each field, "never shows amount to anyone but support or
      support-lead" (registered roles, as `seen_by` reads them); "never shows outcomes or outputs
      to anyone but …". Witness: 13a's readers witness;
    - **sensitive values:** "never gives national_id to a workflow step" for each sensitive field
      a workflow step could be given. Witness: 13a's sensitive witness;
    - **who may not approve:** for each step with an approval, "never lets whoever answers review
      approve pay" (from `excluded`). Witness: 13b's exclusion witness;
    - **runs only approved:** for a step whose approval has no `when`: "never runs pay without a
      support-lead's approval"; with a `when`, nothing is said here (it may run unapproved where
      the condition is false). Witness: 13b's approval witness;
    - **forgetting:** with `never`, "never forgets a case's records"; with `while_open`, "never
      forgets a closed case". Witness: 13b's forgetting witness.

    Not offered: anything decided by a condition or by data ("never pays more than 100"); "never
    sends" by a name; reachability ("never reaches paid without assessed": validation's to prove,
    D34, and a released package has no error); "never closes with open work" (an engine-wide rule
    already, D10). *Recommended,* as a closed list (`NEVERS`), each kind with its witness and a
    test that the witnesses cover the list, as D45's clauses do.

42. **The commands:** `ventoux diff OLD NEW --plain` prints the plain form; `ventoux map FOLDER`
    prints the case map and the sheet of one package, against the development catalog (as `diff`
    does). Both print Markdown (headings and lists), which 13e's job summary shows as it is. Exit
    codes as `ventoux diff`'s. *Recommended.*

43. **Points kept throughout:** no value from a case file (every reading and the sheet take the
    package and the catalog, never a case file: a test checks their signatures, as 13a's does);
    the same order every time (the format's, choice 10); the guide's examples run by tests. The
    guides: the releases guide's "What changed" gains the plain form; the cases guide gains "What
    a case can do, and will never do", the map and the sheet of its refund. *Recommended.*

44. **Where it is recorded:** a new decision, **D56** ("The case map and the 'will never do'
    sheet: readings of a package, and only proven nevers"); dated amendment lines on D45 (readings
    of every kind of entry) and D55 (the plain form, and "written otherwise"). No new dependency.
    *Recommended.*

### Choices from the tutor review of #49

What the review showed, each with a run. The runtime excludes from approving a step only the
person whose answer the step reads *now* (D11, `someone_else` reads the case's current sources),
and a later answer replaces an earlier one:

- an edited value comes from its proposer and its approver (D52), so once `approved_amount` is
  edited, whoever answered `review` may approve `pay`, which reads it;
- a repeatable task answered a second time gives its new answerer's values, so the first answerer
  may approve;
- a field another task's answer also sets (13b's `recheck`) holds whichever answer came last.

So the sheet's "never let whoever answers review approve pay" is false where `pay` reads a field
a form sets, and 13b's "stricter: whoever answers recheck is now excluded from approving pay" is
false when recheck's answer replaces review's value. The engine-wide line ("let anyone approve a
step their own answer feeds") stays true: it says *feeds*, what the step reads now.

What is fixed: a task's **outcome** can't be edited (D52: "an outcome or an output records what
happened"), and a task that isn't repeatable is answered once. So when a step's inputs or its
`when` read `review.outcome` itself, and `review` isn't repeatable, the person who answered review
is the outcome's source in every run of the step, and is excluded from approving it every time.

45. **"Who may not approve" on the sheet: said only where it is proven for every case,** that is,
    for a task's outcome the step's inputs or its `when` read directly, the task not repeatable.
    Not said for a field a form sets (an edit, a second answer or another writer replaces its
    sources), nor for anything read through a rule (a rule's field may be edited). The line keeps
    its words: "let whoever answers review approve pay". The cases guide's refund is unchanged:
    none of its case steps has an approval, so it says no such line today; 13b's `excluding`
    refund, whose `pay` reads `approved_amount`, says none after this.

    Weighed: the tutor's proposal, kept as it is. Set aside: a line with its exceptions ("… unless
    the value is edited or answered again"), which is no longer a never; and dropping the kind from
    `NEVERS`, which loses a line that is proven. *Recommended.*

46. **13b's exclusion verdict, from the same proof.** Each version gives two sets for a step: who
    *may* be excluded (`excluded` today, every person whose answer can reach what it reads) and
    who is excluded *in every run* (by choice 45's proof). Then:
    - **stricter** only if nobody leaves either set and everyone the new version may exclude it
      excludes in every run;
    - **looser** if someone leaves either set (no longer possibly excluded, or no longer excluded
      every time) and nobody joins the first;
    - **not proven** otherwise, which reads as looser.

    Weighed against the tutor's "a newly excluded person is not proven unless the same proof
    holds": right for the newcomer, but not enough, for two runs it misses:
    - a newcomer proven while an old exclusion weakens: `pay` starts reading `check.outcome`
      (proven), and `check`'s form also sets `approved_amount`, which `pay` already read. Whoever
      answers review was excluded before; after, not once check answers. The proposal says
      stricter; this choice says not proven;
    - the same people, a proof lost: `pay` stops reading `review.outcome` and reads
      `approved_amount`, set by review. Both versions may exclude whoever answers review, so
      nothing is said today; after an edit, they may approve. This choice says looser.

    The witness becomes a proven one: `pay` with `when: review.outcome = "approve"`, then
    without (Ana reviews and approves the payment: refused, then accepted). The three runs of the
    review become negative tests: the edit and the repeatable task each give no sheet line, and
    13b's `recheck` gives "not proven", never "stricter", with the run where review's answerer
    approves `pay` after the change and is refused before it. 13b's
    `test_a_step_that_starts_reading_an_answer_excludes_its_people` (from `amount` to
    `approved_amount`) becomes "not proven", and says why. *Recommended.*

47. **Where it is recorded:** a dated line on D55 (the exclusion verdict, choice 46) and on D56
    (the sheet's line, choice 45, and the heading, choice 48). Nothing on D11: it says what the
    runtime does, and the runtime is unchanged. *Recommended.*

48. **The sheet's heading says for which cases it holds.** "For every case of refund" holds only
    while a case runs this release: a migration moves a case to the target release (D53), whose
    definition the sheet doesn't read, and a field with no `visible_to` follows the target's
    roles. Offered:
    - (a) `## For every case of refund, while it runs this release`;
    - (b) `## For every case running this release of refund`;
    - (c) `## For every case of this release of refund`.

    *Recommended:* (a), the scope said where it ends. The engine's heading stays as it is: its
    lines hold whatever release a case runs.

49. **The cases guide says what a migration does to the sheet,** one sentence after the
    paragraph on the package's own lines: "A migration moves a case to the target release, and
    so to that release's sheet: the diff between the two releases (`ventoux diff`, in the
    releases guide) says what the move loosens." The guide's pasted output is made again from the
    command, and runs as written. *Recommended.*

50. **A plan state's `timeout` written otherwise (optional finding).** `48h` -> `2d` counts as
    "may loosen" today: choice 38 covered only `max_age`, and a plan's approval or wait state's
    `timeout` falls to the default, not proven. Offered: compare a `timeout` as a duration, as
    `max_age` is; the same duration is a "written otherwise" line, how the history words it said
    if it does; a different one stays not proven (what a timeout leads to decides whether shorter
    is looser, and the diff doesn't judge that). The negative test as choice 38's: no verdict,
    never counted as may loosen, the digest's path covered. *Recommended:* small, the same
    function, and a line nobody should have to read as a doubt.

51. **A test that "who sees" on the sheet counts registered roles only (optional finding).** The
    sheet filters roles the catalog registers (13b found the diff counted unregistered ones), and
    no test pins it there. Offered: a field `visible_to` a role nobody registers reads as seen by
    the registered roles only ("show … to anyone" when none), shown failing with the filter taken
    out. *Recommended.*

The notify witness needs no choice (from the review): a contract declared `notify` joins
`test_what_changes_the_world_is_read_from_declared_effects`, and taking `notify` out of
`CHANGES_THE_WORLD` must fail it.

### Answers to choices 45 to 51

45, 47, 48 (a), 49 and 51 as recommended. 46 and 50 changed, and 47 adds a line:

- **46, with two changes.** As written, the rule claimed verdicts that runs contradict. Each run
  below uses the quickstart's refund, plus a `check` task (support) whose `ok` sets a declared
  `checked_amount`. `pay` requires review and check, and asks for approval on every run. The
  history is the same each time: Ana answers review approve, Tom answers check ok, Bob proposes an
  edit of `approved_amount`, and Lee approves the edit. Then one person approves pay.
  - **R1.** Old `pay` reads `approved_amount`, with `when` review.outcome = approve. New `pay`
    reads `amount`, with `when` review.outcome = approve and check.outcome = ok. The rule said
    stricter. Lee's approval: the old version refuses it ("lee set approved_amount, which pay
    uses"), the new one takes it.
  - **R2.** Old `pay` reads `approved_amount`, with `when` checked_amount > 0. New `pay` reads
    `approved_amount`, with `when` review.outcome = approve. The rule said looser (check leaves
    the first set, nobody joins it). Ana's approval: the old version takes it, the new one
    refuses it.
  - **R3** (the second example in choice 46). Old `pay` reads `amount`, with `when`
    review.outcome = approve. New `pay` reads `approved_amount`, no `when`. The rule said looser.
    Lee's approval: the old version takes it, the new one refuses it.

  The changes:
  - **(a)** who *may* be excluded also counts whoever proposes or approves an edit of each
    declared field the step reads (D52), whenever a registered role may edit. And check that the
    static sources cover every other way a field the step reads can get a new value, each said
    in this note (below, "Every way a value the step reads is given");
  - **(b)** looser only if nobody joins *either* set.

  With both, R1, R2 and R3 each read "not proven", and the three runs become negative tests,
  beside the review's three.

  This makes "stricter" rare on exclusions: a step that reads any editable field is never proven
  stricter, since an edit's people may be excluded and are never excluded in every run. That's an
  honest doubt, never a false claim. A second proof (the new step reads every field the old one
  read, each with the same writers) could prove more "stricter" verdicts later. It isn't needed
  now.
- **47:** D55's dated line also says that an edit's proposer and approver count among who may be
  excluded.
- **50, widened to every age the format holds:** a plan state's `timeout`, a rule's `after`
  (`2d` -> `48h` reads "not proven" today) and a reminder's `after`, each compared as a duration.
  The negative test is as in choice 38. An sla's `within` is an age the format holds too, so it
  is compared the same way. A reminder's rules are named by their ages (`chase_2d`), so its line
  also says the history names them otherwise.

#### Every way a value the step reads is given

Who *may* be excluded is every person the static sources (`could_come_from`, layer 10c) name for a
value the step's inputs or its `when` read, plus an edit's people. Checked against each way the
runtime gives a value a source:

- **the opening:** the case file's first values come from whoever opened the case. The static
  sources read a system opener, so this person is not counted. The runtime excludes the opener
  from approving every step of the case whichever release it runs (D11), so no change of
  definition loosens or tightens it;
- **a task's answer:** its outcome and the fields its form sets, from whoever answers
  (`person:answering review`), counted;
- **an event's arrival:** each value it carries, from whoever sends it (`person:sending noted`),
  counted. An event may arrive again, so a value it carries is never excluded in every run;
- **a rule's `set`:** from everything the rule read, grown until nothing changes (D42), so a
  person reaches a field through a rule, counted. A rule's field is a declared field, so it may
  be edited too;
- **a call's or a plan's outcome and outputs:** from its contract or plan, plus what steered the
  run; a start passes on only what it doesn't trust (D43), so no person, at runtime as in the
  static sources;
- **an edit (D52):** from its proposer and its approver. Not in the static sources until now: a
  source for "whoever proposes or approves an edit of approved_amount" is added for each declared
  field when the catalog registers a role that may edit, and grown through rules like any other;
- **a migration (D53):** renames a value and may add a mark, never a person, and gives no new
  value.

#### Decided while building, after the review

- **The exclusion witness runs on a catalog where nobody edits** (slice 6). In the development
  catalog support and support-lead may edit, so `pay`, which reads `order_id` and `amount`, may
  exclude their edits' people in every version, never in every run: no change to it is proven
  stricter. The witness needs both directions, so its catalog registers the refund's roles with no
  right to edit; a test shows the same change not proven in the development catalog.
- **The verdict's line names who moved, never the whole sets** (slice 6): `whoever answers review,
  no longer`; `…, now in every run`; `…, now in some runs` (may be excluded, not every time). The
  people of an edit every version shares are left out, so the line says only what changed.
- **An sla's `within` and a plan's seconds** (slice 8): an sla's `within` is an age the format
  holds, so it is compared too; a plan's timeout may be written in seconds (`3600s`), which a
  case's ages can't, so a plan's are read with seconds as well.
- **A reminder's ages name its rules** (slice 8): `chase_2d` becomes `chase_48h`, so the line says
  the history names them otherwise, and ages in another order stay not proven (the rules come in
  that order).
- **An event's value is never excluded every time** (slice 5, from the note's list): a test shows
  it, with the run where Tom sends the event again and Ana may then approve.

#### Slices after the review, in order

Each starts with its negative test, seen failing for the right reason.

5. **Who may not approve, on the sheet** (choice 45): the edit's and the repeatable task's runs
   give no line; a task's outcome read directly does, with its run.
6. **The exclusion verdict from both sets** (choices 46 and 47): an edit's people among who may
   be excluded; R1, R2, R3 and the review's `recheck` read not proven, each with its run; a proven
   witness.
7. **The heading and the guide** (choices 48 and 49).
8. **Every age written otherwise** (choice 50): a plan state's `timeout`, a rule's `after`, an
   sla's `within`, a reminder's `after`.
9. **Who sees counts registered roles** (choice 51).

### The flaky activation test

`test_activate_refuses_a_release_no_worker_serves` (12e) has failed twice, each in a full run, its
message never kept. From 13c on, every full run's output is kept (`uv run pytest > run.txt 2>&1`);
if it fails, the whole output is kept and said in the pull request.

A carried note, not fixed in 13c (from the review of #49): its root cause is not known. Load is
not it: over three full runs, every dev-server start took 0.12 to 0.21 s, the file's first start,
the one that fails elsewhere, included; and the failing run captured no output from the server.
The test's harness is unchanged in this pull request. The next step is to keep the server's own
output when a start fails, then find the cause from it.

*Found 2026-10-24, in the tutor review of #50, and fixed in 12e's follow-up
(`docs/layers/12-releases.md`, "12e, fixed later: the dev server's cold start", choices 81 to
88):* the first start after a container is restored reads the server's 156 MB binary from a cold
disk, longer than the 5 s the SDK waits. The harness now starts the binary with a deadline of its
own.

### Not in 13c

- Release notes in the record and a contract's readable diff (13d); the CI step (13e).
- Re-judging a plan's approvers for a changed risk (choice 37 says it, nothing judges it).
- Nothing at runtime: no workflow changes, no new engine version.

### Seams the tests use

- `diff(before, after, catalog)` and its `rewritten` lines; `plain(found, before, after,
  catalog)`; `read_entry(path, case, plans, catalog)` and `EntryReading`; `case_map(package,
  catalog)`, `never_sheet(package, catalog)` and `nevers(package, catalog)`.
- `run_case` and 13a's and 13b's witnesses, reused for the sheet's lines.
- `main(["diff", …, "--plain"])` and `main(["map", …])`, through the guides' examples.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Written otherwise** (choice 38): an age of the same duration is no verdict.
1. **Every entry read** (choices 35 and 36): steps, fields, events, close reasons, closing, a
   plan's states and fields; the three new clauses and their witnesses.
2. **The plain form** (choices 33, 34 and 37).
3. **The case map and the sheet** (choices 39 to 41): the engine's lines with the tests that prove
   them, the package's lines with their witnesses.
4. **The commands, the guides, the Promises** (choices 42 to 44).

### Decided while building

- **Requirements written in another order stay not proven** (while drafting choice 38, checked
  against the code): the runtime names the first unmet requirement in a refusal and records what
  steered a run in that order, so the order is read. Only a `max_age` of the same duration is said
  as written otherwise, with how the history words it (`freshness.as_said`).
- **A sheet is offered only for what a case's steps name:** who may not approve, and runs only
  approved, read a case's own approvals; a plan's approval states are read in the map, not said in
  the sheet (whether every path to an activity passes its approval is layer 3's to prove, and the
  sheet doesn't repeat a proof it doesn't make). The releases guide's package, whose `settle` runs
  a plan, shows it: no "who may not approve" line.
- **Who sees, on the sheet, groups fields seen by the same roles** into one line, in the fields'
  order; a field no registered role sees reads "show … to anyone".
- **The proposer's witness keeps its case open** (`stays_open` and a close reason): with `pay`
  proposed, nothing is left to do once the review is answered, and a proposal to a closed case is
  refused before anything about approving is checked.
- **The guides' examples are pasted from the commands' own output,** then run by the tests, as
  12a's were: the plain form's and the map's `## ` headings sit inside the guides' code blocks, so
  the tests read a block by its fences, never by the next heading.
- **The engine-wide lines cite their decisions as the source does,** `(brief, D11) (brief, D25)`,
  so the sheet prints them so: the decision-citation check (layer 3) found them bare.
- **The 12e activation test failed a third time, and this time its output was kept** (the full run
  of slice 4, `uv run pytest > run.txt 2>&1`). It never reached its assertion: Temporal's dev server
  didn't start in time, in `WorkflowEnvironment.start_local`:
  `RuntimeError: Failed starting Temporal dev server: ephemeral server at 127.0.0.1:39227 did not
  start within 5s. Make sure another download isn't stuck and delete the temp file.`
  I first put it down to load and proposed one dev server per module. The review corrected it:
  every start took 0.12 to 0.21 s over three full runs, the file's first start, the one that
  fails elsewhere, included; and the failing run captured no output from the server. So the
  cause is not known; a carried note (see "The flaky activation test" above), the harness
  unchanged here.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`L` is `tests/test_plain.py` (new), `S` is `tests/test_sheet.py` (new), `D` is 13a's
`tests/test_diff.py`, `P` is 13b's `tests/test_diff_people.py`. Checked against the tests,
2026-10-24, again after the review of #49: every test named here exists, every test in `L` and
`S` is named here, and every test the review's round added to `P` is named here.

| Promise | Test |
|---|---|
| An age written otherwise with the same duration is no verdict and never counted as may loosen; it says how the history words it, and covers the path the digest sees (from the review of #48) | L `test_an_age_written_otherwise_is_no_verdict` |
| Every other age the format holds, written otherwise with the same duration, is no verdict, as `max_age` is: a rule's timer, an sla's `within`, a reminder's ages (its rules named otherwise, said), a plan's approval and wait timeouts, a plan's seconds included; another duration, or a reminder's ages reordered, stays not proven (from the review of #49, choice 50) | L `test_every_age_written_otherwise_is_no_verdict`, `test_an_age_of_another_duration_is_still_not_proven` |
| A step reads as what it is (a task for whom, a contract with its risk and declared effect), when it starts (requirements with `sequence`, `when`, by itself or proposed by whom, repeatable), who approves it and how many, what it sets | L `test_a_call_step_reads_as_what_it_calls_and_when_it_starts`, `test_a_task_reads_as_who_answers_and_what_each_answer_does`, `test_a_proposed_step_reads_as_who_proposes_it` |
| A field reads as its type, who sees it (registered roles only), `sensitive` and its mark | L `test_a_field_reads_as_its_type_and_who_sees_it` |
| An event, a close reason, the closing and forgetting, and a plan's states read | L `test_an_event_a_close_reason_and_the_closing_read`, `test_a_plans_states_read` |
| A shape the reader doesn't know is refused, never left out | L `test_a_shape_the_reader_doesnt_know_is_refused` |
| The new fine print, each clause with its witness: unapproved where the approval's condition is false; distinct approvers, one rejection rejecting; the proposer never approves; and the witnesses cover the list | L `test_a_step_runs_unapproved_where_its_approvals_condition_is_false`, `test_several_approvers_are_distinct_and_one_rejection_rejects`, `test_whoever_proposes_a_run_never_approves_it`, `test_every_entry_clause_has_a_witness` |
| The plain form reads each entry before and after, then each change in its verdict's words, from the change alone, in the change list's order | L `test_the_plain_form_reads_each_entry_before_and_after`, `test_every_verdict_word_is_its_changes` |
| An entry added reads after only | L `test_an_entry_added_reads_after_only` |
| Written otherwise and wording are listed apart, last | L `test_written_otherwise_and_wording_are_listed_apart` |
| 13b's known limit is said where a plan's approved activity moves to another contract | L `test_a_plans_approved_activity_moved_says_the_known_limit` |
| Readings, the plain form, the map and the sheet are given no case file | L `test_readings_are_given_no_case_file`, `test_a_plain_form_is_given_no_case_file`; S `test_the_map_and_the_sheet_are_given_no_case_file` |
| The case map reads every entry in the format's order | S `test_the_case_map_reads_every_entry_in_the_formats_order` |
| The sheet says the engine's guarantees once, each naming tests that exist and prove it, then the package's own lines | S `test_the_sheet_says_the_engines_guarantees_once_then_the_packages`, `test_each_engine_wide_guarantee_names_tests_that_prove_it` |
| Each kind of line the sheet offers has a witness, and the witnesses cover the closed list: calls only; changes the world only through, from declared effects, `notify` included (from the review of #49); input policies (trusted only, only from); who sees; sensitive; who may not approve; runs only approved (never with a `when`); forgetting | S `test_a_run_calls_only_what_the_sheet_says`, `test_what_changes_the_world_is_read_from_declared_effects`, `test_an_input_policy_line_is_the_runtimes_refusal`, `test_a_who_sees_line_is_the_view`, `test_a_sensitive_line_is_the_workflow_steps_refusal`, `test_a_who_may_not_approve_line_is_the_exclusion`, `test_a_runs_only_approved_line_is_the_wait_for_approval`, `test_a_forgetting_line_is_the_requests_refusal`, `test_every_kind_of_line_has_a_witness` |
| Who may not approve is said only where it holds in every run: a task's outcome read directly, the task not repeatable; never of a field a form sets (an edit replaces its sources), a repeatable task's outcome or an event's value (each may be given again), each with the run that lets the person approve (from the review of #49, choice 45) | S `test_who_may_not_approve_is_never_said_of_a_field_a_form_sets`, `test_who_may_not_approve_is_never_said_of_a_repeatable_tasks_outcome`, `test_who_may_not_approve_is_never_said_of_an_events_value`, `test_a_who_may_not_approve_line_is_the_exclusion` |
| Who is excluded is compared as two sets: R1, R2, R3 and another writer of a field read are not proven, each with its runs (choice 46) | P `test_r1_a_newcomer_excluded_every_time_while_an_edit_frees_another_is_not_proven`, `test_r2_someone_excluded_every_time_who_joins_is_never_looser`, `test_r3_an_edits_people_who_join_are_never_looser`, `test_another_writer_of_a_field_read_is_never_stricter` |
| An edit's proposer and approver may be excluded wherever a role may edit, reaching a step through a rule too; where they join, it is never looser (choices 46 and 47) | P `test_an_edits_people_who_join_make_it_not_proven`, `test_an_edits_people_reach_a_step_through_a_rule` |
| Stricter only where everyone who may be excluded is excluded in every run: a task's outcome where nobody may edit; a step reading an editable field is never proven stricter; the comparison's witness is a proven one | P `test_a_step_that_starts_reading_a_tasks_outcome_is_stricter_where_nobody_edits`, `test_each_comparison_has_a_witness` |
| The package's own lines say they hold while a case runs this release (choice 48) | S `test_the_sheet_says_the_engines_guarantees_once_then_the_packages`, `test_the_guides_map_runs_as_written` |
| Who sees on the sheet counts registered roles only, for each field and for outcomes and outputs (choice 51) | S `test_who_sees_counts_registered_roles_only` |
| `ventoux map` prints the map and the sheet, exits 1 when refused and 2 when unreadable; the cases guide's example runs as written | S `test_the_guides_map_runs_as_written`, `test_the_map_command_refuses_and_fails_to_read` |
| `ventoux diff --plain`: the releases guide's plain example runs as written | D `test_the_guides_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new modules too | `tests/test_layers.py`, unchanged |

## 13d. Release notes in the record, and a contract's readable diff

Status: choices drafted 2026-10-24, from `main` at `e6ea6b2` (13c merged as #49). Answered "all
as recommended", the same day: choices 52 to 62. D57, and the dated lines on D50 and design
question 16, written before building 13d.

### Warm-up: learning question 11, behaviour vs wording

> A step drafts a customer letter through `letters.draft@1`, with the opening sentence passed as a
> literal input: `"intro": "'Dear customer, we are pleased to confirm…'"`. Marketing wants
> "pleased" changed to "happy". Release or no release, and why? What would you change in the
> definition so that wording like this becomes presentation next time, without weakening any
> guarantee?

Open since layer 1; put at layer 12's warm-up and left unanswered. Answer from memory first. It is
13d's question from the other side: a wording revision's notes say only wording, so what counts as
wording decides what reaches open cases without review.

Asked to be told, 2026-10-24; answered briefly and recorded in the log. The question stays open.

### What this part is for

Two things say "what changed" today by path or by name only, and 13d makes each say it as the
diff does:

- **A release's notes.** `ventoux release` writes the record with the paths the digest saw
  change (`changed`, D50): `behaviour changed at
  plans.refund-order@1.states.approve_refund.approval.timeout`. 12a's guide says those paths are
  the notes "until the release notes are generated from it (layer 13d)". The notes become the
  semantic diff against the release before, kept in the record.
- **A contract changed without a new version.** The hash check says `payments.refund@2 changed
  without a new version: register it as payments.refund@3.` and nothing about what changed. The
  cause can be invisible: renaming the input class changes its JSON Schema, so the hash (design
  question 16, in the brief).
  The message becomes path by path: `timeouts.start_to_close: 10 -> 30`.

A small example, the guide's second release (the plan's approval given 72 hours, not 48), as
13d prints it:

```
$ ventoux release examples/packages/refund --releases releases --commit c90d4e2
refund 2 released: digest dfdac910acbb (method 1); behaviour changed at plans.refund-order@1.states.approve_refund.approval.timeout
refund: 1 behaviour change: 1 may loosen (0 looser, 1 not proven), 0 stricter; no wording change
not proven plans.refund-order@1.states.approve_refund.approval.timeout: 48h -> 72h
```

And the record keeps that line as data, in `releases/refund/2.json`, beside 12a's paths.

### What the code does today

- `case/releases.py`: `next_release` reads every record back (`stored`: of this package, method
  1, its digest its own package's) and gives `Released(n, changed)` or `Reworded(n, k, changed)`,
  `changed` comparing the latest wording of the newest release with the package being released.
  `record` builds the `Record`; `tooling/releases.py` writes it once (`FolderStore.write`: the
  same bytes accepted, other bytes refused).
- `case/diff.py`: `diff(before, after, catalog)` gives the change list, the lines written
  otherwise and the wording; for a step moved to another contract, `differing` says only which
  top-level keys of the promise differ: `its contract also differs: input, timeouts`.
- `core/hash_check.py`: `check_hashes(catalog, recorded)`, run by
  `test_every_development_contract_matches_its_recorded_hash` against `contracts.lock.json`.
  There is no command, and CI checks out one commit only.
- `core/contract_hash.py`: the promise the hash reads (everything but `display`, schemas as JSON
  Schema, outcomes sorted, `cancellable: false` left out), never kept anywhere.

### Choices for 13d

52. **The notes are a field of the record, written once with it.** A new field, `notes`, in each
    record (`<n>.json` and `<n>.wording-<k>.json`), holding the diff as data: which record it is
    against (release and wording), each change (path, verdict, what it says, its comparison, its
    `because`, its entry), each line written otherwise, and each wording line (path, before,
    after). The record is immutable (brief, D50), so the notes are made with it and never
    rewritten. 12a's paths (`changed`) stay beside them, unchanged: the digest's own account.
    A record written before 13d has no notes, and reads as "no notes: recorded before layer 13d";
    it is never given them later (a record is never written over; `ventoux diff` on the two
    stored packages answers the question).

    Set aside: (b) notes computed when asked, from two records. The diff's rules change (13c's
    review changed the exclusion verdict), so the same two releases could read differently later,
    and an immutable record should say what its reviewers were told. (c) Dropping `changed`: it
    loses the digest's account, and changes a shape D50 decided. *Recommended.*

53. **Computed from the stored packages, never the working tree.** Before: the latest wording of
    the newest release, read back from its record and checked against its digest (`stored`, as
    12a does). After: the new record's own package, read again from the text the record keeps,
    not from the folder. So the notes are a function of two records and the catalog, and a test
    recomputes them from the records alone. And each contract the earlier record names must
    still hash, in the catalog, as that record says: otherwise the notes would compare a promise
    the release never ran, and the release is refused, saying which. *Recommended.*

54. **A wording revision's and a first release's notes.** A wording revision's are against the
    release's latest wording: wording lines only. It has the release's digest, so its diff can
    hold no behaviour change and nothing written otherwise; if it did, the tool refuses (a digest
    and a diff that disagree is a bug, never recorded). Release 1's notes are against nothing:
    `"against": null`, read as "the first release: nothing to compare". *Recommended.*

55. **The same words as 13b and 13c, rendered when read.** A note keeps the verdict and what the
    change says, never rendered text. `ventoux notes FOLDER --release N [--wording K]
    --releases DIR [--plain]` prints a record's notes: the developer form as `ventoux diff`
    prints it, or the plain form as `ventoux diff --plain` does (its readings made from the two
    stored packages, the record's and the one it is against). `ventoux release` prints the
    summary line and the developer form after what it did, as above.

    Set aside: storing the rendered Markdown. A reading's words are presentation, which may be
    worded better later; the verdict and what changed are what the record must keep.
    *Recommended.*

56. **Never says less, never quotes a case value.** When the record is made, the tool checks that
    the notes cover every path the digest saw change (12a's `changed`: 13a's choice 5, enforced
    here at run time too). If they don't, the release is refused, naming the paths: a bug said,
    never a shorter record. The notes are made from two packages and the catalog only; no case
    file is given (a test checks the signatures, as 13a's does). *Recommended.*

57. **Fail closed.** Anything the notes can't read refuses the release (exit 1), saying why: the
    diff refusing (a contract the catalog doesn't hold, a policy of a kind it doesn't know), a
    record that can't be read back (12a already), a contract whose promise isn't the one the
    earlier record names (choice 53). Nothing is recorded without its notes.

    Set aside: a release recorded with "notes unavailable". A release without its account would
    reach production unread. *Recommended.*

58. **A contract's readable diff, path by path.** `promise_changes(before, after)` compares two
    promises as `contract_hash` reads them, leaf by leaf, in dotted paths as the diff names them:
    - a value changed: `retry.maximum_attempts: 5 -> 9`;
    - a key one side has: `input.properties.reason: added {"type": "string"}`, or `removed …`,
      the value as compact JSON;
    - a list shown whole on both sides (outcomes are sorted already, so a reorder never shows);
    - the invisible cause design question 16 names shows too: `input.title: RefundInput ->
      RefundRequest`.

    A promise is written by the platform team in the catalog, never by a case, so its values are
    shown (13a's choice 9). Pure, in `ventoux.core`, beside the hash. Anything it can't read (a
    value that isn't JSON) is refused, never skipped. *Recommended.*

59. **Where the old promise comes from: the base commit, checked against the lockfile.** The
    lockfile keeps hashes only (brief, D50), and a hash can't be read back. Offered:
    - (a) **the base commit's own code** prints its promises (`ventoux promises`: each
      contract's promise, by reference, as canonical JSON), and the head's check is given that
      file. A promise given is used only if it hashes to what the lockfile records (method 1);
      otherwise the line says "what changed can't be said: the promise given for
      payments.refund@2 isn't the one contracts.lock.json records". With none given, today's
      line, then "to see what changed, give the base commit's promises (`ventoux promises`)".
      The base's code, because a promise is what that code's models give: the same contract
      under another Pydantic gives another schema (D50's method);
    - (b) each promise kept in `contracts.lock.json`: a readable diff in every pull request, but
      a shape layer 12 decided keeps (13a's choice 8 set it aside);
    - (c) promises kept in release records: only for contracts some release names, while the
      case that matters is a contract edited in place before any release.

    *Recommended:* (a). Running the base's `ventoux promises` in CI needs a second checkout of
    the base commit, which 13e adds for its digest anyway; 13d's own base has no such command, so
    the CI wiring lands in 13e.

60. **The hash check becomes a command; the test stays.** `ventoux hashes --lock FILE [--before
    PROMISES]` prints today's lines, each contract changed in place followed by its paths
    (choice 58), indented. Exit 0 when every contract matches, 1 on any problem, 2 when the
    lockfile or the promises can't be read. `test_every_development_contract_matches_its_recorded_hash`
    stays as it is. *Recommended.*

61. **The diff's "its contract also differs" goes path by path too.** A step moved from `@2` to
    `@3` says each differing path on its own line, not proven:
    `payments.refund@2 -> payments.refund@3: timeouts.start_to_close: 10 -> 30`, from the same
    function, so the diff and the hash check read alike. Input policies and output sources stay
    judged as 13a judges them, never repeated as paths. The examples in the guides are made again
    from the commands. *Recommended.*

62. **Where it is recorded:** a new decision, **D57** ("Release notes in the record, and a
    contract's readable diff"); dated lines on D50 (records gain `notes`, the paths kept) and on
    design question 16 ("decided by D57"). The releases guide's "What the tool says" gains the
    notes; the activities guide says what the hash check prints. No new dependency.
    *Recommended.*

### Not in 13d

- The CI step (13e): the base checkout, the job summary, running the base's `ventoux promises`.
- Notes for records written before 13d: never added (a record is never written over).
- Re-judging an old release's notes with a newer diff: `ventoux diff` on two stored packages
  does that, and the record keeps what was said.
- Nothing at runtime: no workflow changes, no new engine version.

### Seams the tests use

- `next_release` and `record`, the `Record` and its `notes`; `FolderStore`; `release(folder,
  store, commit, catalog)`.
- `promise_changes(before, after)`; `check_hashes(catalog, recorded, before=None)`;
  `promise_of(contract)`.
- `diff(before, after, catalog)`, for a step moved to another contract.
- `main(["release", …])`, `main(["notes", …])`, `main(["promises"])`, `main(["hashes", …])`,
  through the guides' examples.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **A promise read path by path** (choice 58): a value that isn't JSON refused.
1. **The hash check says what changed** (choices 59 and 60): a promise given that isn't the
   lockfile's refused, never compared; `ventoux promises`, `ventoux hashes`.
2. **The diff's contract lines path by path** (choice 61).
3. **Notes in the record** (choices 52 to 57): a release whose notes the diff refuses is refused;
   a contract whose hash isn't the earlier record's refused; notes that say less than the digest
   refused; a wording revision; the first release; recomputed from the records alone.
4. **`ventoux notes`, the guides, the Promises** (choices 55 and 62).

### Decided while building

- **`ventoux notes PACKAGE RELEASE`, not `FOLDER`** (slice 4). Choice 55 wrote `ventoux notes
  FOLDER`, but a folder is the working tree, which the notes never read: the package's name and
  the records are all they need. So it takes the name and the number, as `ventoux activate` does:
  `ventoux notes refund 2 --releases releases [--wording K] [--plain]`.
- **The diff's wording line and `quoted` moved to `case/changes.py`** (slice 3), beside `Change`
  and `Rewritten`: a record keeps all three, and `case/releases.py` can't import `case/diff.py`,
  which imports it.
- **A note shows a literal as the definition writes it** (slice 4). 12a's
  `test_the_tool_names_paths_never_values` said `ventoux release` prints no value; its first line
  still names paths only, and the record's `changed` too, but the notes after it show the
  letter's text, written in the definition (13a's choice 9; learning question 11, told at this
  part's warm-up). The test now pins both, and D50's dated line says so.
- **The notes are made in the release tool, and the store refuses a record without them**
  (slice 3): `record` builds the record as 12a's did, `notes_for` adds its notes from the records,
  and `FolderStore.write` refuses a record whose notes are missing, so nothing written skips them.
- **Two guards only a bug could trip** (notes that say less than the digest, a wording
  revision's diff saying more than wording) are tested by giving the notes a diff that says too
  little or too much (`monkeypatch`): no package makes the real diff do either.
- **`promise_of` moved out of the contract hash** (slice 0), so the hash, the readable diff and
  `ventoux promises` read one promise; every hash in `contracts.lock.json` is unchanged.
- **Promises are read as plain JSON** (slice 1), never with numbers as decimals as a definition is:
  a promise is hashed as JSON gives it (`2.0` stays `2.0`), and a decimal is a value no promise
  holds.
- **`ventoux release` prints notes only when they compare something**: a first release prints its
  one line, as before.
- **One partial run** (selected with `-k release`, which includes the Temporal activation tests)
  had one failure whose output I didn't keep; the same selection passed when run again. Every run
  after it kept its output.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`R` is `tests/test_promise.py` (new), `N` is `tests/test_notes.py` (new), `C` is
`tests/test_catalog.py`, `D` is `tests/test_diff.py`, `E` is `tests/test_releases.py`. Checked
against the tests, 2026-10-24: every test named here exists, and every test in `R` and `N` is
named here.

| Promise | Test |
|---|---|
| A promise is compared leaf by leaf, in dotted paths: a value changed as `before -> after`, a key one side has as added or removed with its value, a list whole, outcomes never by their order; the class rename the hash hides is named | R `test_a_value_changed_is_said_path_by_path`, `test_a_key_one_side_has_is_added_or_removed_with_its_value`, `test_a_list_is_shown_whole_and_outcomes_never_by_their_order`, `test_a_class_renamed_shows_the_cause_the_hash_hides` |
| A promise holding a value no JSON holds is refused, never skipped | R `test_a_value_that_isnt_json_is_refused` |
| A contract changed in place says what changed, given the base commit's promise; a promise given that isn't the one the lockfile records is never compared; none given for it, or none at all, is said | R `test_a_contract_changed_in_place_says_what_changed`, `test_a_promise_given_that_isnt_the_lockfiles_is_never_compared`, `test_a_contract_with_no_promise_given_says_so`; C `test_a_contract_changed_without_a_new_version_is_reported` |
| `ventoux promises` prints each contract's promise; `ventoux hashes` passes when every contract matches, says what changed from the base's promises (the activities guide's example, as written), and exits 2 when a file can't be read | R `test_hashes_passes_when_every_contract_matches`, `test_the_base_commits_promises_say_what_changed`, `test_hashes_refuses_promises_it_cant_read` |
| Every hash in `contracts.lock.json` is unchanged | C `test_every_development_contract_matches_its_recorded_hash` |
| The diff's contract lines go path by path; an input or output only one contract has is said once; input policies stay judged, never repeated as paths | D `test_other_contract_differences_are_said_not_proven`, `test_an_input_policy_loosened_is_reported_looser` |
| A record keeps its notes: the diff of the two stored packages, the same when made from the records alone; a first release's against nothing; a wording revision's wording only | N `test_a_releases_notes_are_the_diff_of_the_stored_packages`, `test_a_wording_revisions_notes_hold_wording_only` |
| A contract the earlier record names that promises otherwise now refuses the release, and nothing is written | N `test_a_contract_whose_promise_isnt_the_earlier_records_refuses_the_release`, `test_the_release_command_refuses_when_the_notes_cant_be_made` |
| Notes that say less than the digest refuse the release, naming the paths; a wording revision whose diff says more than wording is refused | N `test_notes_that_say_less_than_the_digest_refuse_the_release`, `test_a_wording_revisions_diff_saying_more_refuses_it` |
| Nothing is written without its notes; a record from before 13d reads with none and is said so; notes that aren't a proof are refused when read | N `test_nothing_is_written_without_its_notes`, `test_a_record_from_before_13d_reads_with_no_notes`, `test_the_notes_command_says_a_record_has_none_and_refuses_one_it_lacks`, `test_notes_that_arent_a_proof_are_refused_when_read` |
| Notes are given no case file; the record's paths name no value, the notes show a literal as the definition writes it | N `test_notes_are_given_no_case_file`; E `test_the_tool_names_paths_never_values` |
| `ventoux release` prints the notes after what it did, in the diff's words; `ventoux notes` reads them again, plain with `--plain`; the releases guide's runs, as written | N `test_the_release_command_prints_the_notes_after_what_it_did`, `test_the_notes_command_reads_a_records_notes`; E `test_the_command_says_what_it_did`, `test_the_guides_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new modules too | `tests/test_layers.py`, unchanged |

## 13e. The CI step: what merging a pull request changes, in its job summary

Status: choices drafted 2026-10-24, from `main` at `9004cbd` (the 12e cold-start fix merged as
#51). Answered "all as recommended", the same day: choices 63 to 76. The dated lines on D55 and
D57 written before building 13e.

### Warm-up: learning question 34, why check input policies twice

> Why check sink policies twice? (`validate` before the plan runs, and again before each activity
> is scheduled; "input policies" since brief, D21.) Follow-up: if the runtime check catches
> everything with the real sources, why keep the static one at all?

Open since layer 5; last asked at 11d's warm-up, where "every path" came back a second time.
Answer the follow-up from memory first. It is 13e's question: the summary is the static check's
voice in the pull request, so whoever can change the definition hears of a loosening before any
case runs it.

Answered from memory, 2026-10-24: "every path" came back; "when it costs" and "who hears of it"
didn't, and were discussed. Recorded in the log; the question stays open.

### What this part is for

13a to 13d made the diff, its verdicts, its plain form and the release notes, all run by hand.
13e runs them where a change is reviewed: on each pull request, the job summary (choice 7) says
for each package whether merging it creates a release, a wording revision or nothing, then what
changes, in the plain form. And the hash check gets the base commit's promises, so a contract
changed in place says what changed (13d's choice 59).

### What the code does today

- `.github/workflows/ci.yml`: one job, `check`, on every push and pull request: `uv sync --locked`,
  `ruff format --check`, `ruff check`, `mypy`, `pytest`, with the dev server's CLI cached in
  `TEMPORAL_CLI_DIR` (12e). No `permissions` block, so the token has the repository's default
  rights. One checkout, of what GitHub gives: on a pull request, the merge commit it makes
  (`refs/pull/N/merge`), whose first parent is the base it was made on.
- The tools exist, each by hand: `digest`, `wording` and `changed` (12a); `diff` and `plain`
  (13a to 13c); `ventoux promises` and `ventoux hashes --before` (13d). The hash check also runs
  as a test (`test_every_development_contract_matches_its_recorded_hash`), saying only that a
  hash changed.
- `ventoux release` isn't run by CI, though the releases guide says "CI runs `ventoux release`":
  where records are kept for a deployment is still open (choice 76).

### Choices for 13e

63. **One command makes the summary; the YAML only calls it.** `ventoux summary --base BASE
    --head HEAD --packages DIR [--packages DIR …] --lock FILE --before PROMISES --summary-file FILE
    [--base-commit SHA --head-commit SHA]`: reads both trees, says each package and the contracts,
    prints the whole Markdown to the log, and appends it to the summary file (choice 69). Its
    logic is `tooling/summary.py`, tested with any catalog; the command uses the development
    catalog, as `ventoux diff` does (until `ventoux check` brings the deployment's, layer 14).
    The commits are given by CI, only to name them in the heading: the tool never reads git
    (brief, D50). *Recommended.*

64. **What is compared: the merge commit against its first parent.** On a pull request GitHub
    checks out the merge commit it makes, which is what merging creates; its first parent is the
    base it was made on. So the head is the default checkout (fetched with depth 2), and the base
    is a second checkout, into `base/`, of `HEAD^1`. Set aside: the pull request's head commit
    against `pull_request.base.sha`, which may be a base the branch was never merged with.
    *Recommended.*

65. **Per package, what merging does, from 12a's digest and wording, base against head**
    (brief, D50):
    - the same digest and wording: "nothing to release";
    - the same digest, other wording: "a wording revision of its latest release";
    - another digest: "a new release, unless an earlier release has this behaviour (`ventoux
      release` decides on merge, from the records)": the summary reads no records (choice 7);
    - only in the head: "a new package: its first release";
    - only in the base: "removed: merging it releases nothing; its records and the cases open on
      them are untouched";

    then, for a package in both whose digest or wording differs, the diff in the plain form
    (13c), which carries the verdicts' words and the paths. Packages are matched by name (the
    case's `case`, as a record names them), found as the folders holding a `case.json` under each
    `--packages` directory, in both trees. *Recommended.*

66. **The contracts: the hash check with the base commit's own promises.** CI runs `ventoux
    promises` in `base/` with the base's own code and environment (`uv run --directory base`), then
    the summary runs the hash check against `contracts.lock.json` with them (13d's choices 59 and
    60): a contract changed in place says what changed, path by path, in its own section.
    *Recommended.*

67. **Fail closed.** The step fails, saying why, and never reads as "nothing changed" when:
    - the base can't be checked out (the checkout step fails) or read (`--base` isn't a folder:
      exit 2);
    - a package in either tree can't be read or is refused (exit 1, naming it, its tree and why);
    - the diff refuses (a contract the catalog doesn't hold, a policy it doesn't know): exit 1;
    - the base's `ventoux promises` can't run, or prints what isn't promises: exit 2;
    - a contract changed in place: exit 1, after the summary says what changed.

    What the summary says up to the failure is still written, with the failure last. A looser
    change fails nothing: it is the reviewer's to judge, as `ventoux diff` exits 0.
    *Recommended.*

    *Amended 2026-10-25* (`docs/layers/fix-summary-validation.md`, found in layer 13's
    walk-through): "refused" covered only a package that can't be read. The summary now checks
    every package in the head as `ventoux release` does: an error fails the step, and the
    package's line says it can't be released as it is.

68. **The curriculum's negative test, end to end.** A base whose refund calls `payments.refund@2`
    and a head whose refund calls `@3`, which takes any amount: the summary's Markdown says "a new
    release" and "**Looser** … input amount …", and the summary file holds it. Through
    `tooling/summary.py` with a catalog holding `@3` (as 13a's tests do), and once through `main`
    with the development catalog for a change it holds (an approval removed, looser). *Recommended.*

69. **Never hidden, within GitHub's limit.** A step's summary may hold at most 1 MiB
    (1,048,576 bytes); more isn't shown. The whole text always goes to the step's log. When it
    fits, it goes to the summary too; when it doesn't, the summary holds one line per package
    (what merging does) and the contracts' status, then "The whole summary is N bytes, past the
    job summary's 1 MiB: it is in this step's log, under 'ventoux summary'." Never cut silently.
    Set aside: uploading it as an artifact (another action and a download, for a case that may
    never come). *Recommended.*

70. **Sends nothing.** The job summary only: no comment, no third-party action, no `gh`. The
    workflow gets `permissions: contents: read` at its top, so every job's token reads and nothing
    more, and it runs on `pull_request`, never `pull_request_target`, which would run the head's
    code with the base's rights and a token that can write. A pull request from a fork runs it the
    same way, with a read-only token. A test reads `ci.yml` as text and fails if it lacks the
    read-only permissions, names `pull_request_target`, or gives a step `write`. *Recommended.*

71. **On a push to `main`:** only `check` runs, as today. The summary job runs on pull requests
    only (`if: github.event_name == 'pull_request'`): a push has no pull request base, and what a
    merge released is `ventoux release`'s to record, which CI doesn't run yet (above). Said in the
    guide. *Recommended.*

72. **The existing checks stay as they are**, the cached CLI included. The summary is a second job,
    `changes`, beside `check`, so a red test never hides the summary and the summary never delays
    the tests. *Recommended.*

73. **The number written otherwise in a promise (from the review of #50).** `2` and `2.0` (or
    `true` and `1`) are equal to Python, not to the hash, so a base promise differing only so
    prints a changed contract with nothing under it. 13e is where that line reaches a reviewer.
    Offered: compare leaves as the hash writes them (canonical JSON), and say "what changed can't
    be said: no path differs as written" if still nothing differs. *Recommended:* in this pull
    request, with its negative test.

74. **The dev server's flags pinned to temporalio 1.34.0 (from the review of #51).** Not this
    layer's: *recommended* for the carried pull request with the idle thread-pool workers.

75. **Where it is recorded:** a dated line on D55 (the CI step: the job summary, what it compares,
    fail closed, read-only) and on D57 (the base's promises in CI); the releases guide's "What
    changed: the diff" gains "On each pull request", with the summary's example run as written.
    No new dependency: no third-party action, no YAML parser (the workflow test reads text).
    *Recommended.*

76. **`ventoux release` in CI, and where records live:** not in 13e. Running it on a merge needs a
    place to keep records that outlives a runner, which is a deployment's decision (layer 14,
    with `ventoux check`). Until then the releases guide's "CI runs `ventoux release`" becomes
    "run `ventoux release` on merge, where your records are kept". *Recommended.*

### Not in 13e

- Running `ventoux release` in CI (choice 76).
- A comment on the pull request (choice 7, set aside).
- The pinned flags and the idle thread-pool workers (choice 74, carried).

### Seams the tests use

- `summarize(base, head, packages, catalog, recorded, before)` in `tooling/summary.py`, and what
  it returns: the Markdown and the exit code.
- `main(["summary", …])`, with a summary file in a temporary folder.
- `.github/workflows/ci.yml`, read as text.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **A promise's number written otherwise** (choice 73).
1. **What merging does, per package** (choices 63 to 65): a package only in the base said
   removed, never left out.
2. **The diff and the contracts in the summary** (choices 66 to 68): the curriculum's test end to
   end; a contract changed in place.
3. **Fail closed and never hidden** (choices 67 and 69): a refused package fails the step; a
   summary past the limit says where the whole text is.
4. **The workflow, the guide, the Promises** (choices 70 to 72, 75, 76): the read-only test.

### Decided while building

- **A package only one tree shows is never said removed, or new, while the other tree has one it
  can't read** (slice 3, found writing its negative test): the unreadable one may be it. Such a
  package reads "not compared: a package in the head can't be read (below)", and the step fails.
- **Two packages of one name in a tree are refused**, naming the second folder: a record names a
  package by its case's `case` (brief, D50), so which one merging releases would be a guess.
- **Two messages were pinned from what the code says,** not what I guessed: the diff's refusal of
  a contract the catalog doesn't hold, and Python's reading of a `case.json` that isn't JSON.
- **The workflow's test reads the lines that do something,** its comments left out: the workflow's
  own comment says it never uses `pull_request_target`.
- **Both checkouts in `changes` keep no credentials** (`persist-credentials: false`): the token,
  read-only anyway, stays out of their git configuration.
- **The base's commit reaches the command through an environment variable** (`BASE_COMMIT`),
  never written into the shell line by GitHub's expressions.
- **The workflow's commands were run locally first**, against `main` in its own worktree: `uv run
  --directory base --locked ventoux promises` builds the base's own environment, its progress on
  stderr and the promises alone on stdout; then `ventoux summary`, exit 0.
- **A diff's plain form keeps its own headings** (`## refund: what changes`), at the level of the
  summary's `## Packages` and `## Contracts`: the summary shows it as `ventoux diff --plain` prints
  it.

#### Decided while building, after the review of #52

- **Escaped where Markdown is written, so what is data stays plain.** A sheet's lines (`nevers`,
  which its tests read), a summary's failures and a change's `said` stay as written; only
  `plain`, `case_map`, `never_sheet` and the summary escape them as they place them. The
  developer forms print what they printed before.
- **Fifteen expectations changed, each an escape only:** `order_id` reads `order\_id`, `>`
  reads `&gt;` and `->` in what a change says reads `-&gt;`, outside code spans; paths in code
  spans are unchanged. Each diff was read before the expectation was updated, and the guides'
  examples were made again from the commands, never edited by hand.
- **No Markdown renderer is a dependency,** none is installed, so the tests check the escaped text
  itself (every `<` gone, each character escaped), not a rendering.
- **The review's run, as a test:** a task `vet` before `pay`, its condition comparing review's
  outcome with the review's literal, and `pay` moved to an `@3` that takes any amount.

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`Y` is `tests/test_summary.py` (new), `R` is 13d's `tests/test_promise.py`, `D` is 13a's
`tests/test_diff.py`. Checked against the tests, 2026-10-24, again after the review of #52: every
test named here exists, every test in `Y` is named here, and every test 13e added to `R` is named
here.

| Promise | Test |
|---|---|
| A number written otherwise in a promise is said as the hash writes it (`2 -> 2.0`); a hash that differs where no path does says what changed can't be said, never a contract with nothing under it | R `test_a_number_written_otherwise_is_said_as_the_hash_reads_it`, `test_a_hash_that_differs_where_no_path_does_says_so` |
| What merging does to each package, from 12a's digest and wording, said as only the two trees show (the same behaviour and wording as the base; the same behaviour, other wording; a new release; a first release; removed), never left out; matched by name | Y `test_what_merging_does_to_each_package`, `test_a_package_only_in_the_base_is_said_removed`, `test_packages_are_matched_by_name_not_by_folder` |
| The curriculum's negative test, end to end: an input policy loosened reads Looser in the summary, and fails nothing | Y `test_an_input_policy_loosened_reads_as_looser_in_the_summary` |
| The contracts: the hash check with the base commit's own promises; a contract changed in place says what changed and fails the step; matching contracts are said to | Y `test_a_contract_changed_in_place_says_what_changed_and_fails`, `test_contracts_that_match_are_said_to` |
| Fail closed: a package that can't be read, a diff the catalog can't make, a checkout that isn't a folder, base promises that can't be read: each fails the step, said in the summary, and nothing is read as removed or unchanged on a guess | Y `test_a_package_that_cant_be_read_fails_the_step_and_is_never_read_as_removed`, `test_a_diff_the_catalog_cant_make_fails_the_step`, `test_a_base_that_isnt_a_folder_cant_be_read`, `test_base_promises_that_cant_be_read_fail_and_say_so` |
| Never hidden: the whole text to the log, appended to the summary file; past the limit, one line per package and where the whole text is | Y `test_the_command_logs_the_whole_summary_and_appends_it`, `test_a_summary_past_the_limit_says_where_the_whole_text_is`, `test_the_command_says_where_a_summary_too_long_is` |
| Sends nothing: `permissions: contents: read`, never `pull_request_target`, nothing that writes or comments; the summary job on pull requests only, from the base's own promises, both checkouts without credentials | Y `test_the_workflow_sends_nothing_and_reads_only`, `test_the_summary_runs_on_pull_requests_from_the_base_s_own_promises` |
| Two packages of one name in a tree are refused, naming the second folder | Y `test_two_packages_of_one_name_in_a_tree_are_refused` |
| The existing checks are as they were, the cached CLI included; a push to `main` runs them only | Y `test_the_existing_checks_are_as_they_were` |
| The releases guide's summary runs as written | Y `test_the_guides_summary_runs_as_written` |
| Text a definition writes is shown, never rendered: the review's run has no `<` from a definition in the summary, its literal shown escaped and the Looser line visible; a backtick, `*`, `[`, `#` and a line break shown as written (from the review of #52, choice 77) | Y `test_html_a_pull_request_writes_never_reaches_the_summary`, `test_markdown_a_definition_writes_is_shown_as_written` |
| A path's code span and the hash check's block are fenced past any backtick run in them | Y `test_a_path_in_a_code_span_is_fenced_past_its_backticks`, `test_a_backtick_in_a_contract_never_closes_the_hash_checks_block` |
| The plain form, the map and the sheet escape what they place, and their tests and the guides' examples pin it | 13c's `tests/test_plain.py` and `tests/test_sheet.py`, `test_the_guides_map_runs_as_written`; D `test_the_guides_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal: the summary is `tooling`'s | `tests/test_layers.py`, unchanged |

### From the tutor review of #52: text a pull request writes reaches rendered Markdown

The review's run: a head adds a task before `pay` whose condition is `review.outcome =
"approve</li></ul><details><summary>checked: nothing loosens</summary>"`, and moves `pay` to an
`@3` that takes any amount. `summarize` exits 0, and rendered (CommonMark, then the HTML tree
browsers and GitHub's sanitizer build), the Looser line and everything after it sit inside a
collapsed `<details>` reading "checked: nothing loosens". A pull request can hide the curriculum's
negative test from its reviewer.

Every route found, checked against the code:

- **the plain form** (`case/plain.py`): each change's `said` (literals as the expression renderer
  writes them, through `json.dumps`, which leaves `<` and `>` as they are), the readings and their
  fine print, the wording lines' titles, the entries' and changes' paths;
- **the map and the sheet** (`case/sheet.py`): the readings, the rules' sentences, the package's
  name in its headings, the sheet's lines (roles, contract references, field names);
- **the summary** (`tooling/summary.py`): the folder names and refusal messages in "Why the step
  fails", which quote what the tree holds; and the hash check's block, fenced with three
  backticks, which a docstring or a field's title holding three backticks ends early (the head's
  own code writes the catalog);
- names a definition gives are checked against patterns (a case's `case`, `[a-z][a-z0-9-]*`), but
  not every key that becomes a path is, so a path is treated as text too.

The developer forms (`ventoux diff`, `ventoux release`, `ventoux notes` without `--plain`,
`ventoux hashes`) print plain text to a terminal, and a record keeps data: neither is Markdown.

77. **Where the escaping goes: where Markdown is written, never at the source.** One small module,
    `case/markdown.py`, and every renderer of Markdown uses it for every piece of text it didn't
    write itself: the plain form, the map and the sheet, so `ventoux diff --plain`, `ventoux notes
    --plain`, `ventoux map` and the summary all inherit it; and the summary's own pieces (package
    and folder names, refusal messages, commits):
    - `text(s)` for text in a paragraph or list item: `&`, `<` and `>` as the entities `&amp;`,
      `&lt;` and `&gt;`; a backslash before each of `\`, `` ` ``, `*`, `_`, `[`, `]`, `~`, `#`,
      `|` and `!`; and a line break, a carriage return or a tab shown as `\n`, `\r` or `\t`, so a
      value never starts a line of its own;
    - `code(s)` for a path in a code span: fenced with one backtick more than the longest run in
      it, as CommonMark allows, so nothing in it closes it;
    - `block(lines)` for the hash check's lines: fenced with one backtick more than the longest
      run in them, never less than three.

    Set aside: escaping at the source (the diff's `said`, the readings), which would put entities
    in the developer forms and in every record's notes; and backslashes before every ASCII
    punctuation mark, which CommonMark allows and which would be safe without an argument, but
    turns every `refund-order@1, giving order_id` into `refund\-order\@1\, giving order\_id` in
    the raw text the guides show. The set above is enough because a value never starts a line (its
    line breaks are shown, not kept), so only what can open a construct inside a line matters:
    raw HTML and autolinks (`<`), entities (`&`), emphasis (`*`, `_`, `~`), code (`` ` ``), links
    and images (`[`, `]`, `!`), and the escape itself (`\`); `#` and `|` are escaped too, should a
    value ever be placed at a line's start. *Recommended.*

78. **"Nothing to release" claims what the summary doesn't know (optional, from the review).** It
    assumes the base was released when it merged; the summary reads no records. Offered: each line
    says only what the two trees show, and leaves releasing to `ventoux release`:
    - the same digest and wording: "the same behaviour and wording as the base";
    - the same digest, other wording: "the same behaviour as the base, other wording: a wording
      revision, if the base's behaviour is the latest release's (`ventoux release` decides on
      merge, from the records)";
    - the others as they are (a new release already says `ventoux release` decides).

    *Recommended:* yes, in this pull request, beside the escaping.

79. **Where it is recorded:** a dated line on D56 (the Markdown the plain form, the map and the
    sheet print escapes what a definition writes) and one on 13e's line in D55 (the summary
    inherits it, and fences the hash check by its content). *Recommended.*

Answered "all as recommended", 2026-10-24: choices 77 to 79.

The negative test, test-first: the review's run, the literal shown escaped and no `<` in the
summary coming from a definition; then literals holding a backtick, a `*`, a `[` and a `#`, each
shown as written once rendered, and a docstring holding three backticks kept inside the hash
check's block.
