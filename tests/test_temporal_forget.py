"""Layer 9c on Temporal: forgetting a case, and reading one once its key is gone.

See docs/layers/09-case-data.md (9c) and docs/guides/case-data.md ("Forgetting a person").
"""

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from temporalio import workflow
from temporalio.client import Client, WorkflowHandle, WorkflowQueryFailedError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker
from test_temporal_case import LARGE, REVIEW_FORM, CasesWithPlans, refund_with_plan

from ventoux.temporal.cases import CaseReport, CaseWorkflow, answer, report, start_case
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import (
    ForgetActivities,
    ForgetReport,
    answer_forget,
    forget_report,
    propose_forget,
)
from ventoux.temporal.worker import SANDBOX, case_worker

# Temporal: this module defines a workflow, so the workflow sandbox imports it afresh. What it
# uses from the development setup is passed through, imported once and shared (as in 8c's tests).
with workflow.unsafe.imports_passed_through():
    from test_sensitive import FILE, NATIONAL_ID, claim

    from ventoux.case.memory import Activity
    from ventoux.testing import (
        FAKES,
        DevelopmentCases,
        DevelopmentForget,
        DevelopmentPlans,
        as_json,
        development_converter,
        load_definition,
    )
    from ventoux.tooling.keys import FileKeys, KeyRefused, KeyState

Case = WorkflowHandle[CaseWorkflow, CaseReport]
QUEUE = "cases"


