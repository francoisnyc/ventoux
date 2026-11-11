"""A case's requests to forget share one audit stream, numbered on from one to the next
(fix-forget-stream): a second request's records are kept, never refused as other content under a
number the first already used (brief, D77)."""

import asyncio
from pathlib import Path
from typing import Any

from temporalio.client import Client
from test_sensitive import FILE, claim
from test_temporal_forget import QUEUE, on_temporal

from ventoux.temporal.cases import start_case
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import ForgetReport, answer_forget, propose_forget
from ventoux.testing import DevelopmentCases, DevelopmentForget, as_json
from ventoux.tooling.audit import FileAudit
from ventoux.tooling.keys import KeyState


async def asked(client: Client, case: str, by: str, outcome: str | None, approver: str) -> Any:
    """A request to forget `case`, proposed by `by` and, if `outcome`, answered by `approver`:
    its end, within a bound, so one that never ends fails its test."""
    request = await propose_forget(client, DevelopmentForget, case, by, ["privacy"], QUEUE)
    if outcome is not None:
        await answer_forget(request, outcome, approver, ["privacy"])
    return await asyncio.wait_for(request.result(), timeout=15)


def acts(store: FileAudit, stream: str) -> list[tuple[int, str, str | None]]:
    """Each record of `stream` in the store: its number, its act and who made it."""
    return [
        (record["number"], record["act"]["kind"], record["act"]["by"])
        for record in store.read(stream)
        if record["stream"] == stream
    ]


def test_a_second_request_to_forget_is_recorded_after_the_first(tmp_path: Path) -> None:
    # Pia's request is rejected; Quinn's, approved, forgets the case. Both are in the one stream,
    # in order: who proposed, who answered, and the key destroyed (brief, D32, D77). A third,
    # made once the case is forgotten, is refused, ends, and is recorded too.
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[list[ForgetReport], KeyState]:
        await start_case(client, DevelopmentCases, claim(), as_json(FILE), "claim-1", QUEUE)
        ended = [
            await asked(client, "claim-1", "pia", "reject", "olu"),
            await asked(client, "claim-1", "quinn", "approve", "rosa"),
            await asked(client, "claim-1", "pia", None, ""),
        ]
        return ended, keys_of(client).state("claim-1")

    ended, key = on_temporal(scenario, audit=store)
    assert [each.status for each in ended] == ["rejected", "forgotten", "refused"]
    assert key == "destroyed"
    assert acts(store, "claim-1/forget") == [
        (1, "forget proposed", "pia"),
        (2, "answered", "olu"),
        (3, "forget proposed", "quinn"),
        (4, "answered", "rosa"),
        (5, "key destroyed", None),
        (6, "forget proposed", "pia"),
    ]
