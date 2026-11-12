# Fix: a value under a name that is no field is never kept

A fix, not a layer: no warm-up, and nothing new to build. Found by the whole-project review of
November 2026 (its finding 1c.7, kept on the branch `review-2026-11`), and decided in D89.

## The bug

A person's answer arrives with every form value wrapped, since the client can't tell which
fields are sensitive (D31). A refused act is recorded with what it gave (D76), each value "as
the case file keeps it". For a name that is no field of the case, `kept` unwrapped the value: a
name the engine didn't recognise was read as "not sensitive", a permissive default.

```
answer, a name that is no field -> AnswerRefused the answer gives scratch, which accept doesn't set
   record's values: {'scratch': 'STRAY-1'}
edit, a name that is no field -> ChangeRefused scratch is not a field of claim: only a declared field is edited
   record's values: {'scratch': 'STRAY-3'}
```

So a date of birth typed into a box the task doesn't have was written in clear: in the case's
history (the export activity's input), in the audit store, shown by `read_audit` to every role
and to none, in the state a case continues as new with, and still there after the case was
forgotten. The first door is the review's; the second, a proposed edit of a name that is no
field, was found while reproducing it.

## Decided

- **A refused act's record keeps a value only under a name that is a field** (D89: "never
  kept"). One small function, `given_for_fields` in `case/recording.py`, says so for an
  opening, an answer and a proposed edit. A value under any other name is dropped still wrapped.
- **`kept` has no permissive branch any more.** Asked about a name that is no field it fails
  (`KeyError`) instead of unwrapping. Nothing calls it that way; no test asks it to.
- **A real field the outcome doesn't set is unchanged:** its value is recorded as its field
  says, wrapped if sensitive, plain if not (D76, D89).
- **The refusal's line is unchanged:** it already said the name and never the value.
- **No new engine version, no patch marker** (D84). No history in `tests/histories` held such
  an act, so none is recorded again; every recorded history replays as it is.
- **The guide says what D89 asks of it:** a field that may hold personal data is declared
  `sensitive` (`docs/guides/case-data.md`, "Forgetting a person").

## The seams

- In memory: `decide` and `record_refused`, and the state as it is carried (`state_as_data`), as
  `tests/test_audit_records.py` already uses them.
- On Temporal: `answer` and `propose_change`; the case's history as the server stores it and as
  it is exported; the audit store's files; `read_audit`. Read before and after forgetting. The
  request's end is read by query, never by a `result()`, and the test asserts the case ended
  `closed: forgotten` (the lesson of #104).

## Known limits

- **A refusal says the first problem it finds.** An answer with two names that are no field, or
  a missing field and such a name, has every such value dropped and one problem said.
- **A history already recorded keeps what it held.** Nothing takes a value out of Temporal's
  history or out of an append-only store.
- **A case continuing as new on Temporal is not driven here.** A refused act's record is
  carried only while it isn't exported yet, which a test can't time reliably; the carried state
  is read directly instead.
- **A refused edit's value is still unwrapped for one line.** `kept` in `case/requests.py`
  unwraps it into a local variable, and the next check refuses the edit: the value is kept
  nowhere, so no test could see a change there. D89 says "dropped unopened"; for an edit it is
  opened for a moment and then dropped.

## Found, not fixed

A refused event's record keeps its payload as it was carried (`act_of`, the `Sent` case),
including under a name the event doesn't declare. Events come from systems, never from a form.
Read in the code, not run: whether such a payload can hold anything sensitive wasn't checked.

## Promises

| The note says | The test that fails if it weren't true |
|---|---|
| A refused answer's record holds no value under a name that is no field, and the carried state doesn't either; the refusal says the name | `tests/test_audit_records.py::test_a_refused_answer_keeps_no_value_under_a_name_that_is_no_field` |
| The same for a refused edit | `tests/test_audit_records.py::test_a_refused_edit_keeps_no_value_under_a_name_that_is_no_field` |
| A refused answer's value for a real field is recorded as its field says | `tests/test_audit_records.py::test_a_refused_answers_value_for_a_real_field_follows_that_field` |
| On Temporal neither value is in the history, the store's files or what `read_audit` shows, before forgetting or after; the case went on waiting, then closed as forgotten | `tests/test_temporal_stray_values.py::test_a_value_under_a_name_that_is_no_field_is_kept_nowhere` |
| Every recorded history replays as it is | the replay tests, unchanged |

Seen failing: the first, second and fourth with each door opened again (the answer's, then the
edit's); the third with the rule over-applied (every value of a refused act dropped). The
Temporal test was run 10 times in a row, all passing.
