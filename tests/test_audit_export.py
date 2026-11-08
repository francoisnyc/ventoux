"""The audit export: what is written, sealed, and where it is kept (layer 19b).

Through `exported`, the store, the case on Temporal and `read_audit`. See
docs/layers/19-audit-keys.md (19b), docs/guides/audit.md and brief, D77.
"""

import asyncio
import base64
import dataclasses
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from replaying import replay_history
from skipping_server import time_skipping
from temporalio import workflow
from temporalio.client import Client, WorkflowHistory
from temporalio.common import RetryPolicy
from test_audit_records import checked_claim, known
from test_case import REFUND
from test_child_cases import claim as repair_claim
from test_child_cases import repair
from test_sensitive import FILE, NATIONAL_ID, claim
from test_temporal_case import (
    LARGE,
    PEOPLE,
    QUEUE,
    REVIEW_FORM,
    CasesWithPlans,
    SwitchingCases,
    child_waiting_at,
    on_temporal,
    proposed_settle,
    reported,
)
from test_temporal_children import CLOSING, VIN, sensitive, started
from test_temporal_children import FILE as REPAIR_FILE
from test_temporal_forget import on_temporal as forgetting_on_temporal
from worker_threads import worker_threads

from ventoux.case.admission import RetryRefused
from ventoux.case.audit import AuditRecord
from ventoux.case.definition import parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import ExportRetried
from ventoux.temporal import client as plans
from ventoux.temporal.audit import ExportRefused, exported, restricted_fields, sensitive_fields
from ventoux.temporal.cases import (
    CaseReport,
    CaseStart,
    CaseWorkflow,
    answer,
    close,
    propose,
    retry_export,
    shown,
    start_case,
)
from ventoux.temporal.converter import keys_of
from ventoux.temporal.forget import ForgetReport, answer_forget, propose_forget
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    CATALOG,
    FAKES,
    DevelopmentCases,
    DevelopmentForget,
    DevelopmentPlans,
    as_json,
    development_converter,
    fixture_converter,
    release_of,
    run_case,
)
from ventoux.tooling.audit import AuditRefused, FileAudit, read_audit
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
        exported("claim-7", [unwrapped(records[0]), *records[1:]], sensitive, {}, keys)
    assert str(refused.value) == (
        "audit record claim-7/1 holds national_id, a sensitive field, in clear: nothing was written"
    )
    assert NATIONAL_ID not in str(refused.value)
    # Wrapped, it is sealed under the case's key, for its own place, where alone it opens.
    [opening, *_] = exported("claim-7", records, sensitive, {}, keys)
    sealed = opening["act"]["values"]["national_id"]
    assert NATIONAL_ID not in str(opening)
    assert sealed["part"] == "audit/claim-7/1/act/values/national_id"
    assert sealed["visible_to"] == ["claims-sensitive"]
    ciphertext = base64.b64decode(sealed["sealed"])
    assert keys.open("claim-7", ciphertext, sealed["part"]) == f'"{NATIONAL_ID}"'.encode()
    with pytest.raises(KeyRefused):
        keys.open("claim-7", ciphertext, "audit/claim-7/2/act/values/national_id")


def test_read_audit_opens_a_value_only_for_a_role_that_may_see_it(tmp_path: Path) -> None:
    # Filtered as the case file is: a value whose `visible_to` excludes every role given is said
    # hidden, with the roles that would see it, sealed or not; a sealed one is opened only for a
    # role in it, while the key exists, and said forgotten after. A sealed value that doesn't
    # open is an error, never a guess (brief, D30) (brief, D31) (brief, D77).
    definition, _ = claim_records()
    definition["fields"]["policy_id"]["visible_to"] = ["claims-lead"]  # narrowed, not sensitive
    run = run_case(
        definition, FILE, [], {"ana": ["adjuster"]}, activities={"orders.lookup@1": known}, engine=3
    )
    case = parse_case(definition)
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    store = FileAudit(tmp_path / "audit")
    sight = sensitive_fields(case), restricted_fields(case)
    store.append(exported("claim-7", run.audit, *sight, keys))

    def opening(roles: list[str]) -> dict[str, Any]:
        [first, *_] = read_audit(store, "claim-7", roles, keys)
        values: dict[str, Any] = first["act"]["values"]
        return values

    adjuster = opening(["adjuster"])
    assert adjuster["national_id"] == "hidden (needs claims-sensitive)"
    assert adjuster["policy_id"] == "hidden (needs claims-lead)"
    assert adjuster["customer_id"] == "cus-7"
    assert NATIONAL_ID not in str(read_audit(store, "claim-7", ["adjuster"], keys))
    both = opening(["claims-lead", "claims-sensitive"])
    assert (both["national_id"], both["policy_id"]) == (NATIONAL_ID, "pol-3")
    keys.destroy("claim-7")
    assert opening(["claims-sensitive"])["national_id"] == "‹forgotten›"
    assert opening(["adjuster"])["national_id"] == "hidden (needs claims-sensitive)"
    # Moved to another place in the store, a sealed value doesn't open: an error, saying so.
    other = FileAudit(tmp_path / "other")
    keys.create("claim-8")
    [first, second, *_] = exported("claim-8", run.audit, *sight, keys)
    second["act"]["values"]["national_id"] = first["act"]["values"]["national_id"]
    second["act"]["values"]["national_id"]["visible_to"] = ["claims-sensitive"]
    other.append([first, second])
    with pytest.raises(KeyRefused, match="a sealed part of claim-8 doesn't open"):
        read_audit(other, "claim-8", ["claims-sensitive"], keys)


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


