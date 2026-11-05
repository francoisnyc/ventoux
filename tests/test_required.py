"""Layer 18a: required steps. A required step is work the case owes: it may not close by itself
until the step's latest run is done, and only its doing or a person's close ends that (brief, D72).

See docs/layers/18-lifecycle.md (18a) and docs/guides/cases.md, "Required steps".
"""

import copy
import json
import runpy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from temporalio.client import Client
from test_temporal_case import LARGE, QUEUE, on_temporal, reported

from ventoux.case.advising import advisor_view
from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.simulate import simulate
from ventoux.case.story import parse_story
from ventoux.case.validate import validate_case
from ventoux.temporal.cases import CaseReport, answer, start_case
from ventoux.testing import (
    CATALOG,
    START,
    ChangeRefused,
    DevelopmentCases,
    Outcome,
    ProposalRefused,
    close,
    forget,
    load_definition,
    migrate,
    propose,
    release_of,
    retry,
    run_case,
    skip,
)
from ventoux.tooling.builder.written import written

ROOT = Path(__file__).parent.parent
GUIDE = ROOT / "docs" / "guides" / "cases.md"
SECTION = "## Required steps"
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")  # the quickstart's


def guide_confirm() -> dict[str, Any]:
    """The guide's required `confirm` step, as stored data, read from the guide itself so the
    guide can't drift from what is tested."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[1].split("```")[0]
    fragment: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    return fragment


def refund_confirmed() -> dict[str, Any]:
    """The quickstart's refund, with the guide's required `confirm` step."""
    definition = copy.deepcopy(REFUND)
    definition["steps"] |= guide_confirm()
    return definition


def test_a_required_step_nothing_can_ever_start_is_refused_at_validation() -> None:
    # The curriculum's negative test. A step that can never run is already an error for every
    # step (NEVER_RUNS, from layer 10's fixpoint); a required one gets that issue alone, one
    # cause, one issue (brief, D72).
    definition = refund_confirmed()
    definition["milestones"] = {"reported": {"display": {"title": "Reported"}}}
    definition["steps"]["confirm"]["requires"] = ["reported"]  # nothing reaches it
    found = validate_case(parse_case(definition), CATALOG)
    assert [(issue.path, issue.code, issue.message) for issue in found] == [
        (
            "steps.confirm.requires",
            "NEVER_RUNS",
            (
                "confirm can never run: it requires reported, which no step or rule reaches: "
                "reach reported from a step or a rule, or remove the requirement"
            ),
        )
    ]


def test_a_required_step_with_a_condition_is_refused_when_read() -> None:
    # A required step is owed in every case, so it has no `when`: a step owed only sometimes is
    # started by a rule, or proposed, and isn't required (brief, D72).
    definition = refund_confirmed()
    definition["steps"]["confirm"]["when"] = {"==": [{"var": "review.outcome"}, "reject"]}
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == (
        "steps.confirm: a required step is owed in every case, so it has no when: start it from "
        "a rule, or drop required"
    )


ORDER = {"order_id": "ord-1", "amount": 250}
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "omar": ["operations"]}


def test_a_case_that_owes_a_required_step_stays_open_and_says_so() -> None:
    # The guide's example, as written: a rejected refund starts nothing more, but the case owes
    # `confirm`, so it doesn't close by itself, and says what it owes and who may start it.
    refund = refund_confirmed()
    rejected = run_case(refund, file=ORDER, answers=[("review", "reject", "ana")], people=PEOPLE)
    assert rejected.waiting_for == ["confirm, required, proposed by support"]
    assert not rejected.closed

    confirmed = run_case(
        refund,
        file=ORDER,
        answers=[
            ("review", "reject", "ana"),
            propose("confirm", "ana"),
            ("confirm", "confirmed", "ana"),
        ],
        people=PEOPLE,
    )
    assert confirmed.closed


def test_the_builder_writes_the_guides_required_step() -> None:
    # The builder guide's example is the cases guide's refund, word for word as data: the same
    # JSON whichever way it is written (brief, D58).
    found = runpy.run_path(str(ROOT / "examples" / "builder" / "required.py"))["refund"]
    assert json.loads(written(found), parse_float=Decimal) == refund_confirmed()


def refund_paying_required() -> dict[str, Any]:
    """The quickstart's refund, its payment owed in every case: no `when` (a required step has
    none), so it runs after any review, and support may propose it again."""
    definition = copy.deepcopy(REFUND)
    pay = definition["steps"]["pay"]
    del pay["when"]
    pay |= {"required": True, "repeatable": True, "proposed_by": ["support"]}
    return definition


def declining(inputs: dict[str, Any]) -> dict[str, Any]:
    """A provider that declines the refund: a business outcome, declared by the contract."""
    raise Outcome("declined")


def test_a_required_step_done_with_any_outcome_is_no_longer_owed() -> None:
    # Done is done with any outcome, as `requires` reads it: a declined refund is an outcome
    # someone handles (here, the call), not work left undone (brief, D72).
    run = run_case(
        refund_paying_required(),
        file={"order_id": "ord-1", "amount": 40},
        answers=[
            ("review", "approve", "ana", {"approved_amount": 40}),
            ("call_customer", "called", "ana"),
        ],
        people=PEOPLE,
        activities={"payments.refund@2": declining},
    )
    assert run.closed


def refund_confirmed_withdrawable() -> dict[str, Any]:
    """The guide's refund with `confirm`, made repeatable, and a rule that stops it when the
    customer withdraws, which support records by answering `take_call`."""
    definition = refund_confirmed()
    definition["steps"]["confirm"]["repeatable"] = True
    definition["milestones"] = {"withdrawn": {"display": {"title": "Withdrawn"}}}
    definition["steps"]["take_call"] = {
        "kind": "task",
        "display": {"title": "Take the customer's call"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"withdrew": {"display": {"title": "Withdrew"}, "reaches": ["withdrawn"]}},
    }
    definition["rules"] = {
        "withdraw": {
            "display": {"title": "Stop confirming when the customer withdraws"},
            "on": {"reached": "withdrawn"},
            "then": {"stop": ["confirm"]},
        }
    }
    return definition


def test_a_required_step_a_rule_stopped_is_owed_still() -> None:
    # A run a rule stopped ends `cancelled`, neither done nor failed (brief, D40): the step is
    # owed still, and the case waits for another run of it (brief, D72).
    run = run_case(
        refund_confirmed_withdrawable(),
        file=ORDER,
        answers=[
            ("review", "reject", "ana"),
            propose("confirm", "ana"),
            propose("take_call", "ana"),
            ("take_call", "withdrew", "ana"),
        ],
        people=PEOPLE,
    )
    assert "cancelled confirm#1" in "\n".join(run.history)
    assert run.waiting_for == ["confirm, required, proposed by support"]
    assert not run.closed


def test_a_required_step_whose_approval_was_rejected_is_owed_still() -> None:
    # A rejected approval ends the run `rejected`: nothing was done, so the step is owed still
    # (brief, D72), and support may propose it again.
    run = run_case(
        refund_paying_required(),
        file=ORDER,
        answers=[("review", "approve", "ana", {"approved_amount": 250}), ("pay", "reject", "sam")],
        people=PEOPLE,
    )
    assert run.waiting_for == ["pay, required, proposed by support"]
    assert not run.closed


def failing_once() -> Any:
    """A provider down for the first call, then up: the run fails, and its retry goes through."""
    calls: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs["idempotency_key"])
        if len(calls) == 1:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-ord-1"}

    return refund


OPERATING = PEOPLE | {"olga": ["operations"]}  # two operators, so a skip could be approved


def test_a_skip_of_a_required_steps_failed_run_is_refused() -> None:
    # A skip goes on as if the run weren't needed, and a required step is one that is: its
    # obligation ends only by doing it, or by a person's close (brief, D72).
    reviewed = ("review", "approve", "ana", {"approved_amount": 40})
    small = {"order_id": "ord-1", "amount": 40}
    with pytest.raises(
        ChangeRefused,
        match="^pay is required, so its run is never skipped: retry it, or close the case with a "
        "reason$",
    ):
        run_case(
            refund_paying_required(),
            file=small,
            answers=[reviewed, skip("pay#1", "omar")],
            people=OPERATING,
            activities={"payments.refund@2": failing_once()},
        )
    # The retry that completes does it, and the case closes.
    retried = run_case(
        refund_paying_required(),
        file=small,
        answers=[reviewed, retry("pay#1", "omar")],
        people=OPERATING,
        activities={"payments.refund@2": failing_once()},
    )
    assert retried.closed


def test_only_the_latest_run_of_a_required_step_counts() -> None:
    # Done is the latest run's (brief, D72): `confirm` done once, run again, and stopped, is owed
    # again, as `requires` reads its latest run.
    run = run_case(
        refund_confirmed_withdrawable(),
        file=ORDER,
        answers=[
            ("review", "reject", "ana"),
            propose("take_call", "ana"),  # open, so the case stays open meanwhile
            propose("confirm", "ana"),
            ("confirm", "confirmed", "ana"),
            propose("confirm", "ana"),
            ("take_call", "withdrew", "ana"),  # stops confirm#2
        ],
        people=PEOPLE,
    )
    assert "cancelled confirm#2" in "\n".join(run.history)
    assert run.waiting_for == ["confirm, required, proposed by support"]
    assert not run.closed


def test_an_owed_step_with_its_run_open_is_said_once() -> None:
    # While its run is open, the entry says what the case waits for; the owed line would say it
    # twice (brief, D24) (brief, D72).
    run = run_case(
        refund_confirmed(),
        file=ORDER,
        answers=[("review", "reject", "ana"), propose("confirm", "ana")],
        people=PEOPLE,
    )
    assert run.waiting_for == ["confirm by support"]


def always_down(inputs: dict[str, Any]) -> dict[str, Any]:
    """A provider that never answers: every run of the payment fails, and needs attention."""
    raise ConnectionError("provider unreachable")


def test_a_skip_proposed_before_its_step_became_required_is_not_applied() -> None:
    # A skip is checked again when it is approved, against the case as it is then (brief, D52):
    # proposed on release 1, where `pay` isn't required, it isn't applied on release 2, where it
    # is (brief, D72).
    not_required = refund_paying_required()
    not_required["steps"]["pay"]["required"] = False
    release_1 = release_of(not_required, 1)
    release_2 = release_of(refund_paying_required(), 2)
    people = OPERATING | {"pia": ["platform"], "lee": ["support-lead", "platform"]}
    run = run_case(
        not_required,
        file={"order_id": "ord-1", "amount": 40},
        answers=[
            ("review", "approve", "ana", {"approved_amount": 40}),
            skip("pay#1", "omar"),
            migrate(release_2, {}, "pia"),
            ("case.change#2", "approve", "lee"),
            ("case.change#1", "approve", "olga"),
        ],
        people=people,
        release=release_1,
        activities={"payments.refund@2": always_down},
    )
    assert run.history[-1] == (
        "case.change#1 not applied: pay is required, so its run is never skipped: retry it, or "
        "close the case with a reason"
    )


# --- Every reader of what the case waits for says what it owes (from the tutor's review) ---


def test_a_story_ends_saying_what_the_case_owes() -> None:
    # A story's end lists every kind of pending work; what is owed keeps the case open, so it is
    # said too, never "nothing pending" (brief, D10) (brief, D72).
    story = {
        "title": "The refund is rejected",
        "definition": "refund-confirmed.json",
        "file": {"order_id": "ord-1", "amount": 40},
        "people": {"ana": ["support"]},
        "fakes": {"payments.refund@2": {"gives": {"refund_id": "refund-1"}}},
        "timeline": [
            {"at": "day 1", "answer": {"step": "review", "outcome": "reject", "by": "ana"}}
        ],
    }
    simulation = simulate(parse_story(story), parse_case(refund_confirmed()), CATALOG)
    assert simulation.end == ("status: open", "waiting for: confirm, required, proposed by support")


def test_the_advisor_is_shown_what_the_case_owes() -> None:
    # The advisor sees what the case waits for as the inbox says it (brief, D61): what it owes
    # included.
    run = run_case(
        refund_confirmed(), file=ORDER, answers=[("review", "reject", "ana")], people=PEOPLE
    )
    view = advisor_view(
        parse_case(refund_confirmed()), CATALOG, run.state, "ana", frozenset({"support"}), START
    )
    assert view.waiting_for == ("confirm, required, proposed by support",)


def test_the_report_on_temporal_says_what_the_case_owes() -> None:
    # The same words on Temporal as in memory (brief, D24) (brief, D72).
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(
            client, DevelopmentCases, refund_confirmed(), LARGE, "refund-1", QUEUE
        )
        await reported(case, lambda now: now.waiting_at == ["review#1"])
        await answer(case, "review#1", "reject", "ana", PEOPLE["ana"], {})
        return await reported(case, lambda now: "review#1 done" in now.history)

    report = on_temporal(scenario)
    assert report.waiting_for == ["confirm, required, proposed by support"]
    assert report.waiting_at == []  # an owed step has no entry yet: it is proposed, not answered
    assert report.status == "open"


# --- Slice 3: closes_when waits for what is owed ---


def refund_confirmed_closing_when_paid() -> dict[str, Any]:
    """The guide's refund with `confirm`, closing as soon as it is paid."""
    definition = refund_confirmed()
    definition["milestones"] = {"paid": {"display": {"title": "Refund paid"}}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["closes_when"] = ["paid"]
    return definition


SMALL = {"order_id": "ord-1", "amount": 40}  # under 100: paid with no approval
SMALL_REVIEW = ("review", "approve", "ana", {"approved_amount": 40})


def test_closes_when_waits_for_an_owed_step() -> None:
    # "Close early" and "not before this" meet, and the stricter wins: paid is reached, but the
    # case owes confirm, so it doesn't close; nothing new starts but the owed step (brief, D72).
    held = run_case(
        refund_confirmed_closing_when_paid(), file=SMALL, answers=[SMALL_REVIEW], people=PEOPLE
    )
    assert held.reached("pay")
    assert held.waiting_for == ["confirm, required, proposed by support"]
    assert not held.closed
    with pytest.raises(
        ProposalRefused,
        match="^paid is reached, so the case closes once confirm is done, or a person closes it: "
        "nothing new starts but confirm$",
    ):
        run_case(
            refund_confirmed_closing_when_paid(),
            file=SMALL,
            answers=[SMALL_REVIEW, propose("review", "ana")],
            people=PEOPLE,
        )
    done = run_case(
        refund_confirmed_closing_when_paid(),
        file=SMALL,
        answers=[SMALL_REVIEW, propose("confirm", "ana"), ("confirm", "confirmed", "ana")],
        people=PEOPLE,
    )
    assert done.closed
    assert done.history[-1] == "closed: paid reached"


def with_close_reasons(definition: dict[str, Any]) -> dict[str, Any]:
    """`definition`, which support may close as a duplicate."""
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    }
    return definition


