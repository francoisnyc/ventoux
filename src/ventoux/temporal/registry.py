"""An environment's registry on Temporal: one long-running workflow per environment, its
activities, and the calls clients make to it (layer 12e).

The registry keeps each worker's manifest, the active release of each package, the retired ones
and each release's open cases (brief, D5). Every request is an Update, answered, and decided one
at a time in the order its history records them, by the pure functions in `case/registry.py`, so
an activation, a retirement and a case opening never race. See docs/layers/12-releases.md (12e).
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, ClassVar

from temporalio import activity, workflow
from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
from temporalio.client import Client, WorkflowExecutionStatus, WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

# Temporal: the workflow sandbox imports a workflow's modules afresh; `case` is deterministic and
# passed through, imported once and shared (as in `cases.py`).
with workflow.unsafe.imports_passed_through():
    from ventoux.case import registry as pure
    from ventoux.case.activation import Manifest, activation_problems
    from ventoux.case.registry import (
        Activating,
        Answer,
        Moving,
        Opening,
        Registry,
        Released,
        Retiring,
        open_on,
    )
    from ventoux.case.releases import Record

# The task queue every environment's registry runs on, served by `registry_worker`.
REGISTRY_QUEUE = "ventoux-registry"
# How long one call to Temporal, from an activity, may take; Temporal retries it until it answers,
# as a system that is down is retried (brief, D17).
CALL = timedelta(seconds=30)


def registry_id(environment: str) -> str:
    """The registry's workflow ID: `ventoux-registry-production`. A case ID has no `/`, and none
    is used, so the codec never looks for a key here: no payload of it is sensitive."""
    return f"ventoux-registry-{environment}"


class RegistryMissing(Exception):
    """An environment whose registry doesn't exist: create it first, on purpose."""


@dataclass
class RegistryStart:
    """What a registry starts each run with: its whole state (brief, D27's rule, for the
    registry)."""

    registry: Registry


@dataclass
class Retire:
    """A request to retire a release, as it reaches the registry."""

    asked: Retiring


@dataclass
class Ended:
    """The cases a retirement asks Temporal about: those listed open on the release."""

    cases: list[str]


@dataclass
class Asked:
    """A case's question to its environment's registry, through an activity of the case's worker:
    what it opens on, or the migration it is about to apply."""

    environment: str
    opening: Opening | None = None
    moving: Moving | None = None
    closing: str | None = None  # the case that has closed


@workflow.defn(name="ventoux.registry")
class RegistryWorkflow:
    """The registry of one environment, as long as the environment lives."""

    # How many requests one run decides before it continues as new: a count, never a clock
    # (brief, D27).
    requests_per_run: ClassVar[int] = 500

    # Temporal: `workflow.init` gives `__init__` the run's start, so an Update that arrives with the
    # start, in the same workflow task, already reads the registry, never an empty one.
    @workflow.init
    def __init__(self, start: RegistryStart) -> None:
        self.registry = start.registry
        self.decided = 0  # requests this run has decided
        # Temporal: an async handler may wait (a retirement asks Temporal about cases); the lock
        # keeps requests one at a time, in the order they came.
        self.lock = asyncio.Lock()

    @workflow.run
    async def run(self, start: RegistryStart) -> None:
        # Temporal: switch only once no Update is part-way, so none is carried as a queue.
        await workflow.wait_condition(
            lambda: (
                self.decided >= self.requests_per_run
                or workflow.info().is_continue_as_new_suggested()
            )
        )
        await workflow.wait_condition(workflow.all_handlers_finished)
        workflow.continue_as_new(RegistryStart(self.registry))

    def decided_with(self, after: tuple[Registry, Answer]) -> Answer:
        """Keep the registry after a request, and give its answer."""
        self.registry, answer = after
        self.decided += 1
        return answer

    # Temporal: an Update is a request into a running workflow that is answered; recorded in its
    # history, so a replay decides it again at the same point.
    @workflow.update(name="publish")
    def publish(self, manifest: Manifest) -> Answer:
        return self.decided_with(pure.publish(self.registry, manifest))

    @workflow.update(name="activate")
    def activate(self, asked: Activating) -> Answer:
        return self.decided_with(pure.activate(self.registry, asked))

    @workflow.update(name="opened")
    def opened(self, asked: Opening) -> Answer:
        return self.decided_with(pure.opened(self.registry, asked))

    @workflow.update(name="moved")
    def moved(self, asked: Moving) -> Answer:
        return self.decided_with(pure.moved(self.registry, asked))

    @workflow.update(name="closed")
    def closed(self, case: str) -> Answer:
        return self.decided_with(pure.closed(self.registry, case))

    @workflow.update(name="harden")
    def harden(self, by: str) -> Answer:
        return self.decided_with(pure.harden(self.registry, by))

    @workflow.update(name="retire")
    async def retire(self, sent: Retire) -> Answer:
        """Retire a release, once Temporal has said which of the cases listed on it have ended
        without saying so: its answer comes from an activity, recorded in this history, so a
        replay reads it there and never asks again (layer 12e, choice 67, as answered)."""
        async with self.lock:
            listed = open_on(self.registry, sent.asked.released)
            ended: dict[str, str] = {}
            if listed:
                ended = await workflow.execute_activity(
                    "ventoux.registry.ended",
                    Ended(listed),
                    start_to_close_timeout=CALL,
                    result_type=dict[str, str],
                )
            return self.decided_with(pure.retire(self.registry, sent.asked, ended))

    # Temporal: a query reads a workflow's state without changing it, and isn't recorded.
    @workflow.query(name="registry")
    def view(self) -> Registry:
        return self.registry


