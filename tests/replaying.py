"""Replaying a history in a test, on threads the test owns and shuts down (fix-replayer-threads).

The SDK's `Replayer`, given no `workflow_task_executor`, makes a thread pool of its own that it
never shuts down (its docstring, 1.34.0): its threads end only when the garbage collector reclaims
it, at some later test. So whoever makes the replayer gives it one, and shuts it down once the
replay is done, off the event loop and within a bound, as a worker's activity threads are
(fix-worker-executors, choices 1 and 5): the same helper does both.
"""

from collections.abc import Sequence

from temporalio.client import WorkflowHistory
from temporalio.converter import DataConverter
from temporalio.worker import Replayer
from worker_threads import worker_threads

from ventoux.temporal.sandbox import SANDBOX


async def replay_history(
    history: WorkflowHistory, workflows: Sequence[type], converter: DataConverter
) -> None:
    """Replay `history` against `workflows`, as a worker would after a restart, with the converter
    that recorded it. A replay that fails raises; its threads are shut down either way."""
    async with worker_threads() as threads:
        replayer = Replayer(
            workflows=workflows,
            data_converter=converter,
            workflow_runner=SANDBOX,
            workflow_task_executor=threads,  # the replayer's workflow tasks run on these
        )
        await replayer.replay_workflow(history)
