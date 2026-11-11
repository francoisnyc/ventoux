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
from ventoux.temporal.forget import (
    CaseEnded,
    ForgetReport,
    answer_forget,
    ending_refusal,
    propose_forget,
)
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


def test_a_closed_case_that_may_be_forgotten_still_is(tmp_path: Path) -> None:
    # The same window, and a definition that allows forgetting: the case refuses the request,
    # being closed, and a closed case can be forgotten, so its key goes once it has ended
    # (brief, D32).
    ended, told, key = closed_then_proposed(claim(), DownAudit(tmp_path / "audit"))
    assert ended.status == "closed"
    assert not ended.forget_taken and ended.forgetting == "allowed"
    assert told.status == "forgotten"
    assert told.history[-1] == "the key of claim-1 was destroyed"
    assert key == "destroyed"


def test_an_open_case_that_keeps_closed_cases_is_forgotten_while_it_is_open() -> None:
    # `while_open` refuses once the case is closed, never before: asked while open, the case
    # takes the request, says so in the report it returns, and its key goes (brief, D32).
    kept = {**claim(), "forgetting": "while_open"}

    async def scenario(client: Client) -> Ended:
        case = await start_case(
            client, QuicklyFailingExports, kept, as_json(FILE), "claim-2", QUEUE
        )
        request = await propose_forget(
            client, DevelopmentForget, "claim-2", "pia", ["privacy"], QUEUE
        )
        await reported(request, lambda now: bool(now.history))
        await answer_forget(request, "approve", "olu", ["privacy"])
        told = await asyncio.wait_for(request.result(), timeout=20)
        return await case.result(), told, keys_of(client).state("claim-2")

    closed, told, key = on_temporal(scenario, cases=QuicklyFailingExports)
    assert closed.forget_taken and closed.forgetting == "while_open"
    assert closed.history[-1] == "closed: forgotten"
    assert told.status == "forgotten"
    assert key == "destroyed"


def ended(forgetting: str, took: bool = False) -> CaseEnded:
    """A case that closed with its own reason, saying `forgetting` of its records."""
    return CaseEnded("closed: nothing left to do", [], forgetting, took)


def test_the_cases_word_as_it_ended_decides_whether_its_key_goes() -> None:
    # A case that took the request is forgotten, whatever closed it. One that didn't was closed
    # already: it is forgotten unless its definition, as it ended, keeps its records. That
    # definition may be stricter than the one the proposal was checked against: a migration
    # moves a case to another release between the two (brief, D32, D53).
    assert ending_refusal("claim-1", ended("while_open", took=True)) is None
    assert ending_refusal("claim-1", ended("allowed")) is None
    assert ending_refusal("claim-1", ended("while_open")) == (
        "claim-1 closed before forgetting was approved, and its definition keeps closed cases "
        "(forgetting: while_open)"
    )
    assert ending_refusal("claim-1", ended("never")) == (
        "claim-1 keeps its records (forgetting: never): it can't be forgotten"
    )
    # No word: the case returned no report (terminated, failed at its opening), or its worker
    # predates this. Its key goes, as before.
    assert ending_refusal("claim-1", ended("")) is None
