# Fix: a case's requests to forget share one stream, numbered on

A fix, not a layer: no warm-up, and nothing new to build. Found by the whole-project review of
November 2026 (its finding 1c.2, kept on the branch `review-2026-11`).

## The bug

A request to forget writes its own audit records (D77): the proposal, each answer, the key
destroyed. Every request for a case wrote them to the stream `<case ID>/forget`, each numbering
from 1. The store keeps a record once by its stream and number, and refuses other content under
a number it holds. So a second request's record 1 was refused, and:

```
first request: rejected
   the request's stream: ["1: forget proposed by pat", "2: answered by noor: rejected"]
second request's workflow, 3 s after the key went: RUNNING
   its report can't be read: TimeoutError
   key of claim-1: destroyed
   the request's stream now: ["1: forget proposed by pat", "2: answered by noor: rejected"]
```

The second request went on beside its failing writer: the case closed and the key was
destroyed. Only then did it meet the writer's failure, which it could no longer seal, the key
being gone. Its workflow task failed again and again: the request never ended, its report
couldn't be read, and the store held nothing of who proposed the forgetting, who approved it, or
that the key was destroyed. A third request, made once the case was forgotten, was refused as
D32 says, and never ended either. D32: "what stays: … the request's own history"; D17, as amended
by D77: "nothing is dropped, nothing decided unrecorded".

## Decided

(The maintainer's choice of the two options put to them, 2026-11-11.)

- **One stream, numbered on.** The stream stays `<case ID>/forget`, as the brief and the guides
  name it. Before its first write, a request's writer asks the store for the number of the last
  record it holds of that stream, and numbers its own after it. Readers see one record of
  everything asked about forgetting the case, in order.
- **Asked beside the request, never before it.** The asking is the writer's first step, and the
  writer runs beside the request (D77: "beside the request, never in its way"). So the asking
  keeps no answer waiting: with the store down the proposal and the approval are still taken, and
  the case is asked to close. That is all it promises. Whether the request is then carried out
  is the case's rule, unchanged: a case whose own records can't be written doesn't end, so its
  key is kept until the store is back (D77). The request's records are written once the store
  answers.
- **A new activity, `ventoux.audit.last_number`,** registered with the export's, reading the
  store through the `read` every store already has. It counts the stream itself, never a stream
  under it.
- **Behind the patch marker `ventoux-forget-numbers`** (D51): a new activity is a new command, so
  a request in flight at the upgrade would otherwise fail its replay. A request recorded before
  the fix numbers from 1, as it did; `at_19b_forget_request` replays.
- **No race.** Two requests for one case are one workflow ID, so the second starts only once the
  first has ended, its records written.
- Rejected: a stream per request, named with the request's run ID. Simpler, but it puts an
  identifier Temporal generates into a record's ID, where D76 says "numbered in a stream, never
  by time or chance", and it changes a name the brief and both guides give.

## The seams

`propose_forget`, `answer_forget`, each request's result within a bound, the key provider's
state, and the store read back.

## The worker now reads the store (from the tutor's review of #104)

Before this fix a worker only appended to the audit store; `read` was `read_audit`'s alone. Now
every request to forget reads its stream once, the first request included. So:

- **The worker's credential must be allowed to read.** The deployment guide ("The audit store")
  and the audit guide say so.
- **A read the store refuses is retried as an outage is, on purpose.** The worker can't tell a
  credential that may not read from a store that is away, and neither may lose a record. Two
  cases, each with its test:
  - **the store down, for reads as for appends:** the proposal and the approval are taken, the
    key is kept while the case's own export waits (D77), and once the store is back the case
    ends, the key goes, and the stream reads 1 to 5;
  - **reads refused, appends taken** (a credential that may only append): the case writes its
    records, closes and ends, the key is destroyed, the request's report says `forgotten`, and
    its workflow runs on with its records unwritten until the worker may read; then they are
    written, in order. Nothing is dropped, but nothing of the request is in the store until
    then.
- **Left open, for the maintainer:** whether a request should be refused before anyone answers
  when its stream can't be read, as it is when the key service can't answer (D78), so that no
  key goes while nothing can be recorded. That would put the store in the request's way at the
  proposal, against D77's "never in its way", so it is a decision, not this fix. And `ventoux
  doctor` could ask the store one read as the worker would, so a write-only credential is seen
  before a request meets it: a rule of its own, in the guide's list.
- **The patch marker** keeps an old branch for requests recorded before the fix. It was written
  before D84, which says a fix owes no old branch before the first release: so it is more than
  is owed. It costs one command per request and is harmless.

## What the second review found in the tests (the tutor's review of #104, round 2)

The first two tests, as first written, passed for a reason they didn't state, and the second
failed about one run in four. Each waited on an earlier request's `result()`. Asking for a
result lets the time-skipping test server run its clock on; the case, sitting idle, then timed
out, ten years on, and the request that "forgot" it found it `ended: timed out`. So the tests
showed the numbering, never a live case closing as forgotten, and the note's promise that "with
the store down the request is still carried out" was not true of a live case: its key is kept
until the store is back.

Now: no test waits on a result while a case must stay alive (a request's end is read by query,
once its workflow no longer runs); each asserts how the case ended, `closed: forgotten`; and the
store-down test says what is true of a live case. The same fault was traced before, in
`fix-flaky-temporal`.

## Found, not fixed

If the store refuses one of a request's records for another reason (a store that keeps other
content under the stream's next number, say) once the key is destroyed, the request can't seal
that failure, and would stall as the second request did. Reasoned from the review's account, not
run. It is about how a failure is sealed for a workflow whose case's key is gone (D31), which is
wider than this fix; a store that is only down is retried and recovers, as the second test shows.

## Promises

| The note says | The test that fails if it weren't true |
|---|---|
| A rejected request, then one that forgets the case, then one refused after it: each ends; the case closes as forgotten, never timed out; and the store holds their records as one stream, 1 to 6, the proposal, the approval and the key destroyed among them | `tests/test_temporal_forget_stream.py::test_a_second_request_to_forget_is_recorded_after_the_first` |
| A first request numbers from 1 | the same test's first two records; `…::test_a_read_the_store_refuses_is_retried_as_an_outage_is`; and every earlier test of a request's stream |
| With the store down, for reads as for appends, the proposal and the approval are taken and the case is asked to close; the key is kept until the store is back; then the case ends as forgotten, the key goes, and the stream reads 1 to 5 | `…::test_a_store_that_is_down_keeps_no_answer_waiting_and_the_key_until_it_is_back` |
| A read the store refuses, appends taken: the case ends and the key goes, the request's records wait with nothing in the store, and are written, in order, once the worker may read | `…::test_a_read_the_store_refuses_is_retried_as_an_outage_is` |
| A request recorded before the fix replays | `tests/test_audit_export.py::test_histories_recorded_at_19b_replay` |

Seen failing: the first with the fix absent (the second request never ends, and the test's bound
is passed). Run after the rewrite: the three tests together 8 times, and the store-down test
alone 12 times, all passing.
