"""A worker: serves plan and case workflows and the activities they call (layers 6 and 8c)."""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from ventoux.case.memory import Activity
from ventoux.temporal.activities import plan_activities
from ventoux.temporal.cases import CaseWorkflow
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


def case_worker(
    client: Client,
    task_queue: str,
    cases: type[CaseWorkflow],
    plans: type[PlanWorkflow],
    implementations: Mapping[str, Activity],
) -> Worker:
    """A worker on `task_queue` for `cases`, the plan workflow its plan steps run as, and the code
    behind its catalog's contracts."""
    require_exact_numbers(client)
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[cases, plans],
        activities=plan_activities(cases.catalog, implementations),
        # Temporal: activities that are plain functions (not `async`) run on these threads.
        activity_executor=ThreadPoolExecutor(),
    )
