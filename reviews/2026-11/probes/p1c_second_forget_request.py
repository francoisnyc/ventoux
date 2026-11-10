# Shows what a SECOND request to forget the same case does to the audit trail: its records collide with the first request's in the one stream `<case>/forget`, so (A) after a rejected request, the request that really forgets the case fails, its approval and "key destroyed" never recorded, and (B) a request made after the case is forgotten never ends, retrying its write without pause.
"""Run: uv run python reviews/2026-11/probes/p1c_second_forget_request.py

Supported names used: start_case, propose_forget, answer_forget, forget_report, read_audit,
FileAudit, FileKeys, case_worker. Past them: `ventoux.testing`, the tests' server harness.
"""

import asyncio
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal, until

from ventoux.temporal.cases import start_case
from ventoux.temporal.forget import answer_forget, forget_report, propose_forget
from ventoux.testing import DevelopmentCases, DevelopmentForget
from ventoux.tooling.audit import read_audit


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


def stream(setup: Setup) -> list[str]:
    """The forget stream of claim-1, as the store keeps it: number, act, who, what was decided."""
    rows = [
        r
        for r in read_audit(setup.audit, "claim-1", [], setup.keys)
        if r["stream"] == "claim-1/forget"
    ]
    return [
        f"{r['number']}: {r['act']['kind']} by {r['act']['by']}: {[d['kind'] for d in r['decisions']]}"
        for r in rows
    ]


async def scenario(setup: Setup) -> list[str]:
    wrong: list[str] = []
    client = setup.client
    case = await start_case(
        client, DevelopmentCases, claim(), {"national_id": "1 85 05"}, "claim-1", QUEUE
    )
    await until(case, lambda now: now.waiting_at == ["assess#1"])

    # A first request, rejected: the case goes on.
    first = await propose_forget(client, DevelopmentForget, "claim-1", "pat", ["privacy"], QUEUE)
    await answer_forget(first, "reject", "noor", ["privacy"])
    print("first request:", (await asyncio.wait_for(first.result(), timeout=30)).status)
    print("   the request's stream:", stream(setup))

    # A. Months later, a second request, approved: the case is forgotten.
    second = await propose_forget(client, DevelopmentForget, "claim-1", "quinn", ["privacy"], QUEUE)
    await answer_forget(second, "approve", "rosa", ["privacy"])
    for _ in range(200):
        if setup.keys.state("claim-1") == "destroyed":
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(3)  # real seconds, for the request to end if it can
    described = await second.describe()
    print("second request's workflow, 3 s after the key went:", described.status.name)
    try:
        told = await asyncio.wait_for(forget_report(second), timeout=5)
        print("   its report:", told.status, told.history)
    except Exception as unread:  # noqa: BLE001 (whatever a request that can't be read says)
        print("   its report can't be read:", type(unread).__name__, str(unread)[:160])
        wrong.append("the request that forgot the case can no longer be read")
    history = await second.fetch_history()
    failed = sum(e.HasField("workflow_task_failed_event_attributes") for e in history.events)
    refused = sum(e.HasField("activity_task_failed_event_attributes") for e in history.events)
    print(
        f"   its history: {refused} write refused (AuditRefused), {failed} workflow task failures so far"
    )
    if described.status.name == "RUNNING":
        wrong.append(
            "the request that forgot the case never ends (its workflow task fails again and again)"
        )
    print("   key of claim-1:", setup.keys.state("claim-1"))
    kept = stream(setup)
    print("   the request's stream now:", kept)
    if not any("rosa" in row for row in kept) or not any("key destroyed" in row for row in kept):
        wrong.append(
            "the audit store holds no record of quinn's proposal, rosa's approval or the key "
            "destroyed"
        )

    # While it runs, no other request for the case can start; an admin terminates it here.
    await second.terminate(reason="the probe goes on")

    # B. A request once the case is forgotten: refused before anyone approves, as D32 says; but
    # does it end?
    third = await propose_forget(client, DevelopmentForget, "claim-1", "pat", ["privacy"], QUEUE)
    await asyncio.sleep(4)  # real seconds
    told = await forget_report(third)
    described = await third.describe()
    pending = described.raw_description.pending_activities
    print(
        "third request, 4 s later:",
        told.status,
        told.history,
        "| its workflow:",
        described.status.name,
    )
    for each in pending:
        print(f"   pending {each.activity_type.name}, attempt {each.attempt}")
    if described.status.name == "RUNNING":
        wrong.append(
            "a request made after the case was forgotten never ends: its write is refused and "
            f"retried without end (attempt {max((p.attempt for p in pending), default=0)} after 4 s)"
        )
    await third.terminate(reason="the probe is done")
    return wrong


wrong = on_temporal(scenario, timeout=200)
if wrong:
    print("RESULT: BROKEN - " + "; ".join(wrong))
else:
    print("RESULT: HELD - each request to forget wrote its own records and ended")
