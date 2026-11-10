# Shows, on Temporal's time-skipping test server, whether D54 (activation: registry, manifests, retiring), D65 (every worker Ventoux builds runs on SANDBOX) and a sample of D75 (child cases) are what the code does.
"""Reaches past the supported names for: the repository's own test harness and its test modules'
helpers (`tests/test_temporal_registry.py`, `tests/test_temporal_children.py`,
`tests/test_temporal_forget.py`), the registry's functions (`ventoux.temporal.registry`, not in
public.json), and `ventoux.testing`'s development catalog and workflows."""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))

from temporalio.api.enums.v1 import EventType, ParentClosePolicy
from production_stand_ins import production_audit
from temporalio.client import Client
from test_migrations import PEOPLE, REFUND_1, REFUND_2
from test_temporal_case import LARGE, reported
from test_temporal_children import FILE, RELEASE, started
from test_temporal_forget import on_temporal as forgetting_on_temporal
from test_temporal_registry import OPEN_ON, QUEUE, ProductionCases, Retyped, activated, hashed, in_production, production_worker, refusal
from worker_threads import worker_threads

from ventoux.case.activation import Manifest
from ventoux.case.registry import Activating, Opening, Released
from ventoux.case.releases import METHOD, Hash
from ventoux.temporal.cases import answer, case_handle, start_case
from ventoux.temporal.forget import propose_forget
from ventoux.temporal.manifests import environment_worker
from ventoux.temporal.registry import ask, create_environment, harden, publish_manifest, registry_handle, registry_of, registry_worker, released, retire
from ventoux.temporal.sandbox import SANDBOX
from ventoux.temporal.worker import case_worker, plan_worker
from ventoux.testing import FAKES, DevelopmentCases, DevelopmentForget, DevelopmentPlans, development_audit

ROWS: list[tuple[str, str, str, bool]] = []


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, " ".join(str(shown).split())[:470], agrees))


async def said(action: Any) -> str:
    try:
        return f"ok: {await action}"
    except Exception as error:
        return f"{type(error).__name__}: {' '.join(str(error).split())}"


async def no_registry(client: Client) -> None:
    async with worker_threads() as threads:
        built = await said(environment_worker(client, QUEUE, ProductionCases, DevelopmentPlans, FAKES, "b1", "refunds-a", activity_executor=threads, audit=development_audit()))
    row("D54", "'A refusal, or an environment with no registry, stops it before it polls' (`environment_worker` is awaited before the worker runs: it raises, and no worker exists to poll)", built, built.startswith("RegistryMissing"))
    there = await said(registry_handle(client, "production").describe())
    row("D54", "'One registry per environment ... created on purpose, never by a first manifest' (after that worker tried to publish its manifest)", there[:150], "not found" in there.lower() or "RPCError" in there)
    lone = Manifest("production", "kyc", "k-1", "kyc-a", {"kyc.check@1": hashed("kyc.check@1")}, ["KycCheck"])
    published = await said(publish_manifest(client, lone))
    there = await said(registry_handle(client, "production").describe())
    row("D54", "(the same, a manifest published directly)", f"{published[:120]}; the registry: {there[:60]}", not published.startswith("ok") and not there.startswith("ok"))
    never = await said(retire(client, "produciton", REFUND_1, "pia"))
    row("D54", "(a misspelt environment's name in a request makes none)", never[:160], not never.startswith("ok"))


