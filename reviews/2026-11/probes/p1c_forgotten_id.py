# After a case is forgotten: tries to open its ID again (start_case, start_plan, a child-like ID, other spellings), to forget it twice, to forget a case that never was, a child alone, with the proposer or the opener approving; and reads what the key file holds.
"""Run: uv run python reviews/2026-11/probes/p1c_forgotten_id.py

Supported names used: start_case, answer, report, start_plan, propose_forget, answer_forget,
forget_report, FileKeys, data_converter, case_worker. Past them: `ventoux.testing`, the tests'
server harness.
"""

import asyncio
from typing import Any

from p1c_harness import QUEUE, Setup, files_under, on_temporal, until

from ventoux.core.provenance import sourced
from ventoux.temporal.cases import answer, report, start_case
from ventoux.temporal.client import start_plan
from ventoux.temporal.forget import answer_forget, forget_report, propose_forget
from ventoux.testing import DevelopmentCases, DevelopmentForget, DevelopmentPlans

NATIONAL_ID = "1 85 05 78 006 084 36"
PLAN: dict[str, Any] = {
    "plan": "check-id",
    "version": 1,
    "display": {"title": "Check an ID"},
    "fields": {"id": {"type": "string"}},
    "initial": "check",
    "states": {
        "check": {
            "activity": "orders.lookup@1",
            "inputs": {"order_id": {"var": "id"}},
            "on": {"done": "ok"},
        },
        "ok": {"final": "succeeded"},
    },
}


def claim() -> dict[str, Any]:
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
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess"},
                "roles": ["adjuster"],
                "outcomes": {"deny": {"display": {"title": "Deny"}}},
            }
        },
    }


async def ended(request: Any) -> Any:
    return await asyncio.wait_for(request.result(), timeout=40)


async def scenario(setup: Setup) -> list[str]:
    wrong: list[str] = []
    client, file = setup.client, {"national_id": NATIONAL_ID}

    async def forget(id: str, proposer: str, approver: str | None) -> Any:
        request = await propose_forget(client, DevelopmentForget, id, proposer, ["privacy"], QUEUE)
        if approver is not None:
            await answer_forget(request, "approve", approver, ["privacy"])
        return request

    case = await start_case(
        client, DevelopmentCases, claim(), file, "claim-1", QUEUE, "olga", ["adjuster"]
    )
    await until(case, lambda now: now.waiting_at == ["assess#1"])
    # The proposer, then the opener, each try to approve: refused, the request waits on.
    request = await forget("claim-1", "pat", "pat")
    await answer_forget(request, "approve", "olga", ["privacy"])
    for _ in range(100):
        told = await forget_report(request)
        if len(told.history) >= 3:
            break
        await asyncio.sleep(0.05)
    print("proposer, then opener, approving:", told.status, told.history[1:])
    if told.status != "waiting" or setup.keys.state("claim-1") != "kept":
        wrong.append("the proposer or the opener approved")
    await answer_forget(request, "approve", "noor", ["privacy"])
    print("then someone else:", (await ended(request)).status, "| key", setup.keys.state("claim-1"))
    key_file = setup.keys.path.read_text()
    print(
        "key file now:",
        " ".join(key_file.split()),
        "| files beside it:",
        sorted(
            name for name in files_under(setup.keys.path.parent) if not name.startswith("audit")
        ),
    )
    if setup.keys.state("claim-1") != "destroyed" or '"claim-1": null' not in key_file:
        wrong.append("the key wasn't destroyed")

    # The ID, again.
    for label, opening in (
        (
            "start_case, same ID",
            lambda: start_case(client, DevelopmentCases, claim(), file, "claim-1", QUEUE),
        ),
        (
            "start_case, a child-like ID",
            lambda: start_case(client, DevelopmentCases, claim(), file, "claim-1/again", QUEUE),
        ),
        (
            "start_plan, same ID",
            lambda: start_plan(
                client,
                DevelopmentPlans,
                PLAN,
                {"id": sourced("x", "system:opener")},
                "claim-1",
                QUEUE,
            ),
        ),
    ):
        try:
            await opening()
            wrong.append(f"{label}: it started")
            print(f"{label}: STARTED")
        except Exception as refused:  # noqa: BLE001
            print(f"{label}: refused, {type(refused).__name__}: {refused}")
    # Other spellings are other cases, with their own keys: nothing of claim-1 opens for them.
    other = await start_case(client, DevelopmentCases, claim(), file, "Claim-1", QUEUE)
    await until(other, lambda now: now.waiting_at == ["assess#1"])
    print(
        "start_case 'Claim-1': opens as another case, key",
        setup.keys.state("Claim-1"),
        "| claim-1's key still",
        setup.keys.state("claim-1"),
    )

    # Twice; never was; a child alone: each refused before anyone approves.
    # (Each is read by its report and then terminated: a request for a case that already has a
    # forget stream never ends, which p1c_second_forget_request.py shows.)
    for id in ("claim-1", "claim-404", "claim-1/verify#1", "Claim-1/assess#1"):
        request = await forget(id, "pat", None)
        for _ in range(100):
            told = await forget_report(request)
            if told.status != "waiting" or told.history:
                break
            await asyncio.sleep(0.05)
        print(f"forget {id}: {told.status}: {told.history}")
        if (await request.describe()).status.name == "RUNNING":
            await request.terminate(reason="the probe goes on")
        if told.status != "refused":
            wrong.append(f"forgetting {id} wasn't refused before anyone approved")
    closed = await report(case)
    print("report of claim-1:", closed.status, "|", closed.history[-1])
    await answer(other, "assess#1", "deny", "ana", ["adjuster"])
    return wrong


wrong = on_temporal(scenario, timeout=200)
if wrong:
    print("RESULT: BROKEN - " + "; ".join(wrong))
else:
    print(
        "RESULT: HELD - the proposer and the opener approve nothing; the destroyed key is a null in the key file; the ID opens no case or run again; twice, never-was and a child alone are refused before anyone approves"
    )
