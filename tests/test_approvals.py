"""Approvals by several people: `count` on a step's approval (layer 11h2).

Tests go through `parse_case`, `run_case` and what a run reports.
See docs/layers/11-rules.md, 11h2, docs/guides/cases.md, "Several approvers", and brief D47.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from test_retry_rejected import DELIVERED, down_once, generated_definition, refund_retried

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_retry_rejected import FILE as RETRIED_FILE
from test_rules import APPROVED_40, CHECKED_OK, LEADS, SMALL, WITHDRAWS, with_goodwill, withdrawable
from test_set import FILE, with_owed

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import Answered
from ventoux.testing import (
    CATALOG,
    START,
    AnswerRefused,
    close,
    finish,
    later,
    load_definition,
    propose,
    retry,
    run_case,
    send,
)

ROOT = Path(__file__).parent.parent
FOUR_EYES = load_definition(ROOT / "examples" / "refund" / "refund-four-eyes.json")


def four_eyes(**approval: Any) -> dict[str, Any]:
    """A copy of the four-eyes refund, its approval changed by `approval`."""
    definition = copy.deepcopy(FOUR_EYES)
    definition["steps"]["pay"]["approval"].update(approval)
    return definition


# --- Slice 1: the shape ---


@pytest.mark.parametrize("count", [0, -1, "2", Decimal("2.0"), 2.0, True, None])
def test_a_count_that_isnt_a_whole_number_of_at_least_one_is_refused(count: object) -> None:
    # Pydantic would read "2" and 2.0 as 2, and `true` as 1: refused instead, never guessed
    # (brief, D47).
    with pytest.raises(
        CaseInvalid,
        match=(
            r"^steps\.pay\.approval\.count: how many people must approve: a whole number of at "
            r"least 1, such as 2$"
        ),
    ):
        parse_case(four_eyes(count=count))


def test_a_count_is_read() -> None:
    assert parse_case(four_eyes()).steps["pay"].approval.count == 2  # type: ignore[union-attr]
    one = four_eyes()
    del one["steps"]["pay"]["approval"]["count"]
    assert parse_case(one).steps["pay"].approval.count == 1  # type: ignore[union-attr]


# --- Slice 2: one entry collects the answers ---

PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "kim": ["support-lead"],
}
LARGE = {"order_id": "ord-1", "amount": 12000}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 12000})


def test_one_approval_of_two_starts_nothing() -> None:
    run = run_case(
        FOUR_EYES, file=LARGE, answers=[REVIEWED, ("pay", "approve", "sam")], people=PEOPLE
    )
    # The warm-up's three assertions, with the count (learning question 14) (brief, D24).
    assert run.waiting_for == ["approval of pay by support-lead: 1 of 2 given"]
    assert not run.reached("pay")
    assert not run.closed
    assert run.history[-2:] == [
        "asked pay.approval#1: approval of pay by support-lead, from 2 people",
        "sam answered pay.approval#1 approve as support-lead: 1 of 2 given",
    ]


def test_the_second_approval_starts_the_step() -> None:
    run = run_case(
        FOUR_EYES,
        file=LARGE,
        answers=[REVIEWED, ("pay", "approve", "sam"), ("pay.approval#1", "approve", "lee")],
        people=PEOPLE,
    )
    asked = run.history.index(
        "asked pay.approval#1: approval of pay by support-lead, from 2 people"
    )
    assert run.history[asked : asked + 4] == [
        "asked pay.approval#1: approval of pay by support-lead, from 2 people",
        "sam answered pay.approval#1 approve as support-lead: 1 of 2 given",
        "lee answered pay.approval#1 approve as support-lead: 2 of 2 given",
        (
            "scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from "
            "person:ana), key memory/pay#1"
        ),
    ]
    assert run.reached("pay")
    assert run.closed


def test_waiting_for_says_how_many_are_given() -> None:
    run = run_case(FOUR_EYES, file=LARGE, answers=[REVIEWED], people=PEOPLE)
    assert run.waiting_for == ["approval of pay by support-lead: 0 of 2 given"]
    three = four_eyes(count=3)
    run = run_case(
        three,
        file=LARGE,
        answers=[REVIEWED, ("pay", "approve", "sam"), ("pay", "approve", "lee")],
        people=PEOPLE,
    )
    assert run.waiting_for == ["approval of pay by support-lead: 2 of 3 given"]
    assert run.history[-2:] == [
        "sam answered pay.approval#1 approve as support-lead: 1 of 3 given",
        "lee answered pay.approval#1 approve as support-lead: 2 of 3 given",
    ]


def test_a_count_of_one_changes_nothing() -> None:
    # Written or left out, a count of 1 decides, records and reports exactly as before 11h2:
    # every earlier test runs the refund without it (brief, D47).
    plain = load_definition(ROOT / "examples" / "refund" / "refund.json")
    written = copy.deepcopy(plain)
    written["steps"]["pay"]["approval"]["count"] = 1
    small = {"order_id": "ord-1", "amount": 250}
    review = ("review", "approve", "ana", {"approved_amount": 250})
    for definition in (plain, written):
        waiting = run_case(definition, file=small, answers=[review], people=PEOPLE)
        assert waiting.waiting_for == ["approval of pay by support-lead"]
        assert waiting.history[-1] == "asked pay.approval#1: approval of pay by support-lead"
        paid = run_case(
            definition, file=small, answers=[review, ("pay", "approve", "sam")], people=PEOPLE
        )
        assert "sam answered pay.approval#1 approve as support-lead" in paid.history
        assert paid.reached("pay")


# --- Slice 3: distinct people, each someone else ---


def test_one_person_one_answer_on_an_entry() -> None:
    # Sam has approved: a second answer of his, approve or reject, is refused, and the entry is
    # unchanged, so Lee's approval still makes the count (brief, D47).
    half = run_case(
        FOUR_EYES, file=LARGE, answers=[REVIEWED, ("pay", "approve", "sam")], people=PEOPLE
    )
    case = parse_case(FOUR_EYES)
    for outcome in ("approve", "reject"):
        again = Answered("pay.approval#1", outcome, "sam", frozenset(PEOPLE["sam"]), at=START)
        with pytest.raises(
            AnswerRefused, match="^sam has already approved pay.approval#1: it needs 1 more person$"
        ):
            decide(case, CATALOG, half.state, again)
    lee = Answered("pay.approval#1", "approve", "lee", frozenset(PEOPLE["lee"]), at=START)
    after, commands = decide(case, CATALOG, half.state, lee)
    assert after.history[-2] == "lee answered pay.approval#1 approve as support-lead: 2 of 2 given"
    assert [command.entry for command in commands] == ["pay#1"]
    three = run_case(
        four_eyes(count=3), file=LARGE, answers=[REVIEWED, ("pay", "approve", "sam")], people=PEOPLE
    )
    with pytest.raises(
        AnswerRefused, match="^sam has already approved pay.approval#1: it needs 2 more people$"
    ):
        decide(parse_case(four_eyes(count=3)), CATALOG, three.state, again)


def refused(
    definition: dict[str, Any], answers: list[Any], people: dict[str, list[str]], **more: Any
) -> str:
    """Why the last answer of `answers` was refused."""
    with pytest.raises(AnswerRefused) as refusal:
        run_case(definition, answers=answers, people=people, **more)
    return str(refusal.value)


def proposed_four_eyes() -> dict[str, Any]:
    """The four-eyes refund, whose payment a team lead proposes."""
    definition = four_eyes()
    definition["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support-lead"]}
    definition["stays_open"] = True  # nothing else keeps it open while pay waits to be proposed
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate"}, "roles": ["support"]}
    }
    return definition


def test_every_approver_is_someone_else() -> None:
    # The second approver passes every check the first does: D11's exclusions hold for each
    # (brief, D11, D25, D26, D39, D42, D47).
    first = ("pay", "approve", "sam")
    leads = {**PEOPLE, "ana": ["support", "support-lead"]}
    # Whoever's answer flows into the step's inputs.
    assert refused(FOUR_EYES, [REVIEWED, first, ("pay", "approve", "ana")], leads, file=LARGE) == (
        "ana set approved_amount, which pay uses, so cannot approve it"
    )
    # The person who opened the case.
    assert refused(
        FOUR_EYES, [REVIEWED, first, ("pay", "approve", "kim")], PEOPLE, file=LARGE, opened_by="kim"
    ) == ("kim opened the case, so cannot approve its steps")
    # The person who proposed the run.
    assert refused(
        proposed_four_eyes(),
        [REVIEWED, propose("pay", "kim"), first, ("pay", "approve", "kim")],
        PEOPLE,
        file=LARGE,
    ) == ("kim proposed pay, so cannot approve it")
    # Whoever's answer the condition of the rule that started it read.
    goodwill = with_goodwill(CHECKED_OK)
    goodwill["steps"]["goodwill"]["approval"]["count"] = 2
    checked = [APPROVED_40, ("lead_check", "ok", "sam")]
    assert refused(
        goodwill,
        [
            *checked,
            ("goodwill.approval#1", "approve", "lee"),
            ("goodwill.approval#1", "approve", "sam"),
        ],
        LEADS,
        file=SMALL,
    ) == (
        "sam set lead_check.outcome, which decided that start_goodwill#1 started goodwill, so "
        "cannot approve it"
    )
    # Whoever's answer is in a value a rule set.
    owed = with_owed()
    owed["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    owed["steps"]["pay"]["approval"]["count"] = 2
    big = ("review", "approve", "sam", {"approved_amount": 500})
    assert refused(
        owed, [big, ("pay", "approve", "lee"), ("pay", "approve", "sam")], PEOPLE, file=FILE
    ) == ("sam's answer is in owed, which a rule computes and pay uses, so cannot approve it")
    # A retried run: whoever its first start excluded (the retry fix's scenario, with two).
    retried = refund_retried()
    retried["fields"]["limit"] = {"type": "number", "display": {"title": "Limit"}}
    retried["steps"]["set_limit"] = {
        "kind": "task",
        "display": {"title": "Set the limit"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"set": {"display": {"title": "Set"}, "sets": ["limit"]}},
    }
    pay = retried["steps"]["pay"]
    pay |= {"automatic": False, "proposed_by": ["support"]}
    pay["approval"] |= {"when": {">": [{"var": "approved_amount"}, {"var": "limit"}]}, "count": 2}
    retried["stays_open"] = True
    operators = {**PEOPLE, "lee": ["support", "support-lead"], "omar": ["operations"]}
    script = [
        ("review", "approve", "ana", {"approved_amount": 250}),
        propose("pay", "lee"),  # limit unset: pay#1 fails before it starts
        propose("set_limit", "ana"),
        ("set_limit", "set", "ana", {"limit": 100}),
        retry("pay#1", "omar"),  # asks pay.approval#1
        ("pay.approval#1", "approve", "kim"),
        ("pay.approval#1", "approve", "lee"),
    ]
    assert refused(
        retried,
        script,
        operators,
        file=RETRIED_FILE,
        activities={"payments.refund@2": down_once([])},
    ) == ("lee proposed pay, so cannot approve it")


def test_distinct_within_the_entry() -> None:
    # Once the entry is withdrawn, the count starts from nothing, and Sam may approve the new
    # entry: he judges the new values (brief, D25, D47).
    definition = four_eyes()
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    run = run_case(
        definition,
        file=LARGE,
        answers=[
            REVIEWED,
            ("pay", "approve", "sam"),
            propose("review", "ana"),
            ("review", "approve", "ana", {"approved_amount": 15000}),
            ("pay", "approve", "sam"),
            ("pay", "approve", "lee"),
        ],
        people=PEOPLE,
    )
    assert (
        "withdrew pay.approval#1: review started again, with 1 of 2 approvals given" in run.history
    )
    assert "asked pay.approval#2: approval of pay by support-lead, from 2 people" in run.history
    assert "sam answered pay.approval#2 approve as support-lead: 1 of 2 given" in run.history
    assert "lee answered pay.approval#2 approve as support-lead: 2 of 2 given" in run.history
    assert run.reached("pay")


# --- Slice 4: one rejection rejects it ---


def test_one_rejection_rejects_the_whole_approval() -> None:
    # Two must agree, and one is enough to refuse, whatever was approved before (brief, D23, D47).
    run = run_case(
        FOUR_EYES,
        file=LARGE,
        answers=[REVIEWED, ("pay", "approve", "sam"), ("pay", "reject", "lee")],
        people=PEOPLE,
    )
    assert run.history[-3:] == [
        "lee answered pay.approval#1 reject as support-lead",
        "pay#1 won't run: lee rejected pay.approval#1, which 1 of 2 had approved",
        "closed: nothing left to do",
    ]
    assert not run.reached("pay")
    first = run_case(
        FOUR_EYES, file=LARGE, answers=[REVIEWED, ("pay", "reject", "lee")], people=PEOPLE
    )
    assert "pay#1 won't run: lee rejected pay.approval#1" in first.history


def test_a_rejected_run_a_rule_started_ends_its_start() -> None:
    # As an ordinary run: recorded rejected, and what the rule's start kept ends with it
    # (brief, D39, D47).
    goodwill = with_goodwill(CHECKED_OK)
    goodwill["steps"]["goodwill"]["approval"]["count"] = 2
    run = run_case(
        goodwill,
        file=SMALL,
        answers=[
            APPROVED_40,
            ("lead_check", "ok", "sam"),
            ("goodwill.approval#1", "approve", "lee"),
            ("goodwill.approval#1", "reject", "kim"),
        ],
        people={**LEADS, "kim": ["support-lead"]},
    )
    assert "goodwill#1 won't run: kim rejected goodwill.approval#1, which 1 of 2 had approved" in (
        run.history
    )
    assert "goodwill" not in run.state.proposed_by_rules
    assert not run.needs_attention


def test_who_rejected_may_answer_a_later_entry() -> None:
    # Rejecting is a judgement, not a reason to exclude (brief, D11, D47): Lee rejects the first
    # entry, and approves the one asked for the payment proposed again.
    definition = four_eyes()
    definition["steps"]["pay"] |= {"repeatable": True, "proposed_by": ["support"]}
    definition["stays_open"] = True  # so the payment can be proposed again after the rejection
    definition["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    # The rejected entry is closed: nobody answers it again.
    with pytest.raises(AnswerRefused, match="^pay.approval#1 is closed$"):
        run_case(
            definition,
            file=LARGE,
            answers=[REVIEWED, ("pay", "reject", "lee"), ("pay.approval#1", "approve", "sam")],
            people=PEOPLE,
        )
    run = run_case(
        definition,
        file=LARGE,
        answers=[
            REVIEWED,
            ("pay", "reject", "lee"),
            propose("pay", "ana"),
            ("pay", "approve", "lee"),
            ("pay", "approve", "sam"),
        ],
        people=PEOPLE,
    )
    assert "lee answered pay.approval#2 approve as support-lead: 1 of 2 given" in run.history
    assert run.reached("pay")


# --- Slice 5: withdrawn, lapsed and cancelled whole ---

HALF = [REVIEWED, ("pay", "approve", "sam")]  # one approval of two given


def test_a_change_withdraws_every_approval() -> None:
    # Nobody approves values they didn't see, however many approved (brief, D25, D42, D47).
    # A task answered again: in `test_distinct_within_the_entry`. A person changes a value pay reads:
    adjusted = four_eyes()
    adjusted["steps"]["adjust"] = {
        "kind": "task",
        "display": {"title": "Adjust the approved amount"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "requires": ["review"],
        "outcomes": {"adjust": {"display": {"title": "Adjust"}, "sets": ["approved_amount"]}},
    }
    run = run_case(
        adjusted,
        file=LARGE,
        answers=[
            *HALF,
            propose("adjust", "ana"),
            ("adjust", "adjust", "ana", {"approved_amount": 11000}),
        ],
        people=PEOPLE,
    )
    assert "withdrew pay.approval#1: approved_amount changed, with 1 of 2 approvals given" in (
        run.history
    )
    assert run.waiting_for == ["approval of pay by support-lead: 0 of 2 given"]
    with pytest.raises(
        AnswerRefused, match="^pay.approval#1 was withdrawn: approved_amount changed$"
    ):
        run_case(
            adjusted,
            file=LARGE,
            answers=[
                *HALF,
                propose("adjust", "ana"),
                ("adjust", "adjust", "ana", {"approved_amount": 11000}),
                ("pay.approval#1", "approve", "lee"),
            ],
            people=PEOPLE,
        )
    # A rule's `set` changes what is owed.
    owed = with_owed()
    owed["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    owed["steps"]["pay"]["approval"]["count"] = 2
    owed["events"] = {
        "fee_changed": {
            "display": {"title": "The fee changes"},
            "sent_by": {"system": "portal"},
            "payload": {"fee": {"type": "number", "display": {"title": "The new fee"}}},
        }
    }
    owed["rules"]["refigure"] = {
        "display": {"title": "Work out what is owed again"},
        "on": {"event": "fee_changed"},
        "then": {"set": {"owed": {"-": [{"var": "approved_amount"}, {"var": "fee_changed.fee"}]}}},
    }
    big = ("review", "approve", "ana", {"approved_amount": 500})
    run = run_case(
        owed,
        file=FILE,
        answers=[big, ("pay", "approve", "sam"), send("fee_changed", {"fee": 50}, "system:portal")],
        people=PEOPLE,
    )
    assert "withdrew pay.approval#1: owed changed, with 1 of 2 approvals given" in run.history
    assert run.waiting_for == ["approval of pay by support-lead: 0 of 2 given"]


def test_a_given_approval_of_several_lapses_with_its_requirement() -> None:
    # The retry fix's path L, with two approvers: approved by Sam and Lee while the order's status
    # is fetched again, then the review it requires is stopped. Nothing can spend the approval,
    # so it lapses, every approval with it (fix-retry-rejected, decision 5) (brief, D47).
    definition = generated_definition(fresh=True, audited=False)
    definition["steps"]["pay"]["approval"]["count"] = 2
    script = [
        finish("check_order#1"),
        ("review", "approve", "ana", {"approved_amount": 250}),
        later("2d"),
        ("pay.approval#1", "approve", "sam"),
        ("pay.approval#1", "approve", "lee"),  # given: the order's status is fetched again
        propose("review", "ana"),
        finish("check_order#2"),
        propose("hold", "ana"),
        ("hold#1", "hold", "ana"),  # halt stops review#2
    ]
    run = run_case(
        definition,
        {"order_id": "ord-1", "amount": 300},
        script,
        PEOPLE,
        activities=DELIVERED,
        held=["check_order"],
    )
    assert run.history[-2:] == [
        "lapsed pay.approval#1: pay requires review, which hasn't completed",
        "closed: nothing left to do",
    ]
    assert run.state.given == {}


def test_a_stop_or_a_close_cancels_every_approval() -> None:
    # A rule's stop does what a close does, to one step (brief, D10, D40, D47).
    stopping = withdrawable()
    stopping["steps"]["pay"]["approval"]["count"] = 2
    stopping |= {
        "stays_open": True,
        "close_reasons": {"duplicate": {"display": {"title": "Duplicate"}, "roles": ["support"]}},
    }
    review = ("review", "approve", "ana", {"approved_amount": 250})
    run = run_case(
        stopping,
        file={"order_id": "ord-1", "amount": 250},
        answers=[review, ("pay", "approve", "sam"), *WITHDRAWS],
        people=PEOPLE,
    )
    assert "cancelled pay.approval#1: stopped by withdraw#1, with 1 of 2 approvals given" in (
        run.history
    )
    assert run.waiting_for == []
    closing = four_eyes()
    closing["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate"}, "roles": ["support"]}
    }
    run = run_case(closing, file=LARGE, answers=[*HALF, close("duplicate", "ana")], people=PEOPLE)
    assert "cancelled pay.approval#1: closed as duplicate by ana, with 1 of 2 approvals given" in (
        run.history
    )
    assert run.closed


def test_a_lapse_names_every_approver() -> None:
    # Sam and Lee approve 12,000, needed at most a day old; it is three days old, from a person,
    # so pay fails, keeping their approval for a retry (brief, D26). Ana reworks it to 11,000, and
    # the retry finds the inputs changed since both approved them (brief, D11, D47).
    definition = four_eyes()
    definition["steps"]["pay"]["max_age"] = {"approved_amount": "1d"}
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    operators = {**PEOPLE, "omar": ["operations"]}
    run = run_case(
        definition,
        file=LARGE,
        answers=[
            REVIEWED,
            later("3d"),
            ("pay", "approve", "sam"),
            ("pay", "approve", "lee"),
            propose("review", "ana"),
            ("review", "approve", "ana", {"approved_amount": 11000}),
            retry("pay#1", "omar"),
        ],
        people=operators,
    )
    [failed] = [r for r in run.state.runs if r.step == "pay"]
    assert failed.approved is not None and failed.approved.approvers == ("sam", "lee")
    assert run.needs_attention == [
        "pay#1: the inputs of pay changed since sam and lee approved them: a new approval is needed"
    ]


# --- Slice 6: the sheet, the readings and the stories ---


def test_the_sheet_says_who_has_approved() -> None:
    # Sam, opening the sheet again, sees he has approved; Lee sees one more is needed. The facts
    # are as before (brief, D18, D47).
    half = run_case(FOUR_EYES, file=LARGE, answers=HALF, people=PEOPLE)
    sheet = half.approval_sheet("pay.approval#1", ["support-lead"], START)
    assert sheet.approved_by == ("sam",)
    assert sheet.needed == 1
    assert sheet.lines[0].startswith("Amount approved: 12000, obtained")
    none_yet = run_case(FOUR_EYES, file=LARGE, answers=[REVIEWED], people=PEOPLE)
    sheet = none_yet.approval_sheet("pay.approval#1", ["support-lead"], START)
    assert (sheet.approved_by, sheet.needed) == ((), 2)
    plain = load_definition(ROOT / "examples" / "refund" / "refund.json")
    one = run_case(
        plain,
        file={"order_id": "ord-1", "amount": 250},
        answers=[("review", "approve", "ana", {"approved_amount": 250})],
        people=PEOPLE,
    )
    sheet = one.approval_sheet("pay.approval#1", ["support-lead"], START)
    assert (sheet.approved_by, sheet.needed) == ((), 1)


GUIDE = (ROOT / "docs" / "guides" / "cases.md").read_text()
SECTION = GUIDE.split("## Several approvers\n")[1].split("\n## ")[0]


def guide_blocks(language: str) -> list[str]:
    """The section's code blocks in `language` (`""` for plain ones), in order."""
    parts = SECTION.split("```")
    return [
        part.removeprefix(language + "\n")
        for part in parts[1::2]
        if part.split("\n")[0] == language
    ]


