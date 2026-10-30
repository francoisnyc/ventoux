# Fix: a replay's threads are shut down

A fix, not a layer: no warm-up, and nothing new to build. It finishes the item that
`docs/layers/fix-worker-executors.md` left under "Not in this fix", and follows that fix's
decisions.

## The cause

The SDK's `Replayer`, given no `workflow_task_executor`, makes "a new thread pool executor with no
max_workers set that will be shared across all replay calls and never explicitly shut down" (its
docstring, `temporalio/worker/_replayer.py`, 1.34.0). The tests built eleven replayers that way,
in nine files: `tests/test_temporal.py`, `test_temporal_advisor.py`, `test_temporal_case.py`,
`test_temporal_case_data.py`, `test_temporal_change_requests.py`, `test_temporal_forget.py`
(three), `test_temporal_fresh_facts.py`, `test_temporal_sensitive.py` and
`test_temporal_workflow_step.py`. None is in `src/` or the guides. As with a worker's activity
threads, a replay's threads ended only when the garbage collector reclaimed the replayer's pool.

## Checked, on `main`, before any change

The plugin from fix-worker-executors, with what its "second plugin" did added: for every carried
thread, it names the test that started it. It still forces no garbage collection:

```python
"""After each test, count the executor threads alive, and those an earlier test started, naming
the test that started each one carried."""
import threading
import time

born: dict[int, str] = {}  # thread ident -> the test that started it
carried_from: dict[str, int] = {}  # starting test -> tests ending with one of its threads alive
tests = 0
carrying = 0
most_alive = 0
most_earlier = 0


def executor_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("ThreadPoolExecutor")]


def pytest_runtest_teardown(item, nextitem):
    global tests, carrying, most_alive, most_earlier
    time.sleep(0.05)  # a thread told to exit has time to
    alive = executor_threads()
    for t in alive:
        born.setdefault(t.ident, item.name)
    earlier = [t for t in alive if born[t.ident] != item.name]
    tests += 1
    carrying += bool(earlier)
    most_alive = max(most_alive, len(alive))
    most_earlier = max(most_earlier, len(earlier))
    for starter in {born[t.ident] for t in earlier}:
        carried_from[starter] = carried_from.get(starter, 0) + 1
    print(f"\nTHREADS {item.name}: {len(alive)} alive, {len(earlier)} from earlier tests")


def pytest_terminal_summary(terminalreporter):
    w = terminalreporter.write_line
    w(f"SUMMARY tests={tests} carrying={carrying} most_alive={most_alive} most_earlier={most_earlier}")
    for starter, n in sorted(carried_from.items()):
        w(f"STARTED BY {starter}: carried into {n} later tests")
```

Run over the four files fix-worker-executors used (`tests/test_temporal.py`,
`test_temporal_case.py`, `test_temporal_workflow_step.py`, `test_temporal_sensitive.py`) and the
replay tests' other five files (`test_temporal_advisor.py`, `test_temporal_case_data.py`,
`test_temporal_change_requests.py`, `test_temporal_forget.py`, `test_temporal_fresh_facts.py`):
157 tests, every one passing.

| Tests | Ending with threads an earlier test started | Most threads alive after one test | Most of those from earlier tests |
|---|---|---|---|
| 157 | 22 | 2 | 1 |

Every carried thread was started by a replay test:

| Started by | Carried into later tests |
|---|---|
| `test_the_bound_on_a_loop_holds_on_temporal_and_replays` | 12 |
| `test_a_case_history_with_its_workflow_type_changed_fails_replay` | 7 |
| `test_a_history_replayed_with_changed_code_fails` | 2 |
| `test_a_history_replays_with_the_same_code` | 1 |

The item holds.

## What a probe showed first

A first test replayed a history that *passes*, and checked no thread it started was still alive.
It failed on `main`, but it passed under the mutation that matters (the helper below without
`workflow_task_executor`, so the SDK makes its own pool again), four runs of four. A probe with
garbage collection disabled showed why:

- a replay that **passes** leaves nothing holding the replayer once its function returns, so
  reference counting frees the SDK's pool at once and its idle thread exits. Whether that thread
  has exited by the next line is a race, which `main` lost and the mutation won;
- a replay that **fails** raises an error whose traceback holds the replaying function's frame,
  and with it the replayer and its pool. Its thread stays alive as long as the error does, until
  the collector runs: on `main` and under the mutation alike, every time.

So the test replays a history that fails. Two of the four starters above are passing replays,
so in the full run something else held them too; that wasn't traced, and the fix doesn't depend
on it: whatever holds the replayer, the pool it runs on is shut down.

