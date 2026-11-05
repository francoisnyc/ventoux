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
from test_diff import packed
from test_diff_people import judged_lines
from test_events import waiting_for_a_receipt
from test_plan_step import refund_order, refund_with_plan
from test_temporal_case import LARGE, QUEUE, SwitchingCases, on_temporal, reported, runs_of

from ventoux.case.advising import advisor_view
from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.memory import CaseRun
from ventoux.case.sheet import case_map
from ventoux.case.simulate import simulate
from ventoux.case.story import parse_story
from ventoux.case.validate import validate_case
from ventoux.temporal.cases import CaseReport, answer, start_case
from ventoux.temporal.cases import propose as temporal_propose
from ventoux.testing import (
    CATALOG,
    START,
    ChangeRefused,
    DevelopmentCases,
    Outcome,
    ProposalRefused,
    close,
    edit,
    forget,
    load_definition,
    migrate,
    propose,
    release_of,
    retry,
    run_case,
    send,
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


# --- Slice 5: REQUIRED_MAY_STRAND, a warning: what may strand an owed step (brief, D72) ---


def strand_warnings(definition: dict[str, Any]) -> list[tuple[str, str]]:
    """Each REQUIRED_MAY_STRAND `ventoux check` gives `definition`: its path and message."""
    found = validate_case(parse_case(definition), CATALOG)
    assert all(i.severity == "warning" for i in found if i.code == "REQUIRED_MAY_STRAND")
    return [(i.path, i.message) for i in found if i.code == "REQUIRED_MAY_STRAND"]


def test_a_required_step_a_rule_may_stop_and_that_cant_run_again_is_warned() -> None:
    # A warning, never an error: the rule may never fire, so it doesn't hold for every case
    # (brief, D37).
    definition = refund_confirmed_withdrawable()
    definition["steps"]["confirm"]["repeatable"] = False
    assert strand_warnings(definition) == [
        (
            "steps.confirm",
            (
                "a rule may stop confirm, and it is required, so it might never run again: make "
                "it repeatable and proposed_by a role, or start it from a rule"
            ),
        )
    ]


def test_a_required_step_whose_approval_may_be_rejected_and_that_cant_run_again_is_warned() -> None:
    definition = refund_paying_required()
    del definition["steps"]["pay"]["repeatable"]
    del definition["steps"]["pay"]["proposed_by"]
    assert strand_warnings(definition) == [
        (
            "steps.pay",
            (
                "its approval may be rejected, and it is required, so it might never run again: "
                "make it repeatable and proposed_by a role, or start it from a rule"
            ),
        )
    ]


def test_a_required_step_that_can_run_again_is_not_warned() -> None:
    # Repeatable and proposed: a stop or a rejection leaves it able to run again.
    assert strand_warnings(refund_confirmed_withdrawable()) == []
    assert strand_warnings(refund_paying_required()) == []
    assert strand_warnings(refund_confirmed()) == []  # the guide's example warns about nothing


def test_a_required_step_whose_requirement_may_end_and_cant_run_again_is_warned() -> None:
    # The tutor's run, read from the definition: pay's approval may be rejected, and pay can't run
    # again, so confirm might never start.
    assert strand_warnings(confirming_after_pay()) == [
        (
            "steps.confirm",
            (
                "confirm requires pay, whose approval may be rejected, and which might never run "
                "again; confirm is required, so it might never start: make pay repeatable and "
                "proposed_by a role, or start it from a rule"
            ),
        )
    ]
    assert strand_warnings(confirming_after_pay(pay_runs_again=True)) == []


def test_a_required_step_whose_requirement_may_be_unmet_once_the_case_may_close_is_warned() -> None:
    # logged is reached by a step that doesn't require the check, which support proposes: it may
    # be reached with the check never run, and then nothing new starts but confirm.
    assert strand_warnings(logged_first(check_first=True)) == [
        (
            "steps.confirm",
            (
                "confirm requires check, which may not be done when logged is reached, and "
                "nothing but confirm starts then; confirm is required, so it might never start: "
                "make what reaches logged require check, or remove logged from closes_when"
            ),
        )
    ]
    # The review starts itself at the opening, so it is on its way, or done, whenever logged is
    # reached: no warning (from the tutor's review).
    assert strand_warnings(logged_first()) == []
    # paid is reached only by pay, which requires the review: done before, proven.
    assert strand_warnings(refund_confirmed_closing_when_paid()) == []


# --- From the tutor's review at 603a254: what is on its way under a held close ---


def withdrawable_closing() -> dict[str, Any]:
    """The guide's refund, closing once the customer withdraws (support records it by answering
    `take_call`), with `confirm` owed."""
    definition = refund_confirmed_withdrawable()
    definition["steps"]["confirm"]["repeatable"] = False
    definition["rules"] = {}
    definition["closes_when"] = ["withdrawn"]
    return definition


WITHDRAWS = [propose("take_call", "ana"), ("take_call", "withdrew", "ana")]


def test_under_a_held_close_a_milestone_an_open_task_will_reach_is_on_its_way() -> None:
    # confirm requires reviewed, which the open review reaches when answered: on its way, so
    # confirm waits; answered, the review reaches it, confirm runs, and the case closes.
    definition = withdrawable_closing()
    definition["milestones"]["reviewed"] = {"display": {"title": "Reviewed"}}
    definition["steps"]["review"]["reaches"] = ["reviewed"]
    definition["steps"]["confirm"]["requires"] = ["reviewed"]
    held = run_case(definition, file=ORDER, answers=WITHDRAWS, people=PEOPLE)
    assert held.needs_attention == []
    assert held.waiting_for == ["review by support"]
    done = run_case(
        definition,
        file=ORDER,
        answers=[
            *WITHDRAWS,
            ("review", "reject", "ana"),
            propose("confirm", "ana"),
            ("confirm", "confirmed", "ana"),
        ],
        people=PEOPLE,
    )
    assert done.history[-1] == "closed: withdrawn reached"


def settling_first() -> dict[str, Any]:
    """`withdrawable_closing`, `confirm` requiring `settle`, a required task support proposes."""
    definition = withdrawable_closing()
    definition["steps"]["settle"] = {
        "kind": "task",
        "display": {"title": "Settle the request"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "required": True,
        "outcomes": {"settled": {"display": {"title": "Settled"}}},
    }
    definition["steps"]["confirm"]["requires"] = ["settle"]
    return definition


def test_under_a_held_close_a_requirement_itself_owed_is_on_its_way() -> None:
    # settle is owed, so it may start under the held close: confirm waits for it, and the case
    # closes once both are done.
    rejected_then_withdrawn = [("review", "reject", "ana"), *WITHDRAWS]
    held = run_case(settling_first(), file=ORDER, answers=rejected_then_withdrawn, people=PEOPLE)
    assert held.needs_attention == []
    assert held.waiting_for == [  # owed steps in the order written
        "confirm, required, after settle",
        "settle, required, proposed by support",
    ]
    done = run_case(
        settling_first(),
        file=ORDER,
        answers=[
            *rejected_then_withdrawn,
            propose("settle", "ana"),
            ("settle", "settled", "ana"),
            propose("confirm", "ana"),
            ("confirm", "confirmed", "ana"),
        ],
        people=PEOPLE,
    )
    assert done.history[-1] == "closed: withdrawn reached"
    # Nor is it warned about: settle may start then, being owed itself.
    assert strand_warnings(settling_first()) == []


def test_under_a_held_close_an_automatic_owed_step_starts_once_its_requirement_completes() -> None:
    # Pin: the held close lets an owed step start by itself, as soon as what it requires is done.
    definition = logged_first()
    definition["steps"]["confirm"]["automatic"] = True
    del definition["steps"]["confirm"]["proposed_by"]
    run = run_case(definition, file=ORDER, answers=[("review", "reject", "ana")], people=PEOPLE)
    assert run.waiting_for == ["confirm by support"]


def test_under_a_held_close_an_owed_step_only_a_rule_starts_needs_attention() -> None:
    # Pin: no rule acts while the close is held (brief, D34), so a rule can't start it then.
    definition = logged_first()
    del definition["steps"]["confirm"]["proposed_by"]
    definition["milestones"]["escalated"] = {"display": {"title": "Escalated"}}
    definition["rules"] = {
        "confirm_when_escalated": {
            "display": {"title": "Confirm once escalated"},
            "on": {"reached": "escalated"},
            "then": {"start": ["confirm"]},
        }
    }
    run = run_case(definition, file=ORDER, answers=[("review", "reject", "ana")], people=PEOPLE)
    assert run.needs_attention == [
        (
            "confirm: required, and it can't start: confirm is started only by a rule, and no "
            "rule acts while the close is held: close the case with a reason"
        )
    ]


def test_a_circle_of_owed_requirements_under_a_held_close_needs_attention_and_ends() -> None:
    # Pin: confirm and settle, each owed, each requiring the other (a deadlock validation refuses,
    # DEADLOCK): the case still answers, saying each can't start, rather than asking for ever.
    definition = settling_first()
    definition["steps"]["settle"]["requires"] = ["confirm"]
    run = run_case(
        definition, file=ORDER, answers=[("review", "reject", "ana"), *WITHDRAWS], people=PEOPLE
    )
    assert run.needs_attention == [
        (
            "confirm: required, and it can't start: confirm requires settle, which hasn't "
            "completed: close the case with a reason"
        ),
        (
            "settle: required, and it can't start: settle requires confirm, which hasn't "
            "completed: close the case with a reason"
        ),
    ]


def test_a_repeatable_step_nobody_can_start_again_is_refused_when_read() -> None:
    # So `REQUIRED_MAY_STRAND` never meets one: "can run again" needs only `repeatable` once the
    # definition is read, and still names who starts it, as the format already insists.
    definition = refund_confirmed()
    definition["steps"]["confirm"] |= {"repeatable": True, "automatic": True}
    del definition["steps"]["confirm"]["proposed_by"]
    with pytest.raises(CaseInvalid, match="a repeatable step runs again only when proposed"):
        parse_case(definition)


def test_a_closes_when_milestone_a_rule_reaches_is_never_proven_after_a_requirement() -> None:
    # confirm requires a check support proposes; paid is reached by pay, which requires it too:
    # proven done before paid. A rule that may reach paid, on a moment that waits for nothing,
    # takes the proof away: doubt warns.
    definition = refund_confirmed_closing_when_paid()
    definition["steps"]["check"] = {
        "kind": "task",
        "display": {"title": "Check the request"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"checked": {"display": {"title": "Checked"}}},
    }
    definition["steps"]["confirm"]["requires"] = ["check"]
    definition["steps"]["pay"]["requires"] = ["check"]
    assert strand_warnings(definition) == []
    definition["milestones"]["escalated"] = {"display": {"title": "Escalated"}}
    definition["rules"] = {
        "paid_when_escalated": {
            "display": {"title": "Count an escalated refund as paid"},
            "on": {"reached": "escalated"},
            "then": {"reach": ["paid"]},
        }
    }
    assert [path for path, _ in strand_warnings(definition)] == ["steps.confirm"]


def test_done_before_is_read_through_what_a_step_requires() -> None:
    # confirm requires a check support proposes; paid is reached by notify, which requires pay,
    # which requires the check: done before paid, through pay, proven.
    definition = refund_confirmed_closing_when_paid()
    del definition["steps"]["pay"]["reaches"]
    definition["steps"]["check"] = {
        "kind": "task",
        "display": {"title": "Check the request"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"checked": {"display": {"title": "Checked"}}},
    }
    definition["steps"]["confirm"]["requires"] = ["check"]
    definition["steps"]["pay"]["requires"] = ["check"]
    definition["steps"]["notify"] = {
        "kind": "task",
        "display": {"title": "Tell the customer"},
        "roles": ["support"],
        "requires": ["pay"],
        "outcomes": {"told": {"display": {"title": "Told"}}},
        "reaches": ["paid"],
    }
    assert strand_warnings(definition) == []


def test_a_required_step_an_error_refuses_is_not_also_warned_about() -> None:
    # One cause, one issue: confirm can never run (NEVER_RUNS), so what might strand it isn't
    # said beside it.
    definition = withdrawable_closing()
    definition["rules"] = {
        "withdraw": {
            "display": {"title": "Stop confirming when the customer withdraws"},
            "on": {"reached": "withdrawn"},
            "then": {"stop": ["confirm"]},
        }
    }
    definition["milestones"]["reported"] = {"display": {"title": "Reported"}}
    definition["steps"]["confirm"]["requires"] = ["reported"]  # nothing reaches it
    codes = [
        i.code
        for i in validate_case(parse_case(definition), CATALOG)
        if i.path.startswith("steps.confirm")
    ]
    assert codes == ["NEVER_RUNS"]


# --- Slice 6: the diff and the case map read it ---


def without_required(definition: dict[str, Any], step: str = "confirm") -> dict[str, Any]:
    """`definition`, its `step` no longer required."""
    changed = copy.deepcopy(definition)
    changed["steps"][step]["required"] = False
    return changed


def test_the_diff_reads_required_turned_on_as_stricter_and_off_as_looser() -> None:
    # The reverse of automatic and repeatable: required, the case does more before it closes by
    # itself (brief, D55) (brief, D72).
    owed, not_owed = refund_confirmed(), without_required(refund_confirmed())
    assert judged_lines(not_owed, owed) == ["stricter   steps.confirm.required: false -> true"]
    assert judged_lines(owed, not_owed) == [
        "looser     steps.confirm.required: true -> false (the case may close without it)"
    ]


def test_the_case_map_says_what_the_case_owes() -> None:
    read = case_map(packed(refund_confirmed()), CATALOG)
    assert "The case owes it: it doesn't close by itself until confirm is done." in read
    assert "- It closes when nothing is left to do and confirm is done." in read
    held = case_map(packed(refund_confirmed_closing_when_paid()), CATALOG)
    assert "- It closes once paid is reached and confirm is done." in held


# --- Slice 7: a migration (brief, D53) ---


def with_a_call(definition: dict[str, Any]) -> dict[str, Any]:
    """`definition` with a call support may take, which keeps the case open while it is."""
    definition["steps"]["take_call"] = {
        "kind": "task",
        "display": {"title": "Take the customer's call"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"taken": {"display": {"title": "Taken"}}},
    }
    return definition


def renamed() -> dict[str, Any]:
    """The refund with `confirm` and a call, `confirm` renamed `tell` in its next release."""
    definition = with_a_call(refund_confirmed())
    definition["steps"]["tell"] = definition["steps"].pop("confirm")
    return definition


PLATFORM = PEOPLE | {"pia": ["platform"], "lee": ["support-lead", "platform"]}


def migrated(before: dict[str, Any], after: dict[str, Any], answers: list[Any]) -> CaseRun:
    """The case opened on `before` (release 1), played with `answers`, then moved to `after`
    (release 2) by Pia, approved by Lee, with the step renamed if `after` has `tell`."""
    mapping = {"steps": {"confirm": "tell"}} if "tell" in after["steps"] else {}
    run = run_case(
        before,
        file=ORDER,
        answers=[
            *answers,
            migrate(release_of(after, 2), mapping, "pia"),
            ("case.change#1", "approve", "lee"),
        ],
        people=PLATFORM,
        release=release_of(before, 1),
    )
    assert any(line.startswith("applied case.change#1: migrated") for line in run.history)
    return run


def test_a_migration_renaming_a_required_step_keeps_it_owed_under_its_new_name() -> None:
    # Owed is worked out from the runs and the definition, never stored, so it follows the
    # rename with the runs (brief, D53) (brief, D72); 17c's review found state that didn't.
    run = migrated(with_a_call(refund_confirmed()), renamed(), [("review", "reject", "ana")])
    assert run.waiting_for == ["tell, required, proposed by support"]


def test_a_migration_renaming_a_done_required_step_owes_nothing() -> None:
    done = [
        ("review", "reject", "ana"),
        propose("take_call", "ana"),  # open, so the case stays open to be migrated
        propose("confirm", "ana"),
        ("confirm", "confirmed", "ana"),
    ]
    run = migrated(with_a_call(refund_confirmed()), renamed(), done)
    assert run.waiting_for == ["take_call by support"]


def test_a_migration_making_a_done_step_required_owes_nothing() -> None:
    # The target decides what is required; a step done already is done. The call is taken first:
    # with nothing owed on release 1, a rejected refund would close at once.
    done = [
        propose("take_call", "ana"),
        ("review", "reject", "ana"),
        propose("confirm", "ana"),
        ("confirm", "confirmed", "ana"),
    ]
    not_required = without_required(with_a_call(refund_confirmed()))
    run = migrated(not_required, with_a_call(refund_confirmed()), done)
    assert run.waiting_for == ["take_call by support"]
    # And one not yet run is owed from the migration on.
    opened = [propose("take_call", "ana"), ("review", "reject", "ana")]
    owing = migrated(not_required, with_a_call(refund_confirmed()), opened)
    assert owing.waiting_for == ["take_call by support", "confirm, required, proposed by support"]


# --- Slice 8: on Temporal, across continue-as-new (brief, D27) ---


def test_what_is_owed_crosses_continue_as_new() -> None:
    # The review rejected, then a refused answer: two events, so the case continues as new. What
    # it owes is worked out from the runs, which cross with its state, so it still says so, and
    # closes once confirm is done (brief, D27) (brief, D72).
    async def scenario(client: Client) -> tuple[CaseReport, CaseReport, tuple[str, str]]:
        case = await start_case(
            client, SwitchingCases, refund_confirmed(), LARGE, "refund-1", QUEUE
        )
        await reported(case, lambda now: now.waiting_at == ["review#1"])
        await answer(case, "review#1", "reject", "ana", PEOPLE["ana"], {})
        await answer(case, "review#1", "reject", "ana", PEOPLE["ana"], {})  # refused: answered
        owing = await reported(case, lambda now: "refused" in "\n".join(now.history))
        switched = await runs_of(client, "refund-1")
        await temporal_propose(case, "confirm", "ana", PEOPLE["ana"])
        await reported(case, lambda now: now.waiting_at == ["confirm#1"])
        await answer(case, "confirm#1", "confirmed", "ana", PEOPLE["ana"], {})
        return owing, await case.result(), switched

    owing, ended, (first, last) = on_temporal(scenario, cases=SwitchingCases)
    assert last != first  # the case continued as new while it owed confirm
    assert owing.waiting_for == ["confirm, required, proposed by support"]
    assert ended.status == "closed"
    assert ended.history[-1] == "closed: nothing left to do"


# --- Routes: a plan, and an event ---


def test_a_required_plan_step_ending_failed_is_done() -> None:
    # A plan that ends in its failed final state gives the outcome `failed`: done, with an outcome
    # someone handles (brief, D28), so the requirement is met (brief, D72).
    definition = refund_with_plan()
    del definition["steps"]["settle"]["when"]
    definition["steps"]["settle"]["required"] = True
    rejected = run_case(
        definition,
        file=ORDER,
        answers=[("review", "approve", "ana", {"approved_amount": 250})],
        people=PEOPLE,
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "reject", "sam")]},
    )
    assert "settle#1 gave failed" in rejected.history
    assert rejected.closed


