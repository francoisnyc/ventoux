"""Layer 8d: workflow steps on Temporal, against Temporal's test server.

The tests play the KYC team: their workflow, `KycCheck`, runs on their own worker and task queue,
bound to the contract `kyc.check@1`. See docs/layers/08-case.md (8d) and docs/guides/cases.md.
"""

import asyncio
import copy
import functools
import threading
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest
from skipping_server import time_skipping
from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowHandle, WorkflowHistory
from temporalio.common import RetryPolicy
from temporalio.converter import DataConverter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker
from temporalio.workflow import NondeterminismError

from ventoux.core.workflow_contract import WorkflowContract
from ventoux.temporal.bindings import Binding
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    CaseWorkflow,
    answer,
    close,
    propose,
    report,
    retry,
    start_case,
)
from ventoux.temporal.contract_check import cancellation_problems, check_workflow_contract
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import answer_forget, forget_report, propose_forget
from ventoux.temporal.worker import SANDBOX, case_worker

# Temporal: this module defines workflows, so the workflow sandbox imports it afresh. The
# development catalog is passed through, imported once and shared (as in 8c's tests).
with workflow.unsafe.imports_passed_through():
    from ventoux.testing import (
        CATALOG,
        FAKES,
        DevelopmentCases,
        DevelopmentForget,
        DevelopmentPlans,
        development_converter,
        fixture_converter,
        kyc_check,
        load_definition,
        run_case,
    )

CASES = "cases"
KYC = "kyc"  # the KYC team's task queue
REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
FILE = {"order_id": "ord-1", "amount": Decimal(40), "customer_id": "c-1"}
Case = WorkflowHandle[CaseWorkflow, CaseReport]


# The workflow runs that read the documents, by child workflow ID; the first read fails, as a
# system that is down would. An activity: it runs outside the workflow sandbox, on the KYC
# team's worker, and its effects are theirs.
DOCUMENT_READS: list[str] = []


@activity.defn(name="kyc_documents")
def read_documents(customer_id: str) -> str:
    DOCUMENT_READS.append(activity.info().workflow_id or "")
    if len(DOCUMENT_READS) == 1:
        raise ConnectionError("document store unreachable")
    return "readable"


@activity.defn(name="kyc_slow_read")
def slow_read(customer_id: str) -> str:
    """A read that takes half a second of real time: long enough to be running when a contract
    test asks a cancellable workflow to cancel (layer 11c)."""
    threading.Event().wait(0.5)
    return "readable"


def slow_read_of(customer_id: str) -> workflow.ActivityHandle[str]:
    """The slow read, started from a workflow. Cancelled, it is asked to cancel, and the run
    doesn't wait for it to end (Temporal's default for an activity)."""
    return workflow.start_activity(
        "kyc_slow_read",
        customer_id,
        start_to_close_timeout=timedelta(seconds=10),
        result_type=str,
    )


