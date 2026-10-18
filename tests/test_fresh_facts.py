"""Fresh facts: time on events, when each fact was obtained, and `max_age` (layer 9d).

See docs/layers/09-case-data.md and docs/guides/case-data.md.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.freshness import TimeRefused, ago, as_said
from ventoux.case.memory import CaseRun
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseState, Completed, Obtained, Opened, Schedule
from ventoux.case.visibility import SheetRefused
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.interpreter import Outcome
from ventoux.core.output_sources import source as declared_source
from ventoux.core.sensitive import Sensitive
from ventoux.testing import (
    CATALOG,
    DAY,
    START,
    AnswerRefused,
    ProposalRefused,
    finish,
    later,
    load_definition,
    propose,
    retry,
    shown,
)
from ventoux.testing import run_case as run_any_case

ROOT = Path(__file__).parent.parent
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
GUIDE = (ROOT / "docs" / "guides" / "case-data.md").read_text()
FILE = {"order_id": "ord-1", "amount": Decimal(80)}
PEOPLE = {"ana": ["support"], "sam": ["support-lead"]}
HOUR = 60 * 60
# The guide's fresh refund looks the order up with `orders.lookup@2`, which has no development
# fake (layer 11b): each test says what it returns, and this is what the order says unless it
# says otherwise.
DELIVERED = {"orders.lookup@2": lambda inputs: {"status": "delivered"}}


def run_case(*args: Any, **options: Any) -> CaseRun:
    """`run_case`, with `orders.lookup@2` answering "delivered" unless the test gives its own."""
    options["activities"] = {**DELIVERED, **options.get("activities", {})}
    return run_any_case(*args, **options)


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
    # From the orders system, so `pay` may decide on it (brief, D39).
    status: Annotated[str, declared_source("system:orders")]


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
    assert run.state.sources["check_order.status"] == frozenset({"system:orders"})
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


def test_an_undeclared_status_cant_choose_a_payment() -> None:
    # `pay`'s condition reads the status, so the status chooses whether a payment is sent: a status
    # nobody vouched for fails `pay` on its inputs, for a person to look at (brief, D39). The guide
    # looks the order up with `orders.lookup@2`, which says the status comes from the orders system.
    review = [("review", "approve", "ana", {"approved_amount": 80})]
    undeclared = refund_fresh()
    undeclared["steps"]["check_order"]["activity"] = "orders.lookup@1"
    run = run_case(undeclared, file=FILE, answers=review, people=PEOPLE)
    assert run.needs_attention == [
        (
            "pay#1: payments.refund@2 takes order_id only from a system or a person, never from "
            "untrusted data, and pay's condition reads check_order.status (untrusted:undeclared)"
        )
    ]
    assert not run.reached("pay")
    assert run_case(refund_fresh(), file=FILE, answers=review, people=PEOPLE).reached("pay")


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


def needing(
    source: dict[str, Any] | None, fact: str, giver: str = "source", needer: str = "letter"
) -> dict[str, Any]:
    """A case whose step `needer` reads `fact`, needing it at most a day old, and runs once
    `confirm` is answered: on day 3, in the tests. `review` is answered on day 0; `giver`, if
    any, gives the fact."""
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
        steps[giver] = {"display": {"title": "Give the fact"}, **source}
        steps["letter"]["requires"].append(giver)
    steps[needer] = steps.pop("letter")
    return {
        "case": "fresh",
        "display": {"title": "Fresh facts"},
        "fields": {
            # A reference to orders, as the plan's field is: a text would be refused (brief, D36).
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}},
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


def proposed_pay() -> dict[str, Any]:
    """The guide's fresh refund, with `pay` started only when someone in support proposes it."""
    definition = refund_fresh()
    definition["steps"]["pay"].update({"automatic": False, "proposed_by": ["support"]})
    definition["stays_open"] = True
    definition["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    return definition


def test_a_proposal_waits_for_its_fresh_facts() -> None:
    # A proposal is a start like any other: the age of what the step reads is checked first, and a
    # stale read is fetched again before anything else is read (brief, D33) (brief, D39). The
    # proposal waits for it, then the step starts on the fresh value. Until 11b, a proposed `pay`
    # ran at once, on a status three days old.
    looked_up = iter(["delivered", "delivered"])
    run = run_case(
        proposed_pay(),
        file=FILE,
        answers=[
            ("review", "approve", "ana", {"approved_amount": 80}),
            later("3d"),
            propose("pay", "ana"),
        ],
        people=PEOPLE,
        activities={"orders.lookup@2": lambda inputs: {"status": next(looked_up)}},
    )
    proposed = run.history.index("ana proposed pay as support")
    assert run.history[proposed + 1 : proposed + 4] == [
        "refreshing check_order.status for pay: obtained 3 days ago, at most 1 day",
        "scheduled check_order#2: orders.lookup@2 (order_id from system:opener)",
        "check_order#2 done, giving status from system:orders",
    ]
    assert run.history[proposed + 4].startswith("scheduled pay#1: payments.refund@2")
    assert run.reached("pay")


def test_a_second_proposal_of_a_waiting_step_is_refused() -> None:
    # While a proposed `pay` waits for its fact, proposing it again is refused: accepted, the
    # second proposal would replace the first proposer, who could then approve the run
    # (brief, D25) (brief, D39). Once the fact lands, the approval is asked, and lee, who proposed
    # it, still can't give it.
    people = {**PEOPLE, "lee": ["support", "support-lead"], "bea": ["support"]}
    waiting = [
        ("review", "approve", "ana", {"approved_amount": 250}),
        finish("check_order#1"),
        later("3d"),
        propose("pay", "lee"),
    ]
    with pytest.raises(ProposalRefused) as refused:
        run_case(
            proposed_pay(),
            file=LARGE,
            answers=[*waiting, propose("pay", "bea")],
            people=people,
            held=["check_order"],
        )
    assert (
        str(refused.value) == "pay is already proposed, and waits for its facts to be fetched again"
    )
    with pytest.raises(AnswerRefused) as refused_approval:
        run_case(
            proposed_pay(),
            file=LARGE,
            answers=[*waiting, finish("check_order#2"), ("pay.approval#1", "approve", "lee")],
            people=people,
            held=["check_order"],
        )
    assert str(refused_approval.value) == "lee proposed pay, so cannot approve it"


def test_a_proposal_on_a_fact_that_cant_be_fetched_is_refused() -> None:
    # A person's answer can't be fetched again: a proposal that would need it fresher is refused,
    # saying why, and changes nothing (brief, D33) (brief, D39). It never waits for a refresh
    # that can't come.
    definition = proposed_pay()
    definition["steps"]["pay"]["max_age"] = {"review.outcome": "1d"}
    with pytest.raises(ProposalRefused) as refused:
        run_case(
            definition,
            file=FILE,
            answers=[
                ("review", "approve", "ana", {"approved_amount": 80}),
                later("3d"),
                propose("pay", "ana"),
            ],
            people=PEOPLE,
        )
    assert str(refused.value) == (
        "review.outcome was obtained 3 days ago, and pay needs it at most 1 day old: it came "
        "from a person, so it can't be fetched again"
    )


def test_a_contract_with_no_fake_raises() -> None:
    # `orders.lookup@2` has no development fake: a test that runs it says what it returns, so no
    # test reads a status nobody chose (layer 11b).
    with pytest.raises(LookupError, match="^no implementation of orders.lookup@2 is available$"):
        run_any_case(
            refund_fresh(),
            file=FILE,
            answers=[("review", "approve", "ana", {"approved_amount": 80})],
            people=PEOPLE,
        )


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
        activities={"orders.lookup@2": answers_in_turn("delivered", Outcome("not_found"))},
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
            "orders.lookup@2": answers_in_turn("delivered", ConnectionError("down"), "delivered")
        },
    )
    failed = "check_order#2 failed: orders.lookup@2 failed with ConnectionError: ‹sensitive›"
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
        activities={"orders.lookup@2": answers_in_turn("delivered", ConnectionError("down"))},
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


