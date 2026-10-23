"""Layer 9c on Temporal: forgetting a case, and reading one once its key is gone.

See docs/layers/09-case-data.md (9c) and docs/guides/case-data.md ("Forgetting a person").
"""

import asyncio
import json
import logging
import textwrap
import threading
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from temporalio import workflow
from temporalio.api.common.v1 import Payload
from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
    WorkflowHandle,
    WorkflowQueryFailedError,
)
from temporalio.converter import WorkflowSerializationContext
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker
from test_temporal_case import LARGE, REVIEW_FORM, CasesWithPlans, refund_with_plan
from test_temporal_sensitive import (
    TAX_ID,
    SensitiveCases,
    as_stored,
    every_run,
    quoting,
    sensitive_claim,
)
from test_temporal_sensitive import reported as reported_case

from ventoux.temporal import cases
from ventoux.temporal.cases import (
    CaseForgotten,
    CaseReport,
    CaseStart,
    CaseUnanswered,
    CaseWorkflow,
    answer,
    report,
    start_case,
    view,
)
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import (
    CaseLookup,
    CaseOpener,
    ForgetActivities,
    ForgetReport,
    ForgetWorkflow,
    answer_forget,
    closed_first,
    forget_report,
    lookup_refusal,
    opener_refusal,
    propose_forget,
)
from ventoux.temporal.worker import SANDBOX, case_worker

# Temporal: this module defines a workflow, so the workflow sandbox imports it afresh. What it
# uses from the development setup is passed through, imported once and shared (as in 8c's tests).
with workflow.unsafe.imports_passed_through():
    from test_sensitive import FILE, NATIONAL_ID, claim

    from ventoux.case.forgetting import approval_refusal, role_refusal
    from ventoux.case.memory import Activity
    from ventoux.case.state import Schedule
    from ventoux.core.catalog import Catalog
    from ventoux.testing import (
        CATALOG,
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
            await asyncio.wait_for(case.query(CaseWorkflow.report), timeout=10)
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
    # A rejection needs a role registered to forget; the proposer may withdraw their own request,
    # which changes nothing. A new request may then be proposed.
    async def scenario(client: Client) -> tuple[ForgetReport, CaseReport, str, ForgetReport]:
        case = await open_claim(client, "claim-7")
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "reject", "lee", ["support-lead"])
        await answer_forget(request, "reject", "pia", ["privacy"])
        ended = await request.result()
        again = await propose_forget(
            client, DevelopmentForget, "claim-7", "olu", ["privacy"], QUEUE
        )
        waiting = await reported(again, lambda now: bool(now.history))
        return ended, await report(case), keys_of(client).state("claim-7"), waiting

    ended, case, key, again = on_temporal(scenario)
    assert ended.status == "rejected"
    assert ended.history == [
        "pia proposed forgetting claim-7, as privacy",
        (
            "refused lee's answer reject: forgetting claim-7 is rejected by privacy, and lee "
            "has support-lead"
        ),
        "rejected by pia",
    ]
    assert (case.status, case.waiting_for, key) == ("open", ["assess by adjuster"], "kept")
    assert (again.status, again.history) == (
        "waiting",
        ["olu proposed forgetting claim-7, as privacy"],
    )


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


# --- Slice 7: reading a forgotten case ---


async def forgotten_claim(client: Client, id: str) -> Case:
    """The guide's claim, closed, then forgotten by Pia and Olu."""
    case = await closed_claim(client, id)
    request = await propose_forget(client, DevelopmentForget, id, "pia", ["privacy"], QUEUE)
    await answer_forget(request, "approve", "olu", ["privacy"])
    assert (await request.result()).status == "forgotten"
    return case