async def production(client: Client) -> None:
    registry = await registry_of(client, "production")
    row("D54", "'An environment is production unless created for development'", f"created with no word of development: development={registry.development}", registry.development is False)
    again = await said(create_environment(client, "production", development=True))
    now = await registry_of(client, "production")
    row("D54", "'a development one can be made production, never the reverse' (creating production again, for development)", f"{again}; development={now.development}", not again.startswith("ok") and now.development is False)
    async with production_worker(client):
        # The in-memory record names no contract, so the probe says two the refund calls, each with a hash no worker serves.
        first = "payments.refund@2"
        wrong = {first: Hash(METHOD, "00" * 32), "orders.lookup@1": Hash(METHOD, "11" * 32)}
        asked = Activating(released(REFUND_1), wrong, QUEUE, {"refunds": ["refunds-a", "ghost-b"]}, "pia")
        refused = await ask(client, "production", "activate", asked)
        row("D54", "'Every problem is said at once, naming contracts, queues, workers, builds and short hashes'; 'every poller has a manifest here ... and serves it with the record's hash'",
            f"done={refused.done}: {refused.said}", not refused.done and len(refused.said) >= 2 and any("ghost-b" in line for line in refused.said) and any(first in line for line in refused.said))
        draft = await refusal(await start_case(client, ProductionCases, REFUND_1, LARGE, "refund-0", QUEUE))
        row("D54", "'A case in an environment asks its registry ... as it opens (the active release ...)' (a release never activated)", draft, "activated" in draft and "can't open" in draft)
        await activated(client, REFUND_1)
        active = await retire(client, "production", REFUND_1, "pia")
        row("D54", "'Retiring: refused while active'", active.said, not active.done)
        case = await start_case(client, ProductionCases, REFUND_1, LARGE, "refund-1", QUEUE)
        await reported(case, lambda now: now.waiting_at == ["review#1"])
        await activated(client, REFUND_2)
        with_open = await retire(client, "production", REFUND_1, "pia")
        row("D54", "'Retiring: refused ... with open cases'", with_open.said, not with_open.done and any("refund-1" in line for line in with_open.said))
        await answer(case, "review#1", "reject", "ana", PEOPLE["ana"])
        await case.result()
        retired = await retire(client, "production", REFUND_1, "pia")
        row("D54", "(once it is neither active nor holds an open case, it is retired, by a named person)", retired.said, retired.done and "pia retired refund 1" in " ".join(retired.said))
        opened = await refusal(await start_case(client, ProductionCases, REFUND_1, LARGE, "refund-9", QUEUE))
        row("D54", "'Retired, a release opens no case'", opened, "refund 1" in opened)
        back = await ask(client, "production", "activate", Activating(released(REFUND_1), dict(REFUND_1.contracts), QUEUE, OPEN_ON, "pia"))
        row("D54", "'... and is never activated again'", f"done={back.done}: {back.said}", not back.done)
        kyc = Activating(Released("kyc", 1, Hash(1, "55" * 32)), {"kyc.check@1": hashed("kyc.check@1")}, QUEUE, {"refunds": ["refunds-a"], "kyc": ["kyc-a"]}, "pia")
        await publish_manifest(client, Manifest("production", "kyc", "k-12", "kyc-a", {"kyc.check@1": hashed("kyc.check@1")}, ["KycCheck"]))
        assert (await ask(client, "production", "activate", kyc)).done
        assert (await ask(client, "production", "opened", Opening("kyc-7", QUEUE, kyc.released))).done
    async with worker_threads() as threads:
        moved = await said(environment_worker(client, QUEUE, Retyped, DevelopmentPlans, FAKES, "b3", "refunds-c", activity_executor=threads, audit=production_audit()))
        kept = await said(environment_worker(client, QUEUE, ProductionCases, DevelopmentPlans, FAKES, "b4", "refunds-d", activity_executor=threads, audit=development_audit()))
    row("D54", "(amended by D81) 'in a production environment one naming a development provider ... is refused' (a worker writing its audit records to the development store)", kept, kept.startswith("ManifestRefused") and "development" in kept)
    row("D54", "'a manifest binding a workflow contract an open case's release calls to another type is refused'", moved, moved.startswith("ManifestRefused"))
    # D65
    async with worker_threads() as threads:
        built = {
            "case_worker": case_worker(client, "q1", DevelopmentCases, DevelopmentPlans, FAKES, activity_executor=threads, audit=development_audit()),
            "plan_worker": plan_worker(client, "q2", DevelopmentPlans, FAKES, activity_executor=threads),
            "environment_worker": await environment_worker(client, "q3", ProductionCases, DevelopmentPlans, FAKES, "b9", "refunds-z", activity_executor=threads, audit=production_audit()),
        }
        RUNNERS.update({name: worker.config()["workflow_runner"] is SANDBOX for name, worker in built.items()})


