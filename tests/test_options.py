"""Options: one of a system's list, checked through that system's activity when a person gives it.

See docs/layers/16-field-types.md (16b), docs/guides/case-data.md ("Options") and brief D67.
"""

import copy
from typing import Annotated

import pytest
from pydantic import BaseModel
from test_case import contract

from ventoux.core.catalog import Catalog
from ventoux.core.output_sources import source
from ventoux.core.references import reference
from ventoux.testing import CATALOG


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
