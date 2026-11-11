"""Around every test: no thread it started outlives it (fix-replayer-threads, choice 3).

A thread pool nobody shuts down keeps its threads until the garbage collector reclaims it, at some
later test: a worker's activity threads did (fix-worker-executors), and a replayer's did. A test
per place that makes a pool would pin the places there are, not the next one. So every test is
checked: a thread it started that is still alive once it ends fails it, named. No collection is
forced, so a pool left to the collector is caught, not tidied away.
"""

import threading
from collections.abc import Iterator

import pytest


# pytest: `autouse` runs this fixture around every test that can see it (conftest.py imports it).
@pytest.fixture(autouse=True)
def no_thread_outlives_its_test() -> Iterator[None]:
    before = set(threading.enumerate())
    yield
    left = sorted(thread.name for thread in threading.enumerate() if thread not in before)
    if left:
        pytest.fail(
            f"threads this test started are still alive: {', '.join(left)}. Shut down what "
            "started them before the test ends: a worker's or a replayer's executor goes through "
            "worker_threads() (tests/worker_threads.py)."
        )