@workflow.defn(name="KycCheck")
class KycCheck:
    """The KYC team's workflow, as Temporal code: its own logic, its own worker."""

    def __init__(self) -> None:
        self.reviewed = False

    # A person's answer: what a workflow step must never wait for (brief, D6). Only the customer
    # `c-waits` waits for it, to show the timeout.
    @workflow.signal(name="reviewed")
    def review(self) -> None:
        self.reviewed = True

    @workflow.run
    async def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if inputs["customer_id"] == "c-fails":
            raise ApplicationError("documents unreadable")
        if inputs["customer_id"] == "c-waits":
            await workflow.wait_condition(lambda: self.reviewed)
        # How a team's cancellable workflow keeps, or breaks, its promise (brief, D40). Each runs to
        # its end when nobody cancels it.
        if inputs["customer_id"] == "c-sleeps":  # keeps it: a timer, cancelled with the run
            await workflow.sleep(60)
        if inputs["customer_id"] == "c-sleeps-again":  # starts a timer after the request
            try:
                await workflow.sleep(60)
            except asyncio.CancelledError:
                await workflow.sleep(1)  # Temporal: a timer, recorded in its history
                raise
        if inputs["customer_id"] == "c-leaves-early":  # ends while its read still runs
            await slow_read_of(inputs["customer_id"])
        if inputs["customer_id"] == "c-reads-locally":  # runs a local activity after the request
            try:
                await workflow.sleep(60)
            except asyncio.CancelledError:
                # Temporal: a local activity runs in the worker, recorded only once it ends.
                await workflow.execute_local_activity(
                    "kyc_slow_read",
                    inputs["customer_id"],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                raise
        if inputs["customer_id"] == "c-completes-anyway":  # its read completes after the request
            read = slow_read_of(inputs["customer_id"])
            try:
                # asyncio: `shield` keeps the run's cancellation from reaching the read, so the
                # read completes after the request.
                await asyncio.shield(read)
            except asyncio.CancelledError:
                await read  # it completes, after the request; then the run ends cancelled
                raise
        if inputs["customer_id"] == "c-flaky":
            await workflow.execute_activity(
                "kyc_documents",
                inputs["customer_id"],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        output: dict[str, Any] = {
            "status": "clear",
            "risk_score": Decimal(12),
            "analyst_notes": "No concerns in the documents.",
            "contact_email": f"{inputs['customer_id']}@example.com",
        }
        # How a team's workflow drifts from its contract, for the contract test to find.
        if inputs["customer_id"] == "c-no-status":
            del output["status"]
        if inputs["customer_id"] == "c-score":
            output["score"] = Decimal(12)
        if inputs["customer_id"] == "c-wordy":
            output["risk_score"] = "low"
        return output


@workflow.defn(name="ventoux.case")
class CasesWithKyc(CaseWorkflow):
    """The development cases, with `kyc.check@1` bound to the KYC team's workflow."""

    catalog = CATALOG
    workflows: ClassVar[Mapping[str, Binding]] = {
        "kyc.check@1": Binding(workflow="KycCheck", task_queue=KYC)
    }

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def with_kyc(**steps: dict[str, Any]) -> dict[str, Any]:
    """The refund with a customer, checked by the guide's `kyc` step, and `steps` after it."""
    definition = copy.deepcopy(REFUND)
    definition["fields"]["customer_id"] = {
        "type": "reference",
        "system": "crm",
        "display": {"title": "Customer"},
    }
    definition["steps"]["kyc"] = {
        "kind": "workflow",
        "display": {"title": "Check the customer"},
        "workflow": "kyc.check@1",
        "inputs": {"customer_id": {"var": "customer_id"}},
    }
    definition["steps"] |= steps
    return definition


def on_temporal[T](
    scenario: Callable[[WorkflowEnvironment], Awaitable[T]],
    cases: type[CaseWorkflow] = CasesWithKyc,
    converter: DataConverter | None = None,
) -> T:
    """Run `scenario` against Temporal's time-skipping test server: our worker serving `cases`,
    and the KYC team's worker serving their workflow on their queue. `converter` holds the keys,
    for a test that replays what it recorded; else fresh ones."""

    async def go() -> T:
        async with (
            time_skipping(converter or development_converter()) as environment,
            case_worker(
                environment.client, CASES, cases, DevelopmentPlans, FAKES, forget=DevelopmentForget
            ),
            Worker(
                environment.client,
                task_queue=KYC,
                workflows=[KycCheck],
                activities=[read_documents, slow_read],
                activity_executor=ThreadPoolExecutor(),
                # Their workflow lives in this test module, which imports Ventoux: the sandbox
                # re-imports the module, so it passes Ventoux through as our worker does.
                workflow_runner=SANDBOX,
            ),
        ):
            # Bounded: a case that hangs (a workflow task retried forever) fails the test.
            return await asyncio.wait_for(scenario(environment), timeout=20)

    return asyncio.run(go())


async def reported(case: Case, holds: Callable[[CaseReport], bool]) -> CaseReport:
    """The case's report once `holds` is true of it, asked a bounded number of times."""
    for _ in range(100):
        now = await report(case)
        if holds(now):
            return now
        await asyncio.sleep(0.05)  # real time, for the workers to take their next tasks
    raise AssertionError(f"the case never got there: {await report(case)}")


REVIEW = ("review#1", "approve")


async def reviewed(
    client: Client,
    definition: dict[str, Any],
    cases: Any = CasesWithKyc,
    customer: str = "c-1",
    id: str = "refund-1",
) -> Case:
    """A case of `definition` for `customer`, opened and reviewed by Ana."""
    file = FILE | {"customer_id": customer}
    case = await start_case(client, cases, definition, file, id=id, task_queue=CASES)
    await answer(case, *REVIEW, by="ana", roles=["support"], form={"approved_amount": Decimal(40)})
    return case


def test_an_unbound_workflow_needs_attention() -> None:
    # The development cases bind no workflow: the step fails, and the case waits for a person.
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        case = await reviewed(environment.client, with_kyc(), DevelopmentCases)
        return await reported(case, lambda now: bool(now.needs_attention))

    now = on_temporal(scenario, cases=DevelopmentCases)
    assert now.needs_attention == ["kyc#1: kyc.check@1 has no binding here: bind it to a workflow"]
    assert now.status == "open"


def test_a_failing_workflow_needs_attention() -> None:
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        case = await reviewed(environment.client, with_kyc(), customer="c-fails")
        return await reported(case, lambda now: bool(now.needs_attention))

    now = on_temporal(scenario)
    assert now.needs_attention == ["kyc#1: kyc.check@1 failed with ApplicationError: ‹sensitive›"]


def test_a_workflow_past_its_timeout_needs_attention() -> None:
    # It waits for a person, which a workflow step must never do: its contract's timeout ends it.
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        case = await reviewed(environment.client, with_kyc(), customer="c-waits")
        await reported(case, lambda now: "started kyc#1" in " ".join(now.history))
        await environment.sleep(timedelta(seconds=601))  # the time-skipping server moves on
        return await reported(case, lambda now: bool(now.needs_attention))

    now = on_temporal(scenario)
    assert now.needs_attention == ["kyc#1: kyc.check@1 didn't finish within its timeout of 600s"]


async def first_run(client: Client, id: str) -> str:
    """The run ID of the case's first run, which its keys carry (brief, D27)."""
    described = await client.get_workflow_handle(id).describe()
    return described.raw_description.workflow_execution_info.first_run_id


def welcome(to_customer: str) -> dict[str, Any]:
    """A welcome letter drafted after the check, addressed with the field `to_customer`."""
    return {
        "kind": "activity",
        "display": {"title": "Draft a welcome letter"},
        "activity": "letters.draft@2",
        "requires": ["kyc"],
        "inputs": {"to_customer": {"var": to_customer}, "template": "welcome"},
    }


def test_an_undeclared_workflow_output_is_refused_on_temporal() -> None:
    # The curriculum's negative test, on Temporal: the KYC team's workflow gave `contact_email`,
    # whose source nobody declared; the letter refuses it, and the case waits for a person.
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        case = await reviewed(environment.client, with_kyc(welcome=welcome("kyc.contact_email")))
        return await reported(case, lambda now: bool(now.needs_attention))

    now = on_temporal(scenario)
    assert now.needs_attention == [
        "welcome#1: letters.draft@2 takes to_customer only from a system or a person, never "
        + "from untrusted data, and this value comes from kyc.contact_email (untrusted:undeclared)"
    ]


def test_a_workflow_step_runs_as_a_bound_child() -> None:
    # The child is the case's ID and the step run, of the type and on the queue its binding names;
    # the case decides as in memory, line for line, its run naming the case and its first run.
    # The check follows the payment, so the order of the lines doesn't depend on timing.
    definition = with_kyc()
    definition["steps"]["kyc"]["requires"] = ["pay"]

    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, str, Any]:
        client = environment.client
        case = await reviewed(client, definition)
        ended = await case.result()
        child = await client.get_workflow_handle("refund-1/kyc#1").describe()
        return ended, await first_run(client, "refund-1"), child

    ended, run_id, child = on_temporal(scenario)
    in_memory = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 40, "customer_id": "c-1"},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people={"ana": ["support"]},
    )
    assert ended.status == "closed"
    assert [line.replace(f"refund-1/{run_id}/", "memory/") for line in ended.history] == (
        in_memory.history
    )
    assert f"run refund-1/{run_id}/kyc#1" in "\n".join(ended.history)
    assert (child.workflow_type, child.task_queue) == ("KycCheck", KYC)


