"""Layer 18c: child cases. A case step opens a whole case, pinned by its parent's release, given
its opening from the parent's case file, and reporting back as the step's outputs (brief, D74).

See docs/layers/18-lifecycle.md (18c) and docs/guides/cases.md, "Child cases".
"""

import copy
import json
import runpy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from temporalio.client import Client
from test_temporal_case import QUEUE, on_temporal, reported

from ventoux.case import checked
from ventoux.case.admission import RetryRefused
from ventoux.case.answers import AnswerRefused
from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.diff import diff
from ventoux.case.memory import CaseRun
from ventoux.case.releases import PackageRefused, digest, package, stored
from ventoux.case.sheet import case_map
from ventoux.case.validate import validate_case
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.cases import CaseReport, answer, start_case
from ventoux.testing import (
    CATALOG,
    ChangeRefused,
    DevelopmentCases,
    as_text,
    close,
    edit,
    migrate,
    propose,
    release_of,
    retry,
    run_case,
    send,
    skip,
)
from ventoux.tooling.builder.written import package as builder_package
from ventoux.tooling.releases import read_package

ROOT = Path(__file__).parent.parent
GUIDE = ROOT / "docs" / "guides" / "cases.md"
SECTION = "## Child cases"


def guide_steps() -> dict[str, Any]:
    """The guide's `repair` and `pay_garage` steps, as stored data, read from the guide."""
    section = GUIDE.read_text().split(SECTION)[1]
    block = section.split("```json\n")[1].split("```")[0]
    loaded: dict[str, Any] = json.loads("{" + block + "}", parse_float=Decimal)
    return loaded


def claim() -> dict[str, Any]:
    """A claim reduced to what the guide's section needs: an adjuster assesses it, setting the
    payout, then the guide's steps repair the vehicle and pay the garage."""
    return {
        "case": "claim",
        "display": {"title": "Insurance claim"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}},
            "vehicle": {"type": "string", "display": {"title": "Vehicle"}},
            "payout": {"type": "number", "display": {"title": "Payout"}},
        },
        "milestones": {"assessed": {"display": {"title": "Claim assessed"}}},
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess the claim"},
                "roles": ["support"],
                "outcomes": {
                    "accept": {
                        "display": {"title": "Accept the claim"},
                        "sets": ["payout"],
                        "reaches": ["assessed"],
                    }
                },
            },
            **guide_steps(),
        },
    }


def test_a_child_case_that_isnt_supplied_is_refused() -> None:
    # The curriculum's negative test: a case references its child, never defines it, and a child
    # nobody supplied is missing, never read as one with nothing to check (brief, D74).
    issues = validate_case(parse_case(claim()), CATALOG)
    assert [(i.path, i.code, i.message) for i in issues if i.code == "UNKNOWN_CASE"] == [
        (
            "steps.repair.case",
            "UNKNOWN_CASE",
            "repair@3 isn't supplied: add it to the package's cases/",
        )
    ]


# --- Slice 2: what a case step and a report can't be, refused when read (brief, D74) ---


def test_a_case_step_has_no_approval() -> None:
    # The child's own steps carry their approvals, as a plan's do (brief, D28).
    definition = claim()
    definition["steps"]["repair"]["approval"] = copy.deepcopy(
        definition["steps"]["pay_garage"]["approval"]
    )
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == (
        "steps.repair: a case step has no approval: its child's steps ask for their own"
    )


def test_a_case_step_is_never_repeated() -> None:
    # One child per run: a deliberate limit (brief, D74), said as for a plan step (brief, D73).
    definition = claim()
    definition["steps"]["repair"]["for_each"] = {"over": "vehicle", "key": "vehicle"}
    with pytest.raises(CaseInvalid, match="^steps.repair.for_each: not a field here$"):
        parse_case(definition)


def repair() -> dict[str, Any]:
    """The guide's repair: a garage fixes the vehicle within its budget and reports the cost."""
    return {
        "case": "repair",
        "display": {"title": "Vehicle repair"},
        "fields": {
            "vehicle": {"type": "string", "display": {"title": "Vehicle"}},
            "budget": {"type": "number", "display": {"title": "Budget"}},
            "cost": {"type": "number", "display": {"title": "Cost"}},
        },
        "milestones": {"fixed": {"display": {"title": "Vehicle fixed"}}},
        "steps": {
            "fix": {
                "kind": "task",
                "display": {"title": "Fix the vehicle"},
                "roles": ["support-lead"],
                "outcomes": {
                    "fixed": {
                        "display": {"title": "Fixed"},
                        "sets": ["cost"],
                        "reaches": ["fixed"],
                    }
                },
            }
        },
        "reports": ["cost"],
    }


@pytest.mark.parametrize(
    ("field", "declared", "said"),
    [
        (
            None,
            None,
            "reports.mileage: repair has no field mileage: a report lists the case's own fields",
        ),
        (
            "owner",
            {"type": "string", "sensitive": True, "visible_to": ["support-lead"]},
            "reports.owner: owner is sensitive, and a report carries no sensitive field yet",
        ),
        (
            "parts",
            {"type": "list", "fields": {"sku": {"type": "string"}}},
            "reports.parts: parts is a list, and a report carries no list",
        ),
    ],
)
def test_a_report_carries_only_the_cases_own_plain_values(
    field: str | None, declared: dict[str, Any] | None, said: str
) -> None:
    # A report's values land as the step's outputs, each an exact value (brief, D29); a sensitive
    # one is its own door (brief, D74).
    definition = repair()
    if field is None:
        definition["reports"] = ["cost", "mileage"]
    else:
        assert declared is not None
        definition["fields"][field] = declared | {"display": {"title": field}}
        definition["reports"] = ["cost", field]
    with pytest.raises(CaseInvalid) as refused:
        parse_case(definition)
    assert str(refused.value) == said


# --- Slice 3: the child's opening, checked at validation (brief, D74) ---


def issues_of(parent: dict[str, Any], child: dict[str, Any], code: str) -> list[tuple[str, str]]:
    """What `validate_case` says, of `code`, of the claim given `child` as its `repair@3`."""
    issues = validate_case(parse_case(parent), CATALOG, cases={"repair@3": child})
    return [(i.path, i.message) for i in issues if i.code == code]


@pytest.mark.parametrize(
    ("given", "said"),
    [
        (
            "cost",
            "repair@3 takes no input cost: its task fix sets it; its inputs are budget, vehicle",
        ),
        ("mileage", "repair@3 has no input mileage: its inputs are budget, vehicle"),
    ],
)
def test_a_child_is_given_only_what_it_takes_at_its_opening(given: str, said: str) -> None:
    # One source per field: what the child's own form sets is never given at its opening.
    definition = claim()
    definition["steps"]["repair"]["inputs"][given] = {"var": "payout"}
    assert issues_of(definition, repair(), "UNKNOWN_INPUT") == [
        (f"steps.repair.inputs.{given}", said)
    ]


