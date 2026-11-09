"""Does the time-skipping test server keep its clock held after these? Run with
`uv run python scripts/clock_held.py`, against the server the installed `temporalio` bundles.

Outside the test suite: it checks the server, not Ventoux (docs/layers/fix-child-switch-clock.md).
Each case runs a plain workflow on a fresh test server, then asks it to skip an hour within 8
seconds: "moves" if it does, "HELD" if the clock never moves. Each reproduction has a control
that must move. Exit 0 if every case moves, 1 if a reproduction holds the clock, 2 if a control
does (the check itself is broken).
"""

import asyncio
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path

from temporalio import workflow
from temporalio.client import Client
from temporalio.converter import DataConverter
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from temporalio.workflow import ParentClosePolicy

sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from skipping_server import time_skipping  # the tests' harness, found by the path above

QUEUE = "clock"


@workflow.defn(sandboxed=False)
class Waiting:
    """Waits for ever; with `hold`, its first workflow task holds the worker 1.5 s first."""

    @workflow.run
    async def run(self, hold: bool) -> None:
        if hold:
            # Real time, blocking on purpose: the task is in flight while the client terminates it.
            time.sleep(1.5)  # noqa: ASYNC251
        await workflow.wait_condition(lambda: False)


@workflow.defn(sandboxed=False)
class Child:
    @workflow.run
    async def run(self) -> None:
        await workflow.wait_condition(lambda: False)


@workflow.defn(sandboxed=False)
class Parent:
    """Starts an abandoned child, then continues as new: with `await_start`, once the child's
    start is recorded; else with it still pending."""

    @workflow.run
    async def run(self, run: int, await_start: bool) -> None:
        if run == 0:
            start = workflow.start_child_workflow(
                Child.run,
                id=f"{workflow.info().workflow_id}/child",
                parent_close_policy=ParentClosePolicy.ABANDON,
            )
            if await_start:
                await start
            else:
                asyncio.ensure_future(start)
                await asyncio.sleep(0)  # the start command is issued, not awaited
            workflow.continue_as_new(args=[1, await_start])
        await workflow.wait_condition(lambda: False)


async def terminated(client: Client, in_flight: bool) -> None:
    """A workflow terminated with its first workflow task in flight, or once it is idle."""
    handle = await client.start_workflow(
        Waiting.run, in_flight, id=f"w-{uuid.uuid4().hex[:8]}", task_queue=QUEUE
    )
    await asyncio.sleep(0.5 if in_flight else 2.5)
    await handle.terminate("from outside")


async def switched(client: Client, await_start: bool) -> None:
    """A run that continues as new with its child's start pending, or once it is recorded."""
    await client.start_workflow(
        Parent.run, args=[0, await_start], id=f"p-{uuid.uuid4().hex[:8]}", task_queue=QUEUE
    )
    await asyncio.sleep(2)


async def clock_moves(case: Callable[[Client], Awaitable[None]]) -> bool:
    """Whether the server skips an hour within 8 seconds after `case`."""
    async with (
        time_skipping(DataConverter.default) as environment,
        Worker(
            environment.client,
            task_queue=QUEUE,
            workflows=[Waiting, Parent, Child],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ),
    ):
        await case(environment.client)
        try:
            await asyncio.wait_for(environment.sleep(timedelta(hours=1)), timeout=8)
        except TimeoutError:
            return False
        return True


CASES: list[tuple[str, bool, Callable[[Client], Awaitable[None]]]] = [
    # (what, a control, the case): a control must move; a reproduction holds the clock if the
    # server has the fault.
    ("terminated idle", True, lambda c: terminated(c, in_flight=False)),
    ("terminated with a workflow task in flight", False, lambda c: terminated(c, in_flight=True)),
    ("continued as new once its child started", True, lambda c: switched(c, await_start=True)),
    ("continued as new with a child's start pending", False, lambda c: switched(c, False)),
]


def main() -> int:
    held_reproduction = held_control = False
    for what, control, case in CASES:
        moves = asyncio.run(clock_moves(case))
        kind = "control" if control else "reproduction"
        print(f"{'moves' if moves else 'HELD '}  {what} ({kind})")
        held_control |= control and not moves
        held_reproduction |= not control and not moves
    return 2 if held_control else 1 if held_reproduction else 0


if __name__ == "__main__":
    sys.exit(main())