def test_a_failed_child_workflow_is_retried_with_the_same_id_and_key() -> None:
    # The KYC team's document store is down for the first read: the child fails, the case needs
    # attention, an operator retries it, and it runs again under the same ID, so with the same
    # key in every system it reaches (brief, D26).
    DOCUMENT_READS.clear()

    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, str]:
        case = await reviewed(environment.client, with_kyc(), customer="c-flaky")
        failed = await reported(case, lambda now: bool(now.needs_attention))
        assert failed.needs_attention[0].startswith("kyc#1: kyc.check@1 failed with ")
        await retry(case, "kyc#1", by="omar", roles=["operations"])
        return await case.result(), await first_run(environment.client, "refund-1")

    ended, run_id = on_temporal(scenario)
    assert DOCUMENT_READS == ["refund-1/kyc#1", "refund-1/kyc#1"]
    assert ended.status == "closed" and ended.needs_attention == []
    assert (
        ended.history.count(
            f"started kyc#1: workflow kyc.check@1 (customer_id from system:opener), "
            f"run refund-1/{run_id}/kyc#1"
        )
        == 2
    )


DUPLICATE = {"display": {"title": "Duplicate request"}, "roles": ["support"]}
DONE = (
    "kyc#1 done, giving analyst_notes from untrusted:llm; contact_email from untrusted:undeclared; "
    "risk_score from system:kyc; status from system:kyc"
)


