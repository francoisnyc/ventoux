"""Fresh facts: time on events, when each fact was obtained, and `max_age` (layer 9d).

See docs/layers/09-case-data.md and docs/guides/case-data.md.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.freshness import TimeRefused
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseState, Obtained, Opened
from ventoux.testing import CATALOG, START, later, load_definition, run_case

ROOT = Path(__file__).parent.parent
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
GUIDE = (ROOT / "docs" / "guides" / "case-data.md").read_text()
FILE = {"order_id": "ord-1", "amount": Decimal(80)}
PEOPLE = {"ana": ["support"], "sam": ["support-lead"]}
HOUR = 60 * 60


def refund_fresh() -> dict[str, Any]:
    """The refund with the guide's `check_order` and `pay`, as the guide writes them under
    "Saying how fresh a step needs its facts": the tests run what the guide shows."""
    section = GUIDE.split("### Saying how fresh a step needs its facts")[1]
    block = section.split("```json\n")[1].split("```")[0]
    steps: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    definition = copy.deepcopy(REFUND)
    definition["steps"] = {"check_order": steps["check_order"], **definition["steps"]}
    definition["steps"]["pay"] = steps["pay"]
    return definition


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
        # A run's, at the time of the event that started it.
        "pay.outcome": Obtained(reviewed, "pay#1"),
        "pay.refund_id": Obtained(reviewed, "pay#1"),  # its output
    }


def test_max_age_is_checked_when_the_definition_is_read() -> None:
    # Negative first: each mistake is refused with its line, for the author (learning question 34).
    def refused(change: Any) -> str:
        definition = refund_fresh()
        change(definition["steps"])
        with pytest.raises(CaseInvalid) as error:
            parse_case(definition)
        return str(error.value)

    def age(written: str) -> Any:
        return lambda steps: steps["pay"]["max_age"].update({"check_order.status": written})

    unit = 'steps.pay.max_age.check_order.status: an age looks like "30m", "12h" or "1d"'
    for wrong in ("1w", "1", "d", "-1d", "1.5d", " 1d", "١d"):
        assert refused(age(wrong)) == unit
    assert refused(age("0m")) == "steps.pay.max_age.check_order.status: an age is at least 1m"
    assert refused(lambda steps: steps["pay"]["max_age"].update({"amount": "1d"})) == (
        "steps.pay.max_age: pay doesn't read amount in its inputs, its when or its approval: "
        "name only what it reads"
    )
    assert refused(lambda steps: steps["review"].update({"max_age": {"amount": "1d"}})) == (
        "steps.review.max_age: not a field here"
    )
    # A well-formed one is read, on an activity, a workflow or a plan step.
    definition = refund_fresh()
    definition["steps"]["settle"] = {
        "kind": "plan",
        "display": {"title": "Settle the refund"},
        "plan": "refund-order@1",
        "inputs": {"amount": {"var": "approved_amount"}},
        "max_age": {"approved_amount": "12h"},
    }
    definition["steps"]["kyc"] = {
        "kind": "workflow",
        "display": {"title": "Check the customer"},
        "workflow": "kyc.check@1",
        "inputs": {"customer_id": {"var": "order_id"}},
        "max_age": {"order_id": "30m"},
    }
    case = parse_case(definition)
    assert case.steps["pay"].max_age == {"check_order.status": "1d"}  # type: ignore[union-attr]
    assert case.steps["settle"].max_age == {"approved_amount": "12h"}  # type: ignore[union-attr]
    assert case.steps["kyc"].max_age == {"order_id": "30m"}  # type: ignore[union-attr]
