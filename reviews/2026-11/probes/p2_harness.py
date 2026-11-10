# Shared harness for the p2_* probes: replay a recorded history and collect what the replay rebuilds, beside what the history recorded.
"""Not a probe itself. A replay that raises nothing proves little: update handlers and queries
replay with no command check, and Temporal compares a scheduled activity by its type and ID only.
So this harness records, during a replay, everything the workflow code hands to Temporal (each
activity's input and timeouts, each child's start, each signal, each timer, each update's answer,
the result or the next run's start), and reads the same out of the history's events, both as the
exact JSON text Ventoux's converter writes. `compare` then says where they differ.

Reaches past the supported names for: Temporal's SDK internals (`_WorkflowInstanceImpl`, to see
timers and to read a workflow's state at the end of a replay), `ventoux.temporal.converter`
(`ExactJSON`), `ventoux.temporal.sandbox`, and the repository's own test helpers.
"""

import asyncio
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import os  # noqa: E402

# The tree whose code and tests are used: this repository's, unless a probe that travels in time
# points at an older checkout (p2_time_travel.py).
ROOT = Path(os.environ.get("P2_ROOT") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(ROOT / "tests"))

from temporalio import workflow  # noqa: E402
from temporalio.api.enums.v1 import EventType  # noqa: E402
from temporalio.client import WorkflowHistory  # noqa: E402
from temporalio.converter import DataConverter, WorkflowSerializationContext  # noqa: E402
from temporalio.worker import (  # noqa: E402
    Interceptor,
    Replayer,
    WorkflowInboundInterceptor,
    WorkflowOutboundInterceptor,
)
from temporalio.worker import _workflow_instance as sdk_instance  # noqa: E402
from ventoux.temporal.converter import ExactJSON  # noqa: E402

try:
    from worker_threads import worker_threads  # noqa: E402  (the tests' helper)
except ImportError:  # an older tree, before the helper: a pool of the probe's own, shut down after
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def worker_threads() -> Any:  # type: ignore[no-redef]
        pool = ThreadPoolExecutor()
        try:
            yield pool
        finally:
            pool.shutdown(wait=False)

try:
    from ventoux.temporal.sandbox import SANDBOX  # noqa: E402
except ImportError:  # an older tree, where the runner was the worker module's
    from ventoux.temporal.worker import SANDBOX  # type: ignore[no-redef,attr-defined]  # noqa: E402

# What the replay under way has seen: filled by the interceptors, emptied by `replayed`.
SEEN: dict[str, Any] = {}


def written(values: Any) -> list[tuple[str, tuple[str, ...]]]:
    """Each value as the converter writes it: its JSON text, and its sensitive parts."""
    out = []
    for value in values:
        payload = ExactJSON().to_payload(value)
        assert payload is not None
        parts = tuple(
            payload.metadata[name].decode()
            for name in sorted(payload.metadata)
            if name.startswith("sensitive/")
        )
        out.append((payload.data.decode(), parts))
    return out


def seconds(value: Any) -> float | None:
    return None if value is None else value.total_seconds()


class Outbound(WorkflowOutboundInterceptor):
    def continue_as_new(self, input: Any) -> Any:
        SEEN["end"] = ("continued", written(input.args))
        return super().continue_as_new(input)

    def start_activity(self, input: Any) -> Any:
        policy = input.retry_policy
        SEEN["activities"].append(
            {
                "type": input.activity,
                "input": written(input.args),
                "start_to_close": seconds(input.start_to_close_timeout),
                "schedule_to_close": seconds(input.schedule_to_close_timeout),
                "heartbeat": seconds(input.heartbeat_timeout),
                "queue": input.task_queue,
                "attempts": None if policy is None else policy.maximum_attempts,
                "first_wait": None if policy is None else seconds(policy.initial_interval),
                "longest_wait": None if policy is None else seconds(policy.maximum_interval),
                "never_retried": None
                if policy is None
                else sorted(policy.non_retryable_error_types or ()),
            }
        )
        return super().start_activity(input)

    async def start_child_workflow(self, input: Any) -> Any:
        SEEN["children"].append(
            {
                "type": input.workflow,
                "id": input.id,
                "input": written(input.args),
                "queue": input.task_queue,
                "parent_close": int(input.parent_close_policy),
            }
        )
        return await super().start_child_workflow(input)

    async def signal_child_workflow(self, input: Any) -> None:
        SEEN["signals"].append(
            {"to": input.child_workflow_id, "name": input.signal, "input": written(input.args)}
        )
        return await super().signal_child_workflow(input)

    async def signal_external_workflow(self, input: Any) -> None:
        SEEN["signals"].append(
            {"to": input.workflow_id, "name": input.signal, "input": written(input.args)}
        )
        return await super().signal_external_workflow(input)


