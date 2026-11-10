# Shows a case whose definition keeps closed cases (`forgetting: while_open`) forgotten after it closed: it had closed but not yet ended (its audit store was down), the request found it "running", the case refused the approval ("the case is closed"), and the key was destroyed all the same.
"""Run: uv run python reviews/2026-11/probes/p1c_forget_while_open_after_close.py

Supported names used: start_case, answer, retry_export, report, propose_forget, answer_forget,
forget_report, read_audit, FileAudit, FileKeys, data_converter, case_worker. Past them:
`ventoux.testing`, the tests' server harness, and a `FileAudit` subclass that can be down.
"""

import asyncio
import json
import tempfile
from typing import Any

from p1c_harness import QUEUE, ImpatientCases, Setup, on_temporal, until

from ventoux.temporal.cases import answer, retry_export, start_case
from ventoux.temporal.forget import answer_forget, forget_report, propose_forget
from ventoux.testing import DevelopmentForget
from ventoux.tooling.audit import FileAudit, read_audit

NATIONAL_ID = "1 85 05 78 006 084 36"


class Store(FileAudit):
    """The development store, which can be down."""

    down = False

    def append(self, records: list[dict[str, Any]]) -> None:
        if self.down:
            raise OSError("the audit store is down")
        super().append(records)


def claim() -> dict[str, Any]:
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "forgetting": "while_open",  # books and records: a closed claim is kept (brief, D32)
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


async def scenario(setup: Setup) -> bool:
    store = setup.audit
    case = await start_case(
        setup.client, ImpatientCases, claim(), {"national_id": NATIONAL_ID}, "claim-1", QUEUE
    )
    await until(case, lambda now: now.waiting_at == ["assess#1"] and now.unwritten == 0)
    store.down = True
    await answer(case, "assess#1", "deny", "ana", ["adjuster"])
    closed = await until(case, lambda now: now.status == "closed" and bool(now.needs_attention))
    print(
        "the case:",
        closed.status,
        "| its workflow:",
        (await case.describe()).status.name,
        "| unwritten:",
        closed.unwritten,
    )
    print("   last lines:", closed.history[-2:])
    # The case is closed; its definition keeps closed cases. Someone proposes forgetting it.
    request = await propose_forget(
        setup.client, DevelopmentForget, "claim-1", "pat", ["privacy"], QUEUE
    )
    for _ in range(100):
        told = await forget_report(request)
        if told.history:
            break
        await asyncio.sleep(0.05)
    print("the request, after its look-up:", told.status, told.history)
    await answer_forget(request, "approve", "noor", ["privacy"])
    await until(case, lambda now: any("forgetting the case" in line for line in now.history))
    # The store comes back; an operator retries the export; the case ends.
    store.down = False
    await retry_export(case, "omar", ["operations"])
    ended = await asyncio.wait_for(case.result(), timeout=30)
    print("the case's own history, once ended:")
    for line in ended.history:
        print("    ", line)
    told = await asyncio.wait_for(request.result(), timeout=30)
    print("the request:", told.status)
    for line in told.history:
        print("    ", line)
    state = setup.keys.state("claim-1")
    print("key of claim-1:", state)
    shown = json.dumps(
        read_audit(store, "claim-1", ["claims-sensitive"], setup.keys), ensure_ascii=False
    )
    print(
        "read_audit for claims-sensitive: the national ID reads",
        "‹forgotten›" if "‹forgotten›" in shown else "in clear",
    )
    return state == "destroyed"


destroyed = on_temporal(
    scenario, cases=ImpatientCases, audit=Store(tempfile.mkdtemp(prefix="p1c-audit-"))
)
if destroyed:
    print(
        "RESULT: BROKEN - a closed case whose definition says forgetting: while_open refused the "
        "approval, and its key was destroyed anyway"
    )
else:
    print("RESULT: HELD - the closed while_open case kept its key")
