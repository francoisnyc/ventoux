# Fix: a worker's activity threads are shut down

A fix, not a layer: no warm-up, and nothing new to build. Carried from the tutor's review of #51
(choice 87).

## The cause

`plan_worker` and `case_worker` (`src/ventoux/temporal/worker.py`) each build the `Worker` with
`activity_executor=ThreadPoolExecutor()`, and nothing ever calls that executor's `shutdown`. The
SDK doesn't either: the `Worker` uses the executor it is given and leaves its lifetime to whoever
made it (`temporalio/worker/_worker.py`, the `activity_executor` argument; at 1.34.0 nothing in
the worker shuts it down). Three tests build their own worker the same way:
`tests/test_temporal_workflow_step.py`, `tests/test_temporal_sensitive.py` and
`tests/test_temporal_case_release.py`.

So a worker's threads outlive it. An idle executor thread exits only when the garbage collector
reclaims its executor (Python's `ThreadPoolExecutor` wakes its threads from a weak reference's
callback), which happens when it happens: never at a point the code chooses.

## Checked, on `main`, before any change

A pytest plugin, given on the command line (`-p threadcount`, the folder holding it on
`PYTHONPATH`), counts after each test the executor threads alive, and how many of those an earlier
test started. It forces no garbage collection, so it sees the suite as it runs:

```python
"""After each test, count the executor threads alive, and those an earlier test started."""
import threading
import time

born: dict[int, str] = {}  # thread ident -> the test that started it


def executor_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("ThreadPoolExecutor")]


def pytest_runtest_teardown(item, nextitem):
    time.sleep(0.05)  # a thread told to exit has time to
    alive = executor_threads()
    for t in alive:
        born.setdefault(t.ident, item.name)
    earlier = sum(1 for t in alive if born[t.ident] != item.name)
    print(f"\nTHREADS {item.name}: {len(alive)} alive, {earlier} from earlier tests")
```

Run over `tests/test_temporal.py`, `tests/test_temporal_case.py`,
`tests/test_temporal_workflow_step.py` and `tests/test_temporal_sensitive.py` (107 tests, every
one passing):

| Tests | Ending with threads an earlier test started | Most threads alive after one test | Most of those from earlier tests |
|---|---|---|---|
| 107 | 76 | 7 | 6 |

The item holds: threads outlive the test that started them, in 76 tests of 107. They don't grow
without bound, though. The garbage collector reclaims executors often enough that at most 7 were
alive at once in this run, and an earlier run of three of those files saw at most 9. The fault is
that their end is left to the collector, not that they pile up past every limit.

## Choices

Answer by number. Each choice covers all five places that build an executor (the two builders
and the three tests).

*Answered 2026-10-30, from the tutor's review: 1, 5 and 6 taken, 2, 3 and 4 set aside, with
additions and two corrections, each marked where it applies. What was built is under "Decided".*

1. **Whoever starts the worker owns its executor.** `plan_worker` and `case_worker` (and
   `environment_worker`, which passes through to `case_worker`) take the executor as an argument
   and no longer make one. The caller opens it with `with ThreadPoolExecutor() as executor:`
   beside its `async with` for the worker, so the executor is shut down when the caller's block
   ends, after the worker has stopped. This is how the SDK's own samples hold it, and it keeps the
   `Worker` returned as it is today. Its cost is about thirty call sites in the tests, each
   gaining one line; a small helper in `tests/` (a context manager giving a client's worker and
   its executor together) would keep each to one line. *Recommended:* the function that makes a
   resource is the one that ends it, and the builders, which return a worker they don't run,
   can't know when that is.
   *Taken, with additions (2026-10-30):* the parameter is named `activity_executor`, as the SDK
   names it, keyword-only and with no default, so a caller can't forget it. The SDK holds the
   same rule for the one executor it would otherwise make itself, `workflow_task_executor`: "if
   one is provided, the caller is responsible for shutting it down after the worker is shut down"
   (`temporalio/worker/_worker.py`, 1.34.0). The change is public, so the four guides that show
   the builders show the executor's `with` block (below).

