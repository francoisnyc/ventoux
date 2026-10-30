# Fix: four checks carried from earlier reviews

A fix, not a layer: no warm-up, and nothing new to build. Four small items carried from the
tutor's reviews of #51, #55 and #60, and from layer 13e: three gaps in the tests, and one line of
the brief. Each was shown to still hold on `main` before anything changed. Each new test was seen
failing, under the mutation it pins or on `main`'s code, as said under each.

## 1. Why the step fails, shown as written, past the limit too

**The item.** Two parts of 13e's Markdown escaping (`src/ventoux/case/markdown.py`) had no test:
line breaks, and the CI summary's failure messages (`src/ventoux/tooling/summary.py`).

**Checked on `main`.** Each part removed in turn, then the tests run (every test but the Temporal
ones; none of those writes Markdown):

| Mutation | Tests failing |
|---|---|
| `text()` keeps line breaks (the `BREAKS` branch removed) | 1: `test_what_a_draft_or_a_person_writes_is_shown_never_rendered` (`tests/test_approve.py`) |
| `text()` writes a break as `\n` without escaping its backslash | the same 1 |
| `code()` keeps line breaks | 1: `test_a_path_in_a_code_span_is_fenced_past_its_backticks` |
| The whole summary's failures written without `text()` (`said_as`) | 1: `test_an_issues_message_is_shown_as_written` |
| `cant_be_read`'s reason written without `text()` | 1: `test_a_base_that_isnt_a_folder_cant_be_read` |
| The short form's failures written without `text()` (`for_summary_file`, past the limit) | **none** |

So the item holds only in part. Line breaks have been pinned since layer 15, but only in
`test_approve.py`. The test 13e's promises name for them (`test_markdown_a_definition_writes_is_shown_as_written`,
`docs/layers/13-diff.md`) passes without them. Its literal is quoted as JSON before it is
escaped, so `text()` never sees a raw break there. The failure messages are pinned in the whole
summary, but not in the short form CI writes when the summary is past GitHub's limit.

**Decided.** One test in the summary's own file,
`test_why_the_step_fails_is_shown_as_written_in_either_form` (`tests/test_summary.py`). A package
folder in the head named `a<b` + line break + `c`, its `case.json` unreadable (`{`). A folder's
name reaches the failure as it is, never quoted as JSON, so the `<` and the raw break both reach
`text()`. The test checks the failure line in the whole summary and in the short form (limit 100
bytes): `- examples/packages/a&lt;b\\nc, in the head: case.json isn't JSON: …`.

**Seen failing** under each of the three mutations that matter here: the `BREAKS` branch removed,
the break's backslash left unescaped, and either form's failures written without `text()`. It
passes on `main`'s code, which already escapes both. It pins them; it fixes nothing.

## 2. The late-line test, independent of a warm server

**The item.** `test_a_line_printed_late_fails_the_test_on_the_way_out`
(`tests/test_skipping_server.py`) starts the SDK's own test server 0.2 s after the stand-in, and
the stand-in prints its line 3 s in. A cold read of the SDK's binary took 3.84 s (review of #51),
so after a cold start the SDK's server could answer after the line.

**Checked on `main`.** On this machine a cold start isn't slow. Evicting the binary from the page
cache (`posix_fadvise(..., POSIX_FADV_DONTNEED)`) left the SDK's start at 0.12 to 0.22 s, the
same as warm. So a cold read was stood in for by delaying the SDK's start in the test
(`asyncio.sleep(0.2)` set to the delay below), on `main`'s 3 s line, with the harness's `tried`
printed:

| The SDK's server starts after | Result on `main` | Harness starts |
|---|---|---|
| 0.2 s (as written) | passes | 1 |
| 2.7 s | passes | 1 |
| 2.95 s, 3.0 s | **fails**: the start sees the other server on the port, three times, "found every port it was given taken" | 1, then 2 skipped |
| 3.84 s (the cold read) | passes | **2** |
| 5.0 s | passes | **2** |
| 6.5 s | passes | **3** |

The item holds, though not as the review expected. A server answering just as the line comes
fails the test. A slower one, as after a cold read, passes, but only because the harness stopped
the stand-in when it printed its line and started it again on the same port. The second
stand-in's line then came during the body. So the test passed without being the case it is about
(a line that comes after the test began on the first start). A retry hid the cause.

