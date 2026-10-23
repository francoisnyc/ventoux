"""Activation on Temporal (layer 12e): manifests, the environment registry, a case in an
environment; and the histories recorded before them.

The histories were recorded under main at `2fde255`, before 12e changes anything on Temporal:
whatever 12e adds to a case's start or commands, a case opened before it replays as it was
recorded (brief, D17) (brief, D51).
See docs/layers/12-releases.md (12e).
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest
from temporalio import workflow
from temporalio.client import Client, WorkflowHistory
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from test_temporal_approvals import EveryEventCases
from test_temporal_case import replay

from ventoux.case.activation import Bound, Manifest
from ventoux.case.releases import METHOD, Hash
from ventoux.core.contract_hash import contract_hash
from ventoux.temporal.bindings import Binding
from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow
from ventoux.temporal.manifests import environment_worker
from ventoux.temporal.registry import (
    RegistryMissing,
    RegistryStart,
    RegistryWorkflow,
    create_environment,
    publish_manifest,
    registry_handle,
    registry_of,
    registry_worker,
)
from ventoux.testing import (
    CATALOG,
    FAKES,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
    fixture_converter,
)

HERE = Path(__file__).parent / "histories"

# A draft and a release, each waiting for its approval; the same release continued as new after
# every event; a case migrated to refund 2 across switches; and a case closed, its review rejected.
BEFORE_12E: dict[str, type[CaseWorkflow]] = {
    "before_12e_draft_waiting": DevelopmentCases,
    "before_12e_released_waiting": DevelopmentCases,
    "before_12e_released_switched": EveryEventCases,
    "before_12e_migrated_switched": EveryEventCases,
    "before_12e_closed": DevelopmentCases,
}


def test_histories_from_before_12e_replay() -> None:
    for name, cases in BEFORE_12E.items():
        recorded = HERE / f"{name}.json"
        history = WorkflowHistory.from_json("refund-1", recorded.read_text())
        replay(history, cases, fixture_converter(recorded))


# --- Slice 3: manifests and the registry on Temporal ---


# Temporal: production's case workflow, as a deployment names it: the development catalog, in an
# environment, so each case asks production's registry.
@workflow.defn(name="ventoux.case")
class ProductionCases(CaseWorkflow):
    catalog = CATALOG
    environment = "production"
    workflows: ClassVar[Mapping[str, Binding]] = {
        "kyc.check@1": Binding(workflow="KycCheck", task_queue="kyc")
    }

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


QUEUE = "refunds"


def in_production[T](
    scenario: Callable[[Client], Awaitable[T]],
    create: bool = True,
    development: bool = False,
    registry: type[RegistryWorkflow] = RegistryWorkflow,
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with the registries' worker
    running and production's registry created (unless not `create`); the scenario starts its own
    case workers, since each publishes its manifest as it starts."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(
            data_converter=development_converter()
        )
        async with environment, registry_worker(environment.client, registry):
            if create:
                await create_environment(environment.client, "production", development)
            return await asyncio.wait_for(scenario(environment.client), timeout=20)

    return asyncio.run(go())


async def production_worker(
    client: Client, identity: str = "refunds-a", build: str = "4f2a9c1"
) -> Worker:
    """A case worker in production, on refunds, its manifest published as it starts."""
    return await environment_worker(
        client, QUEUE, ProductionCases, DevelopmentPlans, FAKES, build, identity
    )


def hashed(reference: str) -> Hash:
    return Hash(METHOD, contract_hash(CATALOG.lookup(reference)))


def test_a_worker_publishes_its_manifest() -> None:
    # Built from its code: each contract it has code for, hashed by its own catalog; its workflow
    # types; its case workflow's bindings; the build and identity it was given.
    async def scenario(client: Client) -> Manifest:
        async with await production_worker(client):
            return (await registry_of(client, "production")).manifests["refunds-a"]

    manifest = in_production(scenario)
    assert manifest == Manifest(
        "production",
        "refunds",
        "4f2a9c1",
        "refunds-a",
        {reference: hashed(reference) for reference in sorted(FAKES)},
        ["ventoux.case", "ventoux.plan"],
        "ventoux.case",
        {"kyc.check@1": Bound("KycCheck", "kyc")},
    )


def test_a_worker_refuses_to_start_without_its_registry() -> None:
    # An environment exists only once created, on purpose: a worker of one that doesn't, or of a
    # case workflow naming none, never starts polling.
    async def scenario(client: Client) -> tuple[str, str]:
        with pytest.raises(RegistryMissing) as missing:
            await production_worker(client)
        with pytest.raises(ValueError) as nowhere:
            await environment_worker(client, QUEUE, DevelopmentCases, DevelopmentPlans, FAKES, "b")
        return str(missing.value), str(nowhere.value)

    assert in_production(scenario, create=False) == (
        "production has no registry: create it with `ventoux environment create production`",
        "DevelopmentCases names no environment: set its `environment` to publish a manifest",
    )


def test_an_environment_is_created_once() -> None:
    async def scenario(client: Client) -> str:
        with pytest.raises(RegistryMissing) as twice:
            await create_environment(client, "production")
        return str(twice.value)

    assert in_production(scenario) == "production exists already: its registry is running"


# Temporal: a registry that continues as new after every request.
@workflow.defn(name="ventoux.registry")
class EveryRequestRegistry(RegistryWorkflow):
    requests_per_run = 1

    @workflow.run
    async def run(self, start: RegistryStart) -> None:
        await super().run(start)


def test_the_registry_crosses_continue_as_new() -> None:
    # After every request a new run, carrying the whole registry: each request is answered by the
    # run whose history records it, and nothing is lost on the way (brief, D27's rule).
    async def scenario(client: Client) -> tuple[bool, list[str], bool]:
        team = Manifest(
            "production",
            "kyc",
            "k-12",
            "kyc-a",
            {"kyc.check@1": hashed("kyc.check@1")},
            ["KycCheck"],
        )
        for identity in ("kyc-a", "kyc-b", "kyc-c"):
            await publish_manifest(client, replace(team, identity=identity))
        info = (await registry_handle(client, "production").describe()).raw_description
        held = await registry_of(client, "production")
        switched = (
            info.workflow_execution_info.execution.run_id
            != info.workflow_execution_info.first_run_id
        )
        return switched, sorted(held.manifests), held.development

    switched, identities, development = in_production(scenario, registry=EveryRequestRegistry)
    assert switched and identities == ["kyc-a", "kyc-b", "kyc-c"] and development is False
