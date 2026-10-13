"""Starting a plan run, answering its waits, and reading how it went (layer 6)."""

from collections.abc import Mapping, Sequence
from typing import Any

from temporalio.client import Client, WorkflowHandle

from ventoux.core.provenance import Sourced
from ventoux.core.sensitive import Sensitive
from ventoux.temporal.converter import keys_of
from ventoux.temporal.workflow import Given, PlanStart, PlanWorkflow, RunReport, Sent


async def start_plan(
    client: Client,
    workflow: type[PlanWorkflow],
    plan: dict[str, Any],
    fields: Mapping[str, Sourced],
    id: str,
    task_queue: str,
) -> WorkflowHandle[PlanWorkflow, RunReport]:
    """Start `plan` as a run of `workflow`, with `fields`; `id` names the run (`refund-A-1001`).
    The run's key is made first, as a case's is (brief, D31)."""
    keys = keys_of(client)
    # The codec finds a key from the part of a workflow ID before its first `/` (brief, D31).
    if "/" in id:
        raise ValueError(f"{id} can't name a run: a run's ID has no \"/\"")
    keys.create(id)
    start = PlanStart(
        plan, {name: Given(given.value, sorted(given.sources)) for name, given in fields.items()}
    )
    return await client.start_workflow(workflow.run, start, id=id, task_queue=task_queue)


async def answer(
    run: WorkflowHandle[PlanWorkflow, RunReport],
    wait: str,
    outcome: str,
    by: str,
    roles: Sequence[str],
    form: Mapping[str, Any] | None = None,
) -> None:
    """Answer the wait `wait` (`approve_refund#1`, as `report` shows it) with `outcome`, as the
    person `by`, who has `roles`, giving `form` when the outcome sets fields. The caller vouches
    for who `by` is and their roles: only the Ventoux API may send answers (brief, D19). An answer
    the wait doesn't take is refused, and recorded. Every value of `form` crosses sealed, as a
    case's answer does (brief, D31)."""
    sealed = None if form is None else {name: Sensitive(value) for name, value in form.items()}
    sent = Sent(wait, outcome, by, sorted(roles), sealed)
    await run.signal(PlanWorkflow.answer, sent)


async def report(run: WorkflowHandle[PlanWorkflow, RunReport]) -> RunReport:
    """How the run is going: its history so far, and `waiting_at` the wait open for an answer."""
    return await run.query(PlanWorkflow.report)
