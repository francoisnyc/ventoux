# Fix: a replayer's threads are shut down

A fix, not a layer: no warm-up, and nothing new to build. It finishes what
`docs/layers/fix-worker-executors.md` left under "Not in this fix": once a worker's activity
threads were shut down, the only executor threads still carried from one test to the next were
the replayers'.

## The cause

The tests replay recorded histories with Temporal's `Replayer` eleven times, in nine files:
`tests/test_temporal.py`, `test_temporal_advisor.py`, `test_temporal_case.py`,
`test_temporal_case_data.py`, `test_temporal_change_requests.py`, `test_temporal_forget.py` (three),
`test_temporal_fresh_facts.py`, `test_temporal_sensitive.py` and `test_temporal_workflow_step.py`.
No source file or guide makes one. Each passes no `workflow_task_executor`, so the replayer makes
its own. Its docstring says what happens to it (`temporalio/worker/_replayer.py`, 1.34.0):

> Note, unlike the worker, for the replayer the workflow_task_executor will default to a new
> thread pool executor with no max_workers set that will be shared across all replay calls and
> never explicitly shut down. Users are encouraged to provide their own if needing more control.

The worker is the other way round: the executor it makes for itself it shuts down
(`_workflow.py`, `if not self._workflow_task_executor_user_provided:
self._workflow_task_executor.shutdown()`), and one it is given is the caller's to shut down. So a
replayer's threads end only when the garbage collector reclaims the replayer, as the activity
threads did before #73.

## Checked, on `main`, before any change

A pytest plugin, given on the command line (`-p replaythreads`, its folder on `PYTHONPATH`),
records the executor each `Replayer` makes for itself. After each test it counts the executor
threads alive that an earlier test started, split into the replayers' and the rest. It forces no
garbage collection:

```python
"""After each test, count the executor threads alive that an earlier test started, split into the
replayers' (the executor each `Replayer` made for itself) and the rest. No collection is forced."""
import threading
import time
import weakref

import temporalio.worker

replayers: weakref.WeakSet = weakref.WeakSet()  # every executor a Replayer made for itself
born: dict[int, str] = {}
made = temporalio.worker.Replayer.__init__


def recording(self, *args, **kwargs):
    made(self, *args, **kwargs)
    replayers.add(self._config["workflow_task_executor"])


temporalio.worker.Replayer.__init__ = recording


def owner(thread: threading.Thread) -> object:
    ref = getattr(thread, "_args", (None,))[0]  # a pool thread's first argument: its executor, weakly
    return ref() if isinstance(ref, weakref.ref) else None


def pytest_runtest_teardown(item, nextitem):
    time.sleep(0.05)
    carried = {"replayer": 0, "other": 0}
    for t in threading.enumerate():
        if not t.name.startswith("ThreadPoolExecutor"):
            continue
        born.setdefault(t.ident, item.name)
        if born[t.ident] != item.name:
            carried["replayer" if owner(t) in replayers else "other"] += 1
    print(f"\nCARRIED {item.name}: {carried['replayer']} replayer, {carried['other']} other")
```

Run over the nine files (155 passed; the plugin printed for 152 of them):

| Tests | Ending with a replayer's threads an earlier test started | Most at once | Ending with other carried threads |
|---|---|---|---|
| 152 | 27 | 2 | 93 |

The "other" threads are the activity threads #73 shuts down; `main` doesn't have that fix yet.
On #73's branch the same four files that note measured carried 17 tests' worth of threads, every
one a replay test's.

## Choices

Answer by number. This fix uses #73's helper (`tests/activity_threads.py`), so it is built once
#73 is merged, on top of it.

1. **Each replay passes its own executor, from the tests' helper.** Every `Replayer` is given
   `workflow_task_executor=` a pool from the helper, opened around the replay and shut down after
   it, off the event loop and within the helper's bound, as for a worker's activities. It is the
   same rule as fix-worker-executors' choice 1: whoever makes the executor shuts it down. It is the
   rule the replayer's docstring itself points to ("Users are encouraged to provide their own").
   The replay helpers that call `asyncio.run(replayer.replay_workflow(history))` from plain
   functions run the replay in a small `async` function that holds the helper's block.
   *Recommended.*

2. **The helper's name.** It now gives threads to more than activities.
   - (a) **Renamed `worker_threads`** (file `tests/worker_threads.py`), its docstring saying both
     uses: a worker's activities, and the workflow tasks a replayer runs (a replayer runs a
     workflow worker over the history). It touches the twenty-two places #73 opens it, in sixteen files, one name
     each. *Recommended:* one helper, named for what it serves.
   - (b) **Kept as `activity_threads`**, used for replays too. Set aside: the name would say
     something false at eleven places.
   - (c) **A second helper for replays.** Set aside: the same five lines twice.

3. **A guard on the whole suite, not one test per site.** An `autouse` fixture in
   `tests/conftest.py` notes the executor threads alive before each test, and fails the test if
   one it started is still alive after it ends, naming the thread. No garbage collection is
   forced. A test per replay site would pin the eleven sites there are, but not a twelfth, and
   not the next executor an SDK upgrade makes. The guard would have caught both this leak and
   #73's. It holds only if nothing else leaves a thread behind: the worker shuts its own
   workflow-task executor down, and asyncio's default executor's threads are named otherwise
   (`asyncio_0`, …) and ended by `asyncio.run`. The first full run with the guard shows whether
   anything else does; anything it finds is said in this note, never excused by name.
   *Recommended.* Seen failing under each mutation that matters: one replay site back on the
   replayer's own executor, a builder making its own (#73's mutation), the helper shutting
   nothing down.

4. **One pool for the whole session.** A pool made once, given to every replayer and every
   worker, shut down when the session ends. Set aside: its threads are carried between tests by
   design, so the guard in choice 3 couldn't tell a leak from the pool. And a stuck task in one
   test would take a thread from the next.

5. **Left as the SDK documents it.** Set aside: it is the fault #73 fixed, in another executor.

## Not in this fix

- **A daemon thread for the helper's shutdown**, which would let `asyncio.run` return as soon as
  the bound fails (fix-worker-executors, decision 2). It is a choice of its own, still open.

## Promises

To be filled once the choices are answered and the tests written.