LARGE = {"order_id": "ord-1", "amount": 250}
REVIEWED_LARGE = ("review", "approve", "ana", {"approved_amount": 250})


def test_an_approval_is_asked_only_on_fresh_facts() -> None:
    # Reviewed on day 3: the status is refreshed before Sam is asked, so his sheet reads the new
    # value, never the old one.
    run = run_case(
        refund_fresh(),
        file=LARGE,
        answers=[later("3d"), REVIEWED_LARGE],
        people=PEOPLE,
        activities={"orders.lookup@2": answers_in_turn("delivered", "delivered")},
    )
    refreshing = run.history.index(
        "refreshing check_order.status for pay: obtained 3 days ago, at most 1 day"
    )
    assert run.history.index("asked pay.approval#1: approval of pay by support-lead") > refreshing
    assert run.state.obtained["check_order.status"] == Obtained(START + 3 * DAY, "check_order#2")


def test_an_unchanged_refresh_leaves_approvals_standing() -> None:
    # Asked on day 0, given by Sam on day 3: the refresh gives the same status, so his approval
    # stands and is spent on `pay`.
    run = run_case(
        refund_fresh(),
        file=LARGE,
        answers=[REVIEWED_LARGE, later("3d"), ("pay", "approve", "sam")],
        people=PEOPLE,
        activities={"orders.lookup@2": answers_in_turn("delivered", "delivered")},
    )
    assert "scheduled check_order#2: orders.lookup@2 (order_id from system:opener)" in run.history
    assert not any(line.startswith(("lapsed", "withdrew")) for line in run.history)
    assert run.reached("pay")


