"""Events from outside: declared with one sender, a fact on arrival, and a step that waits for one
(layer 11d).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md (11d) and docs/guides/cases.md, "Events from outside".
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_rules import LEDGER, with_ledger

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.state import Obtained
from ventoux.case.validate import validate_case
from ventoux.core.validate import Issue
from ventoux.testing import (
    CATALOG,
    START,
    AnswerRefused,
    CaseRefused,
    EventRefused,
    ProposalRefused,
    close,
    finish,
    later,
    load_definition,
    propose,
    run_case,
    send,
)

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "omar": ["operations"]}
SMALL = {"order_id": "ord-1", "amount": 40}

CANCELLED = {
    "display": {"title": "The customer cancels"},
    "sent_by": {"system": "portal"},
    "payload": {
        "note": {
            "type": "string",
            "display": {"title": "What the customer wrote"},
            "source": "untrusted:customer",
        }
    },
}
WITHDRAW = {
    "display": {"title": "Stop the review when the customer cancels"},
    "on": {"event": "cancelled"},
    "then": {"stop": ["review"]},
}


def cancellable(**changes: Any) -> dict[str, Any]:
    """The quickstart's refund, with the guide's `cancelled` event and the rule that stops the
    review on it; `changes` replaces top-level keys."""
    definition = copy.deepcopy(REFUND)
    definition["events"] = {"cancelled": copy.deepcopy(CANCELLED)}
    definition["rules"] = {"withdraw_on_cancel": copy.deepcopy(WITHDRAW)}
    return definition | changes


# --- Slice 1: the shape ---


def test_a_rule_on_an_event_the_case_doesnt_declare_is_refused() -> None:
    definition = cancellable()
    definition["rules"]["withdraw_on_cancel"]["on"] = {"event": "refunded"}
    with pytest.raises(
        CaseInvalid, match="^rules.withdraw_on_cancel.on.event: refunded is not an event$"
    ):
        parse_case(definition)


@pytest.mark.parametrize(
    "sent_by",
    [{}, {"system": "portal", "roles": ["support"]}],
    ids=["no sender", "two senders"],
)
def test_an_event_is_sent_by_one_sender(sent_by: dict[str, Any]) -> None:
    definition = cancellable()
    definition["events"]["cancelled"]["sent_by"] = sent_by
    with pytest.raises(CaseInvalid, match="^events.cancelled.sent_by: an event is sent by one "):
        parse_case(definition)


def test_an_event_carries_no_list() -> None:
    definition = cancellable()
    definition["events"]["cancelled"]["payload"]["lines"] = {
        "type": "list",
        "fields": {"sku": {"type": "string"}},
        "display": {"title": "Order lines"},
    }
    with pytest.raises(
        CaseInvalid,
        match="^events.cancelled.payload.lines: an event carries no list yet: a list comes once a "
        "list value can be checked$",
    ):
        parse_case(definition)


@pytest.mark.parametrize("key", ["visible_to", "sensitive"])
def test_a_payload_field_says_only_its_type_title_and_source(key: str) -> None:
    definition = cancellable()
    definition["events"]["cancelled"]["payload"]["note"][key] = ["support"]
    with pytest.raises(CaseInvalid, match=f"^events.cancelled.payload.note.{key}: "):
        parse_case(definition)


def test_an_event_is_not_named_like_a_step() -> None:
    definition = cancellable()
    definition["events"]["review"] = definition["events"].pop("cancelled")
    definition["rules"]["withdraw_on_cancel"]["on"] = {"event": "review"}
    with pytest.raises(
        CaseInvalid,
        match="^events.review: an event is not named like a step, a milestone or a rule$",
    ):
        parse_case(definition)


RECEIPT_SENT = {
    "display": {"title": "The customer uploads a receipt"},
    "sent_by": {"system": "portal"},
    "payload": {
        "receipt": {"type": "reference", "system": "documents", "display": {"title": "The receipt"}}
    },
}
WAIT_FOR_RECEIPT = {
    "kind": "wait",
    "display": {"title": "Wait for the customer's receipt"},
    "event": "receipt_sent",
    "requires": ["review"],
}


def waiting_for_a_receipt() -> dict[str, Any]:
    """The quickstart's refund, waiting after its review for the customer's receipt, before it
    pays: the guide's wait."""
    definition = copy.deepcopy(REFUND)
    definition["events"] = {"receipt_sent": copy.deepcopy(RECEIPT_SENT)}
    definition["steps"]["wait_for_receipt"] = copy.deepcopy(WAIT_FOR_RECEIPT)
    definition["steps"]["pay"]["requires"] = ["wait_for_receipt"]
    return definition


