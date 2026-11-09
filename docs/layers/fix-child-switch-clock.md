# Fix: a child-case test whose clock stopped after its parent switched runs

A fix, not a layer: no warm-up, and nothing new to build. Status 2026-11-09: **diagnosed in part,
not yet fixed.** This pull request makes the next failure say what held the clock, and records
what the investigation found; the cause's last step and the fix are still open (below).

Also here, asked by the tutor before 20b: the audit guide's table of what Vault unavailable says
now gives the reason a connection failed, and a timeout apart.

## The failure

`tests/test_temporal_children.py::test_after_a_switch_a_child_terminated_unheard_is_noticed_within_a_day`
failed three times on CI, never locally (37 runs alone or four at a time, here and in the tutor's
review): runs 968 and 980 (`layer-19c-vault-keys`) and 1005 (`layer-20a-conformance`, a push run;
the pull-request run on the same commit passed). Each time the same way:

- it hung in `await environment.sleep(timedelta(hours=25))`, the first step that needs the
  time-skipping test server to move its clock, until the scenario's 20-second bound;
- every step before it passed, the switch waits #91 widened among them;
- the only warning comes about 2.8 s into the test: `Task not found when completing … message:
  "workflow execution already completed" run_id=…`.

## What this pull request changes

- **A scenario past its bound says what held the clock.** `skipping()` in
  `tests/test_temporal_case.py` takes `described`, the workflows to describe if the bound runs out;
  the failure then says each one's status, its pending activities (type, state, attempt, last
  failure) and any workflow task in flight (`what_held_the_clock`), never only `TimeoutError`.
  The time-skipping server can't list workflows (`ListWorkflowExecutions` is unimplemented), so
  the test names them. A test runs a scenario that waits forever under a 1-second bound and reads
  the report.
- **The failing test names its two:** `claim-14` and `claim-14/repair#1`. The 20-second bound
  stays.
- **The audit guide** (`docs/guides/audit.md`, "A key the service can't give"): the unreachable
  row says `can't be reached (ConnectionRefusedError): …`, the timeout has its own row (`didn't
  answer within 10 seconds: …`), and the export's example names the reason too. A test makes each
  message with `VaultKeys` and a transport that fails, and finds it in the guide word for word.

## What was found

**The clock is held from the parent's switch, not from the terminate.** In every CI failure and
every reproduction, the warning's `run_id` is the parent's **first** run: the one that continues
as new. Matched by printing the first run's ID beside the warning.

**The hung run's history.** Reproduced the CI way once (below), the first run's history, read from
the server inside the timeout report, ends:

```
14 ACTIVITY_TASK_COMPLETED          the export came back
15 WORKFLOW_TASK_SCHEDULED
16 CHILD_WORKFLOW_EXECUTION_STARTED  the child's start, after the task was scheduled
17 WORKFLOW_TASK_STARTED             taken by the worker; never completed
```

No `WORKFLOW_TASK_COMPLETED`, no `WORKFLOW_EXECUTION_CONTINUED_AS_NEW`, yet the parent has a new
run, and the worker's completion of task 17 is refused as "already completed". (This server shows
a continue-as-new normally: a plain workflow's first run ends `…TASK_COMPLETED,
WORKFLOW_EXECUTION_CONTINUED_AS_NEW`.) The case switched where it should: task 17 carries both the
export's end and the child's start, so `running` reaches 0 there, and the switch waits for both
(`time_to_switch`, `open_child` in `src/ventoux/temporal/cases.py`).

**Why the clock stays held.** The time-skipping server holds its clock while anything is
outstanding: a workflow task, an activity, a child's start, a query task. Each hold is released
when that thing completes (Temporal's Java SDK, `temporal-test-server`,
`TestWorkflowMutableStateImpl.java`: `lockTimeSkipping` in `update`, `ctx.unlockTimer(...)` in
`completeWorkflowTask`, `childWorkflowStarted`, `completeQuery`; `SelfAdvancingTimerImpl.java`).
A completion that is refused leaves its hold in place, and nothing else releases it: the steps
after the switch run in real time, and the first that needs skipped time waits for ever.

**The server's version.** The tests run the server bundled with `temporalio` 1.34.0
(`/tmp/temporal-test-server-sdk-python-1.34.0`; it holds both messages, "workflow execution already
completed" and "Completed workflow"). Temporal's `master` has since changed
`completeWorkflowTask`: a task that would complete the workflow while new events or messages
arrived is failed as `UnhandledCommand`, "matching real server behavior". Our failure looks like
the older behaviour around a continue-as-new; not proven.

## Reproductions

**In Ventoux, on demand in part.** The failing scenario run with a payload codec (a subclass of
`SensitiveCodec`, so Ventoux accepts it) that sleeps 1 s on every encode and decode of the
parent's own payloads (`workflow_id == "claim-14"`), only during the scenario's first 7 seconds:
CI's exact signature, every step passing and the 25-hour sleep hanging, with the same warning on
the first run, about one run in five. Slowed for the whole scenario, the warning comes every time,
but the scenario fails earlier, on slowness alone (its queries time out).

**In plain Temporal, deterministic** (no Ventoux; the tests' `time_skipping`, one worker,
`UnsandboxedWorkflowRunner`), each then asking `environment.sleep(timedelta(hours=1))` under an
8-second bound:

| What the workflow does | Result |
|---|---|
| terminated while one of its workflow tasks is in flight (a codec holding the task 1.5 s) | clock held, 3 of 3; control (terminated idle): an hour skipped at once |
| continues as new with a child's start still pending (`start_child_workflow` not awaited) | clock held, 2 of 2; awaiting the start first: an hour skipped |

Neither is the case's own: a terminate isn't involved in the hold, and the case never switches
with a child's start pending. These didn't hold the clock: a signal arriving while the
continue-as-new task is in flight; queries asked every 50 ms through the switch; a started child
watched, with or without a pending timer, then continue-as-new; one task taking an activity's
completion and a child's start together, then continue-as-new. Delaying the worker's only task
slot to append an event to a scheduled task tangled with the SDK's deadlock detector and never
took the parent's first task: not usable as written.

## Still open

- **The exact trigger** in plain Temporal: what lets the server create the parent's new run
  without recording task 17's completion. The next CI failure now says each workflow's state at
  the bound.
- **The fix.** Options, none chosen: (a) a later `temporalio`, whose bundled test server may
  behave as `master` does: a dependency change, asked first; (b) a test-side change that doesn't
  need skipped time after a switch with a child: weakens what the test proves; (c) the case
  waiting one more task after a child's start before it switches: an engine change behind a patch
  marker, to suit a test server, not recommended. Reporting the plain reproductions to Temporal
  is the maintainer's call.
- The 20-second bound stays; the test is neither skipped nor retried.
