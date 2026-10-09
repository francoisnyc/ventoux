"""People in the loop: roles, forms and approvals (layer 7).

Tests go through the catalog, `parse_plan`, `validate` and `run_plan`, and read what a run reports.
See docs/layers/07-people.md and docs/guides/plans.md, "People in the loop".
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel

from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.interpreter import Outcome, PlanRun, RunRefused
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.core.policy import only_from
from ventoux.core.provenance import sourced
from ventoux.core.validate import validate
from ventoux.testing import CATALOG, FAKES, payments_refund, run_plan


class RecordInput(BaseModel):
    amount: Annotated[Decimal, only_from("payments")]  # only an amount the payments system gave
    idempotency_key: str


class RecordOutput(BaseModel):
    entry_id: str


# A contract whose input takes a value only from one system: no person's answer satisfies it.
ledger_record = ActivityContract(
    name="ledger.record",
    version=1,
    input=RecordInput,
    output=RecordOutput,
    risk="low",
    effect="write",
    timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
    idempotency_key="idempotency_key",
    outcomes=[],
    display=Display(title="Record an amount", description="Records an amount in the ledger."),
)


def test_a_role_is_written_as_a_label() -> None:
    with pytest.raises(ValueError, match="'Support Lead' is not a role: a role is lowercase"):
        Catalog().register_role("Support Lead")


def test_a_role_approves_up_to_a_risk_or_nothing() -> None:
    with pytest.raises(ValueError, match="'hihg' is not a risk: a role approves up to low, medium"):
        Catalog().register_role("support-lead", approves="hihg")


def test_the_catalog_lists_its_roles_with_what_each_may_approve() -> None:
    catalog = Catalog()
    catalog.register_role("support-lead", approves="high")
    catalog.register_role("support")
    assert catalog.roles == {"support": None, "support-lead": "high"}


def asking(**wait: Any) -> dict[str, Any]:
    """A plan that asks support one question, `confirm`, then ends as the answer says."""
    return {
        "plan": "asking",
        "version": 1,
        "display": {"title": "Asks one question"},
        "fields": {"order_id": {"type": "reference", "system": "orders"}},
        "initial": "confirm",
        "states": {
            "confirm": {
                "wait": {"outcomes": ["accept", "decline"], "roles": ["support"], **wait},
                "on": {"accept": "accepted", "decline": "declined"},
            },
            "accepted": {"final": "succeeded"},
            "declined": {"final": "failed"},
        },
    }


ORDER = {"order_id": sourced("A-1001", "system:orders")}
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "bob": ["support-lead"]}


def lines(run: PlanRun) -> list[str]:
    return [str(event) for event in run.history]


def test_a_wait_without_roles_is_refused() -> None:
    # No roles would mean anyone may answer: a permissive default (brief, D22).
    plan = asking()
    del plan["states"]["confirm"]["wait"]["roles"]
    with pytest.raises(PlanInvalid, match="states.confirm.wait.roles: required"):
        parse_plan(plan)
    with pytest.raises(
        PlanInvalid, match="states.confirm.wait.roles: a wait or an approval names at least one"
    ):
        parse_plan(asking(roles=[]))


def test_a_role_nobody_registered_is_an_issue() -> None:
    issues = validate(parse_plan(asking(roles=["support-laed"])), CATALOG)
    assert [(i.path, i.code, i.message) for i in issues] == [
        (
            "states.confirm.wait.roles",
            "UNKNOWN_ROLE",
            (
                "support-laed is a role nobody registered: the roles are support, support-lead; "
                "use one of them, or ask the platform team to register it"
            ),
        )
    ]


def test_an_answer_from_someone_without_the_role_is_refused_and_the_wait_goes_on() -> None:
    run = run_plan(
        asking(),
        fields=ORDER,
        answers=[
            ("confirm", "accept", "bob"),  # a team lead, not support
            ("confirm", "accept", "eve"),  # nobody listed: no roles at all
            ("confirm", "accept", "mallory"),  # only a role the catalog doesn't know
            ("confirm", "accept", "ana"),
        ],
        people={**PEOPLE, "mallory": ["support-admin"]},
    )
    assert [line for line in lines(run) if line.startswith("refused")] == [
        "refused bob's answer accept: confirm#1 is answered by support, and bob has support-lead",
        "refused eve's answer accept: confirm#1 is answered by support, and eve has no role",
        (
            "refused mallory's answer accept: confirm#1 is answered by support, and mallory has "
            "no role"
        ),
    ]
    assert "ana answered accept as support" in lines(run)
    assert run.status == "succeeded"


def test_the_role_that_counted_is_the_one_recorded() -> None:
    plan = asking(roles=["support-lead", "support"])
    run = run_plan(plan, fields=ORDER, answers=[("confirm", "accept", "sam")], people=PEOPLE)
    assert "sam answered accept as support" in lines(run)  # the first, in order, that let sam


def reviewing(**wait: Any) -> dict[str, Any]:
    """A plan where support reviews a refund and says how much to pay, then the refund is drafted
    in a letter: `approved_amount` is set by the reviewer's form, never given at the start."""
    return {
        "plan": "reviewing",
        "version": 1,
        "display": {"title": "Review, then write"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders"},
            "approved_amount": {"type": "number"},
        },
        "initial": "review",
        "states": {
            "review": {
                "wait": {
                    "outcomes": ["accept", "reject"],
                    "roles": ["support"],
                    "sets": {"accept": ["approved_amount"]},
                    **wait,
                },
                "on": {"accept": "write", "reject": "failed"},
            },
            "write": {
                "activity": "letters.draft@2",
                "inputs": {
                    "to_customer": {"string": [{"var": "approved_amount"}]},
                    "template": "refund",
                },
                "on": {"done": "written"},
            },
            "written": {"final": "succeeded"},
            "failed": {"final": "failed"},
        },
    }