def test_a_wait_names_a_declared_event() -> None:
    definition = waiting_for_a_receipt()
    definition["steps"]["wait_for_receipt"]["event"] = "receipt_uploaded"
    with pytest.raises(
        CaseInvalid, match="^steps.wait_for_receipt.event: receipt_uploaded is not an event$"
    ):
        parse_case(definition)


@pytest.mark.parametrize(
    "key, value",
    [
        ("inputs", {"order_id": {"var": "order_id"}}),
        ("max_age", {"order_id": "1d"}),
        ("approval", {"roles": ["support-lead"], "display": {"reason": "Why"}}),
    ],
)
def test_a_wait_takes_no_inputs_approval_or_max_age(key: str, value: Any) -> None:
    definition = waiting_for_a_receipt()
    definition["steps"]["wait_for_receipt"][key] = value
    with pytest.raises(CaseInvalid, match=f"^steps.wait_for_receipt.{key}: not a field here$"):
        parse_case(definition)


def test_events_and_a_wait_read() -> None:
    parse_case(cancellable())
    parse_case(waiting_for_a_receipt())


# --- Slice 2: an arrival, in memory ---


def test_an_event_the_case_doesnt_declare_is_refused() -> None:
    with pytest.raises(
        EventRefused, match="^refunded is not an event of refund: its events are cancelled$"
    ):
        run_case(
            cancellable(),
            file=SMALL,
            answers=[send("refunded", {}, "system:portal")],
            people=PEOPLE,
        )


CUSTOMER_CALLED = {
    "display": {"title": "The customer called"},
    "sent_by": {"roles": ["support"]},
    "payload": {"wants_refund": {"type": "boolean", "display": {"title": "Still wants it"}}},
}


def with_a_call() -> dict[str, Any]:
    """The cancellable refund, also taking a call support logs."""
    definition = cancellable()
    definition["events"]["customer_called"] = copy.deepcopy(CUSTOMER_CALLED)
    return definition


@pytest.mark.parametrize(
    "sent, refused",
    [
        (
            send("cancelled", {"note": "please cancel"}, "system:crm"),
            "cancelled is sent by portal, and this one comes from system:crm",
        ),
        (
            send("cancelled", {"note": "please cancel"}, "ana"),
            "cancelled is sent by portal, and this one comes from ana",
        ),
        (
            send("customer_called", {"wants_refund": False}, "eve"),
            "customer_called is sent by support, and eve has no role",
        ),
        (
            send("customer_called", {"wants_refund": False}, "system:portal"),
            "customer_called is sent by support, and this one comes from system:portal",
        ),
        (
            send("customer_called", {"wants_refund": False}, "Ana"),
            "",  # a person's identifier is written one way, checked first (brief, D22)
        ),
    ],
    ids=["another system", "a person", "no role", "a system", "a misspelt person"],
)
def test_only_its_sender_sends_an_event(sent: Any, refused: str) -> None:
    with pytest.raises(EventRefused, match=f"^{refused}"):
        run_case(with_a_call(), file=SMALL, answers=[sent], people=PEOPLE)


@pytest.mark.parametrize(
    "payload, refused",
    [
        ({}, "cancelled's payload has no note"),
        (
            {"note": "please cancel", "tone": "angry"},
            "cancelled's payload has no field tone: its fields are note",
        ),
        ({"note": 3}, "cancelled.note is a string, and the event gives a number"),
    ],
    ids=["missing", "extra", "wrong type"],
)
def test_an_event_carries_exactly_its_payload(payload: dict[str, Any], refused: str) -> None:
    with pytest.raises(EventRefused, match=f"^{refused}$"):
        run_case(
            cancellable(),
            file=SMALL,
            answers=[send("cancelled", payload, "system:portal")],
            people=PEOPLE,
        )


def test_an_arrival_lands_its_payload_and_its_rule_acts() -> None:
    run = run_case(
        cancellable(),
        file=SMALL,
        answers=[later("2h"), send("cancelled", {"note": "please cancel"}, "system:portal")],
        people=PEOPLE,
    )
    assert run.history[-4:] == [
        "cancelled#1 from portal, giving note from system:portal, untrusted:customer",
        "withdraw_on_cancel#1 on event cancelled: stopping review",
        "cancelled review#1: stopped by withdraw_on_cancel#1",
        "closed: nothing left to do",
    ]
    # Where it came from: its sender, and the mark the field declares (brief, D12).
    assert run.state.values["cancelled.note"] == "please cancel"
    assert run.state.sources["cancelled.note"] == {"system:portal", "untrusted:customer"}
    # Obtained when it reached the case, by its arrival (brief, D33).
    assert run.state.obtained["cancelled.note"] == Obtained(START + 7200, "cancelled#1")


