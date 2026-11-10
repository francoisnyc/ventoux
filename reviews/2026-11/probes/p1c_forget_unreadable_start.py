# Asks to forget (1) a case refused at its opening because its definition doesn't read, and (2) a standalone plan run: each holds sealed values under a key, and the request neither refuses nor goes on: it waits in silence.
"""Run: uv run python reviews/2026-11/probes/p1c_forget_unreadable_start.py

Supported names used: start_case, start_plan (ventoux.temporal.client), answer (the plan's),
propose_forget, forget_report, FileKeys, data_converter, case_worker. Past them: `ventoux.testing`
and the tests' server harness.
"""

import asyncio
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal
from temporalio.api.enums.v1 import EventType

from ventoux.core.provenance import sourced
from ventoux.temporal.cases import start_case
from ventoux.temporal.client import start_plan
from ventoux.temporal.forget import forget_report, propose_forget
from ventoux.testing import DevelopmentCases, DevelopmentForget, DevelopmentPlans

NATIONAL_ID = "1 85 05 78 006 084 36"


def unreadable() -> dict[str, Any]:
    """A claim with a sensitive field, and a step of a kind that doesn't exist: refused when the
    case opens (`CaseInvalid`), after the client sealed the national ID into its start."""
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {
            "national_id": {
                "type": "string",
                "sensitive": True,
                "visible_to": ["claims-sensitive"],
                "display": {"title": "National ID"},
            }
        },
        "steps": {"assess": {"kind": "ritual", "display": {"title": "Assess"}}},
    }


async def waits(setup: Setup, id: str) -> tuple[str, list[str], int, int]:
    """Propose forgetting `id`; after 8 real seconds: the request's status, its lines, how often
    its look-up was tried, and how often it failed."""
    request = await propose_forget(setup.client, DevelopmentForget, id, "pat", ["privacy"], QUEUE)
    await asyncio.sleep(8)
    told = await forget_report(request)
    described = await request.describe()
    pending = described.raw_description.pending_activities
    attempts = max((each.attempt for each in pending), default=0)
    name = pending[0].activity_type.name if pending else "none"
    history = await request.fetch_history()
    failed = sum(e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED for e in history.events)
    print(
        f"{id}: the request is {told.status!r}, lines {told.history}; pending activity {name}, "
        f"attempt {attempts}; key {setup.keys.state(id)}"
    )
    return told.status, told.history, attempts, failed


async def scenario(setup: Setup) -> list[str]:
    stuck: list[str] = []
    # 1. A case refused at its opening: its start holds the sealed national ID.
    case = await start_case(
        setup.client, DevelopmentCases, unreadable(), {"national_id": NATIONAL_ID}, "claim-1", QUEUE
    )
    for _ in range(100):
        status = (await case.describe()).status
        if status is not None and status.name != "RUNNING":
            break
        await asyncio.sleep(0.05)
    print("claim-1's workflow:", status.name if status else None)
    status_1, lines_1, attempts_1, _ = await waits(setup, "claim-1")
    if status_1 == "waiting" and not lines_1 and attempts_1 > 1:
        stuck.append("a case whose definition doesn't read")

    # 2. A standalone plan run, whose key is made as a case's is (brief, D31).
    plan = {
        "plan": "check-id",
        "version": 1,
        "display": {"title": "Check an ID"},
        "fields": {"id": {"type": "string"}},
        "initial": "check",
        "states": {
            "check": {
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "id"}},
                "on": {"done": "checked"},
            },
            "checked": {"final": "succeeded"},
        },
    }
    fields = {"id": sourced("ord-1", "system:opener")}
    try:
        await start_plan(setup.client, DevelopmentPlans, plan, fields, "run-1", QUEUE)
    except Exception as error:  # noqa: BLE001
        print("the plan run didn't start:", type(error).__name__, error)
    status_2, lines_2, attempts_2, _ = await waits(setup, "run-1")
    if status_2 == "waiting" and not lines_2 and attempts_2 > 1:
        stuck.append("a standalone plan run")
    return stuck


stuck = on_temporal(scenario, timeout=120)
if stuck:
    print(
        "RESULT: BROKEN - a request to forget waits in silence, its look-up failing again and "
        f"again, nothing refused and nothing said, for: {', '.join(stuck)}"
    )
else:
    print("RESULT: HELD - each request was refused saying why, or went on")
