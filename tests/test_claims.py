"""Layer 17a: claiming a task. A task's roles say who may answer it; its holder, who is asked to.
Holding grants nothing, and only the holder answers a held entry (brief, D69).

See docs/layers/17-assignment.md (17a) and docs/guides/cases.md, "Who is asked: claiming and
assigning tasks".
"""

from typing import Any

import pytest
from test_approvals import FOUR_EYES
from test_case import (
    REFUND,
    guide_refund_with_rework,
    guide_seen_by_support,
    guide_with_close_reasons,
)
from test_events import waiting_for_a_receipt
from test_migrations import REFUND_1, REFUND_2, REFUND_3, RENAMES, refund_2
from test_plan_step import refund_order, refund_with_plan
from test_rules import DUPLICATE, WITHDRAWS, withdrawable

from ventoux.case.definition import parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, Claimed
from ventoux.testing import (
    CATALOG,
    START,
    AnswerRefused,
    ClaimRefused,
    claim,
    close,
    edit,
    give_back,
    migrate,
    propose,
    release_of,
    run_case,
)

ORDER = {"order_id": "ord-1", "amount": 250}
PLANS = {"refund-order@1": refund_order()}  # the plan the plan step runs

# The guide's people: Ana reviews refunds, Sam reviews and leads the team, Lee leads it; Omar
# operates.
PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "omar": ["operations"],
}


def test_a_claim_without_the_tasks_role_is_refused() -> None:
    # The curriculum's negative test: a claim is checked as an answer would be, so someone who
    # couldn't answer the review can't be the one asked to (brief, D69).
    with pytest.raises(
        ClaimRefused,
        match="^omar may not claim review#1: review#1 is answered by support, and omar has "
        "operations$",
    ):
        run_case(REFUND, file=ORDER, answers=[claim("review#1", "omar")], people=PEOPLE)


def test_a_claim_makes_its_person_the_holder() -> None:
    # The guide's first example, as written: Ana holds the review, and the case still waits for
    # the same thing, naming nobody (brief, D24) (brief, D69).
    run = run_case(REFUND, file=ORDER, answers=[claim("review#1", "ana")], people=PEOPLE)
    assert run.waiting_for == ["review by support"]
    assert run.assignees == {"review#1": "ana"}
    assert run.history[-1] == "ana claimed review#1 as support"


def test_only_the_holder_answers_a_held_entry() -> None:
    # Holding narrows who may answer, never widens: Sam has the review's role, and is still
    # refused while Ana holds it (brief, D69).
    with pytest.raises(
        AnswerRefused,
        match="^ana holds review#1: ask ana to give it back, or someone who assigns to reassign "
        "it$",
    ):
        run_case(
            REFUND,
            file=ORDER,
            answers=[
                claim("review#1", "ana"),
                ("review", "approve", "sam", {"approved_amount": 250}),
            ],
            people=PEOPLE,
        )
    # The holder's answer is taken, and the assignment ends with the entry.
    run = run_case(
        REFUND,
        file=ORDER,
        answers=[claim("review#1", "ana"), ("review", "approve", "ana", {"approved_amount": 250})],
        people=PEOPLE,
    )
    assert run.reached("review")
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert run.assignees == {}


@pytest.mark.parametrize(
    ("who", "message"),
    [
        ("sam", "^ana holds review#1; ask someone who assigns to reassign it$"),
        ("ana", "^ana already holds review#1$"),
    ],
)
def test_a_held_entry_is_not_claimed_again(who: str, message: str) -> None:
    # One holder at a time: someone else's claim would take the work from Ana, and her own would
    # change nothing (brief, D69).
    with pytest.raises(ClaimRefused, match=message):
        run_case(
            REFUND,
            file=ORDER,
            answers=[claim("review#1", "ana"), claim("review#1", who)],
            people=PEOPLE,
        )


@pytest.mark.parametrize(
    ("script", "message"),
    [
        (
            [claim("review#1", "ana"), give_back("review#1", "sam")],
            "^sam doesn't hold review#1; ana does$",
        ),
        ([give_back("review#1", "ana")], "^nobody holds review#1$"),
    ],
)
def test_only_the_holder_gives_an_entry_back(script: list[Any], message: str) -> None:
    # Giving back is the holder's: anyone else would free work that isn't theirs (brief, D69).
    with pytest.raises(ClaimRefused, match=message):
        run_case(REFUND, file=ORDER, answers=script, people=PEOPLE)


