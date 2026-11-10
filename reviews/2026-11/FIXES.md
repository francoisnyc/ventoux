# A proposed order for the fixes

This page proposes an order for acting on the 76 findings of `REPORT.md`. It is a proposal: it
changes nothing, decides nothing, and holds no patch. Finding numbers are the report's.

How it is arranged:

- **Part 1** lists what needs a decision recorded in the brief before any code is written. Each
  is a question, the options the review saw, and the findings that wait on it.
- **Part 2** is the order of fix pull requests, most serious first, each small enough to be one
  pull request under the project's own rules: a design note in `docs/layers/fix-<name>.md`, the
  negative test first and shown failing for the right reason, the least code that passes it, a
  "Promises" table, and a dated amendment in the brief where a decision's text gains something.
- **Part 3** is what can be done at any time, since it changes no behaviour.

For almost every fix, the failing test already exists in another form: the finding's probe under
`reviews/2026-11/probes/` builds the case and shows the wrong outcome. The probe's scenario,
rewritten as a test, is the negative test to start from; its control (the plain step, the case
opened alone) is the test that must keep passing.

## Part 1. Decisions to record first

### A. Is a fix a new engine version? (touches most of part 2)

D51 says "a change that decides a recorded path differently is the next version: its old branch
kept behind the case's version, a fixture recorded under the old version that replays, and a line
here." D68 made one exception, for code "merged on 2026-11-02 and never released (0.0.0)", and
added: "After the first release, a change of this kind takes a new engine version." The changelog
says 0.1.0 is not yet released.

