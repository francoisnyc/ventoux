"""The fix of a rejected retry: a retry that doesn't start needs attention again (brief, D26).

See docs/layers/fix-retry-rejected.md.
"""

import copy
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from invariants import Silent

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
    finish,
    later,
    load_definition,
    propose,
    run_case,
    wrapped,
)

ROOT = Path(__file__).parent.parent
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support-lead"], "omar": ["operations"]}
DUPLICATE = {"display": {"title": "Duplicate request"}, "roles": ["support", "operations"]}


# --- Slice 1: the invariant, over generated cases ---


def generated_definition(fresh: bool, audited: bool, stays_open: bool = False) -> dict[str, Any]:
    """The refund, with a review that may be proposed again, a `hold` task whose answer makes a
    rule stop the review, and a close reason. `fresh`: pay also requires the order looked up, and
    runs only on a delivered order whose status is at most a day old. `audited`: once reviewed,
    an `audit` task reaches the case's only `closes_when` milestone, and a goodwill refund asks
    its own approval. `stays_open`: only a person closes the case."""
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
    if audited:
        definition["milestones"] = {"audited": {"display": {"title": "Audited"}}}
        steps["audit"] = {
            "kind": "task",
            "display": {"title": "Audit the case"},
            "roles": ["support"],
            "requires": ["review"],
            "outcomes": {"done": {"display": {"title": "Audited"}, "reaches": ["audited"]}},
        }
        steps["goodwill"] = {
            "kind": "activity",
            "display": {"title": "Refund a goodwill gesture"},
            "activity": "payments.refund@2",
            "requires": ["review"],
            "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
            "approval": {"roles": ["support-lead"], "display": {"reason": "Goodwill needs a lead"}},
        }
        definition["closes_when"] = ["audited"]
    if stays_open:
        definition["stays_open"] = True
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
        elif ".approval#" in entry:  # pay's or goodwill's
            for outcome in ("approve", "reject"):
                events.append(Answered(entry, outcome, "sam", roles("sam"), None, at=at))
        else:
            outcome = "hold" if entry.startswith("hold#") else "done"
            events.append(Answered(entry, outcome, "ana", roles("ana"), None, at=at))
    events += [Proposed(step, "ana", roles("ana"), at=at) for step in ("review", "hold")]
    failed = [run.entry for run in state.runs if run.status == "failed"]
    # Each retry offered three times: an operator acting is what the paths found turn on.
    events += [Retried(entry, "omar", roles("omar"), at=at) for entry in failed] * 3
    if chance.random() < 0.05:  # now and then, a person may close the case
        events.append(CloseAsked("duplicate", "ana", roles("ana"), at=at))
    return events


def generated_case(seed: int) -> list[str]:
    """Play one generated case of up to 25 turns, each an event or two days passing; the hook in
    `conftest.py` checks the invariant after every decision. What was played, for the failure's
    message."""
    chance = random.Random(seed)  # a test's randomness, seeded: the engine reads none
    definition = generated_definition(
        fresh=chance.random() < 0.5,
        audited=chance.random() < 0.5,
        stays_open=chance.random() < 0.25,
    )
    case = parse_case(definition)

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:  # pay's and goodwill's
        if chance.random() < 0.5:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-1"}

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        if chance.random() < 0.2:
            raise ConnectionError("orders system down")
        return {"status": chance.choice(["delivered", "delivered", "cancelled"])}

    activities = {**FAKES, "payments.refund@2": refund, "orders.lookup@2": lookup}
    driver = Driver(case, CATALOG, activities, holding=frozenset(), plans=no_plans, workflows={})
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
        except Silent as silent:
            raise Silent("\n".join([str(silent), *played])) from None
    return played


# Seen failing on main, by the note's path (its table) at the first silent decision: each seed's
# mark comes off with the slice that fixes its path (A and D in slice 2, C', F and I in slice 3,
# K in slice 4). C and E' come only after another silent state, which stops the case first, so
# their own tests are scripted, as are L and M, which need a refresh held across a person's act.
SILENT_ON_MAIN = {
    "A": {7, 79, 197, 229, 247, 254, 316, 384, 395, 440, 609, 638, 682, 762, 881},
    "D": {
        31,
        32,
        50,
        93,
        192,
        206,
        220,
        333,
        364,
        486,
        535,
        554,
        557,
        598,
        654,
        673,
        723,
        801,
        891,
        981,
    },
    "C'": {16, 75, 313, 323, 369, 394, 451, 492, 496, 497, 541, 612, 704, 791, 858, 876, 907},
    "F": {71, 511},
    "I": {73, 184, 340},
    "K": {393, 713, 753, 754},
}


