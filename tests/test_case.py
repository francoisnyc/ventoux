"""The case layer: a case definition, and the runtime that runs it in memory (layer 8a).

Tests go through `parse_case` and `run_case`, and read what a run reports.
See docs/layers/08-case.md and docs/guides/cases.md.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import Answered, CaseState, Opened
from ventoux.testing import (
    CATALOG,
    AnswerRefused,
    CaseRefused,
    InputRefused,
    ProposalRefused,
    StepStopped,
    load_definition,
    propose,
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
        ("kind", "steps.pay.kind: a step is a task or an activity, and this one is 'script'"),
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
            "order_id is a reference to orders, and the opening gives 1001",
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
    with pytest.raises(CaseRefused, match="^amount is a number, and the opening gives 0.1$"):
        run_case(REFUND, file={"order_id": "ord-1", "amount": 0.1}, answers=[], people=PEOPLE)
    with pytest.raises(
        AnswerRefused, match="^approved_amount is a number, and the answer gives 40.5$"
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
    with pytest.raises(InputRefused, match="amount"):
        run_case(
            definition,
            file={"order_id": "ord-1", "amount": 40},
            answers=[("review", "approve", "ana", {"approved_amount": 40})],
            people=PEOPLE,
        )


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
    with pytest.raises(
        StepStopped, match="^pay's condition review.outcome = \"approve\" can't be evaluated"
    ):
        run_case(definition, file=LARGE, answers=[], people=PEOPLE)


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
    with pytest.raises(
        StepStopped, match="^payments.refund@2 is high risk, and pay has no approval$"
    ):
        run_case(definition, file=LARGE, answers=[REVIEWED], people=PEOPLE)


# --- Slice 6: the guide, run as written ---

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "cases.md").read_text()


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
        "PEOPLE": PEOPLE,
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
    shown = plain[1].splitlines()
    first = reworked.history.index(shown[0])
    assert reworked.history[first : first + len(shown)] == shown


def test_the_guides_proposed_step_runs() -> None:
    definition = guide_json(0)
    definition["steps"].update(guide_json(1))
    run = run_case(
        definition, file=LARGE, answers=[REVIEWED, propose("check_order", "ana")], people=PEOPLE
    )
    assert run.reached("check_order")


def refusal(run: Any) -> str:
    """What the engine says when it refuses `run`."""
    try:
        run()
    except (AnswerRefused, ProposalRefused, CaseRefused) as refused:
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
