"""The case layer: a case definition, and the runtime that runs it in memory (layer 8a).

Tests go through `parse_case` and `run_case`, and read what a run reports.
See docs/layers/08-case.md and docs/guides/cases.md.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseState, Opened
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, RetryPolicy, Timeouts
from ventoux.core.contract import Display as ContractDisplay
from ventoux.core.output_sources import source
from ventoux.core.policy import only_from
from ventoux.testing import (
    CATALOG,
    AnswerRefused,
    CaseRefused,
    CloseRefused,
    Outcome,
    ProposalRefused,
    RetryRefused,
    close,
    finish,
    load_definition,
    propose,
    retry,
    run_case,
)

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")


def refund(**changes: Any) -> dict[str, Any]:
    """A copy of the quickstart's refund, to change."""
    definition = copy.deepcopy(REFUND)
    definition.update(changes)
    return definition


def without(definition: dict[str, Any], *path: str) -> dict[str, Any]:
    """`definition` with the key at `path` removed."""
    inner = definition
    for key in path[:-1]:
        inner = inner[key]
    del inner[path[-1]]
    return definition


# --- Slice 0: the case definition ---


def test_the_quickstarts_refund_is_read() -> None:
    case = parse_case(REFUND)
    assert list(case.steps) == ["review", "pay"]
    assert case.display.title == "Customer refund"


@pytest.mark.parametrize(
    "path",
    [
        ("display",),
        ("fields", "amount", "display"),
        ("steps", "pay", "display"),
        ("steps", "review", "outcomes", "reject", "display"),
        ("steps", "pay", "approval", "display"),
    ],
)
def test_everything_people_read_has_a_title(path: tuple[str, ...]) -> None:
    # A business title on everything people read (brief, D1): a step without one is refused.
    with pytest.raises(CaseInvalid, match=f"^{'.'.join(path)}: required$"):
        parse_case(without(refund(), *path))


def test_a_title_is_never_empty() -> None:
    definition = refund()
    definition["steps"]["pay"]["display"]["title"] = ""
    with pytest.raises(CaseInvalid, match="steps.pay.display.title: "):
        parse_case(definition)


def changed(change: str) -> dict[str, Any]:
    """The refund with one of the changes below made."""
    definition = refund()
    steps = definition["steps"]
    if change == "kind":
        steps["pay"]["kind"] = "script"
    elif change == "sequence":
        definition["sequence"] = ["review", "pya"]
    elif change == "requires":
        steps["pay"]["requires"] = ["reviwe"]
    elif change == "milestone":
        definition["milestones"] = {"review": {"display": {"title": "Reviewed"}}}
    elif change == "reaches":
        steps["pay"]["reaches"] = ["paid"]
    elif change == "sets":
        steps["review"]["outcomes"]["approve"]["sets"] = ["approved_amout"]
    return definition


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            "kind",
            "steps.pay.kind: a step is a task, an activity, a plan or a workflow, and this one is 'script'",
        ),
        ("sequence", "sequence: pya is not a step"),
        ("requires", "steps.pay.requires: reviwe is neither a milestone nor a step"),
        ("milestone", "milestones.review: a milestone is not named like a step"),
        ("reaches", "steps.pay.reaches: paid is not a milestone"),
        ("sets", "steps.review.outcomes.approve.sets: approved_amout is not a field"),
    ],
)
def test_a_definition_that_names_nothing_is_refused(change: str, message: str) -> None:
    with pytest.raises(CaseInvalid, match=f"^{message}$"):
        parse_case(changed(change))


def test_a_step_nobody_can_start_is_refused() -> None:
    manual = refund()
    manual["steps"]["pay"]["automatic"] = False
    with pytest.raises(
        CaseInvalid,
        match="^steps.pay: a step that doesn't start by itself names proposed_by, who may "
        "propose it$",
    ):
        parse_case(manual)
    again = refund()
    again["steps"]["review"]["repeatable"] = True
    with pytest.raises(
        CaseInvalid,
        match="^steps.review: a repeatable step runs again only when proposed: name "
        "proposed_by, who may propose it$",
    ):
        parse_case(again)


def test_an_expression_the_engine_does_not_know_is_refused_when_read() -> None:
    definition = refund()
    definition["steps"]["pay"]["approval"]["when"] = {"now": []}
    with pytest.raises(CaseInvalid, match="steps.pay.approval.when: `now` is not an operator"):
        parse_case(definition)


# --- Slice 1: the runtime replaces the tracer's walk ---

# Who has which role: the test plays the Ventoux API (brief, D22).
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"]}


def test_a_case_waiting_for_its_review_says_so() -> None:
    # Design question 14 (brief, D24): the tracer crashed when nobody had answered the review.
    run = run_case(REFUND, file={"order_id": "ord-1", "amount": 250}, answers=[], people=PEOPLE)
    assert run.waiting_for == ["review by support"]
    assert not run.reached("review")
    assert not run.closed


# --- Slice 2: the case file ---


@pytest.mark.parametrize(
    ("file", "message"),
    [
        (
            {"order_id": "ord-1", "amount": 250, "approved_amount": 250},
            "approved_amount is set by a person in review, never given at the opening",
        ),
        (
            {"order_id": "ord-1", "amount": 250, "colour": "red"},
            "colour is not a field of refund: its fields are amount, approved_amount and order_id",
        ),
        (
            {"order_id": 1001, "amount": 40},
            "order_id is a reference to orders, and the opening gives a number",
        ),
    ],
)
def test_the_opening_gives_the_declared_fields_of_their_types(
    file: dict[str, Any], message: str
) -> None:
    with pytest.raises(CaseRefused, match=f"^{message}$"):
        run_case(REFUND, file=file, answers=[], people=PEOPLE)


def test_a_float_is_refused_never_guessed() -> None:
    # A binary float may already have lost its exact value (brief, D20).
    with pytest.raises(
        CaseRefused, match="^amount is a number, and the opening gives a binary float$"
    ):
        run_case(REFUND, file={"order_id": "ord-1", "amount": 0.1}, answers=[], people=PEOPLE)
    with pytest.raises(
        AnswerRefused, match="^approved_amount is a number, and the answer gives a binary float$"
    ):
        run_case(
            REFUND,
            file={"order_id": "ord-1", "amount": 40},
            answers=[("review", "approve", "ana", {"approved_amount": 40.5})],
            people=PEOPLE,
        )


def test_opening_values_say_who_gave_them() -> None:
    small = {"order_id": "ord-1", "amount": 40}
    review = [("review", "approve", "ana", {"approved_amount": 40})]
    by_a_system = run_case(REFUND, file=small, answers=review, people=PEOPLE)
    assert "opened by system:opener, with amount and order_id" in by_a_system.history
    by_lee = run_case(REFUND, file=small, answers=review, people=PEOPLE, opened_by="lee")
    assert "opened by lee, with amount and order_id" in by_lee.history
    assert (
        "scheduled pay#1: payments.refund@2 (order_id from person:lee; amount from person:ana), "
        "key memory/pay#1" in by_lee.history
    )
    # Who opened it is written one way, as who answers (brief, D22).
    with pytest.raises(CaseRefused, match="'Lee' is not written as a person's identifier"):
        run_case(REFUND, file=small, answers=review, people=PEOPLE, opened_by="Lee")


