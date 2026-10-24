"""A worker's manifest, built from its code, and a worker that publishes it as it starts
(layer 12e).

Temporal knows who polls a queue, never what they serve; so a worker in an environment says it,
with each contract's hash from its own catalog, before it polls: a refusal stops it there, never
later (brief, D5). See docs/layers/12-releases.md (12e).
"""

from collections.abc import Mapping

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker

from ventoux.case.activation import Bound, Manifest
from ventoux.case.memory import Activity
from ventoux.case.releases import METHOD, Hash
from ventoux.core.contract_hash import contract_hash
from ventoux.temporal.cases import CaseWorkflow
from ventoux.temporal.forget import ForgetWorkflow
from ventoux.temporal.registry import publish_manifest
from ventoux.temporal.worker import case_worker
from ventoux.temporal.workflow import PlanWorkflow


def workflow_type(registered: type) -> str:
    """The name a workflow class is registered under: `ventoux.case`."""
    # Temporal: `@workflow.defn` keeps the class's definition, its name included, on the class.
    name = workflow._Definition.must_from_class(registered).name
    if name is None:  # a dynamic workflow takes any type: nothing a manifest can promise
        raise ValueError(f"{registered.__name__} is a dynamic workflow: it has no type to serve")
    return name


def worker_manifest(
    cases: type[CaseWorkflow],
    plans: type[PlanWorkflow],
    implementations: Mapping[str, Activity],
    task_queue: str,
    build: str,
    identity: str,
) -> Manifest:
    """What a case worker serves: each contract it has code for, with the hash its own catalog
    gives (which is what Temporal would run), its workflow types, and its case workflow's
    bindings. Built from the code, never written by hand."""
    if cases.environment is None:
        raise ValueError(
            f"{cases.__name__} names no environment: set its `environment` to publish a manifest"
        )
    serves = {
        reference: Hash(METHOD, contract_hash(cases.catalog.get(reference)))
        for reference in sorted(implementations)
    }
    binds = {
        reference: Bound(binding.workflow, binding.task_queue)
        for reference, binding in sorted(cases.workflows.items())
    }
    case = workflow_type(cases)
    return Manifest(
        cases.environment,
        task_queue,
        build,
        identity,
        serves,
        [case, workflow_type(plans)],
        case,
        binds,
    )


async def environment_worker(
    client: Client,
    task_queue: str,
    cases: type[CaseWorkflow],
    plans: type[PlanWorkflow],
    implementations: Mapping[str, Activity],
    build: str,
    identity: str | None = None,
    forget: type[ForgetWorkflow] | None = None,
) -> Worker:
    """A case worker for `cases`'s environment, as `case_worker` builds one, once its manifest is
    published: refused (`ManifestRefused`, `RegistryMissing`), it never polls (brief, D54).
    `build` is the deployment's name for this build, given, never read from git; `identity` is
    the worker's name among a queue's pollers (the client's own by default)."""
    identity = identity or client.identity
    manifest = worker_manifest(cases, plans, implementations, task_queue, build, identity)
    await publish_manifest(client, manifest)
    return case_worker(client, task_queue, cases, plans, implementations, forget, identity)