class Inbound(WorkflowInboundInterceptor):
    def init(self, outbound: WorkflowOutboundInterceptor) -> None:
        super().init(Outbound(outbound))

    async def execute_workflow(self, input: Any) -> Any:
        try:
            result = await super().execute_workflow(input)
        except workflow.ContinueAsNewError:
            raise
        except BaseException as error:
            SEEN.setdefault("end", ("raised", f"{type(error).__name__}: {error}"))
            raise
        SEEN["end"] = ("completed", written([result]))
        return result

    def handle_update_validator(self, input: Any) -> None:
        try:
            super().handle_update_validator(input)
        except BaseException as error:
            SEEN["updates"][input.id] = ("rejected", input.update, str(error))
            raise

    async def handle_update_handler(self, input: Any) -> Any:
        try:
            result = await super().handle_update_handler(input)
        except BaseException as error:
            SEEN["updates"][input.id] = ("failed", input.update, f"{type(error).__name__}: {error}")
            raise
        SEEN["updates"][input.id] = ("completed", input.update, written([result]))
        return result


class Watching(Interceptor):
    def workflow_interceptor_class(self, input: Any) -> Any:
        return Inbound


_timer = sdk_instance._WorkflowInstanceImpl._timer_impl
_activate = sdk_instance._WorkflowInstanceImpl.activate


def _watched_timer(self: Any, delay: float, *args: Any, **kwargs: Any) -> Any:
    handle = _timer(self, delay, *args, **kwargs)
    if "timers" in SEEN:
        SEEN["timers"][str(self._curr_seqs["timer"])] = round(delay, 3)
    return handle


def _watched_activate(self: Any, act: Any) -> Any:
    done = _activate(self, act)
    try:  # never let the watching break the replay it watches
        if "state" in SEEN:
            SEEN["patches"] = dict(getattr(self, "_patches_memoized", {}))
            thing = getattr(self, "_object", None)
            for name in ("report", "view", "current"):
                method = getattr(thing, name, None)
                code = getattr(getattr(method, "__func__", None), "__code__", None)
                if code is not None and code.co_argcount == 1:
                    try:
                        SEEN["state"] = written([method()])[0]
                    except Exception as error:  # noqa: BLE001 (a state it can't read is said)
                        SEEN["state"] = (f"unread: {type(error).__name__}: {error}", ())
                    break
            # The whole state as it would cross continue-as-new, for a case: every field of it.
            switch = getattr(type(thing), "switch", None)
            as_data = getattr(switch, "__globals__", {}).get("state_as_data")
            if as_data is not None and getattr(thing, "case", None) is not None:
                try:
                    SEEN["carried"] = written([as_data(thing.state)])[0]
                except Exception as error:  # noqa: BLE001
                    SEEN["carried"] = (f"unread: {type(error).__name__}: {error}", ())
    except Exception as error:  # noqa: BLE001
        SEEN["state"] = (f"unread: {type(error).__name__}: {error}", ())
    return done


sdk_instance._WorkflowInstanceImpl._timer_impl = _watched_timer  # type: ignore[method-assign]
sdk_instance._WorkflowInstanceImpl.activate = _watched_activate  # type: ignore[method-assign]


