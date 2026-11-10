# Shared helpers for the p7a_* probes: the review's in-memory findings, run again as case workflows on Temporal's time-skipping test server.
"""Not a probe itself. Builds on `p1c_harness.py` (the case worker on the test server). Reaches
past the supported names for `ventoux.testing` (the development catalog, workflows and fakes, and
`release_of`, which releases a definition in memory so that it can pin plans and child cases),
and for the plan workflow's `answer` signal (`ventoux.temporal.workflow.Sent`), which is how the
repository's own tests answer a wait inside a plan step."""

import asyncio
import contextlib
import importlib
import io
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from typing import Any

from p1c_harness import QUEUE, Setup
from temporalio import activity

from ventoux.temporal.cases import CaseReport, case_handle, report, start_case
from ventoux.temporal.workflow import Sent
from ventoux.testing import FAKES, DevelopmentCases, release_of


def quietly(name: str) -> Any:
    """An earlier probe, imported for its definitions: it runs in memory as it is imported, and
    what it prints is dropped (its own run is the place to read that)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return importlib.import_module(name)


class Received:
    """What the activity worker was really given: each call, by the workflow that asked."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []  # workflow ID, contract, inputs

    def wrap(self, fakes: Mapping[str, Any]) -> dict[str, Any]:
        return {name: self.recording(name, fake) for name, fake in fakes.items()}

    def recording(self, name: str, fake: Any) -> Any:
        def recorded(inputs: dict[str, Any]) -> dict[str, Any]:
            # Temporal: inside an activity, `activity.info()` says which workflow scheduled it.
            self.calls.append((activity.info().workflow_id, name, dict(inputs)))
            return fake(inputs)

        return recorded

    def by(self, workflow_id: str, contract: str) -> list[dict[str, Any]]:
        return [given for id, name, given in self.calls if id == workflow_id and name == contract]


async def open_case(
    setup: Setup,
    definition: dict[str, Any],
    file: Mapping[str, Any],
    id: str,
    plans: Sequence[Any] = (),
    cases: Mapping[str, Any] | None = None,
    opened_by: str | None = None,
    opener_roles: Sequence[str] = (),
    workflow: Any = DevelopmentCases,
) -> Any:
    """Open the case `id`: on a release made in memory when it pins plans or children (only a
    release pins them, D74), else as a draft."""
    on = release_of(definition, 1, plans, cases) if plans or cases else definition
    return await start_case(setup.client, workflow, on, file, id, QUEUE, opened_by, opener_roles)


def child_of(setup: Setup, id: str, entry: str) -> Any:
    """The child case a case step's run opened: its own workflow, `<case ID>/<entry>` (D75)."""
    return case_handle(setup.client, DevelopmentCases, f"{id}/{entry}")


async def answer_plan(
    setup: Setup, id: str, entry: str, wait: str, outcome: str, by: str, roles: list[str]
) -> None:
    """Answer the wait `wait` inside the plan a plan step's run started (`<case ID>/<entry>`)."""
    plan = setup.client.get_workflow_handle(f"{id}/{entry}")
    await plan.signal("answer", Sent(wait, outcome, by, sorted(roles)))


async def quiet(case: Any, still: float = 2.0, bound: float = 40.0) -> CaseReport:
    """The case's report once it has stopped changing for `still` seconds (real time)."""
    last, since, waited = None, 0.0, 0.0
    while waited < bound:
        try:
            now = await asyncio.wait_for(report(case), timeout=10)
        except Exception:  # noqa: BLE001 (not started yet, or busy: asked again)
            now = None
        if now is not None and last is not None and now == last:
            since += 0.1
            if since >= still:
                return now
        else:
            since = 0.0
        last = now
        await asyncio.sleep(0.1)
        waited += 0.1
    raise AssertionError(f"the case never went quiet; last report: {last}")


async def wait_for(
    case: Any, holds: Callable[[CaseReport], bool], bound: float = 40.0
) -> CaseReport:
    """The case's report once `holds` is true of it."""
    waited, now = 0.0, None
    while waited < bound:
        # Not started yet, or busy: asked again.
        with contextlib.suppress(Exception):
            now = await asyncio.wait_for(report(case), timeout=10)
            if holds(now):
                return now
        await asyncio.sleep(0.1)
        waited += 0.1
    raise AssertionError(f"the case never got there; last report: {now}")


async def pass_time(setup: Setup, days: float) -> None:
    """Let `days` pass on the test server, in an instant."""
    await setup.environment.sleep(timedelta(days=days, seconds=1))


def show(title: str, now: CaseReport, skip: int = 0) -> None:
    print(f"--- {title}: status {now.status}")
    for line in now.history[skip:]:
        print("      ", line[:260])
    if now.needs_attention:
        print("       needs attention:", [line[:200] for line in now.needs_attention])


def said(now: CaseReport, text: str) -> bool:
    """Whether a line of the report's history holds `text`."""
    return any(text in line for line in now.history)


def fakes_with(received: Received, more: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return received.wrap({**FAKES, **(more or {})})


class Verdicts:
    """One line per finding, and the probe's RESULT line."""

    def __init__(self) -> None:
        self.lines: dict[str, tuple[str, str]] = {}

    def say(self, finding: str, verdict: str, what: str) -> None:
        self.lines[finding] = (verdict, what)

    def result(self) -> None:
        print()
        for finding, (verdict, what) in self.lines.items():
            print(f"{finding} on Temporal: {verdict} - {what}")
        again = [f for f, (verdict, _) in self.lines.items() if verdict.startswith("REPRODUCED")]
        total = len(self.lines)
        if again:
            print(
                f"RESULT: BROKEN - {len(again)} of {total} findings reproduce on Temporal: "
                + ", ".join(again)
            )
        else:
            print(f"RESULT: HELD - none of the {total} findings reproduces on Temporal")
