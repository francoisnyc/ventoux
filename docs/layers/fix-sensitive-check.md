# Fix: a sensitive option or attachment is asked of its check still wrapped

A fix, not a layer: no warm-up, and nothing new to build. Found by the whole-project review of
November 2026 (its findings 1c.1 and 1b.4, kept on the branch `review-2026-11`).

## The bug

When a person's answer gives an option (D67) or an attachment (D68), the engine asks that
system's check, an activity. The value it asked with was unwrapped, whatever its field said:

```
review#1.receipt asks documents.issued@1 with attachment = str(doc-7f3a)
control: tell#1 asks letters.draft@2 with to_customer = Sensitive(‹sensitive›)
```

On Temporal an activity's input is written into the case's history. So a sensitive attachment's
ID, or a sensitive option, sat there in plain text: read by anyone with namespace access (D16),
kept for the retention period, and still readable after the case's key was destroyed. D31 says
"the value is wrapped wherever it goes", and D68 that "a `sensitive` attachment's ID is sealed
and forgotten with the case's key". In the case file the value was wrapped, as it should be; only
the check's command carried it in clear.

**The cause.** `checked_set` (`case/runtime.py`) built each check's input as
`str(plain(form[name]))`. Every form value arrives wrapped, since the client can't tell which
fields are sensitive (D31), so the wrapper has to come off to read the value; nothing put it back
for a sensitive field.

## Decided

- **A sensitive field's check is asked with the value wrapped;** any other field's in plain text,
  so the rest of the history stays readable (D15). One small function, `asked_with`, says so
  where the command is built. Nothing else changes: the codec seals a wrapped input under the
  case's key and opens it for the activity inside the worker, as for any sensitive input, so the
  check's code is given the plain value as before.
- **No new engine version (D51).** The case decides nothing differently: the same check, for the
  same entry, with the same outcome. Only how one input of an activity crosses Temporal changes,
  and on replay Temporal reads a recorded activity's result back, never its input. Shown by a
  fixture recorded under `main` at `830ed3f`, before the fix, which replays with it.
- **A dated line under D68, and one under D67,** in the brief. No guide changes: the case-data
  guide's "Mark an attachment `sensitive` if its ID itself says something" is now true of the
  history too.

## The seams

- `decide`, for the command the engine asks for, as the tests of approvals read it.
- On Temporal: the case's history as the server stores it (every payload of every event), and
  what each check's code was called with.

## Known limit

A history already recorded keeps what it held in plain text. Nothing can take a value out of
Temporal's history; for a case that matters, the namespace's retention period is the bound, and
that is the deployment's to shorten.

## Found, not fixed

The review found two neighbours of this bug, each its own fix (`reviews/2026-11/FIXES.md` on the
review branch, fixes 5 and 6): a form value given under a name that is no field is kept in clear,
and a contract validator's message quoting a sensitive value is written in clear.

## Promises

| The note says | The test that fails if it weren't true |
|---|---|
| A sensitive attachment's check is asked with its ID wrapped | `tests/test_attachments.py::test_a_sensitive_attachments_check_is_asked_with_the_id_still_wrapped` |
| A sensitive option's check is asked with its value wrapped | `tests/test_attachments.py::test_a_sensitive_options_check_is_asked_with_the_value_still_wrapped` |
| A field that isn't sensitive is asked in plain text | `tests/test_attachments.py::test_a_check_of_a_field_that_isnt_sensitive_is_asked_in_plain_text` (and the second assertion of the test above) |
| On Temporal neither value is anywhere in the stored history, and each check's code is still given the plain value | `tests/test_temporal_attachments.py::test_a_sensitive_option_and_attachment_never_cross_temporal_in_plain_text` |
| A history recorded before the fix replays, making no check again, and keeps what it held in plain text | `tests/test_temporal_attachments.py::test_a_history_recorded_before_the_fix_replays_and_keeps_what_it_held` |

Each of the first four was seen failing with the fix taken out (`asked_with` giving the value as
it is), and the third with it over-applied (every value wrapped).

Not promised here, and not tested: that the sealed value can no longer be opened once the case
is forgotten. That is the codec's and the key provider's promise for every sealed part (D31,
D32), tested where forgetting is; this fix only makes the value one of those parts.