def refusals(run: PlanRun) -> list[str]:
    return [line for line in lines(run) if line.startswith("refused")]


def test_a_form_that_does_not_fit_its_outcome_is_refused() -> None:
    run = run_plan(
        reviewing(),
        fields=ORDER,
        answers=[
            ("review", "accept", "ana"),  # no form at all
            ("review", "accept", "ana", {}),  # a form without the field
            ("review", "accept", "ana", {"approved_amount": Decimal(40), "note": "rush"}),
            ("review", "accept", "ana", {"approved_amount": "40"}),  # a text
            ("review", "accept", "ana", {"approved_amount": 40.0}),  # a float: not exact
            ("review", "accept", "ana", {"approved_amount": True}),  # a boolean is no number
            ("review", "reject", "ana", {"approved_amount": Decimal(40)}),  # reject sets nothing
        ],
        people=PEOPLE,
    )
    assert refusals(run) == [
        "refused ana's answer accept: accept sets approved_amount, and the answer doesn't give it",
        "refused ana's answer accept: accept sets approved_amount, and the answer doesn't give it",
        "refused ana's answer accept: the answer gives note, which accept doesn't set",
        "refused ana's answer accept: approved_amount is a number, and the answer gives '40'",
        "refused ana's answer accept: approved_amount is a number, and the answer gives 40.0",
        "refused ana's answer accept: approved_amount is a number, and the answer gives True",
        "refused ana's answer reject: the answer gives approved_amount, which reject doesn't set",
    ]
    assert run.status == "waiting"  # every answer refused: the wait goes on


def test_sets_names_an_outcome_the_wait_offers_and_a_declared_field() -> None:
    plan = reviewing(sets={"acept": ["approved_amount"], "accept": ["approved_amout"]})
    issues = validate(parse_plan(plan), CATALOG)
    assert [(i.path, i.code, i.message) for i in issues] == [
        (
            "states.review.wait.sets.acept",
            "UNKNOWN_EVENT",
            "the wait review never gives acept: its outcomes are accept, reject",
        ),
        (
            "states.review.wait.sets.accept",
            "UNKNOWN_FIELD",
            (
                "review's accept sets approved_amout, which is not a field: the fields are "
                "approved_amount, order_id"
            ),
        ),
    ]


def test_a_field_a_person_sets_is_never_given_at_the_start() -> None:
    with pytest.raises(
        RunRefused,
        match="approved_amount is set by a person in review, never given at the start",
    ):
        run_plan(
            reviewing(),
            fields={**ORDER, "approved_amount": sourced(Decimal(40), "system:opener")},
            answers=[],
            people=PEOPLE,
        )


