# Shared pytest plugin for p2_old_recordings.py: while an older checkout's own Temporal tests run, keeps every workflow history they produce, with the workflow class and the key file each needs to replay.
"""Not a probe itself. Loaded with `-p p2_capture_plugin` in a pytest run of an OLDER tree. It
watches Temporal's SDK only (a client's `start_workflow`, a worker's start and stop), never
Ventoux, so the same plugin works on any commit. As each worker stops, it fetches the history of
every workflow the test started, of each earlier run it continued from, and of each child, and
writes them under P2_CAPTURE_DIR. A capture that fails is skipped: it never fails the test."""

import json
import os
import shutil
from pathlib import Path
from typing import Any

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker

OUT = Path(os.environ["P2_CAPTURE_DIR"])
STARTED: list[str] = []  # workflow IDs started by a client, in this process
CLASSES: dict[tuple[str, str], tuple[str, str]] = {}  # (queue, workflow type) -> (module, class)
SAVED: dict[str, int] = {}  # run ID -> events saved

_start = Client.start_workflow
_init = Worker.__init__
_exit = Worker.__aexit__


async def start_workflow(self: Client, *args: Any, **kwargs: Any) -> Any:
    if "id" in kwargs:
        STARTED.append(kwargs["id"])
    return await _start(self, *args, **kwargs)


def init(self: Worker, client: Client, *args: Any, **kwargs: Any) -> None:
    _init(self, client, *args, **kwargs)
    try:
        self._p2_client = client  # type: ignore[attr-defined]
        for each in kwargs.get("workflows", ()):
            defn = workflow._Definition.from_class(each)
            if defn is not None and defn.name:
                CLASSES[(kwargs.get("task_queue", ""), defn.name)] = (each.__module__, each.__qualname__)
    except Exception:  # noqa: BLE001
        pass


async def aexit(self: Worker, *args: Any) -> Any:
    try:
        await capture(self._p2_client)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return await _exit(self, *args)


async def capture(client: Client) -> None:
    test = os.environ.get("PYTEST_CURRENT_TEST", "?").split(" ")[0]
    codec = client.data_converter.payload_codec
    keys = getattr(getattr(codec, "keys", None), "path", None)
    todo = [(id, None) for id in dict.fromkeys(STARTED)]
    seen: set[tuple[str, str | None]] = set()
    while todo:
        id, run = todo.pop()
        if (id, run) in seen:
            continue
        seen.add((id, run))
        try:
            history = await client.get_workflow_handle(id, run_id=run).fetch_history()
        except Exception:  # noqa: BLE001
            continue
        if not history.events:
            continue
        first = history.events[0].workflow_execution_started_event_attributes
        this_run = first.original_execution_run_id or run or "?"
        if first.continued_execution_run_id:
            todo.append((id, first.continued_execution_run_id))
        for event in history.events:
            if event.HasField("start_child_workflow_execution_initiated_event_attributes"):
                todo.append(
                    (event.start_child_workflow_execution_initiated_event_attributes.workflow_id, None)
                )
        if SAVED.get(this_run, 0) >= len(history.events):
            continue
        SAVED[this_run] = len(history.events)
        queue, kind = first.task_queue.name, first.workflow_type.name
        kept = None
        if keys is not None and Path(keys).exists():
            kept = OUT / f"{this_run}.keys.json"
            shutil.copy(keys, kept)
        (OUT / f"{this_run}.json").write_text(
            json.dumps(
                {
                    "test": test,
                    "id": id,
                    "run": this_run,
                    "queue": queue,
                    "type": kind,
                    "class": CLASSES.get((queue, kind)),
                    "keys": None if kept is None else str(kept),
                    "history": history.to_json(),
                }
            )
        )


Client.start_workflow = start_workflow  # type: ignore[method-assign,assignment]
Worker.__init__ = init  # type: ignore[method-assign,assignment]
Worker.__aexit__ = aexit  # type: ignore[method-assign,assignment]


def pytest_runtest_setup(item: Any) -> None:
    STARTED.clear()
    CLASSES.clear()
