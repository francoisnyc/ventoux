"""Layer 9b in memory: sensitive fields, wrapped wherever they go and never written out.

See docs/layers/09-case-data.md (9b) and docs/guides/case-data.md ("Sensitive data").
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.answers import AnswerRefused
from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.runtime import CaseRefused, decide
from ventoux.case.state import Answered, CaseState, GivenApproval, Opened, StartPlan
from ventoux.core.sensitive import Sensitive
from ventoux.testing import CATALOG, as_json, run_case, shown

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "case-data.md").read_text()
NATIONAL_ID = "1 85 05 78 006 084 36"
PLAIN_TEXT = (
    "national_id is sensitive and was given in plain text: send it through "
    "ventoux.temporal.cases, which encrypts it"
)


def claim() -> dict[str, Any]:
    """The case data guide's claim, with the sensitive field the guide adds to it."""
    blocks = [block.split("```")[0] for block in GUIDE.split("```json\n")[1:]]
    data: dict[str, Any] = json.loads(blocks[0], parse_float=Decimal)
    [added] = [block for block in blocks if block.startswith('"national_id"')]
    field = json.loads("{" + added + "}", parse_float=Decimal)
    data["fields"].update(field)
    return data


def test_a_sensitive_field_names_who_sees_it() -> None:
    # Only the roles it lists see a sensitive value (brief, D16): it must list them.
    definition = claim()
    del definition["fields"]["national_id"]["visible_to"]
    with pytest.raises(
        CaseInvalid, match="national_id is sensitive, so it must say who may see it"
    ):
        parse_case(definition)
    assert parse_case(claim()).fields["national_id"].sensitive


def test_a_sensitive_value_never_prints() -> None:
    # Whatever formats it, a message, a line or a traceback writes the placeholder.
    wrapped = Sensitive(NATIONAL_ID)
    assert str(wrapped) == "‹sensitive›"
    assert repr(wrapped) == "‹sensitive›"
    assert f"{wrapped}" == "‹sensitive›"
    assert NATIONAL_ID not in repr({"national_id": wrapped})
    assert wrapped.value == NATIONAL_ID
    assert wrapped == Sensitive(NATIONAL_ID)


PEOPLE = {"ana": ["adjuster"], "fay": ["fraud"], "kim": ["claims-sensitive"]}
FILE = {
    "customer_id": "cus-7",
    "policy_id": "pol-3",
    "estimated_damage": 1200,
    "fraud_score": 12,
    "national_id": NATIONAL_ID,
}


def test_who_sees_a_sensitive_value() -> None:
    run = run_case(claim(), file=FILE, answers=[], people=PEOPLE)
    # Hidden from a role its field doesn't list, like any field it narrows (brief, D30).
    adjuster = run.view(roles=["adjuster"])
    assert adjuster.lines[-1] == "National ID: hidden (needs claims-sensitive)"
    assert "national_id" not in adjuster.values
    # Seen by the role it lists, still wrapped: the line, which ends up in logs, never shows it.
    officer = run.view(roles=["claims-sensitive"])
    assert officer.lines[-1] == "National ID: ‹sensitive›, from system:opener"
    assert officer.values["national_id"] == Sensitive(NATIONAL_ID)
    # Nothing the run kept writes it out.
    assert NATIONAL_ID not in "\n".join(run.history)


def claim_asking_the_id() -> dict[str, Any]:
    """The claim, where the adjuster gives the national ID when accepting it."""
    definition = claim()
    definition["steps"]["assess"]["outcomes"]["accept"]["sets"] = ["national_id"]
    return definition


def wrapped_file() -> dict[str, Any]:
    """`FILE` as the client sends it: the national ID wrapped."""
    return {**as_json(FILE), "national_id": Sensitive(NATIONAL_ID)}


OPENING = {name: value for name, value in FILE.items() if name != "national_id"}


