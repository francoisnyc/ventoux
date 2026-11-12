"""A value given under a name that is no field is kept nowhere on Temporal
(fix-form-value-no-field): not in the case's history, not in the audit store, before forgetting
or after (brief, D89). That it isn't in the state a case continues as new with is shown in
`test_audit_records.py`, on the state as it is carried."""

from pathlib import Path
from typing import Any

from temporalio.client import Client
from test_sensitive import FILE, claim
from test_temporal_forget import QUEUE, on_temporal
from test_temporal_forget_stream import ended, proposed
from test_temporal_sensitive import as_stored, every_run
from test_temporal_sensitive import reported as reported_case

from ventoux.temporal.cases import CaseReport, answer, propose_change, start_case
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import answer_forget
from ventoux.testing import DevelopmentCases, as_json
from ventoux.tooling.audit import FileAudit, read_audit

IN_AN_ANSWER = "STRAY-ANSWER-1985-05-17"  # typed into a box the task doesn't have
IN_AN_EDIT = "STRAY-EDIT-1985-05-17"  # proposed for a field the case doesn't have
REFUSALS = [
    "refused ana's answer accept to assess#1: the answer gives scratch, which accept doesn't set",
    (
        "refused sam's proposal to edit scratch: scratch is not a field of claim: only a "
        "declared field is edited"
    ),
]


def everything_kept(histories: list[Any], folder: Path, shown: list[Any]) -> bytes:
    """Every place a value could have been kept, as bytes to search: each run's history as
    Temporal stores it and as it is exported, the audit store's files, and what `read_audit`
    shows."""
    parts = [part for history in histories for part in as_stored(history)]
    files = [file.read_bytes() for file in sorted(folder.rglob("*")) if file.is_file()]
    return b"\n".join(
        [part if isinstance(part, bytes) else part.encode() for part in parts]
        + files
        + [repr(shown).encode()]
    )


def test_a_value_under_a_name_that_is_no_field_is_kept_nowhere(tmp_path: Path) -> None:
    # Ana answers with a value under a name her task doesn't set, and Sam proposes an edit of a
    # name the case doesn't have. Both are refused and recorded, saying the name. Neither value
    # is anywhere: not in the case's history, not in the store, for any role, before the case is
    # forgotten or after (brief, D89).
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[CaseReport, bytes, list[str], bytes]:
        case = await start_case(client, DevelopmentCases, claim(), as_json(FILE), "claim-1", QUEUE)
        await reported_case(case, lambda now: now.waiting_at == ["assess#1"])
        await answer(case, "assess#1", "accept", "ana", ["adjuster"], {"scratch": IN_AN_ANSWER})
        await propose_change(case, "edit", "scratch", IN_AN_EDIT, "sam", ["support"])
        told = await reported_case(
            case, lambda now: all(line in now.history for line in REFUSALS) and not now.unwritten
        )
        keys = keys_of(client)

        def shown() -> list[Any]:
            return [read_audit(store, "claim-1", roles, keys) for roles in ([], ["adjuster"])]

        before = everything_kept(await every_run(client, "claim-1"), tmp_path, shown())
        # Forgotten while it waits: read by query once the request is over, never by a
        # `result()`, which would let the test server's clock run the case out (the tutor's
        # review of #104).
        request = await proposed(client, "claim-1", "pia")
        await answer_forget(request, "approve", "olu", ["privacy"])
        forgotten = (await ended(request)).history
        after = everything_kept(await every_run(client, "claim-1"), tmp_path, shown())
        return told, before, forgotten, after

    told, before, forgotten, after = on_temporal(scenario, audit=store)
    # Both acts were refused and recorded, and the case went on waiting.
    assert told.waiting_at == ["assess#1"]
    assert b'"refused"' in before
    assert "claim-1 ended: closed: forgotten" in forgotten
    for value in (IN_AN_ANSWER, IN_AN_EDIT):
        assert value.encode() not in before, f"{value} is kept before forgetting"
        assert value.encode() not in after, f"{value} is kept after forgetting"