def test_an_entry_given_back_is_in_its_queue_again() -> None:
    # Back in the queue, anyone with the role may claim it, or answer it.
    run = run_case(
        REFUND,
        file=ORDER,
        answers=[claim("review#1", "ana"), give_back("review#1", "ana")],
        people=PEOPLE,
    )
    assert run.assignees == {}
    assert run.history[-2:] == ["ana claimed review#1 as support", "ana gave back review#1"]
    again = run_case(
        REFUND,
        file=ORDER,
        answers=[
            claim("review#1", "ana"),
            give_back("review#1", "ana"),
            ("review", "approve", "sam", {"approved_amount": 250}),
        ],
        people=PEOPLE,
    )
    assert again.reached("review")


# What makes `pay`'s approval open: Sam, who leads the team and reviews too, reviewed the refund.
REVIEWED_BY_SAM = ("review", "approve", "sam", {"approved_amount": 250})


def test_a_claim_of_an_approval_is_refused_to_whom_it_excludes() -> None:
    # The guide's example: Sam set approved_amount, which pay sends, so he can never approve the
    # payment; being asked to would grant him nothing (brief, D11) (brief, D69).
    with pytest.raises(
        ClaimRefused,
        match="^sam may not claim pay.approval#1: sam set approved_amount, which pay uses, so "
        "cannot approve it$",
    ):
        run_case(
            REFUND,
            file=ORDER,
            answers=[REVIEWED_BY_SAM, claim("pay.approval#1", "sam")],
            people=PEOPLE,
        )


@pytest.mark.parametrize(
    ("definition", "who", "opened_by"),
    [
        (REFUND, "sam", None),  # whose answer set what pay sends (brief, D11)
        (REFUND, "lee", "lee"),  # who opened the case (brief, D11) (brief, D25)
        (guide_seen_by_support(), "lee", None),  # who can't see what pay reads (brief, D30)
    ],
)
def test_a_claim_of_an_approval_is_refused_as_its_answer_would_be(
    definition: dict[str, Any], who: str, opened_by: str | None
) -> None:
    # A claim is judged as that person's approval would be, by the same checks, so a claim can
    # never be taken where the answer would be refused (brief, D69).
    case = parse_case(definition)
    run = run_case(
        definition, file=ORDER, answers=[REVIEWED_BY_SAM], people=PEOPLE, opened_by=opened_by
    )
    roles = frozenset(PEOPLE[who])
    with pytest.raises(AnswerRefused) as answering:
        decide(
            case, CATALOG, run.state, Answered("pay.approval#1", "approve", who, roles, at=START)
        )
    with pytest.raises(ClaimRefused) as claiming:
        decide(case, CATALOG, run.state, Claimed("pay.approval#1", who, roles, at=START))
    assert str(claiming.value) == f"{who} may not claim pay.approval#1: {answering.value}"


def test_an_approval_needing_several_people_cant_be_held() -> None:
    # One entry collects several people's approvals (brief, D47), so no one person can hold it.
    with pytest.raises(
        ClaimRefused, match="^pay.approval#1 needs 2 people, so nobody can hold it$"
    ):
        run_case(
            FOUR_EYES,
            file={"order_id": "ord-1", "amount": 12000},
            answers=[
                ("review", "approve", "ana", {"approved_amount": 12000}),
                claim("pay.approval#1", "lee"),
            ],
            people=PEOPLE,
        )


def test_a_claim_of_an_approval_by_who_may_approve_it_is_taken() -> None:
    # Lee leads the team and had no hand in the amount: she may approve it, so she may hold it.
    run = run_case(
        REFUND,
        file=ORDER,
        answers=[REVIEWED_BY_SAM, claim("pay.approval#1", "lee")],
        people=PEOPLE,
    )
    assert run.assignees == {"pay.approval#1": "lee"}
    assert run.history[-1] == "lee claimed pay.approval#1 as support-lead"


REVIEWED_BY_ANA = ("review", "approve", "ana", {"approved_amount": 250})