2. **The builders become context managers that own both.** `plan_worker(...)` gives an
   `@asynccontextmanager` that opens the executor, runs the `Worker` inside it, and shuts the
   executor down after the worker stops. Call sites already written `async with plan_worker(...)`
   keep working unchanged. Set aside unless you prefer it: it hides the `Worker` behind a
   home-made wrapper (the conventions keep framework idioms as they are), and a caller that wants
   the `Worker` itself (to call `run()` in a deployment) can no longer have it.

3. **A subclass of `Worker` shuts its executor down on `shutdown()`.** Set aside: it is a
   home-made wrapper around a framework class, and a worker that never starts (refused before
   `__aenter__`) would still leave its executor to the collector.

4. **One executor for the whole process, never shut down.** A module-level
   `ThreadPoolExecutor` every worker shares: threads are bounded by its size and reused. Set
   aside: shared state across tests and workers, a size that must cover every worker running at
   once (the SDK warns when `max_workers` is below a worker's `max_concurrent_activities`), and
   threads still never shut down, only fewer.
   *Corrected 2026-10-30, from the tutor's review; the reason above stands without it:* the SDK
   warns only when `max_concurrent_activities`, or a tuner, is set. By default it is `None`, and
   nothing warns (`_warn_if_activity_executor_max_workers_is_inconsistent`).

5. **How the executor is shut down: wait for its activities.** Whichever owner is chosen, the
   shutdown is `shutdown(wait=True)` (what `with` does): a plain-function activity still running
   when its worker stops is waited for, never abandoned on a thread. A test whose activity never
   returns then hangs at the shutdown instead of passing; the tests already bound their
   scenarios (`asyncio.wait_for`), and a hang points at the activity, the cause, rather than
   hiding it. *Recommended.* Set aside: `wait=False` or `cancel_futures=True`, which would let a
   stuck activity go unnoticed.
   *Corrected 2026-10-30, from the tutor's review:* the tests' bounds don't catch it. A plain
   `with` in async code calls `shutdown(wait=True)` on the event loop's own thread and blocks it,
   so no `asyncio.wait_for` can fire while it waits. Rerun here: a pool thread busy for 5 s at the
   block's end, under a 1 s `wait_for`, "finished after 5.0 s", no timeout said; with
   `await asyncio.to_thread(executor.shutdown, True)`, the `TimeoutError` was raised after 1.0 s.
   So `wait=True` stays, but the tests shut the executor down off the loop, in a helper, within a
   bound. The guides keep a plain `with` around `await worker.run()`: a deployment has no bound
   to keep.

6. **A test pins it.** A test starts a worker built as decided, runs one plain-function activity
   on it, stops the worker, and checks that no thread the worker started is still alive (by
   comparing `threading.enumerate()` before and after, with no garbage collection forced). Seen
   failing on `main`'s builders, where the thread is still alive. *Recommended.*
   *Taken, with additions (2026-10-30):* through the tests' helper, and also seen failing when a
   builder ignores the executor it is given and makes its own.

## Not in this fix

- **The registry worker** (`registry_worker`, `src/ventoux/temporal/registry.py`) passes no
  executor: its activities are `async`, so it makes no threads.
- **The replayer's threads.** The SDK's `Replayer`, given no `workflow_task_executor`, makes "a
  new thread pool executor with no max_workers set that will be shared across all replay calls
  and never explicitly shut down" (its docstring, 1.34.0). The tests build eleven replayers that
  way. Their threads are the only ones still carried from one test to the next after this fix
  (below). They are workflow-task threads, not activity threads, and are left for their own fix.

## Checked, after the fix

The same plugin, over the same four files (108 tests now, the new one included), every test
passing:

| | Tests ending with threads an earlier test started | Most threads alive after one test | Most of those from earlier tests |
|---|---|---|---|
| `main` | 76 of 107 | 7 | 6 |
| this fix | 17 of 108 | 2 | 2 |

Each of the 17 was a replayer's thread: a second plugin named, for every carried thread, the test
that started it, and each was a replay test (`test_the_bound_on_a_loop_holds_on_temporal_and_replays`,
`test_a_case_history_replayed_with_changed_code_fails` and three others). No activity thread was
carried.

## Decided

1. **The builders take the caller's executor.** `plan_worker`, `case_worker` and
   `environment_worker` take `activity_executor`, keyword-only and with no default, and pass it to
   the `Worker`. They make none. A call without it is a `TypeError`, and mypy refuses it.
2. **The tests' helper shuts it down off the loop, within a bound.** `activity_threads()`
   (`tests/activity_threads.py`) is an async context manager. It gives a `ThreadPoolExecutor`,
   then, on the way out, `await asyncio.wait_for(asyncio.to_thread(executor.shutdown, True),
   ending)`, `ending` 10 s by default. Every activity still running is waited for. One still
   running after the bound fails the test with a `TimeoutError`, never a hang. It is entered
   before the worker, so it shuts down after the worker has stopped.
   The bound is the helper's own, not the scenario's: most scenarios bound only the scenario,
   inside the worker's block (`asyncio.wait_for(scenario(...), timeout=20)`), so the shutdown
   comes after that bound has ended. A bound in the helper covers every caller the same way.
3. **Every test that starts a worker goes through it:** the twenty-two calls of the builders, and
   the three tests that build a `Worker` with an executor of their own
   (`tests/test_temporal_workflow_step.py`, `tests/test_temporal_sensitive.py`,
   `tests/test_temporal_case_release.py`). The activation and registry tests' helpers (`started`,
   `production_worker`) return a worker their callers entered; each is now an async context
   manager that opens the threads, starts the worker, and stops both in that order. The registry
   tests' four direct calls of `environment_worker` go through `production_worker`, which takes
   the queue now.