async def replayed(
    history: WorkflowHistory, workflows: list[type], converter: DataConverter
) -> dict[str, Any]:
    """Replay `history`; what the workflow code did during it, and the replay's failure if any."""
    SEEN.clear()
    SEEN.update(activities=[], children=[], signals=[], timers={}, updates={}, state=None, carried=None)
    async with worker_threads() as threads:
        replayer = Replayer(
            workflows=workflows,
            data_converter=converter,
            workflow_runner=SANDBOX,
            workflow_task_executor=threads,
            interceptors=[Watching()],
        )
        result = await replayer.replay_workflow(history, raise_on_replay_failure=False)
    seen = dict(SEEN)
    SEEN.clear()
    failure = result.replay_failure
    seen["failure"] = None if failure is None else f"{type(failure).__name__}: {failure}"[:300]
    return seen


async def recorded(history: WorkflowHistory, converter: DataConverter) -> dict[str, Any]:
    """The same things, read from the history's events."""
    codec = converter.payload_codec
    if codec is not None and hasattr(codec, "with_context"):
        codec = codec.with_context(
            WorkflowSerializationContext(namespace="ReplayNamespace", workflow_id=history.workflow_id)
        )

    async def texts(payloads: Any) -> list[tuple[str, tuple[str, ...]]]:
        given = list(payloads.payloads) if hasattr(payloads, "payloads") else list(payloads)
        opened = given if codec is None else await codec.decode(given)
        return [
            (
                each.data.decode(),
                tuple(
                    each.metadata[name].decode()
                    for name in sorted(each.metadata)
                    if name.startswith("sensitive/")
                ),
            )
            for each in opened
        ]

    out: dict[str, Any] = dict(
        activities=[], children=[], signals=[], timers={}, updates={}, end=None, markers=[],
        events=len(history.events), accepted={},
    )
    for event in history.events:
        kind = EventType.Name(event.event_type).removeprefix("EVENT_TYPE_")
        if kind == "ACTIVITY_TASK_SCHEDULED":
            a = event.activity_task_scheduled_event_attributes
            policy = a.retry_policy
            out["activities"].append(
                {
                    "id": a.activity_id,
                    "type": a.activity_type.name,
                    "input": await texts(a.input),
                    "start_to_close": a.start_to_close_timeout.ToTimedelta().total_seconds(),
                    "schedule_to_close": a.schedule_to_close_timeout.ToTimedelta().total_seconds(),
                    "heartbeat": a.heartbeat_timeout.ToTimedelta().total_seconds(),
                    "queue": a.task_queue.name,
                    "attempts": policy.maximum_attempts,
                    "first_wait": policy.initial_interval.ToTimedelta().total_seconds(),
                    "longest_wait": policy.maximum_interval.ToTimedelta().total_seconds(),
                    "never_retried": sorted(policy.non_retryable_error_types),
                }
            )
        elif kind == "START_CHILD_WORKFLOW_EXECUTION_INITIATED":
            a = event.start_child_workflow_execution_initiated_event_attributes
            out["children"].append(
                {
                    "type": a.workflow_type.name,
                    "id": a.workflow_id,
                    "input": await texts(a.input),
                    "queue": a.task_queue.name,
                    "parent_close": int(a.parent_close_policy),
                }
            )
        elif kind == "SIGNAL_EXTERNAL_WORKFLOW_EXECUTION_INITIATED":
            a = event.signal_external_workflow_execution_initiated_event_attributes
            out["signals"].append(
                {
                    "to": a.workflow_execution.workflow_id,
                    "name": a.signal_name,
                    "input": await texts(a.input),
                }
            )
        elif kind == "TIMER_STARTED":
            a = event.timer_started_event_attributes
            out["timers"][a.timer_id] = round(a.start_to_fire_timeout.ToTimedelta().total_seconds(), 3)
        elif kind == "MARKER_RECORDED":
            a = event.marker_recorded_event_attributes
            name = a.marker_name
            for payloads in a.details.values():  # Temporal: a patch marker's details name it
                for text, _ in await texts(payloads):
                    if text.startswith("{") and '"id"' in text:
                        name = json.loads(text)["id"]
            out["markers"].append(name)
        elif kind == "WORKFLOW_EXECUTION_UPDATE_ACCEPTED":
            a = event.workflow_execution_update_accepted_event_attributes
            out["accepted"][a.accepted_request.meta.update_id] = a.accepted_request.input.name
        elif kind == "WORKFLOW_EXECUTION_UPDATE_COMPLETED":
            a = event.workflow_execution_update_completed_event_attributes
            name = out["accepted"].get(a.meta.update_id, "?")
            if a.outcome.HasField("success"):
                out["updates"][a.meta.update_id] = ("completed", name, await texts(a.outcome.success))
            else:
                out["updates"][a.meta.update_id] = ("failed", name, a.outcome.failure.message)
        elif kind == "WORKFLOW_EXECUTION_COMPLETED":
            a = event.workflow_execution_completed_event_attributes
            out["end"] = ("completed", await texts(a.result))
        elif kind == "WORKFLOW_EXECUTION_CONTINUED_AS_NEW":
            a = event.workflow_execution_continued_as_new_event_attributes
            out["end"] = ("continued", await texts(a.input))
        elif kind == "WORKFLOW_EXECUTION_FAILED":
            out["end"] = ("raised", event.workflow_execution_failed_event_attributes.failure.message)
        elif kind in ("WORKFLOW_EXECUTION_CANCELED", "WORKFLOW_EXECUTION_TERMINATED"):
            out["end"] = (kind.lower(), None)
    return out