async def started(case: Case) -> None:
    """Once the check has started, its child running."""
    await reported(case, lambda now: any(line.startswith("started kyc#1") for line in now.history))


def test_closing_lets_a_workflow_step_finish() -> None:
    # Closed as a duplicate while the check runs: the check isn't cut off (brief, D10); when it
    # ends, what it gave lands, the case is flagged for a person, and closes.
    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, CaseReport]:
        client = environment.client
        definition = with_kyc() | {"close_reasons": {"duplicate": DUPLICATE}}
        case = await reviewed(client, definition, customer="c-waits")
        await started(case)
        await reported(case, lambda now: any(line.startswith("pay#1 done") for line in now.history))
        await close(case, "duplicate", by="ana", roles=["support"])
        closing = await reported(case, lambda now: now.status == "closing")
        await client.get_workflow_handle("refund-1/kyc#1").signal("reviewed")
        return closing, await case.result()

    closing, ended = on_temporal(scenario)
    assert closing.waiting_for == [] and DONE not in closing.history
    assert DONE in ended.history
    assert ended.flags == ["kyc#1 completed after the close was requested"]
    assert ended.status == "closed"


def test_forgetting_waits_for_a_workflow_step() -> None:
    # Layer 9c: forgotten while the KYC team's check runs. The check isn't cut off; the key stays
    # until the case's workflow has ended, then goes (brief, D32).
    async def scenario(environment: WorkflowEnvironment) -> tuple[str, str, CaseReport, str]:
        client = environment.client
        case = await reviewed(client, with_kyc(), customer="c-waits")
        await started(case)
        request = await propose_forget(
            client, DevelopmentForget, "refund-1", "pia", ["privacy"], CASES
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        await reported(case, lambda now: now.status == "closing")
        for _ in range(100):
            if (await forget_report(request)).status == "closing the case":
                break
            await asyncio.sleep(0.05)
        while_checking = (await forget_report(request)).status, keys_of(client).state("refund-1")
        await client.get_workflow_handle("refund-1/kyc#1").signal("reviewed")
        ended = await case.result()
        await request.result()
        return *while_checking, ended, keys_of(client).state("refund-1")

    status, kept, ended, key = on_temporal(scenario)
    assert (status, kept) == ("closing the case", "kept")
    assert ended.flags == ["kyc#1 completed after the close was requested"]
    assert (ended.history[-1], key) == ("closed: forgotten", "destroyed")


@workflow.defn(name="ventoux.case")
class SwitchingCases(CaseWorkflow):
    """The cases with the KYC binding, continuing as new after two events (brief, D27)."""

    catalog = CATALOG
    workflows = CasesWithKyc.workflows
    events_per_run = 2

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


async def runs_of(client: Client, id: str) -> tuple[str, str]:
    """The case's first run ID, and its current one."""
    described = await client.get_workflow_handle(id).describe()
    info = described.raw_description.workflow_execution_info
    return info.first_run_id, info.execution.run_id


def test_a_switch_waits_while_a_workflow_runs() -> None:
    # The case reaches its count with the check running. It must not switch until the check is
    # back: its result would come back to a run that has ended, and be lost (brief, D27).
    staying = with_kyc() | {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}

    async def scenario(environment: WorkflowEnvironment) -> Any:
        client = environment.client
        case = await reviewed(client, staying, cases=SwitchingCases, customer="c-waits")
        await started(case)
        await asyncio.sleep(0.5)  # time enough to switch, were it allowed
        while_running = await runs_of(client, "refund-1")
        await client.get_workflow_handle("refund-1/kyc#1").signal("reviewed")
        checked = await reported(case, lambda now: DONE in now.history)
        await close(case, "duplicate", by="ana", roles=["support"])
        await case.result()
        return while_running, checked, await runs_of(client, "refund-1")

    (first, during), checked, (_, last) = on_temporal(scenario, cases=SwitchingCases)
    assert during == first  # no switch while the check ran
    assert last != first  # and one once it was back
    assert checked.history.count(DONE) == 1


# --- Slice 5: the contract test ---

ACTIVITIES_GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "activities.md"
# Each "Your workflow" cell of the guide's contract-test table, and the customer whose check does
# it in the KYC team's workflow above.
DRIFTS = {
    "returns no `status`": "c-no-status",
    "returns a `score` the contract doesn't have": "c-score",
    "waits for a signal": "c-waits",
    'raises `ApplicationError("documents unreadable")`': "c-fails",
    "declares `cancellable=True`, and starts a timer after the cancellation is requested": (
        "c-sleeps-again"
    ),
    "declares `cancellable=True`, and ends while an activity it started still runs": (
        "c-leaves-early"
    ),
    "declares `cancellable=True`, and ends cancelled though its activity completed after the "
    "request": "c-completes-anyway",
    "declares `cancellable=True`, and ends before it can be cancelled": "c-1",
    "declares `cancellable=True`, and runs a local activity after the cancellation is requested": (
        "c-reads-locally"
    ),
}
# The same check, whose team promises it stops cleanly when cancelled (brief, D40).
KYC_CANCELLABLE = kyc_check.model_copy(update={"version": 3, "cancellable": True})


def contract_test_rows() -> list[tuple[str, str]]:
    """The rows of the guide's table of what the contract test says, as (workflow, says)."""
    text = ACTIVITIES_GUIDE.read_text()
    table = text.split("| Your workflow | The contract test says |")[1].split("\n\n")[0]
    rows = [line for line in table.splitlines() if line.startswith("| ")]
    return [
        (cells[1].strip(), cells[2].strip().strip("`")) for cells in (r.split("|") for r in rows)
    ]


def contract_test_of(customer: str, contract: WorkflowContract = kyc_check) -> list[str]:
    """What the contract test says of the KYC team's workflow, checking `customer`."""

    async def scenario(environment: WorkflowEnvironment) -> list[str]:
        binding = CasesWithKyc.workflows["kyc.check@1"]
        return await check_workflow_contract(
            environment.client, contract, binding, {"customer_id": customer}
        )

    return on_temporal(scenario)


def test_the_contract_test_finds_each_broken_promise() -> None:
    rows = contract_test_rows()
    assert [drift for drift, _ in rows] == list(DRIFTS)
    for drift, says in rows:
        contract = KYC_CANCELLABLE if "cancellable=True" in drift else kyc_check
        # The guide writes code in marks; the problem reads without them.
        assert contract_test_of(DRIFTS[drift], contract) == [says.replace("`", "")], drift
    [mistyped] = contract_test_of("c-wordy")
    assert mistyped.startswith(
        "kyc.check@1 gave an output its contract doesn't declare: risk_score:"
    )


def test_the_kyc_workflow_keeps_its_contract() -> None:
    assert contract_test_of("c-1") == []


def test_the_contract_test_checks_cancellation() -> None:
    # A cancellable workflow's promise in three parts, read from its history once the test has
    # asked it to cancel: it schedules nothing new, it ends only once all it started has ended,
    # and it ends cancelled only if nothing it started completed after the request (brief, D40).
    # A timer cancelled with its run keeps it; each drift above breaks one part, and the rows of
    # the guide's table say which (test_the_contract_test_finds_each_broken_promise).
    assert contract_test_of("c-sleeps", KYC_CANCELLABLE) == []
    # Not cancellable: no second run, so a workflow that would break the promise isn't asked.
    assert contract_test_of("c-sleeps-again") == []

    # A second run no worker takes never starts: the test says so, and doesn't wait for ever.
    async def unserved(environment: WorkflowEnvironment) -> list[str]:
        binding = Binding(workflow="KycCheck", task_queue="nobody-serves-this")
        return await cancellation_problems(
            environment.client, KYC_CANCELLABLE, binding, {"customer_id": "c-sleeps"}
        )

    never = (
        "kyc.check@3 is cancellable, and its run for the cancellation never started: run its "
        "worker, and fix what fails its first workflow task"
    )
    assert on_temporal(unserved) == [never]


def test_the_guides_contract_test_runs_as_written() -> None:
    # The guide's example, the fourth Python block of the activities guide, with the KYC team's
    # workflow above as its `KycCheck`.
    example = ACTIVITIES_GUIDE.read_text().split("```python\n")[4].split("```")[0]
    # The guide's worker, given the runner that passes Ventoux through: here the KYC team's
    # workflow lives in this test module, which imports Ventoux (see `on_temporal`).
    worker = functools.partial(Worker, workflow_runner=SANDBOX)
    namespace: dict[str, Any] = {"Worker": worker, "KycCheck": KycCheck, "kyc_check": kyc_check}
    exec(example, namespace)  # noqa: S102 -- our guide, run so it can't drift from the code

    async def go() -> None:
        async with time_skipping(development_converter()) as environment:
            await namespace["test_kyc_check_keeps_its_contract"](environment)

    asyncio.run(go())


# --- Slice 6: replay ---


def replay(
    history: WorkflowHistory, workflow_class: type[CaseWorkflow], converter: DataConverter
) -> None:
    """Replay `history` against `workflow_class`, as a worker would after a restart, with the
    converter that recorded it: its sealed parts open only with their keys (brief, D31)."""
    replayer = Replayer(
        workflows=[workflow_class], data_converter=converter, workflow_runner=SANDBOX
    )
    asyncio.run(replayer.replay_workflow(history))


def checked_and_retried(converter: DataConverter) -> WorkflowHistory:
    """The history of a case whose check failed once, was retried by an operator, and closed,
    its parts sealed by `converter`."""
    DOCUMENT_READS.clear()

    async def scenario(environment: WorkflowEnvironment) -> WorkflowHistory:
        case = await reviewed(environment.client, with_kyc(), customer="c-flaky")
        await reported(case, lambda now: bool(now.needs_attention))
        await retry(case, "kyc#1", by="omar", roles=["operations"])
        await case.result()
        return await case.fetch_history()

    return on_temporal(scenario, converter=converter)


@workflow.defn(name="ventoux.case")
class RetypedCases(CaseWorkflow):
    """The same cases, with `kyc.check@1` bound to another workflow type."""

    catalog = CATALOG
    workflows: ClassVar[Mapping[str, Binding]] = {
        "kyc.check@1": Binding(workflow="KycCheckV2", task_queue=KYC)
    }

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


@workflow.defn(name="ventoux.case")
class RequeuedCases(CaseWorkflow):
    """The same cases, with `kyc.check@1` moved to another task queue."""

    catalog = CATALOG
    workflows: ClassVar[Mapping[str, Binding]] = {
        "kyc.check@1": Binding(workflow="KycCheck", task_queue="kyc-v2")
    }

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def test_a_case_history_with_its_workflow_type_changed_fails_replay() -> None:
    # The type of each child a case started is in its history: bound to another type under a case
    # that started one, replay refuses, and the case waits until the binding is put back.
    with pytest.raises(NondeterminismError):
        converter = development_converter()
        replay(checked_and_retried(converter), RetypedCases, converter)


BEFORE_11C = Path(__file__).parent / "histories" / "before_11c_workflow_closed.json"


def test_a_workflow_history_from_before_11c_replays() -> None:
    # Recorded under 11b's driver: the check runs on through Ana's close, completes, and the case
    # is flagged. 11c starts a workflow step so that it can be cancelled, which a step whose
    # contract isn't cancellable never is, so the new worker replays it (brief, D29, D40). Ana's
    # review is sealed with the case's key, kept beside the fixture.
    history = WorkflowHistory.from_json("refund-1", BEFORE_11C.read_text())
    replay(history, CasesWithKyc, fixture_converter(BEFORE_11C))


def test_a_case_history_replays() -> None:
    # A failed child, an operator's retry, the child started again and its output: all read back
    # from the case's history, nothing done again.
    converter = development_converter()
    history = checked_and_retried(converter)
    replay(history, CasesWithKyc, converter)
    # Moving the workflow to another task queue is an operations change (brief, D5): the case's
    # history still replays.
    replay(history, RequeuedCases, converter)


# --- Layer 11c: a cancellable workflow step, stopped by a rule or a close (brief, D40) ---


def with_cancellable_kyc_catalog() -> Any:
    """The development catalog, and `kyc.check@3`, the check whose team promises it stops
    cleanly when cancelled."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register(KYC_CANCELLABLE)
    return catalog


@workflow.defn(name="ventoux.case")
class CasesWithCancellableKyc(CaseWorkflow):
    """The development cases, with `kyc.check@3` bound to the KYC team's workflow."""

    catalog = with_cancellable_kyc_catalog()
    workflows: ClassVar[Mapping[str, Binding]] = {
        "kyc.check@3": Binding(workflow="KycCheck", task_queue=KYC)
    }

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def withdrawn_kyc() -> dict[str, Any]:
    """The refund checked by `kyc.check@3`, with a support task logging a withdrawal, a rule that
    stops the check once it is logged, and a close reason."""
    definition = with_kyc()
    definition["steps"]["kyc"]["workflow"] = "kyc.check@3"
    definition["milestones"] = {"withdrawn": {"display": {"title": "Withdrawn"}}}
    definition["steps"]["log_withdrawal"] = {
        "kind": "task",
        "display": {"title": "Log the customer's withdrawal"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"logged": {"display": {"title": "Withdrawn"}, "reaches": ["withdrawn"]}},
    }
    definition["rules"] = {
        "withdraw": {
            "display": {"title": "Stop the check when the customer withdraws"},
            "on": {"reached": "withdrawn"},
            "then": {"stop": ["kyc"]},
        }
    }
    return definition | {"close_reasons": {"duplicate": DUPLICATE}}


async def withdrawn(case: Case) -> None:
    """Ana logs the customer's withdrawal."""
    await propose(case, "log_withdrawal", by="ana", roles=["support"])
    await reported(case, lambda now: "log_withdrawal#1" in now.waiting_at)
    await answer(case, "log_withdrawal#1", "logged", by="ana", roles=["support"])


def cancel_requests(history: WorkflowHistory) -> list[Any]:
    """The cancellations a case asked of its children, in its history."""
    asked = EventType.EVENT_TYPE_REQUEST_CANCEL_EXTERNAL_WORKFLOW_EXECUTION_INITIATED
    return [event for event in history.events if event.event_type == asked]


def test_a_stopped_cancellable_workflow_is_cancelled_on_temporal() -> None:
    # The check sleeps when the customer withdraws: the rule's stop cancels it through Temporal,
    # its reason naming the rule's entry only; the case waits for it to end cancelled, flags it,
    # and closes (brief, D40). The payment is let finish first: the case records events in the
    # order they reach it, so a payment still running would land its line anywhere in the
    # three asserted below (fix-flaky-temporal).
    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, str, list[Any]]:
        client = environment.client
        case = await reviewed(
            client, withdrawn_kyc(), cases=CasesWithCancellableKyc, customer="c-sleeps"
        )
        await started(case)
        await reported(case, lambda now: any(line.startswith("pay#1 done") for line in now.history))
        await withdrawn(case)
        ended = await case.result()
        child = await client.get_workflow_handle("refund-1/kyc#1").fetch_history()
        asked = next(
            event.workflow_execution_cancel_requested_event_attributes.cause
            for event in child.events
            if event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCEL_REQUESTED
        )
        return ended, asked, cancel_requests(await case.fetch_history())

    ended, asked, requests = on_temporal(scenario, cases=CasesWithCancellableKyc)
    stopping = ended.history.index("withdraw#1 on reached withdrawn: stopping kyc")
    assert ended.history[stopping + 1 : stopping + 4] == [
        "kyc#1: stop requested by withdraw#1",
        "kyc#1 cancelled: stopped by withdraw#1",
        "flagged: kyc#1 cancelled after its stop was requested by withdraw#1",
    ]
    assert asked == "stopped by withdraw#1"
    assert len(requests) == 1 and ended.status == "closed"


