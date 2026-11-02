"""Options on Temporal: a person's answer is held while its system's check runs as an activity,
then refused or taken; the history replays without asking the system again, and the case never
continues as new while an answer is held.

See docs/layers/16-field-types.md (16b) and brief D67.
"""

from typing import Any

from temporalio import workflow
from temporalio.client import Client, WorkflowHistory
from temporalio.converter import DataConverter
from test_options import ADJUSTERS, OPEN_BRANCHES, checked, claim
from test_temporal_case import QUEUE, on_temporal, replay, reported, runs_of

from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow, answer, start_case
from ventoux.testing import development_converter

ASKED: list[str] = []  # each option the branches system was asked about, in order


def holds(inputs: dict[str, Any]) -> dict[str, Any]:
    """The branches system's answer, as an activity: whether it holds the option asked about."""
    ASKED.append(inputs["option"])
    return {"held": inputs["option"] in OPEN_BRANCHES}


# Temporal: a case workflow whose catalog has the branches system and its option check.
@workflow.defn(name="ventoux.case")
class CasesWithBranches(CaseWorkflow):
    catalog = checked()

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


# Temporal: the same, continuing as new after every event: an answer is one event, so the run
# would switch while its check runs, if anything let it (brief, D27).
@workflow.defn(name="ventoux.case")
class SwitchingWithBranches(CaseWorkflow):
    catalog = checked()
    events_per_run = 1

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


EXPECTED = [
    "opened by system:opener, with nothing",
    "started assess#1: waiting for accept or deny by adjuster",
    "refused ana's answer accept: branch is not one of the options branches holds",
    "ana answered assess#1 accept as adjuster, setting branch, checked by branches.holds@1",
    "assess#1 done",
    "closed: nothing left to do",
]


def corrected(
    cases: type[CaseWorkflow], converter: DataConverter
) -> tuple[CaseReport, WorkflowHistory, tuple[str, str]]:
    """The claim on the test server: Ana gives a branch the system doesn't hold, then corrects
    it. Its end, its latest run's history, and its first and latest runs."""

    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory, tuple[str, str]]:
        case = await start_case(client, cases, claim(), {}, "claim-1", QUEUE)
        await answer(case, "assess#1", "accept", "ana", ADJUSTERS["ana"], {"branch": "BR-9999"})
        refused = "refused ana's answer accept"
        await reported(case, lambda now: any(refused in line for line in now.history))
        await answer(case, "assess#1", "accept", "ana", ADJUSTERS["ana"], {"branch": "BR-0142"})
        ended = await case.result()
        return ended, await case.fetch_history(), await runs_of(client, "claim-1")

    ASKED.clear()
    return on_temporal(scenario, {"branches.holds@1": holds}, cases=cases, converter=converter)


def test_an_option_not_held_is_refused_on_temporal_and_the_corrected_one_taken() -> None:
    ended, _, _ = corrected(CasesWithBranches, development_converter())
    # The check ran as an activity, once per answer; the refusal and the taking are both kept.
    assert ASKED == ["BR-9999", "BR-0142"]
    assert ended.history == EXPECTED
    assert ended.status == "closed"


def test_a_case_with_a_checked_option_replays_without_asking_the_system_again() -> None:
    converter = development_converter()
    _, history, _ = corrected(CasesWithBranches, converter)
    ASKED.clear()
    # Temporal: the check's answer is read back from history; the activity isn't called again.
    replay(history, CasesWithBranches, converter)
    assert ASKED == []


def test_a_case_never_continues_as_new_while_an_answer_is_held() -> None:
    converter = development_converter()
    ended, history, (first, last) = corrected(SwitchingWithBranches, converter)
    # It did continue as new, but only once each check was back: a held answer is never carried,
    # so each answer was refused or taken in the run that asked (brief, D27) (brief, D67).
    assert first != last
    assert ended.history == EXPECTED
    replay(history, SwitchingWithBranches, converter)
