"""Dates: a day on the calendar the case was given, compared as a value; nothing reads today.

See docs/layers/16-field-types.md (16a), docs/guides/expressions.md and brief D66.
"""

import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, ValidationError
from test_case import (
    PEOPLE,
    SMALL,
    SMALL_REVIEW,
    FindInput,
    contract,
    with_crm,
    with_customer_steps,
)

from ventoux.case.answers import AnswerRefused
from ventoux.case.definition import parse_case
from ventoux.case.types import case_types
from ventoux.case.validate import validate_case
from ventoux.core.expressions import (
    BooleanType,
    DateType,
    ExpressionError,
    ExpressionInvalid,
    FieldType,
    NumberType,
    StringType,
    check,
    evaluate,
    parse_expression,
    render,
)
from ventoux.core.output_sources import source
from ventoux.core.sensitive import Sensitive
from ventoux.temporal.carried import state_as_data, state_from_data
from ventoux.temporal.converter import ExactPayloadConverter
from ventoux.testing import CATALOG, CaseRefused, EventRefused, run_case, send
from ventoux.tooling.schema import case_schema, schema_files

ROOT = Path(__file__).parent.parent


def test_a_date_literal_that_is_not_a_day_is_refused() -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression({"date": "2026-02-30"})
    assert str(refused.value) == (
        'date: "2026-02-30" is not a day on the calendar; '
        'write a date as YYYY-MM-DD, such as "2026-10-31"'
    )


@pytest.mark.parametrize(
    "text",
    [
        "20261031",  # Python's `date.fromisoformat` reads this since 3.11; D66 doesn't
        "2026-W44-6",  # a week date, the same
        "2026-1-5",  # a day and a month need two digits each
        "31/10/2026",
        "2026-10-31T23:30:00Z",  # a moment, not a day
        "0000-01-01",  # there is no year 0
        "2026-13-01",
        "٢٠٢٦-١٠-٣١",  # digits, but not ASCII ones
    ],
)
def test_only_yyyy_mm_dd_naming_a_real_day_is_a_date(text: str) -> None:
    with pytest.raises(ExpressionInvalid, match="is not a day on the calendar"):
        parse_expression({"date": text})


def test_a_date_literal_takes_a_text() -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        parse_expression({"date": 20261031})
    assert str(refused.value) == 'date takes a text, like {"date": "2026-10-31"}'


def test_a_date_literal_is_a_day_and_reads_as_feel_writes_it() -> None:
    literal = parse_expression({"date": "2026-10-31"})
    assert literal == date(2026, 10, 31)
    assert render(literal) == 'date("2026-10-31")'


CLAIM: dict[str, FieldType] = {
    "incident_date": DateType(),
    "policy_start": DateType(),
    "note": StringType(),
    "amount": NumberType(),
}


def test_a_date_compared_with_a_number_is_refused_before_anything_runs() -> None:
    compared = parse_expression({">": [{"var": "incident_date"}, 30]})
    with pytest.raises(ExpressionInvalid) as refused:
        check(compared, CLAIM)
    assert str(refused.value) == (
        ">[1]: `>` compares two numbers or two dates, and this is a number, not a date"
    )


@pytest.mark.parametrize(
    "condition",
    [
        {">=": [{"var": "incident_date"}, {"var": "policy_start"}]},
        {"<": [{"var": "incident_date"}, {"date": "2027-01-01"}]},
        {"==": [{"var": "incident_date"}, {"date": "2026-10-31"}]},
        {"in": [{"var": "incident_date"}, [{"date": "2026-12-25"}, {"date": "2026-12-26"}]]},
    ],
)
def test_two_dates_compare(condition: object) -> None:
    assert check(parse_expression(condition), CLAIM) == BooleanType()


def test_a_date_compared_with_a_text_is_refused_write_a_date_literal() -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        check(parse_expression({"==": [{"var": "incident_date"}, "2026-10-31"]}), CLAIM)
    assert str(refused.value) == (
        "==[1]: `==` compares values of the same type, and this is a string, not a date"
    )


def test_a_date_ordered_against_a_text_is_refused() -> None:
    with pytest.raises(ExpressionInvalid) as refused:
        check(parse_expression({"<": [{"var": "note"}, {"var": "incident_date"}]}), CLAIM)
    assert str(refused.value) == (
        "<[0]: `<` compares two numbers or two dates, and this is a string"
    )


