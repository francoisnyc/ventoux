"""Attachments on Temporal: an answer giving an option and an attachment is held while both
checks run as activities, refused if the store didn't issue the ID, taken once both vouch; the
history replays without asking either system again.

See docs/layers/16-field-types.md (16c) and brief D68.
"""

from typing import Any

from temporalio import workflow
from temporalio.api.history.v1 import History
from temporalio.client import Client, WorkflowHistory
from temporalio.converter import DataConverter
from test_attachments import ADJUSTERS, ISSUED, stored, with_branch
from test_options import OPEN_BRANCHES
from test_temporal_case import QUEUE, on_temporal, replay, reported

from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow, answer, start_case
from ventoux.testing import development_converter

ASKED: list[str] = []  # each value a system was asked about, in order


def holds(inputs: dict[str, Any]) -> dict[str, Any]:
    """The branches system's answer, as an activity."""
    ASKED.append(inputs["option"])
    return {"held": inputs["option"] in OPEN_BRANCHES}


def issued(inputs: dict[str, Any]) -> dict[str, Any]:
    """The documents store's answer, as an activity."""
    ASKED.append(inputs["attachment"])
    return {"issued": inputs["attachment"] in ISSUED}


# Temporal: a case workflow whose catalog has branches' option check and the documents store.
@workflow.defn(name="ventoux.case")
class CasesWithStores(CaseWorkflow):
    catalog = stored()

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def corrected(converter: DataConverter) -> tuple[CaseReport, WorkflowHistory]:
    """The claim on the test server: Ana gives a branch and a receipt the store didn't issue,
    then corrects the receipt. Its end, and its history."""

    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory]:
        case = await start_case(client, CasesWithStores, with_branch(), {}, "claim-1", QUEUE)
        wrong = {"branch": "BR-0142", "receipt": "doc-0000"}
        await answer(case, "assess#1", "accept", "ana", ADJUSTERS["ana"], wrong)
        refused = "refused ana's answer accept"
        await reported(case, lambda now: any(refused in line for line in now.history))
        right = {"branch": "BR-0142", "receipt": "doc-7f3a"}
        await answer(case, "assess#1", "accept", "ana", ADJUSTERS["ana"], right)
        return await case.result(), await case.fetch_history()

    ASKED.clear()
    activities = {"branches.holds@1": holds, "documents.issued@1": issued}
    return on_temporal(scenario, activities, cases=CasesWithStores, converter=converter)


def test_an_option_and_an_attachment_are_checked_on_temporal_then_taken() -> None:
    ended, _ = corrected(development_converter())
    # Both checks ran as activities, for each answer; the refusal and the taking are both kept,
    # and the case file holds the ID, never a file (brief, D68).
    assert sorted(ASKED) == sorted(["BR-0142", "doc-0000", "BR-0142", "doc-7f3a"])
    assert ended.history == [
        "opened by system:opener, with nothing",
        "started assess#1: waiting for accept or deny by adjuster",
        "refused ana's answer accept: receipt is not a document documents issued",
        (
            "ana answered assess#1 accept as adjuster, setting branch and receipt, checked by "
            "branches.holds@1 and documents.issued@1"
        ),
        "assess#1 done",
        "closed: nothing left to do",
    ]
    assert ended.status == "closed"


def test_a_case_with_an_attachment_replays_without_asking_the_store_again() -> None:
    converter = development_converter()
    _, history = corrected(converter)
    ASKED.clear()
    # Temporal: each check's answer is read back from history; no activity is called again.
    replay(history, CasesWithStores, converter)
    assert ASKED == []


def sealed() -> dict[str, Any]:
    """The claim with its branch and its receipt both sensitive, seen by adjusters."""
    definition = with_branch()
    for name in ("branch", "receipt"):
        definition["fields"][name] |= {"sensitive": True, "visible_to": ["adjuster"]}
    return definition


def accepted(converter: DataConverter) -> tuple[CaseReport, WorkflowHistory]:
    """The claim with sensitive fields on the test server: Ana gives a branch and a receipt, both
    held. Its end, and its history."""

    async def scenario(client: Client) -> tuple[CaseReport, WorkflowHistory]:
        case = await start_case(client, CasesWithStores, sealed(), {}, "claim-2", QUEUE)
        given = {"branch": "BR-0142", "receipt": "doc-7f3a"}
        await answer(case, "assess#1", "accept", "ana", ADJUSTERS["ana"], given)
        return await case.result(), await case.fetch_history()

    ASKED.clear()
    activities = {"branches.holds@1": holds, "documents.issued@1": issued}
    return on_temporal(scenario, activities, cases=CasesWithStores, converter=converter)


def test_a_sensitive_option_and_attachment_never_cross_temporal_in_plain_text() -> None:
    # A check is an activity, and Temporal writes an activity's input into the case's history,
    # kept for its retention period and read by anyone with namespace access. So the value a
    # sensitive field's check is asked with crosses sealed under the case's key, and destroying
    # the key forgets it there too (brief, D15, D31, D68). Each system is still asked the plain
    # value: the codec opens it for the activity, inside the worker.
    ended, history = accepted(development_converter())
    assert ended.status == "closed"
    assert sorted(ASKED) == ["BR-0142", "doc-7f3a"]
    # Temporal: the history as the server stores it, every payload of every event.
    raw = History(events=history.events).SerializeToString()
    for value in ("BR-0142", "doc-7f3a"):
        assert value.encode() not in raw, value