class RegistryActivities:
    """The activities that reach a registry, or Temporal, from a workflow: a case asking its
    registry (run by its case worker), and a registry asking Temporal how cases stand (run by the
    registry's worker). Each is retried until it answers, as any activity (brief, D17)."""

    def __init__(self, client: Client) -> None:
        self.client = client

    @activity.defn(name="ventoux.registry.asked")
    async def asked(self, asked: Asked) -> Answer:
        """The registry's answer to a case: opening, moving or closing. A registry that doesn't
        exist refuses an opening or a move, saying so (fail closed); a close waits for it."""
        handle = self.client.get_workflow_handle(registry_id(asked.environment))
        try:
            answer: Answer
            if asked.opening is not None:
                answer = await handle.execute_update("opened", asked.opening, result_type=Answer)
            elif asked.moving is not None:
                answer = await handle.execute_update("moved", asked.moving, result_type=Answer)
            else:
                answer = await handle.execute_update("closed", asked.closing, result_type=Answer)
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND or asked.closing is not None:
                raise  # retried, as any outage
            case = asked.opening.case if asked.opening else asked.moving.case  # type: ignore[union-attr]
            return Answer(False, [f"{case}: {missing(asked.environment)}"])
        return answer

    @activity.defn(name="ventoux.registry.ended")
    async def ended(self, asked: Ended) -> dict[str, str]:
        """For each case, how it ended, if its workflow is no longer running: `terminated`,
        `failed`, `gone` (Temporal holds no history of it). Running cases aren't in the answer."""
        found: dict[str, str] = {}
        for case in asked.cases:
            try:
                described = await self.client.get_workflow_handle(case).describe()
            except RPCError as error:
                if error.status != RPCStatusCode.NOT_FOUND:
                    raise
                found[case] = "gone"
                continue
            if described.status != WorkflowExecutionStatus.RUNNING and described.status:
                found[case] = described.status.name.lower()
        return found

    def for_cases(self) -> list[Any]:
        """What a case worker in an environment runs."""
        return [self.asked]


def missing(environment: str) -> str:
    """Why nothing is done in an environment with no registry."""
    return (
        f"{environment} has no registry: create it with `ventoux environment create {environment}`"
    )


def registry_worker(client: Client, registry: type[RegistryWorkflow] = RegistryWorkflow) -> Worker:
    """A worker for every environment's registry, on its own queue, and the activity it runs.
    A deployment can run it in the same process as a case worker."""
    activities = RegistryActivities(client)
    return Worker(
        client,
        task_queue=REGISTRY_QUEUE,
        workflows=[registry],
        activities=[activities.ended],
    )


def registry_handle(client: Client, environment: str) -> WorkflowHandle[RegistryWorkflow, None]:
    """The registry of `environment`, by its ID alone, reaching its latest run."""
    return client.get_workflow_handle_for(RegistryWorkflow.run, registry_id(environment))


