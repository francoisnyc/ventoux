# Starts a case in a production environment with Temporal's client and a start that says it "continued as new" (`carried` set): the case asks no registry, runs a draft where drafts are refused, takes the state it was handed (here: an approval already given), and is listed nowhere.
"""Run: uv run python reviews/2026-11/probes/p1c_forged_continuation.py

The control: the same draft, started with `start_case`, is refused by production's registry.

Supported names used: start_case, answer, report, CaseStart, environment_worker, data_converter.
Past them: Temporal's client for the forged start; `ventoux.temporal.registry` (registry_worker,
create_environment, registry_of); `ventoux.temporal.carried.state_as_data` and `decide`, to make
the state a continued run carries; `tests/production_stand_ins.py`; `ventoux.testing`.
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))

from p1c_harness import until
from p1c_workflows import ProductionCases
from production_stand_ins import production_audit, production_converter
from skipping_server import time_skipping
from temporalio.client import WorkflowFailureError
from worker_threads import worker_threads

from ventoux.case.definition import parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseState, Opened
from ventoux.temporal.carried import state_as_data
from ventoux.temporal.cases import CaseStart, case_handle, start_case
from ventoux.temporal.manifests import environment_worker
from ventoux.temporal.registry import create_environment, registry_of, registry_worker
from ventoux.testing import CATALOG, FAKES, START, DevelopmentPlans, load_definition

ROOT = Path(__file__).resolve().parents[3]
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
FILE = {"order_id": "ord-1", "amount": Decimal(5000)}
QUEUE = "refunds"


def forged_state() -> dict[str, Any]:
    """The state of a refund nobody opened: decided in memory, here, by the caller, up to the
    review approved by `mallory`, so the next thing the case waits for is its payment's approval."""
    case = parse_case(REFUND)
    state, _ = decide(
        case, CATALOG, CaseState("refund-9/forged"), Opened(FILE, "mallory", at=START, engine=3)
    )
    form = {"approved_amount": Decimal(5000)}
    state, _ = decide(
        case,
        CATALOG,
        state,
        Answered("review#1", "approve", "mallory", frozenset({"support"}), form, at=START),
    )
    return state_as_data(state)


async def scenario() -> tuple[str, Any, list[str]]:
    async with (
        time_skipping(production_converter()) as environment,
        registry_worker(environment.client),
    ):
        client = environment.client
        await create_environment(client, "production")
        async with worker_threads() as threads:
            worker = await environment_worker(
                client,
                QUEUE,
                ProductionCases,
                DevelopmentPlans,
                FAKES,
                "build-1",
                "refunds-a",
                activity_executor=threads,
                audit=production_audit(),
            )
            async with worker:
                # Control: the draft, through start_case.
                await start_case(client, ProductionCases, REFUND, FILE, "refund-1", QUEUE)
                try:
                    await asyncio.wait_for(
                        client.get_workflow_handle("refund-1", result_type=None).result(),
                        timeout=20,
                    )
                    refused = "it opened"
                except WorkflowFailureError as failed:
                    refused = str(getattr(failed.cause, "message", failed.cause))
                # The forged start: the same draft, saying it continued as new.
                from ventoux.temporal.converter import keys_of

                keys_of(client).create("refund-9")
                start = CaseStart(REFUND, {}, "mallory", forged_state())
                await client.start_workflow("ventoux.case", start, id="refund-9", task_queue=QUEUE)
                case = case_handle(client, ProductionCases, "refund-9")
                now = await until(case, lambda now: bool(now.history))
                held = await registry_of(client, "production")
                listed = sorted(held.open) if hasattr(held, "open") else [repr(held)]
                return refused, now, listed


refused, now, listed = asyncio.run(asyncio.wait_for(scenario(), timeout=120))
print("control, start_case with the draft in production:", refused)
print("forged start: the case's report:")
print("   status:", now.status, "| release:", now.release, "| engine:", now.engine)
for line in now.history:
    print("    ", line)
print("   waiting at:", now.waiting_at)
print("production's registry lists as open:", listed)
if now.status == "open" and now.history:
    print(
        "RESULT: BROKEN - a start that says it continued as new runs a draft in production, on "
        "a state its caller wrote, asking no registry"
    )
else:
    print("RESULT: HELD - the forged continuation was refused")