def test_a_changed_refresh_lapses_a_given_approval() -> None:
    # Sam approved a refund for a delivered order; the refresh says it was partly returned. His
    # approval lapses (he never saw that), and `pay`, which may still run, asks again.
    definition = refund_fresh()
    definition["steps"]["pay"]["when"] = {
        "in": [{"var": "check_order.status"}, ["delivered", "partly returned"]]
    }
    run = run_case(
        definition,
        file=LARGE,
        answers=[REVIEWED_LARGE, later("3d"), ("pay", "approve", "sam")],
        people=PEOPLE,
        activities={"orders.lookup@2": answers_in_turn("delivered", "partly returned")},
    )
    lapsed = run.history.index("lapsed pay.approval#1: check_order.status changed when refreshed")
    assert run.history.index("asked pay.approval#2: approval of pay by support-lead") > lapsed
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert not run.reached("pay")
    assert "pay" not in run.state.given


def test_a_changed_refresh_that_stops_the_step_lapses_its_approval() -> None:
    # The order was returned: `pay`'s condition is false now, and Sam's approval lapses with
    # nothing to spend it on. The case closes; nothing is paid.
    run = run_case(
        refund_fresh(),
        file=LARGE,
        answers=[REVIEWED_LARGE, later("3d"), ("pay", "approve", "sam")],
        people=PEOPLE,
        activities={"orders.lookup@2": answers_in_turn("delivered", "returned")},
    )
    assert "lapsed pay.approval#1: check_order.status changed when refreshed" in run.history
    assert not run.reached("pay")
    assert run.closed


def test_a_changed_refresh_withdraws_another_steps_open_approval() -> None:
    # `notice` reads the status in its condition and waits for its approval; the refresh made for
    # `pay` changes the status, so `notice`'s open approval is withdrawn (brief, D25).
    definition = refund_fresh()
    definition["steps"]["notice"] = {
        "kind": "activity",
        "display": {"title": "Draft a notice"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "order_id"}, "template": "notice"},
        "requires": ["check_order"],
        "when": {"!=": [{"var": "check_order.status"}, "lost"]},
        "approval": {"roles": ["support-lead"], "display": {"reason": "Notices need a lead"}},
    }
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 80},
        answers=REVIEWED_ON_DAY_3,
        people=PEOPLE,
        activities={"orders.lookup@2": answers_in_turn("delivered", "returned")},
    )
    assert "withdrew notice.approval#1: check_order.status changed" in run.history
    assert "asked notice.approval#2: approval of notice by support-lead" in run.history


def test_a_lapse_says_when_refreshed_only_when_it_was() -> None:
    # While `check_order#2` runs for Sam's approval, Ana sends the review back and approves 300:
    # the approval lapses because of her answer, not a refresh, and says only what changed.
    definition = refund_fresh()
    definition["steps"]["review"].update({"repeatable": True, "proposed_by": ["support"]})
    run = run_case(
        definition,
        file=LARGE,
        answers=[
            finish("check_order#1"),
            REVIEWED_LARGE,
            later("3d"),
            ("pay", "approve", "sam"),
            propose("review", "ana"),
            ("review", "approve", "ana", {"approved_amount": 300}),
        ],
        people=PEOPLE,
        held=["check_order"],
    )
    assert "lapsed pay.approval#1: approved_amount changed" in run.history
    assert not any(line.endswith("when refreshed") for line in run.history)