def test_a_child_is_never_given_what_its_rules_set() -> None:
    child = repair()
    child["fields"]["costly"] = {"type": "boolean", "display": {"title": "Costly"}}
    child["rules"] = {
        "size_up": {
            "display": {"title": "Mark a costly repair"},
            "on": "opened",
            "when": {">": [{"var": "budget"}, 5000]},
            "then": {"set": {"costly": True}},
        }
    }
    definition = claim()
    definition["steps"]["repair"]["inputs"]["costly"] = {"==": [{"var": "payout"}, 0]}
    assert issues_of(definition, child, "UNKNOWN_INPUT") == [
        (
            "steps.repair.inputs.costly",
            (
                "repair@3 takes no input costly: its rule size_up sets it; its inputs are "
                "budget, vehicle"
            ),
        )
    ]


def test_a_child_is_given_each_input_of_its_type() -> None:
    # Never converted (brief, D36): a text is not a budget.
    definition = claim()
    definition["steps"]["repair"]["inputs"]["budget"] = {"var": "vehicle"}
    assert issues_of(definition, repair(), "INPUT_TYPE") == [
        (
            "steps.repair.inputs.budget",
            "repair@3 takes budget as a number, and is given a string: give it a number",
        )
    ]


def test_a_sensitive_value_enters_a_child_only_into_a_sensitive_field() -> None:
    # A view can hide more than its source, never less (brief, D74).
    definition = claim()
    definition["fields"]["owner"] = {
        "type": "string",
        "display": {"title": "Owner"},
        "sensitive": True,
        "visible_to": ["support"],
    }
    definition["steps"]["repair"]["inputs"]["owner"] = {"var": "owner"}
    child = repair()
    child["fields"]["owner"] = {"type": "string", "display": {"title": "Owner"}}
    expected = [
        (
            "steps.repair.inputs.owner",
            (
                "owner is sensitive, and repair@3's owner isn't: a child keeps a sensitive "
                "value sensitive"
            ),
        )
    ]
    assert issues_of(definition, child, "SENSITIVE_TO_CHILD") == expected
    child["fields"]["owner"] |= {"sensitive": True, "visible_to": ["support-lead"]}
    assert issues_of(definition, child, "SENSITIVE_TO_CHILD") == []


def test_a_child_opens_no_case_of_its_own() -> None:
    # One level only: a deliberate limit (brief, D74), so one close reaches all it must.
    child = repair()
    child["steps"]["order_parts"] = {
        "kind": "case",
        "display": {"title": "Order the parts"},
        "case": "parts@1",
    }
    assert issues_of(claim(), child, "NESTED_CASE") == [
        (
            "steps.repair.case",
            "repair@3 has a case step, order_parts: a child case opens no case of its own",
        )
    ]


def test_a_child_supplied_under_another_name_or_unreadable_is_refused() -> None:
    # Fail closed: it never runs in place of the child the step names.
    child = repair()
    child["case"] = "garage-repair"
    assert issues_of(claim(), child, "UNKNOWN_CASE") == [
        ("steps.repair.case", "repair@3 is supplied as garage-repair: supply the case it names")
    ]
    child = repair()
    del child["display"]
    assert issues_of(claim(), child, "UNKNOWN_CASE") == [
        ("steps.repair.case", "repair@3 can't be read: display: required")
    ]


# --- Slice 4: the guide's example, run as written (brief, D74) ---

PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "lee": ["support-lead"]}


def guide_python() -> str:
    """The section's example, as the guide writes it."""
    section = GUIDE.read_text().split(SECTION)[1]
    return section.split("```python\n")[1].split("```")[0]


def guide_history() -> list[str]:
    """The history lines the section shows."""
    section = GUIDE.read_text().split(SECTION)[1]
    after = section.split("```python\n")[1].split("```\n", 1)[1]  # past the example
    return after.split("```\n", 1)[1].split("```")[0].splitlines()


def test_the_guides_child_case_runs_as_written() -> None:
    # Our own documentation, run so it can't drift from the code; never a definition (data).
    namespace: dict[str, Any] = {
        "run_case": run_case,
        "claim_with_repair": claim(),
        "repair": repair(),
    }
    namespace["PEOPLE"] = PEOPLE
    exec(guide_python(), namespace)  # noqa: S102 -- our guide, as in layer 7
    run = namespace["run"]
    assert isinstance(run, CaseRun)
    shown = guide_history()
    assert [line for line in run.history if line in shown] == shown
    child = run.children["repair#1"]
    assert child.closed
    assert child.history[0] == "opened by memory, from repair#1, with budget and vehicle"


def test_a_value_a_child_was_given_comes_back_with_where_it_came_from() -> None:
    # The static check follows a reported value through the child: an untrusted estimate given as
    # the budget, and reported back, is still the customer's, and a trusted-only input refuses it
    # in every case (brief, D34) (brief, D74).
    definition = claim()
    definition["fields"]["estimate"] = {
        "type": "number",
        "display": {"title": "Estimate"},
        "source": "untrusted:customer",
    }
    definition["steps"]["repair"]["inputs"]["budget"] = {"var": "estimate"}
    definition["steps"]["pay_garage"]["inputs"]["amount"] = {"var": "repair.budget"}
    child = repair()
    child["reports"] = ["cost", "budget"]
    refused = issues_of(definition, child, "INPUT_POLICY")
    assert [path for path, _ in refused] == ["steps.pay_garage.inputs.amount"]
    assert "untrusted:customer" in refused[0][1]
    # What the child's own form set is a person's: trusted, so the guide's payment passes.
    assert issues_of(claim(), repair(), "INPUT_POLICY") == []


