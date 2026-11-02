"""Options: one of a system's list, checked through that system's activity when a person gives it.

See docs/layers/16-field-types.md (16b), docs/guides/case-data.md ("Options") and brief D67.
"""

import copy
from typing import Annotated, Any

import pytest
from pydantic import BaseModel
from test_case import contract

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.output_sources import source
from ventoux.core.references import reference
from ventoux.testing import CATALOG, CaseRefused, run_case


class BranchAsked(BaseModel):
    option: Annotated[str, reference("branches")]  # the value a person gave


class BranchHeld(BaseModel):
    held: Annotated[bool, source("system:branches")]  # whether the branches system holds it


def with_branches() -> Catalog:
    """The development catalog, with the `branches` system."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register_system("branches")
    return catalog


def test_an_option_check_that_writes_is_refused() -> None:
    # An option's check only asks: it never changes the system it asks (brief, D67).
    catalog = with_branches()
    catalog.register(
        contract(
            "branches.reserve",
            BranchAsked,
            BranchHeld,
            effect="write",
            idempotency_key="option",
        )
    )
    with pytest.raises(ValueError) as refused:
        catalog.register_option_check("branches", "branches.reserve@1")
    assert str(refused.value) == (
        "branches.reserve@1 is effect: write, and an option's check only reads: register a "
        "read-only activity that says whether branches holds a value"
    )


class Code(BaseModel):
    code: str  # not a reference: the value's system isn't said


class Found(BaseModel):
    found: Annotated[bool, source("system:branches")]


class HeldByCrm(BaseModel):
    held: Annotated[bool, source("system:crm")]  # another system's word for it


def registered(catalog: Catalog, name: str, given: type[BaseModel], gives: type[BaseModel]) -> str:
    catalog.register(contract(name, given, gives))
    return f"{name}@1"


@pytest.mark.parametrize(
    ("given", "gives", "system", "refused"),
    [
        (
            Code,
            BranchHeld,
            "branches",
            (
                "branches.code@1 takes code, and an option's check takes one value, option, a "
                'reference to branches: declare it Annotated[str, reference("branches")]'
            ),
        ),
        (
            BranchAsked,
            Found,
            "branches",
            (
                "branches.code@1 gives found (system:branches), and an option's check gives one "
                "truth value, held, from system:branches: declare it Annotated[bool, "
                'source("system:branches")]'
            ),
        ),
        (
            BranchAsked,
            HeldByCrm,
            "branches",
            (
                "branches.code@1 gives held (system:crm), and an option's check gives one truth "
                "value, held, from system:branches: declare it Annotated[bool, "
                'source("system:branches")]'
            ),
        ),
    ],
    ids=["input not a reference", "output not held", "held from another system"],
)
def test_an_option_check_of_another_shape_is_refused(
    given: type[BaseModel], gives: type[BaseModel], system: str, refused: str
) -> None:
    catalog = with_branches()
    check = registered(catalog, "branches.code", given, gives)
    with pytest.raises(ValueError) as raised:
        catalog.register_option_check(system, check)
    assert str(raised.value) == refused


def test_a_second_option_check_for_one_system_is_refused() -> None:
    catalog = with_branches()
    first = registered(catalog, "branches.holds", BranchAsked, BranchHeld)
    second = registered(catalog, "branches.open", BranchAsked, BranchHeld)
    catalog.register_option_check("branches", first)
    with pytest.raises(ValueError) as raised:
        catalog.register_option_check("branches", second)
    assert str(raised.value) == (
        "branches has an option check already, branches.holds@1: a system has one"
    )


def test_a_read_only_check_of_the_right_shape_is_how_its_system_is_asked() -> None:
    catalog = with_branches()
    check = registered(catalog, "branches.holds", BranchAsked, BranchHeld)
    assert catalog.option_check("branches") is None  # no check yet: nothing can check an option
    catalog.register_option_check("branches", check)
    assert catalog.option_check("branches") == "branches.holds@1"


# --- Slice 2: the type, and what validation refuses ---


def claim() -> dict[str, Any]:
    """A claim whose adjuster says which branch handles it, an option of `branches`."""
    return {
        "case": "claim",
        "display": {"title": "Insurance claim"},
        "fields": {
            "branch": {
                "type": "option",
                "system": "branches",
                "display": {"title": "Branch handling the claim"},
            }
        },
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess the claim"},
                "roles": ["adjuster"],
                "outcomes": {
                    "accept": {"display": {"title": "Accept the claim"}, "sets": ["branch"]},
                    "deny": {"display": {"title": "Deny the claim"}},
                },
            }
        },
    }


def errors(definition: dict[str, Any], catalog: Catalog) -> list[str]:
    """What validation refuses, as `path: CODE: message`."""
    found = validate_case(parse_case(definition), catalog)
    return [f"{i.path}: {i.code}: {i.message}" for i in found if i.severity == "error"]


def test_an_option_of_a_system_with_no_check_is_refused() -> None:
    # Fail closed: nothing could check it, so nothing would vouch for the answer (brief, D67).
    assert errors(claim(), with_branches()) == [
        (
            "fields.branch: UNCHECKED_OPTION: branch is an option of branches, and branches has no "
            "option check: ask the platform team to register one, or make branch a reference"
        )
    ]


def checked() -> Catalog:
    """The catalog with `branches` and its option check, `branches.holds@1`."""
    catalog = with_branches()
    catalog.register_option_check(
        "branches", registered(catalog, "branches.holds", BranchAsked, BranchHeld)
    )
    return catalog


def test_an_option_a_person_gives_with_its_systems_check_is_accepted() -> None:
    assert errors(claim(), checked()) == []


def test_an_event_carrying_an_option_is_refused() -> None:
    # Only a person gives an option: nothing would check one an event carried (brief, D67).
    definition = claim()
    definition["events"] = {
        "moved": {
            "display": {"title": "The claim moves branch"},
            "sent_by": {"system": "portal"},
            "payload": {"to": {"type": "option", "system": "branches", "display": {"title": "To"}}},
        }
    }
    assert errors(definition, checked()) == [
        (
            "events.moved.payload.to: OPTION_NOT_GIVEN_BY_A_PERSON: to is an option of branches, and "
            "only a person's answer gives one, when it can be checked: make it a reference to branches"
        )
    ]


def with_usual() -> dict[str, Any]:
    """The claim, with `usual`, an option of `branches` no task sets: a person's answer sets
    `branch`, and the one-source rule already keeps rules and the opening off it."""
    definition = claim()
    definition["fields"]["usual"] = {
        "type": "option",
        "system": "branches",
        "display": {"title": "Usual branch"},
    }
    return definition


def test_a_rule_setting_an_option_is_refused() -> None:
    definition = with_usual()
    definition["rules"] = {
        "default_branch": {
            "display": {"title": "Handle it where it usually is"},
            "on": {"answered": "assess"},
            "then": {"set": {"usual": {"var": "branch"}}},
        }
    }
    assert errors(definition, checked()) == [
        (
            "rules.default_branch.then.set.usual: OPTION_NOT_GIVEN_BY_A_PERSON: usual is an option "
            "of branches, and only a person's answer gives one, when it can be checked: set it in a "
            "task's form"
        )
    ]


def test_an_option_given_at_the_opening_is_refused() -> None:
    with pytest.raises(CaseRefused) as refused:
        run_case(
            with_usual(),
            file={"usual": "BR-0142"},
            answers=[],
            people={"ana": ["adjuster"]},
            catalog=checked(),
        )
    assert str(refused.value) == (
        "usual is an option of branches, and only a person's answer gives one, when it can be "
        "checked: leave it out of the opening"
    )