def test_a_plain_sensitive_value_is_refused() -> None:
    # It has already crossed in plain text: the case says so loudly, whatever the client did.
    case = parse_case(claim())
    plain_file = {**as_json(OPENING), "national_id": NATIONAL_ID}
    with pytest.raises(CaseRefused, match=f"^{PLAIN_TEXT}$"):
        decide(case, CATALOG, CaseState("memory"), Opened(plain_file, None))
    asking = parse_case(claim_asking_the_id())
    opened, _ = decide(asking, CATALOG, CaseState("memory"), Opened(as_json(OPENING), None))
    plain_answer = Answered(
        "assess#1", "accept", "ana", frozenset({"adjuster"}), {"national_id": NATIONAL_ID}
    )
    with pytest.raises(AnswerRefused, match=f"^{PLAIN_TEXT}$"):
        decide(asking, CATALOG, opened, plain_answer)


def test_a_refused_sensitive_answer_names_only_its_kind() -> None:
    # The refusal is recorded in history, read by people who may not see the field (brief, D30).
    with pytest.raises(AnswerRefused) as refused:
        run_case(
            claim_asking_the_id(),
            file=OPENING,
            answers=[("assess", "accept", "ana", {"national_id": 1850578006})],
            people=PEOPLE,
        )
    assert str(refused.value) == "national_id is a string, and the answer gives a number"


def test_a_form_keeps_wrapped_only_sensitive_values() -> None:
    # The client wraps every form value: it can't tell which fields are sensitive (brief, D31).
    definition = claim_asking_the_id()
    definition["fields"]["notes"] = {"type": "string", "display": {"title": "Notes"}}
    definition["steps"]["assess"]["outcomes"]["accept"]["sets"] = ["national_id", "notes"]
    form = {"national_id": NATIONAL_ID, "notes": "checked by phone"}
    run = run_case(
        definition, file=OPENING, answers=[("assess", "accept", "ana", form)], people=PEOPLE
    )
    assert run.state.values["national_id"] == Sensitive(NATIONAL_ID)
    assert run.state.values["notes"] == "checked by phone"
    assert "ana answered assess#1 accept as adjuster, setting national_id and notes" in run.history


def with_steps(**steps: dict[str, Any]) -> dict[str, Any]:
    """The claim, with more steps."""
    definition = claim()
    definition["steps"] |= steps
    return definition


def lookup(order_id: Any, **more: Any) -> dict[str, Any]:
    """A step reading the orders system with `order_id`: a stand-in for any activity."""
    return {
        "kind": "activity",
        "display": {"title": "Look it up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": order_id},
    } | more


def test_a_workflow_step_is_never_given_a_sensitive_value() -> None:
    # Its worker belongs to another team and doesn't hold the case's key (brief, D31).
    kyc = {
        "kind": "workflow",
        "display": {"title": "Check the customer"},
        "workflow": "kyc.check@1",
        "inputs": {"customer_id": {"var": "national_id"}},
    }
    called: list[dict[str, Any]] = []

    def kyc_check(inputs: dict[str, Any]) -> dict[str, Any]:
        called.append(inputs)
        return {}

    run = run_case(
        with_steps(kyc=kyc),
        file=FILE,
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": kyc_check},
    )
    assert run.needs_attention == [
        (
            "kyc#1: kyc.check@1 is a workflow step and can't be given national_id, a sensitive "
            "field: its worker doesn't hold the case's key"
        )
    ]
    assert called == []


def test_an_input_from_a_sensitive_value_stays_sensitive() -> None:
    given: list[dict[str, Any]] = []

    def check(inputs: dict[str, Any]) -> dict[str, Any]:
        given.append(inputs)
        return {"status": "known"}

    steps = {
        # Read as it is, and computed from it: both carry it.
        "as_it_is": lookup({"var": "national_id"}),
        "computed": lookup({"cat": ["id:", {"var": "national_id"}]}),
        # A condition reads the real value inside the worker.
        "only_this_id": lookup(
            {"var": "policy_id"}, when={"==": [{"var": "national_id"}, NATIONAL_ID]}
        ),
    }
    run = run_case(
        with_steps(**steps),
        file=FILE,
        answers=[],
        people=PEOPLE,
        activities={"orders.lookup@1": check},
    )
    # The activity's code gets the plain value; the command carrying it, the wrapper.
    assert given == [
        {"order_id": NATIONAL_ID},
        {"order_id": f"id:{NATIONAL_ID}"},
        {"order_id": "pol-3"},
    ]
    assert {"as_it_is", "computed", "only_this_id"} <= run.steps_done
    assert NATIONAL_ID not in "\n".join(run.history)