def test_reading_a_field_before_anyone_sets_it_stops_the_step() -> None:
    plan = reviewing()
    plan["initial"] = "write"  # straight to the letter, before any review
    run = run_plan(plan, fields=ORDER, answers=[], people=PEOPLE)
    assert run.status == "stopped"
    assert run.reason is not None
    assert run.reason.startswith("to_customer can't be evaluated: approved_amount")


def test_a_forms_values_land_tagged_with_who_answered() -> None:
    calls: list[dict[str, Any]] = []

    def draft(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs)
        return {"draft_id": "d-1"}

    run = run_plan(
        reviewing(),
        fields=ORDER,
        answers=[("review", "accept", "ana", {"approved_amount": Decimal(40)})],
        activities={**FAKES, "letters.draft@2": draft},
        people=PEOPLE,
    )
    assert "ana answered accept as support, setting approved_amount" in lines(run)
    assert "scheduled letters.draft@2 (to_customer from person:ana; template from the plan)" in (
        lines(run)
    )
    assert calls[0]["to_customer"] == "40"
    assert run.status == "succeeded"


def test_a_field_a_person_sets_is_trusted_but_from_no_system() -> None:
    # `validate` can't know who will answer, only that a person will: trusted, so `trusted_only`
    # passes (the letter above has no issue), and no system, so `only_from` never does.
    assert validate(parse_plan(reviewing()), CATALOG) == []
    paying = reviewing()
    paying["states"]["write"] = {
        "activity": "ledger.record@1",
        "inputs": {"amount": {"var": "approved_amount"}},
        "on": {"done": "written"},
    }
    catalog = Catalog()
    catalog.register(ledger_record)
    catalog.register_role("support")
    issues = validate(parse_plan(paying), catalog)
    assert [(i.path, i.code) for i in issues] == [("states.write.inputs.amount", "INPUT_POLICY")]
    assert "comes from approved_amount (person:answering review)" in issues[0].message


def approving(**approval: Any) -> dict[str, Any]:
    """The guide's refund: a team lead approves `pay`, then the refund is paid."""
    return {
        "plan": "approving",
        "version": 1,
        "display": {"title": "Approve, then pay"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders"},
            "amount": {"type": "number"},
        },
        "initial": "approve_refund",
        "states": {
            "approve_refund": {
                "approval": {"of": "pay", "roles": ["support-lead"], **approval},
                "on": {"approve": "pay", "reject": "failed"},
            },
            "pay": {
                "activity": "payments.refund@2",
                "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
                "on": {"done": "paid", "declined": "failed"},
            },
            "paid": {"final": "succeeded"},
            "failed": {"final": "failed"},
        },
    }


REFUND = {**ORDER, "amount": sourced(Decimal(250), "system:opener")}


def issues_of(plan: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(i.path, i.code, i.message) for i in validate(parse_plan(plan), CATALOG)]


def test_an_approval_without_roles_is_refused() -> None:
    plan = approving()
    del plan["states"]["approve_refund"]["approval"]["roles"]
    with pytest.raises(PlanInvalid, match="states.approve_refund.approval.roles: required"):
        parse_plan(plan)


def test_an_approval_approves_the_activity_its_approve_leads_to() -> None:
    elsewhere = approving()
    elsewhere["states"]["approve_refund"]["on"]["approve"] = "failed"
    assert issues_of(elsewhere) == [
        (
            "states.approve_refund.on.approve",
            "APPROVAL_TARGET",
            "approve_refund approves pay, and its approve goes to failed: send approve to pay",
        ),
        (
            "states.pay",
            "UNREACHABLE_STATE",
            "no path from approve_refund reaches pay: remove it, or add a transition to it",
        ),
        (
            "states.paid",
            "UNREACHABLE_STATE",
            "no path from approve_refund reaches paid: remove it, or add a transition to it",
        ),
    ]
    not_an_activity = approving(of="paid")
    assert issues_of(not_an_activity)[0] == (
        "states.approve_refund.approval.of",
        "APPROVAL_TARGET",
        (
            "approve_refund approves paid, which is not an activity state: name the activity it "
            "approves"
        ),
    )


