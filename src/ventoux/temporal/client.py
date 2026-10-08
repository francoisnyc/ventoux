"""Starting a plan run, answering its waits, and reading how it went (layer 6)."""

from collections.abc import Mapping
from typing import Any

from temporalio.client import Client, WorkflowHandle

from ventoux.core.provenance import Sourced
from ventoux.temporal.converter import require_exact_numbers
from ventoux.temporal.workflow import Given, PlanStart, PlanWorkflow, RunReport, Sent


async def start_plan(
    client: Client,
    workflow: type[PlanWorkflow],
    plan: dict[str, Any],
    fields: Mapping[str, Sourced],
    id: str,
    task_queue: str,
) -> WorkflowHandle[PlanWorkflow, RunReport]:
    """Start `plan` as a run of `workflow`, with `fields`; `id` names the run (`refund-A-1001`)."""
    require_exact_numbers(client)
    start = PlanStart(
        plan, {name: Given(given.value, sorted(given.sources)) for name, given in fields.items()}
    )
    return await client.start_workflow(workflow.run, start, id=id, task_queue=task_queue)


async def answer(
    run: WorkflowHandle[PlanWorkflow, RunReport], wait: str, outcome: str, by: str
) -> None:
    """Answer the wait `wait` (`approve_refund#1`, as `report` shows it) with `outcome`, as the
    person `by`. An answer to a wait that isn't open is refused, and recorded."""
    await run.signal(PlanWorkflow.answer, Sent(wait, outcome, by))


async def report(run: WorkflowHandle[PlanWorkflow, RunReport]) -> RunReport:
    """How the run is going: its history so far, and `waiting_at` the wait open for an answer."""
    return await run.query(PlanWorkflow.report)
