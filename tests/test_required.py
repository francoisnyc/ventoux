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