def test_a_persons_event_comes_from_them() -> None:
    definition = with_a_call()
    run = run_case(
        definition,
        file=SMALL,
        answers=[send("customer_called", {"wants_refund": True}, "ana")],
        people=PEOPLE,
    )
    assert "customer_called#1 by ana, as support, giving wants_refund from person:ana" in (
        run.history
    )
    assert run.state.sources["customer_called.wants_refund"] == {"person:ana"}
    assert run.waiting_for == ["review by support"]  # listening holds nothing


def test_each_arrival_is_its_own_entry_and_the_latest_payload_stands() -> None:
    definition = cancellable()
    definition["rules"] = {}  # listening only
    run = run_case(
        definition,
        file=SMALL,
        answers=[
            send("cancelled", {"note": "first"}, "system:portal"),
            send("cancelled", {"note": "second"}, "system:portal"),
        ],
        people=PEOPLE,
    )
    assert [line.split(" from ")[0] for line in run.history if line.startswith("cancelled#")] == [
        "cancelled#1",
        "cancelled#2",
    ]
    assert run.state.values["cancelled.note"] == "second"


# --- Arrival is a fact; content is not (brief, D41) ---

SAYS_CANCEL = {"==": [{"var": "cancelled.note"}, "please cancel"]}


def test_untrusted_content_cant_decide() -> None:
    definition = cancellable()
    definition["rules"]["withdraw_on_cancel"]["when"] = SAYS_CANCEL
    run = run_case(
        definition,
        file=SMALL,
        answers=[send("cancelled", {"note": "please cancel"}, "system:portal")],
        people=PEOPLE,
    )
    assert run.history[-1] == (
        "withdraw_on_cancel#1 on event cancelled: stops nothing: its condition reads "
        "cancelled.note, from untrusted:customer, and untrusted data can't decide"
    )
    assert run.waiting_for == ["review by support"]  # the review stays open
    assert not any("please cancel" in line for line in run.history)  # the value is never quoted


def with_a_letter_started_on_cancel(when: dict[str, Any] | None) -> dict[str, Any]:
    """The cancellable refund, drafting a letter to the case's email when the customer cancels:
    started by a rule on the event, whose condition is `when`."""
    definition = cancellable()
    definition["fields"]["email"] = {"type": "string", "display": {"title": "Email"}}
    definition["steps"]["goodbye"] = {
        "kind": "activity",
        "display": {"title": "Draft a goodbye letter"},
        "activity": "letters.draft@2",
        "automatic": False,
        "inputs": {"to_customer": {"var": "email"}, "template": "goodbye"},
    }
    definition["rules"]["say_goodbye"] = {
        "display": {"title": "Say goodbye"},
        "on": {"event": "cancelled"},
        "then": {"start": ["goodbye"]},
    } | ({"when": when} if when is not None else {})
    return definition


def test_untrusted_content_cant_choose_what_is_sent() -> None:
    file = SMALL | {"email": "c@example.com"}
    sent = [send("cancelled", {"note": "please cancel"}, "system:portal")]
    # On the arrival alone, the letter is drafted: the arrival is a fact.
    drafted = run_case(with_a_letter_started_on_cancel(None), file, sent, people=PEOPLE)
    assert any(line.startswith("scheduled goodbye#1: letters.draft@2") for line in drafted.history)
    # On what the customer wrote, it isn't: the condition's untrusted source counts for the
    # input's policy (brief, D39).
    steered = run_case(with_a_letter_started_on_cancel(SAYS_CANCEL), file, sent, people=PEOPLE)
    assert steered.needs_attention == [
        (
            "goodbye#1: letters.draft@2 takes to_customer only from a system or a person, never "
            "from untrusted data, and say_goodbye#1's condition, which started goodbye, reads "
            "cancelled.note (untrusted:customer)"
        )
    ]


# --- Slice 3: a step that waits for an event ---

APPROVED = ("review", "approve", "ana", {"approved_amount": 40})
RECEIPT = send("receipt_sent", {"receipt": "doc-7"}, "system:portal")


def test_a_wait_is_never_answered() -> None:
    with pytest.raises(
        AnswerRefused,
        match="^wait_for_receipt#1 waits for receipt_sent: it is sent, never answered$",
    ):
        run_case(
            waiting_for_a_receipt(),
            file=SMALL,
            answers=[APPROVED, ("wait_for_receipt#1", "done", "ana")],
            people=PEOPLE,
        )


