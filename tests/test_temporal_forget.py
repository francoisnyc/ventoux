"""Layer 9c on Temporal: forgetting a case, and reading one once its key is gone.

See docs/layers/09-case-data.md (9c) and docs/guides/case-data.md ("Forgetting a person").
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from temporalio import workflow
from temporalio.client import Client, WorkflowHandle, WorkflowQueryFailedError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from ventoux.temporal.cases import CaseReport, CaseWorkflow, answer, report, start_case
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import ForgetReport, answer_forget, forget_report, propose_forget
from ventoux.temporal.worker import SANDBOX, case_worker

# Temporal: this module defines a workflow, so the workflow sandbox imports it afresh. What it
# uses from the development setup is passed through, imported once and shared (as in 8c's tests).
with workflow.unsafe.imports_passed_through():
    from test_sensitive import FILE, NATIONAL_ID, claim

    from ventoux.testing import (
        FAKES,
        DevelopmentCases,
        DevelopmentForget,
        DevelopmentPlans,
        as_json,
        development_converter,
    )
    from ventoux.tooling.keys import FileKeys

Case = WorkflowHandle[CaseWorkflow, CaseReport]
QUEUE = "cases"


def on_temporal[T](scenario: Callable[[Client], Awaitable[T]]) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a case worker."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(
            data_converter=development_converter()
        )
        async with (
            environment,
            case_worker(
                environment.client,
                QUEUE,
                DevelopmentCases,
                DevelopmentPlans,
                FAKES,
                forget=DevelopmentForget,
            ),
            Worker(environment.client, task_queue="signals", workflows=[SignalsAnEndedCase]),
        ):
            return await asyncio.wait_for(scenario(environment.client), timeout=30)

    return asyncio.run(go())


async def closed_claim(client: Client, id: str) -> Case:
    """The guide's claim, holding a national ID, denied and so closed."""
    case = await start_case(client, DevelopmentCases, claim(), as_json(FILE), id, QUEUE)
    await answer(case, "assess#1", "deny", "ana", ["adjuster"])
    assert (await case.result()).status == "closed"
    return case


def remove_key_by_hand(client: Client, case: str) -> None:
    """Take `case`'s key out of the development key file, as destroying it will (slice 1)."""
    keys = keys_of(client)
    assert isinstance(keys, FileKeys)
    stored = json.loads(keys.path.read_text())
    del stored[case]
    keys.path.write_text(json.dumps(stored))


# --- Slice 0: what Temporal does without a key, today ---


def test_a_closed_case_read_without_its_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="temporalio")

    async def scenario(client: Client) -> None:
        case = await closed_claim(client, "claim-7")
        before = await case.fetch_history()
        remove_key_by_hand(client, "claim-7")
        # The result the case returned when it closed holds no sensitive part: read without a key.
        assert (await case.result()).history[-1] == "closed: nothing left to do"
        # A query replays the history, which needs the key: it fails at once, saying so. The
        # SDK can't seal its failure either (no key), so it sends the codec's own error in its
        # place: the case's name, never what the failure said.
        with pytest.raises(WorkflowQueryFailedError) as failed:
            await asyncio.wait_for(report(case), timeout=10)
        assert str(failed.value) == (
            "Failed encoding completion: there is no key for claim-7, so its sensitive values "
            "can't be read or written"
        )
        # The worker carries on: the next case answers.
        other = await closed_claim(client, "claim-8")
        assert (await report(other)).status == "closed"
        # A replay, as CI's replay tests run, fails the same way.
        replayer = Replayer(
            workflows=[DevelopmentCases, DevelopmentPlans],
            data_converter=client.data_converter,
            workflow_runner=SANDBOX,
        )
        with pytest.raises(Exception, match="no key for claim-7"):
            await replayer.replay_workflow(before)

    on_temporal(scenario)
    logged = [logging.Formatter().format(record) for record in caplog.records]
    assert not [line for line in logged if NATIONAL_ID in line]


# Temporal: a workflow that signals another, as the forget request will signal its case.
@workflow.defn(name="test.signals-an-ended-case")
class SignalsAnEndedCase:
    @workflow.run
    async def run(self, case: str) -> str:
        try:
            await workflow.get_external_workflow_handle(case).signal("close", {})
        except ApplicationError as refused:
            return f"refused: {refused.message}"
        return "signalled"


def test_a_signal_to_an_ended_case() -> None:
    async def scenario(client: Client) -> list[Any]:
        await closed_claim(client, "claim-7")
        return [
            await client.execute_workflow(
                SignalsAnEndedCase.run, case, id=f"{case}/forget", task_queue="signals"
            )
            for case in ("claim-7", "claim-9")  # ended, and never started
        ]

    # Temporal says the same of a case that ended and one that never existed: the request must
    # ask the key provider which it is (9c, "How it works", step 2).
    not_found = "refused: Unable to signal external workflow because it was not found"
    assert on_temporal(scenario) == [not_found, not_found]