def test_a_wait_offering_approve_approves_nothing() -> None:
    # An approval is declared, never read from an outcome's name (brief, D23).
    plan = approving()
    plan["states"]["approve_refund"] = {
        "wait": {"outcomes": ["approve", "reject"], "roles": ["support-lead"]},
        "on": {"approve": "pay", "reject": "failed"},
    }
    assert [(path, code) for path, code, _ in issues_of(plan)] == [
        ("states.pay", "APPROVAL_REQUIRED")
    ]


def test_a_misspelled_approval_is_refused_never_read_as_not_approved() -> None:
    run = run_plan(
        approving(),
        fields=REFUND,
        answers=[("approve_refund", "aprove", "sam"), ("approve_refund", "approve", "sam")],
        people=PEOPLE,
    )
    assert refusals(run) == ["refused sam's answer aprove: approve_refund offers approve or reject"]
    assert run.status == "succeeded"


def test_a_rejection_takes_reject_and_the_activity_does_not_run() -> None:
    refunds: list[dict[str, Any]] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        refunds.append(inputs)
        return {"refund_id": "r-1"}

    run = run_plan(
        approving(),
        fields=REFUND,
        answers=[("approve_refund", "reject", "sam")],
        activities={**FAKES, "payments.refund@2": refund},
        people=PEOPLE,
    )
    assert lines(run)[1:5] == [
        "entered approve_refund",
        "waiting at approve_refund#1 for approve or reject of pay by support-lead",
        "sam answered reject as support-lead",
        "moved on reject to failed",
    ]
    assert refunds == []
    assert run.status == "failed"


def test_an_approval_role_that_may_not_approve_the_risk_is_an_issue() -> None:
    assert issues_of(approving(roles=["support"])) == [
        (
            "states.approve_refund.approval.roles",
            "APPROVAL_ROLE",
            (
                "support may approve no risk, and payments.refund@2 is high risk: name a role "
                "that may approve high risk"
            ),
        )
    ]
    catalog = Catalog()
    catalog.register(payments_refund)
    catalog.register_role("support-lead", approves="medium")
    found = validate(parse_plan(approving()), catalog)
    assert [(i.code, i.message) for i in found] == [
        (
            "APPROVAL_ROLE",
            (
                "support-lead may approve up to medium risk, and payments.refund@2 is high risk: "
                "name a role that may approve high risk"
            ),
        )
    ]


def test_an_approval_from_a_role_that_may_not_approve_the_risk_is_refused() -> None:
    # Never validated: the runtime checks again, on nothing `validate` did.
    run = run_plan(
        approving(roles=["support", "support-lead"]),
        fields=REFUND,
        answers=[("approve_refund", "approve", "ana"), ("approve_refund", "approve", "sam")],
        people=PEOPLE,
    )
    assert refusals(run) == [
        (
            "refused ana's answer approve: support may approve no risk, and payments.refund@2 is "
            "high risk"
        )
    ]
    assert "sam answered approve as support-lead" in lines(run)


def reviewing_then_approving() -> dict[str, Any]:
    """The guide's review-and-pay: support sets the amount, a team lead approves paying it."""
    plan = reviewing()
    plan["states"]["review"]["on"]["accept"] = "approve_refund"
    plan["states"]["approve_refund"] = {
        "approval": {"of": "pay", "roles": ["support-lead"]},
        "on": {"approve": "pay", "reject": "failed"},
    }
    plan["states"]["pay"] = {
        "activity": "payments.refund@2",
        "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
        "on": {"done": "written", "declined": "failed"},
    }
    del plan["states"]["write"]
    return plan


def test_a_person_whose_answer_flows_into_the_step_cannot_approve_it() -> None:
    # Sam is a team lead, but Sam set the amount being paid (brief, D11).
    run = run_plan(
        reviewing_then_approving(),
        fields=ORDER,
        answers=[
            ("review", "accept", "sam", {"approved_amount": Decimal(250)}),
            ("approve_refund", "approve", "sam"),
            ("approve_refund", "approve", "lee"),
        ],
        people={**PEOPLE, "lee": ["support-lead"]},
    )
    assert refusals(run) == [
        (
            "refused sam's answer approve: sam set approved_amount, which pay uses, so cannot "
            "approve it"
        )
    ]
    assert "lee answered approve as support-lead" in lines(run)
    assert run.status == "succeeded"


