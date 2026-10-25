# Fix: the summary checks the head as `ventoux release` does

A fix, not a layer: no warm-up, and nothing new to build. Found in layer 13's walk-through,
stop 2 (learning question 41, "Found in the walk-through, not fixed"), and left for its own pull
request.

Status: choices put, 2026-10-25, each with a recommendation; waiting for answers by number.

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
