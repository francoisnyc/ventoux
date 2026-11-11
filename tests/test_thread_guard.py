"""The guard around every test: a thread it started that outlives it fails it (fix-replayer-threads,
choice 3). Each case runs in a pytest of its own, in a process of its own, with the guard as the
suite has it: a thread the inner test leaves alive ends with that process, never reaching this
test's own guard."""

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

# The inner run's conftest: this folder on its import path, then the guard, as tests/conftest.py
# imports it.
GUARDED = (
    f"import sys\nsys.path.insert(0, {str(Path(__file__).parent)!r})\n"
    "from thread_guard import no_thread_outlives_its_test  # noqa: F401\n"
)


def test_a_pool_left_running_fails_the_test_that_started_it(pytester: pytest.Pytester) -> None:
    # Held by the module, so the garbage collector can't end it either: as a replayer's pool was
    # held by a failed replay's traceback.
    pytester.makeconftest(GUARDED)
    pytester.makepyfile(
        """
        from concurrent.futures import ThreadPoolExecutor

        KEPT = []

        def test_leaves_a_pool():
            KEPT.append(ThreadPoolExecutor())
            KEPT[0].submit(print).result()
        """
    )
    run = pytester.runpytest_subprocess()
    run.assert_outcomes(passed=1, errors=1)
    run.stdout.fnmatch_lines(
        ["*threads this test started are still alive: ThreadPoolExecutor-*. Shut down*"]
    )


def test_a_pool_shut_down_in_the_test_passes(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(GUARDED)
    pytester.makepyfile(
        """
        from concurrent.futures import ThreadPoolExecutor

        def test_shuts_its_pool_down():
            with ThreadPoolExecutor() as pool:
                pool.submit(print).result()
        """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
