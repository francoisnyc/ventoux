"""Change requests on Temporal (layer 12c), and the histories recorded before them.

The histories were recorded under main at `5801ca0`, before 12c changes anything on Temporal:
whatever 12c adds to a case's state, its signals or the rule of forgetting, a case or a request
opened before it replays as it was recorded (brief, D17) (brief, D51).
See docs/layers/12-releases.md (12c).
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

from temporalio.client import Client, WorkflowHistory
from temporalio.worker import Replayer
from test_sensitive import FILE, NATIONAL_ID, claim
from test_temporal_approvals import EveryEventCases
from test_temporal_case import (
    LARGE,
    PEOPLE,
    QUEUE,
    REFUND,
    on_temporal,
    replay,
    reported,
    runs_of,
)
from test_temporal_forget import on_temporal as forgetting_on_temporal
from test_temporal_sensitive import as_stored

from ventoux.temporal.cases import (
    CaseForget,
    CaseReport,
    CaseWorkflow,
    answer,
    propose_change,
    start_case,
)
from ventoux.temporal.forget import ForgetReport, answer_forget, propose_forget
from ventoux.temporal.sandbox import SANDBOX
from ventoux.testing import (
    DevelopmentCases,
    DevelopmentForget,
    as_json,
    development_converter,
    fixture_converter,
)

HERE = Path(__file__).parent / "histories"

# The refund waiting for its approval, a case open when 12c is deployed; one that continued as new
# after every event, so it starts from states carried before 12c; and a claim its opener, olu,
# approved forgetting, as 9c allowed.
BEFORE_12C: dict[str, tuple[str, type[CaseWorkflow]]] = {
    "before_12c_waiting": ("refund-1", DevelopmentCases),
    "before_12c_switched": ("refund-1", EveryEventCases),
    "before_12c_forgotten_by_its_opener": ("claim-7", DevelopmentCases),
}


def test_histories_from_before_12c_replay() -> None:
    for name, (id, cases) in BEFORE_12C.items():
        recorded = HERE / f"{name}.json"
        history = WorkflowHistory.from_json(id, recorded.read_text())
        replay(history, cases, fixture_converter(recorded))
    # The request that olu approved, recorded with the case's: its approval stands on replay.
    recorded = HERE / "before_12c_forget_request.json"
    request = WorkflowHistory.from_json("claim-7/forget", recorded.read_text())
    replayer = Replayer(
        workflows=[DevelopmentForget],
        data_converter=fixture_converter(recorded),
        workflow_runner=SANDBOX,
    )
    asyncio.run(replayer.replay_workflow(request))


# --- Slice 5: on Temporal ---

TYPED_WRONG = {"approved_amount": Decimal(2500)}  # Ana meant 250


def test_refused_changes_are_recorded_and_the_case_waits_on() -> None:
    # In memory a refusal raises to the test; on Temporal nobody is there to catch it: it is
    # recorded, and the case waits on, the request with it (layer 8c).
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], TYPED_WRONG)
        await propose_change(case, "edit", "approved_amount", Decimal(250), "eve", [])
        await propose_change(case, "edit", "approved_amount", Decimal(250), "ana", PEOPLE["ana"])
        await answer(case, "case.change#1", "approve", "ana", PEOPLE["ana"])
        return await reported(case, lambda now: "\n".join(now.history).count("refused") == 2)

    now = on_temporal(scenario)
    assert [line for line in now.history if line.startswith("refused")] == [
        (
            "refused eve's proposal to edit approved_amount: an edit is proposed by support or "
            "support-lead, and eve has no role"
        ),
        (
            "refused ana's answer approve to case.change#1: ana proposed case.change#1, so "
            "cannot approve it"
        ),
    ]
    assert now.waiting_at == ["pay.approval#1", "case.change#1"]


def test_a_pending_request_crosses_continue_as_new() -> None:
    # Each event is decided in a run of its own: the request proposed in one is approved in a
    # later one, and applied as in memory; the history replays (brief, D27) (brief, D52).
    converter = development_converter()

    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory, tuple[str, str]]:
        case = await start_case(client, EveryEventCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], TYPED_WRONG)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        await propose_change(case, "edit", "approved_amount", Decimal(250), "ana", PEOPLE["ana"])
        await reported(case, lambda now: "case.change#1" in now.waiting_at)
        await answer(case, "case.change#1", "approve", "lee", PEOPLE["lee"])
        now = await reported(case, lambda now: now.waiting_at == ["pay.approval#2"])
        return now, await case.fetch_history(), await runs_of(client, "refund-1")

    now, history, (first, latest) = on_temporal(
        scenario, cases=EveryEventCases, converter=converter
    )
    assert first != latest  # it continued as new, more than once
    assert now.history[-5:] == [
        (
            "ana proposed case.change#1: edit approved_amount, to be approved by support or "
            "support-lead"
        ),
        "lee answered case.change#1 approve as support-lead",
        "applied case.change#1: approved_amount edited by ana, approved by lee",
        "withdrew pay.approval#1: approved_amount changed",
        "asked pay.approval#2: approval of pay by support-lead",
    ]
    replay(history, EveryEventCases, converter)


CORRECTED_ID = "2 90 01 75 123 456 78"
# Kim and Lee see the claim's national ID, and may edit a case file.
CLAIMS = {"kim": ["claims-sensitive", "support"], "lee": ["claims-sensitive", "support-lead"]}


def test_a_sensitive_edit_crosses_sealed() -> None:
    # The new value is sealed by the client, and kept sealed in the case: neither the signal nor
    # the carried state holds it in plain text (brief, D31).
    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory]:
        case = await start_case(client, EveryEventCases, claim(), as_json(FILE), "claim-7", QUEUE)
        await propose_change(case, "edit", "national_id", CORRECTED_ID, "kim", CLAIMS["kim"])
        await reported(case, lambda now: "case.change#1" in now.waiting_at)
        await answer(case, "case.change#1", "approve", "lee", CLAIMS["lee"])
        now = await reported(case, lambda now: any("applied" in line for line in now.history))
        return now, await case.fetch_history()

    now, history = on_temporal(scenario, cases=EveryEventCases)
    assert "applied case.change#1: national_id edited by kim, approved by lee" in now.history
    stored, exported = as_stored(history)
    for planted in (CORRECTED_ID, NATIONAL_ID):
        assert planted.encode() not in stored and planted not in exported


# --- Slice 6: forgetting under the same rules ---


def test_a_request_to_forget_refuses_the_opener() -> None:
    # Olu opened the claim: the request refuses his approval, recorded, and waits on; Eli approves
    # it. The case checks again, depending on nothing the request did (brief, D52).
    async def scenario(client: Client) -> tuple[ForgetReport, CaseReport]:
        case = await start_case(
            client, DevelopmentCases, claim(), as_json(FILE), "claim-7", QUEUE, opened_by="olu"
        )
        request = await propose_forget(
            client, DevelopmentForget, "claim-7", "pia", ["privacy"], QUEUE
        )
        await answer_forget(request, "approve", "olu", ["privacy"])
        await answer_forget(request, "approve", "eli", ["privacy"])
        return await request.result(), await case.result()

    ended, case = forgetting_on_temporal(scenario)
    assert ended.history[:3] == [
        "pia proposed forgetting claim-7, as privacy",
        "refused olu's answer approve: olu opened claim-7, so cannot approve forgetting it",
        "approved by eli, as privacy",
    ]
    assert ended.status == "forgotten"
    assert "forgetting approved by eli as privacy, proposed by pia as privacy" in case.history


def test_the_case_refuses_its_openers_forget_from_engine_2() -> None:
    # Sent as a request would, but a request under this code refuses it first: the case's own
    # check holds on nothing the request did, and is recorded (brief, D34) (brief, D52).
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(
            client, DevelopmentCases, claim(), as_json(FILE), "claim-7", QUEUE, opened_by="olu"
        )
        await case.signal("forget", CaseForget("pia", ["privacy"], "olu", ["privacy"]))
        return await reported(case, lambda now: any("refused" in line for line in now.history))

    now = forgetting_on_temporal(scenario)
    assert now.history[-1] == (
        "refused forgetting the case, approved by olu: olu opened the case, so cannot approve "
        "forgetting it"
    )
    assert now.status == "open"


# --- Slice 7: the guide ---

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "cases.md").read_text()
SNIPPET = GUIDE.split("## Changing an open case\n")[1].split("\n## ")[0].split("```python\n")[4]


def test_the_guides_temporal_example_runs_as_written() -> None:
    # The cases guide's request on Temporal, run as written inside a coroutine, as a client
    # would (our own documentation, never a definition).
    code = "async def snippet():\n" + "".join(
        f"    {line}\n" for line in SNIPPET.split("```")[0].splitlines()
    )

    async def scenario(client: Client) -> CaseReport:
        case = await start_case(client, DevelopmentCases, REFUND, LARGE, "refund-1", QUEUE)
        await answer(case, "review#1", "approve", "ana", PEOPLE["ana"], TYPED_WRONG)
        await reported(case, lambda now: now.waiting_at == ["pay.approval#1"])
        namespace: dict[str, Any] = {
            "case": case,
            "propose_change": propose_change,
            "answer": answer,
            "Decimal": Decimal,
        }
        exec(code, namespace)  # noqa: S102
        await namespace["snippet"]()
        return await reported(case, lambda now: now.waiting_at == ["pay.approval#2"])

    now = on_temporal(scenario)
    assert "applied case.change#1: approved_amount edited by ana, approved by lee" in now.history