def test_a_wait_holds_the_case_until_its_event_arrives() -> None:
    waiting = run_case(waiting_for_a_receipt(), file=SMALL, answers=[APPROVED], people=PEOPLE)
    assert waiting.history[-1] == "started wait_for_receipt#1: waiting for receipt_sent from portal"
    assert waiting.waiting_for == ["receipt_sent from portal"]
    assert waiting.status == "open"  # pending work (brief, D10)
    paid = run_case(waiting_for_a_receipt(), file=SMALL, answers=[APPROVED, RECEIPT], people=PEOPLE)
    at = paid.history.index("receipt_sent#1 from portal, giving receipt from system:portal")
    assert paid.history[at + 1] == "wait_for_receipt#1 done: receipt_sent#1 arrived"
    assert paid.reached("wait_for_receipt") and paid.reached("pay")
    assert paid.closed


def test_only_an_arrival_after_a_wait_opens_ends_it() -> None:
    run = run_case(waiting_for_a_receipt(), file=SMALL, answers=[RECEIPT, APPROVED], people=PEOPLE)
    assert run.state.values["receipt_sent.receipt"] == "doc-7"  # in the case file already
    assert run.waiting_for == ["receipt_sent from portal"]  # and the wait waits for the next


def test_a_wait_sent_by_people_says_who_sends_it() -> None:
    definition = waiting_for_a_receipt()
    definition["events"]["receipt_sent"]["sent_by"] = {"roles": ["support", "fraud"]}
    run = run_case(definition, file=SMALL, answers=[APPROVED], people=PEOPLE)
    assert run.waiting_for == ["receipt_sent by support or fraud"]