# --- Slice 4: the request on Temporal ---


async def open_claim(client: Client, id: str) -> Case:
    """The guide's claim, holding a national ID, waiting for its assessment."""
    return await start_case(client, DevelopmentCases, claim(), as_json(FILE), id, QUEUE)


def test_a_proposal_without_the_role_is_refused() -> None:
    async def scenario(client: Client) -> ForgetReport:
        await open_claim(client, "claim-7")
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "lee", ["support-lead"], QUEUE
        )
        return await request.result()

    ended = on_temporal(scenario)
    assert ended.status == "refused"
    assert ended.history == [
        "refused lee's proposal: forgetting claim-7 is proposed by privacy, and lee has support-lead"
    ]


async def reported(
    request: WorkflowHandle[Any, ForgetReport], holds: Callable[[ForgetReport], bool]
) -> ForgetReport:
    """The request's report once `holds` is true of it, asked a bounded number of times."""
    for _ in range(200):
        now = await forget_report(request)
        if holds(now):
            return now
        await asyncio.sleep(0.05)
    raise AssertionError("the request never got there")


def test_refused_answers_are_recorded_and_the_request_waits() -> None:
    async def scenario(client: Client) -> ForgetReport:
        await open_claim(client, "claim-7")
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        # The curriculum's negative test, on Temporal: recorded, and the request waits on.
        await answer_forget(request, "approve", "pia", ["privacy"])
        await answer_forget(request, "approve", "lee", ["support-lead"])
        await answer_forget(request, "forget", "olu", ["privacy"])
        return await reported(request, lambda now: len(now.history) == 4)

    now = on_temporal(scenario)
    assert now.status == "waiting"
    assert now.history == [
        "pia proposed forgetting claim-7, as privacy",
        "refused pia's answer approve: pia proposed forgetting claim-7, so cannot approve it",
        (
            "refused lee's answer approve: forgetting claim-7 is approved by privacy, and lee "
            "has support-lead"
        ),
        "refused olu's answer forget: a request to forget is answered approve or reject",
    ]


def test_forgetting_needs_a_case_with_a_key() -> None:
    # Temporal can't tell a case that ended from one that never was (slice 0); the key provider
    # can, and remembers a destroyed key after Temporal has dropped its case.
    async def scenario(client: Client) -> list[ForgetReport]:
        await open_claim(client, "claim-8")
        keys_of(client).destroy("claim-8")  # forgotten before
        ended = []
        for case in ("claim-9", "claim-8"):
            request = await propose_forget(
                client, DevelopmentForget, case, "pia", ["privacy"], QUEUE
            )
            ended.append(await request.result())
        return ended

    never, already = on_temporal(scenario)
    assert (never.status, never.history) == (
        "refused",
        ["refused pia's proposal: there is no case claim-9: no key was ever made for it"],
    )
    assert (already.status, already.history) == (
        "refused",
        ["refused pia's proposal: claim-8 was already forgotten: its key was destroyed"],
    )


def test_a_rejected_request_changes_nothing() -> None:
    async def scenario(client: Client) -> tuple[ForgetReport, CaseReport, str]:
        case = await open_claim(client, "claim-7")
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "reject", "olu", ["privacy"])
        return await request.result(), await report(case), keys_of(client).state("claim-7")

    ended, case, key = on_temporal(scenario)
    assert ended.status == "rejected"
    assert ended.history == ["pia proposed forgetting claim-7, as privacy", "rejected by olu"]
    assert (case.status, case.waiting_for, key) == ("open", ["assess by adjuster"], "kept")


def test_forgetting_an_open_case() -> None:
    async def scenario(client: Client) -> tuple[ForgetReport, CaseReport, str]:
        case = await open_claim(client, "claim-7")
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        return await request.result(), await case.result(), keys_of(client).state("claim-7")

    ended, case, key = on_temporal(scenario)
    assert ended.status == "forgotten"
    assert ended.history == [
        "pia proposed forgetting claim-7, as privacy",
        "approved by olu, as privacy",
        "claim-7 asked to close as forgotten",
        "claim-7 ended: closed: forgotten",
        "the key of claim-7 was destroyed",
    ]
    assert case.history[-3:] == [
        "forgetting approved by olu as privacy, proposed by pia as privacy",
        "cancelled assess#1: the case is being forgotten",
        "closed: forgotten",
    ]
    assert key == "destroyed"
