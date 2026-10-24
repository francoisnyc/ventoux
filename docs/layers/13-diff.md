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
- **The reason:** "an earlier workflow tool failed at the user's company largely because nobody
  could tell what had changed between process versions". And the diff is the review step for
  definitions a builder *generates* (layer 14), so its output must stay readable even when nobody
  wrote the JSON by hand. This is the curriculum's check-yourself: a JSON diff of generated output
  is noise.
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

Status: choices drafted 2026-10-24, from `main` at `3888f95` (13a merged as #47). Waiting for
answers by number. Nothing built yet.

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