def test_a_persons_close_is_never_held_and_names_what_was_owed() -> None:
    # A requirement never traps a case: a person closes it with a declared reason, as ever, and
    # the last line says what was owed (brief, D72). A closed case waits for nothing.
    closed = run_case(
        with_close_reasons(refund_confirmed()),
        file=ORDER,
        answers=[("review", "reject", "ana"), close("duplicate", "ana")],
        people=PEOPLE,
    )
    assert closed.closed
    assert closed.history[-1] == "closed: duplicate, by ana; confirm not done"
    assert closed.waiting_for == []


def test_a_close_by_forgetting_is_never_held_and_names_what_was_owed() -> None:
    # Forgetting closes the case first (brief, D32): a requirement never holds that close either.
    forgotten = run_case(
        refund_confirmed(),
        file=ORDER,
        answers=[("review", "reject", "ana"), forget("pia", "olu")],
        people=PEOPLE | {"pia": ["privacy"], "olu": ["privacy"]},
    )
    assert forgotten.closed
    assert forgotten.history[-1] == "closed: forgotten; confirm not done"


# --- Slice 4: an owed step that can no longer start needs attention (choice 12) ---


def confirming_after_pay(pay_runs_again: bool = False) -> dict[str, Any]:
    """The guide's refund, `confirm` requiring the payment instead of the review (the tutor's
    run); with `pay_runs_again`, support may propose the payment again."""
    definition = refund_confirmed()
    definition["steps"]["confirm"]["requires"] = ["pay"]
    if pay_runs_again:
        definition["steps"]["pay"] |= {"repeatable": True, "proposed_by": ["support"]}
    return definition