def test_a_reported_value_passes_trusted_only_and_never_reads_as_from_a_system() -> None:
    # `case:repair` is the route the value came by, trusted: its other sources decide (brief, D74).
    run = run_case(
        claim(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[("assess", "accept", "ana", {"payout": 900}), ("pay_garage", "approve", "sam")],
        cases={"repair@3": repair()},
        case_answers={"repair": [("fix", "fixed", "lee", {"cost": 640})]},
        people=PEOPLE,
    )
    assert (
        "scheduled pay_garage#1: payments.refund@2 (order_id from system:opener; amount from "
        "case:repair, person:lee), key memory/pay_garage#1"
    ) in run.history
    assert run.closed
    # A value the opening system gave the child, reported back, came by the child: `only_from`
    # names systems, and a child is none of them.
    from test_case_validation import with_ledger  # here: that module imports this one's guide

    definition = claim()
    definition["fields"]["estimate"] = {"type": "number", "display": {"title": "Estimate"}}
    definition["steps"]["repair"]["inputs"]["budget"] = {"var": "estimate"}
    definition["steps"]["record"] = {
        "kind": "activity",
        "display": {"title": "Record the repair's budget"},
        "activity": "ledger.record@1",
        "requires": ["repair"],
        "inputs": {"amount": {"var": "repair.budget"}},
    }
    child = repair()
    child["reports"] = ["cost", "budget"]
    issues = validate_case(parse_case(definition), with_ledger(), cases={"repair@3": child})
    refused = [(i.path, i.message) for i in issues if i.code == "INPUT_POLICY"]
    assert [path for path, _ in refused] == ["steps.record.inputs.amount"]
    assert "case:repair" in refused[0][1]


# --- Slice 5: a child that is still open (brief, D74) ---


def test_an_open_child_keeps_its_step_running_and_its_parent_waiting() -> None:
    # The child is pending work, said in one line: its own entries are the child's, since those
    # who see the claim may not see the repair (brief, D24) (brief, D74).
    run = run_case(
        claim(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[("assess", "accept", "ana", {"payout": 900})],
        cases={"repair@3": repair()},
        people=PEOPLE,
    )
    assert run.status == "open"
    assert run.waiting_for == ["repair#1: case repair, open"]
    assert not run.reached("repair")
    assert run.children["repair#1"].waiting_for == ["fix by support-lead"]


# --- Slice 6: the report (brief, D74) ---


def written_off_repair() -> dict[str, Any]:
    """The guide's repair, which a garage lead may also close as written off, with no cost."""
    child = repair()
    child["close_reasons"] = {
        "written_off": {"display": {"title": "Written off"}, "roles": ["support-lead"]}
    }
    return child


def test_a_child_closed_by_a_person_reports_its_reason_as_the_outcome() -> None:
    definition = claim()
    definition["steps"]["pay_garage"]["when"] = {"==": [{"var": "repair.outcome"}, "done"]}
    run = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[("assess", "accept", "ana", {"payout": 900})],
        cases={"repair@3": written_off_repair()},
        case_answers={"repair": [close("written_off", "lee")]},
        people=PEOPLE,
    )
    assert "repair#1 done: repair closed, written_off, by lee; reporting nothing" in run.history
    assert run.state.values["repair.outcome"] == "written_off"
    # Which reason was chosen is a person's act, as a task's outcome is (brief, D11).
    assert run.state.sources["repair.outcome"] == {"case:repair", "person:lee"}
    assert "repair.cost" not in run.state.values  # never set in the child, so absent
    assert run.closed


def test_a_reported_field_the_child_never_set_fails_whatever_reads_it() -> None:
    # Fail closed: an absent value is never read as zero (brief, D74).
    run = run_case(
        claim(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[("assess", "accept", "ana", {"payout": 900})],
        cases={"repair@3": written_off_repair()},
        case_answers={"repair": [close("written_off", "lee")]},
        people=PEOPLE,
    )
    assert run.waiting_for == ["approval of pay_garage by support-lead"]
    run = run_case(
        claim(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[("assess", "accept", "ana", {"payout": 900}), ("pay_garage", "approve", "sam")],
        cases={"repair@3": written_off_repair()},
        case_answers={"repair": [close("written_off", "lee")]},
        people=PEOPLE,
    )
    assert run.needs_attention == [
        "pay_garage#1: the inputs of pay_garage can't be read: repair.cost has no value"
    ]


def test_the_check_warns_where_a_reported_field_may_be_unset() -> None:
    issues = validate_case(parse_case(claim()), CATALOG, cases={"repair@3": written_off_repair()})
    assert [(i.path, i.message, i.severity) for i in issues if i.code == "MAY_BE_UNSET"] == [
        (
            "steps.pay_garage.inputs.amount",
            (
                "pay_garage reads repair.cost, which repair gives only when done, and repair may "
                "end written_off: then pay_garage fails and needs attention: read it only when "
                "repair.outcome is done"
            ),
            "warning",
        )
    ]
    # A child with no close reason closes only done: the guide's repair isn't warned about.
    issues = validate_case(parse_case(claim()), CATALOG, cases={"repair@3": repair()})
    assert [i for i in issues if i.code == "MAY_BE_UNSET"] == []
    guarded = claim()
    guarded["steps"]["pay_garage"]["when"] = {"==": [{"var": "repair.outcome"}, "done"]}
    issues = validate_case(parse_case(guarded), CATALOG, cases={"repair@3": written_off_repair()})
    assert [i for i in issues if i.code == "MAY_BE_UNSET"] == []


def test_a_childs_outcome_is_done_or_one_of_its_close_reasons() -> None:
    definition = claim()
    definition["steps"]["pay_garage"]["when"] = {"==": [{"var": "repair.outcome"}, "fixed"]}
    issues = validate_case(
        parse_case(definition), CATALOG, cases={"repair@3": written_off_repair()}
    )
    assert [(i.path, i.message) for i in issues if i.code == "EXPRESSION_INVALID"] == [
        (
            "steps.pay_garage.when",
            '==[1]: repair.outcome has no outcome "fixed"; its outcomes are done, written_off',
        )
    ]


# --- Slice 7: who approves in the child (brief, D25) (brief, D74) ---


def paying_repair() -> dict[str, Any]:
    """The guide's repair, which also pays for its parts behind a team lead's approval."""
    child = repair()
    child["fields"]["order_id"] = {
        "type": "reference",
        "system": "orders",
        "display": {"title": "Order"},
    }
    child["steps"]["pay_parts"] = {
        "kind": "activity",
        "display": {"title": "Pay for the parts"},
        "activity": "payments.refund@2",
        "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "budget"}},
        "approval": {"roles": ["support-lead"], "display": {"reason": "Parts cost money"}},
    }
    return child


def test_who_proposed_the_case_step_approves_nothing_in_the_child() -> None:
    # The parent's exclusions cross, or a child case would be a way around "someone else
    # approves": here sam proposed the repair, so sam approves nothing in it (brief, D25). The
    # parent's opener crosses the same way.
    definition = claim()
    definition["steps"]["repair"] |= {"automatic": False, "proposed_by": ["support-lead"]}
    definition |= {
        "stays_open": True,
        "close_reasons": {"done": {"display": {"title": "Done"}, "roles": ["support"]}},
    }
    definition["steps"]["repair"]["inputs"]["order_id"] = {"var": "order_id"}
    answered = [("assess", "accept", "ana", {"payout": 900}), propose("repair", "sam")]
    opened: dict[str, Any] = {
        "file": {"order_id": "ord-1", "vehicle": "veh-9"},
        "answers": answered,
        "cases": {"repair@3": paying_repair()},
        "people": PEOPLE,
    }
    with pytest.raises(AnswerRefused, match="sam proposed repair, so cannot approve it"):
        run_case(definition, case_answers={"repair": [("pay_parts", "approve", "sam")]}, **opened)
    run = run_case(definition, case_answers={"repair": [("pay_parts", "approve", "lee")]}, **opened)
    child = run.children["repair#1"]
    assert "lee answered pay_parts.approval#1 approve as support-lead" in child.history
    # Its keys are the child's run's: never the same as one of its parent's (brief, D17).
    assert any("key memory/repair#1/pay_parts#1" in line for line in child.history)
    # Opened by its parent, never by a person: nobody is the child's own opener.
    assert child.state.opened_by is None


# --- Slice 8: a child that refuses its opening (brief, D74) ---


def test_a_refused_opening_fails_the_step_and_a_retry_opens_no_second_child() -> None:
    # The parent's step fails, needing attention: the operator fixes the cause, then retries it,
    # under the same entry. Nothing is skipped automatically, and nothing guesses (brief, D26).
    child = repair()
    child["fields"]["budget"]["source"] = "untrusted:robots"  # a label nobody registered
    said = (
        "repair#1: repair@3 refused its opening: budget is declared untrusted:robots, a label "
        "nobody registered"
    )
    script: list[Any] = [("assess", "accept", "ana", {"payout": 900})]
    opened: dict[str, Any] = {
        "file": {"order_id": "ord-1", "vehicle": "veh-9"},
        "cases": {"repair@3": child},
        "people": PEOPLE | {"omar": ["operations"]},
    }
    run = run_case(claim(), answers=script, **opened)
    assert run.needs_attention == [said]
    assert run.children == {}  # it never opened
    run = run_case(claim(), answers=[*script, retry("repair#1", "omar")], **opened)
    assert run.needs_attention == [said]  # the same run, refused again
    started = (
        "started repair#1: case repair@3 (vehicle from system:opener; budget from person:ana), "
        "run memory/repair#1"
    )
    assert [line for line in run.history if line.startswith("started repair")] == [started] * 2


def test_a_child_that_opened_is_never_opened_again_by_a_retry() -> None:
    # A child needing attention is the child's, retried there: its parent's step runs on, and
    # only a failed run is retried (brief, D26) (brief, D74).
    with pytest.raises(RetryRefused, match="repair#1"):
        run_case(
            claim(),
            file={"order_id": "ord-1", "vehicle": "veh-9"},
            answers=[("assess", "accept", "ana", {"payout": 900}), retry("repair#1", "omar")],
            cases={"repair@3": repair()},
            people=PEOPLE | {"omar": ["operations"]},
        )


# --- Slice 9: the parent's routes (brief, D40) (brief, D74) ---

CLOSABLE = {"duplicate": {"display": {"title": "Duplicate claim"}, "roles": ["support"]}}


def test_a_parent_that_closes_closes_its_child_saying_why() -> None:
    # Through D40's one place: the child's tasks are cancelled, and the parent closes once the
    # child has ended. Its report changes nothing in the parent (brief, D74).
    definition = claim() | {"close_reasons": CLOSABLE}
    run = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[("assess", "accept", "ana", {"payout": 900}), close("duplicate", "ana")],
        cases={"repair@3": repair()},
        people=PEOPLE,
    )
    child = run.children["repair#1"]
    assert child.history[-2:] == [
        "cancelled fix#1: closed by its parent: duplicate, by ana",
        "closed: by its parent: duplicate, by ana",
    ]
    assert "repair#1 cancelled: the case is closing" in run.history
    assert "repair.outcome" not in run.state.values
    assert run.closed


def test_a_rule_that_stops_the_step_closes_its_child_and_the_parent_goes_on() -> None:
    definition = claim()
    definition["events"] = {
        "withdrawn": {
            "display": {"title": "The customer withdraws"},
            "sent_by": {"system": "portal"},
        }
    }
    definition["rules"] = {
        "withdraw": {
            "display": {"title": "Stop the repair when the customer withdraws"},
            "on": {"event": "withdrawn"},
            "then": {"stop": ["repair"]},
        }
    }
    run = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[
            ("assess", "accept", "ana", {"payout": 900}),
            send("withdrawn", {}, "system:portal"),
        ],
        cases={"repair@3": repair()},
        people=PEOPLE,
    )
    assert run.children["repair#1"].history[-1] == "closed: by its parent: stopped by withdraw#1"
    assert "repair#1 cancelled: stopped by withdraw#1" in run.history
    assert not run.reached("repair")


def test_an_edit_never_reaches_a_child() -> None:
    # The child keeps what it was given at its opening (brief, D52) (brief, D74).
    run = run_case(
        claim(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[
            ("assess", "accept", "ana", {"payout": 900}),
            edit("vehicle", "veh-10", "ana"),
            ("case.change#1", "approve", "lee"),
        ],
        cases={"repair@3": repair()},
        people=PEOPLE,
    )
    assert run.state.values["vehicle"] == "veh-10"
    assert run.children["repair#1"].state.values["vehicle"] == "veh-9"


def test_a_failed_opening_may_be_skipped_by_operators_like_any_failed_run() -> None:
    # A person decides, another approves: nothing is skipped automatically (brief, D52).
    child = repair()
    child["fields"]["budget"]["source"] = "untrusted:robots"  # a label nobody registered
    definition = claim()
    del definition["steps"]["pay_garage"]  # nothing reads what the repair would have given
    run = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[
            ("assess", "accept", "ana", {"payout": 900}),
            skip("repair#1", "omar"),
            ("case.change#1", "approve", "olga"),
        ],
        cases={"repair@3": child},
        people=PEOPLE | {"omar": ["operations"], "olga": ["operations"]},
    )
    assert any(
        line == "applied case.change#1: repair#1 skipped by omar, approved by olga"
        for line in run.history
    )
    assert run.children == {}
    assert run.closed


def test_a_required_case_step_is_done_once_its_child_closes_and_owed_if_stopped() -> None:
    # Done is a run that ended with an outcome: a child closed as written off is done; a child its
    # parent closed is cancelled, so the step is still owed, and only a person's close ends it
    # (brief, D72) (brief, D74).
    definition = claim() | {"close_reasons": CLOSABLE}
    definition["steps"]["repair"]["required"] = True
    definition["steps"]["pay_garage"]["when"] = {"==": [{"var": "repair.outcome"}, "done"]}
    written_off = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[("assess", "accept", "ana", {"payout": 900})],
        cases={"repair@3": written_off_repair()},
        case_answers={"repair": [close("written_off", "lee")]},
        people=PEOPLE,
    )
    assert written_off.closed
    definition["events"] = {
        "withdrawn": {
            "display": {"title": "The customer withdraws"},
            "sent_by": {"system": "portal"},
        }
    }
    definition["rules"] = {
        "withdraw": {
            "display": {"title": "Stop the repair when the customer withdraws"},
            "on": {"event": "withdrawn"},
            "then": {"stop": ["repair"]},
        }
    }
    stopped = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[
            ("assess", "accept", "ana", {"payout": 900}),
            send("withdrawn", {}, "system:portal"),
        ],
        cases={"repair@3": repair()},
        people=PEOPLE,
    )
    assert stopped.status == "open"
    owed = (
        "repair: required, and it can't start: repair has run, and is not repeatable: close the "
        "case with a reason"
    )
    assert stopped.needs_attention == [owed]


