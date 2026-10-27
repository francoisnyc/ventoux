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
from typing import Any, ClassVar

import pytest
from one_copy import put_back, second_copies
from skipping_server import time_skipping
from temporalio import workflow
from temporalio.client import Client, WorkflowFailureError, WorkflowHistory
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from test_migrations import PEOPLE, REFUND_1, REFUND_2
from test_temporal_approvals import EveryEventCases
from test_temporal_case import (
    LARGE,
    REFUND,
    SMALL,
    SMALL_FORM,
    on_temporal,
    replay,
    reported,
    skipping,
)
from test_temporal_case_release import markers_of

from ventoux.case.activation import Bound, Manifest
from ventoux.case.registry import Activating, Answer, Opening, Released
from ventoux.case.releases import METHOD, Hash, Record
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract
from ventoux.core.contract_hash import contract_hash
from ventoux.temporal.bindings import Binding
from ventoux.temporal.cases import (
    REGISTRY_PATCH,
    CaseReport,
    CaseStart,
    CaseWorkflow,
    PreviewAnswer,
    answer,
    preview_migrations,
    propose_migration,
    start_case,
)
from ventoux.temporal.manifests import environment_worker
from ventoux.temporal.registry import (
    ManifestRefused,
    RegistryMissing,
    RegistryStart,
    RegistryWorkflow,
    ask,
    create_environment,
    open_cases,
    publish_manifest,
    registry_handle,
    registry_of,
    registry_worker,
    released,
    retire,
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
        async with (
            time_skipping(development_converter()) as environment,
            registry_worker(environment.client, registry),
        ):
            if create:
                await create_environment(environment.client, "production", development)
            return await asyncio.wait_for(scenario(environment.client), timeout=20)

    return asyncio.run(go())


async def production_worker(
    client: Client,
    identity: str = "refunds-a",
    build: str = "4f2a9c1",
    cases: type[CaseWorkflow] = ProductionCases,
) -> Worker:
    """A case worker in production, on refunds, its manifest published as it starts."""
    return await environment_worker(client, QUEUE, cases, DevelopmentPlans, FAKES, build, identity)


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


def test_the_registry_worker_loads_no_second_copy_of_ventoux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Temporal: a registry defined here is imported afresh with this file, which imports the
    # builder through `ventoux.testing`; only Ventoux's runner passes the builder through, so a
    # registry worker on Temporal's default runner would hang a second builder on
    # `ventoux.tooling` (brief, D62).
    put_back(monkeypatch)

    async def scenario(client: Client) -> None:
        return None

    in_production(scenario, registry=EveryRequestRegistry)
    assert second_copies() == []


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

    @workflow.init
    def __init__(self, start: RegistryStart) -> None:
        super().__init__(start)

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


# --- Slice 4: a case in an environment ---

RECORD_1 = REFUND_1
OPEN_ON = {"refunds": ["refunds-a"]}


async def activated(client: Client, record: Record, queue: str = QUEUE) -> Answer:
    """Pia activates `record` in production, the registry given the pollers a command would see:
    the time-skipping server can't list them (layer 12e, choice 77); the dev server's tests read them."""
    asked = Activating(released(record), dict(record.contracts), queue, OPEN_ON, "pia")
    answer = await ask(client, "production", "activate", asked)
    assert answer.done, answer.said
    return answer


async def refusal(case: Any) -> str:
    """Why a case that never opened was refused, as its workflow's failure says."""
    with pytest.raises(WorkflowFailureError) as failed:
        await case.result()
    cause: Any = failed.value.cause
    assert isinstance(cause, ApplicationError) and cause.type == "CaseRefused"
    return str(cause.message)


def test_a_case_opens_only_on_its_environments_active_release() -> None:
    # The registry answers as the case opens, through an activity recorded in its history; a
    # replay reads that answer there, with no registry at all.
    async def scenario(client: Client) -> tuple[list[str], CaseReport, list[str], WorkflowHistory]:
        async with await production_worker(client):
            await activated(client, REFUND_1)
            refused = [
                await refusal(
                    await start_case(client, ProductionCases, REFUND_2, LARGE, "refund-2", QUEUE)
                ),
            ]
            async with await environment_worker(
                client, "refunds-old", ProductionCases, DevelopmentPlans, FAKES, "4f2a9c1", "old-a"
            ):
                old = await start_case(
                    client, ProductionCases, REFUND_1, LARGE, "refund-3", "refunds-old"
                )
                refused.append(await refusal(old))
            case = await start_case(client, ProductionCases, REFUND_1, LARGE, "refund-1", QUEUE)
            now = await reported(case, lambda now: now.waiting_at == ["review#1"])
            listed = await open_cases(client, "production", REFUND_1)
            return refused, now, listed, await case.fetch_history()

    refused, now, listed, history = in_production(scenario)
    assert REGISTRY_PATCH in markers_of(history)
    assert refused == [
        "refund-2 can't open on refund 2: production never activated refund 2: activate it first",
        "refund-3 can't open on refund 1 on refunds-old: production activated it on refunds",
    ]
    assert now.release == "refund 1" and listed == ["refund-1"]
    replay(history, ProductionCases, development_converter())


def test_a_draft_is_refused_in_production() -> None:
    # Refused at its opening in production, nothing decided; it opens in an environment created
    # for development, and with no environment at all, as before 12e (brief, D51).
    async def refused(client: Client) -> str:
        async with await production_worker(client):
            return await refusal(
                await start_case(client, ProductionCases, REFUND, LARGE, "refund-1", QUEUE)
            )

    async def opened(client: Client) -> str:
        async with await production_worker(client):
            case = await start_case(client, ProductionCases, REFUND, LARGE, "refund-1", QUEUE)
            return (await reported(case, lambda now: now.waiting_at == ["review#1"])).release

    assert in_production(refused) == (
        "refund-1 can't open as a draft in production: open it on a release"
    )
    assert in_production(opened, development=True) == "draft"
    assert on_temporal(lambda client: draft_opens(client)) == "draft"


async def draft_opens(client: Client) -> str:
    case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", "cases")
    return (await reported(case, lambda now: now.waiting_at == ["review#1"])).release


def test_the_registry_knows_each_releases_open_cases() -> None:
    # Each case says it opened, moved and closed: the registry lists each release's open cases,
    # a migration's cohort, and a closed case is no longer listed. Its worker switches after
    # every event, so the environment the case asks crosses every continue-as-new.
    async def scenario(client: Client) -> list[tuple[list[str], list[str]]]:
        seen: list[tuple[list[str], list[str]]] = []

        async def listed() -> None:
            seen.append(
                (
                    await open_cases(client, "production", REFUND_1),
                    await open_cases(client, "production", REFUND_2),
                )
            )

        async with await production_worker(client, cases=EveryEventInProduction):
            await activated(client, REFUND_1)
            rejected = await start_case(
                client, EveryEventInProduction, REFUND_1, LARGE, "refund-1", QUEUE
            )
            moving = await start_case(
                client, EveryEventInProduction, REFUND_1, LARGE, "refund-2", QUEUE
            )
            await reported(moving, lambda now: now.waiting_at == ["review#1"])
            await listed()
            await answer(rejected, "review#1", "reject", "ana", PEOPLE["ana"])
            await rejected.result()
            await listed()
            await activated(client, REFUND_2)
            await propose_migration(moving, REFUND_2, {}, "pia", PEOPLE["pia"])
            await reported(moving, lambda now: "case.change#1" in now.waiting_at)
            await answer(moving, "case.change#1", "approve", "lee", PEOPLE["lee"])
            await reported(moving, lambda now: now.release == "refund 2")
            await listed()
        return seen

    assert in_production(scenario) == [
        (["refund-1", "refund-2"], []),
        (["refund-2"], []),
        ([], ["refund-2"]),
    ]


def test_a_migration_target_is_the_registrys() -> None:
    # When an approval would apply a migration, the case asks its registry first: a target this
    # environment never activated, or retired, is refused, recorded, and the request waits on.
    async def scenario(client: Client) -> tuple[list[str], str, str]:
        async with await production_worker(client):
            await activated(client, REFUND_1)
            case = await start_case(client, ProductionCases, REFUND_1, LARGE, "refund-1", QUEUE)
            await reported(case, lambda now: now.waiting_at == ["review#1"])
            await propose_migration(case, REFUND_2, {}, "pia", PEOPLE["pia"])
            await reported(case, lambda now: "case.change#1" in now.waiting_at)
            await answer(case, "case.change#1", "approve", "lee", PEOPLE["lee"])
            now = await reported(
                case, lambda now: any("refused lee" in line for line in now.history)
            )
            return now.waiting_at, now.history[-1], now.release

    waiting, line, release = in_production(scenario)
    assert line == (
        "refused lee's answer approve to case.change#1: refund-1 can't move to refund 2: "
        "production never activated refund 2: activate it first"
    )
    assert "case.change#1" in waiting and release == "refund 1"


def test_a_case_without_an_environment_is_as_before() -> None:
    # No environment: nothing is asked and no marker written. In one, the opening writes the
    # marker; and a history recorded before 12e replays under a class in an environment too,
    # since its opening has no marker.
    async def scenario(client: Client) -> WorkflowHistory:
        history: WorkflowHistory = await (await draft_handle(client)).fetch_history()
        return history

    history = on_temporal(scenario)
    assert REGISTRY_PATCH not in markers_of(history)
    for name, cases in BEFORE_12E.items():
        recorded = HERE / f"{name}.json"
        before = WorkflowHistory.from_json("refund-1", recorded.read_text())
        replay(before, IN_PRODUCTION[cases], fixture_converter(recorded))


async def draft_handle(client: Client) -> Any:
    case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", "cases")
    await reported(case, lambda now: now.waiting_at == ["review#1"])
    return case


# Temporal: the same switching workflow as `EveryEventCases`, in production.
@workflow.defn(name="ventoux.case")
class EveryEventInProduction(ProductionCases):
    events_per_run = 1

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


IN_PRODUCTION: dict[type[CaseWorkflow], type[CaseWorkflow]] = {
    DevelopmentCases: ProductionCases,
    EveryEventCases: EveryEventInProduction,
}


def test_a_worker_moving_a_workflow_type_under_open_cases_refuses_to_start() -> None:
    # Open cases of a release that calls kyc.check@1, bound to KycCheck: a worker binding it to
    # another type never starts; one moving only its task queue does (brief, D29).
    async def scenario(client: Client) -> str:
        async with await production_worker(client):
            kyc = Activating(
                Released("kyc", 1, Hash(1, "55" * 32)),
                {"kyc.check@1": hashed("kyc.check@1")},
                QUEUE,
                {"refunds": ["refunds-a"], "kyc": ["kyc-a"]},
                "pia",
            )
            team = Manifest(
                "production",
                "kyc",
                "k-12",
                "kyc-a",
                {"kyc.check@1": hashed("kyc.check@1")},
                ["KycCheck"],
            )
            await publish_manifest(client, team)
            assert (await ask(client, "production", "activate", kyc)).done
            opening = Opening("kyc-7", QUEUE, kyc.released)
            assert (await ask(client, "production", "opened", opening)).done
        async with await environment_worker(
            client, QUEUE, MovedQueue, DevelopmentPlans, FAKES, "b2", "refunds-b"
        ):
            pass
        with pytest.raises(ManifestRefused) as refused:
            await environment_worker(
                client, QUEUE, Retyped, DevelopmentPlans, FAKES, "b3", "refunds-c"
            )
        return str(refused.value)

    assert in_production(scenario) == (
        "kyc.check@1 is bound to KycCheck, and 1 open case of kyc 1 calls it: a workflow type "
        "never moves under open cases; move its task queue, or bind a new contract version"
    )


@workflow.defn(name="ventoux.case")
class MovedQueue(ProductionCases):
    workflows: ClassVar[Mapping[str, Binding]] = {
        "kyc.check@1": Binding(workflow="KycCheck", task_queue="kyc-2")
    }

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


@workflow.defn(name="ventoux.case")
class Retyped(ProductionCases):
    workflows: ClassVar[Mapping[str, Binding]] = {
        "kyc.check@1": Binding(workflow="KycCheckV2", task_queue="kyc")
    }

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def test_a_case_ended_from_outside_never_blocks_retirement() -> None:
    # Terminated in Temporal's UI, a case never says it closed. Retiring its release, the registry
    # asks Temporal through an activity, drops it saying so, and refuses only for the rest
    # (layer 12e, choice 67, as answered).
    async def scenario(client: Client) -> tuple[list[str], list[str]]:
        async with await production_worker(client):
            await activated(client, REFUND_1)
            cases = [
                await start_case(client, ProductionCases, REFUND_1, LARGE, id, QUEUE)
                for id in ("refund-1", "refund-2")
            ]
            for case in cases:
                await reported(case, lambda now: now.waiting_at == ["review#1"])
            await activated(client, REFUND_2)
            await cases[0].terminate("an operator, by hand")
            refused = await retire(client, "production", REFUND_1, "pia")
            await answer(cases[1], "review#1", "reject", "ana", PEOPLE["ana"])
            await cases[1].result()
            done = await retire(client, "production", REFUND_1, "pia")
            return refused.said, done.said

    refused, done = in_production(scenario)
    assert refused == [
        "refund-1 ended (terminated) without saying it closed: no longer open on refund 1",
        (
            "refund 1 not retired: 1 case is open on it in production (refund-2): migrate them, "
            "or let them close"
        ),
    ]
    assert done == ["pia retired refund 1 in production"]


# --- Slice 5: migrations and the cohort ---


def test_a_cohort_is_the_releases_open_cases() -> None:
    # The registry lists the cases open on a release; each previews the migration for itself
    # (brief, D53). A closed case is no longer in the cohort.
    async def scenario(client: Client) -> dict[str, PreviewAnswer]:
        async with await production_worker(client):
            await activated(client, REFUND_1)
            for id in ("refund-1", "refund-2", "refund-3"):
                case = await start_case(client, ProductionCases, REFUND_1, LARGE, id, QUEUE)
                await reported(case, lambda now: now.waiting_at == ["review#1"])
            await answer(case, "review#1", "reject", "ana", PEOPLE["ana"])
            await case.result()
            await activated(client, REFUND_2)
            cohort = await open_cases(client, "production", REFUND_1)
            return await preview_migrations(client, ProductionCases, cohort, REFUND_2, {})

    seen = in_production(scenario)
    assert list(seen) == ["refund-1", "refund-2"]
    assert all(preview.refused == [] for preview in seen.values())


# --- Slice 7: D5's second line ---


def refund_timed(**timeouts: int) -> Catalog:
    """The development catalog, but with payments.refund@2's timeouts changed: what a build from
    a branch that changed a contract without a new version would serve, or a contract a test can
    wait out."""
    other = Catalog()
    for label in CATALOG.labels:
        other.register_label(label)
    for system in CATALOG.systems:
        other.register_system(system)
    for contract in CATALOG.contracts():
        if isinstance(contract, ActivityContract) and contract.reference == "payments.refund@2":
            changed = contract.timeouts.model_copy(update=timeouts)
            contract = contract.model_copy(update={"timeouts": changed})
        other.register(contract)
    for role in ("support", "support-lead"):
        other.register_role(role, approves=CATALOG.roles[role])
    return other


# Temporal: development cases whose refund waits at most 2 s for a worker to pick it up: the
# time-skipping server waits out an activity's timeouts in real time, never skipping them.
@workflow.defn(name="ventoux.case")
class QuicklyTimedOut(CaseWorkflow):
    catalog = refund_timed(schedule_to_start=2)

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def test_an_activity_nobody_picks_up_needs_attention() -> None:
    # The case worker serves no activity at all, so nobody polls for payments.refund@2: past its
    # contract's schedule-to-start timeout the step fails loudly, never retried (Temporal doesn't
    # retry that timeout), and the case needs attention, never waits silently (brief, D5)
    # (brief, D17).
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        client = environment.client
        case = await start_case(client, QuicklyTimedOut, REFUND, SMALL, "refund-1", "cases")
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], SMALL_FORM)
        return await reported(case, lambda now: bool(now.needs_attention))

    now = skipping(scenario, {}, QuicklyTimedOut)
    assert now.needs_attention == ["pay#1: payments.refund@2 failed with TimeoutError: ‹sensitive›"]
    assert now.status == "open"