PAY_REJECTED = [("review", "approve", "ana", {"approved_amount": 250}), ("pay", "reject", "sam")]


def test_an_owed_step_whose_requirement_cant_run_again_needs_attention() -> None:
    # Sam rejected the payment, which is not repeatable: it never runs again, so confirm can never
    # start. Only a person's close ends that, so the case says so to a person (brief, D72).
    run = run_case(confirming_after_pay(), file=ORDER, answers=PAY_REJECTED, people=PEOPLE)
    assert run.needs_attention == [
        (
            "confirm: required, and it can't start: confirm requires pay, which hasn't completed: "
            "close the case with a reason"
        )
    ]
    assert run.waiting_for == []  # in needs_attention, as a failed run is (brief, D24)
    assert not run.closed


def test_an_owed_step_that_cant_run_again_needs_attention() -> None:
    # confirm, stopped by the rule, isn't repeatable: nothing can start it again.
    definition = refund_confirmed_withdrawable()
    definition["steps"]["confirm"]["repeatable"] = False
    run = run_case(
        definition,
        file=ORDER,
        answers=[
            ("review", "reject", "ana"),
            propose("confirm", "ana"),
            propose("take_call", "ana"),
            ("take_call", "withdrew", "ana"),
        ],
        people=PEOPLE,
    )
    assert run.needs_attention == [
        (
            "confirm: required, and it can't start: confirm has run, and is not repeatable: close "
            "the case with a reason"
        )
    ]
    assert run.waiting_for == []


