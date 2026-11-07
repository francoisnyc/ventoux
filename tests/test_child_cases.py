"""Layer 18c: child cases. A case step opens a whole case, pinned by its parent's release, given
its opening from the parent's case file, and reporting back as the step's outputs (brief, D74).

See docs/layers/18-lifecycle.md (18c) and docs/guides/cases.md, "Child cases".
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.memory import CaseRun
from ventoux.case.validate import validate_case
from ventoux.testing import CATALOG, run_case

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