def test_a_forms_values_land_in_the_case_file() -> None:
    # A field declared untrusted keeps its mark when a person's form sets it (layer 7's review):
    # the form adds who answered, and payments.refund@2 takes no untrusted amount.
    definition = refund()
    definition["fields"]["approved_amount"]["source"] = "untrusted:customer"
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 40},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
    )
    # Since 8b a refused input fails the step, and the case needs attention.
    [failed] = run.needs_attention
    assert failed.startswith("pay#1: payments.refund@2 takes amount only from")
    assert not run.reached("pay")


# --- Slice 3: requires, proposals, milestones ---


def with_check_order() -> dict[str, Any]:
    """The refund, with the guide's step a person proposes: look the order up again."""
    definition = refund()
    definition["steps"]["check_order"] = {
        "kind": "activity",
        "display": {"title": "Look the order up again"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "automatic": False,
        "proposed_by": ["support"],
        "requires": ["review"],
    }
    return definition


def reworkable() -> dict[str, Any]:
    """The refund, whose review a person in support may send back for rework."""
    definition = refund()
    definition["steps"]["review"]["repeatable"] = True
    definition["steps"]["review"]["proposed_by"] = ["support"]
    return definition


LARGE = {"order_id": "ord-1", "amount": 250}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 250})
SMALL = {"order_id": "ord-1", "amount": 40}
SMALL_REVIEW = ("review", "approve", "ana", {"approved_amount": 40})
OPERATORS = {**PEOPLE, "omar": ["operations"]}


@pytest.mark.parametrize(
    ("definition", "script", "message"),
    [
        (
            with_check_order,
            [propose("check_order", "ana")],
            "check_order requires review, which hasn't completed",
        ),
        (
            with_check_order,
            [REVIEWED, propose("check_order", "eve")],
            "check_order is proposed by support, and eve has no role",
        ),
        (
            with_check_order,
            [REVIEWED, propose("pay", "ana")],
            "pay starts by itself: nobody proposes it",
        ),
        (reworkable, [propose("review", "ana")], "review is already running: review#1"),
        (
            with_check_order,
            [REVIEWED, propose("check_order", "ana"), propose("check_order", "ana")],
            "check_order has run, and is not repeatable",
        ),
        (
            with_check_order,
            [REVIEWED, propose("check_ordr", "ana")],
            "check_ordr is not a step of refund",
        ),
    ],
)
def test_a_proposal_is_checked_against_admission(
    definition: Any, script: list[Any], message: str
) -> None:
    with pytest.raises(ProposalRefused, match=f"^{message}$"):
        run_case(definition(), file=LARGE, answers=script, people=PEOPLE)


def test_a_proposal_whose_condition_is_false_is_refused() -> None:
    definition = with_check_order()
    definition["steps"]["check_order"]["when"] = {"==": [{"var": "review.outcome"}, "reject"]}
    with pytest.raises(
        ProposalRefused, match='^check_order doesn\'t run now: review.outcome = "reject" is false$'
    ):
        run_case(
            definition,
            file=LARGE,
            answers=[REVIEWED, propose("check_order", "ana")],
            people=PEOPLE,
        )


def test_a_proposal_whose_condition_cannot_be_read_is_refused() -> None:
    # Fail closed: nothing starts on a condition the engine can't read.
    definition = with_check_order()
    definition["steps"]["check_order"]["requires"] = []
    definition["steps"]["check_order"]["when"] = {">": [{"var": "approved_amount"}, 0]}
    with pytest.raises(
        ProposalRefused, match="^check_order's condition approved_amount > 0 can't be evaluated"
    ):
        run_case(definition, file=LARGE, answers=[propose("check_order", "ana")], people=PEOPLE)


def test_a_proposal_names_its_person_one_way() -> None:
    with pytest.raises(ProposalRefused, match="'Ana' is not written as a person's identifier"):
        run_case(
            with_check_order(),
            file=LARGE,
            answers=[REVIEWED, propose("check_order", "Ana")],
            people={**PEOPLE, "Ana": ["support"]},
        )


def test_a_closed_case_takes_no_more_answers() -> None:
    with pytest.raises(AnswerRefused, match="^the case is closed: nothing waits for an answer$"):
        run_case(
            REFUND,
            file=LARGE,
            answers=[("review", "reject", "ana"), ("review", "approve", "ana")],
            people=PEOPLE,
        )


def test_a_proposed_step_runs() -> None:
    run = run_case(
        with_check_order(),
        file=LARGE,
        answers=[REVIEWED, propose("check_order", "ana")],
        people=PEOPLE,
    )
    assert run.reached("check_order")
    assert "ana proposed check_order as support" in run.history
    assert run.waiting_for == ["approval of pay by support-lead"]


def test_a_step_starts_by_itself_once() -> None:
    # The review is done and the case waits for the approval: the review doesn't open again by
    # itself, though it is repeatable; a person proposes it.
    run = run_case(reworkable(), file=LARGE, answers=[REVIEWED], people=PEOPLE)
    assert run.waiting_for == ["approval of pay by support-lead"]


def test_a_condition_on_an_unset_field_stops_the_case() -> None:
    # Without `sequence`, pay's condition is read before anyone answered the review: a missing
    # value is an error, never "false" (fail closed).
    definition = refund(sequence=[])
    run = run_case(definition, file=LARGE, answers=[], people=PEOPLE)
    # Since 8b the step fails and the case needs attention; the review still opens.
    [failed] = run.needs_attention
    assert failed.startswith(
        "pay#1: pay's condition review.outcome = \"approve\" can't be evaluated"
    )
    assert run.waiting_for == ["review by support"]
    assert not run.closed


def test_a_milestone_admits_what_requires_it() -> None:
    definition = refund(sequence=[])
    definition["milestones"] = {
        "approved": {"display": {"title": "Refund approved"}},
        "paid": {"display": {"title": "Refund paid"}},
    }
    definition["steps"]["review"]["outcomes"]["approve"]["reaches"] = ["approved"]
    definition["steps"]["pay"]["requires"] = ["approved"]
    definition["steps"]["pay"]["reaches"] = ["paid"]
    del definition["steps"]["pay"]["when"]
    small = {"order_id": "ord-1", "amount": 40}
    run = run_case(
        definition,
        file=small,
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
    )
    assert run.reached("pay")
    assert run.history.index("reached approved") < run.history.index("reached paid")
    rejected = run_case(
        definition, file=small, answers=[("review", "reject", "ana")], people=PEOPLE
    )
    assert not rejected.reached("pay")
    assert rejected.closed


# --- Slice 4: parallel steps ---