def test_string_of_a_date_is_a_text() -> None:
    assert check(parse_expression({"string": [{"var": "incident_date"}]}), CLAIM) == StringType()


def test_today_has_no_shape_so_it_cannot_be_written() -> None:
    # No operator reads the calendar, as none reads the clock (brief, D66).
    with pytest.raises(ExpressionInvalid, match="^`today` is not an operator"):
        parse_expression({">": [{"var": "incident_date"}, {"today": []}]})


BEFORE_2027 = parse_expression({"<": [{"var": "incident_date"}, {"date": "2027-01-01"}]})


def test_a_date_field_holding_a_text_is_an_error_never_false() -> None:
    with pytest.raises(ExpressionError) as stopped:
        evaluate(BEFORE_2027, {"incident_date": "2026-10-31"})
    assert str(stopped.value) == (
        "`<` compares two numbers or two dates, and it was given a string"
    )


def test_a_date_field_holding_a_moment_is_an_error() -> None:
    # Python: a `datetime` is also a `date`, so it must be refused by name (brief, D66).
    moment = datetime(2026, 10, 31, 23, 30, tzinfo=UTC)
    with pytest.raises(ExpressionError) as stopped:
        evaluate(BEFORE_2027, {"incident_date": moment})
    assert str(stopped.value) == (
        "incident_date holds a datetime, and an expression reads only decimals, texts, "
        "booleans and dates"
    )


@pytest.mark.parametrize(
    ("condition", "holds"),
    [
        ({">=": [{"var": "incident_date"}, {"var": "policy_start"}]}, True),
        ({"<": [{"var": "incident_date"}, {"var": "policy_start"}]}, False),
        ({"==": [{"var": "incident_date"}, {"date": "2026-10-31"}]}, True),
        ({"!=": [{"var": "incident_date"}, {"date": "2026-10-31"}]}, False),
        ({"in": [{"var": "incident_date"}, [{"date": "2026-10-31"}]]}, True),
    ],
)
def test_two_dates_compare_as_days(condition: object, holds: bool) -> None:
    file = {"incident_date": date(2026, 10, 31), "policy_start": date(2026, 1, 1)}
    assert evaluate(parse_expression(condition), file) is holds


def test_string_of_a_date_gives_yyyy_mm_dd() -> None:
    said = evaluate(
        parse_expression({"string": [{"var": "incident_date"}]}),
        {"incident_date": date(2026, 1, 5)},
    )
    assert said == "2026-01-05"


def test_the_published_schema_holds_the_date_and_no_today() -> None:
    written = json.dumps(case_schema())
    # A date field, and the literal's shape: the calendar check is the engine's (brief, D60).
    assert '"const": "date"' in written or '"enum": ["date"]' in written
    assert '"required": ["date"]' in written
    # No operator reads the calendar, so the schema has no shape for one (brief, D66).
    assert "today" not in written
    # Regenerated with `ventoux schema`; CI's `--unchanged` checks the same bytes.
    for name, text in schema_files().items():
        assert (ROOT / "schema" / name).read_text() == text


# --- An activity's output: a date is read as every entry point reads one (tutor review) ---


class Reported(BaseModel):
    email: Annotated[str, source("system:crm")]
    # The day the customer reported it, as the CRM means it, and the CRM's own fact.
    reported_on: Annotated[date, source("system:crm")]


@pytest.mark.parametrize(
    ("given", "kind"),
    [
        (1793145600, "an int"),  # a Unix timestamp: lax Pydantic would pick 2026-10-28, in UTC
        ("2026-10-31T00:00:00Z", "a string"),  # a moment, written as text
        (datetime(2026, 10, 31, tzinfo=UTC), "a datetime"),  # a moment at midnight
    ],
)
def test_an_output_date_that_is_a_moment_fails_the_step_and_nothing_lands(
    given: object, kind: str
) -> None:
    # Ventoux never turns a moment into a day (brief, D66): as "31/10/2026" in a form is refused.
    catalog = with_crm()
    found = catalog.get("crm.find@1").model_copy(update={"output": Reported})  # no check runs
    catalog._contracts["crm.find@1"] = found  # bypassing registration, as test_case does
    run = run_case(
        with_customer_steps("find.email", "notices.draft@1", "to"),
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={
            "crm.find@1": lambda inputs: {"email": "c@x.com", "reported_on": given},
            "notices.draft@1": lambda inputs: {"notice_id": "n-1"},
        },
        catalog=catalog,
    )
    assert run.needs_attention == [
        (
            f"find#1: crm.find@1 gave reported_on as {kind}, which isn't a day: an output date is "
            "a date, or a text written YYYY-MM-DD, never a moment (brief, D66)"
        )
    ]
    assert not any(line.startswith("find#1 done") for line in run.history)
    assert "find.reported_on" not in run.state.values  # nothing it gave lands
    assert "find.email" not in run.state.values


