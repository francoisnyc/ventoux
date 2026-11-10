# Shows a sensitive option and a sensitive attachment written in plain text in the case's Temporal history, as the input of the activity that checks them, still there once the case is forgotten.
"""Run: uv run python reviews/2026-11/probes/p1c_sensitive_check_in_history.py

Supported names used: start_case, answer, propose_forget, answer_forget, data_converter, FileKeys,
case_worker. Past them: `ventoux.testing` (the development catalog, whose `branches` option check
and `documents` store are the case data guide's), the tests' server harness.
"""

import asyncio
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal, until
from temporalio.api.enums.v1 import EventType

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.temporal.cases import answer, start_case
from ventoux.temporal.forget import answer_forget, propose_forget
from ventoux.testing import CATALOG, DevelopmentCases, DevelopmentForget

SENSITIVE = {"sensitive": True, "visible_to": ["claims-sensitive"]}
BRANCH, SCAN = "BR-0142", "doc-7f3a"  # the two values the development fakes hold


def claim() -> dict[str, Any]:
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {
            "branch": {"type": "option", "system": "branches", "display": {"title": "Branch"}}
            | SENSITIVE,
            "id_scan": {"type": "attachment", "store": "documents", "display": {"title": "Scan"}}
            | SENSITIVE,
        },
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess"},
                "roles": ["adjuster"],
                "outcomes": {
                    "accept": {"display": {"title": "Accept"}, "sets": ["branch", "id_scan"]}
                },
            }
        },
    }


async def in_clear(setup: Setup) -> list[str]:
    """Each event of claim-1's history holding either value in plain text."""
    history = await setup.client.get_workflow_handle("claim-1").fetch_history()
    found = []
    for event in history.events:
        raw = event.SerializeToString()
        for name, value in (("branch", BRANCH), ("id_scan", SCAN)):
            if value.encode() in raw:
                kind = EventType.Name(event.event_type).removeprefix("EVENT_TYPE_")
                activity = event.activity_task_scheduled_event_attributes.activity_type.name
                data = event.activity_task_scheduled_event_attributes.input.payloads[0].data
                found.append(f"{name}: event {event.event_id} {kind} {activity} input {data!r}")
    return found


async def scenario(setup: Setup) -> tuple[list[str], list[str]]:
    errors = [i.code for i in validate_case(parse_case(claim()), CATALOG) if i.severity == "error"]
    print("validation errors:", errors)
    case = await start_case(setup.client, DevelopmentCases, claim(), {}, "claim-1", QUEUE)
    await until(case, lambda now: now.waiting_at == ["assess#1"])
    await answer(
        case, "assess#1", "accept", "ana", ["adjuster"], {"branch": BRANCH, "id_scan": SCAN}
    )
    closed = await until(case, lambda now: now.status == "closed")
    for line in closed.history:
        print("   ", line)
    before = await in_clear(setup)
    request = await propose_forget(
        setup.client, DevelopmentForget, "claim-1", "pat", ["privacy"], QUEUE
    )
    await answer_forget(request, "approve", "noor", ["privacy"])
    told = await asyncio.wait_for(request.result(), timeout=40)
    print("forget request:", told.status, "| key:", setup.keys.state("claim-1"))
    return before, await in_clear(setup)


before, after = on_temporal(scenario)
print("in plain text in the history before forgetting:", *before, sep="\n    ")
print("in plain text in the history after forgetting:", *after, sep="\n    ")
if before or after:
    print(
        "RESULT: BROKEN - a sensitive option and a sensitive attachment cross Temporal in plain "
        "text as their check's input, and stay readable once the case's key is destroyed"
    )
else:
    print("RESULT: HELD - neither value is in plain text in the case's history")