def test_steps_admitted_together_run_together() -> None:
    # Simple parallelism (brief, D2): nothing orders the two checks, so both open at once.
    definition = refund()
    definition["steps"]["check_documents"] = {
        "kind": "task",
        "display": {"title": "Check the customer's documents"},
        "roles": ["support"],
        "outcomes": {"complete": {"display": {"title": "Documents complete"}}},
    }
    small = {"order_id": "ord-1", "amount": 40}
    opened = run_case(definition, file=small, answers=[], people=PEOPLE)
    assert opened.waiting_for == ["review by support", "check_documents by support"]
    one = run_case(
        definition,
        file=small,
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
    )
    assert one.reached("pay")
    assert one.waiting_for == ["check_documents by support"]
    assert not one.closed
    both = run_case(
        definition,
        file=small,
        answers=[
            ("check_documents", "complete", "ana"),
            ("review", "approve", "ana", {"approved_amount": 40}),
        ],
        people=PEOPLE,
    )
    assert both.closed


# --- Slice 5: approvals in a case ---


def test_the_opener_cannot_approve() -> None:
    # Lee opened the case and is a team lead; Ana reviewed. Lee is excluded all the same
    # (brief, D11): the person who opened a case approves none of its steps.
    with pytest.raises(AnswerRefused, match="^lee opened the case, so cannot approve its steps$"):
        run_case(
            REFUND,
            file=LARGE,
            answers=[REVIEWED, ("pay", "approve", "lee")],
            people=PEOPLE,
            opened_by="lee",
        )


REWORKED = [
    REVIEWED,
    propose("review", "ana"),
    ("review", "approve", "ana", {"approved_amount": 900}),
]


def test_an_entry_is_closed_or_not_open() -> None:
    # Layer 8c: on Temporal an answer names its entry, and its refusal says which it was: an
    # entry that has been open is closed (a double click); one that hasn't, isn't open.
    reworked = [REVIEWED, propose("review", "ana")]
    with pytest.raises(AnswerRefused, match="^review#1 is closed$"):
        run_case(
            reworkable(),
            file=LARGE,
            answers=[*reworked, ("review#1", "approve", "ana", {"approved_amount": 900})],
            people=PEOPLE,
        )
    with pytest.raises(AnswerRefused, match="^review#3 isn't open$"):
        run_case(
            reworkable(),
            file=LARGE,
            answers=[*reworked, ("review#3", "approve", "ana", {"approved_amount": 900})],
            people=PEOPLE,
        )
    # An approval's entry, the same: Sam's double click while the payment runs.
    with pytest.raises(AnswerRefused, match="^pay.approval#1 is closed$"):
        run_case(
            REFUND,
            file=LARGE,
            answers=[
                REVIEWED,
                ("pay.approval#1", "approve", "sam"),
                ("pay.approval#1", "approve", "sam"),
            ],
            people=PEOPLE,
            held=["pay"],
        )


def test_an_open_approval_follows_the_case_file() -> None:
    # Sam reads the sheet for 250 while the review is sent back and reworked to 900 (brief, D25).
    with pytest.raises(AnswerRefused, match="^pay.approval#1 was withdrawn: review started again$"):
        run_case(
            reworkable(),
            file=LARGE,
            answers=[*REWORKED, ("pay.approval#1", "approve", "sam")],
            people=PEOPLE,
        )
    run = run_case(
        reworkable(), file=LARGE, answers=[*REWORKED, ("pay", "approve", "sam")], people=PEOPLE
    )
    rework = run.history.index("ana proposed review as support")
    assert run.history[rework : rework + 6] == [
        "ana proposed review as support",
        "started review#2: waiting for approve or reject by support",
        "withdrew pay.approval#1: review started again",
        "ana answered review#2 approve as support, setting approved_amount",
        "review#2 done",
        "asked pay.approval#2: approval of pay by support-lead",
    ]
    assert "sam answered pay.approval#2 approve as support-lead" in run.history
    assert run.reached("pay")


