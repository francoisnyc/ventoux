"""Layer 9b on Temporal: keys, the codec, and no sensitive value in plain text anywhere.

See docs/layers/09-case-data.md (9b) and docs/guides/case-data.md ("On Temporal").
"""

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest
from skipping_server import time_skipping
from temporalio import workflow
from temporalio.api.common.v1 import Payload
from temporalio.api.failure.v1 import Failure
from temporalio.api.history.v1 import History
from temporalio.client import Client, WorkflowHandle, WorkflowHistory
from temporalio.converter import (
    ActivitySerializationContext,
    DataConverter,
    WorkflowSerializationContext,
)
from temporalio.exceptions import ApplicationError
from temporalio.worker import Replayer, Worker

from ventoux.case.visibility import CaseView
from ventoux.temporal.activities import plan_activities
from ventoux.temporal.cases import (
    CaseAnswer,
    CaseReport,
    CaseStart,
    CaseWorkflow,
    answer,
    report,
    start_case,
    view,
)
from ventoux.temporal.client import start_plan
from ventoux.temporal.converter import ExactPayloadConverter, data_converter
from ventoux.temporal.logs import TEMPORAL_LOGGERS
from ventoux.temporal.sandbox import SANDBOX
from ventoux.temporal.worker import case_worker
from ventoux.testing import START

# Temporal: this module defines a workflow, so the workflow sandbox imports it afresh. What it
# uses from the development setup is passed through, imported once and shared (as in 8c's tests).
with workflow.unsafe.imports_passed_through():
    from test_sensitive import FILE, OPENING, claim

    from ventoux.case.definition import CaseInvalid, parse_case
    from ventoux.case.runtime import CaseRefused, decide
    from ventoux.case.state import CaseState, Opened
    from ventoux.core.sensitive import Sensitive
    from ventoux.testing import (
        CATALOG,
        FAKES,
        DevelopmentPlans,
        as_json,
        development_converter,
        run_case,
    )
    from ventoux.tooling.keys import FileKeys, KeyRefused

Case = WorkflowHandle[CaseWorkflow, CaseReport]

NATIONAL_ID = "1 85 05 78 006 084 36"