def test_record_numbers_never_repeat_across_switches(tmp_path: Path) -> None:
    # A case continuing as new after every two events: its records leave the state as they are
    # written, the counter crosses each switch, and the store holds each number once, in order,
    # the whole history line for line (brief, D27) (brief, D77).
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, SwitchingCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", ["support"], REVIEW_FORM)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await answer(case, "pay.approval#1", "approve", "sam", ["support", "support-lead"])
        return await case.result()

    ended = on_temporal(scenario, cases=SwitchingCases, audit=store)
    written = store.read("refund-1")
    assert [each["number"] for each in written] == list(range(1, len(written) + 1))
    assert [line for each in written for line in each["lines"]] == ended.history


class DownAudit(FileAudit):
    """A store that can be taken down, and brought back: a test's own."""

    down = False

    def append(self, records: list[dict[str, Any]]) -> None:
        if self.down:
            raise ConnectionError("the audit database at db.internal refused ord-1's records")
        super().append(records)


# Temporal: the development cases, trying the export twice, quickly, before the case is told it
# failed: a deployment keeps the default (brief, D77).
@workflow.defn(name="ventoux.case")
class QuicklyFailingExports(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    export_retries = RetryPolicy(
        maximum_attempts=2,
        initial_interval=timedelta(milliseconds=50),
        non_retryable_error_types=["ExportRefused", "AuditRefused"],
    )

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


FAILED = (
    "audit export failed: the store failed with ConnectionError: ‹sensitive›: look at the store, "
    "then retry the export"
)


def test_with_the_store_down_the_case_closes_only_once_its_export_is_retried(
    tmp_path: Path,
) -> None:
    # The store down: the case decides on and closes, but doesn't end; after the export's retries
    # it needs attention, saying why but never what the store said. Only an operator retries the
    # export; once it is written, the case ends (brief, D17) (brief, D26) (brief, D77).
    store = DownAudit(tmp_path / "audit")
    store.down = True

    async def scenario(client: Client) -> tuple[CaseReport, CaseReport, CaseReport]:
        case = await start_case(client, QuicklyFailingExports, REFUND, SMALL, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", ["support"], {"approved_amount": FORTY})
        failed = await reported(case, lambda now: now.needs_attention == [FAILED])
        await retry_export(case, "ana", ["support"])
        refused = await reported(case, lambda now: "ana's retry" in now.history[-1])
        store.down = False
        await retry_export(case, "omar", ["operations"])
        return failed, refused, await case.result()

    failed, refused, ended = on_temporal(scenario, cases=QuicklyFailingExports, audit=store)
    assert failed.status == "closed"  # closed, and waiting for its export to end
    assert "db.internal" not in str(failed)
    assert refused.history[-1] == (
        "refused ana's retry of the audit export: the audit export is retried by an operating "
        "role (operations), and ana has support"
    )
    assert ended.needs_attention == [] and ended.unwritten == 0
    assert ended.history[-1] == "omar retried the audit export as operations"
    written = store.read("refund-1")
    assert [line for each in written for line in each["lines"]] == ended.history


def test_an_export_that_hasnt_failed_is_never_retried() -> None:
    # Nothing to retry: refused, saying so, as a retry of a run that hasn't failed (brief, D26).
    run = run_case(REFUND, {"order_id": "ord-1", "amount": 40}, [], {"omar": ["operations"]})
    with pytest.raises(RetryRefused) as refused:
        decide(
            run.definition,
            CATALOG,
            run.state,
            ExportRetried("omar", frozenset({"operations"}), at=1_800_000_000),
        )
    assert str(refused.value) == "the audit export hasn't failed: nothing to retry"


# Temporal: the export failing quickly, and a case holding past 4 KB of records unwritten.
@workflow.defn(name="ventoux.case")
class SmallBound(CaseWorkflow):
    catalog = DevelopmentCases.catalog
    export_retries = QuicklyFailingExports.export_retries
    audit_bound = 4 * 1024

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def longer_than(seen: int) -> Callable[[CaseReport], bool]:
    """Whether a report's history has grown past `seen` lines."""
    return lambda now: len(now.history) > seen


HELD = "the audit export is 4 KB behind: the case decides nothing until it is written"


def test_past_its_bound_the_case_holds_until_its_export_catches_up(tmp_path: Path) -> None:
    # The store down, records pile up; past the bound the case decides nothing new, says so, and
    # each event sent waits, in order; once the export is written, it decides them (brief, D77).
    store = DownAudit(tmp_path / "audit")
    store.down = True

    async def scenario(client: Client) -> tuple[CaseReport, CaseReport, CaseReport]:
        case = await start_case(client, SmallBound, REFUND, LARGE, "refund-1", QUEUE)
        await reported(case, lambda now: FAILED in now.needs_attention)
        for _ in range(30):  # bounded: records of a record shown, until the case holds
            now = await reported(case, lambda now: True)
            if HELD in now.needs_attention:
                break
            seen = len(now.history)
            await shown(case, "order_id", "ana", ["support"])
            await reported(case, longer_than(seen))
        held = await reported(case, lambda now: HELD in now.needs_attention)
        await answer(case, "review#1", "approve", "ana", ["support"], REVIEW_FORM)
        await asyncio.sleep(0.3)  # time enough to decide it, were it allowed
        waiting = await reported(case, lambda now: True)
        store.down = False
        await retry_export(case, "omar", ["operations"])
        decided = await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        return held, waiting, decided

    held, waiting, decided = on_temporal(scenario, cases=SmallBound, audit=store)
    assert waiting.history == held.history  # the answer waits, undecided
    assert not any(line.startswith("ana answered") for line in waiting.history)
    assert HELD not in decided.needs_attention
    retried = decided.history.index("omar retried the audit export as operations")
    answered = decided.history.index(
        "ana answered review#1 approve as support, setting approved_amount"
    )
    assert retried < answered  # decided once the export caught up, in the order it came


async def open_claim(client: Client, cases: type[CaseWorkflow]) -> Any:
    """The guide's claim, holding a national ID, waiting for its assessment."""
    return await start_case(client, cases, claim(), as_json(FILE), "claim-7", QUEUE)


def test_forgetting_closes_exports_then_destroys(tmp_path: Path) -> None:
    # Close, export, destroy: every record of the case is written, sealed, before its key goes,
    # and no longer opens after; the request writes its own stream (brief, D32) (brief, D77).
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[ForgetReport, str]:
        await open_claim(client, DevelopmentCases)
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        return await request.result(), keys_of(client).state("claim-7")

    ended, key = forgetting_on_temporal(scenario, audit=store)
    assert (ended.status, key) == ("forgotten", "destroyed")
    written = store.read("claim-7")
    case = [each for each in written if each["stream"] == "claim-7"]
    assert case[-1]["lines"][-1] == "closed: forgotten"
    sealed = case[0]["act"]["values"]["national_id"]
    assert NATIONAL_ID not in str(written)
    keys = FileKeys(tmp_path / "unused.json")  # any provider: the key itself is gone
    with pytest.raises(KeyRefused):
        keys.open("claim-7", base64.b64decode(sealed["sealed"]), sealed["part"])
    request = [each for each in written if each["stream"] == "claim-7/forget"]
    assert [(each["act"]["kind"], each["act"]["by"]) for each in request] == [
        ("forget proposed", "pia"),
        ("answered", "olu"),
        ("key destroyed", None),
    ]
    assert [line for each in request for line in each["lines"]] == ended.history


def test_a_refused_answer_and_a_rejection_are_each_recorded_in_the_request_s_stream(
    tmp_path: Path,
) -> None:
    # Each answer is an act of the request, refused or not: its record says what was decided and
    # why, in the line's own words; nothing is forgotten, and the key stays (brief, D77).
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[ForgetReport, str]:
        await open_claim(client, DevelopmentCases)
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "pia", ["privacy"])  # the proposer: refused
        await answer_forget(request, "reject", "olu", ["privacy"])
        return await request.result(), keys_of(client).state("claim-7")

    ended, key = forgetting_on_temporal(scenario, audit=store)
    assert (ended.status, key) == ("rejected", "kept")
    request = [each for each in store.read("claim-7") if each["stream"] == "claim-7/forget"]
    decided = [
        (each["act"]["kind"], each["act"]["by"], [d["kind"] for d in each["decisions"]])
        for each in request
    ]
    assert decided == [
        ("forget proposed", "pia", ["admitted"]),
        ("answered", "pia", ["refused"]),
        ("answered", "olu", ["rejected"]),
    ]
    [refused] = request[1]["decisions"]
    assert request[1]["lines"] == [f"refused pia's answer approve: {refused['reason']}"]
    assert [line for each in request for line in each["lines"]] == ended.history


def test_with_the_store_down_forgetting_keeps_the_key_until_the_export_is_written(
    tmp_path: Path,
) -> None:
    # The store down as forgetting is approved: the case closes but doesn't end, needing
    # attention; the request waits, and the key stays. Once an operator retries the export, the
    # case ends, and only then does the key go (brief, D32) (brief, D77).
    store = DownAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[CaseReport, str, ForgetReport, str]:
        case = await open_claim(client, QuicklyFailingExports)
        await reported(case, lambda now: now.unwritten == 0)
        store.down = True
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        waiting = await reported(case, lambda now: FAILED in now.needs_attention)
        kept = keys_of(client).state("claim-7")
        store.down = False
        await retry_export(case, "omar", ["operations"])
        return waiting, kept, await request.result(), keys_of(client).state("claim-7")

    waiting, kept, ended, key = forgetting_on_temporal(
        scenario, cases=QuicklyFailingExports, audit=store
    )
    assert (waiting.status, kept) == ("closed", "kept")
    assert (ended.status, key) == ("forgotten", "destroyed")
    case = [each for each in store.read("claim-7") if each["stream"] == "claim-7"]
    assert case[-1]["lines"][-1] == "omar retried the audit export as operations"


def test_a_childs_records_are_its_own_stream_sealed_under_its_parents_key(tmp_path: Path) -> None:
    # A child writes its own stream, under its parent's ID: a sensitive value it was given is
    # sealed with its parent's key, the key it is under, and is in clear nowhere in the store
    # (brief, D75) (brief, D77).
    store = FileAudit(tmp_path / "audit")
    released = release_of(
        sensitive(repair_claim(), "support"),
        1,
        cases={"repair@3": sensitive(repair(), "support-lead")},
    )

    async def scenario(client: Client) -> tuple[CaseReport, bytes]:
        file = REPAIR_FILE | {"vehicle": VIN}
        parent = await start_case(client, DevelopmentCases, released, file, "claim-41", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, DevelopmentCases, "claim-41/repair#1")
        done = await reported(child, lambda now: now.waiting_at == ["fix#1"] and not now.unwritten)
        [opening] = [each for each in store.stream("claim-41/repair#1") if each["number"] == 1]
        sealed = opening["act"]["values"]["vehicle"]
        opened = keys_of(client).open(
            "claim-41", base64.b64decode(sealed["sealed"]), sealed["part"]
        )
        return done, opened

    child, opened = on_temporal(scenario, audit=store)
    written = store.stream("claim-41/repair#1")
    assert [line for each in written for line in each["lines"]] == child.history
    assert written[0]["act"]["values"]["vehicle"]["visible_to"] == ["support-lead"]
    assert opened == f'"{VIN}"'.encode()
    assert VIN not in str(store.read("claim-41"))


def test_with_the_store_down_a_parent_closing_its_child_ends_once_both_exports_are_retried(
    tmp_path: Path,
) -> None:
    # The store down as a parent closes: its child closes and waits for its export, and the
    # parent for its child; each needs attention, neither ends, nothing deadlocks. Once an
    # operator retries each export, the child ends, then the parent (brief, D75) (brief, D77).
    store = DownAudit(tmp_path / "audit")

    async def scenario(client: Client) -> tuple[CaseReport, CaseReport, CaseReport, CaseReport]:
        cases = QuicklyFailingExports
        parent = await start_case(client, cases, CLOSING, REPAIR_FILE, "claim-42", QUEUE)
        await answer(parent, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        child = await started(client, cases, "claim-42/repair#1")
        await reported(child, lambda now: now.waiting_at == ["fix#1"] and not now.unwritten)
        await reported(parent, lambda now: not now.unwritten)
        store.down = True
        await close(parent, "duplicate", "ana", ["support"])
        closed = await reported(child, lambda now: FAILED in now.needs_attention)
        held = await reported(parent, lambda now: FAILED in now.needs_attention)
        store.down = False
        await retry_export(child, "omar", ["operations"])
        await retry_export(parent, "omar", ["operations"])
        return closed, held, await child.result(), await parent.result()

    closed, held, child, parent = on_temporal(scenario, cases=QuicklyFailingExports, audit=store)
    assert closed.status == "closed"
    assert closed.history[-2:] == [
        "closed: by its parent: duplicate, by ana",
        "audit export failed: the store failed with ConnectionError: ‹sensitive›",
    ]
    assert held.status != "closed"  # its child hasn't ended: the parent waits for it
    assert child.unwritten == 0 and parent.unwritten == 0
    assert parent.status == "closed"
    for case, ended in (("claim-42", parent), ("claim-42/repair#1", child)):
        written = store.stream(case)
        assert [line for each in written for line in each["lines"]] == ended.history, case


def test_a_plan_steps_events_are_in_the_record_of_its_end(tmp_path: Path) -> None:
    # A plan run writes nothing itself: what it decided rides in the record of its step's end,
    # each event a decision (choice 28): the payment started on its inputs, with their sources;
    # Sam's refused answer, by him, saying why; Lee's answer; the payment completed; then the
    # step's own end (brief, D28) (brief, D77).
    store = FileAudit(tmp_path / "audit")

    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, CasesWithPlans, proposed_settle(), LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], REVIEW_FORM)
        await propose(case, "settle", "sam", PEOPLE["sam"])
        plan = await child_waiting_at(client, "refund-1/settle#1", "approve_refund#1")
        await plans.answer(plan, "approve_refund#1", "approve", "sam", PEOPLE["sam"])
        await plans.answer(plan, "approve_refund#1", "approve", "lee", PEOPLE["lee"])
        return await reported(
            case, lambda now: "settle#1 done" in now.history and not now.unwritten
        )

    on_temporal(scenario, cases=CasesWithPlans, audit=store)
    [ended] = [
        each
        for each in store.stream("refund-1")
        if (each["act"]["kind"], each["act"]["entry"]) == ("completed", "settle#1")
    ]
    decided = [
        (d["kind"], d["step"], d["entry"], d["target"], d["by"], d["outcome"])
        for d in ended["decisions"]
    ]
    assert decided[-1] == ("completed", "settle", "settle#1", None, None, None)
    ran = [each for each in decided[:-1] if each[0] != "started" or each[3] == "payments.refund@2"]
    assert ran[-4:] == [
        ("refused", "settle", "settle#1", "approve_refund#1", "sam", "approve"),
        ("answered", "settle", "settle#1", "approve_refund#1", "lee", "approve"),
        ("started", "settle", "settle#1", "payments.refund@2", None, None),
        ("completed", "settle", "settle#1", "payments.refund@2", None, "done"),
    ]
    [refused] = [d for d in ended["decisions"] if d["kind"] == "refused"]
    assert refused["reason"] == "sam proposed settle, so cannot approve it"
    [paying] = [d for d in ended["decisions"] if d["target"] == "payments.refund@2"][:1]
    assert {fact["field"]: fact["sources"] for fact in paying["read"]} == {
        "order_id": ["system:opener"],
        "amount": ["person:ana"],
    }


HERE = Path(__file__).parent / "histories"

# Recorded under 19b's code, at engine 3: a refund whose export failed with the store down, a
# retry refused, then one taken; and a request forgetting a claim, a refused answer then an
# approval, writing its own stream. Each replays as recorded, from now on (brief, D51).
AT_19B: dict[str, tuple[str, type[Any]]] = {
    "at_19b_refund_export_retried": ("refund-19b", QuicklyFailingExports),
    "at_19b_forget_request": ("claim-7/forget", DevelopmentForget),
}


def test_histories_recorded_at_19b_replay() -> None:
    for name, (id, workflow_class) in AT_19B.items():
        recorded = HERE / f"{name}.json"
        history = WorkflowHistory.from_json(id, recorded.read_text())
        asyncio.run(replay_history(history, [workflow_class], fixture_converter(recorded)))
