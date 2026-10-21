"""The fix of a rejected retry: a retry that doesn't start needs attention again (brief, D26).

See docs/layers/fix-retry-rejected.md.
"""

import copy
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from invariants import Silent, unshown
from test_case import OPERATORS, SMALL, SMALL_REVIEW, goodwill_while_held

from ventoux.case.definition import parse_case
from ventoux.case.memory import Activity, CaseRun, Driver, no_plans, outcome_of
from ventoux.case.runtime import decide
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
    close,
    finish,
    later,
    load_definition,
    propose,
    retry,
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


def generated_case(seed: int) -> CaseState:
    """Play one generated case of up to 25 turns, each an event or two days passing; the hook in
    `conftest.py` checks the invariant after every decision. Where the case ended."""
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
    return state


def seeds(listed: str) -> set[int]:
    """The seeds written in `listed`, separated by spaces: `"7 79 197"`."""
    return {int(seed) for seed in listed.split()}


# Silent before the fix, by the path of the note's table each seed is silent on now: its mark
# comes off with the slice that fixes that path; none is left. A seed whose path is fixed may play
# on to another, as 229 did after A. L and M are scripted below: they need a refresh held across a
# person's act.
SILENT_ON_MAIN: dict[str, set[int]] = {}
# The seeds that were silent on a path now fixed, with the line its fix writes, as a part it
# contains and its ending: each seed must still reach it, so a change to the generated cases can't
# drop the path unseen.
FIXED = {
    "A": (
        seeds("7 79 197 229 247 254 316 384 394 395 440 496 541 609 638 682 762 881"),
        ("won't run: ", ", so it needs attention again"),
    ),
    "D": (
        seeds(
            "16 31 32 50 75 93 192 206 220 333 364 486 535 554 557 598 654 673 704 723 801 891 981"
        ),
        ("won't run: ", ", so it needs attention again"),
    ),
    "C": (seeds("313 369 492 497 791"), ("its retry can't start: ", " is false now")),
    "E'": (seeds("229 323 876"), ("its retry can't start: ", ", which hasn't completed")),
    "F": (seeds("71 511"), ("its retry can't start: ", " is false now")),
    "K": (seeds("393 713 753 754"), ("goodwill not started: ", ": nothing new starts")),
}


def expected_to_fail(seed: int) -> Any:
    """The seed as a test parameter, marked if it is still silent, naming the path it is on now.
    pytest: `pytest.param` gives one seed a mark; `xfail(strict=True, raises=Silent)` expects the
    invariant's own failure, and fails the run if the seed passes, or fails any other way."""
    for path, marked in SILENT_ON_MAIN.items():
        if seed in marked:
            reason = f"path {path}, silent until its slice fixes it"
            return pytest.param(
                seed, marks=pytest.mark.xfail(strict=True, raises=Silent, reason=reason)
            )
    return seed


# pytest: `parametrize` runs the test once for each seed.
@pytest.mark.parametrize("seed", [expected_to_fail(seed) for seed in range(1000)])
def test_generated_cases_show_what_is_pending(seed: int) -> None:
    generated_case(seed)


@pytest.mark.parametrize("path", sorted(FIXED))
def test_the_generated_cases_reach_the_paths(path: str) -> None:
    # Each seed once silent on a fixed path now writes that fix's line; for D, while the close
    # is held, after the audit reached the case's closes_when milestone, and for A, not; for F,
    # as the fact fetched again lands, and for C, not.
    found, (part, ending) = FIXED[path]
    still_silent: set[int] = set().union(*SILENT_ON_MAIN.values())  # marked: silent elsewhere
    checked = sorted(found - still_silent)
    assert checked, f"no seed left to show path {path}"
    for seed in checked:
        history = generated_case(seed).history
        fixed = [i for i, said in enumerate(history) if part in said and said.endswith(ending)]
        assert fixed, f"seed {seed} no longer reaches path {path}"
        if path in ("A", "D"):  # the same line: told apart by whether the close is held
            held = "reached audited" in history[: fixed[0]]
            assert held == (path == "D"), f"seed {seed}: the close is {'' if held else 'not '}held"
        if path in ("C", "F"):  # the same line: told apart by whether a refresh just landed
            refreshed = "done, giving status" in history[fixed[0] - 1]
            assert refreshed == (path == "F"), f"seed {seed}: {'a' if refreshed else 'no'} refresh"


# --- Slice 1: the paths the generated cases can't reach, scripted ---

FILE = {"order_id": "ord-1", "amount": 300}
DELIVERED = {"orders.lookup@2": lambda inputs: {"status": "delivered"}}


def test_a_given_approval_lapses_with_its_requirement() -> None:
    # Path L. Sam approves pay while its fact is fetched again; the review is proposed again, the
    # fact lands, and a rule stops the review. Nothing can spend the approval now, so it lapses,
    # saying why; with nothing else to do, the case closes, as when an open approval is withdrawn
    # (brief, D10). In a case that stays open, once the review completes again, pay asks a new
    # approval (the note, decision 5).
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
    lapse = "lapsed pay.approval#1: pay requires review, which hasn't completed"
    assert run.history[-2:] == [lapse, "closed: nothing left to do"]
    assert run.state.given == {}
    definition["stays_open"] = True
    again = [
        *before,
        propose("review", "ana"),
        ("review#3", "approve", "ana", {"approved_amount": 250}),
    ]
    run = run_case(definition, FILE, again, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert lapse in run.history
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


def held_by_a_rule() -> dict[str, Any]:
    """The refund with the order looked up, `hold`, an `audit` reaching the case's only
    closes_when milestone, and `broken`, a rule on the hold's answer whose condition reads a
    note nobody sets: it fails, for a person, and so holds the close once the audit is done."""
    definition = generated_definition(fresh=True, audited=True)
    definition["fields"]["note"] = {"type": "string", "display": {"title": "A note nobody sets"}}
    definition["rules"]["broken"] = {
        "display": {"title": "Read a note on hold"},
        "on": {"answered": "hold"},
        "when": {"==": [{"var": "note"}, "x"]},
        "then": {"stop": ["hold"]},
    }
    return definition


HELD = (
    "audited is reached, so the case closes once broken#1 is retried, or a person closes it: "
    "nothing new starts"
)


def test_a_proposal_waiting_when_the_close_is_held_is_dropped() -> None:
    # Path M. Ana proposes pay, which waits for its fact; meanwhile a rule fails and the audit
    # reaches the case's only closes_when milestone, so the close is held. Nothing new starts,
    # so the proposal is dropped then, before its fact lands, saying why (the note, decision 3)
    # (brief, D39).
    definition = held_by_a_rule()
    definition["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support"]}
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
    dropped = run.history.index(f"dropped ana's proposal of pay: {HELD}")
    assert dropped < run.history.index("check_order#2 done, giving status from system:orders")
    assert run.state.waiting_to_start == []
    assert not any(line.startswith("scheduled pay") for line in run.history)


def test_an_approval_waiting_for_its_fact_when_the_close_is_held_is_let_go() -> None:
    # Path K, given before the close is held. Sam approves pay while its fact is fetched again;
    # then the audit holds the close. The approval can't be spent now, so it is let go in that
    # decision, before the fact lands, saying why (the note, decision 3).
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),  # pay asks pay.approval#1
        later("2d"),
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # broken#1 fails
        ("pay.approval#1", "approve", "sam"),  # given: the status is fetched again, held
        ("audit", "done", "ana"),  # the close is held by broken#1
    ]
    definition = held_by_a_rule()
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    after = run.history[run.history.index("reached audited") :]
    assert after.count(f"pay not started: {HELD}") == 1
    assert "pay" not in run.state.given