def test_a_stop_or_a_close_cancels_a_wait() -> None:
    stopping = waiting_for_a_receipt()
    stopping["events"]["cancelled"] = copy.deepcopy(CANCELLED)
    stopping["rules"] = {
        "withdraw_on_cancel": copy.deepcopy(WITHDRAW) | {"then": {"stop": ["wait_for_receipt"]}}
    }
    cancelled = send("cancelled", {"note": "please cancel"}, "system:portal")
    stopped = run_case(stopping, file=SMALL, answers=[APPROVED, cancelled], people=PEOPLE)
    assert "cancelled wait_for_receipt#1: stopped by withdraw_on_cancel#1" in stopped.history
    assert stopped.closed  # nothing is left to do: pay requires a wait that ended without
    closing = waiting_for_a_receipt()
    closing["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    }
    closed = run_case(
        closing, file=SMALL, answers=[APPROVED, close("duplicate", "ana")], people=PEOPLE
    )
    assert "cancelled wait_for_receipt#1: closed as duplicate by ana" in closed.history
    assert closed.closed and closed.waiting_for == []


# --- Slice 4: events and the close ---

REJECTED = ("review", "reject", "ana")
CANCEL = send("cancelled", {"note": "please cancel"}, "system:portal")


def test_a_closed_case_refuses_an_event() -> None:
    with pytest.raises(EventRefused, match="^the case is closed: it takes no more events$"):
        run_case(cancellable(), file=SMALL, answers=[REJECTED, CANCEL], people=PEOPLE)


def test_a_closing_case_refuses_an_event_and_is_flagged() -> None:
    definition = cancellable()
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    }
    run = run_case(
        definition,
        file=SMALL,
        answers=[APPROVED, close("duplicate", "ana"), CANCEL, finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    assert appears_in_order(
        [
            "refused cancelled from portal: the case is closing, so it takes no more events",
            "flagged: cancelled from portal arrived while the case was closing, and was refused",
        ],
        run.history,
    )
    assert "cancelled from portal arrived while the case was closing, and was refused" in run.flags
    assert "cancelled.note" not in run.state.values  # nothing it carried landed
    assert not any(line.startswith("withdraw_on_cancel#") for line in run.history)
    assert run.closed


def appears_in_order(lines: list[str], history: list[str]) -> bool:
    """Whether `lines` appear in `history` one after the other."""
    return any(history[at : at + len(lines)] == lines for at in range(len(history)))


def unreachable_payment(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("provider unreachable")


def test_while_a_failed_run_holds_the_close_an_event_lands_and_no_rule_acts() -> None:
    definition = cancellable()
    definition["events"]["receipt_sent"] = copy.deepcopy(RECEIPT_SENT)
    definition["milestones"] = {"confirmed": {"display": {"title": "Confirmed"}}}
    definition["closes_when"] = ["confirmed"]
    definition["steps"]["confirm"] = {
        "kind": "task",
        "display": {"title": "Confirm the refund"},
        "roles": ["support"],
        "outcomes": {"confirmed": {"display": {"title": "Confirmed"}, "reaches": ["confirmed"]}},
    }
    definition["steps"]["wait_for_receipt"] = copy.deepcopy(WAIT_FOR_RECEIPT) | {"requires": []}
    run = run_case(
        definition,
        file=SMALL,
        answers=[APPROVED, ("confirm", "confirmed", "ana"), RECEIPT, CANCEL],
        people=PEOPLE,
        activities={"payments.refund@2": unreachable_payment},
    )
    assert run.needs_attention[0].startswith("pay#1: payments.refund@2 failed")  # holds the close
    assert "wait_for_receipt#1 done: receipt_sent#1 arrived" in run.history  # the wait it ends
    assert run.state.values["cancelled.note"] == "please cancel"  # what it carries lands
    assert run.history[-1] == (
        "withdraw_on_cancel#1 on event cancelled: not applied: confirmed is reached, so the case "
        "closes and nothing new is decided"
    )
    assert run.status == "open"


# --- Slice 5: time stays data ---


def with_a_goodbye_support_proposes() -> dict[str, Any]:
    """The cancellable refund with a goodbye letter, quoting the customer's note, that support
    proposes, needing the note at most an hour old."""
    definition = cancellable()
    definition["fields"]["email"] = {"type": "string", "display": {"title": "Email"}}
    definition["rules"] = {}
    definition["steps"]["goodbye"] = {
        "kind": "activity",
        "display": {"title": "Draft a goodbye letter"},
        "activity": "letters.draft@2",
        "automatic": False,
        "proposed_by": ["support"],
        "inputs": {"to_customer": {"var": "email"}, "template": {"var": "cancelled.note"}},
        "max_age": {"cancelled.note": "1h"},
    }
    return definition


def test_a_stale_value_an_event_carried_is_never_fetched_again() -> None:
    with pytest.raises(
        ProposalRefused,
        match="^cancelled.note was obtained 2 hours ago, and goodbye needs it at most 1 hour old: "
        "it came from the event cancelled#1, sent from outside, so it can't be fetched again$",
    ):
        run_case(
            with_a_goodbye_support_proposes(),
            file=SMALL | {"email": "c@example.com"},
            answers=[CANCEL, later("2h"), propose("goodbye", "ana")],
            people=PEOPLE,
        )


# --- Slice 6: validation stays a proof ---


def issues(definition: dict[str, Any]) -> list[Issue]:
    return validate_case(parse_case(definition), CATALOG)


def test_the_guides_events_get_no_issue() -> None:
    assert issues(cancellable()) == []
    assert issues(waiting_for_a_receipt()) == []


def test_a_rule_deciding_on_untrusted_content_is_refused() -> None:
    definition = cancellable()
    definition["rules"]["withdraw_on_cancel"]["when"] = SAYS_CANCEL
    assert issues(definition) == [
        Issue(
            "rules.withdraw_on_cancel.when",
            "UNTRUSTED_TRIGGER",
            "withdraw_on_cancel's condition reads cancelled.note, which comes from "
            "untrusted:customer whoever writes it, and untrusted data can't decide, so it never "
            "stops review: read a value a person or a trusted system gives, such as a task's "
            "answer",
        )
    ]
    # The runtime refuses the same, on nothing validation did (brief, D34): shown above, in
    # test_untrusted_content_cant_decide.


def correcting() -> dict[str, Any]:
    """The refund, where support sends the corrected amount, which is recorded in the ledger once
    it arrives: `ledger.record@1` takes an amount only the opener gave."""
    definition = copy.deepcopy(REFUND)
    definition["events"] = {
        "amount_corrected": {
            "display": {"title": "Support corrects the amount"},
            "sent_by": {"roles": ["support"]},
            "payload": {"amount": {"type": "number", "display": {"title": "Corrected amount"}}},
        }
    }
    definition["steps"]["wait_for_correction"] = {
        "kind": "wait",
        "display": {"title": "Wait for the corrected amount"},
        "event": "amount_corrected",
    }
    definition["steps"]["record"] = {
        "kind": "activity",
        "display": {"title": "Record the corrected amount"},
        "activity": "ledger.record@1",
        "requires": ["wait_for_correction"],
        "inputs": {"amount": {"var": "amount_corrected.amount"}},
    }
    return definition


def test_a_persons_payload_is_refused_where_only_a_system_may_give_it() -> None:
    [issue] = validate_case(parse_case(correcting()), with_ledger())
    assert (issue.path, issue.code, issue.severity) == (
        "steps.record.inputs.amount",
        "INPUT_POLICY",
        "error",
    )
    assert issue.message.startswith("ledger.record@1 takes amount only from opener")
    # The runtime refuses it on its own (brief, D34).
    run = run_case(
        correcting(),
        file=SMALL,
        answers=[send("amount_corrected", {"amount": 35}, "ana")],
        people=PEOPLE,
        catalog=with_ledger(),
        activities=LEDGER,
    )
    [failed] = run.needs_attention
    assert failed.startswith("record#1: ledger.record@1 takes amount only from opener")


def test_a_payload_read_where_nothing_waits_for_it_may_be_unset() -> None:
    definition = with_a_goodbye_support_proposes()
    del definition["steps"]["goodbye"]["max_age"]
    assert issues(definition) == [
        Issue(
            "steps.goodbye.inputs.template",
            "MAY_BE_UNSET",
            "goodbye reads cancelled.note, which only the event cancelled carries, and goodbye "
            "doesn't wait for it: if goodbye runs before it arrives, it fails and needs attention: "
            "require a wait for cancelled",
            "warning",
        )
    ]


def test_a_payload_is_surely_set_after_its_wait_and_in_a_rule_on_its_event() -> None:
    # After its wait: `correcting` reads the amount only once the wait is done.
    assert validate_case(parse_case(correcting()), with_ledger()) != []  # its policy issue only
    assert [i.code for i in validate_case(parse_case(correcting()), with_ledger())] == [
        "INPUT_POLICY"
    ]
    # In a rule on its event: the event has just arrived. A trusted note, so the rule may decide.
    definition = cancellable()
    del definition["events"]["cancelled"]["payload"]["note"]["source"]
    definition["rules"]["withdraw_on_cancel"]["when"] = SAYS_CANCEL
    assert issues(definition) == []


def test_a_payload_read_as_the_case_opens_is_never_set_after() -> None:
    # No step writes it, so nothing proves it fails every time: a warning, never SET_AFTER,
    # whose proof is a step that waits for its reader (brief, D37) (brief, D41).
    definition = cancellable()
    definition["rules"]["withdraw_on_cancel"] |= {
        "on": "opened",
        "when": {"!": [{"var": "cancelled.note"}]},
    }
    definition["events"]["cancelled"]["payload"]["note"] = {
        "type": "boolean",
        "display": {"title": "Cancelled by mistake"},
    }
    [issue] = issues(definition)
    assert (issue.path, issue.code, issue.severity) == (
        "rules.withdraw_on_cancel.when",
        "MAY_BE_UNSET",
        "warning",
    )


def test_a_max_age_on_a_payload_is_never_refreshed() -> None:
    found = issues(with_a_goodbye_support_proposes())
    assert [i.code for i in found] == ["MAY_BE_UNSET", "NEVER_REFRESHED"]
    assert found[1] == Issue(
        "steps.goodbye.max_age.cancelled.note",
        "NEVER_REFRESHED",
        "cancelled.note comes from the event cancelled, sent from outside, and can't be fetched "
        "again: whenever it is older than goodbye's max_age allows, a proposal of goodbye is "
        "refused: keep it only if a person should decide each time",
        "warning",
    )


def test_what_an_event_names_is_registered() -> None:
    definition = with_a_call()
    definition["events"]["cancelled"]["sent_by"] = {"system": "helpdesk"}
    definition["events"]["cancelled"]["payload"]["note"]["source"] = "untrusted:chat"
    definition["events"]["customer_called"]["sent_by"] = {"roles": ["suport"]}
    assert [(i.path, i.code) for i in issues(definition)] == [
        ("events.customer_called.sent_by.roles", "UNKNOWN_ROLE"),
        ("events.cancelled.payload.note.source", "UNKNOWN_SOURCE"),
        ("events.cancelled.sent_by.system", "UNKNOWN_SYSTEM"),
    ]


def test_a_case_naming_an_unregistered_sender_or_label_doesnt_open() -> None:
    # The runtime's own refusal, on nothing validation did (brief, D34).
    definition = cancellable()
    definition["events"]["cancelled"]["sent_by"] = {"system": "helpdesk"}
    definition["events"]["cancelled"]["payload"]["note"]["source"] = "untrusted:chat"
    with pytest.raises(
        CaseRefused,
        match="^cancelled is sent by helpdesk, a system nobody registered\n"
        "cancelled.note is declared untrusted:chat, a label nobody registered$",
    ):
        run_case(definition, file=SMALL, answers=[], people=PEOPLE)


def test_a_misspelt_payload_field_is_refused_and_fails_its_rule() -> None:
    definition = cancellable()
    definition["rules"]["withdraw_on_cancel"]["when"] = {
        "==": [{"var": "cancelled.notes"}, "please cancel"]
    }
    [issue] = issues(definition)
    assert (issue.path, issue.code) == ("rules.withdraw_on_cancel.when", "EXPRESSION_INVALID")
    run = run_case(definition, file=SMALL, answers=[CANCEL], people=PEOPLE)
    [failed] = run.needs_attention
    assert failed.startswith("withdraw_on_cancel#1: withdraw_on_cancel.when can't be read")


def test_a_wait_open_as_the_case_opens_keeps_it_from_closing_at_once() -> None:
    # Without its wait, the refund with no review would close as it opens: CLOSES_AT_OPENING.
    definition = waiting_for_a_receipt()
    definition["steps"] = {"wait_for_receipt": definition["steps"]["wait_for_receipt"]}
    definition["steps"]["wait_for_receipt"]["requires"] = []
    definition["sequence"] = []
    assert issues(definition) == []
    run = run_case(definition, file=SMALL, answers=[], people=PEOPLE)
    assert run.waiting_for == ["receipt_sent from portal"]


def test_a_loop_that_comes_round_through_an_event_is_not_claimed() -> None:
    # Whether an event comes again is its sender's, not the case's: nothing proves the loop goes
    # on, so neither NEVER_CLOSES nor LOOPS_UNTIL_CLOSED (brief, D39) (brief, D41).
    definition = with_a_call()
    definition["stays_open"] = True
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["suport"]}
    }
    definition["steps"]["review"] |= {"repeatable": True}
    definition["rules"] = {
        "review_again": {
            "display": {"title": "Review again after a call"},
            "on": {"event": "customer_called"},
            "then": {"start": ["review"]},
        }
    }
    codes = [issue.code for issue in issues(definition)]
    assert "LOOPS_UNTIL_CLOSED" not in codes
    assert codes == ["NEVER_CLOSES"]  # its close reason's role is misspelt: nothing else


def test_a_sender_is_a_role_the_case_names() -> None:
    # Anyone holding a role the case names sees its ordinary values (brief, D30): a sender too.
    definition = with_a_call()
    definition["events"]["customer_called"]["sent_by"] = {"roles": ["fraud"]}
    run = run_case(
        definition,
        file=SMALL,
        answers=[send("customer_called", {"wants_refund": True}, "fay")],
        people={**PEOPLE, "fay": ["fraud"]},
    )
    assert run.view(["fraud"]).values["customer_called.wants_refund"] is True


def test_what_a_rule_on_an_event_reaches_can_close_the_case() -> None:
    # A case that stays open, whose one close reason names no registered role, closed only by
    # what a rule on an event reaches: no NEVER_CLOSES, no CLOSE_UNREACHABLE, no NEVER_FIRES
    # (brief, D34) (brief, D41).
    definition = cancellable(stays_open=True, closes_when=["withdrawn"])
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["suport"]}
    }
    definition["milestones"] = {"withdrawn": {"display": {"title": "Withdrawn"}}}
    definition["rules"]["withdraw_on_cancel"]["then"] = {"stop": ["review"], "reach": ["withdrawn"]}
    assert [issue.code for issue in issues(definition)] == ["UNKNOWN_ROLE"]
    run = run_case(definition, file=SMALL, answers=[CANCEL], people=PEOPLE)
    assert run.closed
    assert run.history[-1] == "closed: withdrawn reached"