def test_reading_a_forgotten_case(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="temporalio")

    async def scenario(client: Client) -> CaseReport:
        case = await forgotten_claim(client, "claim-7")
        # The view would hold the case file: refused, saying why.
        with pytest.raises(
            CaseForgotten, match="^claim-7 was forgotten: its case file can't be read$"
        ):
            await view(case, ["claims-sensitive"])
        # Any query sent another way replays the history, which needs the key: it fails at once,
        # with the provider's message, never what the case held.
        forgotten = (
            "the key of claim-7 was destroyed when it was forgotten: its sensitive values can't "
            "be read or written"
        )
        with pytest.raises(WorkflowQueryFailedError) as failed:
            await asyncio.wait_for(case.query(CaseWorkflow.report), timeout=10)
        assert str(failed.value) == f"Failed encoding completion: {forgotten}"
        # So does a replay, as CI's replay tests run one.
        replayer = Replayer(
            workflows=[DevelopmentCases, DevelopmentPlans],
            data_converter=client.data_converter,
            workflow_runner=SANDBOX,
        )
        with pytest.raises(Exception, match=forgotten):
            await replayer.replay_workflow(await case.fetch_history())
        # The worker carries on: the next case answers.
        other = await open_claim(client, "claim-8")
        assert (await report(other)).waiting_for == ["assess by adjuster"]
        return await report(case)

    closing = on_temporal(scenario)
    # The report the case returned when it closed: lines and placeholders, read without a key.
    assert (closing.status, closing.history[-1]) == ("closed", "closed: nothing left to do")
    logged = [logging.Formatter().format(record) for record in caplog.records]
    assert not [line for line in logged if NATIONAL_ID in line]


# --- Slice 8: the audit after forgetting (the curriculum's "check yourself") ---


def stored(payload: Payload) -> Any:
    """A payload's data as Temporal stores it, read as JSON with no converter and no key."""
    return json.loads(payload.data, parse_float=Decimal)


def test_what_the_audit_keeps_after_forgetting() -> None:
    # The richest case 9b planted a national ID in: in the opening, a tax ID in Ana's form, a
    # lookup failing with a message that quotes the ID, a child plan, and several runs. Pia and
    # Olu forget it. What can the audit still show, and what can't it? (brief, D15)
    async def scenario(client: Client) -> Any:
        case = await start_case(
            client, SensitiveCases, sensitive_claim(), as_json(FILE), "claim-7", QUEUE
        )
        await answer(case, "assess#1", "accept", "ana", ["adjuster"], {"tax_id": TAX_ID})
        await reported_case(case, lambda now: len(now.needs_attention) == 2)
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        assert (await request.result()).status == "forgotten"
        runs = await every_run(client, "claim-7")
        child = await every_run(client, "claim-7/check_id#1")
        forgetting = await client.get_workflow_handle("claim-7/forget").fetch_history()
        return client.data_converter, runs, child, forgetting, await report(case)

    converter, runs, child, forgetting, closing = on_temporal(
        scenario, {**FAKES, "orders.lookup@1": quoting}, SensitiveCases
    )
    events = [event for history in runs for event in history.events]

    # Gone for good: no sensitive value in plain text, in what Temporal stores or its export.
    for history in [*runs, *child, forgetting]:
        raw, exported = as_stored(history)
        for value in (NATIONAL_ID, TAX_ID, "1 85 05"):
            assert value.encode() not in raw and value not in exported
    # And what was sealed can't be opened any more: the opening, Ana's form, the failure.
    opening = events[0].workflow_execution_started_event_attributes.input.payloads
    gone = "the key of claim-7 was destroyed when it was forgotten"
    claim_7 = converter.with_context(WorkflowSerializationContext("default", "claim-7"))
    with pytest.raises(KeyRefused, match=gone):
        await_now(claim_7.decode(opening, [Any]))
    [failed] = [
        event.activity_task_failed_event_attributes.failure
        for event in events
        if event.HasField("activity_task_failed_event_attributes")
    ]
    assert failed.message == "Encoded failure"  # its text is only in the sealed part
    with pytest.raises(KeyRefused, match=gone):
        await_now(claim_7.decode_failure(failed))

    # Kept, read with no key: the definition (its rules), each decision, who made it, and as what.
    started = stored(opening[0])
    assert started["definition"]["case"] == "claim"
    assert started["file"]["national_id"] == {"‹sensitive›": 0}
    answers = [
        stored(event.workflow_execution_signaled_event_attributes.input.payloads[0])
        for event in events
        if event.workflow_execution_signaled_event_attributes.signal_name == "answer"
    ]
    assert [(each["entry"], each["outcome"], each["by"], each["roles"]) for each in answers] == [
        ("assess#1", "accept", "ana", ["adjuster"])
    ]
    assert answers[0]["form"] == {"tax_id": {"‹sensitive›": 0}}  # the value sealed, and gone
    [approved] = [
        stored(event.workflow_execution_signaled_event_attributes.input.payloads[0])
        for event in events
        if event.workflow_execution_signaled_event_attributes.signal_name == "forget"
    ]
    assert approved == {
        "proposed_by": "pia",
        "proposer_roles": ["privacy"],
        "approved_by": "olu",
        "approver_roles": ["privacy"],
    }
    # A value that wasn't sensitive stays where the case carried it to its next run.
    carried = stored(
        runs[-1].events[0].workflow_execution_started_event_attributes.input.payloads[0]
    )
    assert carried["carried"]["values"]["estimated_damage"] == Decimal(1200)
    # The case's closing report: its lines, with placeholders, read without a key.
    assert "assess#1 done" in "\n".join(closing.history)
    assert closing.history[-4:] == [
        "forgetting approved by olu as privacy, proposed by pia as privacy",
        "cancelled lookup_id#1: the case is being forgotten",
        "cancelled check_id#1: the case is being forgotten",
        "closed: forgotten",
    ]
    # The request's own history replays with no key at all: none of its payloads is sealed.
    replayer = Replayer(
        workflows=[DevelopmentForget],
        data_converter=development_converter(),
        workflow_runner=SANDBOX,
    )
    asyncio.run(replayer.replay_workflow(forgetting))


