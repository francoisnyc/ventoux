# Fix: the summary checks the head as `ventoux release` does

A fix, not a layer: no warm-up, and nothing new to build. Found in layer 13's walk-through,
stop 2 (learning question 41, "Found in the walk-through, not fixed"), and left for its own pull
request.

Status: choices put, 2026-10-25, each with a recommendation. Answered "1 to 8, all as recommended",
the same day. The dated lines on D55 and on 13e's choice 67, and the releases guide's sentence,
written before building. Built test-first, slices 1 to 6, and the Promises table checked against
the tests, the same day (see "Decided while building").

## The bug

`ventoux summary` says what merging does to each package, and choice 67 of 13e promised that "a
package in either tree [that] can't be read or is refused" fails the step. It reads each package
with `read_package`, which parses it, and never runs `checked` (`tooling/releases.py`), the
validation `ventoux release` runs before it releases anything. So:

- **A package `ventoux release` will refuse is said to be released.** A head whose `settle.when`
  reads an undeclared field and whose `call_customer` names a role nobody registered:

  ```
  $ ventoux release ... (on merge)
  steps.settle.when: EXPRESSION_INVALID: ==[0]: nosuch is not a declared field
  steps.call_customer.roles: UNKNOWN_ROLE: nobody-has-this is a role nobody registered: ...

  $ ventoux summary ... (on the pull request)
  - **refund**: a new release, unless an earlier release has this behaviour (`ventoux release` decides on merge, from the records).
  exit 0
  ```

- **A warning reaches nobody before merge.** The releases guide's own example drops `settle`'s
  `requires`. The summary shows its Looser line, and its plain form says `settle` "starts by
  itself when the case opens". But every new case would start with `settle#1` failed, since its
  condition reads `review.outcome` before anyone has set it. Validation says so; the summary
  doesn't:

  ```
  MAY_BE_UNSET (warning) at steps.settle.when: settle reads review.outcome, and doesn't wait for
    review, which gives it: if settle runs first, it fails and needs attention: require review
  ```

  Only `ventoux release` prints it, on merge, after the review, and releases anyway.

The Promises table didn't catch it: its fail-closed test refuses a package that can't be read
(`case.json` isn't JSON), never one that reads and fails validation.

## Choices

Answer by number.

1. **Every package in the head is checked, changed or not.** `ventoux release` checks a package
   before it compares it with its records, so it refuses an unchanged package too, and a pull
   request can make one fail without touching it: its code changes the catalog (a role, a
   contract), or the checks themselves. The base is never checked: it isn't what merging
   releases, and its issues aren't this pull request's. *Recommended.* Set aside: checking only
   the packages that change (an unchanged package the head's code breaks would pass, and
   `ventoux release` refuse it on merge).

2. **The same check, never a copy:** `summarize` calls `checked(package, catalog)` from
   `tooling/releases.py`, with the catalog it already diffs with, and reads its refusal and its
   warnings. What the summary says a release will refuse is then what release refuses, by
   construction. *Recommended.*

3. **An error fails the step, and the package's line says so.** In place of "a new release…" (or
   "the same behaviour and wording as the base", for one that didn't change), the line reads:

   ```
   - **refund**: can't be released as it is: `ventoux release` refuses it (below).
   ```

   Exit 1 (`REFUSED`). Under "Why the step fails", one line per error, as `ventoux release` says
   it, with the package and its tree:

   ```
   - refund, in the head: steps.settle.when: EXPRESSION\_INVALID: ==\[0\]: nosuch is not a declared field
   - refund, in the head: steps.call\_customer.roles: UNKNOWN\_ROLE: nobody-has-this is a role nobody registered: ...
   ```

   The diff is still made and shown for a package that changed: the reviewer sees what the
   pull request does, and why it can't be released. *Recommended.* Set aside: keeping the
   outcome line and adding only the failure (the line would still claim a release that merging
   won't make).

4. **Warnings are shown, and fail nothing**, as `ventoux release` releases with them. Shown for
   a package merging changes (a release, a wording revision, a first release), after its diff,
   under its own heading, each as `ventoux release` says it:

   ```
   ### What `ventoux release` warns

   - steps.settle.when: MAY\_BE\_UNSET: settle reads review.outcome, and doesn't wait for review, which gives it: if settle runs first, it fails and needs attention: require review
   ```

   An unchanged package's warnings aren't shown: they aren't this pull request's, and repeating
   them on every pull request teaches people to skip them. *Recommended.* Set aside: only the
   warnings the base doesn't have (it would mean checking the base too, and matching issues
   across two versions of a definition, whose paths may move).

5. **Past the 1 MiB limit,** nothing new: the short form keeps each package's line (so "can't be
   released as it is" stays) and "Why the step fails" (so every error stays); the warnings are in
   the whole text, in the log, which the short form already points to. *Recommended.*

6. **Escaped as the rest of the summary is** (13e, choice 77): an issue's message quotes names a
   definition writes (a role, a field, a step), so each line goes through `text()`. A test puts a
   `<` and a `*` in an unregistered role's name and reads them shown as written.
   *Recommended.*

7. **The negative tests, in `tests/test_summary.py`, each seen failing first:**
   - the head with two errors (`EXPRESSION_INVALID`, `UNKNOWN_ROLE`): exit 1, the line "can't be
     released as it is", both errors under "Why the step fails" (today: "a new release", exit 0);
   - an unchanged package the head's catalog refuses (its role not registered there): exit 1,
     the same line in place of "the same behaviour and wording as the base";
   - the guide's head (`settle`'s `requires` dropped): exit 0, `MAY_BE_UNSET` under its diff;
   - a base that fails validation and a head that passes: exit 0, nothing said about the base;
   - an unchanged package with a warning: exit 0, the warning not shown.

   *Recommended.*

