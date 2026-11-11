"""The request to forget decides on the case's own word as it ends (fix-forget-on-the-cases-word).

A case that has closed but not yet ended (its audit records aren't all written) still runs, so
Temporal's "running" never says "open". What the case's definition says of forgetting, and
whether the case took the request, are read from the report the case returns (brief, D32).
"""

import asyncio
from pathlib import Path
from typing import Any

from temporalio.client import Client
from test_audit_export import DownAudit, QuicklyFailingExports
from test_sensitive import FILE, claim
from test_temporal_forget import QUEUE, on_temporal, reported
from test_temporal_sensitive import reported as reported_case

from ventoux.temporal.cases import CaseReport, answer, retry_export, start_case
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import ForgetReport, answer_forget, propose_forget
from ventoux.testing import DevelopmentForget, as_json
from ventoux.tooling.keys import KeyState

Ended = tuple[CaseReport, ForgetReport, KeyState]


def closed_then_proposed(definition: dict[str, Any], store: DownAudit) -> Ended:
    """The claim, denied while its audit store is down: closed, and not ended. Then Pia proposes
    forgetting it and Olu approves; the store comes back, an operator retries the export, and the
    case ends. The case's end, the request's, and where the key stands."""

    async def scenario(client: Client) -> Ended:
        case = await start_case(
            client, QuicklyFailingExports, definition, as_json(FILE), "claim-1", QUEUE
        )
        await reported_case(case, lambda now: now.waiting_at == ["assess#1"] and not now.unwritten)
        store.down = True
        await answer(case, "assess#1", "deny", "ana", ["adjuster"])
        await reported_case(case, lambda now: now.status == "closed" and bool(now.needs_attention))
        request = await propose_forget(
            client, DevelopmentForget, "claim-1", "pia", ["privacy"], QUEUE
        )
        await reported(request, lambda now: bool(now.history))
        await answer_forget(request, "approve", "olu", ["privacy"])
        await reported(request, lambda now: now.status != "waiting")
        store.down = False
        await retry_export(case, "omar", ["operations"])
        ended = await asyncio.wait_for(case.result(), timeout=20)
        told = await asyncio.wait_for(request.result(), timeout=20)
        return ended, told, keys_of(client).state("claim-1")

    return on_temporal(scenario, cases=QuicklyFailingExports, audit=store)


def test_a_case_that_keeps_closed_cases_closed_but_not_ended_is_not_forgotten(
    tmp_path: Path,
) -> None:
    # Closed is the case's word, never Temporal's: with its records unwritten its workflow still
    # runs, and its definition keeps closed cases. The key stays (brief, D32).
    kept = {**claim(), "forgetting": "while_open"}
    ended, told, key = closed_then_proposed(kept, DownAudit(tmp_path / "audit"))
    assert ended.status == "closed"
    assert told.status == "refused"
    assert told.history[-1] == (
        "refused: claim-1 closed before forgetting was approved, and its definition keeps "
        "closed cases (forgetting: while_open)"
    )
    assert key == "kept"
