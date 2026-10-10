"""Layer 8d: workflow steps on Temporal, against Temporal's test server.

The tests play the KYC team: their workflow, `KycCheck`, runs on their own worker and task queue,
bound to the contract `kyc.check@1`. See docs/layers/08-case.md (8d) and docs/guides/cases.md.
"""

import asyncio
import copy
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

from temporalio import activity, workflow
from temporalio.client import Client, WorkflowHandle
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from ventoux.temporal.bindings import Binding
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    CaseWorkflow,
    answer,
    close,
    report,
    retry,
    start_case,
)
from ventoux.temporal.converter import DATA_CONVERTER
from ventoux.temporal.worker import case_worker

# Temporal: this module defines workflows, so the workflow sandbox imports it afresh. The
# development catalog is passed through, imported once and shared (as in 8c's tests).
with workflow.unsafe.imports_passed_through():
    from ventoux.testing import (
        CATALOG,
        FAKES,
        DevelopmentCases,
        DevelopmentPlans,
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
        if inputs["customer_id"] == "c-flaky":
            await workflow.execute_activity(
                "kyc_documents",
                inputs["customer_id"],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        return {
            "status": "clear",
            "risk_score": Decimal(12),
            "analyst_notes": "No concerns in the documents.",
            "contact_email": f"{inputs['customer_id']}@example.com",
        }


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
        "system": "customers",
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
) -> T:
    """Run `scenario` against Temporal's time-skipping test server: our worker serving `cases`,
    and the KYC team's worker serving their workflow on their queue."""

    async def go() -> T:
        environment = await WorkflowEnvironment.start_time_skipping(data_converter=DATA_CONVERTER)
        client = environment.client
        async with (
            environment,
            case_worker(client, CASES, cases, DevelopmentPlans, FAKES),
            Worker(
                client,
                task_queue=KYC,
                workflows=[KycCheck],
                activities=[read_documents],
                activity_executor=ThreadPoolExecutor(),
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
    assert now.needs_attention == ["kyc#1: kyc.check@1 failed: documents unreadable"]


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
        assert failed.needs_attention[0].startswith("kyc#1: kyc.check@1 failed: ")
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