def test_a_repeatable_case_step_proposed_again_opens_another_child() -> None:
    # Each run is its own child, with its own script by entry, and its own keys (brief, D74).
    definition = claim() | {"close_reasons": CLOSABLE, "stays_open": True}
    definition["steps"]["repair"] |= {"repeatable": True, "proposed_by": ["support-lead"]}
    run = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[("assess", "accept", "ana", {"payout": 900}), propose("repair", "lee")],
        cases={"repair@3": repair()},
        case_answers={
            "repair#1": [("fix", "fixed", "lee", {"cost": 640})],
            "repair#2": [("fix", "fixed", "lee", {"cost": 120})],
        },
        people=PEOPLE,
    )
    assert sorted(run.children) == ["repair#1", "repair#2"]
    assert run.children["repair#2"].state.case == "memory/repair#2"
    assert run.state.values["repair.cost"] == 120  # the latest run's, as for any step


# --- Slice 10: the package holds its children (brief, D50) (brief, D74) ---


def folder_of(tmp_path: Path, parent: dict[str, Any], children: dict[str, Any]) -> Path:
    """A package folder: `parent` as case.json, and each child as `cases/<reference>/case.json`."""
    folder = tmp_path / "claim"
    (folder / "cases").mkdir(parents=True)
    (folder / "case.json").write_text(as_text(parent))
    for reference, child in children.items():
        (folder / "cases" / reference).mkdir()
        (folder / "cases" / reference / "case.json").write_text(as_text(child))
    return folder