def await_now[T](awaitable: Awaitable[T]) -> T:
    """Run one awaitable to its end, outside the test server."""

    async def go() -> T:
        return await awaitable

    return asyncio.run(go())


# --- Slice 9: 9b's gap, an exception nobody retrieves in a case's task ---


# Temporal: a case workflow with an engine bug where it runs an activity, quoting a value.
@workflow.defn(name="ventoux.case")
class BrokenCases(CaseWorkflow):
    catalog = DevelopmentCases.catalog

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)

    async def run_activity(self, command: Schedule) -> None:
        raise ValueError(f"no record for {NATIONAL_ID}")


def test_an_engine_bug_in_a_task_blocks_the_case(caplog: pytest.LogCaptureFixture) -> None:
    # An engine bug never vanishes: the case's workflow task fails, and Temporal retries it until
    # fixed code is deployed (brief, D17). The log keeps the exception's type, never its text,
    # nor the task's description, which quotes it (brief, D31).
    caplog.set_level(logging.DEBUG, logger="temporalio")

    async def scenario(client: Client) -> bytes:
        case = await start_case(client, BrokenCases, claim(), as_json(FILE), "claim-7", QUEUE)
        await answer(case, "assess#1", "deny", "ana", ["adjuster"])
        for _ in range(100):  # until the worker says the workflow task failed
            if any("Failed activation" in record.getMessage() for record in caplog.records):
                break
            await asyncio.sleep(0.05)
        history = await case.fetch_history()
        # Held where the bug struck: the task deciding Ana's answer never completed.
        assert history.events[-1].HasField("workflow_task_started_event_attributes")
        assert (await case.describe()).status == WorkflowExecutionStatus.RUNNING
        return as_stored(history)[0]

    raw = on_temporal(scenario, cases=BrokenCases)
    assert NATIONAL_ID.encode() not in raw  # the failure is sealed with the case's key
    logged = [logging.Formatter().format(record) for record in caplog.records]
    assert any("Failed activation" in line and line.endswith("(ValueError)") for line in logged)
    assert not [line for line in logged if NATIONAL_ID in line]


# --- Slice 10: the guide ---

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "case-data.md").read_text()
FORGETTING = GUIDE.split("## Forgetting a person")[1].split("\n## ")[0]


