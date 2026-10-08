"""People in the loop: roles, forms and approvals (layer 7).

Tests go through the catalog, `parse_plan`, `validate` and `run_plan`, and read what a run reports.
See docs/layers/07-people.md and docs/guides/plans.md, "People in the loop".
"""

from decimal import Decimal
from typing import Annotated, Any

import pytest
from pydantic import BaseModel

from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.interpreter import PlanRun, RunRefused
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.core.policy import only_from
from ventoux.core.provenance import sourced
from ventoux.core.validate import validate
from ventoux.testing import CATALOG, FAKES, run_plan


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
    with pytest.raises(PlanInvalid, match="states.confirm.wait.roles: a wait names at least one"):
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