SECRET = "ORD-7-SECRET"  # an order ID treated as personal data, to look for where it mustn't be


def refund_with_a_sensitive_order() -> dict[str, Any]:
    """The refund, its order ID sensitive: only support and team leads see it (brief, D31)."""
    definition = refund_fresh()
    definition["fields"]["order_id"].update(
        {"sensitive": True, "visible_to": ["support", "support-lead"]}
    )
    return definition


def test_a_stale_sensitive_fact_needs_attention_and_quotes_nothing() -> None:
    definition = refund_with_a_sensitive_order()
    definition["steps"]["pay"]["max_age"] = {"order_id": "1d"}
    run = run_case(
        definition,
        file={"order_id": SECRET, "amount": 80},
        answers=REVIEWED_ON_DAY_3,
        people=PEOPLE,
    )
    assert run.needs_attention == [
        (
            "pay#1: order_id was obtained 3 days ago, and pay needs it at most 1 day old: it came "
            "from the opening, so it can't be fetched again"
        )
    ]
    assert not any(SECRET in line for line in [*run.history, *run.needs_attention])
    # Its time obtained isn't sensitive: a plain number, never wrapped.
    assert run.state.obtained["order_id"] == Obtained(START, None)


def test_a_refresh_passes_a_sensitive_input_wrapped() -> None:
    case = parse_case(refund_with_a_sensitive_order())
    file = {"order_id": Sensitive(SECRET), "amount": Decimal(80)}  # as the client sends it
    state, _ = decide(case, CATALOG, CaseState("t"), Opened(file, None, at=START))
    looked_up = Completed("check_order#1", {"status": "delivered"}, at=START)
    state, _ = decide(case, CATALOG, state, looked_up)
    answer = Answered(
        "review",
        "approve",
        "ana",
        frozenset({"support"}),
        {"approved_amount": Sensitive(Decimal(80))},
        at=START + 3 * DAY,
    )
    state, commands = decide(case, CATALOG, state, answer)
    [refresh] = commands
    assert isinstance(refresh, Schedule) and refresh.entry == "check_order#2"
    assert refresh.inputs["order_id"] == Sensitive(SECRET)  # wrapped through the refresh too
    assert not any(SECRET in line for line in state.history)


def test_people_see_when_each_fact_was_obtained() -> None:
    # The guide's sheet, run as written: Sam reads it three days after the lookup.
    namespace: dict[str, Any] = {
        "run_case": run_case,
        "refund_fresh": refund_fresh(),
        "PEOPLE": PEOPLE,
        "START": START,
        "DAY": DAY,
    }
    exec(guide_example("### Approvals and fresh facts"), namespace)  # noqa: S102 -- our guide
    run, sheet = namespace["run"], namespace["sheet"]
    # Every fact the approval depends on: what pay's when reads too, its guards included.
    assert sheet.lines == [
        "Amount approved: 250, obtained 3 days ago",
        "check_order.outcome: done, obtained 3 days ago",
        "check_order.status: delivered, obtained 3 days ago",
        "Order: ord-1, obtained 3 days ago",
        "review.outcome: approve, obtained 3 days ago",
    ]
    # The view gives each value's time, in seconds since the epoch.
    assert run.view(roles=["support"]).obtained["check_order.status"] == START
    # A sheet is read at the reader's time, never decided on: in an hour, an hour older.
    later_sheet = run.approval_sheet("pay.approval#1", roles=["support-lead"], at=START + HOUR)
    assert later_sheet.lines[2] == "check_order.status: delivered, obtained 1 hour ago"


