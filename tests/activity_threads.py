"""The threads a test's worker runs its plain-function activities on, shut down when the test is
done with them (fix-worker-executors).

The worker never shuts them down: whoever made them does, after the worker has stopped (choice 1).
A plain `with ThreadPoolExecutor()` would do that, but on the event loop's own thread: it blocks
the loop while it waits, so no `asyncio.wait_for` can fire, and an activity that never returns
hangs the test with no timeout said. So the threads are shut down off the loop, and waited for
within a bound (choice 5).
"""

import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

# How long the activities still running when the worker stopped may take to end, in seconds.
ENDING = 10


@asynccontextmanager
async def activity_threads(ending: float = ENDING) -> AsyncIterator[ThreadPoolExecutor]:
    """A thread pool for a worker's `activity_executor`, shut down on the way out: every activity
    still running is waited for, never abandoned, and one still running after `ending` seconds
    fails the test (`TimeoutError`)."""
    executor = ThreadPoolExecutor()
    try:
        yield executor
    finally:
        # Off the loop's thread, so the bound can fire while it waits.
        await asyncio.wait_for(asyncio.to_thread(executor.shutdown, True), ending)