@pytest.mark.parametrize("given", ["2026-10-31", date(2026, 10, 31)])
def test_an_output_date_lands_as_a_day(given: object) -> None:
    # As text, which is how a date comes back over Temporal, or as a date, in memory.
    catalog = with_crm()
    found = catalog.get("crm.find@1").model_copy(update={"output": Reported})
    catalog._contracts["crm.find@1"] = found
    run = run_case(
        with_customer_steps("find.email", "notices.draft@1", "to"),
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={
            "crm.find@1": lambda inputs: {"email": "c@x.com", "reported_on": given},
            "notices.draft@1": lambda inputs: {"notice_id": "n-1"},
        },
        catalog=catalog,
    )
    assert run.needs_attention == []
    assert type(run.state.values["find.reported_on"]) is date
    assert run.state.values["find.reported_on"] == date(2026, 10, 31)


class Moment(BaseModel):
    reported_at: datetime  # a moment: which day it falls on depends on a time zone


def test_a_contract_whose_output_is_a_moment_is_refused_at_registration() -> None:
    with pytest.raises(ValidationError) as refused:
        contract("crm.reported", FindInput, Moment)
    assert (
        "crm.reported@1: output reported_at is datetime, which the case file can't hold exactly. "
        "An output is a decimal (Decimal), a text (str), true or false (bool) or a day (date)"
    ) in str(refused.value)


def test_a_contract_whose_output_is_a_day_registers() -> None:
    catalog = with_crm()
    catalog.register(contract("crm.reported", FindInput, Reported))
    assert catalog.get("crm.reported@1").output is Reported


# --- A form: a person gives a date (slice 4) ---


def claim_case() -> dict[str, Any]:
    """A claim: the policy's start from the opener, the incident's day from the adjuster's form,
    and a settlement only for an incident while the policy was in force."""
    return {
        "case": "claim",
        "display": {"title": "Insurance claim"},
        "fields": {
            "policy_start": {"type": "date", "display": {"title": "Policy start"}},
            "incident_date": {"type": "date", "display": {"title": "Date of the incident"}},
        },
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess the claim"},
                "roles": ["adjuster"],
                "outcomes": {
                    "accept": {
                        "display": {"title": "Accept the claim"},
                        "sets": ["incident_date"],
                    },
                    "deny": {"display": {"title": "Deny the claim"}},
                },
            },
            "settle": {
                "kind": "task",
                "display": {"title": "Settle the claim"},
                "roles": ["adjuster"],
                "requires": ["assess"],
                "when": {">=": [{"var": "incident_date"}, {"var": "policy_start"}]},
                "outcomes": {"settled": {"display": {"title": "Claim settled"}}},
            },
        },
    }


ADJUSTERS = {"ana": ["adjuster"]}
OPENED = {"policy_start": "2026-01-01"}


@pytest.mark.parametrize(
    ("given", "message"),
    [
        (
            "31/10/2026",
            "incident_date is a date, written YYYY-MM-DD, and the answer gives a string that isn't one",
        ),
        (
            "2026-10-31T23:30:00Z",
            "incident_date is a date, written YYYY-MM-DD, and the answer gives a string that isn't one",
        ),
        (Decimal(20261031), "incident_date is a date, and the answer gives a number"),
        (
            datetime(2026, 10, 31, tzinfo=UTC),
            "incident_date is a date, and the answer gives a datetime",
        ),
    ],
)
def test_a_form_giving_a_date_that_is_not_a_day_is_refused(given: object, message: str) -> None:
    # The message names the kind, never the value: it may be hidden from a reader (brief, D30).
    with pytest.raises(AnswerRefused, match=f"^{re.escape(message)}$"):
        run_case(
            claim_case(),
            file=OPENED,
            answers=[("assess", "accept", "ana", {"incident_date": given})],
            people=ADJUSTERS,
        )


