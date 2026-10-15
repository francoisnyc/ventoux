"""Fresh facts: time on events, when each fact was obtained, and `max_age` (layer 9d).

See docs/layers/09-case-data.md and docs/guides/case-data.md.
"""

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from ventoux.case.definition import parse_case
from ventoux.case.freshness import TimeRefused
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseState, Obtained, Opened
from ventoux.testing import CATALOG, START, later, load_definition, run_case

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
FILE = {"order_id": "ord-1", "amount": Decimal(80)}
PEOPLE = {"ana": ["support"], "sam": ["support-lead"]}
HOUR = 60 * 60


def test_an_event_says_when_it_happened() -> None:
    # Fail closed: a time that isn't a whole number of seconds is refused, never rounded or
    # guessed, and the case is left as it was.
    case = parse_case(REFUND)
    for wrong, kind in ((Decimal(START), "Decimal"), (float(START), "float"), (True, "bool")):
        with pytest.raises(TimeRefused) as refused:
            decide(case, CATALOG, CaseState("t"), Opened(FILE, None, at=wrong))  # type: ignore[arg-type]
        assert str(refused.value) == (
            f"an event's time is a whole number of seconds since the epoch, and this one is a "
            f"{kind}: stamp it from the workflow's time"
        )
    opened, _ = decide(case, CATALOG, CaseState("t"), Opened(FILE, None, at=START))
    before = copy.deepcopy(opened)
    answer = Answered(
        "review",
        "approve",
        "ana",
        frozenset({"support"}),
        {"approved_amount": Decimal(80)},
        at=Decimal(START),  # type: ignore[arg-type]
    )
    with pytest.raises(TimeRefused):
        decide(case, CATALOG, opened, answer)
    assert opened == before


def test_every_fact_knows_when_it_was_obtained() -> None:
    run = run_case(
        REFUND,
        file={"order_id": "ord-1", "amount": 80},
        answers=[later("2h"), ("review", "approve", "ana", {"approved_amount": 80})],
        people=PEOPLE,
    )
    assert run.reached("pay")
    reviewed = START + 2 * HOUR
    assert run.state.obtained == {
        "order_id": Obtained(START, None),  # the opening
        "amount": Obtained(START, None),
        "review.outcome": Obtained(reviewed, None),  # a person's answer
        "approved_amount": Obtained(reviewed, None),  # its form
        "pay.outcome": Obtained(
            reviewed, "pay#1"
        ),  # a run, at the time of the event that started it
        "pay.refund_id": Obtained(reviewed, "pay#1"),  # its output
    }
