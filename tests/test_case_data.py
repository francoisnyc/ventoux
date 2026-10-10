"""Case data: references, and who sees what (layer 9a).

See docs/layers/09-case-data.md and docs/guides/case-data.md.
"""

import copy
from typing import Any

import pytest

from ventoux.case.runtime import CaseRefused
from ventoux.testing import run_case

# Who has which role, as the Ventoux API would state it (brief, D22).
PEOPLE = {
    "ana": ["adjuster"],
    "fay": ["fraud"],
    "eve": ["support"],
}


def claim() -> dict[str, Any]:
    """The case data guide's claim (its first JSON block), as stored data."""
    return copy.deepcopy(CLAIM)


CLAIM: dict[str, Any] = {
    "case": "claim",
    "display": {"title": "Insurance claim"},
    "fields": {
        "customer_id": {"type": "reference", "system": "crm", "display": {"title": "Customer"}},
        "policy_id": {"type": "reference", "system": "policies", "display": {"title": "Policy"}},
        "estimated_damage": {"type": "number", "display": {"title": "Estimated damage"}},
        "fraud_score": {"type": "number", "display": {"title": "Fraud score"}},
    },
    "steps": {
        "assess": {
            "kind": "task",
            "display": {"title": "Assess the claim"},
            "roles": ["adjuster"],
            "outcomes": {
                "accept": {"display": {"title": "Accept the claim"}},
                "deny": {"display": {"title": "Deny the claim"}},
            },
        },
        "deny": {
            "kind": "activity",
            "display": {"title": "Draft the denial letter"},
            "activity": "letters.draft@3",
            "requires": ["assess"],
            "when": {"==": [{"var": "assess.outcome"}, "deny"]},
            "inputs": {"customer": {"var": "customer_id"}, "template": "claim-denied"},
        },
    },
}

FILE = {"customer_id": "cus-7", "policy_id": "pol-3", "estimated_damage": 1200, "fraud_score": 12}


# Slice 1: references at the opening.


def test_a_reference_to_an_unregistered_system_is_refused() -> None:
    # A typo in a system name is caught when the case opens, never a system nobody runs (D30).
    sailing = claim()
    sailing["fields"]["customer_id"]["system"] = "sail"
    with pytest.raises(CaseRefused, match="customer_id is a reference to sail, which is not a reg"):
        run_case(sailing, file=FILE, answers=[], people=PEOPLE)


# Slice 2: references into inputs.

DENIED = ("assess", "deny", "ana")
TAKES = "deny#1: letters.draft@3 takes customer as a reference to crm, and is given"


def denying_with(customer: object) -> dict[str, Any]:
    """The claim, its `deny` step giving `customer` from the expression `customer`."""
    data = claim()
    data["steps"]["deny"]["inputs"]["customer"] = customer
    return data


@pytest.mark.parametrize(
    ("customer", "given"),
    [
        ({"var": "policy_id"}, "policy_id, a reference to policies"),  # the curriculum's
        ({"var": "estimated_damage"}, "estimated_damage, a number"),
        ({"var": "assess.outcome"}, "assess.outcome, which is not a reference"),
        ({"cat": [{"var": "customer_id"}, ""]}, "a computed value"),
        ("cus-7", "a value written in the definition"),
    ],
)
def test_a_reference_goes_only_where_its_system_is_expected(customer: object, given: str) -> None:
    # An ID from the wrong system can look exactly like a right one: the step fails before the
    # activity is called, whatever the value is (brief, D30).
    calls: list[dict[str, Any]] = []

    def drafting(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs)
        return {"draft_id": "d-1"}

    run = run_case(
        denying_with(customer),
        file=FILE,
        answers=[DENIED],
        people=PEOPLE,
        activities={"letters.draft@3": drafting},
    )
    assert run.needs_attention == [f"{TAKES} {given}"]
    assert calls == []


def test_a_reference_of_its_system_goes_in() -> None:
    run = run_case(claim(), file=FILE, answers=[DENIED], people=PEOPLE)
    assert run.reached("deny")
    assert run.closed