def test_a_required_wait_is_done_by_its_event() -> None:
    # An event's arrival completes the wait's run, and with it the requirement (brief, D41).
    definition = waiting_for_a_receipt()
    definition["steps"]["wait_for_receipt"]["required"] = True
    approved = ("review", "approve", "ana", {"approved_amount": 40})
    small = {"order_id": "ord-1", "amount": 40}
    waiting = run_case(definition, file=small, answers=[approved], people=PEOPLE)
    assert waiting.waiting_for == ["receipt_sent from portal"]  # said once, by its open run
    receipt = send("receipt_sent", {"receipt": "doc-7"}, "system:portal")
    sent = run_case(definition, file=small, answers=[approved, receipt], people=PEOPLE)
    assert sent.closed


def test_an_edit_changes_nothing_the_case_owes() -> None:
    # `required` is the definition's, never a value: an edit of the case file leaves what is owed
    # as it was (brief, D52) (brief, D72).
    edited = run_case(
        refund_confirmed(),
        file=ORDER,
        answers=[
            ("review", "approve", "ana", {"approved_amount": 2500}),
            edit("approved_amount", 250, "ana"),
            ("case.change#1", "approve", "lee"),
        ],
        people=PEOPLE | {"lee": ["support-lead"]},
    )
    assert any(line.startswith("applied case.change#1") for line in edited.history)
    assert edited.waiting_for == [
        "approval of pay by support-lead",
        "confirm, required, proposed by support",
    ]


