"""The authoring loop (layer 15c): a model drafts a plan, checked as a release checks it; the
problems go back, for a bounded number of rounds; then it is drafted, or abandoned.

See docs/layers/15-authoring.md (15c) and brief D63.
"""

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.authoring.loop import Authored, DraftRefused, author
from ventoux.authoring.provider import Message, ProviderFailed, Recorded, Request
from ventoux.case.releases import Package, package
from ventoux.testing import CATALOG

ROOT = Path(__file__).parent.parent
SCHEMA: dict[str, Any] = json.loads((ROOT / "schema" / "plan.schema.json").read_text())
GOAL = "Refund the order, then draft a letter telling the customer it is on its way."


def read(path: Path) -> Any:
    return json.loads(path.read_text(), parse_float=Decimal)


def refund_case() -> dict[str, Any]:
    """The refund package's case, its plan step also given the customer's note (untrusted) and
    their email (from the system that opens the case)."""
    case: dict[str, Any] = read(ROOT / "examples" / "packages" / "refund" / "case.json")
    case["fields"]["note"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The customer's note"},
    }
    case["fields"]["customer_email"] = {
        "type": "string",
        "display": {"title": "The customer's email"},
    }
    case["steps"]["settle"]["inputs"] |= {
        "note": {"var": "note"},
        "customer_email": {"var": "customer_email"},
    }
    return case


def refund_plan() -> dict[str, Any]:
    """The refund package's plan as it is, taking the two fields the step gives it."""
    plan: dict[str, Any] = read(
        ROOT / "examples" / "packages" / "refund" / "plans" / "refund-order.json"
    )
    plan["fields"] |= {"note": {"type": "string"}, "customer_email": {"type": "string"}}
    return plan


