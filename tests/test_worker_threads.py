"""The tests' worker threads (`worker_threads`): shut down off the event loop, within a bound
(fix-worker-executors, choice 5)."""

import asyncio
import time

import pytest
from worker_threads import worker_threads


def test_an_activity_still_running_at_the_end_fails_within_the_bound() -> None:
    # Waited for, never abandoned; but off the loop's thread, so the bound fires while it waits.
    # On the loop (a plain `with`), the wait would block it, and no timeout could be said.
    async def go() -> float:
        began = time.monotonic()
        with pytest.raises(TimeoutError):
            async with worker_threads(ending=0.2) as threads:
                threads.submit(time.sleep, 1)  # a pool thread busy past the bound
        return time.monotonic() - began

    assert asyncio.run(go()) < 0.9


def test_an_activity_that_ends_in_time_is_waited_for() -> None:
    finished: list[str] = []

    def slow() -> None:
        time.sleep(0.3)
        finished.append("done")

    async def go() -> None:
        async with worker_threads(ending=2) as threads:
            threads.submit(slow)

    asyncio.run(go())
    assert finished == ["done"]
