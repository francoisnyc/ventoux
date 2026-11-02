"""Options: one of a system's list, checked through that system's activity when a person gives it.

See docs/layers/16-field-types.md (16b), docs/guides/case-data.md ("Options") and brief D67.
"""

import copy
from typing import Annotated, Any

import pytest
from pydantic import BaseModel
from test_case import contract

from ventoux.case.answers import AnswerRefused
from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import (
    BooleanType,
    ExpressionInvalid,
    FieldType,
    OptionType,
    ReferenceType,
    StringType,
    check,
    parse_expression,
)
from ventoux.core.output_sources import source
from ventoux.core.references import reference
from ventoux.testing import CATALOG, CaseRefused, close, finish, run_case


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


# --- Slice 3: the curriculum's negative test, an answer held while it is checked ---

OPEN_BRANCHES = {"BR-0142", "BR-0007"}  # what the branches system holds, in these tests
ADJUSTERS = {"ana": ["adjuster"]}


def holds(inputs: dict[str, Any]) -> dict[str, Any]:
    """The branches system's answer: whether it holds the option asked about."""
    return {"held": inputs["option"] in OPEN_BRANCHES}


def test_an_option_the_system_does_not_hold_is_refused_and_the_refusal_recorded() -> None:
    run = run_case(
        claim(),
        file={},
        answers=[
            ("assess", "accept", "ana", {"branch": "BR-9999"}),  # no such branch
            ("assess", "accept", "ana", {"branch": "BR-0142"}),  # corrected
        ],
        people=ADJUSTERS,
        activities={"branches.holds@1": holds},
        catalog=checked(),
    )
    # The refusal names the field and the system, never the value (brief, D30) (brief, D67); the
    # task stays open, and the corrected answer is taken, saying which check vouched for it.
    assert run.history == [
        "opened by system:opener, with nothing",
        "started assess#1: waiting for accept or deny by adjuster",
        "refused ana's answer accept: branch is not one of the options branches holds",
        "ana answered assess#1 accept as adjuster, setting branch, checked by branches.holds@1",
        "assess#1 done",
        "closed: nothing left to do",
    ]
    # Nothing the refused answer set landed: the corrected one is what the case holds.
    assert run.state.values["branch"] == "BR-0142"


# --- Slice 4: a held option is taken, from the person and the system that vouched ---


def test_an_option_the_system_holds_comes_from_the_person_and_the_system() -> None:
    run = run_case(
        claim(),
        file={},
        answers=[("assess", "accept", "ana", {"branch": "BR-0142"})],
        people=ADJUSTERS,
        activities={"branches.holds@1": holds},
        catalog=checked(),
    )
    # Ana chose it, and branches vouched for it: both are where it came from (brief, D67).
    assert run.state.values["branch"] == "BR-0142"
    assert run.state.sources["branch"] == frozenset({"person:ana", "system:branches"})
    # The outcome is Ana's alone: a system vouches for a value, never for an answer.
    assert run.state.sources["assess.outcome"] == frozenset({"person:ana"})


# --- Slice 5: a check that can't be made takes nothing, and the answer can be given again ---


def broken(inputs: dict[str, Any]) -> dict[str, Any]:
    """The branches system is down."""
    raise RuntimeError("branches is down")


def garbled(inputs: dict[str, Any]) -> dict[str, Any]:
    """The branches system answers something its contract doesn't describe."""
    return {"yes": True}


@pytest.mark.parametrize(
    ("check", "why"),
    [
        (broken, "branches.holds@1 failed with RuntimeError: ‹sensitive›"),
        (
            garbled,
            "branches.holds@1 gave an output its contract doesn't declare: held: Field required",
        ),
    ],
    ids=["the check fails", "the check answers another shape"],
)
def test_an_option_whose_check_cannot_be_made_is_not_taken(check: Any, why: str) -> None:
    # Fail closed: never read as held; and nothing failed that answering again can't fix, so the
    # case doesn't need attention (brief, D67).
    run = run_case(
        claim(),
        file={},
        answers=[("assess", "accept", "ana", {"branch": "BR-0142"})],
        people=ADJUSTERS,
        activities={"branches.holds@1": check},
        catalog=checked(),
    )
    assert run.history[-1] == (
        f"ana's answer accept to assess#1 is not taken: {why}; the task waits for an answer"
    )
    assert "branch" not in run.state.values
    assert list(run.state.waiting) == ["assess#1"]  # the task is open for a new answer
    assert run.needs_attention == []


