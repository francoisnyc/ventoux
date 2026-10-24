# Layer 13: the semantic diff

Status: draft, 2026-10-24. Prior art read (the `chartering` prototype at `81389b3`, its `main`);
layer 13 explained, split into five parts, and 13a's choices put with a recommendation each.
Waiting for answers by number. Nothing built yet. Layer 12's walk-through and check-yourself are
deferred, by the user's choice, and aren't part of this layer.

## Warm-up: learning question 40, arrival is a fact, content is not

> "Arrival is a fact, content is not": give an example.

Open since layer 11's check-yourself (2026-10-21), and not asked during layer 12. Answer from
memory first. Last time these didn't come back: the sender check that makes an arrival a fact,
that content may still start steps and set fields (it informs), and the line validation draws
(`UNTRUSTED_TRIGGER`). The answer and the discussion are recorded in `docs/LEARNING.md`.

It is relevant here: a diff that says "looser" about who may send an event, or about a field's
`untrusted:` mark, relies on exactly that line.

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
| **13a: the change list, by effect** | `diff(before, after, catalog)`: every behaviour change between two packages, said in the developer form by path, each with a verdict (stricter, looser, or not proven). Judged in 13a: the guards on data (input policies, `untrusted:` marks, `sensitive`, who sees a field). Every other change is said and left unproven. `ventoux diff OLD NEW` | a change that loosens an input policy is reported as looser, never hidden |
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
     plan's field; `sensitive` removed; a field seen by more roles (its `visible_to` widened or
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

18. **Witnesses for 13a's four comparisons:** a run with `run_case` where the old version refuses
    and the new one lets through:
    - input policy: a value from `untrusted:customer` refused by `@2`'s `amount`, taken by `@3`'s;
    - `untrusted:` mark: the same value, refused while the field carried the mark, taken once it
      doesn't;
    - `sensitive`: refused to a workflow step while sensitive, given once not;
    - who sees: the field absent from `auditor`'s view, then present.

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

### Promises

Each claim this section makes about behaviour, and the test that would fail if it weren't true.
`D` is `tests/test_diff.py` (new). Drafted before building; to be checked against the tests
before the pull request opens.

| Promise | Test |
|---|---|
| A step moved to a contract whose input policy accepts more is reported looser, at the step's path, naming the input and both policies: never hidden (the curriculum's negative test) | D `test_an_input_policy_loosened_is_reported_looser` |
| A policy that accepts less is stricter; two policies neither wider nor narrower are not proven | D `test_an_input_policy_tightened_is_stricter`, `test_policies_neither_wider_nor_narrower_are_not_proven` |
| `compared` orders every pair of the two kinds exactly, and refuses a kind it doesn't know | D `test_policies_are_compared_exactly`, `test_a_policy_kind_the_diff_doesnt_know_is_refused` |
| A contract the catalog doesn't hold refuses the diff, naming it | D `test_a_contract_missing_from_the_catalog_refuses_the_diff` |
| An input in only one of the two contracts, or another difference between them, is said and not proven | D `test_other_contract_differences_are_said_not_proven` |
| An `untrusted:` mark removed is looser, added is stricter, relabelled is not proven, on case fields, payload fields and a plan's fields | D `test_an_untrusted_mark_removed_is_looser`, `test_an_untrusted_mark_added_is_stricter`, `test_a_relabelled_mark_is_not_proven`, `test_marks_on_payloads_and_plans_are_judged` |
| `sensitive` removed is looser; added is stricter | D `test_sensitive_removed_is_looser`, `test_sensitive_added_is_stricter` |
| Who sees a field is compared as `seen_by` computes it: widened looser, narrowed stricter, both not proven | D `test_visible_to_widened_is_looser`, `test_visible_to_narrowed_is_stricter`, `test_readers_both_added_and_removed_are_not_proven` |
| A new role named anywhere is said on every field without `visible_to`, and on outcomes and outputs, naming the change that caused it (a change the JSON diff hides) | D `test_a_new_role_sees_every_unnarrowed_field` |
| A change outside the comparisons is said at its path, not proven, with the definition's literals before and after | D `test_a_change_the_diff_doesnt_judge_is_said_not_proven` |
| Every behaviour path 12a's `changed` sees is covered by a change | D `test_the_diff_says_everything_the_digest_sees` |
| The same behaviour digest gives no change: reformatting and wording alone included | D `test_the_same_behaviour_has_no_changes` |
| Wording is listed apart, before and after, never as behaviour | D `test_wording_is_listed_apart` |
| "Not proven" is counted with looser in the summary, and listed before stricter | D `test_not_proven_counts_with_looser` |
| A renamed step is one removed and one added, the added one saying it behaves as the removed one did and that a migration must map it | D `test_a_renamed_step_is_removed_and_added` |
| Changes come in the order of choice 10, the same every time | D `test_changes_come_in_the_packages_order` |
| The diff is given only the two packages and the catalog: no case file to quote from | D `test_the_diff_reads_only_packages_and_the_catalog` |
| Each looser and stricter comparison has a witness run, and the witnesses cover the list | D `test_each_comparison_has_a_witness`, `test_the_witnesses_cover_every_comparison` |
| The command exits 0 when it compared, 1 when refused, 2 when unreadable, and prints the developer form | D `test_the_command_says_the_diff` |
| The guide's example runs as written | D `test_the_guides_example_runs_as_written` |
| `case` reads no clock or I/O and imports no Temporal, in the new module too | `tests/test_layers.py`, unchanged |
