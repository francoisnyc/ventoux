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
`test_the_registry_knows_each_releases_open_cases`), noted
for their own fix. Each race was reproduced by a probe before the fix (above).

## Promises

| Promise | Test that would fail |
|---|---|
| A reading of a request saying `closing the case` already says the case was asked | `test_a_report_closing_the_case_already_says_the_case_was_asked` (`tests/test_temporal_forget.py`), seen failing before the fix |
| The three lines of a stop keep their order once the payment is done | `test_a_stopped_cancellable_workflow_is_cancelled_on_temporal` (`tests/test_temporal_workflow_step.py`), 50 runs under load |
| The key goes only after the case ended, read at `closing the case` | `test_the_key_goes_only_after_the_case_has_ended`, `test_the_key_goes_only_after_a_child_plan_has_ended`, 50 runs under load |