def test_a_key_is_made_once(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    # Never made again, even by another provider on the same file: a reused ID never inherits
    # or remakes a case's key (brief, D31).
    with pytest.raises(KeyRefused, match="^a key was already made for claim-7: open the case"):
        FileKeys(tmp_path / "keys.json").create("claim-7")
    # A case without one has nothing to seal or open with: fail closed, never plain text.
    no_key = "^there is no key for claim-8, so its sensitive values can't be read or written$"
    with pytest.raises(KeyRefused, match=no_key):
        keys.seal("claim-8", NATIONAL_ID.encode(), "sensitive/0")
    with pytest.raises(KeyRefused, match=no_key):
        keys.open("claim-8", b"anything", "sensitive/0")


def test_a_part_opens_only_where_it_was_sealed(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    keys.create("claim-8")
    sealed = keys.seal("claim-7", NATIONAL_ID.encode(), "sensitive/0")
    assert NATIONAL_ID.encode() not in sealed
    assert keys.open("claim-7", sealed, "sensitive/0") == NATIONAL_ID.encode()
    # The key never leaves the provider: it seals and opens, and nothing else reads it.
    assert not any(
        name.startswith(("key", "get")) for name in dir(keys) if not name.startswith("_")
    )
    damaged = sealed[:-1] + bytes([sealed[-1] ^ 1])
    for case, data, part in [
        ("claim-8", sealed, "sensitive/0"),  # another case
        ("claim-7", sealed, "sensitive/1"),  # another place in the payload
        ("claim-7", damaged, "sensitive/0"),
    ]:
        with pytest.raises(KeyRefused, match=f"^a sealed part of {case} doesn't open"):
            keys.open(case, data, part)


def converter(keys: FileKeys, workflow_id: str | None) -> DataConverter:
    """Ventoux's data converter as Temporal hands it a payload of `workflow_id`'s: a case, or a
    child `<case ID>/<entry>`. None: Temporal gave no workflow ID."""
    plain = data_converter(keys)
    if workflow_id is None:
        return plain
    return plain.with_context(WorkflowSerializationContext("default", workflow_id))


def test_a_sensitive_value_crosses_encrypted(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    value = {"national_id": Sensitive(NATIONAL_ID), "amount": Decimal("1200.50")}

    async def go() -> None:
        claim_7 = converter(keys, "claim-7")
        [payload] = await claim_7.encode([value])
        # Its own part, encrypted; the rest of the payload stays readable.
        assert NATIONAL_ID.encode() not in payload.SerializeToString()
        assert b'"amount": 1200.50' in payload.data
        assert set(payload.metadata) == {"encoding", "encrypted/0"}
        assert (await claim_7.decode([payload], [Any]))[0] == value

    asyncio.run(go())


def test_a_child_uses_its_cases_key(tmp_path: Path) -> None:
    # Temporal gives a child workflow's payloads the child's ID: `claim-7/collect#1`.
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    value = [Sensitive(NATIONAL_ID)]

    async def go() -> None:
        [payload] = await converter(keys, "claim-7/collect#1").encode([value])
        assert (await converter(keys, "claim-7").decode([payload], [Any]))[0] == value
        activity = ActivitySerializationContext(
            "default", "1", "orders.lookup@1", "q", "claim-7/collect#1", "ventoux.plan", False
        )
        in_activity = data_converter(keys).with_context(activity)
        assert (await in_activity.decode([payload], [Any]))[0] == value

    asyncio.run(go())


def test_the_codec_fails_closed(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    value = [Sensitive(NATIONAL_ID)]

    async def go() -> None:
        with pytest.raises(KeyRefused, match="^there is no key for claim-9"):
            await converter(keys, "claim-9").encode([value])
        with pytest.raises(KeyRefused, match="^a sensitive part has no case"):
            await converter(keys, None).encode([value])
        [payload] = await converter(keys, "claim-7").encode([value])
        with pytest.raises(KeyRefused, match="^a sensitive part has no case"):
            await converter(keys, None).decode([payload], [Any])
        damaged = Payload()
        damaged.CopyFrom(payload)
        sealed = damaged.metadata["encrypted/0"]
        damaged.metadata["encrypted/0"] = sealed[:-1] + bytes([sealed[-1] ^ 1])
        with pytest.raises(KeyRefused, match="^a sealed part of claim-7 doesn't open"):
            await converter(keys, "claim-7").decode([damaged], [Any])
        # A converter given a payload the codec never decoded refuses it, never guesses.
        with pytest.raises(ValueError, match="^a sensitive part arrived encrypted"):
            ExactPayloadConverter().from_payloads([payload])
        # Its own marker can't be forged by data: a dict with that key is refused.
        with pytest.raises(TypeError, match="‹sensitive›"):
            await converter(keys, "claim-7").encode([{"‹sensitive›": 0}])

    asyncio.run(go())


def test_a_payload_without_parts_needs_no_key(tmp_path: Path) -> None:
    # A case without a sensitive value, and every history written before 9b, needs no key.
    keys = FileKeys(tmp_path / "keys.json")
    value = {"amount": Decimal(250), "order_id": "ord-1"}

    async def go() -> None:
        [payload] = await converter(keys, "refund-1").encode([value])
        assert payload == ExactPayloadConverter().to_payloads([value])[0]
        assert (await converter(keys, "refund-1").decode([payload], [Any]))[0] == value

    asyncio.run(go())


def test_a_failure_crosses_encrypted(tmp_path: Path) -> None:
    # Temporal keeps a failure's message and stack trace outside payloads: both are sealed, at
    # every level of its causes, whoever raised it.
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")

    async def go() -> None:
        claim_7 = converter(keys, "claim-7")
        try:
            try:
                raise LookupError(f"no customer {NATIONAL_ID}")
            except LookupError as cause:
                raise RuntimeError(f"lookup of {NATIONAL_ID} failed") from cause
        except RuntimeError as error:
            failure = Failure()
            await claim_7.encode_failure(error, failure)
        assert NATIONAL_ID.encode() not in failure.SerializeToString()
        assert failure.message == failure.cause.message == "Encoded failure"
        assert failure.stack_trace == failure.cause.stack_trace == ""  # moved, and sealed
        back = await claim_7.decode_failure(failure)
        # Read back where the key is, as it was raised.
        assert isinstance(back, ApplicationError)
        assert back.message == f"lookup of {NATIONAL_ID} failed"
        assert isinstance(back.cause, ApplicationError)
        assert back.cause.message == f"no customer {NATIONAL_ID}"

    asyncio.run(go())


# --- On Temporal: no sensitive value in plain text anywhere (curriculum, layer 9) ---

QUEUE = "cases"
TAX_ID = "FR-77-4410-2296"
CHECK_ID_PLAN: dict[str, Any] = {
    "plan": "check-id",
    "version": 1,
    "display": {"title": "Check an ID"},
    "fields": {"id": {"type": "string"}},
    "initial": "check",
    "states": {
        "check": {
            "activity": "orders.lookup@1",
            "inputs": {"order_id": {"var": "id"}},
            "on": {"done": "checked"},
        },
        "checked": {"final": "succeeded"},
    },
}


# Temporal: a case workflow with a plan, that continues as new after every 2 events, so one test
# crosses several runs and a child plan. A deployment keeps the default (brief, D27).
@workflow.defn(name="ventoux.case")
class SensitiveCases(CaseWorkflow):
    catalog = CATALOG
    plans: ClassVar[Mapping[str, Any]] = {"check-id@1": CHECK_ID_PLAN}
    events_per_run = 2

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def sensitive_claim() -> dict[str, Any]:
    """The guide's claim with its national ID, a tax ID the adjuster gives, a lookup of the ID
    and a plan step given it."""
    definition = claim()
    definition["fields"]["tax_id"] = {
        "type": "string",
        "sensitive": True,
        "visible_to": ["claims-sensitive"],
        "display": {"title": "Tax ID"},
    }
    definition["steps"]["assess"]["outcomes"]["accept"]["sets"] = ["tax_id"]
    definition["steps"]["lookup_id"] = {
        "kind": "activity",
        "display": {"title": "Look the ID up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "national_id"}},
    }
    definition["steps"]["check_id"] = {
        "kind": "plan",
        "display": {"title": "Check the ID"},
        "plan": "check-id@1",
        "inputs": {"id": {"var": "national_id"}},
    }
    return definition


LOOKED_UP: list[object] = []  # what the lookup's code was given, on the worker


def quoting(inputs: dict[str, Any]) -> dict[str, Any]:
    """A lookup that fails saying what it was given, as a careless system's error would."""
    LOOKED_UP.append(inputs["order_id"])
    raise ApplicationError(f"no record for {inputs['order_id']}", non_retryable=True)


def on_temporal[T](
    scenario: Callable[[Client], Awaitable[T]], converter: DataConverter | None = None
) -> T:
    """Run `scenario` against Temporal's time-skipping test server, with a worker serving
    `SensitiveCases` and a lookup that quotes what it was given."""

    async def go() -> T:
        activities = {**FAKES, "orders.lookup@1": quoting}
        async with (
            time_skipping(converter or development_converter()) as environment,
            case_worker(environment.client, QUEUE, SensitiveCases, DevelopmentPlans, activities),
        ):
            return await asyncio.wait_for(scenario(environment.client), timeout=20)

    return asyncio.run(go())


async def answered[T](query: Callable[[], Awaitable[T]]) -> T:
    """What `query` gives. A query asked as the case continues as new can go unanswered (the
    cases guide): it is asked again, a bounded number of times."""
    for _ in range(20):
        try:
            return await asyncio.wait_for(query(), timeout=1)
        except TimeoutError:
            continue
    raise AssertionError("the case never answered")


async def reported(case: Case, holds: Callable[[CaseReport], bool]) -> CaseReport:
    """The case's report once `holds` is true of it, asked a bounded number of times."""
    for _ in range(200):
        now = await answered(lambda: report(case))
        if holds(now):
            return now
        await asyncio.sleep(0.05)
    raise AssertionError("the case never got there")


async def every_run(client: Client, id: str) -> list[WorkflowHistory]:
    """The history of every run of the workflow `id`, first to latest, as Temporal stores it:
    payloads still encoded, as an export would hold them."""
    first = (await client.get_workflow_handle(id).describe()).raw_description
    run_id = first.workflow_execution_info.first_run_id
    histories = []
    while run_id:
        history = await client.get_workflow_handle(id, run_id=run_id).fetch_history()
        histories.append(history)
        last = history.events[-1]
        switched = last.workflow_execution_continued_as_new_event_attributes
        run_id = (
            switched.new_execution_run_id
            if last.HasField("workflow_execution_continued_as_new_event_attributes")
            else ""
        )
    return histories


def as_stored(history: WorkflowHistory) -> tuple[bytes, str]:
    """`history` as Temporal stores it (its raw bytes) and as it is exported (JSON)."""
    return History(events=history.events).SerializeToString(), history.to_json()


def test_no_sensitive_value_in_plain_text_in_history(caplog: pytest.LogCaptureFixture) -> None:
    planted = [NATIONAL_ID, TAX_ID, "1850578006"]
    # The worker's log too: Temporal's SDK logs a failed activity or workflow task, with its
    # exception, before the failure is sealed; logs go where many people read them (tutor review).
    caplog.set_level(logging.DEBUG, logger="temporalio")
    LOOKED_UP.clear()

    async def scenario(client: Client) -> list[WorkflowHistory]:
        file = as_json(FILE)  # numbers as the API passes them on: exact decimals
        case = await start_case(client, SensitiveCases, sensitive_claim(), file, "claim-7", QUEUE)
        # Refused for its type, and recorded: the refusal names the kind, and the value sent
        # crossed sealed.
        await answer(
            case, "assess#1", "accept", "ana", ["adjuster"], {"tax_id": Decimal(1850578006)}
        )
        await answer(case, "assess#1", "accept", "ana", ["adjuster"], {"tax_id": TAX_ID})
        ended = await reported(
            case, lambda now: len(now.needs_attention) == 2 and "assess#1 done" in now.history
        )
        assert sorted(ended.needs_attention) == [
            "check_id#1: check-id@1 stopped: orders.lookup@1 failed with ApplicationError: ‹sensitive›",
            "lookup_id#1: orders.lookup@1 failed with ApplicationError: ‹sensitive›",
        ]
        assert any(line.startswith("refused ana's answer accept") for line in ended.history)
        # The activity's code got the plain value, in the case and in its plan.
        assert LOOKED_UP == [NATIONAL_ID, NATIONAL_ID]
        runs = await every_run(client, "claim-7")
        assert len(runs) > 1  # it continued as new, carrying both IDs
        return runs + await every_run(client, "claim-7/check_id#1")

    for history in on_temporal(scenario):
        raw, exported = as_stored(history)
        for value in planted:
            assert value.encode() not in raw, (history.workflow_id, value)
            assert value not in exported, (history.workflow_id, value)
    # Each record as a handler would write it, its exception and traceback included.
    logged = [logging.Formatter().format(record) for record in caplog.records]
    assert any("Completing activity as failed" in line for line in logged)  # it was logged
    for value in planted:
        assert not [line for line in logged if value in line], value


def test_the_view_on_temporal_decrypts_for_who_may_see() -> None:
    async def scenario(client: Client) -> tuple[CaseView, CaseView]:
        case = await start_case(
            client, SensitiveCases, sensitive_claim(), as_json(FILE), "c-1", QUEUE
        )
        await reported(case, lambda now: "started assess#1" in "\n".join(now.history))
        officer = await answered(lambda: view(case, ["claims-sensitive"]))
        return officer, await answered(lambda: view(case, ["adjuster"]))

    officer, adjuster = on_temporal(scenario)
    # Filtered in the worker, sealed across Temporal, opened by the client, which holds the keys.
    assert officer.values["national_id"] == Sensitive(NATIONAL_ID)
    assert "National ID: ‹sensitive›, from system:opener" in officer.lines
    assert "national_id" not in adjuster.values
    assert "National ID: hidden (needs claims-sensitive)" in adjuster.lines


def test_a_client_without_the_codec_is_refused() -> None:
    # Fail closed: a client or worker without the codec would send a sensitive value in plain
    # text, and nothing would say so (brief, D31).
    exact_only = dataclasses.replace(
        DataConverter.default, payload_converter_class=ExactPayloadConverter
    )

    async def go() -> None:
        async with time_skipping(exact_only) as environment:
            refused = (
                "^this client doesn't encrypt sensitive values: connect it with data_converter"
            )
            with pytest.raises(ValueError, match=refused):
                case_worker(environment.client, QUEUE, SensitiveCases, DevelopmentPlans, FAKES)
            with pytest.raises(ValueError, match=refused):
                await start_case(environment.client, SensitiveCases, claim(), FILE, "c-1", QUEUE)
            with pytest.raises(ValueError, match=refused):
                await start_plan(
                    environment.client, DevelopmentPlans, CHECK_ID_PLAN, {}, "r-1", QUEUE
                )

    asyncio.run(go())


def test_an_id_with_a_slash_is_refused() -> None:
    # The codec finds a child's key from the part of its ID before the first `/`: a case's own ID
    # holding one would find another case's key (brief, D31).
    async def scenario(client: Client) -> None:
        with pytest.raises(ValueError, match='^claim/7 can\'t name a case: a case ID has no "/"$'):
            await start_case(client, SensitiveCases, claim(), FILE, "claim/7", QUEUE)
        with pytest.raises(ValueError, match="^check/1 can't name a run: a run's ID has no \"/\"$"):
            await start_plan(client, DevelopmentPlans, CHECK_ID_PLAN, {}, "check/1", QUEUE)

    on_temporal(scenario)


# --- Replay ---


def sensitive_history(converter: DataConverter) -> WorkflowHistory:
    """The latest run of a case holding a national ID and a tax ID, its parts sealed by
    `converter`: it continued as new, ran a plan and recorded failures."""

    async def scenario(client: Client) -> WorkflowHistory:
        case = await start_case(
            client, SensitiveCases, sensitive_claim(), as_json(FILE), "claim-7", QUEUE
        )
        await answer(case, "assess#1", "accept", "ana", ["adjuster"], {"tax_id": TAX_ID})
        await reported(case, lambda now: len(now.needs_attention) == 2)
        return await case.fetch_history()

    return on_temporal(scenario, converter)


def replay(history: WorkflowHistory, converter: DataConverter) -> None:
    """Replay `history` as a worker would after a restart, with Ventoux's runner (brief, D31)."""
    replayer = Replayer(
        workflows=[SensitiveCases, DevelopmentPlans],
        data_converter=converter,
        workflow_runner=SANDBOX,
    )
    asyncio.run(replayer.replay_workflow(history))


def test_replay_needs_the_key() -> None:
    converter = development_converter()
    history = sensitive_history(converter)
    # Without the case's key, nothing sealed can be read: replay fails, never reads plain text.
    with pytest.raises(Exception, match="no key for claim-7"):
        replay(history, development_converter())
    replay(history, converter)


def test_a_history_from_before_9b_replays() -> None:
    # A case recorded with no codec at all, as before 9b: its payloads have no parts, so the
    # codec passes them as they are, asking for no key (brief, D31).
    before_9b = dataclasses.replace(
        DataConverter.default, payload_converter_class=ExactPayloadConverter
    )

    async def go() -> WorkflowHistory:
        async with time_skipping(before_9b) as environment:
            client = environment.client
            async with Worker(
                client,
                task_queue=QUEUE,
                workflows=[SensitiveCases, DevelopmentPlans],
                activities=plan_activities(CATALOG, FAKES),
                activity_executor=ThreadPoolExecutor(),
                workflow_runner=SANDBOX,
            ):
                start = CaseStart(claim_without_the_id(), as_json(OPENING))
                case = await client.start_workflow(
                    SensitiveCases.run, start, id="claim-1", task_queue=QUEUE
                )
                await answered(lambda: case.query(SensitiveCases.report))
                denied = CaseAnswer("assess#1", "deny", "ana", ["adjuster"])
                await case.signal(SensitiveCases.answer, denied)
                assert (await case.result()).status == "closed"
                return await case.fetch_history()

    history = asyncio.run(go())
    replay(history, development_converter())


def claim_without_the_id() -> dict[str, Any]:
    """The guide's claim as it was before it had a sensitive field."""
    definition = claim()
    del definition["fields"]["national_id"]
    return definition


# --- The guide ---

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "case-data.md").read_text()


def guide_refusal_rows() -> list[tuple[str, str]]:
    """The rows of the guide's second "What the engine refuses" table: 9b's."""
    table = GUIDE.split("### What the engine refuses")[2].split("\n## ")[0]
    rows = [line for line in table.splitlines() if line.startswith("| ")][1:]  # after the header
    return [
        (cells[1].strip(), cells[2].strip().strip("`")) for cells in (r.split("|") for r in rows)
    ]


def refusal_in_memory(when: str) -> str:
    """What the engine says, for each of the guide's rows that needs no Temporal server."""
    if when == "a sensitive field doesn't say who may see it":
        definition = claim()
        del definition["fields"]["national_id"]["visible_to"]
        with pytest.raises(CaseInvalid) as invalid:
            parse_case(definition)
        return str(invalid.value)
    if when == "a sensitive value arrives in plain text":
        with pytest.raises(CaseRefused) as refused:
            decide(
                parse_case(claim()),
                CATALOG,
                CaseState("memory"),
                Opened(as_json(FILE), None, at=START),
            )
        return str(refused.value)
    if when == "a sensitive value reaches a workflow step":
        kyc = {
            "kind": "workflow",
            "display": {"title": "Check the customer"},
            "workflow": "kyc.check@1",
            "inputs": {"customer_id": {"var": "national_id"}},
        }
        definition = claim()
        definition["steps"]["kyc"] = kyc
        run = run_case(definition, file=FILE, answers=[], people={})
        return run.needs_attention[0].removeprefix("kyc#1: ")
    raise LookupError(when)


async def refusal_on_temporal(when: str, client: Client, keys_file: Path) -> str:
    """What the engine says, for each of the guide's rows about keys and clients."""
    keys = FileKeys(keys_file)
    try:
        if when == "a case ID has a `/`":
            await start_case(client, SensitiveCases, claim(), FILE, "claim/7", QUEUE)
        elif when == "a case's key was already made":
            keys.create("claim-7")
            keys.create("claim-7")
        elif when == "a client or worker doesn't encrypt":
            exact_only = dataclasses.replace(
                DataConverter.default, payload_converter_class=ExactPayloadConverter
            )
            plain = await Client.connect(
                client.service_client.config.target_host, data_converter=exact_only
            )
            await start_case(plain, SensitiveCases, claim(), FILE, "claim-7", QUEUE)
        elif when == "a case has no key":
            keys.seal("claim-7", b"", "sensitive/0")
    except (ValueError, KeyRefused) as refused:
        return str(refused)
    raise LookupError(when)


GUIDE_REFUSALS = [
    "a sensitive field doesn't say who may see it",
    "a sensitive value arrives in plain text",
    "a sensitive value reaches a workflow step",
    "a case ID has a `/`",
    "a case's key was already made",
    "a client or worker doesn't encrypt",
    "a case has no key",
]


def test_every_refusal_in_the_guide_is_tested() -> None:
    assert [when for when, _ in guide_refusal_rows()] == GUIDE_REFUSALS


def test_the_guides_refusals_are_what_the_engine_says(tmp_path: Path) -> None:
    rows = guide_refusal_rows()
    for when, says in rows[:3]:
        assert refusal_in_memory(when) == says, when

    async def scenario(client: Client) -> list[str]:
        return [
            await refusal_on_temporal(when, client, tmp_path / f"keys-{n}.json")
            for n, (when, _) in enumerate(rows[3:])
        ]

    assert on_temporal(scenario) == [says for _, says in rows[3:]]


def test_the_workers_log_keeps_only_an_exceptions_type(caplog: pytest.LogCaptureFixture) -> None:
    # A failed workflow task is logged as a failed activity is, on another of Temporal's loggers:
    # once a worker is made, each keeps the exception's type and drops its text (brief, D31).
    async def go() -> None:
        async with time_skipping(development_converter()) as environment:
            case_worker(environment.client, QUEUE, SensitiveCases, DevelopmentPlans, FAKES)

    asyncio.run(go())
    caplog.set_level(logging.DEBUG, logger="temporalio")
    for name in TEMPORAL_LOGGERS:
        try:
            raise LookupError(f"no customer {NATIONAL_ID}")
        except LookupError:
            logging.getLogger(name).warning("Failed activation on workflow", exc_info=True)
    logged = [logging.Formatter().format(record) for record in caplog.records]
    assert logged == ["Failed activation on workflow (LookupError)"] * len(TEMPORAL_LOGGERS)