def test_a_person_whose_answer_decides_the_approval_cannot_give_it() -> None:
    # Ana flagged the order as checked; the approval's `approve` runs pay only if it was. Ana is a
    # team lead here, and still can't approve: her answer decides whether pay runs.
    plan = approving()
    plan["fields"]["checked"] = {"type": "boolean"}
    plan["initial"] = "check"
    plan["states"]["check"] = {
        "wait": {"outcomes": ["done"], "roles": ["support"], "sets": {"done": ["checked"]}},
        "on": {"done": "approve_refund"},
    }
    plan["states"]["approve_refund"]["on"]["approve"] = [
        {"when": {"var": "checked"}, "target": "pay"}
    ]
    run = run_plan(
        plan,
        fields=REFUND,
        answers=[
            ("check", "done", "ana", {"checked": True}),
            ("approve_refund", "approve", "ana"),
            ("approve_refund", "approve", "sam"),
        ],
        people={**PEOPLE, "ana": ["support", "support-lead"]},
    )
    assert refusals(run) == [
        (
            "refused ana's answer approve: ana set checked, which decides whether pay runs, so "
            "cannot approve it"
        )
    ]
    assert run.status == "succeeded"


def amending() -> dict[str, Any]:
    """Review, approval, then a chance to amend the amount before paying. `validate` refuses it
    (APPROVAL_TARGET: approve must lead straight to pay); the runtime checks on its own."""
    plan = reviewing_then_approving()
    plan["states"]["approve_refund"]["on"]["approve"] = "amend"
    plan["states"]["amend"] = {
        "wait": {
            "outcomes": ["amend", "keep"],
            "roles": ["support"],
            "sets": {"amend": ["approved_amount"]},
        },
        "on": {"amend": "pay", "keep": "pay"},
    }
    return plan


def recording_refunds(refunds: list[dict[str, Any]]) -> Any:
    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        refunds.append(inputs)
        return {"refund_id": "r-1"}

    return refund


@pytest.mark.parametrize("amended", [Decimal(300), Decimal(40)])
def test_an_approval_lapses_when_an_input_changes_before_the_step_runs(amended: Decimal) -> None:
    # Up or down, the approval saw other values: it is tied to the values it saw (brief, D11).
    assert "APPROVAL_TARGET" in [code for _, code, _ in issues_of(amending())]
    refunds: list[dict[str, Any]] = []
    run = run_plan(
        amending(),
        fields=ORDER,
        answers=[
            ("review", "accept", "ana", {"approved_amount": Decimal(250)}),
            ("approve_refund", "approve", "sam"),
            ("amend", "amend", "ana", {"approved_amount": amended}),
        ],
        activities={**FAKES, "payments.refund@2": recording_refunds(refunds)},
        people=PEOPLE,
    )
    assert refunds == []
    assert run.status == "stopped"
    assert (
        run.reason == "the inputs of pay changed since sam approved them: a new approval is needed"
    )


def test_an_approval_holds_when_its_inputs_are_unchanged() -> None:
    refunds: list[dict[str, Any]] = []
    run = run_plan(
        amending(),
        fields=ORDER,
        answers=[
            ("review", "accept", "ana", {"approved_amount": Decimal(250)}),
            ("approve_refund", "approve", "sam"),
            ("amend", "keep", "ana"),
        ],
        activities={**FAKES, "payments.refund@2": recording_refunds(refunds)},
        people=PEOPLE,
    )
    assert [r["amount"] for r in refunds] == [Decimal(250)]
    assert run.status == "succeeded"


def test_a_high_risk_activity_nobody_approved_stops_even_unvalidated() -> None:
    plan = approving()
    plan["initial"] = "pay"  # straight to the refund, past the approval
    refunds: list[dict[str, Any]] = []
    run = run_plan(
        plan,
        fields=REFUND,
        answers=[],
        activities={**FAKES, "payments.refund@2": recording_refunds(refunds)},
        people=PEOPLE,
    )
    assert refunds == []
    assert run.reason == "payments.refund@2 is high risk, and nobody approved this run of pay"


