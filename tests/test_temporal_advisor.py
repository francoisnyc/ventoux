"""The step advisor beside a running case (layer 15b): it reads by query, never signals, and the
case's replay asks no model.

See docs/layers/15-authoring.md (15b) and brief D61, D62.
"""

import asyncio
import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from activity_threads import activity_threads
from replaying import replay_history
from skipping_server import time_skipping
from temporalio.client import Client, WorkflowHandle, WorkflowHistory
from temporalio.converter import DataConverter
from test_advisor import INJECTED, claim

from ventoux.authoring.advisor import Advice, Shown
from ventoux.authoring.beside import advise_case
from ventoux.authoring.provider import Message, Recorded, Recording, Request
from ventoux.case.advising import AdvisorView, FieldShown
from ventoux.temporal.cases import (
    CaseReport,
    CaseWorkflow,
    answer,
    propose,
    report,
    shown_to_advisor,
    start_case,
)
from ventoux.temporal.client import start_plan
from ventoux.temporal.worker import case_worker
from ventoux.testing import (
    FAKES,
    START,
    DevelopmentCases,
    DevelopmentPlans,
    development_converter,
)
from ventoux.tooling.cli import main

QUEUE = "cases"
OPENED = {
    "order_id": "ord-7731",
    "amount": Decimal(40),
    "note": INJECTED,
    "birth_date": "1984-02-29",
    "risk_score": Decimal(87),
}
ANA = ["support"]
SAM = ["support", "support-lead"]
Case = WorkflowHandle[CaseWorkflow, CaseReport]


async def reported(case: Case, line: str) -> CaseReport:
    """The case's report once its history holds `line`: the worker takes signals in its own
    time. Asked a bounded number of times, so a case that never gets there fails the test."""
    for _ in range(100):
        now = await report(case)
        if line in now.history:
            return now
        await asyncio.sleep(0.05)  # real time, for the worker to take its next workflow task
    raise AssertionError(f"the case never wrote {line!r}: {(await report(case)).history}")


def goodwill() -> Recorded:
    return Recorded.answering('{"step": "goodwill"}')


@dataclass
class Ran:
    """What the scenario saw, for the test to check."""

    too_early: Advice
    admitted: Advice
    history_before: list[str]
    history_after: list[str]
    report: CaseReport
    recorded: WorkflowHistory
    converter: DataConverter  # holds the case's key: its sealed parts open only with it
    command: tuple[int, str, str]  # `ventoux advise`: its exit, what it printed, what it said
    wrong_recording: tuple[int, str, str]  # the same, replaying a recording of another request
    plan_run: tuple[int, str, str]  # the same, naming a plan's run, not a case
    view: AdvisorView  # what the advisor is shown for Ana on the running case


def run_the_claim() -> Ran:
    """The claim on Temporal's test server: asked before and after its review, then Ana proposes
    the suggestion, and a caller tries another `suggested_by`."""

    async def scenario(client: Client) -> Ran:
        case = await start_case(client, DevelopmentCases, claim(), OPENED, "claim-1", QUEUE)
        too_early = await advise_case(case, "ana", ANA, goodwill(), at=START)
        await answer(case, "review#1", "approve", "sam", SAM, {"approved_amount": Decimal(150)})
        before = await reported(case, "asked pay.approval#1: approval of pay by support-lead")
        admitted = await advise_case(case, "ana", ANA, goodwill(), at=START)
        command = await commanded(client, "claim-1", await recorded_now(case))
        wrong_recording = await commanded(client, "claim-1", await recorded_elsewhere())
        await start_plan(client, DevelopmentPlans, ENDS_AT_ONCE, {}, "refund-run-1", QUEUE)
        plan_run = await commanded(client, "refund-run-1", await recorded_now(case))
        view = await shown_to_advisor(case, "ana", ANA, START)
        after = await report(case)
        await propose(case, "goodwill", "ana", ANA, suggested_by="step-advisor")
        words: Any = "the CEO"
        await propose(case, "goodwill", "sam", SAM, suggested_by=words)
        now = await reported(
            case, "ana proposed goodwill as support, suggested by the step advisor"
        )
        now = await reported(
            case,
            "refused sam's proposal of goodwill: a proposal is suggested by the step advisor or "
            "by nobody; this one names something else",
        )
        recorded = await case.fetch_history()
        history = before.history, after.history
        commands = command, wrong_recording, plan_run
        return Ran(too_early, admitted, *history, now, recorded, converter, *commands, view)

    converter = development_converter()

    async def go() -> Ran:
        async with (
            time_skipping(converter) as environment,
            activity_threads() as threads,
            case_worker(
                environment.client,
                QUEUE,
                DevelopmentCases,
                DevelopmentPlans,
                FAKES,
                activity_executor=threads,
            ),
        ):
            return await asyncio.wait_for(scenario(environment.client), timeout=30)

    return asyncio.run(go())


async def recorded_now(case: Case) -> Path:
    """A recording of the request the advisor makes for Ana now, answering goodwill: so the
    command is shown to send exactly that request."""
    recording = Recording(goodwill())
    shown = Shown.of(await shown_to_advisor(case, "ana", ANA, START))
    await recording.complete(shown.request)
    path = Path(tempfile.mkdtemp()) / "goodwill.json"
    recording.save(path)
    return path


