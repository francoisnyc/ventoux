# Fix: a contract is checked against the hash the base recorded

A fix, not a layer: no warm-up, and nothing new to build. Found in layer 13's walk-through,
stop 7 (learning question 41, "Found in the walk-through, not fixed"), and left for its own pull
request; confirmed in the code by the tutor review of #53.

Status: choices put, 2026-10-25, each with a recommendation. Answered "1 to 10, all as
recommended", the same day. The dated lines on D5 and D57, the activities guide's paragraph and
learning question 41's lines written before building. Built test-first, slices 0 to 8, and the
Promises table checked against the tests, the same day (see "Decided while building").

## The bug

Contracts are immutable: CI "fails if it changed without a new number" (brief, D5). Two places
check it, and both compare the catalog with the **head's** `contracts.lock.json`:

- the `check` job's test, `test_every_development_contract_matches_its_recorded_hash`;
- the `changes` job's summary (`check_hashes` in `core/hash_check.py`), which also reads the base
  commit's promises, but only to describe a mismatch it is given (brief, D57).

So a pull request that edits a contract in place and rewrites its hash in the same commit passes
both. The walk-through's run: `orders.lookup@1`'s `start_to_close` from 10 to 5, its lockfile
entry replaced by the new hash, the real base's promises given:

```
## Contracts

Every contract matches `contracts.lock.json`.
exit 0
```

The only trace is two lines of hex in the pull request's diff. D5's rule holds only if a reviewer
reads them.

## Choices

Answer by number.

1. **Each contract the base's lockfile records is checked against the base's hash.** For a
   reference the base records and the head's catalog holds, the catalog must hash as the base
   recorded it. If it doesn't, it changed in place, whatever the head's lockfile says: the
   existing line (`orders.lookup@1 changed without a new version: register it as
   orders.lookup@3.`), then what changed, path by path, from the base's promises, and the step
   fails (exit 1). *Recommended.*

2. **A recorded hash never changes, said even where the contract didn't.** For a reference the
   base records, the head's lockfile must keep the base's hash. If it rewrites or drops it, that is
   said, under the contract's line when the contract changed too:

   ```
   orders.lookup@1 changed without a new version: register it as orders.lookup@3.
     timeouts.start_to_close: 10 -> 5
     contracts.lock.json rewrites the hash the base recorded: a recorded hash never changes
   ```

   and alone when only the lockfile changed (`orders.lookup@1: contracts.lock.json rewrites the
   hash the base recorded: a recorded hash never changes; put back <the base's hash>`). Either
   fails the step. Without this, a rewritten entry for an unchanged contract would read as "changed
   without a new version", which the contract wasn't. *Recommended.* Set aside: ignoring the head's
   entry for a recorded reference (the wrong hash would reach `main`, and the next pull request's
   base).