def test_a_child_is_cancelled_once_on_temporal() -> None:
    # The check takes a while to cancel, finishing its read first; Ana closes the case meanwhile.
    # The close asks nothing again: one cancellation request in the case's history (brief, D40).
    async def scenario(environment: WorkflowEnvironment) -> tuple[CaseReport, list[Any]]:
        client = environment.client
        case = await reviewed(
            client, withdrawn_kyc(), cases=CasesWithCancellableKyc, customer="c-completes-anyway"
        )
        await started(case)
        await withdrawn(case)
        await reported(case, lambda now: "kyc#1: stop requested by withdraw#1" in now.history)
        await close(case, "duplicate", by="ana", roles=["support"])
        ended = await case.result()
        return ended, cancel_requests(await case.fetch_history())

    ended, requests = on_temporal(scenario, cases=CasesWithCancellableKyc)
    assert len(requests) == 1
    assert ended.history[-1] == "closed: duplicate, by ana"
    assert "kyc#1 cancelled: stopped by withdraw#1" in ended.history


def test_a_workflow_step_cancelled_from_outside_needs_attention() -> None:
    # From the review: someone cancels the check from outside the case, with Temporal's tools.
    # The case never asked, so nothing it does explains it: the step failed, and waits for a
    # person, as before 11c. Until the fix it read "cancelled: the case is closing", and the case
    # closed with the check skipped (brief, D17, D40).
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        client = environment.client
        case = await reviewed(client, with_kyc(), customer="c-waits")
        await started(case)
        await client.get_workflow_handle("refund-1/kyc#1").cancel()
        return await reported(case, lambda now: bool(now.needs_attention))

    now = on_temporal(scenario)
    assert now.needs_attention == ["kyc#1: kyc.check@1 failed with CancelledError: ‹sensitive›"]
    assert now.status == "open" and now.flags == []