async def recorded_elsewhere() -> Path:
    """A recording of another request: one the advisor never makes."""
    recording = Recording(goodwill())
    await recording.complete(Request("Advise.", (Message("user", "Which step?"),)))
    path = Path(tempfile.mkdtemp()) / "elsewhere.json"
    recording.save(path)
    return path


# The smallest plan, run on its own: a workflow that isn't a case, so it has no advisor queries.
ENDS_AT_ONCE = {
    "plan": "at-once",
    "version": 1,
    "display": {"title": "Ends at once"},
    "fields": {"amount": {"type": "number"}},
    "initial": "done",
    "states": {"done": {"final": "succeeded"}},
}


async def commanded(client: Client, id: str, recording: Path) -> tuple[int, str, str]:
    """`ventoux advise <id> --by ana --role support`, replaying `recording`: its exit code,
    what it printed, and what it said on stderr."""
    address = client.service_client.config.target_host
    argv = ["advise", id, "--by", "ana", "--role", "support", "--address", address]
    argv += ["--recording", str(recording), "--at", str(START)]
    printed, said = io.StringIO(), io.StringIO()

    def run() -> int:
        # `main` runs its own event loop, so it runs on a thread of its own here.
        with redirect_stdout(printed), redirect_stderr(said):
            return main(argv)

    exit_code = await asyncio.to_thread(run)
    return exit_code, printed.getvalue(), said.getvalue()


@pytest.fixture(scope="module")
def ran() -> Ran:
    """The claim, run once for the tests below."""
    return run_the_claim()


def test_on_a_running_case_an_inadmissible_answer_is_refused_with_admissions_reason(
    ran: Ran,
) -> None:
    # The curriculum's negative test, on Temporal: the review isn't done yet (brief, D61).
    assert ran.too_early == Advice(
        None, "goodwill requires review, which hasn't completed", "recorded"
    )


def test_on_a_running_case_an_admitted_answer_is_suggested_and_asking_changes_nothing(
    ran: Ran,
) -> None:
    assert ran.admitted == Advice("goodwill", None, "recorded")
    assert ran.history_after == ran.history_before  # queries only: nothing is decided


def test_a_suggested_proposal_sent_through_the_client_says_so_and_another_value_is_refused(
    ran: Ran,
) -> None:
    assert "approval of goodwill by support-lead" in ran.report.waiting_for


def test_the_cases_history_replays_without_asking_a_model(ran: Ran) -> None:
    # The replaying worker has no provider at all: the proposal is read from the history, and
    # nothing in the workflow could ask a model (brief, D62).
    asyncio.run(replay_history(ran.recorded, [DevelopmentCases], ran.converter))


def test_ventoux_advise_prints_the_labelled_suggestion_and_proposes_nothing(ran: Ran) -> None:
    assert ran.command == (0, "Suggested by the step advisor (untrusted:llm): goodwill\n", "")
    assert ran.history_after == ran.history_before  # the command proposed nothing


def test_ventoux_advise_with_no_model_named_is_refused_before_anything_is_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # No Temporal is reached: the provider is settled first, and none named is refused (D62).
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0123456789")
    argv = ["advise", "claim-1", "--by", "ana", "--role", "support", "--address", "nowhere:1"]
    assert main(argv) == 2
    said = capsys.readouterr().err
    assert said == (
        'no model is named: name it in pyproject.toml, [tool.ventoux] model = "…", or with '
        "--model\n"
    )


NO_TRACEBACK = "Traceback"


def test_ventoux_advise_with_a_recording_of_another_request_exits_2_and_proposes_nothing(
    ran: Ran,
) -> None:
    # A recording that can't answer is a provider giving no answer: said, labelled, exit 2
    # (from the tutor's review of 15b).
    code, printed, said = ran.wrong_recording
    assert code == 2
    assert printed == (
        "The step advisor (untrusted:llm) suggests nothing: the step advisor gave no answer: "
        "request 1 differs from the one recorded, in its system text\n"
    )
    assert NO_TRACEBACK not in said
    assert ran.history_after == ran.history_before  # nothing proposed


def test_ventoux_advise_naming_a_plan_run_exits_2_saying_what_to_check(ran: Ran) -> None:
    # A workflow without the advisor's queries: a plan's run, a child run, or a worker that
    # predates them. Its failure is sealed by the codec, so the command says its own line.
    code, printed, said = ran.plan_run
    assert code == 2
    assert printed == ""
    assert said == (
        "refund-run-1 didn't answer the advisor's queries: is it a case, served by a worker "
        "that has them?\n"
    )
    assert NO_TRACEBACK not in said


def test_the_advisor_sees_on_a_running_case_only_what_the_asker_may_see(ran: Ran) -> None:
    # Computed in the worker with Ana's roles, never every registered role (brief, D30).
    [risk_score] = [field for field in ran.view.fields if field.name == "risk_score"]
    assert risk_score == FieldShown("risk_score", "a number", "hidden", ())