def test_a_plan_step_carries_a_sensitive_value() -> None:
    plan = {
        "plan": "check-id",
        "version": 1,
        "display": {"title": "Check an ID"},
        "fields": {"id": {"type": "string"}},
        "initial": "check",
        "states": {
            "check": {
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "id"}},
                "on": {"done": "checked"},
            },
            "checked": {"final": "succeeded"},
        },
    }
    step = {
        "kind": "plan",
        "display": {"title": "Check the ID"},
        "plan": "check-id@1",
        "inputs": {"id": {"var": "national_id"}},
    }
    # The plan's field carries the wrapper into the plan (brief, D28).
    case = parse_case(with_steps(check_id=step))
    _, commands = decide(case, CATALOG, CaseState("memory"), Opened(wrapped_file(), None))
    [start] = [command for command in commands if isinstance(command, StartPlan)]
    assert start.fields["id"].value == Sensitive(NATIONAL_ID)
    given: list[dict[str, Any]] = []

    def check(inputs: dict[str, Any]) -> dict[str, Any]:
        given.append(inputs)
        return {"status": "known"}

    run = run_case(
        with_steps(check_id=step),
        file=FILE,
        answers=[],
        people=PEOPLE,
        plans={"check-id@1": plan},
        activities={"orders.lookup@1": check},
    )
    # Inside the plan, its activity's code gets the plain value.
    assert given == [{"order_id": NATIONAL_ID}]
    assert "check_id" in run.steps_done


def test_an_approval_of_a_sensitive_input_keeps_its_digest_sensitive() -> None:
    # A digest of a national ID is easy to reverse by trying every one: it is wrapped too.
    approved = lookup(
        {"var": "national_id"},
        approval={"roles": ["support-lead"], "display": {"reason": "It reads the ID"}},
    )
    run = run_case(
        with_steps(approved=approved),
        file=FILE,
        answers=[("approved.approval#1", "approve", "kim")],
        people={**PEOPLE, "kim": ["claims-sensitive", "support-lead"]},
    )
    [ran] = [r for r in run.state.runs if r.step == "approved"]
    assert ran.status == "done" and isinstance(ran.approved, GivenApproval)
    assert isinstance(ran.approved.digest, Sensitive)


def test_showing_a_sensitive_reference_writes_no_reference() -> None:
    definition = claim()
    definition["fields"]["customer_id"] |= {"sensitive": True, "visible_to": ["adjuster"]}
    run = run_case(definition, file=FILE, answers=[shown("customer_id", "ana")], people=PEOPLE)
    assert "ana was shown customer_id (crm ‹sensitive›)" in run.history
    assert "cus-7" not in "\n".join(run.history)


def test_an_activitys_message_is_never_recorded() -> None:
    # Ventoux can't know what an activity says: a CRM's error may quote the ID it was given.
    def failing(inputs: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(f"no order {inputs['order_id']}")

    for given in ({"var": "national_id"}, {"var": "policy_id"}):  # sensitive or not, the same
        run = run_case(
            with_steps(check=lookup(given)),
            file=FILE,
            answers=[],
            people=PEOPLE,
            activities={"orders.lookup@1": failing},
        )
        assert run.needs_attention == ["check#1: orders.lookup@1 failed: ‹sensitive›"]
        assert "no order" not in "\n".join(run.history)


def test_the_guides_examples_run_as_written() -> None:
    # The case data guide's sensitive example, its second Python block, run as the guide shows it.
    example = GUIDE.split("```python\n")[2].split("```")[0]
    assert "national_id" in example
    namespace: dict[str, Any] = {"run_case": run_case, "claim": claim(), "PEOPLE": PEOPLE}
    exec(example, namespace)  # noqa: S102 -- our guide, run so it can't drift from the code