async def hardened(client: Client) -> None:
    before = (await registry_of(client, "production")).development
    done = await harden(client, "production", "pia")
    after = (await registry_of(client, "production")).development
    row("D54", "'a development one can be made production'", f"development before: {before}; {done.said}; after: {after}", before is True and after is False)


RUNNERS: dict[str, bool] = {}


async def children(client: Client) -> None:
    RUNNERS["registry_worker"] = registry_worker(client).config()["workflow_runner"] is SANDBOX  # built here: only one may hold the registries' queue
    row("D65", "'Every worker Ventoux builds (case_worker, plan_worker, registry_worker) runs its workflows on SANDBOX, from ventoux.temporal.sandbox'", f"workflow_runner is SANDBOX: {RUNNERS}", len(RUNNERS) == 4 and all(RUNNERS.values()))
    parent = await start_case(client, DevelopmentCases, RELEASE, FILE, "claim-7", "cases")
    await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
    await reported(parent, lambda now: "repair#1: case repair, open" in now.waiting_for)
    child = await started(client, DevelopmentCases, "claim-7/repair#1")
    described = await child.describe()
    row("D75", "'A child is its own workflow, <parent ID>/<entry> (claim-7/repair#1)'", f"workflow {described.id}, type {described.workflow_type}, its parent: {described.parent_id}", described.id == "claim-7/repair#1" and described.parent_id == "claim-7")
    policies = [ParentClosePolicy.Name(event.start_child_workflow_execution_initiated_event_attributes.parent_close_policy)
                async for event in parent.fetch_history_events() if event.event_type == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED]
    row("D75", "'Started with ABANDON' ('the policy is tested from the parent's history')", policies, policies == ["PARENT_CLOSE_POLICY_ABANDON"])
    alone = await (await propose_forget(client, DevelopmentForget, "claim-7/repair#1", "pia", ["privacy"], "cases")).result()
    row("D75", "'a child is never forgotten alone, the request refused naming its parent'", f"{alone.status}: {alone.history}", alone.status == "refused" and "claim-7" in " ".join(alone.history))
    try:
        ended = await (await propose_forget(client, DevelopmentForget, "nobody/at-all", "pia", ["privacy"], "cases")).result()
        other, agrees = f"{ended.status}: {ended.history}", ended.status == "refused"
    except Exception as error:
        other, agrees = f"{type(error).__name__}: {error}", True
    row("D75", "'any ID with a / is refused for forgetting alone' (an ID with a / that is no case's child)", other[:300], agrees)
    await reported(child, lambda now: now.waiting_at == ["fix#1"])
    await answer(child, "fix#1", "fixed", "lee", ["support-lead"], {"cost": Decimal(640)})
    await reported(parent, lambda now: now.waiting_at == ["pay_garage.approval#1"])
    handle = case_handle(client, DevelopmentCases, "claim-7")
    await handle.signal("child_ended", "repair#1")
    await handle.signal("child_ended", "repair#1")
    now = await reported(parent, lambda now: sum("child_ended for repair#1" in line for line in now.history) >= 2)
    landed = [line for line in now.history if line.startswith("repair#1 done")]
    rung = [line for line in now.history if "child_ended" in line]
    row("D75", "'A doorbell ... rung twice finds nothing to read: it is recorded and changes nothing' ('a child's end read twice lands once')", f"landed: {len(landed)}; then: {rung}", len(landed) == 1 and len(rung) >= 2 and all("nothing read" in line for line in rung))
    slash = await said(start_case(client, DevelopmentCases, RELEASE, FILE, "claim/8", "cases"))
    row("D75", "'the codec takes a case's key from its workflow ID's first part' (so a case's own ID has no /)", slash, slash.startswith("ValueError"))


in_production(no_registry, create=False)
in_production(production)
in_production(hardened, development=True)
forgetting_on_temporal(children)

print("decision | the brief's claim (quoted, short) | what a run shows | agrees?")
for decision, claim, shown, agrees in ROWS:
    print(f"{decision} | {claim} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{decision}: {claim}" for decision, claim, _, agrees in ROWS if not agrees]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