Fixes 4 to 12 below all decide recorded paths differently (a run that started now fails, a
milestone reached now isn't). The options: (i) take them as engine version 4, in one version or
several, each with its old branch and a fixture; (ii) decide, once and in writing, that nothing
before the first published release is owed an old branch, as D68 did for one shape, and say which
commit that covers. Option (ii) is far less code and is honest only if no case outside the tests
runs on today's engine 3. This is the maintainer's to say; the review can't know it.

### B. A child case's failed run when its parent closes or stops the step (1b.6)

D74 says a parent's close or a rule's stop "closes the child through D40's one place ... a close
never waits for a person (D48)". D17, D26 and D40 say a failed run is never cancelled by a
milestone or stopped by a rule. Options: (i) a child holding a failed run holds its parent's
automatic close and refuses a rule's stop, as a failed run does in one case; a person's close of
the parent still closes both; (ii) D74 says in words that a child's failed runs are let go, and
both cases are flagged so a person looks at what may have been paid. Option (i) is the reading
"nothing is skipped automatically" asks for.

### C. How far steering goes into a child case, and whether a list's items steer (1a.1, 1a.2, 1a.5)

Three questions the brief doesn't answer:

- A case step steered by untrusted data: D43's rule for a plan is that its condition's untrusted
  sources travel "beside its fields" and are checked against each input's policy. A child has
  tasks, where D43 says steering ends. Does the child's opening carry the steering, and to where?
- A step repeated over a list the customer typed runs only because the customer listed the item.
  Is each run steered by the list's sources?
- May the absence of a person's work decide? A rule reading that a task has no answer, or a step
  requiring a task repeated over an empty untrusted list, closes a case with nobody in it. D48 and
  D73 record the two halves (a step kept from starting; an empty list meeting `requires` at once)
  and neither says the absence may then reach a milestone. Options: accept it with a warning from
  `ventoux check`; or make the absence carry what steered it, as an activity's unset output
  already does.

### D. Who is excluded across a plan step, a case step and a milestone (1b.1, 1b.8, 1b.7)

- A plan's outcome carries only `system:<plan>`, so the person whose answer inside the plan chose
  it approves what it decides. D74 already answers this for a child a person closed
  (`person:<closer>, case:repair`). The same rule for a plan's outcome is the natural reading.
- D28 and D74 carry the opener and the proposer into a plan and a child. Whoever's answer the
  step's own `when` read is refused on a call step and not carried. Add them, or record why not.
- D39 records on purpose that a person whose answer only brought a moment, or whose run a step
  `requires`, is not excluded. Nothing tells an author which of two equivalent definitions they
  wrote. A warning from `ventoux check`, or leave as it is and say so in the cases guide.

### E. What crosses with a value hidden by `visible_to` (1b.5, 1c.4)

D42 already refuses, when a definition is read, a field set from a field fewer roles may see. The
same rule is missing at three joins: a parent's value given to a child's field, a child's reported
field, and a plan step's input as the audit store records it. Decide that validation refuses each
(as D74 already does for sensitive values: "a sensitive value enters a child only into a
sensitive field"), and what the runtime does when validation was skipped.

### F. Form values, and a value under a name that is no field (1c.7; D32 against D76)

D32 says "every form value in the answers people sent" goes with forgetting. D76 keeps a
non-sensitive form value in clear in the state and the audit store. Decide which is meant and
amend the other. Apart from that, an answer giving a value under a name the task doesn't set
should be refused, as an undeclared answer is.

### G. "Anything that talks to people drafts by default; it never sends on its own" (1b.9)

Nothing checks it. Options: build the check D56 waits for (for instance, a `notify` contract's
step must carry an approval with no `when`, refused at validation and at the start); or reword the
non-negotiable as a convention for contract authors that the engine doesn't check yet.

### H. Refusals that depend on what the worker's code knows (2.1, 2.2, 2.3)

A migration refused for an engine version the code didn't know is taken when newer code replays
the history. The refusal reads a list in the code on every replay. Options: record what the code
knew as data in the state when it refuses (so the replay refuses the same), or put such refusals
behind a patch marker. The same question covers the forget request's records taking their engine
version from a constant, and the class settings `events_per_run` and `audit_bound`.

### I. Messages sent with Temporal's client directly (1c.8, 1c.9, 1c.11, 1c.14)

D79 forbids them and Temporal doesn't prevent them. Decide whether the engine is hardened anyway
(a number that isn't finite refused and recorded; a signal that can't be read recorded as
refused; a start claiming to have continued as new checked against the run's own history), or
whether the deployment guide says plainly that these four are inside the trusted caller's
boundary and `ventoux doctor` lists them as unchecked.

### J. Which names are supported (5.3, 6b.1)

The guides teach `run_case`, `CATALOG`, `Catalog`, `registry_worker`, and `propose`, `retry`,
`close`, `view` and `propose_change`, none in `public.json`. Decide the list, and make the test
that guards it read calls and the quickstart, not only `from ... import` lines in the guides.

## Part 2. The fixes, in order

Each line: what the pull request does, the findings it closes, and the decision it waits on.

### First, because nothing depends on it and it protects everything after

1. **Three missing negative tests.** A case with two `closes_when` milestones that has reached
   one stays open; an approver holding a role the approval doesn't list is refused; the runtime
   alone refuses a repeated high-risk step. Tests only. Closes 4.1, 4.2, 4.4. Waits on nothing.

### Forgetting and sealing (the promises a data-protection role relies on)

2. **A sensitive option or attachment is sealed in its check's command.** Closes 1c.1, 1b.4.
   Waits on A.
3. **The forget request reads the case's answer before it destroys the key,** and refuses, saying
   why, a case whose start doesn't read as a case. Closes 1c.5, 1c.10. Waits on A.
4. **Each request to forget has its own audit stream.** Closes 1c.2. Needs a line in D76 or D77
   on the stream's name.
5. **A form value under a name that is no field is refused.** Closes 1c.7. Waits on F.
6. **Messages that carry values.** A contract validator's message is treated as an activity's own
   is; the worker's log keeps only a type when sealing fails; a failure's details are sealed. Closes
   3.3, 1c.6, 1c.12.
7. **The Vault client.** A token the header can't carry is `KeyRefused` naming the setting, never
   the value; a `404` is Vault's answer only in the shape Vault gives. Closes 3.1, 3.2, 3.8.

### Untrusted data (the trust model)

8. **A repeated step keeps what steered it.** Closes 1a.1. Waits on A, C.
9. **A case step keeps what steered it, and a child's declared mark is added at its opening;**
   `ventoux check` claims the same at a case step's `reaches`. Closes 1a.2, 1a.3. Waits on A, C.
10. **A refresh keeps what steered the run it fetches again.** Closes 1a.4. Waits on A.
11. **The absence of a person's work,** as decided. Closes 1a.5. Waits on C.

### People and child cases

12. **Exclusions across a plan step and a case step:** a change request in a child, the answerer
    of a plan's wait, the reader of the step's `when`. Closes 1b.2, 1b.1, 1b.8. Waits on A, D.
13. **A child's reported field may not be named `outcome`,** refused when the package is read, as
    a contract's output is. Closes 1b.3.
14. **`visible_to` across a child, a report and a plan step's audit record.** Closes 1b.5, 1c.4.
    Waits on E.
15. **A child's failed run and its parent's close,** as decided. Closes 1b.6. Waits on A, B.
16. **A proposal whose approval an edit withdrew** is asked again, or its line says it is over; a
    lapsed retry's message says what can be done. Closes 1b.10, 1b.11.

### The audit export

17. **A record's names can't refuse the export for good.** The sensitive check is made by where a
    value sits in the record, not by a name it shares with a field. Closes 1c.3.
18. **`read_audit` refuses a stored shape it doesn't know.** Closes 3.5.

### Replay

19. **Refusals recorded with what the code knew,** as decided. Closes 2.1, 2.2, 2.3. Waits on H.
20. **Fixtures for what has none, and tests that compare what a replay rebuilds.** A plan run, a
    timer, a child case and its doorbell, a registry that continued as new, a case migrated to
    engine 3. The probe `p2_replay_every_history.py` shows one way to compare. Closes 2.4.

### Commands and readers that don't fail closed

21. **A path that isn't there is an error** in `summary`, `conformance --since`, `check` and
    `check --unchanged`. Closes 3.4.
22. **Stricter readers:** a JSON key written twice is refused; a manifest file and a release
    record refuse unknown keys and loose conversions; a role registered twice is refused; a text
    that can't be written is refused by `ventoux check` with nothing left on disk. Closes 3.6,
    3.7, 3.9, 7b.1.
23. **Bounds:** an age has an upper bound; a result too small for decimal128 is an error, as one
    too large is. Each is a line in D20 or D44. Closes 6b.3, 3.10.
24. **The stated refusals and readers with no negative test.** Closes 4.5, 4.6, 4.7, 4.8.

### Messages sent past the client functions

25. **As decided under I.** Closes 1c.8, 1c.9, 1c.11, 1c.14. And `report` of a case refused at its
    opening says so. Closes 1c.13.

### "Drafts by default"

26. **As decided under G.** Closes 1b.9.

## Part 3. Documents, at any time

None of these changes behaviour, so none waits on part 1 or 2, and the first is the cheapest
thing on this page for what it gives a newcomer.

27. **The README and the quickstart say what exists.** Remove "There is no code yet" and "none of
    it is built yet"; replace `ventoux init`, `dev` and `start` with what a reader can run today
    (how to install, how to start a local Temporal server, the `pytest` command that works);
    correct section 7's step and the `ventoux diff` line; count the concepts again against
    principle 5. Closes 6.4.1, 6.4.2, 5.1, 5.2, and 6.1.2 with a dated line in D13.
28. **The supported names,** as decided under J, with the guard test widened. Closes 5.3, 6b.1.
29. **Guide snippets that don't run as written:** `run_case`'s `catalog=`; what `start_case`
    takes, with a refusal that says so before the ID is spent; `environment_worker`'s `audit`;
    `report` right after `start_case` in an environment; the schema's `$id` in the cases guide;
    `ventoux version`'s output in the deployment guide and D82's wording; which commands assume
    the repository's `examples/`. Closes 5.4, 5.5, 5.6, 5.7, 5.10, 6.4.3, 6.1.1, and 5.8, 5.9
    where a message can say more.
30. **The brief's housekeeping,** each a dated line and never a rewrite: the status line; the
    glossary's "Step" and "Catalog" rows and "Simplifications adopted" gaining `wait` and `case`
    by a line under D74; D60 saying D82 moved the schemas; D76's example; D45 or D38 saying when a
    rule's start is decided; the three wordings that print otherwise; "the Ventoux API" in guides
    and docstrings; the two "Promises" rows naming tests that are gone. Closes 6.2.1, 6.2.2,
    6.2.3, 6b.2, 6b.4, 7b.2, 7b.3, 6.4.4, 6.4.5.
31. **Names in the repository's history** (6.6.1 to 6.6.3). The three mentions in files are a
    rewording. The commit messages can't be changed without rewriting history, which the
    project's rules forbid: if the repository is to be shared where that matters, the choice is
    a fresh history at the first published release. The maintainer's to make.

## What this order assumes

- That the forgetting and sealing fixes come before the trust fixes because their harm can't be
  undone: a value left readable after a key is destroyed stays readable in every copy of the
  history. A milestone wrongly reached can be seen and reversed by a person.
- That decision A is taken first. If the answer is "engine version 4", fixes 2 to 15 are best
  grouped so that one version carries them, and fix 20's fixtures are recorded before it.
- That each fix lands with its probe's scenario as a test. The probes themselves stay under
  `reviews/2026-11/`, as the record of what was found at `3edb471`.
