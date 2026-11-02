"""Options: one of a system's list, checked through that system's activity when a person gives it.

See docs/layers/16-field-types.md (16b), docs/guides/case-data.md ("Options") and brief D67.
"""

import copy
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel
from test_case import contract

from ventoux.case.answers import AnswerRefused
from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.contract_hash import contract_hash
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
from ventoux.temporal.carried import state_as_data
from ventoux.testing import (
    CATALOG,
    BranchAsked,
    BranchHeld,
    CaseRefused,
    ChangeRefused,
    branches_holds,
    close,
    edit,
    finish,
    later,
    run_case,
)
from ventoux.tooling.builder import Case, Field
from ventoux.tooling.cli import main


def with_branches() -> Catalog:
    """A catalog with the `branches` system and no option check yet: the development catalog
    registers one, `branches.holds@1`, and a system has one."""
    catalog = Catalog()
    for system in ("branches", "crm"):  # crm: a check that answers in another system's name
        catalog.register_system(system)
    catalog.register_role("adjuster")
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
    """The development catalog, with `branches` and its option check, `branches.holds@1`."""
    return copy.deepcopy(CATALOG)


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


# --- Slice 8: an option is a fact with its time ---


def test_a_stale_option_needs_attention_where_it_must_be_fresh() -> None:
    # "BR-0142 was held when Ana answered" stays true; a step that needs it still held says so with
    # max_age, and an option given by a person can't be fetched again (brief, D18) (brief, D67).
    catalog = checked()
    catalog.register(contract("branches.route", Routed, Routing))
    definition = claim()
    definition["steps"]["confirm"] = {
        "kind": "task",
        "display": {"title": "Confirm the claim"},
        "roles": ["adjuster"],
        "outcomes": {"ok": {"display": {"title": "Confirmed"}}},
    }
    definition["steps"]["route"] = {
        "kind": "activity",
        "display": {"title": "Route the claim"},
        "activity": "branches.route@1",
        "requires": ["assess", "confirm"],
        "when": {"exists": "branch"},
        "inputs": {"branch": {"var": "branch"}},
        "max_age": {"branch": "1d"},
    }
    run = run_case(
        definition,
        file={},
        answers=[FIRST, later("3d"), ("confirm", "ok", "ana")],
        people=ADJUSTERS,
        activities={"branches.holds@1": holds, "branches.route@1": lambda i: {"routed": True}},
        catalog=catalog,
    )
    assert run.needs_attention == [
        (
            "route#1: branch was obtained 3 days ago, and route needs it at most 1 day old: it "
            "came from a person, so it can't be fetched again"
        )
    ]


# --- Slice 10: the builder declares an option, read like a reference to its system ---


def test_the_builder_refuses_a_text_beside_an_option() -> None:
    # A text says nothing about which system holds it: an option compares with an option or a
    # reference of its system, as the expression check says (brief, D67).
    claim = Case("claim", title="Insurance claim")
    branch = claim.field("branch", Field.option("branches"), title="Branch handling the claim")
    with pytest.raises(TypeError) as refused:
        branch == "BR-0142"  # noqa: B015
    assert str(refused.value) == "'BR-0142' can't be compared with ReferenceExpr"


def test_the_case_map_reads_an_option_with_its_system(capsys: pytest.CaptureFixture[str]) -> None:
    # The map says which system's list it is, and that a person's answer is checked against it.
    assert main(["map", str(Path(__file__).parent / "digests" / "options")]) == 0
    assert "branch is an option of branches, checked when given" in capsys.readouterr().out