# --- Slice 8: the guide, as the engine does it ---

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "cases.md").read_text()
EVENTS_SECTION = GUIDE.split("## Events from outside\n")[1].split("\n## ")[0]


def guide_blocks(language: str) -> list[str]:
    """The section's code blocks in `language` (`""` for plain ones), in order."""
    found: list[str] = []
    opened: str | None = None
    body: list[str] = []
    for line in EVENTS_SECTION.splitlines():
        if not line.startswith("```"):
            body.append(line)
        elif opened is None:
            opened, body = line.removeprefix("```"), []
        else:
            if opened == language:
                found.append("\n".join(body))
            opened = None
    return found


def guide_json(index: int) -> dict[str, Any]:
    """The section's JSON block `index`, a fragment (`"name": {...}`) read as an object."""
    loaded: dict[str, Any] = json.loads("{" + guide_blocks("json")[index] + "}")
    return loaded


def shown(index: int) -> list[str]:
    """The section's plain block `index`, as history lines."""
    return guide_blocks("")[index].splitlines()


def test_the_guides_definitions_are_these_tests() -> None:
    assert guide_json(0) == {"events": {"cancelled": CANCELLED}}
    assert guide_json(1) == {"withdraw_on_cancel": WITHDRAW}
    assert guide_json(2) == {"wait_for_receipt": WAIT_FOR_RECEIPT}
    assert guide_json(3) == {"receipt_sent": RECEIPT_SENT}


