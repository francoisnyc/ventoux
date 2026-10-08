"""A worker: serves a plan workflow and the activities its plans call (layer 6)."""

from collections.abc import Mapping

from temporalio.client import Client
from temporalio.worker import Worker

from ventoux.case.runner import Activity
from ventoux.temporal.converter import require_exact_numbers
from ventoux.temporal.workflow import PlanWorkflow


def plan_worker(
    client: Client,
    task_queue: str,
    workflow: type[PlanWorkflow],
    implementations: Mapping[str, Activity],
) -> Worker:
    """A worker on `task_queue` for `workflow`, and the code behind its catalog's contracts."""
    require_exact_numbers(client)
    return Worker(client, task_queue=task_queue, workflows=[workflow])
