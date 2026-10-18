# Fix: a retry that doesn't start needs attention again

A fix, not a layer: no warm-up, and nothing new to build. Found in 11c ("From the code map", its
last bullet) and left for its own pull request. Adds to D26 (brief), as an amendment dated
2026-10-18.

## The bug

An operator's retry makes a failed run `retrying`: the same run, with the same key, waiting to
start again (D26). It may wait across decisions for two things only: its approval, asked when
no approval was spent on its run (one that was spent still holds only while the inputs it saw
are unchanged; otherwise the retry fails again, saying a new approval is needed, D23), and a fact
it needs fresh, fetched again. Nothing ended a retry that stopped waiting for something else.
Each case below is open, with nothing in `waiting_for` or `needs_attention`, against "nothing is
skipped automatically" (D17) and "a waiting case says what it waits for" (D24). Some never close;
the others go on only if a person happens to act (proposes the review again) without being told:

| | Path | What happened |
|---|---|---|
| A | The retry's approval is rejected | recorded on a new entry, `pay#2 won't run`; `pay#1` stays `retrying`; and a repeatable step can then run again under a new key, since the rejection is now its latest run, while nobody knows what `pay#1` did |
| D | The same, while the close is held by `closes_when` | the same, and the retried run holds the close for ever |
| C | The retry's approval is withdrawn (a review proposed again), and the review is then rejected, so the step's `when` is false | admission drops the run with no line |
| F | The retry's stale fact is fetched again, and the new value makes its `when` false | the same |
| E′ | The retry waits for a review proposed again, which a rule then stops | its requirement isn't met again unless someone proposes the review, and nothing is open |
| C′, I | (Not stuck: shown through another entry, which waits for a person) the retry waits for a review proposed again, still open (C′); or for a step whose refresh failed, which needs attention (I) | `pay#1` runs once the review is answered, or the refresh is retried; left as it is (decision 2) |
| K | (Found by the suite) an approval given while the close is held | given, never spent, and shown nowhere; the failed run holding the close is shown, so the case isn't stuck |
| L | (Found in the review of slice 1) an approval given while its fact is fetched again, whose requirement (a review proposed again) a rule then stops | the approval is never spent unless someone proposes the review, and nothing is open. On a retry, once slice 3 failed the retry again, the approval stayed, and a review answered again would have spent it on a new run, `pay#2`, under a new key: fixed by decision 5, slice 5 |
| M | (Found in the review of slice 1) a person's proposal waiting for its fact when the close becomes held | it never starts and shows nowhere, and a later close drops it with no line, against "starts the step or says why not" (D39) |

## Decided

1. **A rejected rescue goes back to `failed`** (choice (b)). The failure isn't resolved: the run's
   side effect may or may not have happened (D26), so the case can't close on it. `pay#1` needs
   attention again, saying its retry's approval was rejected; an operator retries it again,
   which asks again, or closes the case with a reason. The rejection is recorded on the
   approval's entry, never on a new run of the step: there is no `pay#2`. It is the same run, so
   whoever may not approve it still may not (D25, D39), and nothing starts beside it (D39).
   - history: `pay#1 won't run: sam rejected pay.approval#1, so it needs attention again`
   - needs attention: `pay#1: sam rejected pay.approval#1, the approval of its retry: retry it to
     ask again, or close the case`