def guide_blocks() -> list[str]:
    """The Python blocks of the guide's section on forgetting, in order."""
    return [block.split("```")[0] for block in FORGETTING.split("```python\n")[1:]]


def test_the_guides_forget_example_runs_as_written() -> None:
    registering, subclassing, serving, forgetting = guide_blocks()
    # The platform team's part: a role registered to forget, and the request named after the
    # catalog. Our guide, run so it can't drift from the code.
    catalog = Catalog()
    exec(registering, {"catalog": catalog})  # noqa: S102
    assert catalog.forgetters == ["privacy"]
    # Python: `exec` with a module's name, as the guide's code would have in its own module.
    defined: dict[str, Any] = {"__name__": "claim_workflows", "catalog": CATALOG}
    exec(subclassing, defined)  # noqa: S102
    assert issubclass(defined["ClaimForget"], ForgetWorkflow)
    assert defined["ClaimForget"].catalog is CATALOG

    # The rest, with the development workflows in place of the guide's claim workflows.
    async def scenario(client: Client) -> None:
        names: dict[str, Any] = {
            "client": client,
            "case_worker": case_worker,
            "ClaimCases": DevelopmentCases,
            "ClaimPlans": DevelopmentPlans,
            "ClaimForget": DevelopmentForget,
            "implementations": FAKES,
        }
        exec(serving, names)  # noqa: S102
        async with names["worker"]:  # the guide's own worker, on its queue
            case = await start_case(
                client, DevelopmentCases, claim(), as_json(FILE), "claim-7", "claims"
            )
            await answer(case, "assess#1", "deny", "ana", ["adjuster"])
            await case.result()
            # The guide's lines run inside a function: `await` is written as an API caller would.
            exec("async def example():\n" + textwrap.indent(forgetting, "    "), names)  # noqa: S102
            await names["example"]()

    on_temporal(scenario)


def guide_refusal_rows() -> list[tuple[str, str]]:
    """The rows of the forgetting section's "What the engine refuses" table."""
    table = FORGETTING.split("### What the engine refuses")[1]
    rows = [line for line in table.splitlines() if line.startswith("| ")][1:]  # after the header
    return [
        (cells[1].strip(), cells[2].strip().strip("`")) for cells in (r.split("|") for r in rows)
    ]


def refusal(when: str, tmp: Path) -> str:
    """What the engine says, for each of the guide's rows, from the code that says it."""
    support = frozenset({"support"})
    kept = CaseLookup("kept", False, "allowed")
    said: dict[str, Callable[[], str | None]] = {
        "the proposer's roles may not forget": lambda: role_refusal(
            CATALOG, "claim-7", "proposed", "lee", support
        ),
        "the approver's roles may not forget": lambda: role_refusal(
            CATALOG, "claim-7", "approved", "lee", support
        ),
        "the proposer approves their own request": lambda: approval_refusal(
            CATALOG, "claim-7", "pia", "pia", frozenset({"privacy"})
        ),
        "the person who opened the case approves forgetting it": lambda: opener_refusal(
            "claim-7", "olu", CaseOpener("olu")
        ),
        "who opened the case can't be told any more": lambda: opener_refusal(
            "claim-7", "olu", CaseOpener(None, known=False)
        ),
        "no case has that ID": lambda: lookup_refusal(
            "claim-9", CaseLookup("never made", False, "")
        ),
        "the case was already forgotten": lambda: lookup_refusal(
            "claim-7", CaseLookup("destroyed", False, "")
        ),
        "the case is closed and keeps its records": lambda: lookup_refusal(
            "claim-7", CaseLookup("kept", False, "while_open")
        ),
        "the case is never forgotten": lambda: lookup_refusal(
            "claim-7", CaseLookup("kept", True, "never")
        ),
        "the case closed before the approval reached it, and keeps closed cases": lambda: (
            closed_first("claim-7")
        ),
        "the case's definition can't be read any more": lambda: lookup_refusal(
            "claim-7", CaseLookup("kept", False, "")
        ),
        "a forgotten case's history is read or replayed": lambda: destroyed_key(tmp),
    }
    assert lookup_refusal("claim-7", kept) is None  # a case that may be forgotten goes on
    # Anyone but its opener approves; a case a system opened has no opener to refuse.
    assert opener_refusal("claim-7", "eli", CaseOpener("olu")) is None
    assert opener_refusal("claim-7", "eli", CaseOpener(None)) is None
    if when not in said:
        raise LookupError(when)
    message = said[when]()
    assert message is not None
    return message