def test_a_package_holds_each_child_it_pins_as_a_package_of_its_own(tmp_path: Path) -> None:
    read = read_package(folder_of(tmp_path, claim(), {"repair@3": repair()}))
    assert list(read.cases) == ["repair@3"]
    assert read.cases["repair@3"].case.case == "repair"
    assert validate_case(read.case, CATALOG, cases=read.pinned) == validate_case(
        read.case, CATALOG, cases={"repair@3": repair()}
    )


def test_a_package_whose_children_dont_fit_its_case_steps_is_refused(tmp_path: Path) -> None:
    # Refused, never ignored: nothing is released (brief, D50) (brief, D74).
    def refused(children: dict[str, Any], extra: str | None = None) -> str:
        folder = folder_of(tmp_path / str(len(list(tmp_path.iterdir()))), claim(), children)
        if extra is not None:
            (folder / "cases" / extra).mkdir()
        with pytest.raises(PackageRefused) as refusal:
            read_package(folder)
        return str(refusal.value)

    assert refused({}) == "repair@3 is opened by a case step and isn't in cases/: add it"
    assert refused({"repair@3": repair(), "repair@4": repair()}) == (
        "cases/repair@4 is opened by no case step: remove it, or name it in a step"
    )
    assert refused({"repair@3": repair() | {"case": "garage"}}) == (
        "cases/repair@3 holds the case garage: a child's folder is named by its case and release"
    )
    assert refused({"repair@3": repair()}, extra="notes") == (
        "cases/notes isn't a package: a child case is a folder holding case.json"
    )


def test_a_child_that_pins_children_of_its_own_is_refused(tmp_path: Path) -> None:
    # One level only, in the package as at validation (brief, D74).
    child = repair()
    child["steps"]["order_parts"] = {
        "kind": "case",
        "display": {"title": "Order the parts"},
        "case": "parts@1",
    }
    folder = folder_of(tmp_path, claim(), {"repair@3": child})
    inner = folder / "cases" / "repair@3" / "cases" / "parts@1"
    inner.mkdir(parents=True)
    (inner / "case.json").write_text(as_text(repair() | {"case": "parts"}))
    with pytest.raises(PackageRefused) as refusal:
        read_package(folder)
    assert str(refusal.value) == "cases/repair@3 has cases/ of its own: a child opens no case"


def test_a_plan_reference_meaning_two_plans_in_one_package_is_refused() -> None:
    # One reference is one plan, so the digest and a reader never tell two apart (brief, D50).
    from test_releases import written  # here: that module reads the example package

    case, plans = written()
    case["steps"]["repair"] = {"kind": "case", "display": {"title": "Repair"}, "case": "repair@3"}
    child = repair()
    child["steps"]["settle"] = {
        "kind": "plan",
        "display": {"title": "Settle"},
        "plan": "refund-order@1",
    }
    changed = copy.deepcopy(plans[0])
    changed["states"]["approve_refund"]["approval"]["timeout"] = "72h"
    for given, problems in ((plans[0], ""), (changed, "differs")):
        inner = package(as_text(child), [as_text(given)])
        if not problems:
            assert list(package(as_text(case), [as_text(plans[0])], {"repair@3": inner}).cases)
            continue
        with pytest.raises(PackageRefused) as refusal:
            package(as_text(case), [as_text(plans[0])], {"repair@3": inner})
        assert str(refusal.value) == (
            "plans/refund-order@1 differs between refund and cases/repair@3: one reference is "
            "one plan"
        )


def test_the_parents_digest_covers_what_its_children_do() -> None:
    # A new garage process reaches claims only by a release of the claim (brief, D50) (brief, D74).
    def digest_with(child: dict[str, Any]) -> str:
        pinned = package(as_text(child), [])
        return digest(package(as_text(claim()), [], {"repair@3": pinned})).sha256

    slower = repair()
    slower["steps"]["fix"]["roles"] = ["support"]
    assert digest_with(slower) != digest_with(repair())
    # Wording only changes no digest, in a child as in its parent.
    reworded = repair()
    reworded["steps"]["fix"]["display"]["title"] = "Repair the vehicle"
    assert digest_with(reworded) == digest_with(repair())


def test_a_release_record_keeps_its_children_and_reads_back_as_the_same_package() -> None:
    record = release_of(claim(), 1, cases={"repair@3": repair()})
    kept = stored(record, "claim")
    assert list(kept.cases) == ["repair@3"]
    assert digest(kept) == record.digest


