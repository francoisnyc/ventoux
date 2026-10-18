# Fix: a retry that doesn't start needs attention again

A fix, not a layer: no warm-up, and nothing new to build. Found in 11c ("From the code map", its
last bullet) and left for its own pull request. Adds to D26 (brief), as an amendment dated
2026-10-18.

## The bug

An operator's retry makes a failed run `retrying`: the same run, with the same key, waiting to
start again (D26). It may wait across decisions for two things only: its approval, asked again
when the values it reads changed since the run was approved, and a fact it needs fresh, fetched
again. Nothing ended a retry that stopped waiting for something else. Each case below stays open
for ever, with nothing in `waiting_for` or `needs_attention`, against "nothing is skipped
automatically" (D17) and "a waiting case says what it waits for" (D24):

| Path | What happened |
|---|---|
| The retry's approval is rejected | recorded on a new entry, `pay#2 won't run`; `pay#1` stays `retrying` |
| The same, while the close is held by `closes_when` | the same, and the retried run holds the close for ever |
| The retry's approval is withdrawn (a review proposed again), and the review is then rejected, so the step's `when` is false | admission drops the run with no line |
| The retry's stale fact is fetched again, and the new value makes its `when` false | the same |
| The retry waits for a review proposed again, which a rule then stops | its requirement is never met again, and nothing is open |
| (Not stuck, shown only through another entry) the retry waits for a review proposed again, still open; or for a step whose refresh failed | `pay#1` itself shows nowhere |
| (Found by the suite) an approval given while the close is held | given, never spent, and shown nowhere; the failed run holding the close is shown, so the case isn't stuck |

## Decided

1. **A rejected rescue goes back to `failed`** (choice (b)). The failure isn't resolved: the run's
   side effect may or may not have happened (D26), so the case can't close on it. `pay#1` needs
   attention again, saying its retry's approval was rejected; an operator retries it again,
   which asks again, or closes the case with a reason. The rejection is recorded on the
   approval's entry, never on a new run of the step: there is no `pay#2`.
   - history: `pay#1 won't run: sam rejected pay.approval#1, so it needs attention again`
   - needs attention: `pay#1: sam rejected pay.approval#1, the approval of its retry: retry it to
     ask again, or close the case`
2. **Widened: a retry lives only while it waits for its own approval or its own fact.** Anything
   else that keeps it from starting, as the operator's retry is checked (D26), puts it back to
   `failed`, saying why and what to do, in the same decision: its `when` is false now, or a step
   it requires hasn't completed (started again, stopped by a rule, or its refresh failed). This
   is what `retry` itself refuses, so a retry is never kept in a state a new retry couldn't make.
   It is stricter for a requirement that is still on its way (a review proposed again and
   open): the operator retries again once it is done, rather than the engine keeping the retry
   alive by itself.
   - history: `pay#1 failed again: its retry can't start: pay requires review, which hasn't
     completed`
   - needs attention: `pay#1: its retry can't start: pay requires review, which hasn't
     completed: retry it once it has, or close the case`; for the condition, `… review.outcome
     == "approve" is false now: retry it once it holds, or close the case` (the condition as the
     definition writes it, never a value from the case file).
3. **An approval answered while the close is held starts nothing, and isn't kept** (fixes K).
   Once every `closes_when` milestone is reached, nothing new starts (D34); a given approval
   that can't be spent was pending work nobody saw. The answer is recorded, then
   `goodwill not started: paid is reached, so the case closes once notify#1 is retried, or a
   person closes it: nothing new starts`. The retried run itself is the exception: it is what the
   held close waits for, so its approval is spent as before.
4. **The replay gap is a known limit.** These paths schedule nothing different on the decision
   that changes, so a history recorded before the fix replays (a fixture shows one). A history in
   which someone then sent `retry pay#1` doesn't: before the fix that retry was refused (`has not
   failed`), after it the retry is accepted and schedules `pay#1`. Temporal refuses such a history
   and the case waits until the code is fixed, as 11b's note says of paths it decides differently
   (D17). Closing it would need a patch marker passed to `decide` as event data; not built.