def test_an_approval_is_spent_when_its_step_is_scheduled() -> None:
    # Declined, the refund goes straight back to pay: `validate` refuses it (APPROVAL_REUSED), and
    # at runtime the second pass has no approval of its own.
    plan = approving()
    plan["states"]["pay"]["on"]["declined"] = "pay"
    calls: list[dict[str, Any]] = []

    def declines(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs)
        raise Outcome("declined")

    run = run_plan(
        plan,
        fields=REFUND,
        answers=[("approve_refund", "approve", "sam")],
        activities={**FAKES, "payments.refund@2": declines},
        people=PEOPLE,
    )
    assert len(calls) == 1
    assert run.reason == "payments.refund@2 is high risk, and nobody approved this run of pay"


def test_an_approval_of_inputs_that_cannot_be_read_yet_stops_the_step() -> None:
    # Approving before anyone set the amount would approve a value nobody has seen.
    plan = reviewing_then_approving()
    plan["initial"] = "approve_refund"
    run = run_plan(
        plan, fields=ORDER, answers=[("approve_refund", "approve", "sam")], people=PEOPLE
    )
    assert run.status == "stopped"
    assert run.reason is not None
    assert run.reason.startswith("the inputs of pay can't be read: approved_amount")


def test_an_approval_of_something_that_is_no_activity_approves_nothing() -> None:
    # Never validated (APPROVAL_TARGET): the runtime refuses the answer, never guesses.
    run = run_plan(
        approving(of="paid"),
        fields=REFUND,
        answers=[("approve_refund", "approve", "sam")],
        people=PEOPLE,
    )
    assert refusals(run) == [
        "refused sam's answer approve: paid can't be approved: paid is not an activity state"
    ]
    assert run.status == "waiting"


GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "plans.md"
PEOPLE_SECTION = GUIDE.read_text().split("## People in the loop\n")[1].split("\n## ")[0]


def guide_review_and_pay() -> dict[str, Any]:
    """The guide's review then approval, its fourth JSON block."""
    example = GUIDE.read_text().split("```json\n")[4].split("```")[0]
    plan: dict[str, Any] = json.loads(example, parse_float=Decimal)
    return plan


def test_the_guides_people_example_runs_as_written() -> None:
    # Our own documentation, run so it can't drift from the code; never a definition (data).
    code = PEOPLE_SECTION.split("```python\n")[2].split("```")[0]
    namespace: dict[str, Any] = {
        "review_and_pay": guide_review_and_pay(),
        "run_plan": run_plan,
        "sourced": sourced,
        "Decimal": Decimal,
    }
    exec(code, namespace)  # noqa: S102 -- our guide, as in layer 1
    # The plain block under the example: its history, from Ana's answer on.
    start = PEOPLE_SECTION.index("ana answered accept")
    shown = PEOPLE_SECTION[start:].split("```")[0].splitlines()
    history = lines(namespace["run"])
    # The lines the guide shows appear in the run's history, in order; `...` skips some.
    found = [history.index(line) for line in shown if line != "..."]
    assert found == sorted(found)


# Each "Refused when" row of the guide's table, and a run that is refused that way.
GUIDE_REFUSALS: dict[str, Any] = {
    "the outcome isn't one the wait offers": lambda: run_plan(
        approving(), REFUND, [("approve_refund", "aprove", "sam")], people=PEOPLE
    ),
    "the person has none of the wait's roles": lambda: run_plan(
        approving(),
        REFUND,
        [("approve_refund", "approve", "bob")],
        people={"bob": ["support"]},
    ),
    "the form doesn't fit what the outcome sets": lambda: run_plan(
        guide_review_and_pay(),
        ORDER,
        [("review", "accept", "ana", {"approved_amount": "250"})],
        people=PEOPLE,
    ),
    "for an approval: the person's answer flows into what it approves": lambda: run_plan(
        guide_review_and_pay(),
        ORDER,
        [
            ("review", "accept", "ana", {"approved_amount": Decimal(250)}),
            ("approve_refund", "approve", "ana"),
        ],
        people={"ana": ["support", "support-lead"]},
    ),
}


def guide_refusal_rows() -> list[tuple[str, str]]:
    """The rows of the guide's table "Refused when | Example", code unquoted."""
    table = PEOPLE_SECTION.split("| Refused when | Example |")[1].split("\n\n")[0]
    rows = [line.split("|") for line in table.splitlines()[2:] if line.startswith("| ")]
    return [(when.strip(), example.strip().strip("`")) for _, when, example, _ in rows]


