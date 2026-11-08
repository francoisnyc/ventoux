"""The key provider on Temporal, as a production provider makes it matter (layer 19c).

Calls made off the event loop; the audit export saying which service failed; forgetting and
reading with the key service down. Through a development provider that notes or fails its calls,
as `VaultKeys` would: the provider protocol is what the codec, the export and the forget request
use. See docs/layers/19-audit-keys.md (19c) and brief, D78.
"""

import asyncio
import threading
from pathlib import Path

from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from test_audit_export import QuicklyFailingExports, open_claim
from test_temporal_advisor import ENDS_AT_ONCE
from test_temporal_case import reported
from test_temporal_forget import on_temporal as forgetting_on_temporal
from test_temporal_workflow_step import KYC_CANCELLABLE, CasesWithKyc
from test_temporal_workflow_step import on_temporal as contract_on_temporal

from ventoux.case.state import CaseState
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.cases import CaseReport, retry_export
from ventoux.temporal.client import start_plan
from ventoux.temporal.contract_check import check_workflow_contract
from ventoux.temporal.converter import data_converter
from ventoux.temporal.forget import ForgetReport, answer_forget, forget_report, propose_forget
from ventoux.testing import DevelopmentCases, DevelopmentForget, DevelopmentPlans
from ventoux.tooling.keys import FileKeys, KeyRefused, KeyState, KeyUnavailable

QUEUE = "cases"


class NotingThreads(FileKeys):
    """A development provider that notes the thread each call ran on: a test's own."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.calls: list[tuple[str, int]] = []  # each call's name, and its thread's identity

    def noted(self, call: str) -> None:
        self.calls.append((call, threading.get_ident()))

    def create(self, case: str) -> None:
        self.noted("create")
        super().create(case)

    def seal(self, case: str, data: bytes, part: str) -> bytes:
        self.noted("seal")
        return super().seal(case, data, part)

    def open(self, case: str, data: bytes, part: str) -> bytes:
        self.noted("open")
        return super().open(case, data, part)

    def destroy(self, case: str) -> None:
        self.noted("destroy")
        super().destroy(case)

    def state(self, case: str) -> KeyState:
        self.noted("state")
        return super().state(case)


def test_no_provider_call_runs_on_the_event_loop(tmp_path: Path) -> None:
    # A call to the key service waits a round trip, and its whole timeout while the service is
    # down: made on the event loop, it would stall every workflow and activity on the worker, and
    # the client's other calls. So each is made on a thread: the client opening a case, the codec
    # sealing and opening, the forget request reading and destroying the key (brief, D78).
    keys = NotingThreads(tmp_path / "keys.json")

    async def scenario(client: Client) -> tuple[ForgetReport, int]:
        loop = threading.get_ident()  # the event loop's thread: client, worker and codec share it
        await open_claim(client, DevelopmentCases)
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        plan = ENDS_AT_ONCE | {"fields": {}}  # a plan that asks for nothing, and ends
        run = await start_plan(client, DevelopmentPlans, plan, {}, "run-1", QUEUE)
        await run.result()
        return await request.result(), loop

    ended, loop = forgetting_on_temporal(scenario, converter=data_converter(keys))
    assert ended.status == "forgotten"
    made = [call for call, _ in keys.calls]
    assert set(made) >= {"create", "seal", "open", "state", "destroy"}  # each kind was made
    assert made.count("create") == 2  # the case's key, and the plan run's
    on_the_loop = sorted({call for call, thread in keys.calls if thread == loop})
    assert on_the_loop == []


DOWN = (
    "the key service at https://vault.internal:8200 can't be reached: claim-7's sensitive values "
    "can't be read or written now"
)
LEAVES = "the key of claim-7 can leave the key service (exportable): it is not used"


class SealingForTheExport(FileKeys):
    """A development provider whose sealing for the audit export fails, as `VaultKeys` would:
    unavailable, or refused for good. The case's own payloads seal as usual. A test's own."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.failing: Exception | None = None  # what sealing for the export raises, if anything
        self.tries = 0  # how many times the export tried to seal while failing

    def seal(self, case: str, data: bytes, part: str) -> bytes:
        if part.startswith("audit/") and self.failing is not None:
            self.tries += 1
            raise self.failing
        return super().seal(case, data, part)


def exporting_once_fixed(keys: SealingForTheExport) -> tuple[CaseReport, CaseReport]:
    """The claim's reports once its export failed, and once an operator retried it with the key
    service back."""

    async def scenario(client: Client) -> tuple[CaseReport, CaseReport]:
        case = await open_claim(client, QuicklyFailingExports)
        failed = await reported(case, lambda now: bool(now.needs_attention))
        keys.failing = None  # the key service back
        await retry_export(case, "omar", ["operations"])
        return failed, await reported(case, lambda now: now.unwritten == 0)

    return forgetting_on_temporal(
        scenario, cases=QuicklyFailingExports, converter=data_converter(keys)
    )


