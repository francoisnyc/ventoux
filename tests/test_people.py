"""People in the loop: roles, forms and approvals (layer 7).

Tests go through the catalog, `parse_plan`, `validate` and `run_plan`, and read what a run reports.
See docs/layers/07-people.md and docs/guides/plans.md, "People in the loop".
"""

from typing import Any

import pytest

from ventoux.core.catalog import Catalog
from ventoux.core.interpreter import PlanRun
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.core.provenance import sourced
from ventoux.core.validate import validate
from ventoux.testing import CATALOG, run_plan


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