# --- Slice 6: an answer being checked takes no second answer, and a close waits for it ---

FIRST = ("assess", "accept", "ana", {"branch": "BR-0142"})


def test_a_second_answer_while_the_first_is_checked_is_refused() -> None:
    with pytest.raises(AnswerRefused) as refused:
        run_case(
            claim(),
            file={},
            answers=[FIRST, ("assess", "deny", "ana")],
            people=ADJUSTERS,
            activities={"branches.holds@1": holds},
            catalog=checked(),
            held=["assess"],  # its check keeps running
        )
    assert str(refused.value) == (
        "assess#1 is being checked: its answer is taken, or refused, once branches answers"
    )


def closable() -> dict[str, Any]:
    definition = claim()
    definition["close_reasons"] = {
        "withdrawn": {"display": {"title": "Withdrawn"}, "roles": ["adjuster"]}
    }
    return definition


def test_a_close_waits_for_a_running_check_and_the_held_answer_is_not_taken() -> None:
    def closed(*more: Any) -> Any:
        return run_case(
            closable(),
            file={},
            answers=[FIRST, close("withdrawn", "ana"), *more],
            people=ADJUSTERS,
            activities={"branches.holds@1": holds},
            catalog=checked(),
            held=["assess"],
        )

    # Its check runs, as any activity does: the case closes once it finishes (brief, D10).
    assert closed().status == "closing"
    run = closed(finish("assess#1.branch"))
    assert run.status == "closed"
    assert "branch" not in run.state.values  # its task was cancelled by the close
    assert run.history[-2:] == [
        "ana's answer accept to assess#1 is not taken: the case closed while it was checked",
        "closed: withdrawn, by ana",
    ]


# --- Slice 7: expressions read an option like a reference to its system ---

TYPES: dict[str, FieldType] = {
    "branch": OptionType(system="branches"),
    "usual": OptionType(system="branches"),
    "home": ReferenceType(system="branches"),
    "customer": ReferenceType(system="crm"),
    "elsewhere": OptionType(system="crm"),
}


@pytest.mark.parametrize(
    "other", ["usual", "home"], ids=["an option of its system", "a reference to its system"]
)
def test_an_option_compares_with_a_value_of_its_system(other: str) -> None:
    compared = parse_expression({"==": [{"var": "branch"}, {"var": other}]})
    assert check(compared, TYPES) == BooleanType()


@pytest.mark.parametrize(
    ("other", "refused"),
    [
        (
            "customer",
            (
                "==[1]: `==` compares values of the same type, and this is a reference to "
                "crm, not an option of branches"
            ),
        ),
        (
            "elsewhere",
            (
                "==[1]: `==` compares values of the same type, and this is an option of "
                "crm, not an option of branches"
            ),
        ),
    ],
    ids=["a reference to another system", "an option of another system"],
)
def test_an_option_never_compares_with_another_systems_value(other: str, refused: str) -> None:
    with pytest.raises(ExpressionInvalid) as raised:
        check(parse_expression({"==": [{"var": "branch"}, {"var": other}]}), TYPES)
    assert str(raised.value) == refused


def test_string_of_an_option_is_a_text() -> None:
    assert check(parse_expression({"string": [{"var": "branch"}]}), TYPES) == StringType()


class Routed(BaseModel):
    branch: Annotated[str, reference("branches")]  # a reference to the branch to route it to


class Routing(BaseModel):
    routed: bool


def test_an_option_goes_where_a_reference_to_its_system_is_wanted() -> None:
    # An option is a reference to its system, and a checked one (brief, D67).
    catalog = checked()
    catalog.register(contract("branches.route", Routed, Routing))
    definition = claim()
    definition["steps"]["route"] = {
        "kind": "activity",
        "display": {"title": "Route the claim"},
        "activity": "branches.route@1",
        "requires": ["assess"],
        "inputs": {"branch": {"var": "branch"}},
    }
    assert errors(definition, catalog) == []