PLATFORM = PEOPLE | {"pia": ["platform"], "lee": ["support-lead", "platform"]}
ASSESSED = ("assess", "accept", "ana", {"payout": 900})


def test_a_migration_renaming_the_case_step_keeps_its_open_child() -> None:
    # Running work finishes under what it started with: the child keeps its release, and the
    # record of which child the run opened follows the rename (brief, D53) (brief, D74).
    after = claim() | {"close_reasons": CLOSABLE}
    after["steps"]["fix_vehicle"] = after["steps"].pop("repair")
    after["steps"]["pay_garage"]["requires"] = ["fix_vehicle"]
    after["steps"]["pay_garage"]["inputs"]["amount"] = {"var": "fix_vehicle.cost"}
    run = run_case(
        claim() | {"close_reasons": CLOSABLE},
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[
            ASSESSED,
            migrate(
                release_of(after, 2, cases={"repair@3": repair()}),
                {"steps": {"repair": "fix_vehicle"}},
                "pia",
            ),
            ("case.change#1", "approve", "lee"),
            close("duplicate", "ana"),
        ],
        cases={"repair@3": repair()},
        people=PLATFORM,
        release=release_of(claim() | {"close_reasons": CLOSABLE}, 1, cases={"repair@3": repair()}),
    )
    assert any(line.startswith("applied case.change#1: migrated") for line in run.history)
    # The close still reaches the child, by the entry it opened under.
    assert run.children["repair#1"].history[-1] == "closed: by its parent: duplicate, by ana"
    assert run.closed


def test_a_migration_opening_another_release_from_the_step_is_refused_until_it_ends() -> None:
    after = claim()
    after["steps"]["repair"]["case"] = "repair@4"
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            claim(),
            file={"order_id": "ord-1", "vehicle": "veh-9"},
            answers=[
                ASSESSED,
                migrate(release_of(after, 2, cases={"repair@4": repair()}), {}, "pia"),
            ],
            cases={"repair@3": repair()},
            people=PLATFORM,
            release=release_of(claim(), 1, cases={"repair@3": repair()}),
        )
    assert (
        "repair#1 is running on repair@3, and claim 2's repair opens repair@4: migrate after it finishes"
        in str(refused.value)
    )


def test_the_release_check_checks_each_child_and_gives_the_parent_its_children() -> None:
    # One check before release, for the parent and every child it pins (brief, D50) (brief, D74).
    pinned = package(as_text(repair()), [])
    released = package(as_text(claim()), [], {"repair@3": pinned})
    assert [i.code for i in checked.issues_of(released, CATALOG) if i.severity == "error"] == []
    broken = repair()
    broken["steps"]["fix"]["roles"] = ["mechanic"]  # a role nobody registered
    released = package(as_text(claim()), [], {"repair@3": package(as_text(broken), [])})
    paths = [i.path for i in checked.issues_of(released, CATALOG) if i.severity == "error"]
    assert paths and all(path.startswith("cases.repair@3.") for path in paths)


def test_a_childs_plan_step_finds_its_plan_beside_its_parents() -> None:
    # One reference is one plan, so `plans` serves the parent and its children (brief, D74).
    from test_case import refund_order  # here: that module imports this one's guide

    child = repair()
    child["fields"]["order_id"] = {
        "type": "reference",
        "system": "orders",
        "display": {"title": "Order"},
    }
    child["steps"]["settle"] = {
        "kind": "plan",
        "display": {"title": "Settle the parts"},
        "plan": "refund-order@1",
        "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "budget"}},
    }
    definition = claim()
    definition["steps"]["repair"]["inputs"]["order_id"] = {"var": "order_id"}
    run = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED],
        cases={"repair@3": child},
        case_answers={"repair": [("fix", "fixed", "lee", {"cost": 640})]},
        plans={"refund-order@1": refund_order()},
        plan_answers={"settle": [("approve_refund", "approve", "sam")]},
        people=PEOPLE,
    )
    assert "settle#1 done" in run.children["repair#1"].history


# --- Slice 11: the diff, the case map, the builder, the schema (brief, D55) (brief, D74) ---


def packed_with(parent: dict[str, Any], children: dict[str, Any]) -> Any:
    """The package of `parent`, pinning each child by reference."""
    pinned = {ref: package(as_text(child), []) for ref, child in children.items()}
    return package(as_text(parent), [], pinned)


def test_the_diff_says_what_changes_inside_a_child_with_the_childs_verdict() -> None:
    # Never silent: what a child does is what its parent's cases do (brief, D55) (brief, D74).
    wider = repair()
    wider["steps"]["fix"]["roles"] = ["support-lead", "support"]
    changed = diff(
        packed_with(claim(), {"repair@3": repair()}),
        packed_with(claim(), {"repair@3": wider}),
        CATALOG,
    )
    said = {(c.path, c.verdict) for c in changed.changes}
    # The child's own diff, every change under its reference: the role, and who sees its fields.
    assert ("cases.repair@3.steps.fix.roles", "looser") in said
    assert all(path.startswith("cases.repair@3.") for path, _ in said)
    moved = claim()
    moved["steps"]["repair"]["case"] = "repair@4"
    changed = diff(
        packed_with(claim(), {"repair@3": repair()}),
        packed_with(moved, {"repair@4": repair()}),
        CATALOG,
    )
    assert [(c.path, c.verdict, c.entry) for c in changed.changes] == [
        ("steps.repair.case", "not proven", ""),
        ("cases.repair@3", "not proven", "removed"),
        ("cases.repair@4", "not proven", "added"),
    ]


def test_the_case_map_reads_the_case_step_and_maps_each_child() -> None:
    # What a case of the package can do includes what its children do (brief, D56) (brief, D74).
    mapped = case_map(packed_with(claim(), {"repair@3": repair()}), CATALOG)
    assert "- repair opens the case repair@3, giving" in mapped
    child = mapped.split("## Child case repair@3\n")[1]
    assert "### Steps" in child and "- fix is a task for support-lead" in child
    assert "it reports cost to the case that opened it" in child


def test_the_builder_writes_the_guides_claim_and_its_child() -> None:
    # The same JSON whichever way it is written, the child in its package (brief, D58).
    built = runpy.run_path(str(ROOT / "examples" / "builder" / "child.py"))
    files = builder_package(built["claim"])
    assert sorted(files) == ["case.json", "cases/repair@3/case.json"]
    assert json.loads(files["case.json"], parse_float=Decimal) == claim()
    assert json.loads(files["cases/repair@3/case.json"], parse_float=Decimal) == repair()