def written(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


def the_package() -> Package:
    return package(written(refund_case()), [written(refund_plan())])


def with_letter(to_customer: str) -> dict[str, Any]:
    """The plan, drafting a letter to the customer after the refund, its address read from
    the plan field `to_customer` names."""
    plan = refund_plan()
    plan["states"]["pay"]["on"]["done"] = "write_letter"
    plan["states"]["write_letter"] = {
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": to_customer}, "template": "refund-sent"},
        "on": {"done": "paid"},
    }
    return plan


TO_THE_NOTE = written(with_letter("note"))  # untrusted data reaching a trusted_only input
TO_THE_EMAIL = written(with_letter("customer_email"))  # the repair
INPUT_POLICY = (
    "steps.settle.inputs.note: INPUT_POLICY: refund-order@1, in its state write_letter: "
    "letters.draft@2 takes to_customer only from a system or a person, never from untrusted "
    "data, and this value comes from note (the opener, untrusted:customer): use a value a system "
    "or a person gave"
)


def drafted_by(*answers: str, rounds: int = 3) -> Authored:
    """What the loop makes of a model that answers `answers`, in order."""
    provider = Recorded.answering(*answers)
    return asyncio.run(
        author(GOAL, the_package(), "refund-order@1", CATALOG, SCHEMA, provider, rounds)
    )


def test_untrusted_data_reaching_a_trusted_only_input_never_repaired_is_abandoned() -> None:
    # The curriculum's negative test, first flow: refused each round, and after the last the
    # draft is abandoned, saying why, with no plan (brief, D63).
    authored = drafted_by(TO_THE_NOTE, TO_THE_NOTE, TO_THE_NOTE)
    assert authored.verdict == "abandoned"
    assert authored.plan is None
    assert [each.problems for each in authored.rounds] == [(INPUT_POLICY,)] * 3
    assert authored.reason == "abandoned after 3 rounds: the last draft still has 1 problem"


def test_untrusted_data_reaching_a_trusted_only_input_repaired_is_drafted() -> None:
    authored = drafted_by(TO_THE_NOTE, TO_THE_EMAIL)
    assert authored.verdict == "drafted"
    assert authored.plan == TO_THE_EMAIL + "\n"  # as a file ends
    assert [each.problems for each in authored.rounds] == [(INPUT_POLICY,), ()]
    assert authored.reason is None


def branching_on_the_note() -> dict[str, Any]:
    """The repaired letter, sent only when the customer's note says "urgent": a path chosen by
    untrusted data (brief, D49)."""
    plan = with_letter("customer_email")
    plan["states"]["pay"]["on"]["done"] = [
        {"target": "write_letter", "when": {"==": [{"var": "note"}, "urgent"]}},
        {"target": "paid"},
    ]
    return plan


UNTRUSTED_TRIGGER = (
    "steps.settle.inputs.note: UNTRUSTED_TRIGGER: refund-order@1 branches on note (in pay, the "
    "transition to write_letter), and this input reads note, which comes from untrusted:customer "
    "whoever writes it, and untrusted data can't choose a plan's path, so the plan stops whenever "
    "it tries that transition: give it a value a person or a trusted system gives, or branch in "
    "the case"
)


def test_a_transition_reading_untrusted_data_is_refused_then_repaired() -> None:
    # The curriculum's negative test, second flow (brief, D49).
    authored = drafted_by(written(branching_on_the_note()), TO_THE_EMAIL)
    assert authored.verdict == "drafted"
    assert [each.problems for each in authored.rounds] == [(UNTRUSTED_TRIGGER,), ()]


def back_to_pay_on_a_decline() -> dict[str, Any]:
    """The plan, trying the refund again when it is declined: a high-risk activity reached
    again on the approval already spent (brief, D11)."""
    plan = refund_plan()
    plan["states"]["pay"]["on"]["declined"] = "pay"
    return plan


APPROVAL_REUSED = (
    "plans.refund-order@1.states.pay: APPROVAL_REUSED: one approval would unlock two high-risk "
    "runs: after pay, pay can run without a new approval: add an approval before pay"
)


def test_a_loop_back_to_a_high_risk_activity_is_refused_then_repaired() -> None:
    # Added from the warm-up on learning question 33: one approval unlocks one run.
    authored = drafted_by(written(back_to_pay_on_a_decline()), written(refund_plan()))
    assert authored.verdict == "drafted"
    assert [each.problems for each in authored.rounds] == [(APPROVAL_REUSED,), ()]


class Asked:
    """A provider that keeps every request it is sent, and answers `answers` in order."""

    name = "asked"

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.requests: list[Request] = []

    async def complete(self, request: Request) -> str:
        self.requests.append(request)
        return self.answers.pop(0)


def asked_with(provider: Asked, rounds: int = 3) -> Authored:
    return asyncio.run(
        author(GOAL, the_package(), "refund-order@1", CATALOG, SCHEMA, provider, rounds)
    )


def test_the_problems_go_back_in_the_fixed_form_after_the_models_own_answer() -> None:
    provider = Asked(TO_THE_NOTE, TO_THE_EMAIL)
    asked_with(provider)
    first, second = provider.requests
    assert second.system == first.system
    assert second.messages[:1] == first.messages
    assert second.messages[1] == Message("assistant", TO_THE_NOTE)
    assert second.messages[2] == Message(
        "user",
        "The draft was refused. Fix every problem below and answer with the whole plan, as one "
        f"JSON object.\n{INPUT_POLICY}",
    )


NOT_JSON = (
    "answer: NOT_ONE_OBJECT: the answer is not one JSON object: not JSON: Expecting value at line "
    "1, column 1"
)
WRONG_PLAN = (
    "plan: WRONG_PLAN: the draft is evergreen@1, and the package's step names refund-order@1"
)


@pytest.mark.parametrize(
    ("answer", "problem"),
    [
        (
            "Here is the plan.",
            NOT_JSON,
        ),
        (
            f"Sure:\n```json\n{TO_THE_EMAIL}\n```",  # prose around one fenced block
            NOT_JSON,
        ),
        (
            f"[{TO_THE_EMAIL}]",
            "answer: NOT_ONE_OBJECT: the answer is not one JSON object: JSON, but not one object",
        ),
        (
            '{"plan": "refund-order", "plan": "evergreen"}',
            "answer: NOT_ONE_OBJECT: the answer is not one JSON object: a key is given twice: plan",
        ),
        (
            '{"plan": "refund-order", "version": 1}',
            "display: SHAPE: required",
        ),
        (
            written(refund_plan() | {"plan": "evergreen"}),
            WRONG_PLAN,
        ),
    ],
)
def test_an_answer_that_isnt_a_draft_of_the_plan_is_a_problem_fed_back(
    answer: str, problem: str
) -> None:
    # Never scraped: prose around a block, a list, a key twice are problems, as for the advisor's
    # answer (brief, D61) (brief, D63).
    authored = drafted_by(answer, TO_THE_EMAIL)
    assert authored.rounds[0].problems[0] == problem
    assert authored.verdict == "drafted"


class Failing:
    """A provider whose model gives no answer, as the live one fails closed (brief, D62)."""

    name = "failing"

    async def complete(self, request: Request) -> str:
        raise ProviderFailed("the model refused to answer")


def test_a_provider_that_gives_no_answer_stops_the_loop_saying_why() -> None:
    authored = asyncio.run(
        author(GOAL, the_package(), "refund-order@1", CATALOG, SCHEMA, Failing(), 3)
    )
    assert authored == Authored(
        "no answer", None, (), "the authoring model gave no answer: the model refused to answer"
    )


def test_the_model_is_shown_the_step_its_sources_the_catalog_and_the_plan_never_a_case() -> None:
    provider = Asked(TO_THE_EMAIL)
    asked_with(provider)
    [request] = provider.requests
    shown = json.loads(request.messages[0].content)
    assert shown["goal"] == GOAL
    assert shown["plan_to_draft"] == {"plan": "refund-order", "version": 1}
    assert shown["the_step_that_runs_it"] == {
        "step": "settle",
        "title": "Settle the refund",
        "fields_it_gives_and_their_sources": {
            "order_id": ["system:opener"],
            "amount": ["person"],  # a person's answer, said only as `person`
            "note": ["system:opener", "untrusted:customer"],
            "customer_email": ["system:opener"],
        },
    }
    assert [each["name"] for each in shown["contracts"]] == [
        contract.name for contract in CATALOG.contracts()
    ]
    assert shown["roles_and_the_risk_each_may_approve"] == CATALOG.roles
    assert shown["source_labels"] == CATALOG.labels
    assert shown["systems"] == CATALOG.systems
    assert shown["the_plan_as_it_is"] == json.loads(written(refund_plan()))
    assert set(shown) == {
        "goal",
        "plan_to_draft",
        "the_step_that_runs_it",
        "contracts",
        "roles_and_the_risk_each_may_approve",
        "source_labels",
        "systems",
        "the_plan_as_it_is",
    }  # and nothing else: no case file, no implementation
    assert json.dumps(SCHEMA, indent=2) in request.system


@pytest.mark.parametrize("rounds", [0, 6])
def test_rounds_out_of_bounds_are_refused_before_anything_is_asked(rounds: int) -> None:
    provider = Asked(TO_THE_EMAIL)
    with pytest.raises(DraftRefused) as refused:
        asked_with(provider, rounds)
    assert str(refused.value) == f"--rounds is {rounds}: a loop takes 1 to 5 rounds"
    assert provider.requests == []


def test_a_plan_no_step_names_is_refused_before_anything_is_asked() -> None:
    provider = Asked(TO_THE_EMAIL)
    with pytest.raises(DraftRefused) as refused:
        asyncio.run(author(GOAL, the_package(), "evergreen@1", CATALOG, SCHEMA, provider, 3))
    assert str(refused.value) == (
        "evergreen@1 is run by no plan step of refund: draft a plan one of its steps names"
    )
    assert provider.requests == []