@pytest.mark.parametrize(
    ("incident", "settles"),
    [("2026-10-31", True), ("2025-12-31", False)],  # during the policy, then the day before it
)
def test_a_form_date_is_read_into_a_day_and_a_condition_reads_it(
    incident: str, settles: bool
) -> None:
    run = run_case(
        claim_case(),
        file=OPENED,
        answers=[("assess", "accept", "ana", {"incident_date": incident})],
        people=ADJUSTERS,
    )
    assert type(run.state.values["incident_date"]) is date
    assert type(run.state.values["policy_start"]) is date  # the opening's, read the same way
    assert any("settle" in waiting for waiting in run.waiting_for) is settles


def test_a_sensitive_date_is_kept_wrapped_and_read_into_a_day() -> None:
    # `run_case`, as the client, wraps a sensitive value; kept wrapped, with the day inside
    # (brief, D31) (brief, D66).
    definition = claim_case()
    definition["fields"]["incident_date"] |= {"sensitive": True, "visible_to": ["adjuster"]}
    run = run_case(
        definition,
        file=OPENED,
        answers=[("assess", "accept", "ana", {"incident_date": "2026-10-31"})],
        people=ADJUSTERS,
    )
    kept = run.state.values["incident_date"]
    assert isinstance(kept, Sensitive)
    assert kept.value == date(2026, 10, 31)
    assert any("settle" in waiting for waiting in run.waiting_for)  # its condition read the day


# --- The opening and an event: the same reading (slice 5) ---


def reportable() -> dict[str, Any]:
    """The claim, with an event from the portal saying which day the customer reported it."""
    definition = claim_case()
    definition["events"] = {
        "reported": {
            "display": {"title": "The customer reports the claim"},
            "sent_by": {"system": "portal"},
            "payload": {"on": {"type": "date", "display": {"title": "Reported on"}}},
        }
    }
    return definition


NOT_A_DAY = "is a date, written YYYY-MM-DD, and {by} gives a string that isn't one"


@pytest.mark.parametrize(
    ("given", "message"),
    [
        ("31/10/2026", f"reported.on {NOT_A_DAY.format(by='the event')}"),
        (Decimal(20261031), "reported.on is a date, and the event gives a number"),
    ],
)
def test_an_event_carrying_a_date_that_is_not_a_day_is_refused(given: object, message: str) -> None:
    with pytest.raises(EventRefused, match=f"^{re.escape(message)}$"):
        run_case(
            reportable(),
            file=OPENED,
            answers=[send("reported", {"on": given}, "system:portal")],
            people=ADJUSTERS,
        )


@pytest.mark.parametrize(
    ("given", "message"),
    [
        ("31/10/2026", f"policy_start {NOT_A_DAY.format(by='the opening')}"),
        (
            datetime(2026, 1, 1, tzinfo=UTC),
            "policy_start is a date, and the opening gives a datetime",
        ),
    ],
)
def test_an_opening_giving_a_date_that_is_not_a_day_is_refused(given: object, message: str) -> None:
    with pytest.raises(CaseRefused, match=f"^{re.escape(message)}$"):
        run_case(claim_case(), file={"policy_start": given}, answers=[], people=ADJUSTERS)


def test_an_events_date_lands_as_a_day() -> None:
    run = run_case(
        reportable(),
        file=OPENED,
        answers=[send("reported", {"on": "2026-10-31"}, "system:portal")],
        people=ADJUSTERS,
    )
    assert run.state.values["reported.on"] == date(2026, 10, 31)
    assert type(run.state.values["reported.on"]) is date


def reading_the_report(condition: object) -> list[str]:
    """What validation says of the CRM lookup's date output, read by the notice's condition."""
    catalog = with_crm()
    catalog.register(contract("crm.reported", FindInput, Reported))
    definition = with_customer_steps("find.email", "notices.draft@1", "to")
    definition["steps"]["find"]["activity"] = "crm.reported@1"
    definition["steps"]["notify"]["when"] = condition
    return [
        f"{issue.path}: {issue.message}"
        for issue in validate_case(parse_case(definition), catalog)
        if issue.severity == "error"
    ]


