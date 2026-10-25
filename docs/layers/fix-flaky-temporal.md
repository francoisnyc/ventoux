# Fix: two Temporal tests that failed one full run in three

A fix, not a layer: no warm-up, and nothing new to build. Two tests on Temporal's test server
failed now and then in full `uv run pytest` runs (2026-10-25, during 14a, 14b and 14c, each time
a different one), and passed alone. Neither change touched `src/ventoux/temporal/`, `case` or the
tests: the full suite only loads the machine, and both tests had a race that load widens.

## The two races

**1. `test_a_stopped_cancellable_workflow_is_cancelled_on_temporal`** (11c) asserted the three
lines after `withdraw#1 on reached withdrawn: stopping kyc` in order: stop requested, cancelled,
flagged. Seen failing with `pay#1 done, giving refund_id from untrusted:undeclared` as the second
of the three.

The refund approved by Ana schedules `pay#1` (an activity on the case worker) and starts `kyc#1`
(a child workflow on the KYC team's worker) in the same decision. The test waited for the check
to start, then withdrew. It never waited for the payment: alone, the fake payment is done long
before Ana's two answers reach the case; under load, the activity's completion can reach the
case any time, so its line lands anywhere, including between the stop request and the child's
cancellation. Reproduced by holding the fake payment until the stop had been requested: `pay#1
done` then lands after the three lines, or between them, depending on which completion the
server records first.

**The engine's order is specified, and kept.** The case records events in the order they reach
it: its inbox keeps arrival order, which Temporal's history records, and replay reads the same
history (layer 8, "One inbox, one event at a time"; brief, D47: *decided one at a time in the
order history records*). Two completions in flight at once arrive in the order the server took
them, which is real time, not something the engine chooses or should: ordering them by anything
else would need a rule the brief doesn't have, and the three asserted lines are one chain of
consequences (a stop requested, the child ending cancelled, the flag), whose order the engine
does promise. So the test keeps asserting the order, and controls the one thing it had left
to chance: it lets the payment finish before Ana logs the withdrawal, as
`test_closing_lets_a_workflow_step_finish` already did. Asserting set membership instead would
have dropped a promise the test exists to check.

**2. `test_the_key_goes_only_after_the_case_has_ended`** (9c) waited for the request's status
to be `closing the case`, then asserted its history held `refund-1 asked to close as
forgotten`. Seen once with the status there and the line not.

`carry_out` set the status, then awaited the signal to the case, then appended the line. The
await ends the workflow task; the signal's completion starts the next. A query between the two
reads the report as it is then: status changed, line not yet written. The poll every 50 ms rarely
lands in that window, a signal's round trip; a poll as fast as the server answers lands in it
every time (the new test, seen failing before the fix with `('closing the case', False)` among
its readings). The sibling test `test_the_key_goes_only_after_a_child_plan_has_ended` read the
*case's* status right after the same wait, and would have read `open` in the same window.

**The fix is the engine's,** not the test's: the status now changes after the signal, in the
same workflow task as its line, so any reading that says `closing the case` also says the case
was asked (or was already closed). A report is read by people through the CLI as well as by
tests; its status and the line that explains it should never disagree. Nothing else changes:
the status before the signal is sent stays `waiting`, which it was, and a request recorded
before the fix replays, since no command moved.

## Not in this fix

- The 50 ms polls in the tests' `reported` helpers: bounded and fine; they read a state the
  engine now keeps consistent.
- Other tests asserting a history slice: each was read (`grep "history\[" tests/test_temporal_*`);
  the others wait for every concurrent completion first, or assert the end of a history where
  nothing else is in flight.

## Checked

Three loops of 50 runs of the four tests (the two that failed, the sibling that read the case's
status in the same window, and the new one), the fix in place, each loop with another pytest
process running beside it: the full suite twice, then the suite without its Temporal tests.
49, 46 and 48 runs green, and **no run failed on what the tests assert**, 143 of 143. The 7
other runs all read `RuntimeError: Failed starting test server: … did not start within 5s`:
Temporal's time-skipping test server didn't start within the 5 seconds the SDK's core allows,
though asked alone at the same moment it started in 0.11 s (five times, load average 4.5 on 16
cores); `start_time_skipping` takes no startup timeout. The run's tests never ran, so they
neither passed nor failed. Not this fix's, and not the machine's load alone: left for its own
investigation. The doubled full-suite load also timed out two unrelated tests once each
(`test_a_continued_run_whose_digest_changed_waits_for_its_code`, 60 s;
`test_the_registry_knows_each_releases_open_cases`), noted for their own fix. *2026-10-25: the
first is found and fixed below, "The third test".* Each race was reproduced by a probe before the
fix (above).

## Promises

| Promise | Test that would fail |
|---|---|
| A reading of a request saying `closing the case` already says the case was asked | `test_a_report_closing_the_case_already_says_the_case_was_asked` (`tests/test_temporal_forget.py`), seen failing before the fix |
| The three lines of a stop keep their order once the payment is done | `test_a_stopped_cancellable_workflow_is_cancelled_on_temporal` (`tests/test_temporal_workflow_step.py`), 50 runs under load |
| The key goes only after the case ended, read at `closing the case` | `test_the_key_goes_only_after_the_case_has_ended`, `test_the_key_goes_only_after_a_child_plan_has_ended`, 50 runs under load |

## The third test: a report asked faster than the sandbox replays

*Added 2026-10-25, from `main` at `9c692aa` (the two fixes above merged as #59).*
`test_a_continued_run_whose_digest_changed_waits_for_its_code` (12b, from the tutor review) is
the test the "Checked" section above left for its own fix: it failed once at its 60 s bound in a
full run that shared the machine with another pytest process, and passed in every other run.
Diagnosed as the two above and the ones before them were: a reproduction probe first, then the
cause, then the smallest fix in the test or the engine. No decision in the brief changes: nothing
the engine does is touched.

### The failure

`TimeoutError` from the test's own bound, `asyncio.wait_for(scenario(), timeout=60)`. The only
output kept was sdk-core's `Task not found when completing … workflow execution already
completed`, which a passing run prints too: a query completed for a run that had just continued as
new. The test takes three workers in turn on the same queue (`serving(...)`): one whose code gives
the release's digest, under which the case opens and continues as new; one whose code no longer
gives it, which fails the next workflow task; the first again, under which the case goes on.
Which phase hung, the output didn't say.

### The probe

On this machine, an Intel Mac (x86_64, 16 cores), idle, the test fails every time, in 65 s with
62 s of CPU: the first phase never sees `waiting_at == ["review#1"]`. The same workers and the
same `reported` loop, run outside pytest, get there on the second ask, in 1.8 s. Under pytest,
every ask is unanswered, each taking 2 s against the 1 s `answered_report` waits. One `report`
query, on a worker that caches no workflow, measured by the module the workflow class lives in:

| In the sandbox | under pytest | `--assert=plain` | outside pytest |
|---|---|---|---|
| `EveryEventCases`, in `tests/test_temporal_approvals.py` | 2.1 s | 0.57 s | 0.55 s |
| `DevelopmentCases`, in `ventoux.testing` | 0.08 s | 0.08 s | 0.07 s |

For comparison, `EveryEventCases` on a worker that caches workflows (`case_worker`): 0.01 s; on a
worker caching nothing but run by `UnsandboxedWorkflowRunner`: 0.01 s. Re-importing
`test_temporal_approvals` and the sixteen test modules behind it, in the main interpreter: 1.29 s
with pytest's assertion rewriting, 0.16 s without.

### The cause

Three things, each right on its own:

- **The test's workers cache no workflow** (12b's tutor review), so a stopped worker's own queue
  never holds the next worker's task. With no cache, every workflow task replays the case from
  its start, each `report` query included.
- **The sandbox re-imports the workflow's module for every run instance** (the SDK's design:
  `SandboxedWorkflowRunner`, "re-imported and instantiated for each workflow run"). The test's
  workflow classes live in test modules, and `test_temporal_approvals` imports
  `test_temporal_case`, which imports most of the suite: sixteen modules, each run again inside
  the sandbox, and under pytest each parsed and rewritten again by the assertion hook. Two
  seconds a replay here; `DevelopmentCases`, defined in `ventoux.testing`, replays in 80 ms.
- **`reported` gives each ask one second** (`answered_report`), because a query that reaches a run
  as it continues as new is never answered; then it asks again, up to 100 times.

Put together: the first ask that takes over a second is abandoned by the client, but the worker is
still replaying for it; the next ask queues behind that replay, then replays again, so it is late
too, and so is every ask after it. The stall sustains itself once it starts, and nothing ends it
but the 60 s bound. On a faster machine the replay fits under a second with room to spare and the
test passes; a second pytest process takes that room, one ask is late, and the stall begins. The
phase is whichever `reported` is asked under load: the first (seen here every time) or the third;
the second phase polls history, which needs no worker. So: not a worker switch racing a workflow
task, and not a bound too tight for two suites (60 s is twenty times the test's work), but a
report polled on a one-second bound against a replay that can take two.

### Decided

1. **The three workers run unsandboxed** (`UnsandboxedWorkflowRunner`), still caching nothing: the
   switch stays immediate, and a replay costs 10 ms, a hundredth of the bound. The sandbox isn't
   what the test proves: it proves the engine's `StartUnread` on a continued run, and the case
   going on under code that gives the digest again. Every other Temporal test still runs its
   workflow under `SANDBOX`, through `case_worker`. Set aside:
   - keeping the sandbox and caching workflows again, with `sticky_queue_schedule_to_start_timeout`
     cut from 10 s to 1 s: each switch then waits a timer out, as the tutor review found, and a
     timed wait is what this fix removes;
   - a longer bound in `answered_report`: it is shared by every Temporal test, its second is there
     for continue-as-new, and a longer wait moves the race, it doesn't end it;
   - moving the test's workflow classes to a light module the sandbox re-imports cheaply:
     `EveryEventCases` is imported by three test files, and the sandbox's re-import is the SDK's
     to make cheaper, not this test's to work around.
2. **The test still takes 13 s, and 10 s of it is the SDK's own backoff.** When a workflow task
   that failed is retried and fails again, sdk-core doesn't report the second failure: it lets
   the attempt time out (the default workflow task timeout, 10 s), seen in the history as
   `WORKFLOW_TASK_TIMED_OUT` then attempt 3, which the third worker takes at once. A probe kept
   the second worker up for 4 s after the failure: attempt 2 sat started, never failed. The
   time-skipping server doesn't skip it: `environment.sleep(10 s)` took 10 s real while the task
   was in flight. Left as it is: a fixed server timer, never a race, and well inside the bound.
   Shortening it needs `task_timeout` on the start, which `start_case` doesn't take, and wouldn't
   for a test.
3. **A carried note:** every Temporal test file defines workflow subclasses in its own module, and
   a cached worker still pays the sandbox's re-import once per run instance: with
   `events_per_run = 1`, once per event, 2 s each under pytest here. It costs time, never
   correctness; its own pull request, if the suite's time matters.

### Checked

- The fixed test, alone: 10 runs, 10 pass, 12.8 to 13.6 s each.
- The fixed test while the full suite ran beside it, the failure's conditions: 5 runs, 5 pass,
  12.9 to 13.3 s each.
- Before the fix, alone on this machine: 3 runs, 3 fail at the 60 s bound.
- The full suite, run as the load beside those 5 runs: 3633 pass, 3 fail, none of them this
  test and none of them its cause: `test_a_rejected_retry_on_temporal`,
  `test_refused_changes_are_recorded_and_the_case_waits_on` and
  `test_a_case_with_a_refresh_replays` each failed in `start_time_skipping`, the Java test server
  saying `Failed to bind to address 0.0.0.0:<port>`: the two pytest processes were given the same
  free port at the same moment. A second way two suites on one machine fail each other, in the
  SDK's choice of port; a carried note, its own fix if it recurs (choice 86 of the cold-start fix
  already names the time-skipping server's start as the risk).
- The full suite alone, on `main` merged, ruff and mypy: FULL_SUITE_ALONE

### Promises

Each claim this note makes about behaviour, and the test that would fail if it weren't true. `C`
is `tests/test_temporal_case_release.py`. The costs above are measurements of one machine, not
promises: a test that asserted them would be the flaky test again.

| Promise | Test |
|---|---|
| A continued run whose digest changed fails its workflow task and waits, running, never failed for good; code that gives the digest again lets it go on, and the case reports open on refund 1 | C `test_a_continued_run_whose_digest_changed_waits_for_its_code` |
| After a switch, the next worker takes the case's task as soon as the server offers it: the workers cache nothing, so no task waits on a stopped worker's own queue | C `test_a_continued_run_whose_digest_changed_waits_for_its_code` (its third phase, bounded by `reported`) |
