"""The audit export: what is written, sealed, and where it is kept (layer 19b).

Through `exported`, the store, the case on Temporal and `read_audit`. See
docs/layers/19-audit-keys.md (19b), docs/guides/audit.md and brief, D77.
"""

import asyncio
import base64
import dataclasses
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from skipping_server import time_skipping
from temporalio.client import Client, WorkflowHistory
from test_audit_records import checked_claim, known
from test_case import REFUND
from test_sensitive import FILE, NATIONAL_ID
from test_temporal_case import QUEUE, on_temporal
from worker_threads import worker_threads

from ventoux.case.audit import AuditRecord
from ventoux.case.definition import parse_case
from ventoux.temporal.audit import ExportRefused, exported, sensitive_fields
from ventoux.temporal.cases import CaseReport, answer, start_case
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    FAKES,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
    run_case,
)
from ventoux.tooling.audit import AuditRefused, FileAudit
from ventoux.tooling.keys import FileKeys, KeyRefused


def claim_records() -> tuple[dict[str, Any], list[AuditRecord]]:
    """The sensitive claim's definition, and its records at engine 3: the national ID read by a
    step's condition and computed into its input."""
    definition = checked_claim()
    run = run_case(
        definition,
        FILE,
        [],
        {"ana": ["adjuster"]},
        activities={"orders.lookup@1": known},
        engine=3,
    )
    return definition, run.audit


def unwrapped(record: AuditRecord) -> AuditRecord:
    """`record` with the national ID its act gave in clear: what a bug unwrapping it would give."""
    values = {**record.act.values, "national_id": NATIONAL_ID}
    return dataclasses.replace(record, act=dataclasses.replace(record.act, values=values))


def test_a_sensitive_value_in_clear_fails_the_export(tmp_path: Path) -> None:
    # The curriculum's negative test: a record holding a sensitive field's value in clear is never
    # written, whatever let it through. Read from the definition, never from the wrapper, so a
    # value unwrapped by mistake is still caught (brief, D31) (brief, D77).
    definition, records = claim_records()
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    sensitive = sensitive_fields(parse_case(definition))
    with pytest.raises(ExportRefused) as refused:
        exported("claim-7", [unwrapped(records[0]), *records[1:]], sensitive, keys)
    assert str(refused.value) == (
        "audit record claim-7/1 holds national_id, a sensitive field, in clear: nothing was written"
    )
    assert NATIONAL_ID not in str(refused.value)
    # Wrapped, it is sealed under the case's key, for its own place, where alone it opens.
    [opening, *_] = exported("claim-7", records, sensitive, keys)
    sealed = opening["act"]["values"]["national_id"]
    assert NATIONAL_ID not in str(opening)
    assert sealed["part"] == "audit/claim-7/1/act/values/national_id"
    assert sealed["visible_to"] == ["claims-sensitive"]
    ciphertext = base64.b64decode(sealed["sealed"])
    assert keys.open("claim-7", ciphertext, sealed["part"]) == f'"{NATIONAL_ID}"'.encode()
    with pytest.raises(KeyRefused):
        keys.open("claim-7", ciphertext, "audit/claim-7/2/act/values/national_id")


def numbered(stream: str, number: int, said: str = "") -> dict[str, Any]:
    """A record as the export writes it, reduced to what the store reads: its stream and number."""
    return {"stream": stream, "number": number, "lines": [said]}


def test_the_store_keeps_each_record_once_in_order(tmp_path: Path) -> None:
    store = FileAudit(tmp_path / "audit")
    store.append([numbered("claim-7", 1, "opened"), numbered("claim-7", 2, "answered")])
    # The same record again is kept once: a write retried after a crash duplicates nothing.
    store.append([numbered("claim-7", 2, "answered"), numbered("claim-7", 3, "closed")])
    # A gap, or a record kept with other content, is refused, and nothing of the call is kept.
    with pytest.raises(AuditRefused) as gap:
        store.append([numbered("claim-7", 4), numbered("claim-7", 6)])
    assert str(gap.value) == "audit record claim-7/6 can't be kept: claim-7/5 is missing"
    with pytest.raises(AuditRefused) as changed:
        store.append([numbered("claim-7", 3, "reopened")])
    assert str(changed.value) == "audit record claim-7/3 is already kept, with other content"
    # A case's records, its children's and its requests', each stream in order.
    store.append([numbered("claim-7/repair#1", 1), numbered("claim-7/forget", 1)])
    store.append([numbered("claim-70", 1)])  # another case, whose ID begins the same
    kept = [(each["stream"], each["number"]) for each in store.read("claim-7")]
    assert kept == [
        ("claim-7", 1),
        ("claim-7", 2),
        ("claim-7", 3),
        ("claim-7/forget", 1),
        ("claim-7/repair#1", 1),
    ]


def test_a_case_worker_without_a_store_is_refused() -> None:
    # A case would run with no trail (brief, D77).
    async def build() -> None:
        async with (
            time_skipping(development_converter()) as environment,
            worker_threads() as threads,
        ):
            with pytest.raises(ValueError) as refused:
                case_worker(
                    environment.client,
                    "refunds",
                    DevelopmentCases,
                    DevelopmentPlans,
                    FAKES,
                    activity_executor=threads,
                    audit=None,
                )
            assert str(refused.value) == (
                "a case worker needs an audit store: give case_worker audit=…"
            )

    asyncio.run(build())


# The small refund, as the API sends it: exact numbers (brief, D20).
FORTY = Decimal(40)
SMALL = {"order_id": "ord-1", "amount": FORTY}


def scheduled(history: WorkflowHistory) -> list[str]:
    """The activities a case's run scheduled, by type, in order, as its history recorded them."""
    return [
        event.activity_task_scheduled_event_attributes.activity_type.name
        for event in history.events
        if event.HasField("activity_task_scheduled_event_attributes")
    ]


def test_the_quickstarts_refund_is_exported_on_temporal(tmp_path: Path) -> None:
    # Opened at engine 3, the case writes every record to the store, in order, in its own stream,
    # before it ends: the history line for line (brief, D77).
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory]:
        case = await start_case(client, DevelopmentCases, REFUND, SMALL, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", ["support"], {"approved_amount": FORTY})
        return await case.result(), await case.fetch_history()

    ended, history = on_temporal(scenario, audit=store)
    assert (ended.status, ended.engine) == ("closed", 3)
    written = store.read("refund-1")
    assert [(each["stream"], each["number"]) for each in written] == [
        ("refund-1", number) for number in range(1, len(written) + 1)
    ]
    assert [line for each in written for line in each["lines"]] == ended.history
    assert "ventoux.audit.append" in scheduled(history)
