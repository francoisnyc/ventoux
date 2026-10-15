"""A worker: serves plan and case workflows and the activities they call (layers 6 and 8c)."""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from ventoux.case.memory import Activity
from ventoux.temporal.activities import plan_activities
from ventoux.temporal.cases import CaseWorkflow
from ventoux.temporal.converter import require_ventoux_converter
from ventoux.temporal.forget import ForgetActivities, ForgetWorkflow
from ventoux.temporal.logs import keep_only_exception_types
from ventoux.temporal.workflow import PlanWorkflow

# Temporal: the workflow sandbox imports a workflow's modules afresh for every run; a module passed
# through is imported once and shared. `core` and `case` are deterministic (the boundary test holds
# them to that), and passing them through keeps one copy of each class: a `Sensitive` the
# converter reads back is the class `case` checks for, whichever module first imported it. A
# replay uses the same runner (brief, D31).
SANDBOX = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules(
        "ventoux.core", "ventoux.case", "ventoux.tooling", "cryptography"
    )
)


def plan_worker(
    client: Client,
    task_queue: str,
    workflow: type[PlanWorkflow],
    implementations: Mapping[str, Activity],
) -> Worker:
    """A worker on `task_queue` for `workflow`, and the code behind its catalog's contracts."""
    require_ventoux_converter(client)
    keep_only_exception_types()  # a failure's text never reaches the log (brief, D31)
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[workflow],
        activities=plan_activities(workflow.catalog, implementations),
        # Temporal: activities that are plain functions (not `async`) run on these threads.
        activity_executor=ThreadPoolExecutor(),
        workflow_runner=SANDBOX,
    )


def case_worker(
    client: Client,
    task_queue: str,
    cases: type[CaseWorkflow],
    plans: type[PlanWorkflow],
    implementations: Mapping[str, Activity],
    forget: type[ForgetWorkflow] | None = None,
) -> Worker:
    """A worker on `task_queue` for `cases`, the plan workflow its plan steps run as, and the code
    behind its catalog's contracts; and, given `forget`, the requests to forget a case
    (brief, D32)."""
    require_ventoux_converter(client)
    keep_only_exception_types()  # a failure's text never reaches the log (brief, D31)
    forgetting = [] if forget is None else ForgetActivities(client).all()
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[cases, plans] if forget is None else [cases, plans, forget],
        activities=[*plan_activities(cases.catalog, implementations), *forgetting],
        # Temporal: activities that are plain functions (not `async`) run on these threads.
        activity_executor=ThreadPoolExecutor(),
        workflow_runner=SANDBOX,
    )