def test_the_guides_several_approvers_are_the_engines() -> None:
    # Our own documentation, run so it can't drift from the code; never a definition (data).
    [shown] = guide_blocks("json")
    approval = json.loads("{" + shown + "}", parse_float=Decimal)["approval"]
    assert approval == FOUR_EYES["steps"]["pay"]["approval"]
    [history] = guide_blocks("")
    run = run_case(
        FOUR_EYES,
        file=LARGE,
        answers=[REVIEWED, ("pay", "approve", "sam"), ("pay.approval#1", "approve", "lee")],
        people=PEOPLE,
    )
    lines = history.splitlines()
    first = run.history.index(lines[0])
    assert run.history[first : first + len(lines)] == lines
    [code] = guide_blocks("python")
    exec(code, {"run_case": run_case, "refund_four_eyes": FOUR_EYES, "PEOPLE": PEOPLE})  # noqa: S102
    # The refusals and lines the prose quotes are the engine's.
    for said in (
        "sam has already approved pay.approval#1: it needs 1 more person",
        "pay#1 won't run: lee rejected pay.approval#1, which 1 of 2 had approved",
        "withdrew pay.approval#1: review started again, with 1 of 2 approvals given",
    ):
        assert f"`{said}`" in " ".join(SECTION.split()), said