**Decided.**
- **The line comes after any start of the other server that succeeds.** `LATE = 6` seconds,
  where it was 3. The other server starts 0.2 s after the probe, and the SDK waits at most 5 s for
  its server before it raises ("Try to connect every 100ms for 5s", fix-test-server-port). So a
  start that succeeds answers before 6 s, cold or warm, and one that doesn't fails with the SDK's
  own error, never quietly. 6 s is the shortest whole number past 5.2 s.
- **The body's wait is tied to it:** `LATE + 0.5`, as 3.5 was to 3.
- **The test checks it ran on the first start:** `environment.tried == ["started on <port>"]`,
  so a line that comes too early fails the test instead of passing on a second stand-in.

The test now takes 7.1 s where it took 4.3 s.

**Seen failing:** the new check, on `main`'s 3 s line, with the SDK's start delayed to 3.84 s and
to 5.0 s ("Left contains one more item: 'started on …'"). With `LATE = 6` the same delays (3.84 s,
5.0 s and 5.3 s) pass, each on one start.

## 3. The dev server's flags, pinned to the SDK they were read from

**The item.** `flags()` in `tests/dev_server.py` copies the arguments the SDK passes to
`server start-dev`, read from the SDK's running process at temporalio 1.34.0. Nothing tied them
to that version.

**Checked on `main`.** With `temporalio.service.__version__` set to `1.35.0` before any test
module imports it (a pytest plugin), all 7 tests of `tests/test_dev_server.py` passed, and nothing
mentioned the flags.

**Decided.** `FLAGS_READ_AT = "1.34.0"` beside `flags()`, its docstring naming it. A test,
`test_the_flags_are_the_pinned_sdks` (`tests/test_dev_server.py`), compares it with the SDK's
version. On an upgrade it fails, saying: "temporalio is 1.35.0, but flags() in
tests/dev_server.py was read from the SDK's own start at 1.34.0: check the flags again against the
new SDK's own start (`server start-dev`'s arguments in its running process), then set
FLAGS_READ_AT to the new version."

**Seen failing** with the SDK's version set to 1.35.0, with that message; passing at 1.34.0.

## 4. D5: a pull request that edits the hashing code is code review's to catch

**The item.** The CI summary runs the code of the merge commit it checks out, not the base's
(`.github/workflows/ci.yml`, job `changes`; only the base's promises come from the base's code). A
pull request that also edits the hashing code (`core/promise.py`, `core/contract_hash.py`,
`core/hash_check.py`) can therefore make its own check agree.

**Checked on `main`.** A script ran `summarize` on the refund example, `orders.lookup@1` recorded
by the base with `start_to_close` 5 and changed in place to 10. Run with `main`'s hashing code:
exit 1, "1 contract not as recorded". Run with `promise_of`, as a pull request could edit it,
reading that timeout back as 5: exit 0, "Every contract matches the hash the base recorded".

**Decided.** A dated amendment under D5 in `docs/BRIEF.md` (2026-10-30), the text above it
standing. The summary can't catch this, and doesn't try. Catching it is code review's job: a pull
request that touches those files is read for what its hashes stop covering. No test: it promises
nothing about the code.

## Promises

| Promise | Test that would fail |
|---|---|
| A failure's text is escaped in the whole summary and in the short form past the limit: a `<` shown as `&lt;`, a line break as `\n`, never a line of its own | `test_why_the_step_fails_is_shown_as_written_in_either_form` (`tests/test_summary.py`). Seen failing with the `BREAKS` branch removed, with the break's backslash unescaped, and with either form's failures written without `text()`. |
| The late-line test is the case it is about: one start, its line printed after the test began, at any start of the other server that succeeds (6 s, past the SDK's 5 s wait) | `test_a_line_printed_late_fails_the_test_on_the_way_out`, its new check of `tried`. Seen failing on the 3 s line with the other server's start delayed to 3.84 s and 5.0 s; passing at 6 s. |
| An SDK other than the one `flags()` was read from fails a test, saying to read the flags again | `test_the_flags_are_the_pinned_sdks` (`tests/test_dev_server.py`). Seen failing with the SDK's version set to 1.35.0. |
