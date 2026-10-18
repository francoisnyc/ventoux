"""The contract test: a bound workflow, run on Temporal's test server, against its contract
(brief, D6). See docs/guides/activities.md, "The contract test".

A contract is a promise, not a proof: this checks the shape of what the workflow gives, never
whether a declared source is true, which is for review. A cancellable contract's promise is
checked in its history, once it has been asked to cancel (brief, D40).
"""

import asyncio
import uuid
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import HistoryEvent
from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
    WorkflowFailureError,
)
from temporalio.exceptions import FailureError
from temporalio.exceptions import TimeoutError as TemporalTimeout  # not Python's own TimeoutError
from temporalio.service import RPCError

from ventoux.core.before_activity import one_line
from ventoux.core.workflow_contract import WorkflowContract
from ventoux.temporal.bindings import Binding
from ventoux.temporal.codec import SensitiveCodec


async def check_workflow_contract(
    client: Client, contract: WorkflowContract, binding: Binding, input: dict[str, Any]
) -> list[str]:
    """Every way the bound workflow breaks its contract's promise, run with `input`; none if it
    keeps it. `input` must be one the contract accepts: the test checks the workflow, not you."""
    # Pydantic: `model_validate` checks a dict against the model's fields, or raises.
    contract.input.model_validate(input)
    run = test_run(client, contract)
    try:
        # Temporal: waiting on the result lets the time-skipping test server skip to the timeout.
        output: dict[str, Any] = await client.execute_workflow(
            binding.workflow,
            input,
            id=run,
            task_queue=binding.task_queue,
            execution_timeout=timedelta(seconds=contract.timeout),
            result_type=dict,
        )
    except WorkflowFailureError as error:
        if isinstance(error.cause, TemporalTimeout):
            # A workflow step is automated: a workflow that waits, for a person or anything else,
            # breaks the promise (brief, D6).
            waited = (
                f"{contract.reference} didn't finish within its timeout of {contract.timeout}s: "
                "a workflow step must not wait for people"
            )
            return [waited]
        said = error.cause.message if isinstance(error.cause, FailureError) else str(error)
        return [f"{contract.reference} failed: {said}"]
    problems = output_problems(contract, output)
    if contract.cancellable:
        problems += await cancellation_problems(client, contract, binding, input)
    return problems


def test_run(client: Client, contract: WorkflowContract) -> str:
    """A new workflow ID for one run of the test, never a case's."""
    run = f"contract-test-{contract.reference}-{uuid.uuid4()}"
    codec = client.data_converter.payload_codec
    if isinstance(codec, SensitiveCodec):
        # A client sealing with Ventoux's codec seals the run's failures too: the run needs its
        # key, as every run Ventoux starts has one; and no `/` in its ID (brief, D31).
        codec.keys.create(run)
    return run


# What a workflow starts, by the event that records it, and the events that end each, by the
# attribute naming the event that started it (Temporal's history).
STARTS = {
    EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED: "an activity",
    EventType.EVENT_TYPE_TIMER_STARTED: "a timer",
    EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED: "a child workflow",
}
ENDS = {
    EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED: "activity_task_completed",
    EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED: "activity_task_failed",
    EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT: "activity_task_timed_out",
    EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED: "activity_task_canceled",
    EventType.EVENT_TYPE_TIMER_FIRED: "timer_fired",
    EventType.EVENT_TYPE_TIMER_CANCELED: "timer_canceled",
    EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_FAILED: (
        "start_child_workflow_execution_failed"
    ),
    EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_COMPLETED: "child_workflow_execution_completed",
    EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_FAILED: "child_workflow_execution_failed",
    EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_CANCELED: "child_workflow_execution_canceled",
    EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_TIMED_OUT: "child_workflow_execution_timed_out",
    EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_TERMINATED: (
        "child_workflow_execution_terminated"
    ),
}
# The event recording that the run was asked to cancel.
CANCEL_REQUESTED = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCEL_REQUESTED
# What completing, rather than failing or being cancelled, looks like for what it started.
COMPLETIONS = {
    EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED: "an activity",
    EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_COMPLETED: "a child workflow",
}