8. **Where it is recorded:**
   - this note, with its Promises table, checked both ways before the pull request;
   - a dated line on D55, after 13e's: the summary checks every package in the head as
     `ventoux release` does; an error fails the step, a warning is shown for a package merging
     changes;
   - a dated line on 13e's choice 67 in `docs/layers/13-diff.md`, pointing here;
   - the releases guide's "On each pull request": the sentence on what fails the step names a
     package `ventoux release` would refuse, and its example, made again from the command, now
     shows `MAY_BE_UNSET` under the diff;
   - learning question 41's finding: "fixed in" this pull request (the finding is recorded in
     #53, so this line lands once #53 is merged, or in #53 if it isn't yet).

   *Recommended.*

## Seams the tests use

The ones 13e's tests already use, nothing new: `summarize(base, head, packages, catalog,
recorded, before)` and what its `Summary` says (`outcomes`, `code`, `text`, `failures`), and the
`ventoux summary` command for the guide's example. `checked` is called, never tested again here.

## Slices, in order

1. The head with two errors fails the step, its line saying so (choices 2 and 3), negative first.
2. An unchanged package the head's catalog refuses fails it too (choice 1).
3. A changed package's warnings are shown after its diff; an unchanged one's aren't (choice 4).
4. A base that fails validation says nothing (choice 1).
5. An issue's message is shown as written (choice 6).
6. The guide's example, made again from the command (choice 8).

## Decided while building

- **One check, split so both can read it** (choice 2): `issues_of(package, catalog)` in
  `tooling/releases.py` gives every issue; `checked` refuses on its errors as before, and the
  summary reads the same list. `is_error` says what refuses: anything but a warning (fail
  closed). `ventoux release` is unchanged.
- **The warnings' heading names the package** (choice 4): a first release has no diff to sit
  under, so the heading is ``## refund: what `ventoux release` warns``, after the package's diff
  when it has one.
- **A role's name can't carry a `<`** (choice 6): its pattern refuses it when the package is
  read, before any check, so it fails as a package that can't be read, already escaped. The test
  uses a condition's field name instead: `no<such*`, shown `no&lt;such\*`.
- **The review's head is one `ventoux release` refuses** (slice 5): `vet`'s condition compares
  `review.outcome` with an outcome `review` doesn't declare. It now fails the step, and its error
  quotes the literal: a second way in, escaped too, which a deliberate break (failures not
  escaped) showed failing both tests.
- **Two of 13e's tests changed their trees, not what they check.** The diff the catalog can't
  make now comes from the base (it calls `@9`), so the head passes the check and only the diff
  refuses; and the contracts' block is read from trees with no package, since that test's catalog
  holds one contract no package could run on.
- **Each later slice's test passed at once** (slice 1's code checks every head package), and was
  seen to bite on a deliberate break: checking only changed packages, checking the base,
  warnings shown for every package, warnings only where behaviour changed, failures not escaped.

## Promises

Checked against the tests before the pull request, both ways: every promise names a test that
exists, and every test this fix added is named. `S` is `tests/test_summary.py`.

| Promise | Test |
|---|---|
| A package `ventoux release` would refuse fails the step; its line says it can't be released as it is; each error said as release says it, with the package and its tree; its diff still shown | S `test_a_package_release_would_refuse_fails_the_step` |
| The same check as release, never a copy: the summary refuses exactly what release refuses | S `test_the_summary_refuses_exactly_what_release_refuses` |
| Every package in the head is checked, changed or not | S `test_an_unchanged_package_release_would_refuse_fails_the_step` |
| The base is never checked | S `test_the_base_is_never_checked` |
| A warning fails nothing, and is shown after the diff of a package merging changes | S `test_a_changed_packages_warnings_are_shown_after_its_diff` |
| A first release and a wording revision show their warnings too | S `test_a_new_package_and_a_wording_revision_show_their_warnings_too` |
| An unchanged package's warnings aren't shown | S `test_an_unchanged_packages_warnings_arent_shown` |
| Past the limit, a refused package's line and its errors stay | S `test_past_the_limit_a_refused_package_and_its_errors_stay` |
| An issue's message is shown as written, never rendered | S `test_an_issues_message_is_shown_as_written`, `test_html_a_pull_request_writes_never_reaches_the_summary` |
| The guide's example runs as written, its warning included | S `test_the_guides_summary_runs_as_written` |
| A diff the catalog can't make still fails the step (13e, kept) | S `test_a_diff_the_catalog_cant_make_fails_the_step` |