def test_a_hidden_fact_shows_no_value_and_no_age() -> None:
    definition = refund_with_a_sensitive_order()
    definition["fields"]["approved_amount"]["visible_to"] = ["support"]
    run = run_case(
        definition,
        file={"order_id": SECRET, "amount": 250},
        answers=[REVIEWED_LARGE],
        people=PEOPLE,
    )
    sheet = run.approval_sheet("pay.approval#1", roles=["support-lead"], at=START + DAY)
    assert sheet.lines == [
        "Amount approved: hidden (needs support)",
        "check_order.outcome: done, obtained 1 day ago",
        "check_order.status: delivered, obtained 1 day ago",
        "Order: ‹sensitive›, obtained 1 day ago",  # seen, but never written out (brief, D31)
        "review.outcome: approve, obtained 1 day ago",
    ]
    assert "approved_amount" not in run.view(roles=["support-lead"]).obtained
    assert "order_id" in run.view(roles=["support-lead"]).obtained  # its time isn't sensitive


def test_a_sheet_is_read_only_for_an_open_approval_at_a_whole_time() -> None:
    run = run_case(refund_fresh(), file=LARGE, answers=[REVIEWED_LARGE], people=PEOPLE)
    with pytest.raises(SheetRefused) as refused:
        run.approval_sheet("pay.approval#3", roles=["support-lead"], at=START)
    assert str(refused.value) == "pay.approval#3 is not open: there is no sheet to read"
    with pytest.raises(TimeRefused):
        run.approval_sheet("pay.approval#1", roles=["support-lead"], at=1.5)  # type: ignore[arg-type]


def test_an_age_is_said_in_its_largest_whole_unit() -> None:
    # Rounded down, so an age is never said younger than it is.
    assert [ago(s) for s in (0, 59, 60, 119, 2 * HOUR - 1, DAY, 13 * DAY, 21 * DAY + HOUR)] == [
        "less than a minute",
        "less than a minute",
        "1 minute",
        "1 minute",
        "1 hour",
        "1 day",
        "1 week",
        "3 weeks",
    ]
    assert [as_said(written) for written in ("1d", "36h", "30m")] == [
        "1 day",
        "36 hours",
        "30 minutes",
    ]


def test_an_approved_step_that_fails_on_a_stale_fact_stops_once() -> None:
    # Found on Temporal, where it hung a workflow task: Sam approves three days after Ana's
    # answer, which `pay` needs at most a day old. `pay` fails once, keeping Sam's approval on
    # its failed run for a retry (brief, D26); it isn't admitted again in the same decision.
    definition = refund_fresh()
    definition["steps"]["pay"]["max_age"] = {"approved_amount": "1d"}
    run = run_case(
        definition,
        file=LARGE,
        answers=[REVIEWED_LARGE, later("3d"), ("pay", "approve", "sam")],
        people=PEOPLE,
    )
    assert run.needs_attention == [
        (
            "pay#1: approved_amount was obtained 3 days ago, and pay needs it at most 1 day old: "
            "it came from a person, so it can't be fetched again"
        )
    ]
    [failed] = [r for r in run.state.runs if r.step == "pay"]
    assert failed.approved is not None and failed.approved.by == "sam"
    assert "pay" not in run.state.given


def refusal_rows() -> list[str]:
    """Each example of the guide's "What the engine refuses" table under "Fresh facts"."""
    section = GUIDE.split("## Fresh facts")[1].split("## Reports")[0]
    table = section.split("### What the engine refuses")[1]
    rows = [line for line in table.splitlines() if line.startswith("| ")][1:]  # past the header
    return [row.rsplit("| `", 1)[1].removesuffix("` |") for row in rows]