3. **The head's lockfile is still for what the base doesn't record.** A contract new in the head
   must be recorded in the head's lockfile, with its hash, as today (`orders.lookup@3 is not
   recorded yet: add "orders.lookup@3": "…".`). A contract the base records and the head's
   catalog no longer holds is retired, never an error, whatever either lockfile says.
   *Recommended.*

4. **The base's promise is read against the base's hash.** A promise given in `--before` is used
   to say what changed only if it hashes to what the **base's** lockfile records: it is the base
   commit's own promise, and that is the hash it must give (brief, D57). Otherwise the line says
   what changed can't be said, as today. *Recommended.*

5. **The command takes the base's lockfile: `ventoux summary --base-lock FILE`, required.** Fail
   closed: a base lockfile that can't be read, or isn't a JSON object by contract reference, fails
   the step with exit 2, said in the log and the summary, as `--lock` and `--before` are today. A
   base with no `contracts.lock.json` at all can't be read, and fails the same way. *Recommended.*
   Set aside: an optional argument (a summary run without it would be blind again, and say nothing).

6. **CI passes the base checkout's lockfile, one argument and nothing else:** `--base-lock
   base/contracts.lock.json` on the `ventoux summary` line. The permissions, the triggers and the
   checkouts are unchanged; the workflow test gains the argument. *Recommended.*

7. **The summary's line when everything holds says what was checked:** "Every contract matches the
   hash the base recorded, and every new one is recorded in `contracts.lock.json`." in place of
   "Every contract matches `contracts.lock.json`.", which no longer says what was compared.
   *Recommended.*

8. **`ventoux hashes` and the `check` job's test stay as they are, and their blind spot is said.**
   Both run where there is no base: on a developer's machine, and on every push. They catch an
   edit whose hash wasn't rewritten, and say so in the guide: a hash rewritten with the contract is
   caught only by the pull request's summary, against the base. `core/hash_check.py`'s check gains
   the base's lockfile as an optional argument; the command doesn't. *Recommended.* Set aside:
   `ventoux hashes --base-lock` (a second way in for a check whose place is the pull request).

9. **The negative tests, in `tests/test_summary.py`, each seen failing first:**
   - the walk-through's run: `orders.lookup@1` changed from 10 to 5 and its hash rewritten in one
     commit fails, saying `timeouts.start_to_close: 10 -> 5` and the rewritten hash (today: every
     contract matches, exit 0);
   - a hash rewritten alone, for a contract that didn't change, fails, saying what to put back;
   - a new contract recorded only in the head's lockfile passes; one not recorded fails as today;
   - a contract retired from the catalog passes, its base entry kept or dropped;
   - a base lockfile that can't be read fails with exit 2, said in the summary (through the
     command);
   - the workflow passes `--base-lock base/contracts.lock.json`, and its permissions are as they
     were.

   *Recommended.*

10. **Where it is recorded:**
    - this note, with its Promises table, checked both ways before the pull request;
    - a dated line on D5: CI's rule is enforced in the pull request's summary, against the base's
      lockfile; the `check` job's test and `ventoux hashes` see only the head;
    - a dated line on D57: the base's promise is read against the base's hash;
    - the activities guide's "Changing a contract", saying where the rule is enforced and the
      blind spot; the releases guide's "On each pull request" and its example, made again from
      the command;
    - learning question 41: "fixed in" on both findings, #54 for the first (its line couldn't
      land with #54, which merged first) and this pull request for the second.

    *Recommended.*

## Seams the tests use

`summarize(base, head, packages, catalog, recorded, before, base_recorded)` and what its
`Summary` says (`code`, `text`), the `ventoux summary` command for an unreadable base lockfile and
the guide's example, and the workflow's text. `check_hashes` is reached through the summary, as CI
reaches it.

## Slices, in order

0. The plumbing: `summarize` takes the base's lockfile, the command `--base-lock` (required), CI
   the argument; nothing reads it yet.
1. The walk-through's run fails: a contract changed with its hash rewritten (choices 1, 2),
   negative first.
2. A recorded hash rewritten or dropped alone fails, saying what to put back (choice 2).
3. The head's lockfile records what the base doesn't (choice 3).
4. A contract retired from the catalog is never an error (choice 3).
5. The base's promise is read against the base's hash (choice 4).
6. A base lockfile that can't be read fails, exit 2 (choice 5).
7. CI passes the base checkout's lockfile (choice 6).
8. The all-clear line says what was compared; the guide's example made again (choices 7, 10).

## Decided while building

- **The plumbing came first** (slice 0): `--base-lock` is required, so the workflow had to pass
  it in the same commit or the `changes` job would stop at the command line. Nothing read it until
  slice 1, whose test then failed for the right reason: "Every contract matches", exit 0. The
  workflow's own test is slice 7.
- **`summarize` takes the base's lockfile with no default:** a caller that forgets it can't run
  blind (fail closed). `check_hashes` takes it as an optional `base`, so `ventoux hashes` and the
  `check` job's test, which have no base, are unchanged (choice 8); a contract the base records is
  checked in `against_base`.
- **"Rewrites" or "drops"** (choice 2): an entry the head's lockfile removes says it drops the
  hash the base recorded, and what to put back.
- **The tests use a one-contract catalog** with no package, so a changed `orders.lookup@1`
  registers as `orders.lookup@2` there; the walk-through's run in the development catalog says
  `@3`.
- **The short form's contracts line** said "not as `contracts.lock.json` records", which names one
  lockfile when two are read; it now says "not as recorded", and gets the test it didn't have.
- **The releases guide** says the base's lockfile among what fails the step when it can't be read,
  and a recorded hash rewritten among what is refused.
- **Each later slice's test passed at once or was written after the code it pins,** and was seen
  to bite on a deliberate break: no lockfile line for an unchanged contract, the promise read
  against the head's hash, a retired contract said gone, the base's lockfile not checked as a JSON
  object, the argument removed from the workflow.

## Promises

Checked against the tests before the pull request, both ways: every promise names a test that
exists, and every test this fix added is named. `S` is `tests/test_summary.py`, `C` is
`tests/test_catalog.py`, `P` is `tests/test_promise.py`.

| Promise | Test |
|---|---|
| A contract the base records is checked against the hash recorded there, whatever the head's lockfile says: changed in place, it fails, path by path from the base's promises | S `test_a_contract_changed_with_its_hash_rewritten_fails` |
| A recorded hash never changes: rewritten or dropped by the head's lockfile, it is said under the contract's line, or alone with what to put back, and fails | S `test_a_contract_changed_with_its_hash_rewritten_fails`, `test_a_recorded_hash_rewritten_or_dropped_alone_fails` |
| The head's lockfile records what the base doesn't: a new contract recorded passes, one not recorded fails with the line to add | S `test_the_heads_lockfile_records_what_the_base_doesnt` |
| A contract retired from the catalog is never an error, its base entry kept or dropped | S `test_a_contract_retired_from_the_catalog_is_never_an_error` |
| The base's promise is read against the base's hash | S `test_the_bases_promise_is_read_against_the_bases_hash` |
| A base lockfile that is missing, can't be read or isn't a JSON object fails the step, exit 2, said in the log and the summary | S `test_a_base_lockfile_that_cant_be_read_fails_and_says_so` |
| CI passes the base checkout's lockfile, one argument, with the same permissions | S `test_ci_passes_the_base_checkouts_lockfile`, `test_the_workflow_sends_nothing_and_reads_only` |
| The all-clear line says what was compared | S `test_contracts_that_match_are_said_to` |
| Past the limit, the contracts not as recorded are counted | S `test_past_the_limit_a_contract_not_as_recorded_is_counted` |
| The guide's example runs as written | S `test_the_guides_summary_runs_as_written` |
| `ventoux hashes` and the `check` job's test still compare with the head's lockfile, as before | C `test_every_development_contract_matches_its_recorded_hash`; P `test_hashes_passes_when_every_contract_matches`, `test_the_base_commits_promises_say_what_changed` |