def test_an_approval_whose_requirement_is_on_its_way_when_the_close_is_held_is_let_go() -> None:
    # The same, with the review pay requires proposed again and open: pay can't start while the
    # close is held, whatever its requirements, so the approval is let go then too, and a person's
    # close later has nothing silent to clear (the note, decision 3).
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),
        ("pay.approval#1", "approve", "sam"),
        propose("review", "ana"),  # review#2 opens: pay's requirement is on its way
        ("audit", "done", "ana"),
    ]
    definition = held_by_a_rule()
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert f"pay not started: {HELD}" in run.history[run.history.index("reached audited") :]
    assert "pay" not in run.state.given


# --- Slice 2: a rejected rescue goes back to failed ---


def refund_retried(audited: bool = False) -> dict[str, Any]:
    """The refund with a review that may be proposed again, and a close reason; `audited`: once
    reviewed, an `audit` task reaches the case's only `closes_when` milestone."""
    definition = copy.deepcopy(REFUND)
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    definition["close_reasons"] = {"duplicate": DUPLICATE}
    if audited:
        definition["milestones"] = {"audited": {"display": {"title": "Audited"}}}
        definition["steps"]["audit"] = {
            "kind": "task",
            "display": {"title": "Audit the case"},
            "roles": ["support"],
            "requires": ["review"],
            "outcomes": {"done": {"display": {"title": "Audited"}, "reaches": ["audited"]}},
        }
        definition["closes_when"] = ["audited"]
    return definition


def down_once(keys: list[str]) -> Activity:
    """A refund that fails on its first call, then pays; each call's key goes into `keys`."""

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        if len(keys) == 1:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-1"}

    return refund


# pay#1 fails paying 80, which needs no approval; the review is answered again for 250, and an
# operator retries pay#1, which now asks for one.
RESCUED = [
    ("review", "approve", "ana", {"approved_amount": 80}),
    propose("review", "ana"),
    ("review#2", "approve", "ana", {"approved_amount": 250}),
    retry("pay#1", "omar"),
]
REJECTED = [*RESCUED, ("pay.approval#1", "reject", "sam")]


def test_a_rejected_retry_needs_attention_again() -> None:
    # The bug's reproduction. The rescue's approval is rejected: the failure isn't resolved, since
    # pay#1 may or may not have moved money, so it needs attention again, and there is no new run
    # of pay (brief, D17, D26) (the note, decision 1).
    run = run_case(
        refund_retried(), FILE, REJECTED, PEOPLE, activities={"payments.refund@2": down_once([])}
    )
    assert (
        run.history[-1]
        == "pay#1 won't run: sam rejected pay.approval#1, so it needs attention again"
    )
    assert run.needs_attention == [
        (
            "pay#1: sam rejected pay.approval#1, the approval of its retry: retry it to ask "
            "again, or close the case"
        )
    ]
    assert [(r.entry, r.status) for r in run.state.runs if r.step == "pay"] == [("pay#1", "failed")]
    assert run.status == "open"


def test_a_rejected_retry_retried_again_asks_again() -> None:
    # An operator retries pay#1 again: it is checked again, asks a new approval, and once given,
    # runs as the same run, with the first run's key, so the refund is never made twice
    # (brief, D17, D26).
    keys: list[str] = []
    again = [*REJECTED, retry("pay#1", "omar"), ("pay.approval#2", "approve", "sam")]
    run = run_case(
        refund_retried(), FILE, again, PEOPLE, activities={"payments.refund@2": down_once(keys)}
    )
    assert "asked pay.approval#2: approval of pay by support-lead" in run.history
    assert keys == ["memory/pay#1", "memory/pay#1"]  # the failed call, then the retry's
    assert [(r.entry, r.status) for r in run.state.runs if r.step == "pay"] == [("pay#1", "done")]
    assert run.needs_attention == []
    assert run.closed


def test_a_rejected_retry_holds_the_close_and_says_so() -> None:
    # The audit reaches the case's only closes_when milestone while pay#1 has failed: the close
    # is held. The rescue's approval is rejected: pay#1 needs attention again, and still holds
    # the close, which a proposal refused meanwhile names; retried to completion, the case closes
    # (brief, D26, D34).
    definition = refund_retried(audited=True)
    held = [*RESCUED[:3], ("audit", "done", "ana"), RESCUED[3], ("pay.approval#1", "reject", "sam")]

    # Each run with its own refund, down on its first call.
    def played(script: list[Any]) -> CaseRun:
        return run_case(
            definition, FILE, script, PEOPLE, activities={"payments.refund@2": down_once([])}
        )

    run = played(held)
    assert (
        "pay#1 won't run: sam rejected pay.approval#1, so it needs attention again" in run.history
    )
    assert run.needs_attention[0].startswith("pay#1: sam rejected pay.approval#1")
    assert run.status == "open"
    # pytest: `raises` fails the test unless the block raises ProposalRefused; `why.value` is it.
    with pytest.raises(ProposalRefused) as why:
        played([*held, propose("review", "ana")])
    assert "the case closes once pay#1 is retried, or a person closes it" in str(why.value)
    run = played([*held, retry("pay#1", "omar"), ("pay.approval#2", "approve", "sam")])
    assert run.history[-1] == "closed: audited reached"


def test_a_rejected_retry_can_be_closed() -> None:
    # Or a person closes the case with a declared reason; the failed run is cancelled, saying why
    # (brief, D10, D26).
    closed = [*REJECTED, close("duplicate", "omar")]
    run = run_case(
        refund_retried(), FILE, closed, PEOPLE, activities={"payments.refund@2": down_once([])}
    )
    assert "cancelled pay#1: closed as duplicate by omar" in run.history
    assert run.history[-1] == "closed: duplicate, by omar"


def test_a_rejected_retry_keeps_who_may_not_approve_it() -> None:
    # Lee proposes pay, which fails before it starts: its approval's condition reads a limit
    # nobody has set. Its run keeps no exclusions of its own, so the proposal is what refuses Lee.
    # A rejected rescue is the same run, so Lee still can't approve the next retry's approval
    # (brief, D25, D26).
    definition = refund_retried()
    definition["fields"]["limit"] = {"type": "number", "display": {"title": "Limit"}}
    definition["steps"]["set_limit"] = {
        "kind": "task",
        "display": {"title": "Set the limit"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"set": {"display": {"title": "Set"}, "sets": ["limit"]}},
    }
    pay = definition["steps"]["pay"]
    pay |= {"automatic": False, "proposed_by": ["support"]}
    pay["approval"]["when"] = {">": [{"var": "approved_amount"}, {"var": "limit"}]}
    definition["stays_open"] = True  # nothing else keeps it open while pay waits to be proposed
    people = {**PEOPLE, "lee": ["support", "support-lead"]}
    script = [
        ("review", "approve", "ana", {"approved_amount": 250}),
        propose("pay", "lee"),  # limit unset: pay#1 fails before it starts
        propose("set_limit", "ana"),
        ("set_limit", "set", "ana", {"limit": 100}),
        retry("pay#1", "omar"),  # asks pay.approval#1
        ("pay.approval#1", "reject", "sam"),
        retry("pay#1", "omar"),  # asks pay.approval#2
        ("pay.approval#2", "approve", "lee"),
    ]
    with pytest.raises(AnswerRefused, match="lee proposed pay, so cannot approve it"):
        run_case(definition, FILE, script, people, activities={"payments.refund@2": down_once([])})


def test_an_ordinary_rejection_is_not_a_rescue() -> None:
    # A rejection of a step that isn't being retried is an outcome, as before: a new run of the
    # step is recorded rejected, and nothing needs attention (brief, D23).
    definition = refund_retried()
    definition["steps"]["pay"] |= {"proposed_by": ["support"], "repeatable": True}
    definition["stays_open"] = True
    script = [
        ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 pays, unapproved
        propose("review", "ana"),
        ("review#2", "approve", "ana", {"approved_amount": 250}),
        propose("pay", "ana"),  # pay#2 asks its approval
        ("pay.approval#1", "reject", "sam"),
    ]
    run = run_case(definition, FILE, script, PEOPLE)
    assert run.history[-1] == "pay#2 won't run: sam rejected pay.approval#1"
    assert [(r.entry, r.status) for r in run.state.runs if r.step == "pay"] == [
        ("pay#1", "done"),
        ("pay#2", "rejected"),
    ]
    assert run.needs_attention == []