def test_an_open_approval_is_withdrawn_when_a_value_it_reads_changes() -> None:
    # A team lead adjusts the amount while the approval is open: the step is still admitted, but
    # what it would pay changed, so the approval asked for 250 approves nothing.
    definition = refund()
    definition["steps"]["adjust"] = {
        "kind": "task",
        "display": {"title": "Adjust the approved amount"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "requires": ["review"],
        "outcomes": {"adjust": {"display": {"title": "Adjust"}, "sets": ["approved_amount"]}},
    }
    script = [
        REVIEWED,
        propose("adjust", "ana"),
        ("adjust", "adjust", "ana", {"approved_amount": 260}),
        ("pay.approval#1", "approve", "sam"),
    ]
    with pytest.raises(
        AnswerRefused, match="^pay.approval#1 was withdrawn: approved_amount changed$"
    ):
        run_case(definition, file=LARGE, answers=script, people=PEOPLE)


def test_a_rework_below_the_threshold_needs_no_approval() -> None:
    run = run_case(
        reworkable(),
        file=LARGE,
        answers=[
            REVIEWED,
            propose("review", "ana"),
            ("review", "approve", "ana", {"approved_amount": 50}),
        ],
        people=PEOPLE,
    )
    assert run.reached("pay")
    assert run.closed
    assert not any(line.startswith("asked pay.approval#2") for line in run.history)


def test_an_approval_unlocks_one_run_with_its_own_key() -> None:
    run = run_case(REFUND, file=LARGE, answers=[REVIEWED, ("pay", "approve", "sam")], people=PEOPLE)
    scheduled = [line for line in run.history if line.startswith("scheduled pay")]
    assert scheduled == [
        (
            "scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from "
            "person:ana), key memory/pay#1"
        )
    ]
    assert run.closed


def test_a_high_risk_step_with_no_approval_stops() -> None:
    # Checked at runtime, depending on nothing case validation (layer 10) will do.
    definition = refund()
    del definition["steps"]["pay"]["approval"]
    run = run_case(definition, file=LARGE, answers=[REVIEWED], people=PEOPLE)
    assert run.needs_attention == ["pay#1: payments.refund@2 is high risk, and pay has no approval"]
    assert not run.reached("pay")


# --- Slice 6: the guide, run as written ---

# The guide, without cases on Temporal, whose examples run on Temporal's test server
# (tests/test_temporal_case.py).
NOT_RUN_HERE = ("## Running a case on Temporal\n",)


def without_sections(text: str, headings: tuple[str, ...]) -> str:
    """`text` without each section that starts with one of `headings`, up to the next one."""
    for heading in headings:
        if heading in text:
            before, after = text.split(heading, 1)
            rest = after.split("\n## ", 1)
            text = before + ("## " + rest[1] if len(rest) > 1 else "")
    return text


GUIDE = without_sections(
    (Path(__file__).parent.parent / "docs" / "guides" / "cases.md").read_text(), NOT_RUN_HERE
)


def blocks(language: str) -> list[str]:
    """The guide's code blocks in `language` (`""` for plain ones), in order."""
    found: list[str] = []
    opened: str | None = None  # the language of the block being read, while inside one
    body: list[str] = []
    for line in GUIDE.splitlines():
        if not line.startswith("```"):
            body.append(line)
        elif opened is None:
            opened, body = line.removeprefix("```"), []
        else:
            if opened == language:
                found.append("\n".join(body) + "\n")
            opened = None
    return found


def guide_json(index: int) -> dict[str, Any]:
    """The guide's JSON block `index`; a fragment (`"name": {...}`) is read as an object."""
    text = blocks("json")[index]
    fragment = text if text.lstrip().startswith("{") else "{" + text + "}"
    loaded: dict[str, Any] = json.loads(fragment, parse_float=Decimal)
    return loaded


def guide_seen_by_support() -> dict[str, Any]:
    """The guide's refund, its approved amount seen only by support (the case data guide)."""
    refund = guide_json(0)
    refund["fields"]["approved_amount"]["visible_to"] = ["support"]
    return refund


def guide_refund_with_rework() -> dict[str, Any]:
    """The guide's refund, its review sent back for rework with the guide's two keys."""
    definition = guide_json(0)
    definition["steps"]["review"].update(guide_json(2))
    return definition


def test_the_guides_refund_is_the_quickstarts() -> None:
    assert guide_json(0) == REFUND


def test_the_guides_examples_run_as_written() -> None:
    # Our own documentation, run so it can't drift from the code; never a definition (data).
    namespace: dict[str, Any] = {
        "run_case": run_case,
        "propose": propose,
        "refund": guide_json(0),
        "refund_with_rework": guide_refund_with_rework(),
        "retry": retry,
        "PEOPLE": OPERATORS,
        "refund_with_plan": guide_refund_with_plan(),
        "refund_order": refund_order(),
    }
    for code in blocks("python"):
        exec(code, namespace)  # noqa: S102 -- our guide, as in layer 7


def test_the_guides_histories_are_what_the_engine_records() -> None:
    plain = blocks("")
    paid = run_case(
        guide_json(0), file=LARGE, answers=[REVIEWED, ("pay", "approve", "sam")], people=PEOPLE
    )
    assert plain[0].splitlines() == paid.history
    # The rework: the guide's lines appear one after the other in the run's history.
    reworked = run_case(
        guide_refund_with_rework(),
        file=LARGE,
        answers=[*REWORKED, ("pay", "approve", "sam")],
        people=PEOPLE,
    )
    declined = run_case(
        guide_with(3),  # the guide's step reacting to a declined refund
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={"payments.refund@2": gives("declined")},
    )
    closing = run_case(
        guide_with_close_reasons(),
        file=SMALL,
        answers=[SMALL_REVIEW, close("duplicate", "ana"), finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    small = run_case(guide_json(0), file=SMALL, answers=[SMALL_REVIEW], people=PEOPLE)
    shown_runs = (
        (plain[1], reworked),
        (plain[2], declined),
        (plain[3], small),
        (plain[4], closing),
    )
    for shown, run in shown_runs:
        lines = shown.splitlines()
        first = run.history.index(lines[0])
        assert run.history[first : first + len(lines)] == lines


def test_the_guides_proposed_step_runs() -> None:
    definition = guide_json(0)
    definition["steps"].update(guide_json(1))
    run = run_case(
        definition, file=LARGE, answers=[REVIEWED, propose("check_order", "ana")], people=PEOPLE
    )
    assert run.reached("check_order")


def guide_with(index: int) -> dict[str, Any]:
    """The guide's refund, with the step in its JSON block `index` added."""
    definition = guide_json(0)
    definition["steps"].update(guide_json(index))
    return definition


PLANS_GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "plans.md"


def refund_order() -> dict[str, Any]:
    """The plans guide's `refund-order` plan, its first JSON block, as stored data."""
    example = PLANS_GUIDE.read_text().split("```json\n")[1].split("```")[0]
    plan: dict[str, Any] = json.loads(example, parse_float=Decimal)
    return plan


def guide_refund_with_plan() -> dict[str, Any]:
    """The guide's refund, its payment made by the guide's plan step (JSON block 5)."""
    definition = guide_json(0)
    del definition["steps"]["pay"], definition["sequence"]
    definition["steps"].update(guide_json(5))
    return definition


def test_the_guides_plan_step_runs_as_written() -> None:
    run = run_case(
        guide_refund_with_plan(),
        file=LARGE,
        answers=[REVIEWED],
        people=PEOPLE,
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "approve", "sam")]},
    )
    shown = blocks("")[5].splitlines()
    assert run.history[-len(shown) :] == shown


def guide_with_close_reasons() -> dict[str, Any]:
    """The guide's refund, with the guide's close reason."""
    return guide_json(0) | guide_json(4)


def refusal(run: Any) -> str:
    """What the engine says when it refuses `run`."""
    try:
        run()
    except (AnswerRefused, ProposalRefused, CaseRefused, RetryRefused, CloseRefused) as refused:
        return str(refused)
    raise AssertionError("nothing was refused")


def with_guides_check_order() -> dict[str, Any]:
    definition = guide_json(0)
    definition["steps"].update(guide_json(1))
    return definition


# Each "Refused when" row of the guide's table, and a run that is refused that way.
GUIDE_REFUSALS: dict[str, Any] = {
    "the person has none of the task's roles": lambda: run_case(
        guide_json(0),
        file=LARGE,
        answers=[("review", "approve", "eve", {"approved_amount": 1})],
        people=PEOPLE,
    ),
    "the person opened the case": lambda: run_case(
        guide_json(0),
        file=LARGE,
        answers=[("review", "approve", "sam", {"approved_amount": 250}), ("pay", "approve", "ana")],
        people={"ana": ["support-lead"], "sam": ["support"]},
        opened_by="ana",
    ),
    "the approval was withdrawn": lambda: run_case(
        guide_refund_with_rework(),
        file=LARGE,
        answers=[*REWORKED, ("pay.approval#1", "approve", "sam")],
        people=PEOPLE,
    ),
    "a proposed step's requirements aren't met": lambda: run_case(
        with_guides_check_order(),
        file=LARGE,
        answers=[propose("check_order", "ana")],
        people=PEOPLE,
    ),
    "nobody proposes a step that starts by itself": lambda: run_case(
        guide_json(0), file=LARGE, answers=[REVIEWED, propose("pay", "ana")], people=PEOPLE
    ),
    "the opening gives a field a person sets": lambda: run_case(
        guide_json(0), file={**LARGE, "approved_amount": 250}, answers=[], people=PEOPLE
    ),
    "the person retrying has no operating role": lambda: run_case(
        guide_json(0),
        file=SMALL,
        answers=[SMALL_REVIEW, retry("pay#1", "ana")],
        people=OPERATORS,
        activities={"payments.refund@2": unreachable},
    ),
    "the run hasn't failed": lambda: run_case(
        guide_json(0),
        file=SMALL,
        answers=[SMALL_REVIEW, retry("pay#1", "omar")],
        people=OPERATORS,
        held=["pay"],
    ),
    "the close reason isn't declared": lambda: run_case(
        guide_with_close_reasons(), file=LARGE, answers=[close("spam", "ana")], people=PEOPLE
    ),
    "the person closing has none of the reason's roles": lambda: run_case(
        guide_with_close_reasons(),
        file=LARGE,
        answers=[close("duplicate", "eve")],
        people=PEOPLE,
    ),
    "the case is closing": lambda: run_case(
        guide_with_close_reasons(),
        file=SMALL,
        answers=[SMALL_REVIEW, close("duplicate", "ana"), ("review", "approve", "ana")],
        people=PEOPLE,
        held=["pay"],
    ),
    "the approver can't see a value the step reads": lambda: run_case(
        guide_seen_by_support(),
        file=LARGE,
        answers=[REVIEWED, ("pay", "approve", "lee")],
        people=PEOPLE,
    ),
}


