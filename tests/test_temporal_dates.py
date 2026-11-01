"""Dates on Temporal: a day crosses every payload as `YYYY-MM-DD` and is read back by its type.

The case is opened with a date, answered with one, sent one by an event, and continues as new in
between; after the crossing it still decides on days. See docs/layers/16-field-types.md (16a)
and brief D66.
"""

from datetime import date
from typing import Any

from temporalio.client import Client
from test_dates import ADJUSTERS, reportable
from test_temporal_case import QUEUE, SwitchingCases, on_temporal, reported, runs_of

from ventoux.case.visibility import CaseView
from ventoux.temporal.cases import CaseReport, answer, close, propose, send_event, start_case, view


def proposed() -> dict[str, Any]:
    """The reportable claim, its settlement proposed by the adjuster rather than started: so it
    stays open until the adjuster closes it (brief, D10)."""
    definition = reportable()
    definition["steps"]["settle"] |= {"automatic": False, "proposed_by": ["adjuster"]}
    definition["stays_open"] = True
    definition["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["adjuster"]}}
    return definition


def test_dates_cross_continue_as_new_and_the_case_still_decides_on_days() -> None:
    async def scenario(client: Client) -> tuple[CaseView, CaseReport, tuple[str, str]]:
        # Given as Python days: the client writes each as its text, the case reads it back.
        opened = {"policy_start": date(2026, 1, 1)}
        case = await start_case(client, SwitchingCases, proposed(), opened, "claim-1", QUEUE)
        accepted = {"incident_date": date(2026, 10, 31)}
        await answer(case, "assess#1", "accept", "ana", ADJUSTERS["ana"], accepted)
        await send_event(case, "reported", {"on": date(2026, 11, 2)}, "system:portal")
        # Two events decided: the case continues as new, its dates crossing as text. Then Ana
        # proposes `settle`, and admission reads incident_date >= policy_start in the new run:
        # it is admitted only if both were read back as days.
        await reported(case, lambda now: now.waiting_at == [])
        await propose(case, "settle", "ana", ADJUSTERS["ana"])
        await reported(case, lambda now: now.waiting_at == ["settle#1"])
        seen = await view(case, ADJUSTERS["ana"])
        await answer(case, "settle#1", "settled", "ana", ADJUSTERS["ana"])
        await close(case, "done", "ana", ADJUSTERS["ana"])
        return seen, await case.result(), await runs_of(client, "claim-1")

    seen, ended, (first, last) = on_temporal(scenario, cases=SwitchingCases)
    assert first != last  # it did continue as new
    # A query's answer is a payload: each date as its text, the same in every language.
    assert seen.values["policy_start"] == "2026-01-01"
    assert seen.values["incident_date"] == "2026-10-31"
    assert seen.values["reported.on"] == "2026-11-02"
    assert ended.status == "closed"