def test_an_owed_step_whose_requirement_can_still_run_waits_for_it() -> None:
    # Not stranded: support may propose the payment again, so confirm waits for it, saying so,
    # since nothing else is pending.
    run = run_case(
        confirming_after_pay(pay_runs_again=True), file=ORDER, answers=PAY_REJECTED, people=PEOPLE
    )
    assert run.waiting_for == ["confirm, required, after pay"]
    assert run.needs_attention == []


def test_an_owed_step_a_rule_starts_waits_for_the_rule() -> None:
    # "No rule starts it" is proven from the definition, never guessed (D37): a rule that starts
    # confirm counts, even if its moment never comes, so the case waits, and a person may close it.
    definition = refund_confirmed()
    del definition["steps"]["confirm"]["proposed_by"]
    definition["milestones"] = {"escalated": {"display": {"title": "Escalated"}}}
    definition["steps"]["escalate"] = {
        "kind": "task",
        "display": {"title": "Escalate"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"escalated": {"display": {"title": "Escalated"}, "reaches": ["escalated"]}},
    }
    definition["rules"] = {
        "confirm_when_escalated": {
            "display": {"title": "Confirm once escalated"},
            "on": {"reached": "escalated"},
            "then": {"start": ["confirm"]},
        }
    }
    run = run_case(definition, file=ORDER, answers=[("review", "reject", "ana")], people=PEOPLE)
    assert run.waiting_for == ["confirm, required, started by a rule"]
    assert run.needs_attention == []