def test_an_export_that_cant_seal_names_the_key_service(tmp_path: Path) -> None:
    # The export's failure says which service failed, sending the operator to the key service,
    # not the store. Unavailable, it is retried as a store that is down is; refused for good (a
    # key that can leave Vault), it fails at once, never retried (brief, D77) (brief, D78).
    for failing, said, tries in (
        (KeyUnavailable(DOWN), DOWN, 2),  # QuicklyFailingExports tries twice
        (KeyRefused(LEAVES), LEAVES, 1),
    ):
        keys = SealingForTheExport(tmp_path / f"{tries}.json")
        keys.failing = failing
        failed, written = exporting_once_fixed(keys)
        assert failed.needs_attention == [
            f"audit export failed: {said}: look at the key service, then retry the export"
        ]
        assert keys.tries == tries
        assert written.needs_attention == []


def test_which_service_failed_crosses_continue_as_new() -> None:
    # A case whose export failed runs nothing, so it may switch: the next run still sends the
    # operator to the key service (brief, D27) (brief, D78). A state carried before 19c says the
    # store, as it did.
    state = CaseState("claim-7", export_failed=DOWN, export_service="the key service")
    carried = state_from_data(state_as_data(state), {})
    assert (carried.export_failed, carried.export_service) == (DOWN, "the key service")
    before = state_as_data(CaseState("claim-7", export_failed="the store failed"))
    del before["export_service"]
    assert state_from_data(before, {}).export_service == "the store"


class DownFor(FileKeys):
    """A development provider unavailable for the calls named in `down`, as `VaultKeys` is when
    Vault doesn't answer: a test's own."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.down: set[str] = set()  # the calls that fail, while they do
        self.failed: list[str] = []  # each call that failed, in order

    def failing(self, call: str) -> None:
        if call in self.down:
            self.failed.append(call)
            raise KeyUnavailable(DOWN)

    def state(self, case: str) -> KeyState:
        self.failing("state")
        return super().state(case)

    def destroy(self, case: str) -> None:
        self.failing("destroy")
        super().destroy(case)


def test_with_the_key_service_down_a_proposal_to_forget_is_refused_saying_so(
    tmp_path: Path,
) -> None:
    # Before anyone answers, nothing was decided: the proposal is refused, saying why and what to
    # do, never "there is no case" or "already forgotten", which an unreachable Vault would be if
    # its silence were read as an answer (brief, D32) (brief, D78).
    keys = DownFor(tmp_path / "keys.json")

    async def scenario(client: Client) -> ForgetReport:
        await open_claim(client, DevelopmentCases)
        keys.down = {"state"}
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        return await request.result()

    refused = forgetting_on_temporal(scenario, converter=data_converter(keys))
    assert refused.status == "refused"
    assert refused.history == [f"refused pia's proposal: {DOWN}: propose again once it answers"]


def test_with_the_key_service_down_an_approved_request_waits_then_forgets(tmp_path: Path) -> None:
    # After the approval, the request waits for the key service, closing the case, and never ends
    # without destroying the key: once the service answers, the key goes (brief, D17) (brief, D78).
    keys = DownFor(tmp_path / "keys.json")

    async def scenario(client: Client) -> tuple[ForgetReport, ForgetReport, str]:
        await open_claim(client, DevelopmentCases)
        keys.down = {"destroy"}
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        for _ in range(200):  # bounded: until the destroy has failed twice, so was retried
            if keys.failed.count("destroy") >= 2:
                break
            await asyncio.sleep(0.05)
        waiting = await forget_report(request)
        kept = keys.state("claim-7")
        keys.down = set()
        return waiting, await request.result(), kept

    waiting, ended, kept = forgetting_on_temporal(scenario, converter=data_converter(keys))
    assert keys.failed.count("destroy") >= 2
    assert (waiting.status, kept) == ("closing the case", "kept")
    assert (ended.status, ended.history[-1]) == ("forgotten", "the key of claim-7 was destroyed")


def test_the_contract_test_makes_its_runs_keys_off_the_event_loop(tmp_path: Path) -> None:
    # A contract test's runs have keys, as every run Ventoux starts: made on a thread, as a case's
    # are, both the run checked and the one asked to cancel (brief, D78) (tutor review of #92).
    keys = NotingThreads(tmp_path / "keys.json")

    async def scenario(environment: WorkflowEnvironment) -> tuple[list[str], int]:
        loop = threading.get_ident()
        binding = CasesWithKyc.workflows["kyc.check@1"]  # the same workflow, bound once
        said = await check_workflow_contract(
            environment.client, KYC_CANCELLABLE, binding, {"customer_id": "c-sleeps"}
        )
        return said, loop

    said, loop = contract_on_temporal(scenario, converter=data_converter(keys))
    assert said == []
    made = [thread for call, thread in keys.calls if call == "create"]
    assert len(made) == 2  # the run checked, and the run asked to cancel
    assert loop not in made
