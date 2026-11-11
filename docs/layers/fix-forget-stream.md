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
  writer runs beside the request (D77: "beside the request, never in its way"). With the store
  down the request is still proposed, answered and carried out; its records are written once the
  store is back.
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

## Found, not fixed

If the store refuses one of a request's records for another reason (a store that keeps other
content under the stream's next number, say) once the key is destroyed, the request can't seal
that failure, and would stall as the second request did. Reasoned from the review's account, not
run. It is about how a failure is sealed for a workflow whose case's key is gone (D31), which is
wider than this fix; a store that is only down is retried and recovers, as the second test shows.

## Promises

| The note says | The test that fails if it weren't true |
|---|---|
| A rejected request, then one that forgets the case, then one refused after it: each ends, and the store holds their records as one stream, 1 to 6, the proposal, the approval and the key destroyed among them | `tests/test_temporal_forget_stream.py::test_a_second_request_to_forget_is_recorded_after_the_first` |
| A first request numbers from 1 | the same test's first two records, and every earlier test of a request's stream |
| With the store down the request is still carried out, and its records are written, numbered on, once the store is back | `tests/test_temporal_forget_stream.py::test_a_store_that_is_down_keeps_no_answer_waiting` |
| A request recorded before the fix replays | `tests/test_audit_export.py::test_histories_recorded_at_19b_replay` |

Seen failing: the first with the fix absent (the second request never ends, and the test's bound
is passed); both with every request numbering from 1 again.