def test_nothing_new_starts_beside_a_rejected_rescue() -> None:
    # Before the fix, the rejection was a new run, pay#2, so a repeatable pay could be proposed
    # again and run under a new key while nobody knew what pay#1 did. Now pay#1 is its latest run,
    # failed, and nothing starts beside a failed run (brief, D26, D39).
    definition = refund_retried()
    definition["steps"]["pay"] |= {"proposed_by": ["support"], "repeatable": True}
    script = [*REJECTED, propose("pay", "ana")]
    with pytest.raises(
        ProposalRefused, match="^pay#1 needs attention: retry it, or close the case$"
    ):
        run_case(definition, FILE, script, PEOPLE, activities={"payments.refund@2": down_once([])})


# --- Slice 3: a retry waits only for what can still let it start ---


def test_a_retry_whose_condition_turns_false_needs_attention() -> None:
    # Path C. While pay#1's retry waits for its approval, the review is proposed again, which
    # withdraws the approval, and the new review is rejected: pay's condition is false now, so
    # nothing can let the retry start. It goes back to failed, naming the condition as the
    # engine writes it from the definition, never a value (the note, decision 2) (brief, D17, D26).
    script = [*RESCUED, propose("review", "ana"), ("review#3", "reject", "ana")]
    run = run_case(
        refund_retried(), FILE, script, PEOPLE, activities={"payments.refund@2": down_once([])}
    )
    assert "withdrew pay.approval#1: review started again" in run.history
    assert run.history[-1] == (
        'pay#1 failed again: its retry can\'t start: review.outcome = "approve" is false now'
    )
    assert run.needs_attention == [
        (
            'pay#1: its retry can\'t start: review.outcome = "approve" is false now: retry it once '
            "it holds, or close the case"
        )
    ]


def looked_up(*answers: str) -> Activity:
    """An order lookup that gives each status in turn; `down` for a call that fails."""
    given = iter(answers)

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        status = next(given)
        if status == "down":
            raise ConnectionError("orders system down")
        return {"status": status}

    return lookup


def test_a_retry_whose_refreshed_fact_turns_it_false_needs_attention() -> None:
    # Path F. pay#1 fails; two days on, an operator retries it, its order status is fetched again
    # and says the order was cancelled: pay's condition is false now, so the retry fails again,
    # naming the condition, never the value the lookup gave (the note, decision 2).
    activities = {
        "orders.lookup@2": looked_up("delivered", "cancelled"),
        "payments.refund@2": down_once([]),
    }
    script = [
        ("review", "approve", "ana", {"approved_amount": 80}),
        later("2d"),
        retry("pay#1", "omar"),
    ]
    definition = generated_definition(fresh=True, audited=False)
    run = run_case(definition, FILE, script, PEOPLE, activities=activities)
    condition = 'review.outcome = "approve" and check_order.status = "delivered"'
    assert run.history[-2:] == [
        "check_order#2 done, giving status from system:orders",
        f"pay#1 failed again: its retry can't start: {condition} is false now",
    ]
    assert run.needs_attention == [
        (
            f"pay#1: its retry can't start: {condition} is false now: retry it once it holds, or "
            "close the case"
        )
    ]
    assert "cancelled" not in run.needs_attention[0]  # what the case file holds is never quoted


@pytest.mark.parametrize("requires", [["check_order", "review"], ["review", "check_order"]])
def test_a_retry_whose_requirement_was_stopped_needs_attention(requires: list[str]) -> None:
    # Path E'. While pay#1's retry waits for its approval, the review is proposed again, so the
    # retry waits for it; then a rule stops that review. Nothing is on its way to meet pay's
    # requirement now, so the retry fails again, naming the one that ended, wherever it is
    # listed beside one that is met (the note, decision 2).
    definition = generated_definition(fresh=True, audited=False)  # `hold` stops the review
    definition["steps"]["pay"]["requires"] = requires
    script = [
        *RESCUED,
        propose("review", "ana"),  # withdraws pay.approval#1; the retry waits for review#3
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # halt stops review#3
    ]
    activities = {**DELIVERED, "payments.refund@2": down_once([])}
    run = run_case(definition, FILE, script, PEOPLE, activities=activities)
    assert "cancelled review#3: stopped by halt#1" in run.history
    assert run.history[-1] == (
        "pay#1 failed again: its retry can't start: pay requires review, which hasn't completed"
    )
    assert run.needs_attention == [
        (
            "pay#1: its retry can't start: pay requires review, which hasn't completed: retry it "
            "once it has, or close the case"
        )
    ]


def test_a_retry_waits_for_a_requirement_on_its_way() -> None:
    # Paths C' and I: a step pay requires is on its way, and the case shows it, so the retry
    # waits, and runs once it completes, as the same run with its key (the note, decision 2).
    # C': the review proposed again, open in waiting_for.
    keys: list[str] = []
    waiting = [*RESCUED, propose("review", "ana")]
    activities = {"payments.refund@2": down_once(keys)}
    run = run_case(refund_retried(), FILE, waiting, PEOPLE, activities=activities)
    assert [(r.entry, r.status) for r in run.state.runs if r.step == "pay"] == [
        ("pay#1", "retrying")
    ]
    assert run.waiting_for == ["review by support"]
    assert run.needs_attention == []
    keys.clear()
    paid = [
        *waiting,
        ("review#3", "approve", "ana", {"approved_amount": 250}),
        ("pay.approval#2", "approve", "sam"),
    ]
    run = run_case(refund_retried(), FILE, paid, PEOPLE, activities=activities)
    assert keys == ["memory/pay#1", "memory/pay#1"]
    assert run.reached("pay")
    # I: the retry's refresh fails, and needs attention itself; retried, it lands, and pay runs.
    definition = generated_definition(fresh=True, audited=False)
    looked = [
        ("review", "approve", "ana", {"approved_amount": 80}),
        later("2d"),
        retry("pay#1", "omar"),
    ]
    run = run_case(
        definition,
        FILE,
        looked,
        PEOPLE,
        activities={
            "orders.lookup@2": looked_up("delivered", "down"),
            "payments.refund@2": down_once([]),
        },
    )
    assert run.needs_attention == [
        "check_order#2: orders.lookup@2 failed with ConnectionError: ‹sensitive›"
    ]
    keys.clear()
    run = run_case(
        definition,
        FILE,
        [*looked, retry("check_order#2", "omar")],
        PEOPLE,
        activities={
            "orders.lookup@2": looked_up("delivered", "down", "delivered"),
            "payments.refund@2": down_once(keys),
        },
    )
    assert keys == ["memory/pay#1", "memory/pay#1"]
    assert run.closed


