"""Child cases on Temporal: what a child is started with, what it returns, and the activity its
parent reads its end through (layer 18d) (brief, D75).

A child is its own case workflow, `<parent ID>/<entry>`, under its parent's key. Its end reaches
the parent as a doorbell, a signal with the entry only: a signal says nothing of who sent it, so
the parent reads the report itself, from the child's own result, through `read`.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from temporalio import activity
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from ventoux.case.state import CaseEnded, ChildNotEnded
from ventoux.core.provenance import Sourced
from ventoux.temporal.workflow import Given


@dataclass
class ParentStart:
    """What a child case knows of its parent: who opened it, and what it was given with."""

    case: str  # the parent's workflow ID, `claim-7`, which its doorbell rings
    entry: str  # the step run that opened it, `repair#1`
    sources: dict[str, list[str]]  # each opening value's sources, as the parent gave them
    excluded: dict[str, str]  # who approves nothing in it, and why (brief, D25)


@dataclass
class ChildEnding:
    """A closed child's report, as its workflow returns it (brief, D74)."""

    outcome: str  # `done`, or the close reason a person used
    closed_by: str | None  # who chose that reason; None: it closed by itself
    closed: str  # its closed line, without `closed: `
    reached: list[str]  # its milestones, in the order reached
    report: dict[str, Given] = field(default_factory=dict[str, Given])


# How long a doorbell's read waits, in seconds, for the child that rang to end: it rings as its
# last act, then ends in its next workflow task, which a parent quick to read can come before.
SETTLE = 5
PAUSE = 0.1  # seconds between two questions to Temporal while it waits


@dataclass
class ChildAsked:
    """A read of a child: which, and how long to wait for one still running to end."""

    child: str  # the child's workflow ID, `claim-7/repair#1`
    # A doorbell's read waits `SETTLE` for the child that rang to end; a question asked as a run
    # starts, or daily, waits for nothing: an open child is the usual answer (brief, D75).
    settle: int = 0  # in whole seconds: the case's converter carries no float


@dataclass
class ChildRead:
    """What the parent's read found: the child's ending, or how it stands without one."""

    ending: ChildEnding | None
    # `open` while its case is; else how its workflow ended without reporting: `it was
    # terminated`, `it failed`, `it timed out`, `it was cancelled`, `it is gone`. Empty with an
    # ending.
    how: str = ""


def ending_data(ended: CaseEnded) -> ChildEnding:
    """The ending as it crosses Temporal: plain data, each value with its sources."""
    return ChildEnding(
        ended.outcome,
        ended.closed_by,
        ended.closed,
        list(ended.reached),
        {name: Given(given.value, sorted(given.sources)) for name, given in ended.report.items()},
    )


def event_of(entry: str, read: ChildRead, at: int) -> CaseEnded | ChildNotEnded:
    """What the parent decides on, from what its read found (brief, D75)."""
    if read.ending is None:
        return ChildNotEnded(entry, read.how, at=at)
    ending = read.ending
    return CaseEnded(
        entry,
        ending.outcome,
        ending.closed_by,
        ending.closed,
        tuple(ending.reached),
        {
            name: Sourced(given.value, frozenset(given.sources))
            for name, given in ending.report.items()
        },
        at=at,
    )


# How a child's workflow ended without its report, as the parent's line says it.
ENDED_WITHOUT = {
    WorkflowExecutionStatus.TERMINATED: "it was terminated",
    WorkflowExecutionStatus.FAILED: "it failed",
    WorkflowExecutionStatus.TIMED_OUT: "it timed out",
    WorkflowExecutionStatus.CANCELED: "it was cancelled",
}


class ChildActivities:
    """What a case worker runs to read a child case's end, through its own client."""

    def __init__(self, client: Client) -> None:
        self.client = client

    @activity.defn(name="ventoux.child.read")
    async def read(self, asked: ChildAsked) -> ChildRead:
        """How the child workflow stands: its ending, read from its own latest run's result,
        never from a signal; `open` while it runs, once `asked.settle` has passed; or how it
        ended without one. Any other failure is retried, as any outage (brief, D17)."""
        handle = self.client.get_workflow_handle(asked.child)
        waited = 0.0  # seconds
        while True:
            try:
                described = await handle.describe()
            except RPCError as error:
                if error.status != RPCStatusCode.NOT_FOUND:
                    raise
                return ChildRead(None, "it is gone")
            if described.status != WorkflowExecutionStatus.RUNNING:
                break
            if waited >= asked.settle:
                return ChildRead(None, "open")
            await asyncio.sleep(PAUSE)
            waited += PAUSE
        status = described.status
        if status != WorkflowExecutionStatus.COMPLETED:
            how = "it ended otherwise" if status is None else ENDED_WITHOUT.get(status)
            return ChildRead(None, how or "it ended otherwise")
        result: Any = await handle.result(follow_runs=True)
        ending = result.get("ending") if isinstance(result, dict) else result.ending
        if ending is None:
            return ChildRead(None, "it ended without its report")  # fail closed
        if isinstance(ending, dict):
            ending = ChildEnding(
                ending["outcome"],
                ending["closed_by"],
                ending["closed"],
                list(ending["reached"]),
                {name: Given(**given) for name, given in ending["report"].items()},
            )
        return ChildRead(ending)

    def all(self) -> list[Any]:
        return [self.read]