def test_the_guides_histories_are_what_the_engine_records() -> None:
    cancelled = run_case(cancellable(), file=SMALL, answers=[CANCEL], people=PEOPLE)
    assert appears_in_order(shown(0), cancelled.history)
    untrusted = cancellable()
    untrusted["rules"]["withdraw_on_cancel"]["when"] = SAYS_CANCEL
    decided = run_case(untrusted, file=SMALL, answers=[CANCEL], people=PEOPLE)
    assert appears_in_order(shown(1), decided.history)
    waited = run_case(
        waiting_for_a_receipt(), file=SMALL, answers=[APPROVED, RECEIPT], people=PEOPLE
    )
    assert appears_in_order(shown(2), waited.history)
    closing = cancellable()
    closing["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    }
    held = run_case(
        closing,
        file=SMALL,
        answers=[APPROVED, close("duplicate", "ana"), CANCEL, finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    assert appears_in_order(shown(3), held.history)


def refusal(play: Any) -> str:
    """What the engine says when `play` runs into a refusal."""
    try:
        play()
    except (EventRefused, AnswerRefused) as refused:
        return str(refused)
    raise AssertionError("nothing was refused")


def sent(*events: Any, answers: tuple[Any, ...] = ()) -> Any:
    """A run of the refund taking a call too, playing `answers` then `events`."""
    return lambda: run_case(with_a_call(), file=SMALL, answers=[*answers, *events], people=PEOPLE)


GUIDE_REFUSALS: dict[str, Any] = {
    "the case declares no such event": lambda: run_case(
        cancellable(), file=SMALL, answers=[send("refunded", {}, "system:portal")], people=PEOPLE
    ),
    "another system sends it": sent(send("cancelled", {"note": "x"}, "system:crm")),
    "a person sends a system's event": sent(send("cancelled", {"note": "x"}, "ana")),
    "the person has none of its roles": sent(
        send("customer_called", {"wants_refund": True}, "eve")
    ),
    "a payload field is missing": sent(send("cancelled", {}, "system:portal")),
    "it carries a field it doesn't declare": sent(
        send("cancelled", {"note": "x", "tone": "angry"}, "system:portal")
    ),
    "a field is of another type": sent(send("cancelled", {"note": 3}, "system:portal")),
    "the case is closed": sent(CANCEL, answers=(REJECTED,)),
}


def guide_refusal_rows() -> list[tuple[str, str]]:
    """The rows of the section's table "An event is refused when | Example", code unquoted."""
    table = EVENTS_SECTION.split("| An event is refused when | Example |")[1].split("\n\n")[0]
    rows = [line.split("|") for line in table.splitlines()[2:] if line.startswith("| ")]
    return [(when.strip(), example.strip().strip("`")) for _, when, example, _ in rows]


@pytest.mark.parametrize(("when", "example"), guide_refusal_rows())
def test_the_guides_refusals_are_what_the_engine_says(when: str, example: str) -> None:
    assert when in GUIDE_REFUSALS, f"the guide's row {when!r} has no test"
    assert refusal(GUIDE_REFUSALS[when]) == example


def test_every_refusal_in_the_guide_is_tested() -> None:
    assert [when for when, _ in guide_refusal_rows()] == list(GUIDE_REFUSALS)


def test_the_guides_answer_to_a_wait_is_refused_as_it_says() -> None:
    said = refusal(
        lambda: run_case(
            waiting_for_a_receipt(),
            file=SMALL,
            answers=[APPROVED, ("wait_for_receipt#1", "done", "ana")],
            people=PEOPLE,
        )
    )
    assert f"`{said}`" in " ".join(EVENTS_SECTION.split())  # the guide wraps its lines


def test_no_event_line_or_issue_quotes_a_value() -> None:
    # What an event carries reaches the history and its refusals only by name and source: people
    # who may not see a value read them (brief, D30).
    secret = "SECRET-NOTE-42"
    runs = [
        run_case(
            cancellable(),
            file=SMALL,
            answers=[send("cancelled", {"note": secret}, "system:portal")],
            people=PEOPLE,
        ),
        run_case(
            cancellable() | {"rules": {"withdraw_on_cancel": WITHDRAW | {"when": SAYS_CANCEL}}},
            file=SMALL,
            answers=[send("cancelled", {"note": secret}, "system:portal")],
            people=PEOPLE,
        ),
    ]
    for run in runs:
        assert not any(secret in line for line in [*run.history, *run.flags, *run.needs_attention])
    with pytest.raises(EventRefused) as wrong_type:
        run_case(
            cancellable(),
            file=SMALL,
            answers=[send("cancelled", {"note": 42}, "system:portal")],
            people=PEOPLE,
        )
    assert "42" not in str(wrong_type.value)
    definition = cancellable()
    definition["rules"]["withdraw_on_cancel"]["when"] = {"==": [{"var": "cancelled.note"}, secret]}
    # A literal the author wrote may be quoted where it is the mistake (brief, D35); this one
    # isn't, so no issue quotes it.
    assert not any(secret in issue.message for issue in issues(definition))
