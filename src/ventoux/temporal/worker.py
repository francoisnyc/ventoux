"""A worker: serves a plan workflow and the activities its plans call (layer 6)."""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from ventoux.case.memory import Activity
from ventoux.temporal.activities import plan_activities
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
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[workflow],
        activities=plan_activities(workflow.catalog, implementations),
        # Temporal: activities that are plain functions (not `async`) run on these threads.
        activity_executor=ThreadPoolExecutor(),
    )