def guide_refusal_rows() -> list[tuple[str, str]]:
    """The rows of the guide's table "Refused when | Example", code unquoted."""
    table = GUIDE.split("| Refused when | Example |")[1].split("\n\n")[0]
    rows = [line.split("|") for line in table.splitlines()[2:] if line.startswith("| ")]
    return [(when.strip(), example.strip().strip("`")) for _, when, example, _ in rows]


@pytest.mark.parametrize(("when", "example"), guide_refusal_rows())
def test_the_guides_refusals_are_what_the_engine_says(when: str, example: str) -> None:
    assert when in GUIDE_REFUSALS, f"the guide's row {when!r} has no test"
    assert refusal(GUIDE_REFUSALS[when]) == example


def test_every_refusal_in_the_guide_is_tested() -> None:
    assert [when for when, _ in guide_refusal_rows()] == list(GUIDE_REFUSALS)


# --- Tutor review: the person who proposes a step can't approve it ---


def with_goodwill() -> dict[str, Any]:
    """The refund, with an extra refund a team lead may propose: high risk, approved by one."""
    definition = refund()
    definition["steps"]["goodwill"] = {
        "kind": "activity",
        "display": {"title": "Refund a goodwill gesture"},
        "activity": "payments.refund@2",
        "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
        "automatic": False,
        "proposed_by": ["support-lead"],
        "requires": ["review"],
        "approval": {
            "roles": ["support-lead"],
            "display": {"reason": "A goodwill refund needs a team lead"},
        },
    }
    return definition


def test_the_person_who_proposed_a_step_cannot_approve_it() -> None:
    # Sam asks for the payment; someone else approves it (curriculum, layer 7; brief, D25). The
    # refund waits for its own approval, so the case is open when Sam proposes.
    proposed = [REVIEWED, propose("goodwill", "sam")]
    with pytest.raises(AnswerRefused, match="^sam proposed goodwill, so cannot approve it$"):
        run_case(
            with_goodwill(),
            file=LARGE,
            answers=[*proposed, ("goodwill", "approve", "sam")],
            people=PEOPLE,
        )
    waiting = run_case(with_goodwill(), file=LARGE, answers=proposed, people=PEOPLE)
    assert waiting.waiting_for == [
        "approval of pay by support-lead",
        "approval of goodwill by support-lead",
    ]
    paid = run_case(
        with_goodwill(),
        file=LARGE,
        answers=[*proposed, ("goodwill", "approve", "lee")],
        people=PEOPLE,
    )
    assert [line for line in paid.history if line.startswith("scheduled goodwill")] == [
        (
            "scheduled goodwill#1: payments.refund@2 (order_id from system:opener; amount from "
            "system:opener), key memory/goodwill#1"
        )
    ]
    assert paid.waiting_for == ["approval of pay by support-lead"]


# === Layer 8b ===

# --- Slice 0: decide never changes the state passed in (carried from 8a) ---


def test_decide_never_changes_the_state_passed_in() -> None:
    # A driver keeps the state it had if an event is refused part-way, and on Temporal (8c) a
    # refused answer is recorded and the case runs on: `decide` works on its own copy.
    case = parse_case(REFUND)
    opened, _ = decide(
        case, CATALOG, CaseState("t"), Opened({"order_id": "o", "amount": Decimal(250)}, None)
    )
    before = copy.deepcopy(opened)
    answer = Answered(
        "review", "approve", "ana", frozenset({"support"}), {"approved_amount": Decimal(250)}
    )
    after, _ = decide(case, CATALOG, opened, answer)
    assert opened == before
    assert after != before
    refused = Answered("review", "approve", "eve", frozenset(), {"approved_amount": Decimal(250)})
    with pytest.raises(AnswerRefused):
        decide(case, CATALOG, opened, refused)
    assert opened == before


# --- Slice 1: a failed step needs attention ---