def deep(old: Any, new: Any, path: str, changed: list[str], added: list[str]) -> None:
    """Where two JSON values differ: `changed` for a value the record holds and the replay gives
    otherwise (or not at all), `added` for what only the replay holds (a field added since)."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in old:
            if key not in new:
                changed.append(f"{path}.{key}: recorded {short(old[key], 200)} | replay has none")
            else:
                deep(old[key], new[key], f"{path}.{key}", changed, added)
        for key in new:
            if key not in old:
                added.append(f"{path}.{key}={short(new[key], 60)}")
        shared_old = [key for key in old if key in new]
        shared_new = [key for key in new if key in old]
        if shared_old != shared_new:
            changed.append(f"{path}: keys in another order: recorded {shared_old} | replay {shared_new}")
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            changed.append(f"{path}: {len(old)} items recorded, {len(new)} on replay")
        for n, (a, b) in enumerate(zip(old, new, strict=False)):
            if a != b and not isinstance(a, dict | list):
                changed.append(f"{path}[{n}]: recorded {short(a, 300)!r} | replay {short(b, 300)!r}")
            else:
                deep(a, b, f"{path}[{n}]", changed, added)
    elif old != new or type(old) is not type(new):
        changed.append(f"{path}: recorded {short(old, 300)!r} | replay {short(new, 300)!r}")


def texts_differ(old: Any, new: Any, path: str, changed: list[str], added: list[str]) -> None:
    """Compare two lists of written values (text, sensitive parts): exactly, then as JSON."""
    import json
    from decimal import Decimal

    if old == new:
        return
    if not isinstance(old, list) or not isinstance(new, list) or len(old) != len(new):
        changed.append(f"{path}: recorded {short(old)} | replay {short(new)}")
        return
    for n, ((a, a_parts), (b, b_parts)) in enumerate(zip(old, new, strict=True)):
        if a == b and a_parts == b_parts:
            continue
        before = len(changed) + len(added)
        try:
            deep(json.loads(a, parse_float=Decimal), json.loads(b, parse_float=Decimal),
                 f"{path}[{n}]", changed, added)
        except ValueError:
            changed.append(f"{path}[{n}]: recorded {short(a)} | replay {short(b)}")
        grew = len(changed) + len(added) > before and not any(
            line.startswith(f"{path}[{n}]") for line in changed[-(len(changed)):] if False
        )
        if a_parts != b_parts and len(added) > 0 and len(a_parts) < len(b_parts) and grew:
            added.append(f"{path}[{n}]: a sensitive part in a field added since")
        elif a_parts != b_parts:
            changed.append(f"{path}[{n}] sensitive parts: recorded {a_parts} | replay {b_parts}")
        if before == len(changed) + len(added):
            changed.append(f"{path}[{n}]: same JSON value, another text: {difference(a, b)}")


def compare(was: dict[str, Any], now: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Where the replay differs from the record: what changed in something the record holds;
    what the replay adds that the record never held (fields added since); and what Temporal
    doesn't check and the code now asks for otherwise (timeouts, retry policies)."""
    said: list[str] = []
    added: list[str] = []
    options: list[str] = []
    for kind, checked in (
        ("activities", ("type", "input", "queue")),
        ("children", ("type", "id", "input", "queue", "parent_close")),
        ("signals", ("to", "name", "input")),
    ):
        if len(was[kind]) != len(now[kind]):
            said.append(f"{kind}: {len(was[kind])} recorded, {len(now[kind])} on replay")
        for n, (old, new) in enumerate(zip(was[kind], now[kind], strict=False)):
            label = f"{kind}[{n}] {old.get('type', old.get('name'))}"
            for field in checked:
                if field == "queue" and new[field] is None:
                    continue  # the workflow's own queue: Temporal fills it in
                if field == "input":
                    texts_differ(old[field], new[field], f"{label} input", said, added)
                elif old[field] != new[field]:
                    said.append(f"{label} {field}: recorded {old[field]} | replay {new[field]}")
            if kind == "activities":
                for field in ("start_to_close", "attempts", "first_wait", "longest_wait", "never_retried"):
                    if new[field] is not None and old[field] != new[field]:
                        options.append(f"{label} {field}: recorded {old[field]} | replay {new[field]}")
    for timer, delay in was["timers"].items():
        if timer not in now["timers"]:
            said.append(f"timer {timer}: recorded, not started on replay")
        elif abs(now["timers"][timer] - delay) > 0.002:
            said.append(f"timer {timer}: recorded {delay}s | replay {now['timers'][timer]}s")
    for update, outcome in was["updates"].items():
        got = now["updates"].get(update)
        if got is None or got[:2] != outcome[:2] or isinstance(outcome[2], str):
            if got != outcome:
                said.append(f"update {outcome[1]} {update[:8]}: recorded {short(outcome)} | replay {short(got)}")
        else:
            texts_differ(outcome[2], got[2], f"update {outcome[1]} {update[:8]}", said, added)
    if was["end"] is not None and was["end"][0] in ("completed", "continued"):
        got = now.get("end")
        if got is None or got[0] != was["end"][0]:
            said.append(f"end: recorded {short(was['end'])} | replay {short(got)}")
        else:
            texts_differ(was["end"][1], got[1], f"end ({got[0]})", said, added)
    return said, added, options


def short(value: Any, limit: int = 600) -> str:
    text = str(value)
    return text if len(text) <= limit else first_difference_free(text, limit)


def first_difference_free(text: str, limit: int) -> str:
    return text[:limit] + f"... ({len(text)} chars)"


def difference(old: str, new: str, around: int = 140) -> str:
    """The first place two texts differ, with some of each around it."""
    at = next((n for n, (a, b) in enumerate(zip(old, new, strict=False)) if a != b), min(len(old), len(new)))
    start = max(0, at - around // 2)
    return f"at char {at}: recorded ...{old[start:at + around]}... | replay ...{new[start:at + around]}..."


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


__all__ = ["ROOT", "compare", "dataclasses", "difference", "recorded", "replayed", "run", "short"]