# --- From the tutor's review of #86 ---


def test_under_a_held_close_a_milestone_an_owed_step_will_reach_is_on_its_way() -> None:
    # settle is owed, and may start under the held close; answered settled, it reaches settled,
    # which confirm requires: so confirm waits for it, and the case closes once both are done.
    definition = settling_first()
    definition["milestones"]["settled"] = {"display": {"title": "Settled"}}
    definition["steps"]["settle"]["outcomes"]["settled"]["reaches"] = ["settled"]
    definition["steps"]["confirm"]["requires"] = ["settled"]
    rejected_then_withdrawn = [("review", "reject", "ana"), *WITHDRAWS]
    held = run_case(definition, file=ORDER, answers=rejected_then_withdrawn, people=PEOPLE)
    assert held.needs_attention == []
    assert held.waiting_for == [  # owed steps in the order written
        "confirm, required, after settled",
        "settle, required, proposed by support",
    ]
    done = run_case(
        definition,
        file=ORDER,
        answers=[
            *rejected_then_withdrawn,
            propose("settle", "ana"),
            ("settle", "settled", "ana"),
            propose("confirm", "ana"),
            ("confirm", "confirmed", "ana"),
        ],
        people=PEOPLE,
    )
    assert done.history[-1] == "closed: withdrawn reached"


def test_a_requirement_at_the_opening_that_may_end_undone_is_warned() -> None:
    # The review starts itself at the opening, but a rule may stop it: then it may not be done
    # when logged is reached, though it can run again, so the warning stands.
    definition = logged_first()
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    definition["rules"] = {
        "stop_review": {
            "display": {"title": "Stop the review once logged"},
            "on": {"reached": "logged"},
            "then": {"stop": ["review"]},
        }
    }
    assert [message for _, message in strand_warnings(definition)] == [
        (
            "confirm requires review, which may not be done when logged is reached, and "
            "nothing but confirm starts then; confirm is required, so it might never start: "
            "make what reaches logged require review, or remove logged from closes_when"
        )
    ]