def unreachable(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("provider unreachable")


def test_a_failed_step_needs_attention_and_keeps_the_case_open() -> None:
    # Nothing is skipped automatically (brief, D17): the case waits for a person.
    run = run_case(
        REFUND,
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={"payments.refund@2": unreachable},
    )
    assert run.needs_attention == ["pay#1: payments.refund@2 failed: provider unreachable"]
    assert "pay#1 failed: payments.refund@2 failed: provider unreachable" in run.history
    assert not run.reached("pay")
    assert not run.closed
    assert run.status == "open"


def test_other_steps_go_on_while_one_needs_attention() -> None:
    definition = refund()
    definition["steps"]["check_documents"] = {
        "kind": "task",
        "display": {"title": "Check the customer's documents"},
        "roles": ["support"],
        "requires": ["review"],
        "outcomes": {"complete": {"display": {"title": "Documents complete"}}},
    }
    run = run_case(
        definition,
        file=SMALL,
        answers=[SMALL_REVIEW, ("check_documents", "complete", "ana")],
        people=PEOPLE,
        activities={"payments.refund@2": unreachable},
    )
    assert run.reached("check_documents")
    assert run.needs_attention == ["pay#1: payments.refund@2 failed: provider unreachable"]
    assert not run.closed


# --- Slice 2: an activity's outcome ---


def gives(outcome: str) -> Any:
    """A fake refund that gives the outcome `outcome`, as a provider would."""

    def refund_giving(inputs: dict[str, Any]) -> dict[str, Any]:
        raise Outcome(outcome)

    return refund_giving


def with_call_customer() -> dict[str, Any]:
    """The refund, with the guide's step reacting to a declined refund, and a `paid` milestone."""
    definition = refund()
    definition["milestones"] = {"paid": {"display": {"title": "Refund paid"}}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["steps"]["call_customer"] = {
        "kind": "task",
        "display": {"title": "Call the customer about the declined refund"},
        "roles": ["support"],
        "requires": ["pay"],
        "when": {"==": [{"var": "pay.outcome"}, "declined"]},
        "outcomes": {"called": {"display": {"title": "Customer called"}}},
    }
    return definition


def test_an_outcome_the_contract_does_not_declare_fails_the_step() -> None:
    # Fail closed: never read as `done`, never ignored (brief, D17).
    run = run_case(
        REFUND,
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={"payments.refund@2": gives("bounced")},
    )
    assert run.needs_attention == [
        (
            "pay#1: payments.refund@2 gave the outcome bounced, which its contract doesn't "
            "declare: its outcomes are declined"
        )
    ]


def test_an_output_the_contract_does_not_declare_fails_the_step() -> None:
    run = run_case(
        REFUND,
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={"payments.refund@2": lambda inputs: {"refund": "r-1"}},
    )
    [failed] = run.needs_attention
    assert failed.startswith(
        "pay#1: payments.refund@2 gave an output its contract doesn't declare: refund_id:"
    )


def test_a_declined_refund_is_an_outcome_a_step_reacts_to() -> None:
    run = run_case(
        with_call_customer(),
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={"payments.refund@2": gives("declined")},
    )
    assert "pay#1 gave declined" in run.history
    assert run.waiting_for == ["call_customer by support"]
    assert "reached paid" not in run.history  # milestones come only with `done`
    assert run.needs_attention == []


def test_an_outcome_is_tagged_with_the_contract_that_declares_it() -> None:
    definition = refund()
    definition["steps"]["letter"] = {
        "kind": "activity",
        "display": {"title": "Draft a letter about the refund"},
        "activity": "letters.draft@2",
        "requires": ["pay"],
        "inputs": {"to_customer": {"var": "order_id"}, "template": {"var": "pay.outcome"}},
    }
    run = run_case(definition, file=SMALL, answers=[SMALL_REVIEW], people=PEOPLE)
    assert (
        "scheduled letter#1: letters.draft@2 (to_customer from system:opener; template from "
        "system:payments.refund@2), key memory/letter#1"
    ) in run.history


# --- Slice 3: an operator retries a failed step ---


def down_once() -> tuple[list[str], Any]:
    """A fake refund that fails on its first call, and the keys it was called with."""
    keys: list[str] = []

    def refund_down_once(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        if len(keys) == 1:
            raise ConnectionError("provider unreachable")
        return {"refund_id": "refund-ord-1"}

    return keys, refund_down_once


def test_only_an_operating_role_retries() -> None:
    _, refund_down = down_once()
    with pytest.raises(
        RetryRefused,
        match=r"^pay#1 is retried by an operating role \(operations\), and ana has support$",
    ):
        run_case(
            REFUND,
            file=SMALL,
            answers=[SMALL_REVIEW, retry("pay#1", "ana")],
            people=OPERATORS,
            activities={"payments.refund@2": refund_down},
        )


def test_only_a_failed_run_is_retried() -> None:
    with pytest.raises(RetryRefused, match="^review#1 has not failed: nothing to retry$"):
        run_case(
            REFUND, file=LARGE, answers=[REVIEWED, retry("review#1", "omar")], people=OPERATORS
        )


def test_a_retry_is_the_same_run_with_the_same_key() -> None:
    # The first attempt may have moved money: the same key lets the provider say so (brief, D26).
    keys, refund_down = down_once()
    run = run_case(
        REFUND,
        file=SMALL,
        answers=[SMALL_REVIEW, retry("pay#1", "omar")],
        people=OPERATORS,
        activities={"payments.refund@2": refund_down},
    )
    assert keys == ["memory/pay#1", "memory/pay#1"]
    assert "omar retried pay#1 as operations" in run.history
    assert run.needs_attention == []
    assert run.reached("pay")
    assert run.closed


def test_an_approval_spent_on_the_run_holds_for_its_retry() -> None:
    keys, refund_down = down_once()
    run = run_case(
        REFUND,
        file=LARGE,
        answers=[REVIEWED, ("pay", "approve", "sam"), retry("pay#1", "omar")],
        people=OPERATORS,
        activities={"payments.refund@2": refund_down},
    )
    assert keys == ["memory/pay#1", "memory/pay#1"]
    assert not any(line.startswith("asked pay.approval#2") for line in run.history)
    assert run.closed


def test_a_retry_checks_the_step_again() -> None:
    # pay failed at the opening, its condition unreadable; once the review is answered, the
    # retry reads it again, and the approval is asked for the same run.
    definition = refund(sequence=[])
    run = run_case(
        definition,
        file=LARGE,
        answers=[REVIEWED, retry("pay#1", "omar"), ("pay", "approve", "sam")],
        people=OPERATORS,
    )
    assert run.reached("pay")
    assert (
        "scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from "
        "person:ana), key memory/pay#1" in run.history
    )
    rejected = refund(sequence=[])
    with pytest.raises(
        RetryRefused, match='^pay#1 can\'t be retried: review.outcome = "approve" is false now$'
    ):
        run_case(
            rejected,
            file=LARGE,
            answers=[("review", "reject", "ana"), retry("pay#1", "omar")],
            people=OPERATORS,
        )


# --- Slice 4: closing a case with a declared reason ---


def closable() -> dict[str, Any]:
    """The refund, with the guide's close reason, and one for operations."""
    definition = refund()
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]},
        "abandoned": {"display": {"title": "Abandoned after a failure"}, "roles": ["operations"]},
    }
    return definition


def test_an_undeclared_close_reason_is_refused() -> None:
    with pytest.raises(
        CloseRefused,
        match="^refund has no close reason 'spam': its reasons are abandoned, duplicate$",
    ):
        run_case(closable(), file=LARGE, answers=[close("spam", "ana")], people=PEOPLE)


def test_a_close_reason_names_who_may_use_it() -> None:
    with pytest.raises(CloseRefused, match="^duplicate is closed by support, and eve has no role$"):
        run_case(closable(), file=LARGE, answers=[close("duplicate", "eve")], people=PEOPLE)


def test_closing_cancels_what_waits_saying_why() -> None:
    # D10: the people an open task or approval was assigned to see why it went away.
    run = run_case(
        closable(), file=LARGE, answers=[REVIEWED, close("duplicate", "ana")], people=PEOPLE
    )
    assert "ana closed the case as duplicate, as support" in run.history
    assert "cancelled pay.approval#1: closed as duplicate by ana" in run.history
    assert run.history[-1] == "closed: duplicate, by ana"
    assert run.waiting_for == []
    assert run.closed
    assert not run.reached("pay")
    with pytest.raises(AnswerRefused, match="^the case is closed: nothing waits for an answer$"):
        run_case(
            closable(),
            file=LARGE,
            answers=[REVIEWED, close("duplicate", "ana"), ("pay", "approve", "sam")],
            people=PEOPLE,
        )


def test_an_operator_closes_a_case_that_needs_attention() -> None:
    run = run_case(
        closable(),
        file=SMALL,
        answers=[SMALL_REVIEW, close("abandoned", "omar")],
        people=OPERATORS,
        activities={"payments.refund@2": unreachable},
    )
    assert "cancelled pay#1: closed as abandoned by omar" in run.history
    assert run.needs_attention == []
    assert run.closed


# --- Slice 5: closing, then closed ---

PAY_HELD = [SMALL_REVIEW, close("duplicate", "ana")]  # pay#1 is running when Ana closes


def test_while_closing_nothing_waits_and_nothing_starts() -> None:
    closing = run_case(closable(), file=SMALL, answers=PAY_HELD, people=PEOPLE, held=["pay"])
    assert closing.status == "closing"
    assert closing.waiting_for == []
    with pytest.raises(AnswerRefused, match="^the case is closing: nothing waits for an answer$"):
        run_case(
            closable(),
            file=SMALL,
            answers=[*PAY_HELD, ("review", "approve", "ana")],
            people=PEOPLE,
            held=["pay"],
        )
    with pytest.raises(ProposalRefused, match="^the case is closing: nothing starts$"):
        run_case(
            with_check_order() | {"close_reasons": closable()["close_reasons"]},
            file=SMALL,
            answers=[*PAY_HELD, propose("check_order", "ana")],
            people=PEOPLE,
            held=["pay"],
        )