# --- Step 6: promises without a test yet (brief, D74) ---


def test_the_parents_opener_approves_nothing_in_the_child() -> None:
    # The opener's exclusion crosses as the proposer's does. The child's letter reads nothing the
    # opener gave, so only the crossing refuses them (brief, D11) (brief, D25).
    child = repair()
    child["steps"]["tell_owner"] = {
        "kind": "activity",
        "display": {"title": "Tell the owner"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": "owner@example.com", "template": "repair-started"},
        "approval": {"roles": ["support-lead"], "display": {"reason": "A letter is reviewed"}},
    }
    opened: dict[str, Any] = {
        "file": {"order_id": "ord-1", "vehicle": "veh-9"},
        "answers": [ASSESSED],
        "cases": {"repair@3": child},
        "people": PEOPLE,
        "opened_by": "sam",
    }
    with pytest.raises(AnswerRefused, match="sam opened the case, so cannot approve its steps"):
        run_case(claim(), case_answers={"repair": [("tell_owner", "approve", "sam")]}, **opened)
    run = run_case(claim(), case_answers={"repair": [("tell_owner", "approve", "lee")]}, **opened)
    assert "lee answered tell_owner.approval#1 approve as support-lead" in (
        run.children["repair#1"].history
    )


def test_an_event_reaches_the_parent_only() -> None:
    # The child is its own case: what the parent hears, it doesn't, unless a rule stops the step.
    definition = claim()
    definition["events"] = {
        "withdrawn": {
            "display": {"title": "The customer withdraws"},
            "sent_by": {"system": "portal"},
        }
    }
    run = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED, send("withdrawn", {}, "system:portal")],
        cases={"repair@3": repair()},
        people=PEOPLE,
    )
    assert "withdrawn#1 from portal" in run.history
    assert not any("withdrawn" in line for line in run.children["repair#1"].history)
    assert run.children["repair#1"].waiting_for == ["fix by support-lead"]


def test_a_report_carries_nothing_its_child_doesnt_report() -> None:
    # Only the outcome and the fields `reports` lists land; the child's milestones are said in
    # the history, never read (brief, D74).
    run = run_case(
        claim(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED],
        cases={"repair@3": repair()},
        case_answers={"repair": [("fix", "fixed", "lee", {"cost": 640})]},
        people=PEOPLE,
    )
    landed = sorted(name for name in run.state.values if name.startswith("repair."))
    assert landed == ["repair.cost", "repair.outcome"]
    reading = claim()
    reading["steps"]["pay_garage"]["when"] = {"var": "repair.fixed"}
    issues = validate_case(parse_case(reading), CATALOG, cases={"repair@3": repair()})
    assert [i.path for i in issues if i.code == "EXPRESSION_INVALID"] == ["steps.pay_garage.when"]


def test_an_open_childs_line_comes_after_the_parents_own_open_entries() -> None:
    definition = claim()
    definition["steps"]["call"] = {
        "kind": "task",
        "display": {"title": "Call the customer"},
        "roles": ["support"],
        "requires": ["assessed"],
        "outcomes": {"called": {"display": {"title": "Called"}}},
    }
    run = run_case(
        definition,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED],
        cases={"repair@3": repair()},
        people=PEOPLE,
    )
    # repair opened before call: its line still comes after the case's own entries (brief, D74).
    started = [line for line in run.history if line.startswith("started ")]
    assert started.index(next(s for s in started if "repair#1" in s)) < started.index(
        "started call#1: waiting for called by support"
    )
    assert run.waiting_for == ["call by support", "repair#1: case repair, open"]


def test_on_temporal_a_case_step_fails_closed_until_child_cases_run_there() -> None:
    # Layer 18d runs a child as its own workflow; until then the step fails, needing attention,
    # never a silent start (brief, D74).
    async def scenario(client: Client) -> CaseReport:
        case = await start_case(
            client,
            DevelopmentCases,
            claim(),
            {"order_id": "ord-1", "vehicle": "veh-9"},
            "c-1",
            QUEUE,
        )
        await answer(case, "assess#1", "accept", "ana", ["support"], {"payout": Decimal(900)})
        return await reported(case, lambda now: bool(now.needs_attention))

    # Found by this test: an empty start crashed the workflow task, which Temporal retries for
    # ever. Now the engine refuses a child its start didn't give, here and in memory alike.
    refused = (
        "repair#1: repair@3 isn't a child this case holds: its start gives the children its "
        "release pins"
    )
    assert on_temporal(scenario).needs_attention == [refused]
    run = run_case(
        claim(), file={"order_id": "ord-1", "vehicle": "veh-9"}, answers=[ASSESSED], people=PEOPLE
    )
    assert run.needs_attention == [refused]


# --- From the tutor's review of #88 ---


def test_who_closed_the_child_decided_its_outcome_so_approves_nothing_it_feeds() -> None:
    # lee closes the repair as written off, and pay_garage runs only then: lee's choice decided
    # that it runs, so lee approves nothing of it (brief, D11) (brief, D74).
    definition = claim()
    definition["steps"]["pay_garage"]["when"] = {"==": [{"var": "repair.outcome"}, "written_off"]}
    definition["steps"]["pay_garage"]["inputs"]["amount"] = {"var": "payout"}
    opened: dict[str, Any] = {
        "file": {"order_id": "ord-1", "vehicle": "veh-9"},
        "cases": {"repair@3": written_off_repair()},
        "case_answers": {"repair": [close("written_off", "lee")]},
        "people": PEOPLE,
    }
    # Said as for any condition a person's answer feeds: it decides whether the step runs.
    refused = "lee set repair.outcome, which decides whether pay_garage runs, so cannot approve it"
    with pytest.raises(AnswerRefused, match=refused):
        run_case(definition, answers=[ASSESSED, ("pay_garage", "approve", "lee")], **opened)
    run = run_case(definition, answers=[ASSESSED, ("pay_garage", "approve", "sam")], **opened)
    assert any(line.startswith("scheduled pay_garage#1") for line in run.history)
    # A child that closed by itself is done, decided by nobody: its outcome is the child's alone.
    done = run_case(
        claim(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED],
        cases={"repair@3": repair()},
        case_answers={"repair": [("fix", "fixed", "lee", {"cost": 640})]},
        people=PEOPLE,
    )
    assert done.state.sources["repair.outcome"] == {"case:repair"}


def telling_repair() -> dict[str, Any]:
    """The guide's repair, which also drafts a letter to the vehicle's contact."""
    child = repair()
    child["steps"]["tell"] = {
        "kind": "activity",
        "display": {"title": "Tell the owner"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "vehicle"}, "template": "repair-started"},
    }
    return child