def test_the_plain_diff_reports_an_option_moved_to_another_system(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pinned = Path(__file__).parent / "digests" / "options"
    moved = tmp_path / "moved"
    moved.mkdir()
    text = (pinned / "case.json").read_text()
    (moved / "case.json").write_text(text.replace('"branches"', '"depots"'))
    main(["diff", "--plain", str(pinned), str(moved)])
    shown = capsys.readouterr().out
    # Another system's list is another field: what was checked against branches no longer is.
    assert "- Before: branch is an option of branches, checked when given" in shown
    assert "- After: branch is an option of depots, checked when given" in shown
    assert "(`fields.branch.system`): branches -&gt; depots." in shown


# --- Step 6: promises with no test of their own until now ---


def looked_up_once_branched() -> dict[str, Any]:
    """The claim, its order looked up behind a team lead's approval, started by a rule whose
    condition reads `branch`."""
    definition = claim()
    definition["fields"]["order_id"] = {
        "type": "reference",
        "system": "orders",
        "display": {"title": "Order"},
    }
    definition["steps"]["look"] = {
        "kind": "activity",
        "display": {"title": "Look up the order"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "approval": {"roles": ["support-lead"], "display": {"reason": "A lead looks first"}},
        "automatic": False,
    }
    definition["rules"] = {
        "start_look": {
            "display": {"title": "Look up the order once a branch is chosen"},
            "on": {"answered": "assess"},
            "when": {"exists": "branch"},
            "then": {"start": ["look"]},
        }
    }
    return definition


def test_whoever_gave_an_option_a_rule_read_cant_approve_what_it_started() -> None:
    # Ana chose the branch, and the rule's condition read it: her answer decided that the lookup
    # runs, so she can't approve it. The system that vouched for it is no person, and excludes
    # nobody; Lee may approve (brief, D11) (brief, D39) (brief, D67).
    people = {"ana": ["adjuster", "support-lead"], "lee": ["support-lead"]}
    branched = ("assess", "accept", "ana", {"branch": "BR-0142"})

    def approved_by(who: str) -> Any:
        return run_case(
            looked_up_once_branched(),
            file={"order_id": "ord-1"},
            answers=[branched, ("look.approval#1", "approve", who)],
            people=people,
            activities={"branches.holds@1": holds},
            catalog=checked(),
        )

    with pytest.raises(AnswerRefused) as refused:
        approved_by("ana")
    assert str(refused.value) == (
        "ana set branch, which decided that start_look#1 started look, so cannot approve it"
    )
    assert "look#1 done" in " ".join(approved_by("lee").history)


def test_the_activities_guides_option_check_is_the_development_one() -> None:
    # The guide's block, run so it can't drift from the code: it registers, and it is the check
    # the development catalog registers for branches (our own documentation, never a definition).
    guide = (Path(__file__).parent.parent / "docs" / "guides" / "activities.md").read_text()
    example = guide.split("## An option's check")[1].split("```python\n")[1].split("```")[0]
    namespace: dict[str, Any] = {"catalog": with_branches()}
    exec(example, namespace)  # noqa: S102 -- our guide
    assert namespace["catalog"].option_check("branches") == "branches.holds@1"
    assert contract_hash(namespace["holds"]) == contract_hash(branches_holds)


def test_a_held_answer_is_never_carried_to_a_new_run() -> None:
    # A case continues as new only when nothing runs; were it ever asked to carry a held answer,
    # carrying it is refused, never the answer quietly dropped (brief, D27) (brief, D67).
    run = run_case(
        claim(),
        file={},
        answers=[("assess", "accept", "ana", {"branch": "BR-0142"})],
        people=ADJUSTERS,
        activities={"branches.holds@1": holds},
        catalog=checked(),
        held=["assess"],  # its check keeps running
    )
    with pytest.raises(ValueError) as refused:
        state_as_data(run.state)
    assert str(refused.value) == (
        "assess#1 is being checked: a case never continues as new while an answer is held"
    )


def test_the_plain_diff_reports_a_reference_become_an_option(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pinned = Path(__file__).parent / "digests" / "options"
    unchecked = tmp_path / "reference"
    unchecked.mkdir()
    text = (pinned / "case.json").read_text()
    (unchecked / "case.json").write_text(text.replace('"option"', '"reference"'))
    main(["diff", "--plain", str(unchecked), str(pinned)])
    shown = capsys.readouterr().out
    assert "- Before: branch is a reference to branches" in shown
    assert "- After: branch is an option of branches, checked when given" in shown
    assert "(`fields.branch.type`): reference -&gt; option." in shown


def test_the_case_data_guides_lines_are_what_the_case_writes() -> None:
    guide = (Path(__file__).parent.parent / "docs" / "guides" / "case-data.md").read_text()
    section = guide.split("## Options")[1].split("\n## ")[0]
    shown = [block.split("```")[0].strip() for block in section.split("```text\n")[1:]]
    run = run_case(
        claim(),
        file={},
        answers=[
            ("assess", "accept", "ana", {"branch": "BR-9999"}),
            ("assess", "accept", "ana", {"branch": "BR-0142"}),
        ],
        people=ADJUSTERS,
        activities={"branches.holds@1": holds},
        catalog=checked(),
    )
    assert len(shown) == 2
    assert all(line in run.history for line in shown), shown


# --- The tutor's review: an edit never sets an option ---


def test_an_edit_of_an_option_is_refused_when_it_is_proposed() -> None:
    # An edit is checked for its type, never by the system: an option is given only in a
    # person's answer, where its system vouches for it (brief, D52) (brief, D67).
    definition = closable() | {"stays_open": True}
    both = ["adjuster", "support-lead"]  # each sees the branch, and may edit or approve
    people = {"ana": ["adjuster"], "sam": both, "lee": both}
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            definition,
            file={},
            answers=[
                ("assess", "accept", "ana", {"branch": "BR-0142"}),
                edit("branch", "BR-9999", "sam"),  # not a branch the system holds
                ("case.change#1", "approve", "lee"),
            ],
            people=people,
            activities={"branches.holds@1": holds},
            catalog=checked(),
        )
    # Refused when proposed: Lee's approval is never asked, and nothing is applied.
    assert str(refused.value) == (
        "branch is an option of branches, given only by a person's answer, where branches checks "
        "it: an edit is never checked, so give it in the answer to the task that sets it"
    )