def test_the_guides_freshness_refusals_are_what_the_engine_says() -> None:
    # Every row of the guide's table, made to happen, in the guide's own words.
    said: list[str] = []

    def refused(change: Any) -> None:
        definition = refund_fresh()
        change(definition["steps"])
        with pytest.raises(CaseInvalid) as error:
            parse_case(definition)
        said.extend(str(error.value).splitlines())

    refused(lambda steps: steps["pay"]["max_age"].update({"check_order.status": "1w"}))
    refused(lambda steps: steps["pay"]["max_age"].update({"check_order.status": "0m"}))
    refused(lambda steps: steps["pay"]["max_age"].update({"amount": "1d"}))

    def attention(definition: dict[str, Any], answers: list[Any], **more: Any) -> None:
        run = run_case(
            definition,
            file={"order_id": "ord-1", "amount": 80},
            answers=answers,
            people=PEOPLE,
            **more,
        )
        said.extend(line.split(": ", 1)[1] for line in run.needs_attention)

    person = refund_fresh()
    person["steps"]["pay"]["max_age"] = {"approved_amount": "1d"}
    attention(
        person,
        [
            ("review", "approve", "ana", {"approved_amount": 250}),
            later("3d"),
            ("pay", "approve", "sam"),
        ],
    )
    opening = refund_fresh()
    opening["steps"]["pay"]["max_age"] = {"order_id": "1d"}
    attention(opening, REVIEWED_ON_DAY_3)
    three_days_on = [("review", "approve", "ana"), later("3d"), ("confirm", "ok", "ana")]
    for (source, _, _), fact, giver, needer in (
        (SOURCES["a write"], "pay_fee.outcome", "pay_fee", "notify"),
        (SOURCES["a compute"], "fee.fee", "fee", "pay"),
        (SOURCES["a workflow"], "kyc.status", "kyc", "pay"),
    ):
        attention(
            needing(source, fact, giver, needer),
            three_days_on,
            catalog=with_fee(),
            activities={"fees.compute@1": lambda inputs: {"fee": Decimal(2)}},
        )
    attention(
        refund_fresh(),
        REVIEWED_ON_DAY_3,
        activities={"orders.lookup@2": answers_in_turn("delivered", Outcome("not_found"))},
    )
    reads_only = refund_fresh()
    reads_only["steps"]["pay"]["requires"] = ["review"]
    attention(
        reads_only,
        REVIEWED_ON_DAY_3,
        activities={"orders.lookup@2": answers_in_turn("delivered", ConnectionError("x"))},
    )

    credit = refund_fresh()
    credit["steps"]["check_order"].update(
        {
            "activity": "credit.check@1",
            "approval": {"roles": ["support-lead"], "display": {"reason": "Credit checks"}},
        }
    )
    attention(
        credit,
        [
            ("check_order.approval#1", "approve", "sam"),
            later("3d"),
            ("review", "approve", "ana", {"approved_amount": 80}),
        ],
        catalog=with_credit_check(),
        activities={"credit.check@1": lambda inputs: {"status": "delivered"}},
    )

    case = parse_case(refund_fresh())
    state, _ = decide(case, CATALOG, CaseState("t"), Opened(FILE, None, at=START))
    looked_up = Completed("check_order#1", {"status": "delivered"}, at=START)
    state, _ = decide(case, CATALOG, state, looked_up)
    del state.obtained["check_order.status"]  # as in a state carried from before 9d
    answered = Answered(
        "review",
        "approve",
        "ana",
        frozenset({"support"}),
        {"approved_amount": Decimal(80)},
        at=START,
    )
    state, _ = decide(case, CATALOG, state, answered)
    said.extend(run.reason for run in state.runs if run.status == "failed")

    run = run_case(refund_fresh(), file=LARGE, answers=[REVIEWED_LARGE], people=PEOPLE)
    with pytest.raises(SheetRefused) as sheet:
        run.approval_sheet("pay.approval#3", roles=["support-lead"], at=START)
    said.append(str(sheet.value))

    rows = refusal_rows()
    assert len(rows) == 13
    for row in rows:
        assert row in said, row


def test_freshness_is_checked_before_anything_else() -> None:
    # The first look said "returned", so read first, `pay`'s condition would be false and the
    # case would close unpaid. The age comes first: the refresh says "delivered", and the
    # condition is read on that.
    run = run_case(
        refund_fresh(),
        file={"order_id": "ord-1", "amount": 80},
        answers=REVIEWED_ON_DAY_3,
        people=PEOPLE,
        activities={"orders.lookup@2": answers_in_turn("returned", "delivered")},
    )
    assert run.reached("pay")


