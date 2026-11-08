"""The key provider on Temporal, as a production provider makes it matter (layer 19c).

Calls made off the event loop; the audit export saying which service failed; forgetting and
reading with the key service down. Through a development provider that notes or fails its calls,
as `VaultKeys` would: the provider protocol is what the codec, the export and the forget request
use. See docs/layers/19-audit-keys.md (19c) and brief, D78.
"""

import threading
from pathlib import Path

from temporalio.client import Client
from test_audit_export import open_claim
from test_temporal_advisor import ENDS_AT_ONCE
from test_temporal_forget import on_temporal as forgetting_on_temporal

from ventoux.temporal.client import start_plan
from ventoux.temporal.converter import data_converter
from ventoux.temporal.forget import ForgetReport, answer_forget, propose_forget
from ventoux.testing import DevelopmentCases, DevelopmentForget, DevelopmentPlans
from ventoux.tooling.keys import FileKeys, KeyState

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
