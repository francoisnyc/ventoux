# Fix: a contract is checked against the hash the base recorded

A fix, not a layer: no warm-up, and nothing new to build. Found in layer 13's walk-through,
stop 7 (learning question 41, "Found in the walk-through, not fixed"), and left for its own pull
request; confirmed in the code by the tutor review of #53.

Status: choices put, 2026-10-25, each with a recommendation. Answered "1 to 10, all as
recommended", the same day. The dated lines on D5 and D57, the activities guide's paragraph and
learning question 41's lines written before building.

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