def logged_first(check_first: bool = False) -> dict[str, Any]:
    """The guide's refund, closing once the order is logged, which happens at the opening: so the
    close is held from the start by what is owed. With `check_first`, confirm requires a check
    support proposes, which nothing starts while the close is held."""
    definition = refund_confirmed()
    definition["milestones"] = {"logged": {"display": {"title": "Order logged"}}}
    definition["steps"]["log"] = {
        "kind": "activity",
        "display": {"title": "Log the order"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "reaches": ["logged"],
    }
    definition["closes_when"] = ["logged"]
    if check_first:
        definition["steps"]["check"] = {
            "kind": "task",
            "display": {"title": "Check the request"},
            "roles": ["support"],
            "automatic": False,
            "proposed_by": ["support"],
            "outcomes": {"checked": {"display": {"title": "Checked"}}},
        }
        definition["steps"]["confirm"]["requires"] = ["check"]
    return definition


def test_under_a_held_close_an_owed_step_waits_for_a_requirement_on_its_way() -> None:
    # logged is reached at once, with the review still open: it is on its way, so confirm waits
    # for it; the case closes once the review and confirm are done (brief, D72).
    waiting = run_case(logged_first(), file=ORDER, answers=[], people=PEOPLE)
    assert waiting.waiting_for == ["review by support"]
    assert waiting.needs_attention == []
    done = run_case(
        logged_first(),
        file=ORDER,
        answers=[
            ("review", "reject", "ana"),
            propose("confirm", "ana"),
            ("confirm", "confirmed", "ana"),
        ],
        people=PEOPLE,
    )
    assert done.history[-1] == "closed: logged reached"


def test_under_a_held_close_an_owed_step_whose_requirement_cant_start_needs_attention() -> None:
    # While the close is held, nothing new starts but the owed step: the check confirm requires
    # was never run and isn't on its way, so confirm can never start (brief, D72).
    run = run_case(logged_first(check_first=True), file=ORDER, answers=[], people=PEOPLE)
    assert run.needs_attention == [
        (
            "confirm: required, and it can't start: confirm requires check, which hasn't completed: "
            "close the case with a reason"
        )
    ]
