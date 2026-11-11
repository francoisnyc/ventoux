# Fix: a request to forget decides on the case's own word

A fix, not a layer: no warm-up, and nothing new to build. Found by the whole-project review of
November 2026 (its findings 1c.5 and 1c.10, kept on the branch `review-2026-11`). Both are in
the request to forget (`temporal/forget.py`), in what it believes of the case before it acts.

## 1. A case that keeps closed cases was forgotten once closed

**The bug.** Before anyone answers, the request asked Temporal whether the case's workflow runs,
and read "runs" as "open". But a closed case runs on until its audit records are written (D77):
with the store down, or the export under way, it is closed and running. So for a definition
that says `"forgetting": "while_open"`:

```
the case: closed | its workflow: RUNNING | unwritten: 2
the request, after its look-up: waiting ['pat proposed forgetting claim-1, as privacy']
     refused forgetting the case, approved by noor: the case is closed      (the case's line)
     the key of claim-1 was destroyed                                        (the request's)
```

The case refused, rightly, and its answer went nowhere: the request waited for the workflow to
end and destroyed the key. D32: "`while_open` (refused once the case is closed, for books and
records)".

**Decided.** Closed is the case's own word, and so is what it keeps.
- The report a case returns gains two fields: `forgetting`, what its family's definitions say as
  it is now (its own and its pinned children's, the strictest, D75), and `forget_taken`, whether
  it took an approved request. The second is one flag in the case's state, set where the case
  accepts the request, so it crosses continue-as-new; a state carried from before reads false.
- Once the case has ended, and before the key is destroyed, the request reads both
  (`ending_refusal`):

  | The case, as it ended | The key |
  |---|---|
  | took the request | destroyed, as before |
  | didn't, and says `never` | kept: `… keeps its records (forgetting: never): it can't be forgotten` |
  | didn't, and says `while_open` | kept: `… closed before forgetting was approved, and its definition keeps closed cases (forgetting: while_open)` |
  | didn't, and says `allowed` | destroyed: it was closed already, and a closed case can be forgotten (D32) |
  | returned no report (terminated, failed), or its worker predates the fix | destroyed, as before |

- The request then ends `refused`, with one more record in its own stream, of a new kind,
  `key kept`, saying why.
- **A migration between the proposal and the approval is honoured:** the definition read is the
  one the case ended on, never the one its start held when the proposal was checked.

**Why "didn't take it, and allowed" still destroys.** The case refuses any request once it is
closed ("the case is closed: nothing records it any more"), and D32 lets a closed case be
forgotten. For a case already closed, the request's own checks (the roles, the proposer, the
opener) are what stand, as they are for a case whose workflow has ended.

## 2. A start that doesn't read as a case's: waited on in silence

**The bug.** The look-up reads the start of the case's latest run for its definition. If the
definition didn't parse, or the workflow wasn't a case at all, the look-up raised, and Temporal
retried it for ever: the request showed `waiting`, no line, refusing nothing.

**Decided** (the maintainer's choice of the two options put to them, 2026-11-11):
- **A case refused as it opened, for a definition that doesn't read, can be forgotten.** Its
  workflow failed: it never opened, decided nothing and keeps no records, and its start holds
  sealed values under its key. The look-up tells it by the definition not reading and
  Temporal's status being failed.
- **A case that opened, whose definition the worker's code can no longer read, is refused**
  before anyone answers, saying what to do: `… holds a definition this worker can't read, so
  whether it keeps its records is unknown: deploy code that reads it, then propose again`.
- **A plan's run on its own is refused:** `… is not a case: it is a plan's run, and a request
  forgets a case`. D31 gives it a key and seals what is sent to it; D15 and D32 speak of cases.
  Forgetting one is left as a decision of its own, recorded under D32.

## No new engine version, and no patch marker

- The case decides nothing differently: it sets one flag where it already accepted the request,
  and reports two more fields. No command changes.
- The request's two new branches read only what an activity recorded: the look-up's result
  (`unreadable`) and the look at the case's end (`forgetting`, `took`). A result recorded before
  the fix holds neither, so a request recorded before decides as it did; the fixture
  `at_19b_forget_request` replays (`test_histories_recorded_at_19b_replay`). A marker would add
  a command to every new request for nothing. (The outline put to the maintainer said "behind a
  patch marker"; building it showed none is needed, for this reason.)

## The seams

`propose_forget`, `answer_forget`, the request's and the case's results, and the key provider's
state, on Temporal's test server; `lookup_refusal` and `ending_refusal` as pure functions, as
the guide's refusal table already reads them.

## Known limits

- **A case terminated or failed after the approval is forgotten whatever it kept,** as before
  (tutor review of 9c: "its key goes all the same"): it returned no report, so it has no word.
- **A case whose worker predates the fix returns no word either.** During an upgrade, a case
  ended by an old worker is judged as before the fix.
- **The migrated-to-`never` path is tested at the rule,** `ending_refusal`, and not run end to
  end on Temporal with a migration between the proposal and the approval.

## Promises

| The note says | The test that fails if it weren't true |
|---|---|
| A `while_open` case, closed and not ended, then proposed and approved, keeps its key; the request ends refused, saying why | `tests/test_temporal_forget_ending.py::test_a_case_that_keeps_closed_cases_closed_but_not_ended_is_not_forgotten` |
| An `allowed` case in the same window is forgotten | `…::test_a_closed_case_that_may_be_forgotten_still_is` |
| A `while_open` case asked while open takes the request, says so in its report, and is forgotten | `…::test_an_open_case_that_keeps_closed_cases_is_forgotten_while_it_is_open` |
| The rule, case by case, `never` and "no word" included | `…::test_the_cases_word_as_it_ended_decides_whether_its_key_goes` |
| A case refused as it opened, for its definition, can be forgotten | `…::test_a_case_refused_at_its_opening_for_its_definition_can_be_forgotten` |
| A plan's run is refused at once, saying it isn't a case, and its key stays | `…::test_a_plans_run_is_refused_at_once_saying_it_isnt_a_case` |
| A definition the worker can't read refuses the proposal, saying what to do | `…::test_a_definition_this_worker_cant_read_refuses_the_proposal_saying_what_to_do` |
| The guide's three new rows say what the engine says | `tests/test_temporal_forget.py::test_the_guides_refusals_are_what_the_engine_says` |
| A request recorded before the fix replays | `tests/test_audit_export.py::test_histories_recorded_at_19b_replay` |

Seen failing: the first with the fix absent (`assert 'forgotten' == 'refused'`), and again with
the request never reading the case's word; the third with the case never saying it took the
request; the fifth and sixth with the fix absent (each waited until the test's bound).