2. **Widened: a retry waits only for what can still let it start.** That is its own approval,
   asked and listed; its own fact, fetched again; or a step it requires that is still on its way
   and itself shown (open, running, failed or retried), as a given approval does (decision 5).
   Anything else that keeps it from starting puts it back to `failed`, saying why and what to do,
   in the same decision: its `when` is false now (C, F), or a step it requires ended without
   completing, its latest run cancelled or rejected (E′).
   - history: `pay#1 failed again: its retry can't start: pay requires review, which hasn't
     completed`
   - needs attention: `pay#1: its retry can't start: pay requires review, which hasn't
     completed: retry it once it has, or close the case`; for the condition, `… review.outcome
     = "approve" is false now: retry it once it holds, or close the case` (the condition as the
     engine writes it from the definition, never a value from the case file).

   *Changed 2026-10-18, after the review of slice 1:* first agreed as "a retry lives only while
   it waits for its own approval or its own fact", which failed C′ and I at once. Both go on by
   themselves on main, through an entry that waits for a person, so a recorded case that went on
   that way would no longer replay; and they are the likeliest of these paths to be recorded.

   *Added 2026-10-18, after the review of slice 3:* an operator's retry is not refused on a
   condition that is false and reads a fact the step needs fresh that is now too old, whatever
   part of it is false (the engine doesn't tell which): the retry is taken, and admission fetches the fact again before it reads the condition, then
   starts the run or fails it again, saying so. A stale fact is fetched again, never trusted to
   refuse (D18, D33). Without it, F's "retry it once it holds" could never be followed once the
   status had aged: `retry` read the condition on the stale value, and only a close was left.
3. **While the close is held, nothing waits to start** (fixes K and M). Once every
   `closes_when` milestone is reached, nothing new starts (D34); an approval given that can't be
   spent, or a proposal waiting for a fact it can't use, was pending work nobody saw. Each is let
   go, saying so, in the decision that finds the close held:
   - an approval given (answered while the close is held, or given before and waiting for its
     fact): `goodwill not started: paid is reached, so the case closes once notify#1 is retried,
     or a person closes it: nothing new starts`;
   - a person's proposal waiting for its fact: `dropped ana's proposal of pay: paid is reached,
     so …: nothing new starts`, the line a proposal dropped for any other reason gets (D39).

   The retried run itself is the exception: it is what the held close waits for, so its approval
   is spent as before.
4. **What no longer replays is a known limit.** The decision that changes schedules nothing
   different on each path, so a history recorded before the fix up to it, or closed after it,
   replays (a fixture shows one). A history in which the case was later brought back does not:
   - A, D: someone sent `retry pay#1` again: it was refused before the fix (`has not failed`),
     and is now accepted and schedules `pay#1`;
   - A: a repeatable step was proposed again, or started by a rule, after the rejection: before
     the fix it ran as a new run (`pay#3`, with a new key); now the proposal is refused, and the
     rule's start says `… pay not started: pay#1 needs attention: retry it, or close the case`;
   - C, E′, and L on a retry or in a case something keeps open: someone proposed the review
     again, and pay then ran on the run or approval that was kept: the fix asks a person first
     (an operator's retry, or a new approval);
   - L with nothing else open: the fix closes the case at the stop (decision 5), so the review
     proposed again is refused (`the case is closed: nothing starts`);
   - F: an event came once the status was stale again, and it was fetched again: the fix leaves
     the retry failed instead;
   - any step: a retry refused because its condition was false on a fact it needs fresh that was
     stale: it is now taken, and the fact is fetched again.

   Temporal refuses such a history, and the case waits until the code is fixed, as 11b's note
   says of the paths it decided differently (D17). C′, I, K and M decide as before. Closing the
   gap would need a patch marker passed to `decide` as event data; not built.
5. **A given approval lapses with its requirement** (fixes L). An approval given, and not yet
   spent because its step waits for a fact, lapses when a step its step requires has ended
   without completing (its latest run cancelled or rejected): nothing is on its way that could
   let it be spent. `lapsed pay.approval#1: pay requires review, which hasn't completed`. With
   nothing else to do, the case then closes, as it does when an open approval is withdrawn on the
   same path (D10); if something keeps it open, the step asks a new approval once it is admitted
   again, as after a withdrawn approval (D25): by itself once the requirement completes again, if
   it starts by itself; otherwise once a person proposes it again, or its rule fires again. On a
   retry, the approval lapses first, then the retry fails again (decision 2), and the operator's
   next retry asks a new one. While the requirement is still on its way (open, running, failed or
   retried), the approval stays, shown through it: it is tied to the values it saw (D11), and a
   review answered again with the same values changes none. Both this lapse and decision 2's
   failure of a retry on a requirement that ended are read once admission has settled, at the end
   of the decision: a requirement a rule stopped and another rule started again in the same
   decision is on its way, never read as ended. Not "whenever its step stops being admitted", as an open approval is
   withdrawn (D25): that would lapse an approval no value had changed, and decide differently a
   recorded case that went on through a review answered again.

## The invariant

After every decision, an open case has nothing pending, or shows every pending item, whether or
not it stays open:

- an open run or approval: in `waiting_for`;
- a failed run or rule: in `needs_attention`;
- a running run: as running work;
- a retrying run: by its approval in `waiting_for`; or, its requirements met, by a refresh of its
  fact running (admission reads `requires` before freshness, so a refresh helps nothing else);
  or by the steps it requires that haven't completed, each on its way (open, running, failed or
  retried) and itself shown;
- a given approval: by a refresh of its fact running, or by the steps it requires that haven't
  completed, each on its way;
- a person's proposal waiting to start: by a refresh of its fact running.

A run status the check doesn't know fails it (fail closed). Checked in the tests three ways:
after every decision the in-memory driver makes, and every decision a test asks of `decide`
itself, in every test; over generated cases on the refund (proposals, retries, approvals and
rejections, a rule's stop, a lookup that fails, time passing, closes, some cases that stay open);
and by a scripted case for each path the generated cases can't reach (L and M need a refresh
held across a person's act).

## From the review of slice 1

Four readers read slice 1, each with one lens (false negatives, false positives and the hook's
reach, the generated cases' coverage, the conventions), and a skeptic reran each finding. All 20
findings held. What changed because of them:

- **Two paths the table lacked, L and M,** each decided above (decisions 3 and 5), with a
  scripted test seen failing on main.
- **The invariant skipped cases that stay open,** where a stuck retry is just as silent. It now
  checks every open case.
- **A retry with a requirement unmet counted as shown by a refresh running,** which it can't use.
- **The hook reached only the in-memory driver;** it now also wraps `decide` where a test calls
  it directly.
- **The expected failures accepted any error,** so a crash in the fix would have read as expected.
  The hook raises `Silent`, and every mark expects only that.
- **K's mark turned off its test's own assertions** while slices 2 and 3 change the code they
  guard. The test runs on the plain `decide` until slice 4, and a separate marked test shows the
  hook finding K.
- **The generated cases reached neither I nor K:** the lookup never failed, and pay was the only
  step with an approval. The lookup now fails one time in five, cases that close on `audited`
  have a goodwill refund with its own approval, and some cases stay open; the seeds that fail on
  main were found again.
- **The sentence on a retry's approval** said what the runtime doesn't do (corrected above).

## From the review of slice 2

Two readers (the runtime; the tests against the note, by mutating the runtime in a copy), and a
skeptic per finding; all eight held, each fixed in slice 2:

- **Nothing tested the guard that tells a rescue from an ordinary rejection,** nor that a rescue
  keeps who may not approve its run when it failed before it started (only its proposal records
  them): each now has a test, seen failing with the guard dropped or the proposal spent.
- **On main, a rejected rescue let a repeatable step run again under a new key:** row A and
  decision 4 say so, and a test refuses the proposal now.
- **The reach test could pass checking no seed, and couldn't tell A from D;** the marks' reason
  said "seen silent on main" for a seed that moved path; two helpers returned `Any`; a loop
  variable shadowed `seeds`; `pytest.raises` had no comment.

## From the review of slice 3

Two readers (the runtime; the tests, by mutating the runtime in a copy) and a skeptic per
finding; seven held, two were refuted:

- **Three branches of `ended_requirement` had no test:** a requirement rejected, one running,
  and two not met at once. Each mutation of it passed the suite; a test now plays each, and the
  E′ test lists pay's requirements both ways round, so its line names the one that ended.
- **The reach test couldn't tell C, F and E′ apart:** each now has a line only it writes, and F
  is told from C by the refresh that lands just before.
- **A retry's given approval stayed behind when its requirement was stopped**, and a review
  answered again then spent it on a new run, `pay#2`, under a new key. Refuted as a slice 3
  defect: it is L's state, and decision 5's lapse in `follow` runs first and removes it, so it is
  fixed in slice 5, with a marked test of the retried case now.
- **On F, `retry` read the condition on the stale status,** before anything fetches it again, so
  "retry it once it holds" couldn't be followed once the status was a day old. Decided with the
  user: the retry fetches it again (decision 2, added).

## From the review of slice 4

Two readers (the runtime; the tests, by mutating the runtime in a copy) and a skeptic per
finding; nine held, one was refuted (a retry taken when its condition is false for another reason
too: admission's own rule, freshness before the condition, which the addition hands it to):

- **An approval given for a step whose requirement was on its way wasn't let go:** `admit` read
  the requirements before the held close, so a review proposed again kept the approval, and a
  person's close later cleared it with no line. The held close is now read first: nothing starts
  while it holds, whatever the requirements. Seen failing first.
- **Promises with no test:** an approval given before the close is held and waiting for its fact;
  a stale fact the condition doesn't read; only what is let go writing a line; M's drop before the
  fact lands; the retry's own refresh. Each now tested, and each mutation fails a test.
- **Decision 2's addition said "false only by reading a stale fact";** the code takes any false
  condition that reads one, as admission does. The wording now says so.

## From the review of slice 5

Two readers (the runtime; the tests, by mutating the runtime in a copy) and a skeptic per
finding; all seven held, each fixed in slice 5:

- **The lapse was read in the middle of a decision,** after the rules' stops and before their
  starts, so a review one rule stopped and another started again lapsed the approval though it
  was on its way, and a retry failed the same way when the restart came on a later moment. Both
  are now read once admission has settled (decisions 2 and 5), so such a case pays on the first
  approval and key, as main did. Seen failing first.
- **Promises with no test:** a requirement rejected; a requirement running, or failed and
  retried, keeping the approval; a step a person proposed asking again only once proposed again.
  Each tested now, and each mutation fails a test.
- **Decision 4 said L "asks a person first"**: with nothing else open, the case now closes at the
  stop instead. Decision 5's "asks a new approval once the requirement completes" holds only for a
  step that starts by itself: both now say what happens.
- **`follow`'s docstring** said only a refresh's change lapses an approval; any change does.

## Where the code goes

- `case/runtime.py`: `answer_approval` sends a rejected retry back to `failed`; `admit` sends a
  retry it can't start back to `failed`, and lets go of an approval given or a proposal waiting
  while the close is held; `retry` takes a retry whose condition reads a stale fact.
- `case/admission.py`: `ended_requirement`, a requirement with nothing on its way, read for a
  retry (decision 2) and for an approval given (decision 5).
- `case/runtime.py`, once admission has settled: `nothing_on_its_way` lapses an approval given
  and fails a retry whose requirement ended.
- `docs/BRIEF.md`: D26's amendment.
- `tests/invariants.py` (new): the check, as a function of the definition and the state, and
  `Silent`, the one error it raises.
- `tests/conftest.py` (new): the check after every decision, in every test.
- `tests/test_retry_rejected.py` (new): the paths above, the generated cases, the scripted L and M.
- `tests/test_case.py`: K's test, run on the plain `decide` until slice 4, and K's own test,
  marked until then.
- `tests/test_temporal_case.py`: the replay of the fixture, and the rejected retry on Temporal.
- `tests/histories/before_fix_retry_rejected.json`, recorded under main.

No new dependency.

## Seams the tests use

- `run_case(...)`: `needs_attention`, `waiting_for`, `history`, `closed`; `retry`, `propose`,
  `close`, `later`, answers.
- The in-memory `Driver`, one event at a time, for the generated scripts (a refused event is
  skipped, as the API would refuse it).
- `CaseState` after each decision, for the invariant: its runs, approvals open and given,
  refreshes, proposals waiting to start, and `waiting_for`.
- The Temporal test server: the rejected retry, retried again, paying once with the key of
  `pay#1`; `replay` of the fixture.

## Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Before anything changes:** the fixture recorded under main (a retry whose approval is
   rejected, then a close), replayed.
1. **The invariant.** Negative: the generated cases find the stuck retry on main; the suite's
   hook finds K; the scripted L and M are found. Each is marked as a strict expected failure,
   expecting the invariant's own error only, until its slice.
2. **A rejected rescue.** Negative: the reproduction needs attention on `pay#1`, with no
   `pay#2`. Then: retried again, it asks again and pays once with its key; the held close.
3. **Widened.** Negative: the retry whose `when` turns false (C). Then its refreshed fact (F),
   its requirement stopped (E′); a requirement on its way keeps it waiting (C′, I); the line never
   quotes a value.
4. **Nothing waits on a held close.** Negative: the approval given while the close is held is no
   longer pending (K). Then the proposal waiting for its fact (M).
5. **A given approval lapses with its requirement.** Negative: L, and L on a retry.
6. **On Temporal,** the brief's amendment, and the promises.

## Promises

Drafted before building, to be checked against the files once built. Every test is in
`tests/test_retry_rejected.py` unless said otherwise.

| Promise | Test that would fail |
|---|---|
| After every decision the in-memory driver makes, and every one a test asks of `decide`, an open case shows each pending item, whether or not it stays open; a run status the check doesn't know fails it | `every_decision_shows_what_is_pending` (`tests/conftest.py`), run by every test |
| Generated cases on the refund leave nothing pending unshown, and still reach the paths they were seen failing on | `test_generated_cases_show_what_is_pending` (seen failing on main), `test_the_generated_cases_reach_the_paths` |
| A rejected retry goes back to `failed`, needing attention, saying so; there is no new run | `test_a_rejected_retry_needs_attention_again` |
| Retried again, it asks again, and pays once with the first run's key | `test_a_rejected_retry_retried_again_asks_again` |
| It is the same run: whoever may not approve it still may not, though it failed before it started; and nothing starts beside it | `test_a_rejected_retry_keeps_who_may_not_approve_it` (seen failing with the proposal spent), `test_nothing_new_starts_beside_a_rejected_rescue` |
| A rejection of a step that isn't being retried is an outcome, as before: a new run recorded rejected | `test_an_ordinary_rejection_is_not_a_rescue` (seen failing with the guard dropped) |
| A rejected retry while the close is held keeps holding it, shown, and the case closes once it is retried to completion | `test_a_rejected_retry_holds_the_close_and_says_so` |
| A retry whose `when` turns false, before or after its fact is fetched again, needs attention again, naming the condition and never a value | `test_a_retry_whose_condition_turns_false_needs_attention`, `test_a_retry_whose_refreshed_fact_turns_it_false_needs_attention` |
| A retry whose condition is false and reads a fact it needs fresh that is stale is taken, and the fact fetched again: then it runs with its key, or fails again; on a fresh fact, or a stale one its condition doesn't read, it is refused | `test_a_retry_whose_condition_reads_a_stale_fact_fetches_it_again` (seen failing first), `test_a_retry_isnt_taken_for_a_stale_fact_its_condition_doesnt_read` |
| A retry whose requirement a rule stopped, or whose approval was rejected, needs attention again, naming that one, wherever it is listed and beside one still on its way; one whose requirements are on their way (proposed again and open or running, or a failed refresh) waits, and runs once they complete, with its key | `test_a_retry_whose_requirement_was_stopped_needs_attention`, `test_a_retry_reads_each_requirement_it_waits_for`, `test_a_retry_waits_for_a_requirement_on_its_way` (each seen failing on a mutation of `ended_requirement`) |
| An approval given while the close is held, or given before and waiting for its fact, starts nothing, says so in the decision that finds the close held, whatever its step's requirements, and isn't pending; only what is let go says so | `test_an_approval_answered_while_the_close_is_held_starts_nothing` (`tests/test_case.py`, as before, under the hook again), `test_an_approval_given_while_the_close_is_held_is_let_go` (`tests/test_case.py`, seen failing on main), `test_an_approval_waiting_for_its_fact_when_the_close_is_held_is_let_go`, `test_an_approval_whose_requirement_is_on_its_way_when_the_close_is_held_is_let_go` (seen failing first) |
| A person's proposal waiting for its fact when the close becomes held is dropped then, before the fact lands, saying so | `test_a_proposal_waiting_when_the_close_is_held_is_dropped` (seen failing on main) |
| A given approval whose requirement a rule stopped, or was rejected, lapses, saying so, and the case closes if nothing else is left, or the step asks again once admitted again (by itself once the requirement completes, if it starts by itself; once proposed again, if a person proposed it); on a retry, it lapses before the retry fails again, nothing runs under a new key, and the next retry asks again | `test_a_given_approval_lapses_with_its_requirement` (seen failing on main), `test_a_retry_s_given_approval_lapses_with_its_requirement` (seen failing on main), `test_a_given_approval_lapses_with_a_rejected_requirement`, `test_a_proposed_step_whose_approval_lapsed_asks_again_once_proposed_again` |
| A given approval whose requirement is on its way stays, and is spent on the first run's key, asking nothing again: the review answered again with the same values, a refresh that failed and is retried, a requirement running | `test_a_given_approval_survives_a_review_answered_the_same`, `test_a_given_approval_waits_for_a_requirement_on_its_way` (each seen failing on a mutation that lapses it) |
| A requirement one rule stopped and another started again in the same decision, on the same moment or a later one, is on its way: a given approval stays and is spent with the first key; a retry keeps waiting, and runs with its key | `test_a_requirement_a_rule_starts_again_keeps_what_waits_for_it` (seen failing first) |
| A person may close a case whose rescue was rejected | `test_a_rejected_retry_can_be_closed` |
| On Temporal, a rejected retry needs attention, and retried again pays once with its key | `test_a_rejected_retry_on_temporal` (`tests/test_temporal_case.py`) |
| A history recorded under main with a rejected retry and a close replays | `test_a_history_with_a_rejected_retry_replays` (`tests/test_temporal_case.py`) |
