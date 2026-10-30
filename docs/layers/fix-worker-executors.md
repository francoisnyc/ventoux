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

5. **How the executor is shut down: wait for its activities.** Whichever owner is chosen, the
   shutdown is `shutdown(wait=True)` (what `with` does): a plain-function activity still running
   when its worker stops is waited for, never abandoned on a thread. A test whose activity never
   returns then hangs at the shutdown instead of passing; the tests already bound their
   scenarios (`asyncio.wait_for`), and a hang points at the activity, the cause, rather than
   hiding it. *Recommended.* Set aside: `wait=False` or `cancel_futures=True`, which would let a
   stuck activity go unnoticed.

6. **A test pins it.** A test starts a worker built as decided, runs one plain-function activity
   on it, stops the worker, and checks that no thread the worker started is still alive (by
   comparing `threading.enumerate()` before and after, with no garbage collection forced). Seen
   failing on `main`'s builders, where the thread is still alive. *Recommended.*

## Not in this fix

- **The registry worker** (`registry_worker`, `src/ventoux/temporal/registry.py`) passes no
  executor: its activities are `async`, so it makes no threads.

## Promises

To be filled once the choices are answered and the tests written.