@pytest.mark.parametrize(("when", "example"), guide_refusal_rows())
def test_the_guides_refusals_are_what_the_engine_says(when: str, example: str) -> None:
    assert when in GUIDE_REFUSALS, f"the guide's row {when!r} has no test"
    assert example in refusals(GUIDE_REFUSALS[when]())


def test_every_refusal_in_the_guide_is_tested() -> None:
    assert [when for when, _ in guide_refusal_rows()] == list(GUIDE_REFUSALS)


def test_asking_again_withdraws_an_open_approval_so_a_rejection_is_never_outvoted() -> None:
    # From the tutor review, in a plan `validate` refuses: Sam approves, the run goes round and
    # asks again, and Lee rejects. Sam's approval from #1 must not pay the refund (brief, D23).
    plan = approving()
    plan["states"]["approve_refund"]["on"] = {"approve": "note", "reject": "pay"}
    plan["states"]["note"] = {
        "wait": {"outcomes": ["ok"], "roles": ["support"]},
        "on": {"ok": "approve_refund"},
    }
    refunds: list[dict[str, Any]] = []
    run = run_plan(
        plan,
        fields=REFUND,
        answers=[
            ("approve_refund", "approve", "sam"),
            ("note", "ok", "ana"),
            ("approve_refund", "reject", "lee"),
        ],
        activities={**FAKES, "payments.refund@2": recording_refunds(refunds)},
        people={**PEOPLE, "lee": ["support-lead"]},
    )
    assert refunds == []
    assert run.status == "stopped"
    assert run.reason == "payments.refund@2 is high risk, and nobody approved this run of pay"


def customer_typed_amount() -> dict[str, Any]:
    """The review then approval, with `approved_amount` declared as typed by the customer."""
    plan = reviewing_then_approving()
    plan["fields"]["approved_amount"]["source"] = "untrusted:customer"
    return plan


def test_a_form_keeps_the_plans_mark_in_validate() -> None:
    # A mark adds distrust, never removes it: a person's form doesn't wash it off (non-negotiables;
    # tutor review). `payments.refund@2` takes `amount` only from trusted data.
    found = [(path, code) for path, code, _ in issues_of(customer_typed_amount())]
    assert ("states.pay.inputs.amount", "INPUT_POLICY") in found


def test_a_form_keeps_the_plans_mark_at_runtime() -> None:
    refunds: list[dict[str, Any]] = []
    run = run_plan(
        customer_typed_amount(),
        fields=ORDER,
        answers=[
            ("review", "accept", "ana", {"approved_amount": Decimal(250)}),
            ("approve_refund", "approve", "sam"),
        ],
        activities={**FAKES, "payments.refund@2": recording_refunds(refunds)},
        people=PEOPLE,
    )
    assert refunds == []
    assert run.status == "stopped"
    assert run.reason is not None
    assert run.reason.startswith("payments.refund@2 takes amount only from a system or a person")
    assert "untrusted:customer" in run.reason


@pytest.mark.parametrize("spelled", ["Sam", " sam", "person:sam"])
def test_a_person_spelled_any_other_way_is_refused_and_the_wait_goes_on(spelled: str) -> None:
    # From the tutor review: Sam sets the amount, then "Sam" approves, and "someone else" is
    # defeated by a spelling. An identifier is written one way (brief, D22); fail closed.
    run = run_plan(
        reviewing_then_approving(),
        fields=ORDER,
        answers=[
            ("review", "accept", "sam", {"approved_amount": Decimal(250)}),
            ("approve_refund", "approve", spelled),
        ],
        people={**PEOPLE, spelled: ["support", "support-lead"]},
    )
    assert refusals(run) == [
        (
            f"refused {spelled}'s answer approve: {spelled!r} is not written as a person's "
            "identifier: lowercase letters, digits, ., _, @ and -, starting with a letter or digit, "
            "such as ana or ana.lee@example.com"
        )
    ]
    assert run.status == "waiting"  # the wait goes on


def test_an_identifier_may_be_a_lowercase_email() -> None:
    run = run_plan(
        asking(),
        fields=ORDER,
        answers=[("confirm", "accept", "ana.lee@example.com")],
        people={"ana.lee@example.com": ["support"]},
    )
    assert "ana.lee@example.com answered accept as support" in lines(run)