async def cancellation_problems(
    client: Client, contract: WorkflowContract, binding: Binding, input: dict[str, Any]
) -> list[str]:
    """Every part of a cancellable contract's promise its workflow breaks, read from the history
    of a second run, asked to cancel once it has started (brief, D40)."""
    run = test_run(client, contract)
    handle = await client.start_workflow(
        binding.workflow,
        input,
        id=run,
        task_queue=binding.task_queue,
        execution_timeout=timedelta(seconds=contract.timeout),
    )
    # Started: its first workflow task has run, so what it starts first is in its history. The
    # time-skipping test server moves time on only while a result is awaited, so it waits here.
    while not any(
        event.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_COMPLETED
        for event in (await handle.fetch_history()).events
    ):
        await asyncio.sleep(0.05)  # real time, for the worker to take its first task
    if (await handle.describe()).status != WorkflowExecutionStatus.RUNNING:
        return [unchecked(contract)]
    try:
        await handle.cancel()
    except RPCError:
        return [unchecked(contract)]  # it ended in between: nothing left to cancel
    try:
        await handle.result()
    except WorkflowFailureError:
        pass  # ended cancelled, or failed: the history says which
    events = list((await handle.fetch_history()).events)
    asked = next((e.event_id for e in events if e.event_type == CANCEL_REQUESTED), None)
    if asked is None:
        return [unchecked(contract)]  # it ended before the request reached it
    return broken_parts(contract, events, asked)


def unchecked(contract: WorkflowContract) -> str:
    """Fail closed: a run that ended before it could be asked to cancel proves nothing."""
    return (
        f"{contract.reference} is cancellable, and ended before its cancellation was requested, "
        "so the promise wasn't checked: give an input that keeps it running"
    )


def broken_parts(contract: WorkflowContract, events: list[HistoryEvent], asked: int) -> list[str]:
    """The parts of the promise the history breaks, after the cancellation `asked` (an event
    ID): it schedules nothing new; it ends only once all it started has ended; it ends
    cancelled only if nothing it started completed after the request."""
    problems = []
    said = f"{contract.reference} is cancellable, and"
    for event in events:
        if event.event_id > asked and event.event_type in STARTS:
            what = STARTS[event.event_type]
            problems.append(f"{said} started {what} after its cancellation was requested")
            break
    started = {e.event_id for e in events if e.event_type in STARTS}
    for event in events:
        if event.event_type in ENDS:
            attributes = getattr(event, f"{ENDS[event.event_type]}_event_attributes")
            for link in ("scheduled_event_id", "started_event_id", "initiated_event_id"):
                started.discard(getattr(attributes, link, 0))
    if started:
        problems.append(f"{said} ended before everything it started had ended")
    last = events[-1].event_type
    if last == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED:
        for event in events:
            if event.event_id > asked and event.event_type in COMPLETIONS:
                what = COMPLETIONS[event.event_type]
                problems.append(f"{said} ended cancelled though {what} completed after the request")
                break
    return problems


def output_problems(contract: WorkflowContract, output: dict[str, Any]) -> list[str]:
    """What is wrong with `output` against the contract: a field missing or of the wrong type, and
    each field it doesn't declare. A case drops an undeclared field; here it means the contract is
    out of date, which its owners should hear (8d, drafting 3)."""
    problems = []
    try:
        contract.output.model_validate(output)
    except ValidationError as error:
        problems.append(
            f"{contract.reference} gave an output its contract doesn't declare: {one_line(error)}"
        )
    problems += [
        f"{contract.reference} gave {name}, which its contract doesn't declare"
        for name in output
        if name not in contract.output.model_fields
    ]
    return problems