def verified(fresh: bool = False) -> dict[str, Any]:
    """The refund with `hold`, and a `verify` lookup pay also requires, which needs a team
    lead's approval and may be proposed again: a requirement that can be rejected, or running.
    `fresh`: pay also requires the order looked up, at most a day old."""
    definition = generated_definition(fresh=fresh, audited=False)
    definition["steps"]["verify"] = {
        "kind": "activity",
        "display": {"title": "Verify the order"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
        "repeatable": True,
        "proposed_by": ["support"],
        "approval": {"roles": ["support-lead"], "display": {"reason": "A lead verifies"}},
    }
    pay = definition["steps"]["pay"]
    pay["requires"] = [*pay.get("requires", []), "verify"]  # and review, by the sequence
    return definition


def test_a_retry_reads_each_requirement_it_waits_for() -> None:
    # The retry waits while each requirement not met is on its way, and fails again, naming it,
    # once one ended without completing (the note, decision 2). verify runs held, so it can be
    # running while the retry waits.
    proposed_again = [
        ("verify.approval#1", "approve", "sam"),
        finish("verify#1"),
        *RESCUED,  # asks pay.approval#1
        # Asks verify.approval#2; pay.approval#1 stays open until verify#2 is rejected or runs.
        propose("verify", "ana"),
    ]

    def played(script: list[Any], keys: list[str]) -> CaseRun:
        activities = {**DELIVERED, "payments.refund@2": down_once(keys)}
        return run_case(verified(), FILE, script, PEOPLE, activities=activities, held=["verify"])

    # Rejected: verify#2 won't run, so nothing is on its way to meet the requirement.
    run = played([*proposed_again, ("verify.approval#2", "reject", "sam")], [])
    assert run.needs_attention == [
        (
            "pay#1: its retry can't start: pay requires verify, which hasn't completed: retry it "
            "once it has, or close the case"
        )
    ]
    # Running: the retry waits, and runs once verify#2 lands, as the same run, with its key.
    running = [*proposed_again, ("verify.approval#2", "approve", "sam")]
    run = played(running, [])
    assert [(r.entry, r.status) for r in run.state.runs if r.step in ("pay", "verify")] == [
        ("verify#1", "done"),
        ("pay#1", "retrying"),
        ("verify#2", "running"),
    ]
    assert run.needs_attention == []
    keys: list[str] = []
    run = played([*running, finish("verify#2"), ("pay.approval#2", "approve", "sam")], keys)
    assert keys == ["memory/pay#1", "memory/pay#1"]
    assert run.closed
    # Two not met: verify#2 is running, and a rule stops the review proposed again. The retry
    # fails, naming the review, the one with nothing on its way.
    stopped = [
        *running,
        propose("review", "ana"),
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),
    ]
    run = played(stopped, [])
    assert run.needs_attention == [
        (
            "pay#1: its retry can't start: pay requires review, which hasn't completed: retry it "
            "once it has, or close the case"
        )
    ]


def test_a_retry_s_given_approval_lapses_with_its_requirement() -> None:
    # Path L, on a retry. pay#1's retry is approved while its fact is fetched again; the review
    # is proposed again, and a rule stops it. The approval lapses, and the retry fails again;
    # once the review completes again, nothing runs under a new key, and the operator's next
    # retry asks a new approval (the note, decisions 2 and 5) (brief, D26).
    keys: list[str] = []
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 fails, unapproved
        propose("review", "ana"),
        ("review#2", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        retry("pay#1", "omar"),  # its status is stale: check_order#2, held
        finish("check_order#2"),  # fresh: pay#1 asks pay.approval#1
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given; stale again: check_order#3, held
        propose("review", "ana"),  # review#3 opens while the refresh runs
        finish("check_order#3"),  # pay#1 waits for review#3
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # halt stops review#3
        propose("review", "ana"),
        ("review#4", "approve", "ana", {"approved_amount": 250}),
    ]
    run = run_case(
        generated_definition(fresh=True, audited=False),
        FILE,
        script,
        PEOPLE,
        activities={**DELIVERED, "payments.refund@2": down_once(keys)},
        held=["check_order"],
    )
    lapse = "lapsed pay.approval#1: pay requires review, which hasn't completed"
    failed = (
        "pay#1 failed again: its retry can't start: pay requires review, which hasn't completed"
    )
    assert run.history.index(lapse) < run.history.index(failed)
    assert [r.entry for r in run.state.runs if r.step == "pay"] == ["pay#1"]
    assert keys == ["memory/pay#1"]
    # An operator retries pay#1 again: it asks a new approval, never spends the lapsed one.
    run = run_case(
        generated_definition(fresh=True, audited=False),
        FILE,
        [*script, retry("pay#1", "omar")],
        PEOPLE,
        activities={**DELIVERED, "payments.refund@2": down_once([])},
        held=["check_order"],
    )
    assert run.waiting_for == ["approval of pay by support-lead"]


def test_a_retry_whose_condition_reads_a_stale_fact_fetches_it_again() -> None:
    # After F, two days pass: the status pay's condition read is stale. The operator's retry
    # isn't refused on it, since a stale fact is fetched again, never trusted (brief, D18, D33);
    # admission fetches it, then starts pay#1, with its key, or fails it again, saying so
    # (the note, decision 2).
    definition = generated_definition(fresh=True, audited=False)
    after_f = [
        ("review", "approve", "ana", {"approved_amount": 80}),
        later("2d"),
        retry("pay#1", "omar"),  # check_order#2 says cancelled: pay#1 fails again
        later("2d"),
        retry("pay#1", "omar"),  # the status is two days old: fetched again
    ]
    keys: list[str] = []
    activities = {
        "orders.lookup@2": looked_up("delivered", "cancelled", "delivered"),
        "payments.refund@2": down_once(keys),
    }
    refetched = "refreshing check_order.status for pay: obtained 2 days ago, at most 1 day"
    run = run_case(definition, FILE, after_f, PEOPLE, activities=activities)
    assert run.history.count(refetched) == 2  # F's refresh, then the retry's
    assert keys == ["memory/pay#1", "memory/pay#1"]
    assert run.closed
    activities = {
        "orders.lookup@2": looked_up("delivered", "cancelled", "cancelled"),
        "payments.refund@2": down_once([]),
    }
    run = run_case(definition, FILE, after_f, PEOPLE, activities=activities)
    assert run.history.count(refetched) == 2
    assert run.history[-1] == (
        'pay#1 failed again: its retry can\'t start: review.outcome = "approve" and '
        'check_order.status = "delivered" is false now'
    )
    # The same retry while the status is still fresh is refused: it isn't stale, so it is read.
    fresh = [*after_f[:3], retry("pay#1", "omar")]
    activities = {
        "orders.lookup@2": looked_up("delivered", "cancelled"),
        "payments.refund@2": down_once([]),
    }
    with pytest.raises(RetryRefused, match="^pay#1 can't be retried: .* is false now$"):
        run_case(definition, FILE, fresh, PEOPLE, activities=activities)


def test_a_retry_isnt_taken_for_a_stale_fact_its_condition_doesnt_read() -> None:
    # Only a stale fact the condition reads lets a false condition's retry through: here pay
    # needs the order's status fresh for its approval, its condition reads only the review, and
    # the review was rejected. The retry is read, and refused (the note, decision 2).
    definition = generated_definition(fresh=True, audited=False)
    pay = definition["steps"]["pay"]
    pay["when"] = {"==": [{"var": "review.outcome"}, "approve"]}
    pay["approval"]["when"] = {"==": [{"var": "check_order.status"}, "delivered"]}
    script = [
        ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 asks pay.approval#1
        ("pay.approval#1", "approve", "sam"),  # pay#1 fails
        propose("review", "ana"),
        ("review#2", "reject", "ana"),
        later("2d"),  # the status is stale now
        retry("pay#1", "omar"),
    ]
    activities = {**DELIVERED, "payments.refund@2": down_once([])}
    refused = '^pay#1 can\'t be retried: review.outcome = "approve" is false now$'
    with pytest.raises(RetryRefused, match=refused):
        run_case(definition, FILE, script, PEOPLE, activities=activities)


def restarting(moment: str) -> dict[str, Any]:
    """The refund with the order looked up and `hold`, whose answer makes `halt` stop the review,
    and a rule `again` that starts the review again in the same decision: on the hold's answer
    too (`answered`), or once a follow-up task the hold leads to starts (`started`)."""
    definition = generated_definition(fresh=True, audited=False)
    on: dict[str, str] = {"answered": "hold"}
    if moment == "started":
        definition["steps"]["follow_up"] = {
            "kind": "task",
            "display": {"title": "Follow the hold up"},
            "roles": ["support"],
            "requires": ["hold"],
            "outcomes": {"done": {"display": {"title": "Done"}}},
        }
        on = {"started": "follow_up"}
    definition["rules"]["again"] = {
        "display": {"title": "Review it again"},
        "on": on,
        "then": {"start": ["review"]},
    }
    return definition


