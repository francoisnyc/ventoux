"""A plan's path is never chosen by untrusted data (brief, D49).

Tests go through `run_plan`, `run_case`, `validate` and `validate_case`, and read what each reports.
See docs/layers/fix-plan-transitions.md.
"""

from decimal import Decimal
from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.plan import parse_plan
from ventoux.core.provenance import sourced
from ventoux.core.validate import Issue, validate
from ventoux.testing import CATALOG, run_case, run_plan


def branching(note_source: str | None = None) -> dict[str, Any]:
    """A plan that looks the order up, then goes to `paid` if `note` says "go", else `failed`.
    `note_source` marks the field, as a plan declares an untrusted one."""
    note: dict[str, Any] = {"type": "string"}
    if note_source is not None:
        note["source"] = note_source
    return {
        "plan": "check-only",
        "version": 1,
        "display": {"title": "Check the order"},
        "fields": {"order_id": {"type": "reference", "system": "orders"}, "note": note},
        "initial": "check_order",
        "states": {
            "check_order": {
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "order_id"}},
                "on": {
                    "done": [
                        {"target": "paid", "when": {"==": [{"var": "note"}, "go"]}},
                        {"target": "failed"},
                    ],
                    "not_found": "failed",
                },
            },
            "paid": {"final": "succeeded"},
            "failed": {"final": "failed"},
        },
    }


ORDER = sourced("ord-1", "system:opener")


def test_a_transition_reading_untrusted_data_stops_the_plan() -> None:
    # Whatever the note says, the plan stops before reading it: untrusted data can't choose its
    # path (brief, D49). The message names the field and its source, never the value.
    for said in ("go", "anything else"):
        run = run_plan(
            branching(),
            fields={"order_id": ORDER, "note": sourced(said, "untrusted:customer")},
            answers=[],
        )
        assert run.status == "stopped"
        assert run.reason == (
            "on done, the transition to paid reads note (untrusted:customer), and untrusted "
            "data can't choose a plan's path"
        )
        assert said not in run.reason


def test_an_unrecognised_source_stops_the_plan_too() -> None:
    # Fail closed: a source the engine doesn't recognise is never read as trusted.
    run = run_plan(
        branching(),
        fields={"order_id": ORDER, "note": sourced("go", "rumour:mill")},
        answers=[],
    )
    assert run.status == "stopped"
    assert run.reason == (
        "on done, the transition to paid reads note (rumour:mill), and untrusted data can't "
        "choose a plan's path"
    )


def first_holds(plan: dict[str, Any]) -> dict[str, Any]:
    """The plan with a transition on a trusted amount tried before the one on the note."""
    plan["fields"]["amount"] = {"type": "number"}
    plan["states"]["check_order"]["on"]["done"].insert(
        0, {"target": "paid", "when": {"<": [{"var": "amount"}, 100]}}
    )
    return plan


def test_a_transition_never_tried_refuses_nothing() -> None:
    # The first transition reads a trusted amount and holds: the one on the note is never tried,
    # so untrusted data chose nothing. Trusted data still chooses the path.
    small = run_plan(
        first_holds(branching()),
        fields={
            "order_id": ORDER,
            "amount": sourced(Decimal(40), "system:opener"),
            "note": sourced("anything", "untrusted:customer"),
        },
        answers=[],
    )
    assert small.status == "succeeded"
    trusted = run_plan(
        branching(),
        fields={"order_id": ORDER, "note": sourced("other", "person:ana")},
        answers=[],
    )
    assert trusted.status == "failed"


def branching_case() -> dict[str, Any]:
    """A case whose plan step gives the plan the customer's note, and reaches `settled`, the
    milestone that closes it."""
    return {
        "case": "settle",
        "display": {"title": "Settle"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}},
            "note": {
                "type": "string",
                "display": {"title": "What the customer wrote"},
                "source": "untrusted:customer",
            },
        },
        "steps": {
            "settle": {
                "kind": "plan",
                "display": {"title": "Settle"},
                "plan": "check-only@1",
                "inputs": {"order_id": {"var": "order_id"}, "note": {"var": "note"}},
                "reaches": ["settled"],
            }
        },
        "milestones": {"settled": {"display": {"title": "Settled"}}},
        "closes_when": ["settled"],
    }