SECRET_ORDER = "ORD-7-SECRET"  # an order, and an amount, to look for where they mustn't be
SECRET_AMOUNT = 12345


def test_no_approval_line_quotes_a_value_from_the_case_file() -> None:
    # Every line 11h2 adds names entries, steps, roles, people and counts, never a value
    # (brief, D31, D47).
    definition = four_eyes()
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    file = {"order_id": SECRET_ORDER, "amount": SECRET_AMOUNT}
    review = ("review", "approve", "ana", {"approved_amount": SECRET_AMOUNT})
    runs = [
        run_case(definition, file=file, answers=[review, ("pay", "approve", "sam")], people=PEOPLE),
        run_case(
            definition,
            file=file,
            answers=[review, ("pay", "approve", "sam"), ("pay", "reject", "lee")],
            people=PEOPLE,
        ),
        run_case(
            definition,
            file=file,
            answers=[review, ("pay", "approve", "sam"), propose("review", "ana")],
            people=PEOPLE,
        ),
    ]
    said = [line for run in runs for line in [*run.history, *run.waiting_for, *run.needs_attention]]
    sheet = runs[0].approval_sheet("pay.approval#1", ["support-lead"], START)
    said += [*sheet.approved_by]
    with pytest.raises(AnswerRefused) as refused:
        run_case(
            definition,
            file=file,
            answers=[review, ("pay", "approve", "sam"), ("pay", "approve", "sam")],
            people=PEOPLE,
        )
    said.append(str(refused.value))
    approval_lines = [line for line in said if "approv" in line and "opened" not in line]
    assert approval_lines
    for line in approval_lines:
        assert SECRET_ORDER not in line and str(SECRET_AMOUNT) not in line, line