@pytest.mark.parametrize("moment", ["answered", "started"])
def test_a_requirement_a_rule_starts_again_keeps_what_waits_for_it(moment: str) -> None:
    # One rule stops the review, and another starts it again in the same decision: by the
    # decision's end the review is on its way, so what waits for it is kept, read once admission
    # has settled. A given approval stays, and is spent on the review answered with the values it
    # saw; a retried run keeps waiting, and runs with its key (the note, decisions 2 and 5).
    given = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given; the status is fetched again, held
        propose("review", "ana"),
        finish("check_order#2"),
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # halt stops the review; again starts it
        ("review", "approve", "ana", {"approved_amount": 250}),
    ]
    keys: list[str] = []
    activities = {**DELIVERED, "payments.refund@2": down_once(keys)}
    definition = restarting(moment)
    run = run_case(definition, FILE, given, PEOPLE, activities=activities, held=["check_order"])
    assert not any(line.startswith("lapsed pay.approval#1") for line in run.history)
    assert "asked pay.approval#2: approval of pay by support-lead" not in run.history
    assert keys == ["memory/pay#1"]  # pay#1 is paid on the approval Sam gave
    retried = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 fails, unapproved
        propose("review", "ana"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        retry("pay#1", "omar"),  # asks pay.approval#1
        propose("review", "ana"),  # withdraws it: the retry waits for the review
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # halt stops the review; again starts it
        ("review", "approve", "ana", {"approved_amount": 250}),
        ("pay.approval#2", "approve", "sam"),
    ]
    keys.clear()
    run = run_case(definition, FILE, retried, PEOPLE, activities=activities, held=["check_order"])
    assert not any(line.startswith("pay#1 failed again") for line in run.history)
    assert keys == ["memory/pay#1", "memory/pay#1"]


def paid(keys: list[str]) -> Activity:
    """A refund that pays at once; each call's key goes into `keys`."""

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        return {"refund_id": "refund-1"}

    return refund


def test_a_given_approval_lapses_with_a_rejected_requirement() -> None:
    # Path L, with a requirement rejected: verify, proposed again while pay's approval waits for
    # its fact, is rejected, so nothing is on its way to meet it; the approval lapses then, and
    # the case closes once the fact lands (the note, decision 5).
    script = [
        ("verify.approval#1", "approve", "sam"),
        finish("verify#1"),
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),  # pay asks its approval
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given: the order's status is fetched again
        propose("verify", "ana"),  # asks verify.approval#2
        ("verify.approval#2", "reject", "sam"),  # verify#2 won't run
        finish("check_order#2"),
    ]
    held = ["check_order", "verify"]
    run = run_case(verified(fresh=True), FILE, script, PEOPLE, activities=DELIVERED, held=held)
    assert run.history[-3:] == [
        "lapsed pay.approval#1: pay requires verify, which hasn't completed",
        "check_order#2 done, giving status from system:orders",
        "closed: nothing left to do",
    ]


def test_a_given_approval_waits_for_a_requirement_on_its_way() -> None:
    # A given approval stays while what its step requires is on its way: a refresh that failed
    # and is retried, or a requirement running. It is spent on the first run's key, and nothing
    # asks again (the note, decision 5) (brief, D11).
    keys: list[str] = []
    refresh_fails = [
        ("review", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given; check_order#2 fails, for an operator
        retry("check_order#2", "omar"),  # lands: pay starts on the approval
    ]
    activities = {
        "orders.lookup@2": looked_up("delivered", "down", "delivered"),
        "payments.refund@2": paid(keys),
    }
    definition = generated_definition(fresh=True, audited=False)
    run = run_case(definition, FILE, refresh_fails, PEOPLE, activities=activities)
    assert keys == ["memory/pay#1"]
    assert "asked pay.approval#2: approval of pay by support-lead" not in run.history
    keys.clear()
    running = [
        ("verify.approval#1", "approve", "sam"),
        finish("verify#1"),
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given; check_order#2 fetches the status, held
        propose("verify", "ana"),
        ("verify.approval#2", "approve", "sam"),  # verify#2 runs, held
        finish("check_order#2"),  # pay waits for verify#2, running
        finish("verify#2"),  # pay starts on the approval
    ]
    activities = {**DELIVERED, "payments.refund@2": paid(keys)}
    held = ["check_order", "verify"]
    run = run_case(verified(fresh=True), FILE, running, PEOPLE, activities=activities, held=held)
    assert keys == ["memory/pay#1"]
    assert "asked pay.approval#2: approval of pay by support-lead" not in run.history


def test_a_proposed_step_whose_approval_lapsed_asks_again_once_proposed_again() -> None:
    # A step a person proposed whose approval lapsed starts nothing by itself once its
    # requirement completes again, as after a withdrawn approval (brief, D25): a person proposes
    # it again, and it asks a new approval (the note, decision 5).
    definition = generated_definition(fresh=True, audited=False)
    definition["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support"]}
    definition["stays_open"] = True
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        propose("pay", "ana"),  # asks pay.approval#1
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given; the status is fetched again, held
        propose("review", "ana"),
        finish("check_order#2"),
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # halt stops review#2: the approval lapses
        propose("review", "ana"),
        ("review#3", "approve", "ana", {"approved_amount": 250}),
    ]
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert "lapsed pay.approval#1: pay requires review, which hasn't completed" in run.history
    assert run.waiting_for == []
    again = [*script, propose("pay", "ana")]
    run = run_case(definition, FILE, again, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert run.waiting_for == ["approval of pay by support-lead"]


# --- Slice 6: the guide, as the engine does it ---

CASES_GUIDE = (ROOT / "docs" / "guides" / "cases.md").read_text()


def in_the_guide(line: str) -> bool:
    """Whether the guide quotes `line`, read across the guide's own line breaks."""
    return line in " ".join(CASES_GUIDE.split())


def test_the_guides_retry_lines_are_what_the_engine_says() -> None:
    # Each line the guide quotes for a retry that can't start, and for an approval a held close
    # lets go, played: the guide can't drift from the engine.
    rejected = run_case(
        refund_retried(), FILE, REJECTED, PEOPLE, activities={"payments.refund@2": down_once([])}
    )
    turned_false = [*RESCUED, propose("review", "ana"), ("review#3", "reject", "ana")]
    false_now = run_case(
        refund_retried(),
        FILE,
        turned_false,
        PEOPLE,
        activities={"payments.refund@2": down_once([])},
    )
    stopped = [
        *RESCUED,
        propose("review", "ana"),
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),
    ]
    ended = run_case(
        generated_definition(fresh=False, audited=False),
        FILE,
        stopped,
        PEOPLE,
        activities={"payments.refund@2": down_once([])},
    )
    unfetchable = refund_retried()
    unfetchable["steps"]["pay"]["max_age"] = {"review.outcome": "1d"}
    aged: list[Any] = [*turned_false[:1], propose("review", "ana"), ("review#2", "reject", "ana")]
    aged += [later("2d"), retry("pay#1", "omar")]
    stale = run_case(
        unfetchable, FILE, aged, PEOPLE, activities={"payments.refund@2": down_once([])}
    )
    with pytest.raises(RetryRefused) as superseded_retry:
        roles = frozenset(PEOPLE["omar"])
        retried = Retried("check_order#2", "omar", roles, at=START)
        decide(parse_case(rechecked()), CATALOG, superseded().state, retried)
    for line in [
        rejected.history[-1],
        rejected.needs_attention[0],
        false_now.history[-1],
        ended.history[-1],
        stale.history[-1],
        str(superseded_retry.value),
    ]:
        assert in_the_guide(line), line
    # And the line for an approval a held close lets go, which the guide shortens.
    definition, fakes = goodwill_while_held()
    answers = [SMALL_REVIEW, ("goodwill", "approve", "sam")]
    let_go = run_case(definition, SMALL, answers, OPERATORS, activities=fakes)
    quoted = "goodwill not started: paid is reached, "
    assert let_go.history[-1].startswith(quoted), let_go.history[-1]
    assert in_the_guide(f"`{quoted}…`")