def test_freshness_lines_quote_no_value() -> None:
    # A refresh, a lapse and a step stopped on a stale fact: their lines name fields and ages,
    # never what the fields hold (brief, D30).
    first, second = "status-XJ41", "status-QP07"
    definition = refund_fresh()
    definition["steps"]["pay"]["when"] = {"in": [{"var": "check_order.status"}, [first, second]]}
    lapsed = run_case(
        definition,
        file=LARGE,
        answers=[REVIEWED_LARGE, later("3d"), ("pay", "approve", "sam")],
        people=PEOPLE,
        activities={"orders.lookup@2": answers_in_turn(first, second)},
    )
    assert any(line.startswith("lapsed pay.approval#1") for line in lapsed.history)
    stopped = copy.deepcopy(definition)
    stopped["steps"]["pay"]["max_age"] = {"approved_amount": "1d"}
    attention = run_case(
        stopped,
        file=LARGE,
        answers=[REVIEWED_LARGE, later("3d"), ("pay", "approve", "sam")],
        people=PEOPLE,
        activities={"orders.lookup@2": answers_in_turn(first, second)},
    )
    assert attention.needs_attention
    for line in [*lapsed.history, *attention.history, *attention.needs_attention]:
        assert first not in line and second not in line, line


class CreditInput(BaseModel):
    order_id: str


class CreditOutput(BaseModel):
    status: str


def with_credit_check() -> Any:
    """The development catalog, and a high-risk read: a credit check, which needs an approval."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register(
        ActivityContract(
            name="credit.check",
            version=1,
            input=CreditInput,
            output=CreditOutput,
            risk="high",
            effect="read",
            timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
            retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
            idempotency_key=None,
            outcomes=[],
            display=Display(title="Check credit", description="Reads a credit status."),
        )
    )
    return catalog


def refused_refresh(definition: dict[str, Any], answers: list[Any], **more: Any) -> Any:
    """`pay` reviewed on day 3, its fact from `check_order` stale; what the case did."""
    return run_case(
        definition,
        file={"order_id": "ord-1", "amount": 80},
        answers=answers,
        people={**PEOPLE, "omar": ["operations"]},
        activities={"credit.check@1": lambda inputs: {"status": "delivered"}},
        **more,
    )


def test_a_refresh_needs_what_any_run_of_its_step_needs() -> None:
    # Tutor review: a refresh ran a high-risk credit check that nobody approved. A refresh goes
    # through the same gate as any start: if its step needs an approval, a condition that holds
    # or requirements that are met, and they aren't there now, it isn't run, and a person
    # decides (fail closed, brief, D33).
    stale = "check_order.status was obtained 3 days ago, and pay needs it at most 1 day old"
    needing_approval = refund_fresh()
    needing_approval["steps"]["check_order"].update(
        {
            "activity": "credit.check@1",
            "approval": {"roles": ["support-lead"], "display": {"reason": "Credit checks"}},
        }
    )
    run = refused_refresh(
        needing_approval,
        [
            ("check_order.approval#1", "approve", "sam"),
            later("3d"),
            ("review", "approve", "ana", {"approved_amount": 80}),
        ],
        catalog=with_credit_check(),
    )
    assert run.needs_attention == [
        f"pay#1: {stale}: check_order needs an approval to run, so it isn't run again unasked"
    ]
    assert [r.entry for r in run.state.runs if r.step == "check_order"] == ["check_order#1"]

    # Its condition is false now: it isn't run again.
    unless_reviewed = refund_fresh()
    unless_reviewed["steps"]["check_order"]["when"] = {"!": [{"exists": "approved_amount"}]}
    run = refused_refresh(
        unless_reviewed, [later("3d"), ("review", "approve", "ana", {"approved_amount": 80})]
    )
    assert run.needs_attention == [
        f"pay#1: {stale}: check_order's condition is false now, so it isn't run again"
    ]

    # It requires a step that has started again: it isn't run again either.
    after_intake = refund_fresh()
    after_intake["steps"]["intake"] = {
        "kind": "task",
        "display": {"title": "Take the request in"},
        "roles": ["support"],
        "outcomes": {"done": {"display": {"title": "Taken in"}}},
        "repeatable": True,
        "proposed_by": ["support"],
    }
    after_intake["steps"]["check_order"]["requires"] = ["intake"]
    run = refused_refresh(
        after_intake,
        [
            ("intake", "done", "ana"),
            later("3d"),
            propose("intake", "ana"),
            ("review", "approve", "ana", {"approved_amount": 80}),
        ],
    )
    assert run.needs_attention == [
        (
            f"pay#1: {stale}: check_order requires intake, which hasn't completed, so it isn't "
            "run again"
        )
    ]