def test_a_workflow_stopped_as_it_starts_is_cancelled_on_temporal() -> None:
    # From the review: a rule on the check's own start stops it in the decision that starts it,
    # before the child exists. The driver keeps the cancellation, and sends it once the child
    # has started (brief, D40).
    async def scenario(environment: WorkflowEnvironment) -> CaseReport:
        definition = withdrawn_kyc()
        definition["rules"] = {
            "hold_back": {
                "display": {"title": "Hold the check back"},
                "on": {"started": "kyc"},
                "then": {"stop": ["kyc"]},
            }
        }
        case = await reviewed(
            environment.client, definition, cases=CasesWithCancellableKyc, customer="c-sleeps"
        )
        return await reported(
            case, lambda now: "kyc#1 cancelled: stopped by hold_back#1" in now.history
        )

    now = on_temporal(scenario, cases=CasesWithCancellableKyc)
    assert "flagged: kyc#1 cancelled after its stop was requested by hold_back#1" in now.history


OUTSIDE_CANCEL = Path(__file__).parent / "histories" / "before_11c_workflow_cancelled_outside.json"


def test_a_history_with_an_outside_cancel_from_before_11c_replays() -> None:
    # Recorded under 11b's driver, from main: someone cancels the check from outside the case, it
    # fails and needs attention, an operator retries it, and it completes. 11c records a
    # cancellation the case didn't ask for as that same failure, so the new worker replays it
    # (brief, D17, D40); read as a stop, the case would have closed, and replay failed.
    history = WorkflowHistory.from_json("refund-1", OUTSIDE_CANCEL.read_text())
    replay(history, CasesWithKyc, fixture_converter(OUTSIDE_CANCEL))