@pytest.mark.parametrize(
    ("definition", "script", "entry", "who"),
    [
        (REFUND, [REVIEWED_BY_ANA], "review#1", "sam"),  # answered: closed
        (REFUND, [], "review#2", "sam"),  # never opened
        (REFUND, [], "pay#7", "sam"),  # no such run
        (REFUND, [], "review#1", "Ana"),  # an identifier is written one way (brief, D22)
        # A step waiting for an event is sent its event, never answered (brief, D41).
        (waiting_for_a_receipt(), [REVIEWED_BY_ANA], "wait_for_receipt#1", "sam"),
        # A plan step's waits are the plan's, never the case's entries (brief, D28).
        (refund_with_plan(), [REVIEWED_BY_ANA], "settle#1", "sam"),
    ],
)
def test_what_cant_be_answered_cant_be_claimed(
    definition: dict[str, Any], script: list[Any], entry: str, who: str
) -> None:
    # Fail closed: a claim of anything that isn't an open task or approval is refused, as an
    # answer to it is, saying the same (brief, D69).
    case = parse_case(definition)
    run = run_case(definition, file=ORDER, answers=script, people=PEOPLE, plans=PLANS)
    roles = frozenset(PEOPLE.get(who.lower(), ()))
    with pytest.raises(AnswerRefused) as answering:
        decide(case, CATALOG, run.state, Answered(entry, "approve", who, roles, at=START))
    with pytest.raises(ClaimRefused) as claiming:
        decide(case, CATALOG, run.state, Claimed(entry, who, roles, at=START))
    assert str(claiming.value) == str(answering.value)


def test_a_change_request_isnt_held() -> None:
    # A change request is approved by someone else, whoever they are (brief, D52); it is no task.
    with pytest.raises(ClaimRefused, match="^case.change#1 is a change request: nobody holds one$"):
        run_case(
            REFUND,
            file=ORDER,
            answers=[
                REVIEWED_BY_ANA,
                edit("approved_amount", 200, "ana"),
                claim("case.change#1", "lee"),
            ],
            people=PEOPLE,
        )


def test_an_approval_asked_again_keeps_its_holder() -> None:
    # The review is sent back and reworked while Lee holds pay's approval: the old entry is
    # withdrawn (brief, D25), and the new one is Lee's again, since she may still approve it.
    run = run_case(
        guide_refund_with_rework(),
        file=ORDER,
        answers=[
            REVIEWED_BY_ANA,
            claim("pay.approval#1", "lee"),
            propose("review", "ana"),
            ("review", "approve", "ana", {"approved_amount": 300}),
        ],
        people=PEOPLE,
    )
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert run.assignees == {"pay.approval#2": "lee"}
    assert run.history[-2:] == [
        "asked pay.approval#2: approval of pay by support-lead",
        "pay.approval#2 kept for lee",
    ]


def test_an_approval_asked_again_goes_to_its_queue_if_its_holder_cant_approve_it() -> None:
    # The guide's example: Sam holds pay's approval, and this time answers the reworked review
    # himself, so the new values are his and he can't approve them (brief, D11) (brief, D25) (brief, D69).
    run = run_case(
        guide_refund_with_rework(),
        file=ORDER,
        answers=[
            REVIEWED_BY_ANA,
            claim("pay.approval#1", "sam"),
            propose("review", "ana"),
            ("review", "approve", "sam", {"approved_amount": 250}),
        ],
        people=PEOPLE,
    )
    assert run.assignees == {}
    tail = [
        "withdrew pay.approval#1: review started again",
        "sam answered review#2 approve as support, setting approved_amount",
        "review#2 done",
        "asked pay.approval#2: approval of pay by support-lead",
        (
            "pay.approval#2 back in its queue: sam set approved_amount, which pay uses, so "
            "cannot approve it"
        ),
    ]
    assert [line for line in run.history if line in tail] == tail


def test_a_new_run_of_a_task_starts_in_its_queue() -> None:
    # Ana held the first review and answered it. Reviewing again is new work, so nobody holds
    # the second review until someone claims it (brief, D69).
    run = run_case(
        guide_refund_with_rework(),
        file=ORDER,
        answers=[claim("review#1", "ana"), REVIEWED_BY_ANA, propose("review", "ana")],
        people=PEOPLE,
    )
    assert run.waiting_for == ["review by support"]
    assert run.assignees == {}