def test_a_running_activity_finishes_and_the_closed_case_is_flagged() -> None:
    # A payment can't be cut off halfway (brief, D10): it finishes, and a person decides.
    run = run_case(
        closable(), file=SMALL, answers=[*PAY_HELD, finish("pay#1")], people=PEOPLE, held=["pay"]
    )
    assert run.flags == ["pay#1 completed after the close was requested"]
    assert run.history[-4:] == [
        "ana closed the case as duplicate, as support",
        "pay#1 done, giving refund_id from untrusted:undeclared",
        "flagged: pay#1 completed after the close was requested",
        "closed: duplicate, by ana",
    ]
    assert run.closed


def test_an_activity_failing_while_closing_flags_the_case() -> None:
    run = run_case(
        closable(),
        file=SMALL,
        answers=[*PAY_HELD, finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
        activities={"payments.refund@2": unreachable},
    )
    assert run.flags == [
        "pay#1 failed after the close was requested: payments.refund@2 failed: provider unreachable"
    ]
    assert run.needs_attention == []
    assert run.closed


# --- Slice 6: closes_when and stays_open ---


def test_a_case_that_stays_open_names_how_to_close_it() -> None:
    with pytest.raises(
        CaseInvalid,
        match="^stays_open: a case that stays open names close_reasons, or nobody could close it$",
    ):
        parse_case(refund(stays_open=True))
    with pytest.raises(CaseInvalid, match="^closes_when: paid is not a milestone$"):
        parse_case(refund(closes_when=["paid"]))


def test_a_case_of_proposed_steps_stays_open_until_a_person_closes_it() -> None:
    # Carried from the 8a review: without stays_open it closed the moment it opened.
    definition = closable() | {"stays_open": True, "sequence": []}
    for step in definition["steps"].values():
        step["automatic"] = False
        step["proposed_by"] = ["support"]
    definition["steps"]["pay"]["requires"] = ["review"]
    opened = run_case(definition, file=LARGE, answers=[], people=PEOPLE)
    assert opened.status == "open"
    assert opened.waiting_for == []
    proposed = run_case(definition, file=LARGE, answers=[propose("review", "ana")], people=PEOPLE)
    assert proposed.waiting_for == ["review by support"]
    closed = run_case(definition, file=LARGE, answers=[close("duplicate", "ana")], people=PEOPLE)
    assert closed.closed


def test_closes_when_closes_the_case_once_its_milestones_are_reached() -> None:
    # A survey task stays open alongside; reaching `paid` closes the case and cancels it.
    definition = refund(closes_when=["paid"])
    definition["milestones"] = {"paid": {"display": {"title": "Refund paid"}}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["steps"]["survey"] = {
        "kind": "task",
        "display": {"title": "Ask the customer for feedback"},
        "roles": ["support"],
        "outcomes": {"sent": {"display": {"title": "Survey sent"}}},
    }
    run = run_case(definition, file=SMALL, answers=[SMALL_REVIEW], people=PEOPLE)
    assert run.history[-3:] == [
        "reached paid",
        "cancelled survey#1: the case closes when paid is reached",
        "closed: paid reached",
    ]
    assert run.closed


def test_a_closing_case_is_not_closed_or_retried_again() -> None:
    with pytest.raises(CloseRefused, match="^the case is closing: it can't be closed again$"):
        run_case(
            closable(),
            file=SMALL,
            answers=[*PAY_HELD, close("duplicate", "ana")],
            people=PEOPLE,
            held=["pay"],
        )
    with pytest.raises(RetryRefused, match="^the case is closing: nothing starts$"):
        run_case(
            closable(),
            file=SMALL,
            answers=[*PAY_HELD, retry("pay#1", "omar")],
            people=OPERATORS,
            held=["pay"],
        )


def test_a_declared_outcome_while_closing_flags_the_case() -> None:
    run = run_case(
        closable(),
        file=SMALL,
        answers=[*PAY_HELD, finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
        activities={"payments.refund@2": gives("declined")},
    )
    assert run.flags == ["pay#1 completed after the close was requested"]
    assert run.closed


# --- Tutor review: closes_when never cancels a failed step ---


def test_closes_when_waits_while_a_step_needs_attention() -> None:
    # The tutor's probe: a parallel letter fails, then `paid` is reached. Nothing is skipped
    # automatically (brief, D17): the case waits for a person, then closes on `paid`.
    definition = refund(closes_when=["paid"])
    definition["milestones"] = {"paid": {"display": {"title": "Refund paid"}}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["steps"]["notify"] = {
        "kind": "activity",
        "display": {"title": "Draft a letter about the refund"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "order_id"}, "template": "refund"},
    }
    calls: list[str] = []

    def letter_down_once(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs["idempotency_key"])
        if len(calls) == 1:
            raise ConnectionError("provider unreachable")
        return {"draft_id": "draft-refund"}

    fakes = {"letters.draft@2": letter_down_once}
    waiting = run_case(
        definition, file=SMALL, answers=[SMALL_REVIEW], people=OPERATORS, activities=fakes
    )
    assert "reached paid" in waiting.history
    assert waiting.needs_attention == ["notify#1: letters.draft@2 failed: provider unreachable"]
    assert waiting.status == "open"
    calls.clear()
    retried = run_case(
        definition,
        file=SMALL,
        answers=[SMALL_REVIEW, retry("notify#1", "omar")],
        people=OPERATORS,
        activities=fakes,
    )
    assert retried.needs_attention == []
    assert retried.history[-1] == "closed: paid reached"


# --- Layer 8d, slice 1: outputs into the case file ---


def with_letter(to_customer: dict[str, Any]) -> dict[str, Any]:
    """The refund, then a letter drafted once it is paid, addressed with `to_customer`."""
    definition = refund()
    definition["steps"]["letter"] = {
        "kind": "activity",
        "display": {"title": "Draft the refund letter"},
        "activity": "letters.draft@2",
        "requires": ["pay"],
        "inputs": {"to_customer": to_customer, "template": "refund-done"},
    }
    return definition


def test_an_undeclared_output_cannot_reach_a_trusted_input() -> None:
    # Nobody declared where `refund_id` comes from, so it is untrusted (brief, D6), and an input
    # that accepts only trusted data refuses it: the step fails before it starts.
    run = run_case(
        with_letter({"var": "pay.refund_id"}), file=SMALL, answers=[SMALL_REVIEW], people=PEOPLE
    )
    refused = (
        "letter#1: letters.draft@2 takes to_customer only from a system or a person, never from "
        "untrusted data, and this value comes from pay.refund_id (untrusted:undeclared)"
    )
    assert run.needs_attention == [refused]
    assert not run.closed


def test_only_declared_outputs_reach_the_case_file() -> None:
    # The activity sends back a field its contract doesn't declare, and a "source" for its
    # refund_id: neither reaches the case file. Only the contract says where a value comes from.
    def vouching(inputs: dict[str, Any]) -> dict[str, Any]:
        return {"refund_id": "r-1", "email": "a@b.c", "refund_id_source": "system:payments"}

    for read in ("pay.email", "pay.refund_id_source"):
        run = run_case(
            with_letter({"var": read}),
            file=SMALL,
            answers=[SMALL_REVIEW],
            people=PEOPLE,
            activities={"payments.refund@2": vouching},
        )
        assert run.needs_attention == [
            f"letter#1: to_customer can't be evaluated: {read} has no known sources"
        ]
    assert "pay#1 done, giving refund_id from untrusted:undeclared" in run.history


def test_a_declared_outcome_gives_no_output() -> None:
    run = run_case(
        with_letter({"var": "pay.refund_id"}),
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={"payments.refund@2": gives("declined")},
    )
    assert "pay#1 gave declined" in run.history
    # A declined refund is still a run that ended, so the letter reads, and finds nothing.
    assert run.needs_attention == [
        "letter#1: to_customer can't be evaluated: pay.refund_id has no known sources"
    ]


class CustomerFound(BaseModel):
    email: Annotated[str, source("system:crm")]  # the CRM holds the customer's address
    name: str  # nothing declared


class FindInput(BaseModel):
    customer: str


class NoticeInput(BaseModel):
    to: Annotated[str, only_from("crm")]
    idempotency_key: str


class NoticeOutput(BaseModel):
    notice_id: str


def contract(name: str, input: type[BaseModel], output: type[BaseModel], **more: Any) -> Any:
    """A low-risk activity contract `name@1`, for a test's own catalog."""
    fields: dict[str, Any] = {
        "version": 1,
        "risk": "low",
        "effect": "read",
        "timeouts": Timeouts(start_to_close=10, schedule_to_start=60),
        "retry": RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
        "idempotency_key": None,
        "outcomes": [],
        "display": ContractDisplay(title=name, description=name),
    }
    return ActivityContract(name=name, input=input, output=output, **fields | more)


def with_crm() -> Catalog:
    """The development catalog, and a CRM lookup whose `email` is declared `system:crm`."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register(contract("crm.find", FindInput, CustomerFound))
    catalog.register(
        contract(
            "notices.draft",
            NoticeInput,
            NoticeOutput,
            effect="write",
            idempotency_key="idempotency_key",
        )
    )
    return catalog


def with_customer_steps(to: str, activity: str, field: str) -> dict[str, Any]:
    """The refund, a CRM lookup, then `activity` addressed with `to` in its input `field`."""
    definition = refund()
    definition["steps"]["find"] = {
        "kind": "activity",
        "display": {"title": "Find the customer"},
        "activity": "crm.find@1",
        "inputs": {"customer": {"var": "order_id"}},
    }
    definition["steps"]["notify"] = {
        "kind": "activity",
        "display": {"title": "Draft a notice"},
        "activity": activity,
        "requires": ["find"],
        "inputs": {field: {"var": to}}
        | ({"template": "found"} if activity == "letters.draft@2" else {}),
    }
    return definition


def test_a_declared_output_is_as_trusted_as_its_contract_says() -> None:
    crm = {"crm.find@1": lambda inputs: {"email": "c@example.com", "name": "Cleo"}}
    drafts = {"notices.draft@1": lambda inputs: {"notice_id": "n-1"}}
    for activity, field in (("letters.draft@2", "to_customer"), ("notices.draft@1", "to")):
        run = run_case(
            with_customer_steps("find.email", activity, field),
            file=SMALL,
            answers=[SMALL_REVIEW],
            people=PEOPLE,
            activities=crm | drafts,
            catalog=with_crm(),
        )
        assert run.needs_attention == [] and run.closed, run.history
        assert (
            "find#1 done, giving email from system:crm; name from untrusted:undeclared"
            in run.history
        )
    # The same lookup's undeclared `name` is refused by both.
    for activity, field in (("letters.draft@2", "to_customer"), ("notices.draft@1", "to")):
        run = run_case(
            with_customer_steps("find.name", activity, field),
            file=SMALL,
            answers=[SMALL_REVIEW],
            people=PEOPLE,
            activities=crm | drafts,
            catalog=with_crm(),
        )
        [failed] = run.needs_attention
        assert failed.startswith("notify#1: ") and "find.name (untrusted:undeclared)" in failed


def test_the_latest_runs_output_is_read() -> None:
    definition = with_customer_steps("find.email", "notices.draft@1", "to")
    definition["steps"]["find"] |= {"repeatable": True, "proposed_by": ["support"]}
    definition["steps"]["notify"] |= {"automatic": False, "proposed_by": ["support"]}
    definition["stays_open"] = True
    definition["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    addresses = iter(["old@example.com", "new@example.com"])
    sent: list[str] = []

    def drafting(inputs: dict[str, Any]) -> dict[str, Any]:
        sent.append(inputs["to"])
        return {"notice_id": "n-1"}

    run_case(
        definition,
        file=SMALL,
        answers=[SMALL_REVIEW, propose("find", "ana"), propose("notify", "ana")],
        people=PEOPLE,
        activities={
            "crm.find@1": lambda inputs: {"email": next(addresses), "name": "Cleo"},
            "notices.draft@1": drafting,
        },
        catalog=with_crm(),
    )
    assert sent == ["new@example.com"]


# --- Layer 8d, slice 2: workflow contracts ---


def test_an_activity_step_naming_a_workflow_contract_fails() -> None:
    # Fail closed: nothing guesses how to run a contract of the other kind (8d, drafting 4).
    definition = refund()
    definition["steps"]["pay"]["activity"] = "kyc.check@1"
    run = run_case(definition, file=SMALL, answers=[SMALL_REVIEW], people=PEOPLE)
    assert run.needs_attention == [
        "pay#1: kyc.check@1 is a workflow contract, not an activity: run it as a workflow step."
    ]


class Scored(BaseModel):
    email: Annotated[str, source("system:crm")]
    score: float  # what registration refuses (brief, D20); here it is never registered


def test_an_output_the_case_file_cannot_hold_fails_the_step() -> None:
    # Tutor review: checked at runtime on nothing registration did. A contract that skipped
    # registration gives a float: the step fails, and nothing it gave lands, not even its email.
    catalog = with_crm()
    found = catalog.get("crm.find@1").model_copy(update={"output": Scored})  # no check runs
    catalog._contracts["crm.find@1"] = found  # bypassing registration, on purpose
    run = run_case(
        with_customer_steps("find.email", "notices.draft@1", "to"),
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={"crm.find@1": lambda inputs: {"email": "c@x.com", "score": Decimal("0.1")}},
        catalog=catalog,
    )
    assert run.needs_attention == [
        "find#1: crm.find@1 gave score as a binary float, which the case file can't hold exactly "
        + "(brief, D20)"
    ]
    assert not any(line.startswith("find#1 done") for line in run.history)
    assert not any(line.startswith("scheduled notify#1") for line in run.history)