## The invariant

After every decision, an open case that doesn't stay open has nothing pending, or shows every
pending item: an open run or approval in `waiting_for`; a failed run or rule in `needs_attention`;
a running run as running work; a retrying run by its approval in `waiting_for` or a refresh of
its fact running; a given approval by a refresh of its fact running. Checked in the tests two
ways: after every decision of every case the in-memory suite runs, and over generated scripts on
the refund (proposals, retries, approvals and rejections, a rule's stop, time passing, closes).

## Where the code goes

- `case/runtime.py`: `answer_approval` sends a rejected retry back to `failed`, and keeps no
  approval given while the close is held; `admit` sends a retry it can't start back to `failed`.
- `docs/BRIEF.md`: D26's amendment.
- `tests/invariants.py` (new): the check, as a function of the definition and the state.
- `tests/conftest.py` (new): the check after every decision of the in-memory driver.
- `tests/test_retry_rejected.py` (new): the paths above, the generated scripts, and the replay.
- `tests/histories/before_fix_retry_rejected.json`, recorded under main.

No new dependency.

## Seams the tests use

- `run_case(...)`: `needs_attention`, `waiting_for`, `history`, `closed`; `retry`, `propose`,
  `close`, `later`, answers.
- The in-memory `Driver`, one event at a time, for the generated scripts (a refused event is
  skipped, as the API would refuse it).
- `CaseState` after each decision, for the invariant: its runs, approvals and refreshes.
- The Temporal test server: the rejected retry, retried again, paying once with the key of
  `pay#1`; `replay` of the fixture.

## Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Before anything changes:** the fixture recorded under main (a retry whose approval is
   rejected, then a close), replayed.
1. **The invariant.** Negative: the generated scripts find the stuck retry on main. The suite's
   hook finds K.
2. **A rejected rescue.** Negative: the reproduction needs attention on `pay#1`, with no
   `pay#2`. Then: retried again, it asks again and pays once with its key; the held close.
3. **Widened.** Negative: the retry whose `when` turns false. Then the requirement started again,
   stopped, and the failed refresh; the line never quotes a value.
4. **K.** Negative: the approval given while the close is held is no longer pending.
5. **On Temporal,** the brief's amendment, and the promises.

## Promises

Drafted before building, to be checked against the files once built. Every test is in
`tests/test_retry_rejected.py` unless said otherwise.

| Promise | Test that would fail |
|---|---|
| After every decision of every in-memory case, an open case that doesn't stay open shows each pending item | `tests/conftest.py`'s check, run by the whole suite |
| Generated scripts on the refund leave nothing pending unshown | `test_generated_cases_show_what_is_pending` (seen failing on main) |
| A rejected retry goes back to `failed`, needing attention, saying so; there is no new run | `test_a_rejected_retry_needs_attention_again` |
| Retried again, it asks again, and pays once with the first run's key | `test_a_rejected_retry_retried_again_asks_again` |
| A rejected retry while the close is held keeps holding it, shown, and the case closes once it is retried to completion | `test_a_rejected_retry_holds_the_close_and_says_so` |
| A retry whose `when` turns false, before or after its fact is fetched again, needs attention again, naming the condition and never a value | `test_a_retry_whose_condition_turns_false_needs_attention`, `test_a_retry_whose_refreshed_fact_turns_it_false_needs_attention` |
| A retry whose requirement started again, was stopped, or failed needs attention again, saying which | `test_a_retry_whose_requirement_isnt_met_needs_attention` |
| An approval given while the close is held starts nothing, says so, and isn't pending | `test_an_approval_answered_while_the_close_is_held_starts_nothing` (`tests/test_case.py`, extended) |
| A person may close a case whose rescue was rejected | `test_a_rejected_retry_can_be_closed` |
| On Temporal, a rejected retry needs attention, and retried again pays once with its key | `test_a_rejected_retry_on_temporal` (`tests/test_temporal_case.py`) |
| A history recorded under main with a rejected retry and a close replays | `test_a_history_with_a_rejected_retry_replays` (`tests/test_temporal_case.py`) |
