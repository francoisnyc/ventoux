"""The fix of a rejected retry: a retry that doesn't start needs attention again (brief, D26).

See docs/layers/fix-retry-rejected.md.
"""

import copy
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import parse_case
from ventoux.case.memory import Driver, no_plans
from ventoux.case.state import Answered, CaseState, CloseAsked, Event, Opened, Proposed, Retried
from ventoux.core.sensitive import Sensitive
from ventoux.testing import (
    CATALOG,
    DAY,
    FAKES,
    START,
    AnswerRefused,
    CloseRefused,
    ProposalRefused,
    RetryRefused,
    as_json,
    load_definition,
    wrapped,
)

ROOT = Path(__file__).parent.parent
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support-lead"], "omar": ["operations"]}
DUPLICATE = {"display": {"title": "Duplicate request"}, "roles": ["support", "operations"]}


# --- Slice 1: the invariant, over generated cases ---


def generated_definition(fresh: bool, held: bool) -> dict[str, Any]:
    """The refund, with a review that may be proposed again, a `hold` task whose answer makes a
    rule stop the review, and a close reason; `fresh`: pay needs the order's status at most a
    day old; `held`: an `audit` task reaches the case's only `closes_when` milestone."""
    definition = copy.deepcopy(REFUND)
    steps = definition["steps"]
    steps["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    steps["hold"] = {
        "kind": "task",
        "display": {"title": "Hold the review"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "repeatable": True,
        "outcomes": {"hold": {"display": {"title": "Hold it"}}},
    }
    definition["rules"] = {
        "halt": {
            "display": {"title": "Stop the review on hold"},
            "on": {"answered": "hold"},
            "then": {"stop": ["review"]},
        }
    }
    definition["close_reasons"] = {"duplicate": DUPLICATE}
    if fresh:
        steps["check_order"] = {
            "kind": "activity",
            "display": {"title": "Look the order up"},
            "activity": "orders.lookup@2",
            "inputs": {"order_id": {"var": "order_id"}},
        }
        steps["pay"] |= {
            "requires": ["review", "check_order"],
            "when": {
                "and": [
                    {"==": [{"var": "review.outcome"}, "approve"]},
                    {"==": [{"var": "check_order.status"}, "delivered"]},
                ]
            },
            "max_age": {"check_order.status": "1d"},
        }
    if held:
        definition["milestones"] = {"audited": {"display": {"title": "Audited"}}}
        steps["audit"] = {
            "kind": "task",
            "display": {"title": "Audit the case"},
            "roles": ["support"],
            "outcomes": {"done": {"display": {"title": "Audited"}, "reaches": ["audited"]}},
        }
        definition["closes_when"] = ["audited"]
    return definition


def next_events(chance: random.Random, state: CaseState, at: int) -> list[Event]:
    """What a person could do next, as events: answer what is open, propose the review or the
    hold, retry what failed, close the case. Some are refused; the API would refuse them too."""

    def roles(who: str) -> frozenset[str]:
        return frozenset(PEOPLE[who])

    events: list[Event] = []
    for entry in state.waiting:
        if entry.startswith("review#"):
            amount = chance.choice([80, 250])
            form = {"approved_amount": Sensitive(Decimal(amount))}
            events.append(Answered(entry, "approve", "ana", roles("ana"), form, at=at))
            events.append(Answered(entry, "reject", "ana", roles("ana"), None, at=at))
        elif entry.startswith("pay.approval#"):
            for outcome in ("approve", "reject"):
                events.append(Answered(entry, outcome, "sam", roles("sam"), None, at=at))
        else:
            outcome = "hold" if entry.startswith("hold#") else "done"
            events.append(Answered(entry, outcome, "ana", roles("ana"), None, at=at))
    events += [Proposed(step, "ana", roles("ana"), at=at) for step in ("review", "hold")]
    failed = [run.entry for run in state.runs if run.status == "failed"]
    # Each retry offered three times: an operator acting is what the paths found turn on.
    events += [Retried(entry, "omar", roles("omar"), at=at) for entry in failed] * 3
    if chance.random() < 0.05:
        events.append(CloseAsked("duplicate", "ana", roles("ana"), at=at))
    return events


def generated_case(seed: int) -> list[str]:
    """Play one generated case of up to 25 events; the hook in `conftest.py` checks the
    invariant after every decision. What was played, for the failure's message."""
    chance = random.Random(seed)  # a test's randomness, seeded: the engine reads none
    definition = generated_definition(fresh=chance.random() < 0.5, held=chance.random() < 0.5)
    case = parse_case(definition)

    def pay(inputs: dict[str, Any]) -> dict[str, Any]:
        if chance.random() < 0.5:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-1"}

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        return {"status": chance.choice(["delivered", "delivered", "cancelled"])}

    activities = {**FAKES, "payments.refund@2": pay, "orders.lookup@2": lookup}
    driver = Driver(case, CATALOG, activities, frozenset(), no_plans, {})
    at = START
    file = {"order_id": "ord-1", "amount": Decimal(300)}
    state = driver.carry(CaseState("generated"), Opened(wrapped(case, as_json(file)), None, at=at))
    played = [f"seed {seed}, steps {sorted(definition['steps'])}"]
    for _ in range(25):
        if state.phase != "open":
            break
        if chance.random() < 0.15:
            at += 2 * DAY  # facts age: a fresh one is fetched again
            played.append("two days later")
            continue
        event = chance.choice(next_events(chance, state, at))
        played.append(repr(event))
        try:
            state = driver.carry(state, event)
        except (AnswerRefused, ProposalRefused, RetryRefused, CloseRefused):
            played.append("  refused")
        except AssertionError as silent:
            raise AssertionError("\n".join([str(silent), *played])) from None
    return played


# Seen failing on main, each a retry left waiting for nothing (the note's paths A, C and F); each
# mark comes off with the slice that fixes its path, and strict fails one that passes early.
SILENT_ON_MAIN = {3, 59, 97, 165, 303, 323, 369, 418, 463, 610, 871, 886}


@pytest.mark.parametrize(
    "seed",
    [
        pytest.param(seed, marks=pytest.mark.xfail(strict=True, reason="a silent retry"))
        if seed in SILENT_ON_MAIN
        else seed
        for seed in range(1000)
    ],
)
def test_generated_cases_show_what_is_pending(seed: int) -> None:
    generated_case(seed)