# --- The final review: what the branch promised and no test showed ---


def test_a_run_status_the_check_doesnt_know_fails_it() -> None:
    # The invariant fails closed: a status its `match` doesn't name is an error, never "shown".
    definition = refund_retried()
    run = run_case(definition, FILE, [], PEOPLE)
    run.state.runs[0].status = "paused"  # type: ignore[assignment]
    with pytest.raises(AssertionError) as raised:
        unshown(parse_case(definition), run.state)
    assert not isinstance(raised.value, Silent)  # a run it can't read, not a silent one


def test_a_retry_waits_for_a_requirement_itself_retried() -> None:
    # pay#1's retry waits for verify; verify#2 fails, and once its fact is stale an operator
    # retries it, so it waits for the order's status fetched again. A requirement retried is on
    # its way: pay#1 keeps waiting, and runs once verify#2 lands (the note, decision 2).
    definition = verified(fresh=True)
    definition["steps"]["verify"] |= {
        "requires": ["check_order"],
        "when": {"==": [{"var": "check_order.status"}, "delivered"]},
        "max_age": {"check_order.status": "1d"},
    }
    script = [
        finish("check_order#1"),
        ("verify.approval#1", "approve", "sam"),
        finish("verify#1"),
        *RESCUED,  # retried, pay#1 asks pay.approval#1
        propose("verify", "ana"),
        ("verify.approval#2", "approve", "sam"),  # verify#2 runs, held
        finish("verify#2"),  # the lookup is down: verify#2 fails, for an operator
        later("2d"),
        retry("verify#2", "omar"),  # its status is stale: check_order#2 fetches it, held
    ]
    held = ["check_order", "verify"]

    def played(more: list[Any], keys: list[str]) -> CaseRun:
        activities = {
            "orders.lookup@2": looked_up(
                "delivered", "delivered", "down", "delivered", "delivered"
            ),
            "payments.refund@2": down_once(keys),
        }
        return run_case(
            definition, FILE, [*script, *more], PEOPLE, activities=activities, held=held
        )

    run = played([], [])
    assert [(r.entry, r.status) for r in run.state.runs if r.step in ("pay", "verify")] == [
        ("verify#1", "done"),
        ("pay#1", "retrying"),
        ("verify#2", "retrying"),
    ]
    assert run.needs_attention == []
    keys: list[str] = []
    run = played(
        [finish("check_order#2"), finish("verify#2"), ("pay.approval#2", "approve", "sam")], keys
    )
    assert keys == ["memory/pay#1", "memory/pay#1"]
    assert run.closed


def test_a_step_with_an_earlier_run_starts_nothing_while_the_close_is_held() -> None:
    # pay#1 paid; pay, repeatable, is proposed again and asks its approval; then the close is
    # held. The approval given now is let go: pay#1 isn't being retried, so nothing new starts
    # (the note, decision 3).
    definition = held_by_a_rule()
    definition["steps"]["pay"] |= {"proposed_by": ["support"], "repeatable": True}
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 pays, unapproved
        propose("review", "ana"),
        ("review#2", "approve", "ana", {"approved_amount": 250}),
        propose("pay", "ana"),  # asks pay.approval#1
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # broken#1 fails
        ("audit", "done", "ana"),  # the close is held by broken#1
        ("pay.approval#1", "approve", "sam"),
    ]
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert run.history[-1] == f"pay not started: {HELD}"
    assert not any(line.startswith("scheduled pay#2") for line in run.history)


def test_a_run_nobody_retried_isnt_failed_by_its_condition() -> None:
    # pay#1 paid; pay, repeatable, is proposed again and waits for its fact, which says the
    # order was cancelled: the proposal is dropped, and pay#1, which nobody retried, stays done
    # (the note, decision 2: only a retried run fails again).
    definition = held_by_a_rule()
    definition["steps"]["pay"] |= {"proposed_by": ["support"], "repeatable": True}
    definition["stays_open"] = True
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 pays, unapproved
        later("2d"),
        propose("pay", "ana"),  # waits for the status, fetched again: check_order#2, held
        finish("check_order#2"),  # cancelled: pay's condition is false now
    ]
    activities = {"orders.lookup@2": looked_up("delivered", "cancelled")}
    run = run_case(definition, FILE, script, PEOPLE, activities=activities, held=["check_order"])
    assert [(r.entry, r.status) for r in run.state.runs if r.step == "pay"] == [("pay#1", "done")]
    assert run.needs_attention == []


def test_a_close_due_mid_decision_lets_an_approval_go_saying_the_case_closes() -> None:
    # A rule reaches the case's only closes_when milestone while pay's approval waits for its
    # fact, and nothing holds the close: the approval is let go, saying the case closes, in that
    # decision (the note, decision 3).
    definition = generated_definition(fresh=True, audited=False)
    definition["milestones"] = {"audited": {"display": {"title": "Audited"}}}
    definition["closes_when"] = ["audited"]
    definition["rules"]["audit_on_hold"] = {
        "display": {"title": "Audited once held"},
        "on": {"answered": "hold"},
        "then": {"reach": ["audited"]},
    }
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given; the status is fetched again, held
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # audit_on_hold reaches audited
    ]
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert (
        "pay not started: audited is reached, so the case closes and nothing new starts"
        in run.history
    )


def test_a_step_a_rule_started_asks_again_once_its_rule_fires_again() -> None:
    # pay is started by a rule on a nudge's answer; its approval lapses with its requirement. The
    # review completing again starts nothing by itself; the nudge answered again does, and pay
    # asks a new approval (the note, decision 5) (brief, D25).
    definition = generated_definition(fresh=True, audited=False)
    definition["steps"]["pay"] |= {"automatic": False}
    definition["steps"]["nudge"] = {
        "kind": "task",
        "display": {"title": "Nudge the payment"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "repeatable": True,
        "outcomes": {"go": {"display": {"title": "Go"}}},
    }
    definition["rules"]["go"] = {
        "display": {"title": "Pay once nudged"},
        "on": {"answered": "nudge"},
        "then": {"start": ["pay"]},
    }
    definition["stays_open"] = True
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        propose("nudge", "ana"),
        ("nudge#1", "go", "ana"),  # go starts pay: asks pay.approval#1
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given; the status is fetched again, held
        propose("review", "ana"),
        finish("check_order#2"),
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # halt stops review#2: the approval lapses
        propose("review", "ana"),
        ("review#3", "approve", "ana", {"approved_amount": 250}),
    ]
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert "lapsed pay.approval#1: pay requires review, which hasn't completed" in run.history
    assert run.waiting_for == []
    again = [*script, propose("nudge", "ana"), ("nudge#2", "go", "ana")]
    run = run_case(definition, FILE, again, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert run.waiting_for == ["approval of pay by support-lead"]


def test_a_retry_on_a_stale_fact_nothing_can_fetch_fails_at_once_on_its_age() -> None:
    # The fact pay needs fresh came from a person, so nothing can fetch it again: the retry is
    # taken, and fails at once on the fact's age, as any start does, saying why; nothing is
    # fetched, and nothing paid (the note, decision 2) (brief, D33).
    definition = refund_retried()
    definition["steps"]["pay"]["max_age"] = {"review.outcome": "1d"}
    script = [
        ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 fails
        propose("review", "ana"),
        ("review#2", "reject", "ana"),  # pay's condition is false now
        later("2d"),  # review.outcome is stale
        retry("pay#1", "omar"),
    ]
    keys: list[str] = []
    run = run_case(
        definition, FILE, script, PEOPLE, activities={"payments.refund@2": down_once(keys)}
    )
    assert "omar retried pay#1 as operations" in run.history
    assert run.needs_attention == [
        (
            "pay#1: review.outcome was obtained 2 days ago, and pay needs it at most 1 day old: "
            "it came from a person, so it can't be fetched again"
        )
    ]
    assert not any(line.startswith("refreshing") for line in run.history)
    assert keys == ["memory/pay#1"]


def test_a_refresh_spends_no_proposal() -> None:
    # check_order is proposed by Ana and waits for its own fact; meanwhile pay's need fetches
    # check_order again. A refresh is not the proposed run, so Ana's proposal stays hers: once
    # its fact says the order was cancelled, it is dropped, saying whose it was, never an error
    # out of the decision (fail closed).
    definition = copy.deepcopy(REFUND)
    definition["steps"]["check_customer"] = {
        "kind": "activity",
        "display": {"title": "Check the customer"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    definition["steps"]["check_order"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
        "requires": ["check_customer"],
        "repeatable": True,
        "proposed_by": ["support"],
        "when": {"==": [{"var": "check_customer.status"}, "delivered"]},
        "max_age": {"check_customer.status": "1d"},
    }
    definition["steps"]["pay"] |= {
        "requires": ["review", "check_order"],
        "when": {
            "and": [
                {"==": [{"var": "review.outcome"}, "approve"]},
                {"==": [{"var": "check_order.status"}, "delivered"]},
            ]
        },
        "max_age": {"check_order.status": "1d"},
    }
    script = [
        finish("check_customer#1"),
        finish("check_order#1"),
        later("2d"),
        propose("check_order", "ana"),  # its fact is stale: check_customer#2, held
        ("review#1", "approve", "ana", {"approved_amount": 80}),  # pay: check_order#2, held
        finish("check_order#2"),  # delivered: pay runs
        finish("check_customer#2"),  # cancelled: Ana's proposal no longer holds
    ]
    lookup = looked_up("delivered", "delivered", "delivered", "cancelled")
    run = run_case(
        definition,
        FILE,
        script,
        PEOPLE,
        activities={"orders.lookup@2": lookup},
        held=["check_customer", "check_order"],
    )
    dropped = [line for line in run.history if line.startswith("dropped ana's proposal")]
    assert dropped == [
        'dropped ana\'s proposal of check_order: check_customer.status = "delivered" is false'
    ]


def chained() -> dict[str, Any]:
    """The refund whose pay reads the order's status, fresh, without requiring the lookup that
    gives it, a lookup that itself needs the customer's status fresh."""
    definition = copy.deepcopy(REFUND)
    definition["steps"]["check_customer"] = {
        "kind": "activity",
        "display": {"title": "Check the customer"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    definition["steps"]["check_order"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
        "requires": ["check_customer"],
        "when": {"==": [{"var": "check_customer.status"}, "delivered"]},
        "max_age": {"check_customer.status": "1d"},
    }
    definition["steps"]["pay"] |= {
        "when": {
            "and": [
                {"==": [{"var": "review.outcome"}, "approve"]},
                {"==": [{"var": "check_order.status"}, "delivered"]},
            ]
        },
        "max_age": {"check_order.status": "1d"},
    }
    return definition


def test_a_retry_waiting_for_a_retried_refresh_is_shown_through_it() -> None:
    # pay#1's retry waits for the order's status fetched again, check_order#2, which failed and
    # an operator retried; it waits in turn for the customer's status, fetched again. The
    # runtime counts a retried refresh as on its way, so the invariant does too, and the case
    # goes on by itself once the customer's status lands (the note, "The invariant").
    script = [
        finish("check_customer#1"),  # check_order#1 runs
        ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 fails
        later("2d"),
        retry(
            "pay#1", "omar"
        ),  # check_order#2 fetches the status again: it fails, and so does pay#1
        retry("check_order#2", "omar"),  # its own fact is stale: check_customer#2, held
        retry("pay#1", "omar"),  # waits for check_order#2, retried
    ]
    keys: list[str] = []
    activities = {
        "orders.lookup@2": looked_up("delivered", "delivered", "down", "delivered", "delivered"),
        "payments.refund@2": down_once(keys),
    }
    run = run_case(
        chained(),
        FILE,
        [*script, finish("check_customer#2")],
        PEOPLE,
        activities=activities,
        held=["check_customer"],
    )
    assert keys == ["memory/pay#1", "memory/pay#1"]
    assert run.closed


def test_a_given_approval_is_not_shown_by_a_refresh_it_cant_use() -> None:
    # A given approval whose requirement ended can't be spent, so a refresh of its fact still
    # running doesn't show it: admission reads `requires` before freshness. Read on a state the
    # runtime now never leaves (it lapses the approval), so the invariant can't pass it either.
    definition = generated_definition(fresh=True, audited=False)
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        ("pay.approval#1", "approve", "sam"),  # given; check_order#2 runs, held
        propose("review", "ana"),  # review#2 opens: the approval is shown through it
    ]
    run = run_case(definition, FILE, script, PEOPLE, activities=DELIVERED, held=["check_order"])
    assert unshown(parse_case(definition), run.state) == []
    next(r for r in run.state.runs if r.entry == "review#2").status = "cancelled"
    assert unshown(parse_case(definition), run.state) == [
        "pay.approval#1 is given, and pay waits for no fact or requirement"
    ]


# --- Path N: a retry of a run its step has run again since ---


def rechecked() -> dict[str, Any]:
    """The refund with the order looked up and `hold`, whose answer also makes a rule stop the
    lookup: so a refresh of the order's status can be stopped, and another scheduled beside it."""
    definition = generated_definition(fresh=True, audited=False)
    definition["rules"]["recheck"] = {
        "display": {"title": "Stop the lookup on hold"},
        "on": {"answered": "hold"},
        "then": {"stop": ["check_order"]},
    }
    return definition


# pay#1 fails; two days on, its retry fetches the status again, and a rule stops that refresh,
# so pay#1 fails again; retried once more, it fetches the status with a new refresh, beside the
# stopped one, which then fails. The new one lands, and pay#1 is paid: check_order#2 needs
# attention, though check_order#3 is the step's latest run.
SUPERSEDED = [
    finish("check_order#1"),
    ("review", "approve", "ana", {"approved_amount": 80}),  # pay#1 fails
    later("2d"),
    retry("pay#1", "omar"),  # the status is stale: check_order#2, held
    propose("hold", "ana"),
    ("hold#1", "hold", "ana"),  # recheck stops check_order#2: pay#1 fails again
    retry("pay#1", "omar"),  # a new refresh: check_order#3, held
    finish("check_order#2"),  # the lookup is down: check_order#2 fails
    finish("check_order#3"),  # delivered: pay#1 runs with its key
]


def superseded() -> CaseRun:
    """The case above, played to just before check_order#2 is retried."""
    activities = {
        "orders.lookup@2": looked_up("delivered", "down", "delivered"),
        "payments.refund@2": down_once([]),
    }
    return run_case(
        rechecked(), FILE, SUPERSEDED, PEOPLE, activities=activities, held=["check_order"]
    )


def test_a_retry_of_a_run_its_step_has_run_again_since_is_refused() -> None:
    # Path N. Only a step's latest run runs again, so a retry of an earlier one could never
    # start: it is refused, saying which run is the latest and what to do, and nothing in the
    # case changes (the note, decision 6) (brief, D26).
    run = superseded()
    assert [(r.entry, r.status) for r in run.state.runs if r.step == "check_order"] == [
        ("check_order#1", "done"),
        ("check_order#2", "failed"),
        ("check_order#3", "done"),
    ]
    before = copy.deepcopy(run.state)
    roles = frozenset(PEOPLE["omar"])
    with pytest.raises(RetryRefused) as refused:
        decide(
            parse_case(rechecked()),
            CATALOG,
            run.state,
            Retried("check_order#2", "omar", roles, at=START),
        )
    assert str(refused.value) == (
        "check_order#2 can't be retried: check_order#3 has run since, and only a step's latest "
        "run runs again: close the case"
    )
    assert run.state == before


def generated_held_case(seed: int, refusals: list[str]) -> CaseState:
    """A second family of generated cases, its own seeds: the refund with the order looked up,
    the lookup held until a turn lets it finish, and `recheck`, a rule that stops the lookup
    on the hold's answer, so refreshes can be stopped, fail and be superseded across a person's
    acts. Played under the hook in `conftest.py`, as `generated_case` is; each refusal's text
    goes into `refusals`."""
    chance = random.Random(seed)  # a test's randomness, seeded: the engine reads none
    definition = rechecked()
    definition["stays_open"] = chance.random() < 0.25
    case = parse_case(definition)

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        if chance.random() < 0.5:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-1"}

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        if chance.random() < 0.3:
            raise ConnectionError("orders system down")
        return {"status": "delivered"}

    activities = {**FAKES, "payments.refund@2": refund, "orders.lookup@2": lookup}
    holding = frozenset({"check_order"})
    driver = Driver(case, CATALOG, activities, holding=holding, plans=no_plans, workflows={})
    at = START
    file = {"order_id": "ord-1", "amount": Decimal(300)}
    state = driver.carry(CaseState("held"), Opened(wrapped(case, as_json(file)), None, at=at))
    played = [f"seed {seed}"]
    for _ in range(40):
        if state.phase != "open":
            break
        if chance.random() < 0.1:
            at += 2 * DAY
            played.append("two days later")
            continue
        # Each held lookup may finish now, offered twice: what it gives arrives at this turn.
        finishing: list[Event | str] = [*driver.held, *driver.held]
        choice = chance.choice([*next_events(chance, state, at), *finishing])
        played.append(repr(choice))
        try:
            if isinstance(choice, str):
                ended = outcome_of(driver.held.pop(choice), driver.activity, at)
                state = driver.carry(state, ended)
            else:
                state = driver.carry(state, choice)
        except (AnswerRefused, ProposalRefused, RetryRefused, CloseRefused) as refused:
            played.append(f"  refused: {refused}")
            refusals.append(str(refused))
        except Silent as silent:
            raise Silent("\n".join([str(silent), *played])) from None
    return state


@pytest.mark.parametrize("seed", range(500))
def test_generated_cases_with_held_lookups_show_what_is_pending(seed: int) -> None:
    generated_held_case(seed, [])


def test_the_held_generated_cases_reach_a_retry_of_a_superseded_run() -> None:
    # Path N in the generated cases: some seed retries a run its step has run again since, and
    # is refused, so a change to the generator or the runtime can't drop or reopen it unseen.
    refusals: list[str] = []
    for seed in range(500):
        generated_held_case(seed, refusals)
    superseded = [said for said in refusals if "has run since" in said]
    assert superseded, "no generated case retried a run its step has run again since"


def test_a_retry_failed_while_its_requirements_refresh_runs_is_shown_and_retried() -> None:
    # The known limit (the note, decision 4): pay#1's retry waits on check_order, whose coming
    # run a rule cancels in the decision another step's need schedules a refresh of it. The
    # refresh isn't counted, so pay#1 fails one event early, but shown: it needs attention, and
    # the operator's retry, once the refresh has landed, asks its approval again.
    definition = generated_definition(fresh=True, audited=False)
    steps = definition["steps"]
    steps["ping"] = {
        "kind": "activity",
        "display": {"title": "Ping the order"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    steps["check_order"] |= {
        "repeatable": True,
        "proposed_by": ["support"],
        "requires": ["ping"],
        "when": {"==": [{"var": "ping.status"}, "delivered"]},
        "max_age": {"ping.status": "1d"},
    }
    steps["recheck"] = {
        "kind": "activity",
        "display": {"title": "Recheck on hold"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
        "requires": ["hold"],
        "when": {"==": [{"var": "check_order.status"}, "delivered"]},
        "max_age": {"check_order.status": "1d"},
    }
    definition["rules"]["halt_check"] = {
        "display": {"title": "Stop the lookup on hold"},
        "on": {"answered": "hold"},
        "then": {"stop": ["check_order"]},
    }
    script = [
        finish("ping#1"),
        *RESCUED,  # retried, pay#1 asks pay.approval#1
        later("2d"),
        propose("check_order", "ana"),  # ping.status is stale: ping#2 fetches it, held
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # check_order's coming run cancelled; recheck refreshes it
    ]
    activities = {
        "orders.lookup@2": looked_up(*["delivered"] * 10),
        "payments.refund@2": down_once([]),
    }
    run = run_case(definition, FILE, script, PEOPLE, activities=activities, held=["ping"])
    assert run.needs_attention == [
        (
            "pay#1: its retry can't start: pay requires check_order, which hasn't completed: "
            "retry it once it has, or close the case"
        )
    ]
    assert "check_order#3 done, giving status from system:orders" in run.history
    activities["orders.lookup@2"] = looked_up(*["delivered"] * 10)
    activities["payments.refund@2"] = down_once([])
    again = [*script, retry("pay#1", "omar")]
    run = run_case(definition, FILE, again, PEOPLE, activities=activities, held=["ping"])
    assert run.waiting_for == ["approval of pay by support-lead"]


def test_a_rejected_retry_of_several_approvers_needs_attention() -> None:
    # One rejection of two rejects the retry's approval: the run goes back to failed, as with one
    # approver, and the approval given before goes with the entry, so the next retry's entry
    # counts from nothing, and Kim may approve it again (brief, D26, D47).
    definition = refund_retried()
    definition["fields"]["limit"] = {"type": "number", "display": {"title": "Limit"}}
    definition["steps"]["set_limit"] = {
        "kind": "task",
        "display": {"title": "Set the limit"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"set": {"display": {"title": "Set"}, "sets": ["limit"]}},
    }
    pay = definition["steps"]["pay"]
    pay |= {"automatic": False, "proposed_by": ["support"]}
    pay["approval"] |= {"when": {">": [{"var": "approved_amount"}, {"var": "limit"}]}, "count": 2}
    definition["stays_open"] = True
    people = {**PEOPLE, "lee": ["support", "support-lead"], "kim": ["support-lead"]}
    script = [
        ("review", "approve", "ana", {"approved_amount": 250}),
        propose("pay", "lee"),  # limit unset: pay#1 fails before it starts
        propose("set_limit", "ana"),
        ("set_limit", "set", "ana", {"limit": 100}),
        retry("pay#1", "omar"),  # asks pay.approval#1
        ("pay.approval#1", "approve", "kim"),
        ("pay.approval#1", "reject", "sam"),
    ]
    activities = {"payments.refund@2": down_once([])}
    run = run_case(definition, FILE, script, people, activities=activities)
    assert (
        "pay#1 won't run: sam rejected pay.approval#1, which 1 of 2 had approved, so it needs "
        "attention again"
    ) in run.history
    assert run.needs_attention == [
        "pay#1: sam rejected pay.approval#1, the approval of its retry: retry it to ask again, or "
        "close the case"
    ]
    again = run_case(
        definition,
        FILE,
        [*script, retry("pay#1", "omar"), ("pay.approval#2", "approve", "kim")],
        people,
        activities=activities,
    )
    assert again.waiting_for == ["approval of pay by support-lead: 1 of 2 given"]