def test_a_stop_ends_the_assignment_with_its_entry() -> None:
    # The customer withdraws while Ana holds the review: a rule stops it, and Ana holds nothing
    # (brief, D40) (brief, D69). Her late answer is refused as any answer to a closed entry is.
    staying = withdrawable() | {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}
    run = run_case(
        staying, file=ORDER, answers=[claim("review#1", "ana"), *WITHDRAWS], people=PEOPLE
    )
    assert "cancelled review#1: stopped by withdraw#1" in run.history
    assert run.assignees == {}
    with pytest.raises(AnswerRefused, match="^review#1 is closed$"):
        run_case(
            staying,
            file=ORDER,
            answers=[
                claim("review#1", "ana"),
                *WITHDRAWS,
                ("review#1", "approve", "ana", {"approved_amount": 250}),
            ],
            people=PEOPLE,
        )


def test_a_close_ends_the_assignment_with_its_entry() -> None:
    # Closed as a duplicate while Ana holds the review: it is cancelled, and her answer refused
    # (brief, D10) (brief, D69).
    run = run_case(
        guide_with_close_reasons(),
        file=ORDER,
        answers=[claim("review#1", "ana"), close("duplicate", "ana")],
        people=PEOPLE,
    )
    assert run.closed
    assert run.assignees == {}


def test_a_holder_who_lost_the_role_is_refused_and_still_holds_it() -> None:
    # The engine learns roles only when a person acts (brief, D22). Ana claimed the review as
    # support; she answers without it now: refused for the role, as anyone would be, and the
    # entry stays hers, since a refusal changes nothing (brief, D69).
    case = parse_case(REFUND)
    run = run_case(REFUND, file=ORDER, answers=[claim("review#1", "ana")], people=PEOPLE)
    no_longer = Answered(
        "review#1", "approve", "ana", frozenset(), {"approved_amount": 250}, at=START
    )
    with pytest.raises(
        AnswerRefused, match="^review#1 is answered by support, and ana has no role$"
    ):
        decide(case, CATALOG, run.state, no_longer)
    assert run.assignees == {"review#1": "ana"}


# --- Migrations (brief, D53): holders cross with their entries ---

MIGRATING = {**PEOPLE, "pia": ["platform"], "lee": ["support-lead", "platform"], "fay": ["fraud"]}


def on_refund_1(answers: list[Any]) -> Any:
    """The refund opened on its first release, played with `answers`."""
    return run_case(REFUND, file=ORDER, answers=answers, people=MIGRATING, release=REFUND_1)


def test_a_held_entry_crosses_a_migration() -> None:
    run = on_refund_1(
        [
            claim("review#1", "ana"),
            migrate(REFUND_2, {}, "pia"),
            ("case.change#1", "approve", "lee"),
        ]
    )
    assert run.state.release == "refund 2"
    assert run.assignees == {"review#1": "ana"}


def test_a_migration_sends_an_entry_to_its_queue_if_its_holder_cant_answer_it_there() -> None:
    # Release 2 has fraud review the refund: Ana, who claimed it as support, can't answer it
    # there, so it goes back to its queue, saying why (brief, D53) (brief, D69).
    by_fraud = refund_2()
    by_fraud["steps"]["review"]["roles"] = ["fraud"]
    run = on_refund_1(
        [
            claim("review#1", "ana"),
            migrate(release_of(by_fraud, 2), {}, "pia"),
            ("case.change#1", "approve", "lee"),
        ]
    )
    assert run.assignees == {}
    assert "review#1 back in its queue: review#1 is answered by fraud, and ana has support" in (
        run.history
    )


def test_a_withdrawn_approvals_holder_follows_its_steps_new_name() -> None:
    # Release 3 renames pay to payment, and changes it, so its open approval is withdrawn; the
    # one asked once the fraud check clears is Sam's again, under the step's new name.
    run = on_refund_1(
        [
            REVIEWED_BY_ANA,
            claim("pay.approval#1", "sam"),
            migrate(REFUND_3, RENAMES, "pia"),
            ("case.change#1", "approve", "lee"),
            ("fraud_check", "clear", "fay"),
        ]
    )
    assert run.assignees == {"payment.approval#2": "sam"}
    assert run.history[-1] == "payment.approval#2 kept for sam"
