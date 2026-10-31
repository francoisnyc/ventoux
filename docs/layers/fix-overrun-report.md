# Fix: when an activity overruns the helper's bound

A fix, not a layer: no warm-up, and nothing new to build. It answers the choice
`docs/layers/fix-worker-executors.md` left open (decision 2, and "Not in this fix" in
`docs/layers/fix-replayer-threads.md`): a daemon thread for the helper's shutdown.

The helper is `activity_threads()` (`tests/activity_threads.py`) on `main`. #77, still open, renames
it `worker_threads()`. This note says "the helper".

## The cause

The helper shuts a worker's (or a replayer's) pool down off the event loop, within a bound:
`await asyncio.wait_for(asyncio.to_thread(executor.shutdown, True), ending)`. When a task is still
running past the bound, three things wait for it, and the bound reaches only the first:

1. **The `wait_for`** raises `TimeoutError` at the bound, naming the cause. This part works.
2. **`asyncio.run`, on its way out**, shuts down its own default executor, where `to_thread` put
   the shutdown, and waits for its threads: `loop.shutdown_default_executor(THREAD_JOIN_TIMEOUT)`,
   300 s in Python 3.12 (`asyncio/runners.py`). Past that it warns ("The executor did not finishing
   joining its threads within 300 seconds") and returns.
3. **The interpreter, on its way out**, joins every pool thread: `concurrent.futures` registers
   `_python_exit` with `threading._register_atexit`, and it calls `t.join()` on each worker thread
   still known. That is the task's own thread, in the test's pool, not the shutdown's.

A thread can't be stopped from outside, so nothing in the helper can make the task end.

## Checked, on `main`, before any change

A script submits `time.sleep(8)` to a pool and shuts it down as the helper does, with a 0.5 s
bound. A second version runs the shutdown on a daemon thread of its own instead of `to_thread`,
and is woken through `loop.call_soon_threadsafe`. The project's Python (3.12), each run from the
shell so the process's exit is timed too:

| Shutdown | `TimeoutError` raised | `asyncio.run` returned | Process exited |
|---|---|---|---|
| as `main` does (`to_thread`) | 0.5 s | 8.0 s | 8.2 s |
| on a daemon thread | 0.5 s | 0.5 s | 8.1 s |

The daemon version also printed `Exception in thread` at 8 s. When the task ended, its thread
handed the result to an event loop that had already closed.

In pytest, with `main`'s helper: a test whose task overran the bound by 8 s passed its
`pytest.raises(TimeoutError)`, took 8.00 s and was reported only then. The test after it waited.
pytest exited at 8.4 s.

So the item holds as #73's review put it. The failure is decided at the bound, but reported only
when the task ends (or after 300 s), and the run can't exit while the task runs. A daemon thread
moves the report to the bound. It doesn't move the exit: (3) joins the task's own thread.

For a task that never ends, the difference is when the hang starts:

- **today**, the test hangs for 300 s, then the session goes on; at the end, the process never
  exits;
- **with a daemon thread**, every test is reported and pytest prints its summary; then the process
  never exits.

Either way, in CI the job runs until GitHub ends it. Neither job in `.github/workflows/ci.yml` sets
`timeout-minutes`, so that is GitHub's default, 360 minutes. The full suite takes about 5 minutes
here.

No test's task has overrun the bound so far. The tests' activities are fakes, and a replay's
workflow tasks end with the replay.

## Choices

Answer by number.

*Answered 2026-10-31: 1 taken; 2 to 5 set aside, as recommended. What was built is under
"Decided".*

1. **Leave the helper as it is, and bound the CI job.** The report waits for the task (or 300 s),
   as #73's corrected decision 2 says. That only matters for a test whose task overruns, which none
   has. Each job in `ci.yml` gets `timeout-minutes: 20`, four times the suite's 5 minutes. A hung run
   then fails in 20 minutes, not 6 hours, whatever hangs it, the helper's case included. Nothing
   in the tests changes. *Recommended:* the one cost that could happen (a run that never ends) is
   bounded, and it's the CI job that runs into it, not the helper.

2. **A daemon thread for the shutdown.** The helper starts
   `threading.Thread(target=shut_down, daemon=True)`. That thread calls `shutdown(wait=True)`, then
   wakes the helper with `loop.call_soon_threadsafe`, and the helper waits for it within the bound.
   - **Gain:** `asyncio.run` returns at the bound, so the failing test is reported then, the session
     goes on, and pytest's summary is printed even if the task never ends.
   - **Costs:**
     - The process still can't exit while the task runs, by (3).
     - The helper grows a thread and a future of its own.
     - The late wake must handle a closed loop, or it prints an exception at exit, as the probe
       showed. Handling it means passing over the late wake: no one is waiting for it any more by
       then.
     - With #77's guard, the task's thread is still alive at the test's end, so the test also fails
       there, naming the thread. That is right, but it is a second report of one cause.

   Worth taking with choice 1 if a quick report matters more than a simpler helper. Set aside
   alone, since it doesn't remove the hang.

3. **End the process at the session's end, if pool threads remain.** A `pytest_unconfigure` hook
   that finds pool threads still alive prints them and calls `os._exit` with a failing code, so (3)
   never joins them. Set aside: `os._exit` skips every exit hook, not just the one that waits, so
   anything else registered to run at exit (a coverage file written, a temporary folder removed)
   is skipped too, and silently.

4. **A per-test timeout from a plugin** (`pytest-timeout`, a new dependency). With its thread
   method it dumps every thread's stack and ends the process at a test's deadline. Set aside: the
   first hung test ends the whole run, and choice 1 bounds the same hang with no dependency.

5. **Make the task's thread not joined at exit,** by taking it out of `concurrent.futures`'
   record of its threads. Set aside: it edits a private structure of the standard library
   (`_threads_queues`).

## Not in this fix

- **What hangs a task.** None has, and this fix is about how the failure is reported, not about
  any task.

## Decided

1. **The helper stays as it is.** A test whose task overruns the bound fails with a
   `TimeoutError` raised at the bound. The report waits for the task to end (or 300 s), as
   fix-worker-executors' corrected decision 2 says.
2. **Each CI job ends within 20 minutes.** `timeout-minutes: 20` under `runs-on` in both jobs of
   `.github/workflows/ci.yml`, `check` and `changes`, each with a comment saying why. A run that
   hangs, for this reason or any other, fails in 20 minutes, where GitHub's default would wait 360.
3. **A test pins it.** `tests/test_ci_workflow.py` reads the workflow as text, as
   `tests/test_summary.py` does, with no YAML parser. It checks that the jobs are `check` and
   `changes`, so a job added later shows up there and must be bounded too, and that each has the
   line.

## Promises

| Promise | Test that would fail |
|---|---|
| Every CI job ends within 20 minutes | `test_every_job_ends_within_twenty_minutes` (`tests/test_ci_workflow.py`). Seen failing on `main`'s workflow ("the CI job check has no `timeout-minutes: 20`"), and with either job's line removed, naming that job. |
| A job added to the workflow is checked too | The same test: the jobs it reads must be exactly `check` and `changes`, so a third fails it until the test, and the bound, take it in. |
| The reader finds a job's lines, and a job without the bound | `test_a_job_without_a_bound_is_found`, on a two-job workflow, one bounded and one not. |
| A task that overruns the bound fails its test at the bound, reported once the task ends | Unchanged: `test_an_activity_still_running_at_the_end_fails_within_the_bound` (`tests/test_activity_threads.py`). |
