# Shared harness for the p1c_* probes: a case worker on Temporal's time-skipping test server, and the raw bytes of every history.
"""Not a probe itself. Reaches past the supported names for: the repository's own test harness
(`tests/skipping_server.py`, `tests/worker_threads.py`), and `ventoux.testing`'s development
catalog, workflows, converter and audit store (shipped for teams' tests, not in public.json)."""

import asyncio
import sys
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))

from skipping_server import time_skipping  # noqa: E402  (the tests' harness)
from temporalio.api.history.v1 import History  # noqa: E402
from temporalio.client import Client  # noqa: E402
from worker_threads import worker_threads  # noqa: E402  (the tests' harness)

from p1c_workflows import ImpatientCases, SwitchingCases  # noqa: E402, F401

from ventoux.temporal.cases import CaseReport, CaseWorkflow, report  # noqa: E402
from ventoux.temporal.worker import case_worker  # noqa: E402

from ventoux.temporal.converter import data_converter  # noqa: E402
from ventoux.testing import (  # noqa: E402
    FAKES,
    DevelopmentCases,
    DevelopmentForget,
    DevelopmentPlans,
)
from ventoux.tooling.audit import FileAudit  # noqa: E402
from ventoux.tooling.keys import FileKeys  # noqa: E402

QUEUE = "cases"


class Setup:
    """What a scenario is given: the client, its keys file, its audit store."""

    def __init__(self, client: Client, keys: FileKeys, audit: Any, environment: Any) -> None:
        self.client = client
        self.keys = keys
        self.audit = audit
        self.environment = environment


def on_temporal[T](
    scenario: Callable[[Setup], Awaitable[T]],
    cases: type[CaseWorkflow] = DevelopmentCases,
    activities: Mapping[str, Any] = FAKES,
    audit: Any = None,
    timeout: float = 90,
) -> T:
    """Run `scenario` against the time-skipping test server with a case worker (and the
    development forget workflow) on `QUEUE`."""

    async def go() -> T:
        folder = Path(tempfile.mkdtemp(prefix="p1c-"))
        keys = FileKeys(folder / "keys.json")
        store = audit if audit is not None else FileAudit(folder / "audit")
        async with (
            time_skipping(data_converter(keys)) as environment,
            worker_threads() as threads,
            case_worker(
                environment.client,
                QUEUE,
                cases,
                DevelopmentPlans,
                activities,
                forget=DevelopmentForget,
                activity_executor=threads,
                audit=store,
            ),
        ):
            setup = Setup(environment.client, keys, store, environment)
            return await asyncio.wait_for(scenario(setup), timeout=timeout)

    return asyncio.run(go())


async def until(case: Any, holds: Callable[[CaseReport], bool], tries: int = 400) -> CaseReport:
    """The case's report once `holds` is true of it; fails after a bounded number of asks."""
    now = None
    for _ in range(tries):
        try:
            now = await asyncio.wait_for(report(case), timeout=5)
        except TimeoutError:
            continue
        if holds(now):
            return now
        await asyncio.sleep(0.05)
    raise AssertionError(f"the case never got there; last report: {now}")


async def raw_histories(client: Client, id: str) -> dict[str, bytes]:
    """Every run of the workflow `id`, as Temporal stores it (raw bytes, payloads still encoded)
    followed by its JSON export, by `<id> run <n>`. Runs are found from the latest back, each
    start naming the run it continued: the test server sometimes gives an ended run's history
    without its last events, so the chain can't always be followed forward."""
    info = (await client.get_workflow_handle(id).describe()).raw_description.workflow_execution_info
    run_id = info.execution.run_id
    runs: list[bytes] = []
    while run_id:
        history = await client.get_workflow_handle(id, run_id=run_id).fetch_history()
        runs.insert(0, History(events=history.events).SerializeToString() + history.to_json().encode())
        started = history.events[0].workflow_execution_started_event_attributes
        run_id = started.continued_execution_run_id
    return {f"{id} run {n}": raw for n, raw in enumerate(runs, start=1)}


def where(planted: Mapping[str, str], blobs: Mapping[str, bytes]) -> list[str]:
    """Each planted value found in clear in a blob: `<what> in <where>`."""
    return [
        f"{what} in {place}"
        for what, value in planted.items()
        for place, blob in blobs.items()
        if value.encode() in blob
    ]


def files_under(folder: Path) -> dict[str, bytes]:
    """Every file under `folder`, by its relative path."""
    return {
        str(path.relative_to(folder)): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }
