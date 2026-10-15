"""Fresh facts: time on events, when each fact was obtained, and `max_age` (layer 9d).

See docs/layers/09-case-data.md and docs/guides/case-data.md.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.freshness import TimeRefused
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseState, Completed, Obtained, Opened
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.interpreter import Outcome
from ventoux.testing import (
    CATALOG,
    DAY,
    START,
    finish,
    later,
    load_definition,
    retry,
    run_case,
    shown,
)

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


class TrackInput(BaseModel):
    order_id: str
    idempotency_key: str


class TrackOutput(BaseModel):
    status: str


def with_keyed_lookup() -> Any:
    """The development catalog, and a read-only lookup that takes a key, as some systems ask."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register(
        ActivityContract(
            name="orders.track",
            version=1,
            input=TrackInput,
            output=TrackOutput,
            risk="low",
            effect="read",
            timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
            retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
            idempotency_key="idempotency_key",
            outcomes=[],
            display=Display(title="Track an order", description="Reads an order's status."),
        )
    )
    return catalog


def test_a_stale_fact_is_refreshed_before_the_step_runs() -> None:
    # The curriculum's negative test: on day 3 `check_order.status` is 3 days old and `pay` needs
    # it at most a day old, so `pay` doesn't run before `check_order` runs again.
    definition = refund_fresh()
    definition["steps"]["check_order"]["activity"] = "orders.track@1"
    looked_up: list[dict[str, Any]] = []

    def track(inputs: dict[str, Any]) -> dict[str, Any]:
        looked_up.append(inputs)
        return {"status": "delivered"}

    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 80},
        answers=[later("3d"), ("review", "approve", "ana", {"approved_amount": 80})],
        people=PEOPLE,
        activities={"orders.track@1": track},
        catalog=with_keyed_lookup(),
    )
    refreshing = run.history.index(
        "refreshing check_order.status for pay: obtained 3 days ago, at most 1 day"
    )
    assert run.history[refreshing + 1].startswith("scheduled check_order#2: orders.track@1")
    assert (
        run.history.index(
            "scheduled pay#1: payments.refund@2 (order_id from system:opener; "
            "amount from person:ana), key memory/pay#1"
        )
        > refreshing + 1
    )
    # A new run of it, with its own entry and key (brief, D17).
    assert [inputs["idempotency_key"] for inputs in looked_up] == [
        "memory/check_order#1",
        "memory/check_order#2",
    ]
    # Its output replaces the old one, with fresh sources and a fresh time.
    assert run.state.obtained["check_order.status"] == Obtained(START + 3 * DAY, "check_order#2")
    assert run.state.sources["check_order.status"] == frozenset({"untrusted:undeclared"})
    assert run.reached("pay")


def test_a_fresh_fact_refreshes_nothing() -> None:
    run = run_case(
        refund_fresh(),
        file={"order_id": "ord-1", "amount": 80},
        answers=[later("12h"), ("review", "approve", "ana", {"approved_amount": 80})],
        people=PEOPLE,
    )
    assert run.reached("pay")
    assert not any(line.startswith("refreshing") for line in run.history)
    assert [r.entry for r in run.state.runs if r.step == "check_order"] == ["check_order#1"]


def guide_example(heading: str) -> str:
    """The first Python block after `heading` in the guide's "Fresh facts" section."""
    section = GUIDE.split("## Fresh facts")[1].split(heading)[1]
    return section.split("```python\n")[1].split("```")[0]


def test_a_refresh_that_changes_the_condition_stops_the_step() -> None:
    # The guide's example, run as written: the order was returned after the first look, so the
    # refresh gives "returned", `pay`'s condition is checked again on it, and no refund runs.
    namespace: dict[str, Any] = {
        "run_case": run_case,
        "later": later,
        "refund_fresh": refund_fresh(),
        "PEOPLE": PEOPLE,
    }
    exec(guide_example("### What happens to a stale fact"), namespace)  # noqa: S102 -- our guide
    run = namespace["run"]
    assert run.state.values["check_order.status"] == "returned"
    assert not any(line.startswith("scheduled pay") for line in run.history)
    assert run.history[-1] == "closed: nothing left to do"


class FeeInput(BaseModel):
    amount: Decimal


class FeeOutput(BaseModel):
    fee: Decimal


def with_fee() -> Any:
    """The development catalog, and an activity that only computes: a fee from an amount."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register(
        ActivityContract(
            name="fees.compute",
            version=1,
            input=FeeInput,
            output=FeeOutput,
            risk="low",
            effect="compute",
            timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
            retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
            idempotency_key=None,
            outcomes=[],
            display=Display(title="Compute a fee", description="Computes a fee from an amount."),
        )
    )
    return catalog


# Where a fact may come from, as a step giving it (None: the opening or a task), the fact, and why
# it can't be fetched again.
SOURCES: dict[str, tuple[dict[str, Any] | None, str, str]] = {
    "the opening": (None, "order_id", "it came from the opening, so it can't be fetched again"),
    "a person": (None, "review.outcome", "it came from a person, so it can't be fetched again"),
    "a write": (
        {
            "kind": "activity",
            "activity": "letters.draft@2",
            "inputs": {"to_customer": {"var": "order_id"}, "template": "received"},
        },
        "source.outcome",
        "source has side effects (write), so it can't be run again",
    ),
    "a compute": (
        {"kind": "activity", "activity": "fees.compute@1", "inputs": {"amount": {"var": "amount"}}},
        "source.fee",
        "source computes it from its inputs (compute), so running it again gives nothing new",
    ),
    "a workflow": (
        {
            "kind": "workflow",
            "workflow": "kyc.check@1",
            "inputs": {"customer_id": {"var": "order_id"}},
        },
        "source.status",
        "source is a workflow step, so it isn't run again unasked",
    ),
    "a plan": (
        {
            "kind": "plan",
            "plan": "refund-order@1",
            "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
        },
        "source.outcome",
        "source is a plan step, so it isn't run again unasked",
    ),
}


def needing(source: dict[str, Any] | None, fact: str) -> dict[str, Any]:
    """A case whose `letter` reads `fact`, needing it at most a day old, and runs once `confirm`
    is answered: on day 3, in the tests. `review` is answered on day 0."""
    steps: dict[str, Any] = {
        "review": {
            "kind": "task",
            "display": {"title": "Review"},
            "roles": ["support"],
            "outcomes": {"approve": {"display": {"title": "Approve"}}},
        },
        "confirm": {
            "kind": "task",
            "display": {"title": "Confirm"},
            "roles": ["support"],
            "outcomes": {"ok": {"display": {"title": "Confirmed"}}},
        },
        "letter": {
            "kind": "activity",
            "display": {"title": "Draft the letter"},
            "activity": "letters.draft@2",
            "inputs": {"to_customer": {"var": "order_id"}, "template": "refund"},
            "requires": ["review", "confirm"],
            "when": {"exists": fact},
            "max_age": {fact: "1d"},
        },
    }
    if source is not None:
        steps["source"] = {"display": {"title": "Give the fact"}, **source}
        steps["letter"]["requires"].append("source")
    return {
        "case": "fresh",
        "display": {"title": "Fresh facts"},
        "fields": {
            "order_id": {"type": "string", "display": {"title": "Order"}},
            "amount": {"type": "number", "display": {"title": "Amount"}},
        },
        "steps": steps,
        "close_reasons": {"done": {"display": {"title": "Done"}, "roles": ["operations"]}},
    }


@pytest.mark.parametrize("where", list(SOURCES))
def test_a_fact_that_cant_be_fetched_again_needs_attention(where: str) -> None:
    source, fact, why = SOURCES[where]
    plan = load_plan()
    run = run_case(
        needing(source, fact),
        file={"order_id": "ord-1", "amount": 80},
        answers=[("review", "approve", "ana"), later("3d"), ("confirm", "ok", "ana")],
        people={**PEOPLE, "omar": ["operations"]},
        catalog=with_fee(),
        activities={"fees.compute@1": lambda inputs: {"fee": Decimal(2)}},
        plans={"refund-order@1": plan},
        plan_answers={"source": [("approve_refund", "approve", "sam")]},  # the plan's own wait
    )
    line = f"{fact} was obtained 3 days ago, and letter needs it at most 1 day old: {why}"
    assert run.needs_attention == [f"letter#1: {line}"]
    assert not any(line.startswith("refreshing") for line in run.history)
    assert run.status == "open"  # a failed step is pending work (brief, D17)


def test_a_retry_checks_freshness_again() -> None:
    source, fact, why = SOURCES["a person"]
    run = run_case(
        needing(source, fact),
        file={"order_id": "ord-1", "amount": 80},
        answers=[
            ("review", "approve", "ana"),
            later("3d"),
            ("confirm", "ok", "ana"),
            later("1h"),
            retry("letter#1", "omar"),
        ],
        people={**PEOPLE, "omar": ["operations"]},
    )
    assert "omar retried letter#1 as operations" in run.history
    assert run.needs_attention == [
        f"letter#1: {fact} was obtained 3 days ago, and letter needs it at most 1 day old: {why}"
    ]
    assert not run.reached("letter")


def load_plan() -> dict[str, Any]:
    """The plans guide's `refund-order` plan, its first JSON block, as stored data."""
    guide = (ROOT / "docs" / "guides" / "plans.md").read_text()
    plan: dict[str, Any] = json.loads(
        guide.split("```json\n")[1].split("```")[0], parse_float=Decimal
    )
    return plan


def answers_in_turn(*answers: Any) -> Any:
    """A lookup giving each answer in turn: a status, or an exception it raises."""
    queue = list(answers)

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return {"status": answer}

    return lookup


REVIEWED_ON_DAY_3 = [later("3d"), ("review", "approve", "ana", {"approved_amount": 80})]


