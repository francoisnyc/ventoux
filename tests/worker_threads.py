"""The threads a test gives the SDK to run on, shut down when the test is done with them: a
worker's plain-function activities (fix-worker-executors), and the workflow tasks a replayer runs
(fix-replayer-threads, which renamed this helper from `activity_threads`).

Neither the worker nor the replayer shuts a pool it is given down: whoever made it does, once they
have stopped (fix-worker-executors, choice 1).
A plain `with ThreadPoolExecutor()` would do that, but on the event loop's own thread: it blocks
the loop while it waits, so no `asyncio.wait_for` can fire, and an activity that never returns
hangs the test with no timeout said. So the threads are shut down off the loop, and waited for
within a bound (choice 5).

What the bound gives is the failure, decided within the bound and naming the cause. What it can't
give is a quick end: a thread can't be stopped. The shutdown runs on asyncio's default executor,
which `asyncio.run` waits for on its way out (up to 300 s), and Python joins pool threads when the
process exits. So the test is reported only once the activity ends (or after 300 s), and the run
can't exit while it runs.
"""

import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

# How long the tasks still running when the worker or replayer stopped may take to end, in seconds.
ENDING = 10


@asynccontextmanager
async def worker_threads(ending: float = ENDING) -> AsyncIterator[ThreadPoolExecutor]:
    """A thread pool for a worker's `activity_executor` or a replayer's `workflow_task_executor`,
    shut down on the way out: every task still running is waited for, never abandoned. One still
    running after `ending` seconds fails the test with a `TimeoutError`, raised then; the test is
    reported once that task ends, as the module's docstring says."""
    executor = ThreadPoolExecutor()
    try:
        yield executor
    finally:
        # Off the loop's thread, so the bound can fire while it waits.
        await asyncio.wait_for(asyncio.to_thread(executor.shutdown, True), ending)