def customer_vehicle() -> dict[str, Any]:
    """The claim, its vehicle typed by the customer."""
    definition = claim()
    definition["fields"]["vehicle"]["source"] = "untrusted:customer"
    return definition


def test_a_childs_opening_keeps_the_sources_its_parent_gave_it() -> None:
    # The child's own checks judge where a value really came from: the customer, not the parent
    # that opened it (brief, D12) (brief, D74).
    run = run_case(
        customer_vehicle(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED],
        cases={"repair@3": telling_repair()},
        people=PEOPLE,
    )
    [failed] = [
        line for line in run.children["repair#1"].history if line.startswith("tell#1 failed")
    ]
    assert failed.endswith("this value comes from vehicle (system:opener, untrusted:customer)")


def test_the_check_reads_a_childs_opening_with_the_sources_its_parent_gives() -> None:
    # As the check follows a report out of a child, it follows an opening in: refused at the
    # parent's input before any case opens, as a plan's fields are (brief, D36) (brief, D74).
    issues = validate_case(
        parse_case(customer_vehicle()), CATALOG, cases={"repair@3": telling_repair()}
    )
    refused = [(i.path, i.message) for i in issues if i.code == "INPUT_POLICY"]
    assert [path for path, _ in refused] == ["steps.repair.inputs.vehicle"]
    assert refused[0][1].startswith("repair@3, in its step tell: letters.draft@2 takes to_customer")
    assert "untrusted:customer" in refused[0][1]
    # The same child, given a trusted vehicle, is refused nowhere.
    issues = validate_case(parse_case(claim()), CATALOG, cases={"repair@3": telling_repair()})
    assert [i for i in issues if i.code == "INPUT_POLICY"] == []


def test_a_childs_refusal_through_its_rules_is_said_at_the_parents_input() -> None:
    # From the tutor's review of #88: contact is set by a child's rule from vehicle, which the
    # customer typed in the parent. The check follows contact's writers back to the opening
    # field, and never drops the refusal (brief, D36) (brief, D74).
    child = telling_repair()
    child["fields"]["contact"] = {"type": "string", "display": {"title": "Contact"}}
    child["rules"] = {
        "copy": {
            "display": {"title": "Write to the vehicle's contact"},
            "on": "opened",
            "then": {"set": {"contact": {"var": "vehicle"}}},
        }
    }
    child["steps"]["tell"]["inputs"]["to_customer"] = {"var": "contact"}
    run = run_case(
        customer_vehicle(),
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED],
        cases={"repair@3": child},
        people=PEOPLE,
    )
    [failed] = [
        line for line in run.children["repair#1"].history if line.startswith("tell#1 failed")
    ]
    assert failed.endswith("this value comes from contact (system:opener, untrusted:customer)")
    issues = validate_case(parse_case(customer_vehicle()), CATALOG, cases={"repair@3": child})
    refused = [(i.path, i.message) for i in issues if i.code == "INPUT_POLICY"]
    assert [path for path, _ in refused] == ["steps.repair.inputs.vehicle"]
    assert refused[0][1].startswith("repair@3, in its step tell: letters.draft@2 takes to_customer")


def test_a_child_takes_a_reference_only_as_a_reference_of_its_system_read_as_it_is() -> None:
    # Found while answering the review of #88: a child's reference field refused every input.
    # It takes a reference to its system, read as it is, as a plan's does (brief, D30) (brief, D36).
    definition = claim()
    definition["steps"]["repair"]["inputs"]["order_id"] = {"var": "order_id"}
    issues = validate_case(parse_case(definition), CATALOG, cases={"repair@3": paying_repair()})
    assert [i for i in issues if i.code == "INPUT_TYPE"] == []
    definition["steps"]["repair"]["inputs"]["order_id"] = {"var": "vehicle"}
    issues = validate_case(parse_case(definition), CATALOG, cases={"repair@3": paying_repair()})
    assert [(i.path, i.message) for i in issues if i.code == "INPUT_TYPE"] == [
        (
            "steps.repair.inputs.order_id",
            (
                "repair@3 takes order_id as a reference to orders, read as it is, and is given a "
                "string: give it a reference field of orders"
            ),
        )
    ]


def test_a_childs_refusal_that_traces_to_no_input_is_said_at_the_case_step() -> None:
    # The customer's vehicle decides whether the child looks the order up, so the lookup's status
    # carries it (brief, D43); no input of the parent gives status, so the refusal is said at the
    # case step, never dropped.
    child = telling_repair()
    child["fields"]["order_id"] = {
        "type": "reference",
        "system": "orders",
        "display": {"title": "Order"},
    }
    child["steps"]["lookup"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
        "when": {"==": [{"var": "vehicle"}, "veh-9"]},
    }
    child["steps"]["tell"] |= {"requires": ["lookup"]}
    child["steps"]["tell"]["inputs"]["to_customer"] = {"var": "lookup.status"}
    parent = customer_vehicle()
    parent["steps"]["repair"]["inputs"]["order_id"] = {"var": "order_id"}
    issues = validate_case(parse_case(parent), CATALOG, cases={"repair@3": child})
    refused = [(i.path, i.message) for i in issues if i.code == "INPUT_POLICY"]
    assert [path for path, _ in refused] == ["steps.repair"]
    assert refused[0][1].startswith("repair@3, in its step tell: letters.draft@2 takes to_customer")
    run = run_case(
        parent,
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED],
        cases={"repair@3": child},
        activities={"orders.lookup@2": lambda _: {"status": "open"}},
        people=PEOPLE,
    )
    assert any(line.startswith("tell#1 failed") for line in run.children["repair#1"].history)


def test_a_childs_state_crosses_continue_as_new() -> None:
    # Who closed it, with which reason, the children it pins and who its parent excluded: each
    # crosses as the state does, so a case continuing as new reports and excludes the same
    # (brief, D27) (brief, D74).
    run = run_case(
        claim() | {"close_reasons": CLOSABLE},
        file={"order_id": "ord-1", "vehicle": "veh-9"},
        answers=[ASSESSED],
        cases={"repair@3": written_off_repair()},
        case_answers={"repair": [close("written_off", "lee")]},
        people=PEOPLE,
        opened_by="sam",
    )
    child = run.children["repair#1"].state
    assert (child.closed_as, child.closed_by) == ("written_off", "lee")
    assert child.excluded == {"sam": "sam opened the case, so cannot approve its steps"}
    for state in (child, run.state):
        again = state_from_data(state_as_data(state), {})
        assert (again.closed_as, again.closed_by) == (state.closed_as, state.closed_by)
        assert (again.cases, again.excluded) == (state.cases, state.excluded)
    assert list(state_from_data(state_as_data(run.state), {}).cases) == ["repair@3"]