def test_a_refresh_without_a_fresh_value_needs_attention() -> None:
    # It gives a declared outcome, so no output is written: the fact is still 3 days old, and
    # `pay` needs attention rather than refreshing again.
    run = run_case(
        refund_fresh(),
        file={"order_id": "ord-1", "amount": 80},
        answers=REVIEWED_ON_DAY_3,
        people=PEOPLE,
        activities={"orders.lookup@1": answers_in_turn("delivered", Outcome("not_found"))},
    )
    assert run.needs_attention == [
        (
            "pay#1: check_order#2 gave not_found, so check_order.status is still 3 days old, and "
            "pay needs it at most 1 day old"
        )
    ]
    assert [r.entry for r in run.state.runs if r.step == "check_order"] == [
        "check_order#1",
        "check_order#2",
    ]


def test_a_failed_refresh_needs_attention_and_is_retried() -> None:
    # The refresh fails after its retries: it needs attention itself, and `pay`, which requires
    # `check_order`, waits for it. Retried and done, `pay` runs on the fresh value.
    run = run_case(
        refund_fresh(),
        file={"order_id": "ord-1", "amount": 80},
        answers=[*REVIEWED_ON_DAY_3, retry("check_order#2", "omar")],
        people={**PEOPLE, "omar": ["operations"]},
        activities={
            "orders.lookup@1": answers_in_turn("delivered", ConnectionError("down"), "delivered")
        },
    )
    failed = "check_order#2 failed: orders.lookup@1 failed with ConnectionError: ‹sensitive›"
    assert run.history.index(failed) < run.history.index("omar retried check_order#2 as operations")
    assert run.needs_attention == []
    assert run.reached("pay")
    assert [r.entry for r in run.state.runs if r.step == "check_order"] == [
        "check_order#1",
        "check_order#2",
    ]


def test_a_failed_refresh_is_never_made_again_for_the_same_need() -> None:
    # `pay` reads `check_order.status` without requiring `check_order`: once the refresh has
    # failed, `pay` is admitted again, and needs attention instead of refreshing again.
    definition = refund_fresh()
    definition["steps"]["pay"]["requires"] = ["review"]
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 80},
        answers=[*REVIEWED_ON_DAY_3, later("1h"), shown("order_id", "ana")],
        people=PEOPLE,
        activities={"orders.lookup@1": answers_in_turn("delivered", ConnectionError("down"))},
    )
    assert (
        "pay#1: check_order#2 failed, so check_order.status is still 3 days old, and pay "
        "needs it at most 1 day old" in run.needs_attention
    )
    assert [r.entry for r in run.state.runs if r.step == "check_order"] == [
        "check_order#1",
        "check_order#2",
    ]


def test_a_fact_with_no_time_stops_the_step() -> None:
    # A state carried from a run before 9d has no times: an age that can't be told is never
    # read as fresh (fail closed).
    case = parse_case(refund_fresh())
    state, _ = decide(case, CATALOG, CaseState("t"), Opened(FILE, None, at=START))
    state, _ = decide(
        case, CATALOG, state, Completed("check_order#1", {"status": "delivered"}, at=START)
    )
    del state.obtained["check_order.status"]
    answer = Answered(
        "review",
        "approve",
        "ana",
        frozenset({"support"}),
        {"approved_amount": Decimal(80)},
        at=START,
    )
    state, commands = decide(case, CATALOG, state, answer)
    assert commands == []
    [failed] = [run for run in state.runs if run.status == "failed"]
    assert failed.reason == "check_order.status has no time obtained, so pay can't tell its age"


def test_a_running_refresh_undoes_nothing_it_doesnt_change() -> None:
    # `notice` requires `check_order` and waits for its approval. While `check_order#2` runs for
    # `pay`, `check_order` still counts as done: `notice`'s approval stays open, and stays open
    # once the refresh gives the same status. `letter` needs the same fact: one refresh serves
    # both.
    definition = refund_fresh()
    definition["steps"]["notice"] = {
        "kind": "activity",
        "display": {"title": "Draft a notice"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "order_id"}, "template": "notice"},
        "requires": ["check_order"],
        "approval": {"roles": ["support-lead"], "display": {"reason": "Notices need a lead"}},
    }
    definition["steps"]["letter"] = {
        "kind": "activity",
        "display": {"title": "Draft a letter"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "order_id"}, "template": "letter"},
        "requires": ["review"],
        "when": {"==": [{"var": "check_order.status"}, "delivered"]},
        "max_age": {"check_order.status": "1d"},
    }
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 80},
        answers=[finish("check_order#1"), *REVIEWED_ON_DAY_3],
        people=PEOPLE,
        held=["check_order"],
    )
    assert "approval of notice by support-lead" in run.waiting_for  # open while it runs
    assert not any(line.startswith("withdrew") for line in run.history)
    assert [r.entry for r in run.state.runs if r.step == "check_order"] == [
        "check_order#1",
        "check_order#2",
    ]
    assert sum(line.startswith("refreshing check_order.status") for line in run.history) == 1
    finished = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 80},
        answers=[finish("check_order#1"), *REVIEWED_ON_DAY_3, finish("check_order#2")],
        people=PEOPLE,
        held=["check_order"],
    )
    assert "approval of notice by support-lead" in finished.waiting_for  # same status: it stands
    assert finished.reached("pay") and finished.reached("letter")