def destroyed_key(tmp: Path) -> str:
    """What the key provider says when asked to open a part of a forgotten case."""
    tmp.mkdir(exist_ok=True)
    keys = FileKeys(tmp / "keys.json")
    keys.create("claim-7")
    keys.destroy("claim-7")
    with pytest.raises(KeyRefused) as refused:
        keys.open("claim-7", b"", "sensitive/0")
    return str(refused.value)


VIEWED = "the case's file is viewed after forgetting"


def test_every_refusal_in_the_guide_is_tested(tmp_path: Path) -> None:
    rows = [when for when, _ in guide_refusal_rows() if when != VIEWED]
    for when in rows:
        refusal(when, tmp_path / when.replace(" ", "-").replace("'", ""))
    assert VIEWED in [when for when, _ in guide_refusal_rows()]  # on Temporal, below


def test_the_guides_refusals_are_what_the_engine_says(tmp_path: Path) -> None:
    rows = dict(guide_refusal_rows())
    for when, example in rows.items():
        if when != VIEWED:
            folder = tmp_path / when.replace(" ", "-").replace("'", "")
            assert refusal(when, folder) == example, when

    async def viewed(client: Client) -> str:
        case = await forgotten_claim(client, "claim-7")
        with pytest.raises(CaseForgotten) as refused:
            await view(case, ["claims-sensitive"])
        return str(refused.value)

    assert on_temporal(viewed) == rows[VIEWED]


# --- Tutor review: a case that ended without a result ---


def test_forgetting_a_case_that_ended_without_a_result() -> None:
    # A case refused at its opening, and one an operator terminated (brief, D19), have no result
    # to read; their keys still seal the national ID sent at the start. Forgetting waits until
    # the case's latest run no longer runs, however it ended, records how, then destroys the key.
    async def scenario(client: Client) -> list[tuple[ForgetReport, KeyState]]:
        refused = {**as_json(FILE), "colour": "red"}  # a field the claim doesn't declare
        await start_case(client, DevelopmentCases, claim(), refused, "claim-7", QUEUE)
        terminated = await open_claim(client, "claim-8")
        await terminated.terminate(reason="opened twice by mistake")
        ended: list[tuple[ForgetReport, KeyState]] = []
        for case in ("claim-7", "claim-8"):
            request = await propose_forget(
                client, DevelopmentForget, case, "pia", ["privacy"], QUEUE
            )
            await answer_forget(request, "approve", "olu", ["privacy"])
            ended.append((await request.result(), keys_of(client).state(case)))
        return ended

    (refused, refused_key), (terminated, terminated_key) = on_temporal(scenario)
    assert (refused.status, refused_key) == ("forgotten", "destroyed")
    assert refused.history[-2:] == ["claim-7 ended: failed", "the key of claim-7 was destroyed"]
    assert (terminated.status, terminated_key) == ("forgotten", "destroyed")
    assert terminated.history[-2:] == [
        "claim-8 ended: terminated",
        "the key of claim-8 was destroyed",
    ]


def test_a_report_never_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    # A query that gets no answer, as at the moment a case continues as new (layer 8c), is asked
    # again a bounded number of times, then said so; never a wait without end. Here no worker
    # serves the case's queue, so nothing ever answers.
    monkeypatch.setattr(cases, "ASK", timedelta(milliseconds=200))

    async def scenario(client: Client) -> None:
        case = await start_case(
            client, DevelopmentCases, claim(), as_json(FILE), "claim-7", "nobody"
        )
        with pytest.raises(
            CaseUnanswered, match=r"^claim-7 didn't answer in 10 tries of 0\.2s: ask again later$"
        ):
            await asyncio.wait_for(report(case), timeout=10)

    on_temporal(scenario)