def test_a_plan_step_branching_on_untrusted_data_needs_attention() -> None:
    # The bug: the customer's "go" closed the case. Now the plan stops whatever the note says, the
    # step needs attention, and nothing is reached (brief, D17, D49).
    for said in ("go", "anything else"):
        run = run_case(
            branching_case(),
            file={"order_id": "ord-1", "note": said},
            answers=[],
            people={},
            plans={"check-only@1": branching()},
        )
        assert run.needs_attention == [
            (
                "settle#1: check-only@1 stopped: on done, the transition to paid reads note "
                "(untrusted:customer), and untrusted data can't choose a plan's path"
            )
        ]
        assert "reached settled" not in run.history
        assert not run.closed


def test_plan_validation_refuses_a_transition_on_an_untrusted_field() -> None:
    # A field the plan declares untrusted stays untrusted whatever the case gives (a mark adds
    # distrust), so a transition reading it is refused every time it is tried (brief, D49).
    issues = validate(parse_plan(branching("untrusted:llm")), CATALOG)
    assert [(i.path, i.code, i.message, i.severity) for i in issues] == [
        (
            "states.check_order.on.done[0].when",
            "UNTRUSTED_TRANSITION",
            (
                "the transition to paid reads note, which the plan declares untrusted:llm, and "
                "untrusted data can't choose a plan's path: branch in the case instead, where a "
                "step's condition or a person's task decides"
            ),
            "error",
        )
    ]
    # Unmarked, the plan can't know: the case's check and the runtime say it.
    assert validate(parse_plan(branching()), CATALOG) == []


def case_issues(definition: dict[str, Any], plan: dict[str, Any]) -> list[Issue]:
    """What case validation says of trust at the plan step's inputs, given the plan."""
    found = validate_case(parse_case(definition), CATALOG, {"check-only@1": plan})
    trust = ("UNTRUSTED_TRIGGER", "WRITER_DECIDES")
    return [i for i in found if i.path.startswith("steps.settle.inputs") and i.code in trust]


def test_case_validation_refuses_an_untrusted_input_a_transition_reads() -> None:
    # The customer's note reaches the plan's transition whoever writes it: the plan stops each
    # time it tries it, so the case's check refuses the input that carries it (brief, D34, D49).
    assert case_issues(branching_case(), branching()) == [
        Issue(
            "steps.settle.inputs.note",
            "UNTRUSTED_TRIGGER",
            "check-only@1 branches on note (in check_order, the transition to paid), and this "
            "input reads note, which comes from untrusted:customer whoever writes it, and "
            "untrusted data can't choose a plan's path, so the plan stops whenever it tries that "
            "transition: give it a value a person or a trusted system gives, or branch in the "
            "case",
        )
    ]


def with_two_writers() -> dict[str, Any]:
    """The case with `note` set by rules as it opens: from the customer's text by one, from the
    team's own remark by the other."""
    definition = branching_case()
    fields = definition["fields"]
    fields["customer_note"] = fields["note"]
    fields["team_note"] = {"type": "string", "display": {"title": "What the team wrote"}}
    fields["note"] = {"type": "string", "display": {"title": "The note the plan reads"}}
    definition["rules"] = {
        "from_customer": {
            "display": {"title": "Take the customer's note"},
            "on": "opened",
            "then": {"set": {"note": {"var": "customer_note"}}},
        },
        "from_team": {
            "display": {"title": "Take the team's note"},
            "on": "opened",
            "then": {"set": {"note": {"var": "team_note"}}},
        },
    }
    return definition


def test_case_validation_warns_when_only_some_writers_make_it_untrusted() -> None:
    # Whether the plan stops depends on which rule set note last: a warning, never an error,
    # which must hold for every case (brief, D34, D42).
    assert case_issues(with_two_writers(), branching()) == [
        Issue(
            "steps.settle.inputs.note",
            "WRITER_DECIDES",
            "check-only@1 branches on note (in check_order, the transition to paid), and this "
            "input reads note, which comes from untrusted:customer when from_customer sets it, "
            "and not when from_team does, and untrusted data can't choose a plan's path, so "
            "whether the plan stops there depends on which rule set note last: set note only "
            "from trusted values",
            "warning",
        )
    ]


def test_case_validation_says_nothing_of_a_trusted_input_a_transition_reads() -> None:
    definition = branching_case()
    del definition["fields"]["note"]["source"]
    assert case_issues(definition, branching()) == []
    # A field the plan itself declares untrusted is the plan's check to say, whatever the case
    # gives it (one cause, one issue).
    assert case_issues(branching_case(), branching("untrusted:llm")) == []