## Decided

1. **Whoever makes the replayer owns its threads.** One helper, `replay_history(history,
   workflows, converter)` (`tests/replaying.py`), makes every replayer in the tests. It opens a
   thread pool, gives it to the `Replayer` as `workflow_task_executor`, replays, and shuts the pool
   down once the replay is done, whether it passed or raised. This is fix-worker-executors'
   choice 1, and the SDK's own rule for a `workflow_task_executor` it is given: the caller shuts
   it down.
2. **Shut down off the loop, within a bound, by reusing `activity_threads()`.** The helper opens
   its pool with `async with activity_threads() as threads:` (`tests/activity_threads.py`), so the
   shutdown is `shutdown(wait=True)` on a thread of its own, within `ENDING` (10 s), as
   fix-worker-executors decided (choice 5, decision 2). *Reused, not generalised:* the mechanism
   is the same in every way (a pool someone else uses, waited for off the loop within a bound), so
   a second copy would be a second place to keep that bound right. Generalising it (a neutral name
   such as `owned_threads`) would rename twenty-five call sites for no change in behaviour, so its
   name stays; its docstring now says a replayer's pool is held the same way.
3. **Every replayer goes through it:** the eleven, each now one line. `Replayer` now appears
   only in `tests/replaying.py`; no test pins that, so a replayer built directly later would leave
   its threads to the collector again, and only a run of the plugin above would show it. The three in
   `test_temporal_forget.py` run inside a worker's block and `await` it; the others are
   synchronous and `asyncio.run` it. The `replay()` functions of four test files keep their names
   and signatures, so the many tests calling them (in those files and the ones importing them)
   are unchanged.
4. **Nothing in `src/` or the guides changes.** Neither builds a replayer.

## The earlier draft, and where this differs

An earlier draft of this note (commit `4d4c4ba`, on this branch, never reviewed) measured the
same item on `main` before #73 and offered choices instead of deciding. This fix was asked to
decide, so it decides, and differs from the draft's recommendations in two places:

- **The helper's name.** The draft recommended renaming `activity_threads` to `worker_threads`
  (its choice 2a), since the name would then say something false at eleven places. Here the
  eleven places don't open it: only `replay_history` does, once, under a comment saying what the
  pool is for. Renaming would touch twenty-five call sites for no change in behaviour. If the
  tutor prefers the rename, it is mechanical and can follow on its own.
- **A guard over the whole suite** (the draft's choice 3: an `autouse` fixture failing any test
  that leaves a thread it started alive). Not built here: it would be new test machinery for every
  test, beyond this item, and its first run would have to say what else it finds. It stays open,
  under "Not in this fix".

The draft's other choices agree with what was decided (its choice 1 is decisions 1 and 2), or
were set aside there too (its 4 and 5).

## Not in this fix

- **A guard over the whole suite** (above). Without it, a replayer or worker built later without
  an owned executor is caught only by running the plugin above.
- **A daemon thread for the helper's shutdown**, which would let `asyncio.run` return as soon as
  the bound fails (fix-worker-executors, decision 2). A choice of its own, still open.

## Checked, after the fix

The same plugin, over the same nine files (158 tests now, the new one included), every test
passing:

| | Tests ending with threads an earlier test started | Most threads alive after one test | Most of those from earlier tests |
|---|---|---|---|
| `main` | 22 of 157 | 2 | 1 |
| this fix | 0 of 158 | 0 | 0 |

No executor thread was alive after any test.

## Promises

| Promise | Test that would fail |
|---|---|
| A replay's workflow-task threads have ended once it is done, failed or not: none is left for the garbage collector | `test_the_threads_a_failed_replay_ran_on_have_ended_once_it_raises` (`tests/test_temporal.py`): a history replayed against changed code raises `NondeterminismError`, and no thread started during the replay may still be alive while that error is held. No collection is forced. Seen failing three runs of three on `main`'s `replay()` (`ThreadPoolExecutor-1_0` alive), and three of three with `replay_history` giving the `Replayer` no executor (`ThreadPoolExecutor-2_0` alive). Passes three of three with the fix. |
| The pool is shut down off the loop, within a bound, its work waited for | Reused, not re-tested: `test_an_activity_that_ends_in_time_is_waited_for` and `test_an_activity_still_running_at_the_end_fails_within_the_bound` (`tests/test_activity_threads.py`) pin `activity_threads()`, the helper `replay_history` opens its pool with. |