4. **The four guides show the `with` block,** since a deployment following them would otherwise
   get a `TypeError`:
   - `docs/guides/plans.md` ("Running a plan on Temporal"): `plan_worker`, and why the block
     owns the threads;
   - `docs/guides/cases.md`: `case_worker`;
   - `docs/guides/case-data.md`: `case_worker` with `forget=`. This block stays one assignment,
     using the executor the cases guide's `with` block opens: `test_the_guides_forget_example_runs_as_written`
     runs it as written, with `exec`, and a `with` block holding `await worker.run()` can't run
     there. The test gives it the tests' own executor;
   - `docs/guides/releases.md`: `environment_worker`.

## Promises

| Promise | Test that would fail |
|---|---|
| A worker's activity threads have ended once its block is over: none is left for the garbage collector | `test_the_thread_an_activity_ran_on_has_ended_once_its_worker_stops` (`tests/test_temporal.py`): a plain-function activity records its thread, and it must not be alive after `on_temporal` returns. Seen failing on `main`'s builders (`ThreadPoolExecutor-0_0` alive), with `plan_worker` ignoring the executor it is given and making its own (`ThreadPoolExecutor-1_0` alive), and with the helper shutting nothing down. |
| An activity still running when the worker stops is waited for, never abandoned | `test_an_activity_that_ends_in_time_is_waited_for` (`tests/test_activity_threads.py`). Seen failing with `shutdown(wait=False)`. |
| One still running past the bound fails the test with a `TimeoutError` within the bound, never blocking the loop | `test_an_activity_still_running_at_the_end_fails_within_the_bound`. Seen failing ("DID NOT RAISE") with a plain `shutdown(wait=True)` on the loop's thread, and with `wait=False`. |
| A builder can't be called without an executor | mypy, strict, on every call site: `Missing named argument "activity_executor"`. Seen on the registry and activation tests' calls before they were changed. |
