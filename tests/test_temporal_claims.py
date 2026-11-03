"""Layer 17a on Temporal: claiming and giving back are signals, recorded in the case's history like
an answer, and the holders cross continue-as-new with the case's state (brief, D69).

See docs/layers/17-assignment.md (17a).
"""

from temporalio.client import Client
from test_temporal_case import (
    LARGE,
    PEOPLE,
    QUEUE,
    REFUND,
    REVIEW_FORM,
    SwitchingCases,
    on_temporal,
    reported,
    runs_of,
)

from ventoux.temporal.cases import CaseReport, answer, claim, give_back, start_case


def test_claims_are_signals_recorded_and_carried_across_continue_as_new() -> None:
    # Ana claims the review; Sam's claim and Sam's answer are refused and recorded, and the case
    # waits on; Ana gives it back. The case continues as new every 2 events, so the holder
    # crosses a switch (brief, D27) (brief, D69).
    async def scenario(client: Client) -> tuple[CaseReport, CaseReport, tuple[str, str]]:
        case = await start_case(client, SwitchingCases, REFUND, LARGE, "refund-1", QUEUE)
        await claim(case, "review#1", "ana", PEOPLE["ana"])
        await claim(case, "review#1", "sam", PEOPLE["sam"])
        await answer(case, "review#1", "approve", "sam", PEOPLE["sam"], REVIEW_FORM)
        held = await reported(case, lambda now: "\n".join(now.history).count("refused") == 2)
        await give_back(case, "review#1", "ana", PEOPLE["ana"])
        back = await reported(case, lambda now: now.history[-1] == "ana gave back review#1")
        return held, back, await runs_of(client, "refund-1")

    held, back, (first, last) = on_temporal(scenario, cases=SwitchingCases)
    assert last != first  # the case continued as new at least once
    assert held.assignees == {"review#1": "ana"}
    assert held.waiting_for == ["review by support"]
    assert held.history[-3:] == [
        "ana claimed review#1 as support",
        (
            "refused sam's claim of review#1: ana holds review#1; ask someone who assigns to "
            "reassign it"
        ),
        (
            "refused sam's answer approve to review#1: ana holds review#1: ask ana to give it "
            "back, or someone who assigns to reassign it"
        ),
    ]
    assert held.status == "open"
    assert back.assignees == {}
