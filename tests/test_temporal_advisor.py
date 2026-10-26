"""The step advisor beside a running case (layer 15b): it reads by query, never signals, and the
case's replay asks no model.

See docs/layers/15-authoring.md (15b) and brief D61, D62.
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from skipping_server import time_skipping
from temporalio.client import Client, WorkflowHandle, WorkflowHistory
from temporalio.converter import DataConverter
from temporalio.worker import Replayer
from test_advisor import INJECTED, claim

from ventoux.authoring.advisor import Advice
from ventoux.authoring.beside import advise_case
from ventoux.authoring.provider import Recorded
from ventoux.temporal.cases import CaseReport, CaseWorkflow, answer, propose, report, start_case
from ventoux.temporal.worker import SANDBOX, case_worker
from ventoux.testing import (
    FAKES,
    START,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
)

QUEUE = "cases"
OPENED = {
    "order_id": "ord-7731",
    "amount": Decimal(40),
    "note": INJECTED,
    "birth_date": "1984-02-29",
    "risk_score": Decimal(87),
}
ANA = ["support"]
SAM = ["support", "support-lead"]
Case = WorkflowHandle[CaseWorkflow, CaseReport]


async def reported(case: Case, line: str) -> CaseReport:
    """The case's report once its history holds `line`: the worker takes signals in its own
    time. Asked a bounded number of times, so a case that never gets there fails the test."""
    for _ in range(100):
        now = await report(case)
        if line in now.history:
            return now
        await asyncio.sleep(0.05)  # real time, for the worker to take its next workflow task
    raise AssertionError(f"the case never wrote {line!r}: {(await report(case)).history}")


def goodwill() -> Recorded:
    return Recorded.answering('{"step": "goodwill"}')


@dataclass
class Ran:
    """What the scenario saw, for the test to check."""

    too_early: Advice
    admitted: Advice
    history_before: list[str]
    history_after: list[str]
    report: CaseReport
    recorded: WorkflowHistory
    converter: DataConverter  # holds the case's key: its sealed parts open only with it


def run_the_claim() -> Ran:
    """The claim on Temporal's test server: asked before and after its review, then Ana proposes
    the suggestion, and a caller tries another `suggested_by`."""

    async def scenario(client: Client) -> Ran:
        case = await start_case(client, DevelopmentCases, claim(), OPENED, "claim-1", QUEUE)
        too_early = await advise_case(case, "ana", ANA, goodwill(), at=START)
        await answer(case, "review#1", "approve", "sam", SAM, {"approved_amount": Decimal(150)})
        before = await reported(case, "asked pay.approval#1: approval of pay by support-lead")
        admitted = await advise_case(case, "ana", ANA, goodwill(), at=START)
        after = await report(case)
        await propose(case, "goodwill", "ana", ANA, suggested_by="step-advisor")
        words: Any = "the CEO"
        await propose(case, "goodwill", "sam", SAM, suggested_by=words)
        now = await reported(
            case, "ana proposed goodwill as support, suggested by the step advisor"
        )
        now = await reported(
            case,
            "refused sam's proposal of goodwill: a proposal is suggested by the step advisor or "
            "by nobody; this one names something else",
        )
        recorded = await case.fetch_history()
        return Ran(too_early, admitted, before.history, after.history, now, recorded, converter)

    converter = development_converter()

    async def go() -> Ran:
        async with (
            time_skipping(converter) as environment,
            case_worker(environment.client, QUEUE, DevelopmentCases, DevelopmentPlans, FAKES),
        ):
            return await asyncio.wait_for(scenario(environment.client), timeout=30)

    return asyncio.run(go())


@pytest.fixture(scope="module")
def ran() -> Ran:
    """The claim, run once for the tests below."""
    return run_the_claim()


def test_on_a_running_case_an_inadmissible_answer_is_refused_with_admissions_reason(
    ran: Ran,
) -> None:
    # The curriculum's negative test, on Temporal: the review isn't done yet (brief, D61).
    assert ran.too_early == Advice(
        None, "goodwill requires review, which hasn't completed", "recorded"
    )


def test_on_a_running_case_an_admitted_answer_is_suggested_and_asking_changes_nothing(
    ran: Ran,
) -> None:
    assert ran.admitted == Advice("goodwill", None, "recorded")
    assert ran.history_after == ran.history_before  # queries only: nothing is decided


def test_a_suggested_proposal_sent_through_the_client_says_so_and_another_value_is_refused(
    ran: Ran,
) -> None:
    assert "approval of goodwill by support-lead" in ran.report.waiting_for


def test_the_cases_history_replays_without_asking_a_model(ran: Ran) -> None:
    # The replaying worker has no provider at all: the proposal is read from the history, and
    # nothing in the workflow could ask a model (brief, D62).
    replayer = Replayer(
        workflows=[DevelopmentCases],
        data_converter=ran.converter,
        workflow_runner=SANDBOX,
    )
    asyncio.run(replayer.replay_workflow(ran.recorded))