def test_an_outputs_date_is_read_as_a_date_by_validation() -> None:
    assert reading_the_report({">=": [{"var": "find.reported_on"}, {"date": "2026-01-01"}]}) == []
    assert reading_the_report({">=": [{"var": "find.reported_on"}, 30]}) == [
        "steps.notify.when: >=[1]: `>=` compares two numbers or two dates, and this is a number, not a date"
    ]


def test_a_condition_with_a_date_literal_runs_its_activity() -> None:
    # Run for real: the sources of a condition holding a date literal are read before the
    # activity is scheduled, and the literal adds none (brief, D21) (brief, D66).
    catalog = with_crm()
    catalog.register(contract("crm.reported", FindInput, Reported))
    definition = with_customer_steps("find.email", "notices.draft@1", "to")
    definition["steps"]["find"]["activity"] = "crm.reported@1"
    definition["steps"]["notify"]["when"] = {
        ">=": [{"var": "find.reported_on"}, {"date": "2026-01-01"}]
    }
    drafted: list[str] = []

    def drafting(inputs: dict[str, Any]) -> dict[str, Any]:
        drafted.append(inputs["to"])
        return {"notice_id": "n-1"}

    run_case(
        definition,
        file=SMALL,
        answers=[SMALL_REVIEW],
        people=PEOPLE,
        activities={
            "crm.reported@1": lambda inputs: {"email": "c@x.com", "reported_on": "2026-10-31"},
            "notices.draft@1": drafting,
        },
        catalog=catalog,
    )
    assert drafted == ["c@x.com"]


# --- On Temporal: a date crosses a payload as YYYY-MM-DD, and is read back by its type (slice 6) ---


def test_a_date_crosses_a_payload_as_yyyy_mm_dd() -> None:
    payload = ExactPayloadConverter().to_payload({"policy_start": date(2026, 1, 5)})
    assert payload is not None
    assert payload.data == b'{"policy_start": "2026-01-05"}'


def test_a_moment_never_crosses_a_payload_as_a_date() -> None:
    # Fail closed: a `datetime` is a `date` to Python, never to Ventoux (brief, D66).
    with pytest.raises(TypeError, match="^datetime can't be written exactly as JSON$"):
        ExactPayloadConverter().to_payload({"at": datetime(2026, 1, 5, tzinfo=UTC)})


def test_a_carried_state_reads_its_dates_back_as_days() -> None:
    # Continue-as-new carries the state as data, where a day is text; read back by each value's
    # declared type, every date is a day again, a sensitive one inside its wrapper (brief, D27, D66).
    definition = reportable()
    definition["fields"]["policy_start"] |= {"sensitive": True, "visible_to": ["adjuster"]}
    run = run_case(
        definition,
        file={"policy_start": "2026-01-01"},
        answers=[
            ("assess", "accept", "ana", {"incident_date": "2026-10-31"}),
            send("reported", {"on": "2026-11-02"}, "system:portal"),
        ],
        people=ADJUSTERS,
    )
    converter = ExactPayloadConverter()
    payload = converter.to_payload(state_as_data(run.state))
    assert payload is not None
    case = parse_case(definition)
    back = state_from_data(converter.from_payload(payload, dict), case_types(case, CATALOG))
    assert back.values["incident_date"] == date(2026, 10, 31)
    assert back.values["reported.on"] == date(2026, 11, 2)
    sealed = back.values["policy_start"]
    assert isinstance(sealed, Sensitive) and sealed.value == date(2026, 1, 1)
    assert back == run.state


def test_a_carried_date_that_isnt_a_day_is_refused() -> None:
    # Fail closed: a damaged state is never read as text, or as nothing, the case then decides on.
    data = state_as_data(run_case(claim_case(), file=OPENED, answers=[], people=ADJUSTERS).state)
    data["values"]["policy_start"] = "01/01/2026"
    types = case_types(parse_case(claim_case()), CATALOG)
    with pytest.raises(
        ValueError, match="^a carried date is written YYYY-MM-DD, and policy_start isn't$"
    ):
        state_from_data(data, types)