def expected_to_fail(seed: int) -> Any:
    """The seed as a test parameter, marked if it was seen failing on main, naming its path.
    pytest: `pytest.param` gives one seed a mark; `xfail(strict=True, raises=Silent)` expects the
    invariant's own failure, and fails the run if the seed passes, or fails any other way."""
    for path, seeds in SILENT_ON_MAIN.items():
        if seed in seeds:
            reason = f"path {path}, seen silent on main"
            return pytest.param(
                seed, marks=pytest.mark.xfail(strict=True, raises=Silent, reason=reason)
            )
    return seed


# pytest: `parametrize` runs the test once for each seed.
@pytest.mark.parametrize("seed", [expected_to_fail(seed) for seed in range(1000)])
def test_generated_cases_show_what_is_pending(seed: int) -> None:
    generated_case(seed)


# --- Slice 1: the paths the generated cases can't reach, scripted ---

FILE = {"order_id": "ord-1", "amount": 300}
DELIVERED = {"orders.lookup@2": lambda inputs: {"status": "delivered"}}


@pytest.mark.xfail(strict=True, raises=Silent, reason="path L, fixed in slice 5")
def test_a_given_approval_lapses_with_its_requirement() -> None:
    # Path L. Sam approves pay while its fact is fetched again; the review is proposed again, the
    # fact lands, and a rule stops the review. Nothing can spend the approval now, so it lapses,
    # saying why; once the review completes again, pay asks a new one (the note, decision 5).
    definition = generated_definition(fresh=True, audited=False)
    before = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),  # pay asks its approval
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given: the order's status is fetched again
        propose("review", "ana"),  # review#2 opens while the refresh runs
        finish("check_order#2"),  # the fact lands; pay waits for review#2, shown
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # halt stops review#2
    ]
    run = run_case(definition, FILE, before, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert "lapsed pay.approval#1: pay requires review, which hasn't completed" in run.history
    assert run.state.given == {}
    again = [
        *before,
        propose("review", "ana"),
        ("review#3", "approve", "ana", {"approved_amount": 250}),
    ]
    run = run_case(definition, FILE, again, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert run.waiting_for == ["approval of pay by support-lead"]


def test_a_given_approval_survives_a_review_answered_the_same() -> None:
    # Path L's other branch: the review proposed again is answered with the values the approval
    # saw, so pay runs on it (brief, D11) (the note, decision 5).
    definition = generated_definition(fresh=True, audited=False)
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        ("pay.approval#1", "approve", "sam"),
        propose("review", "ana"),
        finish("check_order#2"),
        ("review#2", "approve", "ana", {"approved_amount": 250}),
    ]
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert run.reached("pay")
    assert "asked pay.approval#2: approval of pay by support-lead" not in run.history


@pytest.mark.xfail(strict=True, raises=Silent, reason="path M, fixed in slice 4")
def test_a_proposal_waiting_when_the_close_is_held_is_dropped() -> None:
    # Path M. Ana proposes pay, which waits for its fact; meanwhile a rule fails and the audit
    # reaches the case's only closes_when milestone, so the close is held. Nothing new starts,
    # so the proposal is dropped then, saying why (the note, decision 3) (brief, D39).
    definition = generated_definition(fresh=True, audited=True)
    definition["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support"]}
    definition["fields"]["note"] = {"type": "string", "display": {"title": "A note nobody sets"}}
    definition["rules"]["broken"] = {
        "display": {"title": "Read a note on hold"},
        "on": {"answered": "hold"},
        "when": {"==": [{"var": "note"}, "x"]},  # nobody sets it: the rule fails, for a person
        "then": {"stop": ["hold"]},
    }
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 80}),
        later("2d"),
        propose("pay", "ana"),  # waits for the order's status, fetched again
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # broken#1 fails
        ("audit", "done", "ana"),  # audited is reached: the close is held by broken#1
        finish("check_order#2"),
    ]
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert (
        "dropped ana's proposal of pay: audited is reached, so the case closes once broken#1 is "
        "retried, or a person closes it: nothing new starts"
    ) in run.history
    assert run.state.waiting_to_start == []
    assert not any(line.startswith("scheduled pay") for line in run.history)
