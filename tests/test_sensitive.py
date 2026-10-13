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
from ventoux.case.state import Answered, CaseState, Opened
from ventoux.core.sensitive import Sensitive
from ventoux.testing import CATALOG, as_json, run_case

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