async def create_environment(client: Client, environment: str, development: bool = False) -> None:
    """Create `environment`'s registry, on purpose and once: a production one unless
    `development`, where drafts open. A misspelt name never makes one by itself."""
    try:
        await client.start_workflow(
            RegistryWorkflow.run,
            RegistryStart(Registry(environment, development)),
            id=registry_id(environment),
            task_queue=REGISTRY_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
    except WorkflowAlreadyStartedError:
        raise RegistryMissing(f"{environment} exists already: its registry is running") from None


async def ask(client: Client, environment: str, update: str, request: Any) -> Answer:
    """The registry's answer to `request`, sent as the Update `update`; `RegistryMissing` if the
    environment has no registry."""
    try:
        answer: Answer = await registry_handle(client, environment).execute_update(
            update, request, result_type=Answer
        )
        return answer
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            raise RegistryMissing(missing(environment)) from None
        raise


async def registry_of(client: Client, environment: str) -> Registry:
    """What `environment`'s registry holds now."""
    try:
        return await registry_handle(client, environment).query(RegistryWorkflow.view)
    except RPCError as error:
        if error.status == RPCStatusCode.NOT_FOUND:
            raise RegistryMissing(missing(environment)) from None
        raise


class ManifestRefused(Exception):
    """A worker's manifest its registry refused: the worker never starts."""


async def publish_manifest(client: Client, manifest: Manifest) -> Answer:
    """Publish a worker's manifest to its environment's registry; `ManifestRefused`, saying why,
    if the registry refuses it, and `RegistryMissing` if there is none."""
    answer = await ask(client, manifest.environment, "publish", manifest)
    if not answer.done:
        raise ManifestRefused("\n".join(answer.said))
    return answer


def released(record: Record) -> Released:
    """A release record, as a request names it."""
    return Released(record.name, record.release, record.digest)


async def pollers(client: Client, queues: list[str]) -> dict[str, list[str]]:
    """Each queue's pollers, workflow and activity alike, by identity, as Temporal's server lists
    them now: it drops a poller a few minutes after its last poll (layer 12e, choice 72)."""
    found: dict[str, list[str]] = {}
    for queue in queues:
        identities: set[str] = set()
        for kind in (
            TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
            TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY,
        ):
            # Temporal: `DescribeTaskQueue` lists who polls a queue; the time-skipping test server
            # doesn't implement it, the dev server does (layer 12e, choice 77).
            described = await client.workflow_service.describe_task_queue(
                DescribeTaskQueueRequest(
                    namespace=client.namespace,
                    task_queue=TaskQueue(name=queue),
                    task_queue_type=kind,
                )
            )
            identities |= {poller.identity for poller in described.pollers}
        found[queue] = sorted(identities)
    return found


async def seen_pollers(client: Client, registry: Registry, queue: str) -> dict[str, list[str]]:
    """The pollers a check of `queue` needs: that queue's, and those of every queue its live case
    workers bind a workflow contract to."""
    seen = await pollers(client, [queue])
    bound = {
        bound.task_queue
        for identity in seen[queue]
        if (manifest := registry.manifests.get(identity)) is not None
        for bound in manifest.binds.values()
    }
    return seen | await pollers(client, sorted(bound - {queue}))


async def activate(client: Client, environment: str, record: Record, queue: str, by: str) -> Answer:
    """Activate `record`'s release in `environment`, its new cases opening on `queue`: the registry
    checks the workers' manifests against the record, with the pollers Temporal lists now, and
    refuses saying every problem (brief, D5). Rolling back is activating an earlier release."""
    registry = await registry_of(client, environment)
    seen = await seen_pollers(client, registry, queue)
    asked = Activating(released(record), dict(record.contracts), queue, seen, by)
    return await ask(client, environment, "activate", asked)


async def retire(client: Client, environment: str, record: Record, by: str) -> Answer:
    """Retire `record`'s release in `environment`, for good, once no case is open on it."""
    return await ask(client, environment, "retire", Retire(Retiring(released(record), by)))


async def harden(client: Client, environment: str, by: str) -> Answer:
    """Make a development environment a production one, for good."""
    return await ask(client, environment, "harden", by)


async def active_release(client: Client, environment: str, name: str) -> tuple[int, str] | None:
    """The release of package `name` new cases open on in `environment`, and its queue: what the
    API reads the record of from the store and passes to `start_case`; None if none is active.
    The case checks it again as it opens (brief, D51)."""
    registry = await registry_of(client, environment)
    release = registry.active.get(name)
    if release is None:
        return None
    return release, registry.activated[f"{name} {release}"].task_queue


async def open_cases(client: Client, environment: str, record: Record) -> list[str]:
    """The cases open on `record`'s release in `environment`, by ID: a migration's cohort
    (brief, D53)."""
    return open_on(await registry_of(client, environment), released(record))


async def environment_check(client: Client, environment: str) -> list[str]:
    """Why any release that is active in `environment`, or has open cases there, can't run now on
    the queue it was activated on, one line each, naming it; empty if every one can. An old
    contract version stays served while an open case uses it (brief, D5); the deployment's
    monitoring runs this and alerts on a problem."""
    registry = await registry_of(client, environment)
    labels = {f"{name} {release}" for name, release in registry.active.items()}
    labels |= set(registry.open.values())
    found: list[str] = []
    for label in sorted(labels):
        activation = registry.activated[label]
        seen = await seen_pollers(client, registry, activation.task_queue)
        problems = activation_problems(
            label,
            activation.contracts,
            activation.task_queue,
            environment,
            registry.manifests,
            seen,
        )
        found += [f"{label}: {problem}" for problem in problems]
    return found