def on_temporal[T](
    scenario: Callable[[Client], Awaitable[T]],
    activities: Mapping[str, Activity] = FAKES,
    cases: type[CaseWorkflow] = DevelopmentCases,
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a case worker serving
    `activities` and requests to forget."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(
            data_converter=development_converter()
        )
        async with (
            environment,
            case_worker(
                environment.client,
                QUEUE,
                cases,
                DevelopmentPlans,
                activities,
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
    raise AssertionError(f"the request never got there: {await forget_report(request)}")


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


# --- Slice 5: the order ---


def test_destroy_refuses_while_the_case_runs() -> None:
    # A second guard on the order: whatever asks it, the key stays while the case's workflow
    # runs, since its work in flight would no longer read its own values (brief, D32).
    async def scenario(client: Client) -> str:
        await open_claim(client, "claim-7")
        with pytest.raises(
            ApplicationError,
            match="^claim-7 is still running: its key is destroyed once its workflow has ended$",
        ):
            await ForgetActivities(client).destroy_key("claim-7")
        return keys_of(client).state("claim-7")

    assert on_temporal(scenario) == "kept"


REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")


def test_the_key_goes_only_after_the_case_has_ended() -> None:
    # Pia and Olu forget the refund while its payment runs. The payment can't be cut off
    # halfway (brief, D10), and while it runs it needs the key to read its own values: the key
    # stays until the case's workflow has ended.
    release = threading.Event()
    paying: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        paying.append(inputs["idempotency_key"])
        release.wait(timeout=10)
        return {"refund_id": "refund-ord-1"}

    async def scenario(client: Client) -> tuple[str, str, ForgetReport, CaseReport, str]:
        case = await start_case(
            client,
            DevelopmentCases,
            REFUND,
            as_json({"order_id": "ord-1", "amount": 40}),
            "refund-1",
            QUEUE,
        )
        form = as_json({"approved_amount": 40})
        await answer(case, "review#1", "approve", "ana", ["support"], form)
        for _ in range(100):  # until the payment runs
            if paying:
                break
            await asyncio.sleep(0.05)
        assert len(paying) == 1  # it runs, once
        request = await propose_forget(
            client, DevelopmentForget, "refund-1", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        waiting = await reported(request, lambda now: now.status == "closing the case")
        assert "refund-1 asked to close as forgotten" in waiting.history
        closing = (await report(case)).status
        kept = keys_of(client).state("refund-1")
        release.set()
        ended = await request.result()
        return closing, kept, ended, await case.result(), keys_of(client).state("refund-1")

    activities = {**FAKES, "payments.refund@2": refund}
    closing, kept, ended, case, key = on_temporal(scenario, activities)
    assert (closing, kept) == ("closing", "kept")
    assert case.history[-1] == "closed: forgotten"
    assert case.flags == ["pay#1 completed after the close was requested"]
    assert ended.history[-3:] == [
        "refund-1 ended: closed: forgotten",
        "refund-1 flagged: pay#1 completed after the close was requested",
        "the key of refund-1 was destroyed",
    ]
    assert (ended.status, key) == ("forgotten", "destroyed")


def test_the_key_goes_only_after_a_child_plan_has_ended() -> None:
    # The same with a plan step: its child workflow, `refund-1/settle#1`, seals with the case's
    # key. Forgotten while the plan's lookup runs, the case stops the plan, the lookup finishes,
    # and only once the case's workflow has ended does the key go.
    release = threading.Event()
    looking_up: list[str] = []

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        looking_up.append(inputs["order_id"])
        release.wait(timeout=10)
        return {"status": "delivered"}

    async def scenario(client: Client) -> tuple[str, str, ForgetReport, CaseReport]:
        case = await start_case(
            client, CasesWithPlans, refund_with_plan(), LARGE, "refund-1", QUEUE
        )
        await answer(case, "review#1", "approve", "ana", ["support"], REVIEW_FORM)
        for _ in range(100):  # until the lookup runs inside the child
            if looking_up:
                break
            await asyncio.sleep(0.05)
        assert looking_up == ["ord-1"]
        request = await propose_forget(
            client, DevelopmentForget, "refund-1", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        await reported(request, lambda now: now.status == "closing the case")
        closing = (await report(case)).status
        kept = keys_of(client).state("refund-1")
        release.set()
        return closing, kept, await request.result(), await case.result()

    activities = {**FAKES, "orders.lookup@1": lookup}
    closing, kept, ended, case = on_temporal(scenario, activities, CasesWithPlans)
    assert (closing, kept) == ("closing", "kept")
    assert "settle#1 cancelled: the case is closing" in case.history
    assert case.history[-1] == "closed: forgotten"
    assert (ended.status, ended.history[-1]) == ("forgotten", "the key of refund-1 was destroyed")


# --- Slice 6: closed cases and records ---


def test_a_case_that_keeps_its_records() -> None:
    # Books and records: the definition says whether the case may be forgotten (brief, D32).
    # Refused before anyone answers, or once it is known the case closed first; nothing is
    # destroyed.
    async def proposed(client: Client, case: str) -> WorkflowHandle[Any, ForgetReport]:
        return await propose_forget(client, DevelopmentForget, case, "pia", ["privacy"], QUEUE)

    async def scenario(client: Client) -> tuple[list[ForgetReport], CaseReport, list[KeyState]]:
        never = await start_case(
            client,
            DevelopmentCases,
            {**claim(), "forgetting": "never"},
            as_json(FILE),
            "claim-7",
            QUEUE,
        )
        kept = {**claim(), "forgetting": "while_open"}
        closed = await start_case(client, DevelopmentCases, kept, as_json(FILE), "claim-8", QUEUE)
        await answer(closed, "assess#1", "deny", "ana", ["adjuster"])
        await closed.result()
        # Open when proposed; closed by its own assessment before the approval reaches it.
        closing = await start_case(client, DevelopmentCases, kept, as_json(FILE), "claim-9", QUEUE)
        racing = await proposed(client, "claim-9")
        await reported(
            racing, lambda now: "pia proposed forgetting claim-9, as privacy" in now.history
        )
        await answer(closing, "assess#1", "deny", "ana", ["adjuster"])
        await closing.result()
        await answer_forget(racing, "approve", "olu", ["privacy"])
        # A key made, but the case's start failed: the ID is spent, and nothing says what its
        # definition kept (brief, D31).
        keys_of(client).create("claim-6")
        ended = [
            await (await proposed(client, "claim-7")).result(),
            await (await proposed(client, "claim-8")).result(),
            await racing.result(),
            await (await proposed(client, "claim-6")).result(),
        ]
        states = [
            keys_of(client).state(case) for case in ("claim-7", "claim-8", "claim-9", "claim-6")
        ]
        return ended, await report(never), states

    ended, never, states = on_temporal(scenario)
    assert [each.status for each in ended] == ["refused"] * 4
    assert [each.history[-1] for each in ended] == [
        (
            "refused pia's proposal: claim-7 keeps its records (forgetting: never): it can't be "
            "forgotten"
        ),
        (
            "refused pia's proposal: claim-8 is closed, and its definition keeps closed cases "
            "(forgetting: while_open)"
        ),
        (
            "refused: claim-9 closed before forgetting was approved, and its definition keeps "
            "closed cases (forgetting: while_open)"
        ),
        (
            "refused pia's proposal: claim-6's definition can't be read: Temporal holds no "
            "history of it, so whether it keeps its records is unknown"
        ),
    ]
    assert never.status == "open"
    assert states == ["kept", "kept", "kept", "kept"]


def test_forgetting_a_closed_case() -> None:
    # Most requests come after the case closed: its key is destroyed without touching it, and it
    # keeps its own close reason.
    async def scenario(client: Client) -> tuple[ForgetReport, CaseReport, str]:
        case = await closed_claim(client, "claim-7")
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        return await request.result(), await case.result(), keys_of(client).state("claim-7")

    ended, case, key = on_temporal(scenario)
    assert ended.status == "forgotten"
    assert ended.history[-4:] == [
        "approved by olu, as privacy",
        "claim-7 was already closed",
        "claim-7 ended: closed: nothing left to do",
        "the key of claim-7 was destroyed",
    ]
    assert (case.history[-1], key) == ("closed: nothing left to do", "destroyed")


def test_a_forgotten_id_opens_no_case() -> None:
    # Its key is never made again (brief, D31), so the ID can't bring the case back.
    async def scenario(client: Client) -> None:
        await closed_claim(client, "claim-7")
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        await request.result()
        with pytest.raises(KeyRefused, match="^a key was already made for claim-7: open the case"):
            await start_case(client, DevelopmentCases, claim(), as_json(FILE), "claim-7", QUEUE)

    on_temporal(scenario)
