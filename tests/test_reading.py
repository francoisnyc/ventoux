"""Reading rules: each rule in plain words, worked out from the definition alone (layer 11g1).

Tests go through `parse_case` and `read_rules`, and, for each part a reading says, through
`run_case`, so a reading and the engine can't drift apart.
See docs/layers/11-rules.md (11g), the brief, D45, and docs/guides/cases.md, "Reading rules".
"""

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, cast, get_args, get_origin

import pytest

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_rules import (
    APPROVED_40,
    SAYS_SEND,
    SMALL_REVIEW,
    closing_on_paid,
    notes_say_send,
    only_a_rule_starts,
    stale_notify,
    unreadable,
    welcome_file,
    with_kyc_rule,
    with_rule,
    with_goodwill,
    with_welcome,
    withdrawable,
)
from test_set import FILE as OWED_FILE
from test_set import with_owed
from test_timers import APPROVED, CLOSABLE, NOTED, PEOPLE, SMALL, chased, down
from test_untrusted_moment import LETTER, cancelled, say_goodbye

from ventoux.case.definition import RuleMoment, Then, parse_case
from ventoux.case.reading import CLAUSES, EVERY_RULE, ReadingRefused, read_rules
from ventoux.testing import AnswerRefused, close, finish, later, run_case, send

# --- Slice 1: the moments ---


def test_a_shape_the_reader_doesnt_know_is_refused() -> None:
    # `parse_case` refuses an unknown moment first; this is a definition that didn't come through
    # it. Fail closed: never a sentence with its moment left out, nor read as another moment.
    case = parse_case(chased())
    object.__setattr__(case.rules["chase_review"], "on", {"every": "1d"})
    with pytest.raises(ReadingRefused) as refused:
        read_rules(case)
    assert str(refused.value) == (
        "can't read chase_review's moment {'every': '1d'}: it isn't a moment Ventoux knows"
    )


# Each moment a rule may name, by the tag the definition's type picks it with, and its reading.
# A rule on it starts `chase`; the timer's row is set on a review's start.
MOMENTS = {
    "opened moment": ("opened", "When the case opens: start chase."),
    "reached moment": (
        {"reached": "checked"},
        "When checked is reached (once: a milestone is never undone): start chase.",
    ),
    "started moment": ({"started": "review"}, "Each time a run of review starts: start chase."),
    "answered moment": (
        {"answered": "review"},
        "Each time review is answered, whatever the outcome: start chase.",
    ),
    "event moment": ({"event": "noted"}, "Each time noted arrives: start chase."),
    "timer moment": (
        {"after": "2d", "since": {"started": "review"}},
        "2d after each run of review starts: start chase.",
    ),
}

# What a timer waits after, for each moment it may be set on (brief, D44).
SINCE = {
    "opened moment": ("opened", "2d after the case opens: start chase."),
    "reached moment": (
        {"reached": "checked"},
        "2d after checked is reached (once: a milestone is never undone): start chase.",
    ),
    "started moment": ({"started": "review"}, "2d after each run of review starts: start chase."),
    "answered moment": (
        {"answered": "review"},
        "2d after each answer to review, whatever the outcome: start chase.",
    ),
    "event moment": ({"event": "noted"}, "2d after each arrival of noted: start chase."),
}


def tags(alias: object) -> set[str]:
    """The tags a discriminated union picks its shapes by, nested unions included: read from the
    definition's own type, so a moment added there shows up here."""
    found: set[str] = set()
    for arg in get_args(getattr(alias, "__value__", alias)):
        if get_origin(arg) is Annotated:
            shape, *marks = get_args(arg)
            found |= {mark.tag for mark in marks if hasattr(mark, "tag")}
            found |= {tag for tag in tags(shape) if tag != "moment"}
        else:
            found |= tags(arg)
    return found - {"moment"}


def on_moment(on: object) -> dict[str, Any]:
    """The refund with the guide's chase, its rule fired `on`, and what the moments name."""
    definition = chased(on)
    definition["milestones"] = {"checked": {"display": {"title": "Checked"}}}
    definition["events"] = {
        "noted": {"display": {"title": "A note"}, "sent_by": {"system": "portal"}, "payload": {}}
    }
    return definition


def test_every_moment_the_definition_takes_is_read() -> None:
    # The closed list is the definition's own (brief, D38) (brief, D44): a new moment fails here
    # until it has a reading.
    assert tags(RuleMoment) == set(MOMENTS)
    for on, sentence in MOMENTS.values():
        [reading] = read_rules(parse_case(on_moment(on)))
        assert reading.sentence == sentence
    for since, sentence in SINCE.values():
        [reading] = read_rules(parse_case(on_moment({"after": "2d", "since": since})))
        assert reading.sentence == sentence
    assert set(SINCE) == set(MOMENTS) - {"timer moment"}


# --- Slice 2: conditions and actions ---


class Closing(Then):
    """An action the engine doesn't have: a rule that closes the case."""

    close: tuple[str, ...] = ("done",)


def test_an_action_the_reader_doesnt_know_is_refused() -> None:
    case = parse_case(chased())
    rule = case.rules["chase_review"]
    object.__setattr__(rule, "then", Closing(start=("chase",)))
    with pytest.raises(ReadingRefused) as refused:
        read_rules(case)
    assert str(refused.value) == (
        "can't read chase_review's then.close: it isn't an action Ventoux knows"
    )


def test_an_expression_the_reader_doesnt_know_is_refused() -> None:
    # The expression renderer refuses it (layer 2); the reader says which rule.
    case = parse_case(chased())
    object.__setattr__(case.rules["chase_review"], "when", {"now": []})
    with pytest.raises(ReadingRefused) as refused:
        read_rules(case)
    assert str(refused.value) == (
        "can't read chase_review's condition: can't render {'now': []}: it isn't a parsed "
        "expression"
    )


def every_action() -> dict[str, Any]:
    """The refund with a rule doing all four actions, written in another order than the engine
    takes them."""
    definition = on_moment({"answered": "review"})
    definition["fields"]["owed"] = {"type": "number", "display": {"title": "What is owed"}}
    definition["milestones"]["owed_known"] = {"display": {"title": "What is owed is known"}}
    definition["steps"]["pay"]["automatic"] = False
    definition["steps"]["pay"]["proposed_by"] = ["support"]
    definition["rules"]["chase_review"] |= {
        "when": {"==": [{"var": "review.outcome"}, "approve"]},
        "then": {
            "start": ["chase", "pay"],
            "reach": ["owed_known"],
            "set": {"owed": {"-": [{"var": "approved_amount"}, 1]}},
            "stop": ["call_customer"],
        },
    }
    return definition


# Each action the definition takes, and how it reads.
ACTIONS = {
    "stop": "stop call_customer",
    "set": "set owed to approved_amount - 1",
    "reach": "reach owed_known",
    "start": "start chase and pay",
}


def test_every_action_the_definition_takes_is_read_in_the_engines_order() -> None:
    # The closed list is the definition's own (brief, D38, D39, D40, D42), and the order is the
    # engine's: stop, set, reach, start, whatever order the JSON is written in.
    assert set(Then.model_fields) == set(ACTIONS)
    [reading] = read_rules(parse_case(every_action()))
    assert reading.sentence == (
        'Each time review is answered, whatever the outcome, if review.outcome = "approve" (read '
        "when it fires): stop call_customer, then set owed to approved_amount - 1, then reach "
        "owed_known, then start chase and pay."
    )


def test_a_condition_reads_as_rendered_and_when_it_is_read() -> None:
    # A timer's condition is read when it fires, not when it is set (brief, D44).
    definition = chased()
    definition["rules"]["chase_review"]["when"] = {"!=": [{"var": "review.outcome"}, "approve"]}
    [reading] = read_rules(parse_case(definition))
    assert reading.sentence == (
        '2d after each run of review starts, if review.outcome != "approve" (read when the timer '
        "fires, not when it is set): start chase."
    )


# --- Slices 3 and 4: the fine print, each clause with its witness ---

# Each clause a reading may say, with the test that shows the engine doing what it says.
WITNESSED: set[str] = set()


def witness(clause: str) -> Callable[[Callable[[], None]], Callable[[], None]]:
    """Mark a test as `clause`'s witness: it reads a rule saying it, and runs a case where the
    engine does what it says (brief, D45)."""

    def marked(test: Callable[[], None]) -> Callable[[], None]:
        WITNESSED.add(clause)
        return test

    return marked


def reading_of(definition: dict[str, Any], rule: str = "chase_review") -> Any:
    """The reading of `rule` in `definition`."""
    return next(r for r in read_rules(parse_case(definition)) if r.name == rule)


ON_A_RUN = (
    "The timer is set as each run of review starts, and ends when that run does: done, rejected "
    "or cancelled, a stop included. A failed run keeps it: a retry is the same run."
)


@witness("timer on a run")
def test_a_timer_on_a_run_reads_as_ending_with_it() -> None:
    reading = reading_of(chased())
    assert "timer on a run" in reading.clauses
    assert ON_A_RUN in reading.fine_print
    # Done: the run's timer goes with it (brief, D44).
    done = run_case(chased(), file=SMALL, answers=[APPROVED, later("3d")], people=PEOPLE)
    assert "cancelled chase_review, 2d after started review#1: review#1 is done" in done.history
    # Stopped: cancelled, and its timer with it (brief, D40).
    definition = chased(events=NOTED)
    definition["rules"]["withdraw"] = {
        "display": {"title": "Withdraw"},
        "on": {"event": "noted"},
        "then": {"stop": ["review"]},
    }
    stopped = run_case(
        definition, file=SMALL, answers=[send("noted", {}, "system:portal")], people=PEOPLE
    )
    assert (
        "cancelled chase_review, 2d after started review#1: review#1 is cancelled"
    ) in stopped.history
    # Failed: kept, and the rule acts (brief, D40, as amended by D44).
    failing = chased({"after": "1h", "since": {"started": "look_up"}})
    failing["steps"]["look_up"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    failed = run_case(
        failing,
        file=SMALL,
        answers=[later("2h")],
        people=PEOPLE,
        activities={"orders.lookup@1": down},
    )
    assert failed.needs_attention[0].startswith("look_up#1: orders.lookup@1 failed")
    assert "chase_review#1 on 1h after started look_up#1: starting chase" in failed.history


def after_the_answer() -> dict[str, Any]:
    """The guide's chase, set 30 days after the review is answered: on an instant."""
    return chased({"after": "30d", "since": {"answered": "review"}}, close_reasons=CLOSABLE)


@witness("timer on an instant")
def test_a_timer_on_an_instant_reads_as_living_until_it_fires() -> None:
    reading = reading_of(after_the_answer())
    assert "timer on an instant" in reading.clauses
    assert "The timer is set at each answer to review, and lives until it fires." in (
        reading.fine_print
    )
    # The review is done and the refund paid: the timer lives on, and fires on day 30.
    run = run_case(after_the_answer(), file=SMALL, answers=[APPROVED, later("30d")], people=PEOPLE)
    assert "review#1 done" in run.history and run.reached("pay")
    assert "chase_review#1 on 30d after answered review#1: starting chase" in run.history


@witness("timer holds the case")
def test_a_set_timer_reads_as_keeping_the_case_open() -> None:
    reading = reading_of(after_the_answer())
    assert "timer holds the case" in reading.clauses
    assert "While it is set, the timer keeps the case open; a close cancels it." in (
        reading.fine_print
    )
    # Nothing waits on anyone, and the case is open: the timer holds it (brief, D10).
    paid = run_case(after_the_answer(), file=SMALL, answers=[APPROVED], people=PEOPLE)
    assert paid.waiting_for == [] and not paid.closed
    assert paid.timers == ["chase_review: 30d after answered review#1, due 2026-01-31T00:00:00Z"]
    closed = run_case(
        after_the_answer(),
        file=SMALL,
        answers=[APPROVED, close("duplicate", "ana")],
        people=PEOPLE,
    )
    assert (
        "cancelled chase_review, 30d after answered review#1: closed as duplicate by ana"
    ) in closed.history
    assert closed.closed


@witness("listening")
def test_a_rule_on_an_event_reads_as_listening() -> None:
    definition = chased({"event": "noted"}, events=NOTED)
    reading = reading_of(definition)
    assert "listening" in reading.clauses
    assert "Listening for noted doesn't keep the case open." in reading.fine_print
    # The refund is paid, and the rule still listens: the case closes (brief, D41).
    run = run_case(definition, file=SMALL, answers=[APPROVED], people=PEOPLE)
    assert run.closed


UNTRUSTED = "it acts on nothing, and says why: untrusted data can't decide."


@witness("untrusted data decides nothing")
def test_untrusted_data_reads_as_deciding_nothing() -> None:
    # Its condition reads the model's notes: the rule reaches nothing (brief, D38).
    definition = with_kyc_rule({"!=": [{"var": "kyc.analyst_notes"}, ""]})
    reading = reading_of(definition, "flag_high_risk")
    assert "untrusted data decides nothing" in reading.clauses
    assert f"If its condition reads untrusted data, {UNTRUSTED}" in reading.fine_print
    run = run_case(definition, file={**SMALL, "customer_id": "c-1"}, answers=[], people=PEOPLE)
    assert (
        "flag_high_risk#1 on reached checked: reaches nothing: its condition reads "
        "kyc.analyst_notes, from untrusted:llm, and untrusted data can't decide"
    ) in run.history
    # It reads nothing, and is set on a start the customer's note steered (brief, D43).
    steered = say_goodbye()
    reading = reading_of(steered, "close_it")
    assert f"If untrusted data steered the run of goodbye, {UNTRUSTED}" in reading.fine_print
    run = run_case(steered, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert (
        "close_it#1 on started goodbye: reaches nothing: its moment comes from untrusted data: "
        "say_goodbye#1's condition, which started goodbye, reads cancelled.note "
        "(untrusted:customer), and untrusted data can't decide"
    ) in run.history


@witness("set value carries what it read")
def test_a_set_value_reads_as_carrying_what_it_read() -> None:
    reading = reading_of(with_owed(), "work_out_owed")
    assert "set value carries what it read" in reading.clauses
    assert "The values it sets carry the sources of everything it read." in reading.fine_print
    run = run_case(with_owed(), file=OWED_FILE, answers=[APPROVED], people=PEOPLE)
    assert (
        "work_out_owed#1 on answered review: setting owed, from person:ana, system:opener"
    ) in run.history
    # On a steered start, it carries what steered it too (brief, D43).
    steered = say_goodbye({"set": {"leaving": {">": [{"var": "amount"}, 0]}}})
    steered["fields"]["leaving"] = {"type": "boolean", "display": {"title": "Leaving"}}
    assert (
        "The values it sets carry the sources of everything it read, and what steered the run "
        "of goodbye."
    ) in reading_of(steered, "close_it").fine_print
    run = run_case(steered, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert run.state.sources["leaving"] == {"system:opener", "untrusted:customer"}


@witness("start checked against inputs")
def test_a_start_reads_as_checked_against_inputs() -> None:
    definition = with_welcome(SAYS_SEND)
    del definition["steps"]["welcome"]["when"]
    definition["steps"]["welcome"]["automatic"] = False
    definition["rules"]["send_welcome"] = {
        "display": {"title": "Send a welcome letter"},
        "on": {"reached": "checked"},
        "when": SAYS_SEND,
        "then": {"start": ["welcome"]},
    }
    reading = reading_of(definition, "send_welcome")
    assert "start checked against inputs" in reading.clauses
    assert (
        "What its condition reads counts for the inputs of welcome: an input whose policy "
        "refuses an untrusted source is refused, and its run fails."
    ) in reading.fine_print
    run = run_case(
        definition,
        file=welcome_file(),
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
    )
    assert run.needs_attention == [
        (
            "welcome#1: letters.draft@2 takes to_customer only from a system or a person, never "
            "from untrusted data, and send_welcome#1's condition, which started welcome, reads "
            "kyc.analyst_notes (untrusted:llm)"
        )
    ]
    # Set on a steered start, the start carries what steered it (brief, D43).
    steered = say_goodbye({"start": ["letter"]}, steps={"letter": LETTER})
    assert (
        "What steered the run of goodbye counts for the inputs of letter: an input whose policy "
        "refuses an untrusted source is refused, and its run fails."
    ) in reading_of(steered, "close_it").fine_print
    run = run_case(steered, file=SMALL, answers=[cancelled()], people=PEOPLE)
    assert run.needs_attention[0].startswith("letter#1: letters.draft@2 takes to_customer only")


def test_a_start_of_a_step_without_inputs_says_nothing_of_them() -> None:
    # The fine print says only what applies: the chase is a task, and takes no inputs.
    assert not any("inputs" in line for line in reading_of(chased()).fine_print)


@witness("only while the case decides")
def test_a_rule_reads_as_acting_only_while_the_case_decides() -> None:
    definition = closing_on_paid(on={"reached": "paid"}, when=None)
    reading = reading_of(definition, "flag_large")
    assert "only while the case decides" in reading.clauses
    assert (
        "Only while the case decides: not once paid is reached, nor once the case is closing."
    ) in reading.fine_print
    run = run_case(definition, file=SMALL, answers=[APPROVED], people=PEOPLE)
    assert (
        "flag_large#1 on reached paid: not applied: paid is reached, so the case closes and "
        "nothing new is decided"
    ) in run.history
    # Without closes_when: a person's close. The payment runs on, and reaches paid while the
    # case is closing (brief, D10).
    closing = chased({"reached": "paid"}, close_reasons=CLOSABLE)
    closing["milestones"] = {"paid": {"display": {"title": "Paid"}}}
    closing["steps"]["pay"]["reaches"] = ["paid"]
    decides = "Only while the case decides: not once the case is closing."
    assert decides in reading_of(closing).fine_print
    answers = [APPROVED, close("duplicate", "ana"), finish("pay#1")]
    run = run_case(closing, file=SMALL, answers=answers, people=PEOPLE, held=["pay"])
    assert (
        "chase_review#1 on reached paid: not applied: the case is closing, so nothing new is "
        "decided"
    ) in run.history


@witness("condition read when it fires")
def test_a_condition_reads_as_read_when_it_fires() -> None:
    # Read on the case file as the answer left it: the amount this very answer gives.
    definition = chased({"answered": "review"})
    definition["rules"]["chase_review"]["when"] = {">": [{"var": "approved_amount"}, 100]}
    reading = reading_of(definition)
    assert "condition read when it fires" in reading.clauses
    assert "if approved_amount > 100 (read when it fires)" in reading.sentence
    big = ("review", "approve", "ana", {"approved_amount": 250})
    run = run_case(definition, file=SMALL, answers=[big], people=PEOPLE)
    assert "chase_review#1 on answered review: starting chase" in run.history


@witness("timer's condition read when it fires")
def test_a_timers_condition_reads_as_read_when_the_timer_fires() -> None:
    # Set at the opening, when nothing is approved; read two days later, on the case file then.
    definition = chased({"after": "2d", "since": "opened"})
    definition["rules"]["chase_review"]["when"] = {">": [{"var": "approved_amount"}, 100]}
    reading = reading_of(definition)
    assert "timer's condition read when it fires" in reading.clauses
    assert "(read when the timer fires, not when it is set)" in reading.sentence
    big = ("review", "approve", "ana", {"approved_amount": 250})
    run = run_case(definition, file=SMALL, answers=[later("1d"), big, later("1d")], people=PEOPLE)
    assert "chase_review#1 on 2d after opened: starting chase" in run.history


@witness("actions in the engine's order")
def test_actions_read_in_the_order_the_engine_takes_them() -> None:
    reading = reading_of(every_action())
    assert "actions in the engine's order" in reading.clauses
    run = run_case(every_action(), file=SMALL, answers=[APPROVED], people=PEOPLE)
    said = [line for line in run.history if line.startswith("chase_review#1 on answered review")]
    assert [line.split(": ")[1].split(" ")[0] for line in said] == [
        "stopping",
        "call_customer",  # `call_customer not stopped`: nothing of it was running
        "setting",
        "reaching",
        "starting",
        "starting",
    ]


@witness("every rule")
def test_what_every_rule_does_is_said_once() -> None:
    assert EVERY_RULE == (
        "A rule remembers nothing: its condition is read once, when it fires. A rule whose "
        "condition or value can't be read acts on nothing, and needs attention."
    )
    # Never read as false: the rule fails, and waits for a person (brief, D17) (brief, D38).
    run = run_case(
        unreadable(),
        file={"order_id": "ord-1", "amount": 250},
        answers=[("review", "reject", "ana")],
        people=PEOPLE,
    )
    assert run.needs_attention[0].startswith("flag_large#1: flag_large's condition")
    assert "reached large" not in run.history and not run.closed


# --- From the tutor review: what a stop, a start and a close really do ---


def halting() -> dict[str, Any]:
    """The refund the portal can cancel: on `cancelled`, a rule stops the review and the payment."""
    definition = with_rule(on={"event": "cancelled"}, when=None, then={"stop": ["review", "pay"]})
    definition["rules"]["flag_large"]["display"] = {"title": "Stop paying on a cancel"}
    definition["events"] = {
        "cancelled": {
            "display": {"title": "Cancelled"},
            "sent_by": {"system": "portal"},
            "payload": {},
        }
    }
    return definition


PORTAL_CANCELS = send("cancelled", {}, "system:portal")


@witness("what a stop does")
def test_a_stop_reads_as_what_the_engine_does_to_each_kind() -> None:
    # A stop is what a close does, to one step (brief, D10, D40). "stop pay" alone read as if the
    # payment stops, and the refund went through.
    reading = reading_of(halting(), "flag_large")
    assert "what a stop does" in reading.clauses
    assert "Stopping review cancels its open task at once." in reading.fine_print
    assert (
        "Stopping pay cancels a run waiting for its approval, or to start, at once; a running "
        "call is only asked to stop, may still finish, and is flagged if it does; a failed run "
        "isn't stopped."
    ) in reading.fine_print
    # The payment is running when the portal cancels: the refund completes, flagged.
    paying = run_case(
        halting(),
        file=SMALL,
        answers=[SMALL_REVIEW, PORTAL_CANCELS, finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    stopped = paying.history.index("pay#1: stop requested by flag_large#1")
    assert paying.history[stopped : stopped + 3] == [
        "pay#1: stop requested by flag_large#1",
        "pay#1 done, giving refund_id from untrusted:undeclared",
        "flagged: pay#1 completed after its stop was requested by flag_large#1",
    ]
    assert paying.flags == ["pay#1 completed after its stop was requested by flag_large#1"]
    # The open review, and an approval asked: cancelled at once.
    open_task = run_case(halting(), file=SMALL, answers=[PORTAL_CANCELS], people=PEOPLE)
    assert "cancelled review#1: stopped by flag_large#1" in open_task.history
    big = ("review", "approve", "ana", {"approved_amount": 250})
    asked = run_case(halting(), file=SMALL, answers=[big, PORTAL_CANCELS], people=PEOPLE)
    assert "cancelled pay.approval#1: stopped by flag_large#1" in asked.history


def test_a_stopped_step_of_a_kind_the_reader_doesnt_know_is_refused() -> None:
    # `parse_case` refuses an unknown kind first; this is a definition that didn't come through it.
    case = parse_case(withdrawable())
    case.steps["review"] = cast(Any, "a meeting")
    with pytest.raises(ReadingRefused) as refused:
        read_rules(case)
    assert str(refused.value) == (
        "can't read what stopping review does: 'a meeting' is no kind of step"
    )


def pay_on_approval() -> dict[str, Any]:
    """The refund whose payment a rule starts once the review is approved; over 100, a team lead
    approves it first."""
    definition = with_rule(
        on={"answered": "review"},
        when={"==": [{"var": "review.outcome"}, "approve"]},
        then={"start": ["pay"]},
    )
    definition["steps"]["pay"] |= {"automatic": False}
    del definition["sequence"]
    return definition


@witness("a start is a proposal")
def test_a_start_reads_as_a_proposal_admission_decides() -> None:
    # The engine proposes, and admission decides at once, as for a person's proposal: "start pay"
    # alone read as if pay starts (brief, D39).
    reading = reading_of(pay_on_approval(), "flag_large")
    assert "a start is a proposal" in reading.clauses
    assert (
        "Starting pay is a proposal, decided at once as a person's is: nothing starts, and the "
        "history says why, if its condition is false, it is already running or waiting for its "
        "approval, it has run and isn't repeatable, or its latest run needs attention. It waits "
        "for its approval when one is needed."
    ) in reading.fine_print
    # Over 100: the approval is asked first, and pay waits for it.
    big = ("review", "approve", "ana", {"approved_amount": 250})
    run = run_case(pay_on_approval(), file=SMALL, answers=[big], people=PEOPLE)
    assert "flag_large#1 on answered review: starting pay" in run.history
    assert "asked pay.approval#1: approval of pay by support-lead" in run.history
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert not any(line.startswith("scheduled pay") for line in run.history)
    # Its requirements not met: nothing starts, and the history says why; never later.
    requiring = only_a_rule_starts(requires=["pay"])
    assert (
        "Starting lead_check is a proposal, decided at once as a person's is: nothing starts, and "
        "the history says why, if its requirements aren't met, it is already running, or it has "
        "run and isn't repeatable."
    ) in reading_of(requiring, "flag_large").fine_print
    run = run_case(requiring, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert (
        "flag_large#1 on answered review: lead_check not started: lead_check requires pay, which "
        "hasn't completed"
    ) in run.history
    # A stale fact: the run fails, and needs attention; the start doesn't wait for a refresh.
    stale = stale_notify()
    assert (
        "Starting notify is a proposal, decided at once as a person's is: nothing starts, and the "
        "history says why, if its requirements aren't met, its condition is false, it is already "
        "running, it has run and isn't repeatable, or its latest run needs attention. If a fact "
        "it needs fresh is stale, its run fails and needs attention: a rule's start doesn't wait "
        "for it to be fetched again."
    ) in reading_of(stale, "flag_large").fine_print
    looked_up = {"orders.lookup@2": lambda inputs: {"status": "delivered"}}
    run = run_case(
        stale, file=SMALL, answers=[later("3d"), APPROVED_40], people=PEOPLE, activities=looked_up
    )
    assert run.needs_attention == [
        (
            "notify#1: check_order.status was obtained 3 days ago, and notify needs it at most 1 "
            "day old: a rule's start doesn't wait for it to be fetched again; retry it to fetch it"
        )
    ]


def closing_on_a_note() -> dict[str, Any]:
    """The refund closing once `large` is reached, which a rule reaches when a note is answered;
    a timer is set at the opening."""
    definition = with_rule(on={"answered": "note"}, when=None)
    definition["closes_when"] = ["large"]
    definition["steps"]["note"] = {
        "kind": "task",
        "display": {"title": "Note the refund"},
        "roles": ["support"],
        "outcomes": {"noted": {"display": {"title": "Noted"}}},
    }
    definition["rules"]["remind"] = {
        "display": {"title": "Remind"},
        "on": {"after": "2d", "since": "opened"},
        "then": {"start": ["note"]},
    }
    return definition


@witness("reaching closes the case")
def test_reaching_closes_when_reads_as_closing_the_case() -> None:
    # "reach large" alone doesn't say the case closes, cancelling what is open (brief, D10).
    reading = reading_of(closing_on_a_note(), "flag_large")
    assert "reaching closes the case" in reading.clauses
    assert (
        "Reaching large closes the case, unless a failed run holds the close: open tasks, "
        "approvals and timers are cancelled, and running calls finish."
    ) in reading.fine_print
    run = run_case(
        closing_on_a_note(), file=SMALL, answers=[("note", "noted", "ana")], people=PEOPLE
    )
    assert run.history[-4:] == [
        "reached large",
        "cancelled review#1: the case closes when large is reached",
        "cancelled remind, 2d after opened: the case closes when large is reached",
        "closed: large reached",
    ]
    # With two closes_when milestones, it says which other must be reached too.
    both = closing_on_a_note()
    both["milestones"]["paid"] = {"display": {"title": "Paid"}}
    both["closes_when"] = ["large", "paid"]
    assert (
        "Reaching large closes the case once paid is reached too, unless a failed run holds the "
        "close: open tasks, approvals and timers are cancelled, and running calls finish."
    ) in reading_of(both, "flag_large").fine_print


def test_a_set_value_on_a_rule_that_reaches_still_reads_as_carrying_what_it_read() -> None:
    # Untrusted data stops the whole rule, but a trusted value still carries a person's answer:
    # Sam's answer is in what is owed, so Sam can't approve paying it (brief, D11, D42).
    definition = with_owed()
    definition["milestones"] = {"owed_known": {"display": {"title": "What is owed is known"}}}
    definition["rules"]["work_out_owed"]["then"]["reach"] = ["owed_known"]
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    reading = reading_of(definition, "work_out_owed")
    assert "set value carries what it read" in reading.clauses
    assert "The values it sets carry the sources of everything it read." in reading.fine_print
    big = ("review", "approve", "sam", {"approved_amount": 500})
    with pytest.raises(
        AnswerRefused,
        match="^sam's answer is in owed, which a rule computes and pay uses, so cannot approve it$",
    ):
        run_case(
            definition, file=OWED_FILE, answers=[big, ("pay", "approve", "sam")], people=PEOPLE
        )


def test_every_clause_has_a_witness() -> None:
    # A clause can't be added without a run showing the engine does what it says (brief, D45).
    assert WITNESSED == set(CLAUSES)


# --- Slice 5: the guide, and what a reading is given ---


def test_a_reading_needs_only_the_definition() -> None:
    # It is given no case file, so it can't quote a value from one; the constants it shows are
    # the rule's own (brief, D45).
    assert list(inspect.signature(read_rules).parameters) == ["case"]
    definition = with_kyc_rule({">": [{"var": "kyc.risk_score"}, 70]})
    [reading] = read_rules(parse_case(definition))
    assert "kyc.risk_score > 70" in reading.sentence


GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "cases.md").read_text()
READING_SECTION = GUIDE.split("## Reading rules\n")[1].split("\n## ")[0]


def plain_blocks() -> list[str]:
    """The section's plain code blocks, in order."""
    return [
        block.split("\n", 1)[1]
        for block in READING_SECTION.split("```")[1::2]
        if block.startswith("\n")
    ]


def test_the_guides_readings_are_the_renderers() -> None:
    timer, flag, every = plain_blocks()
    [chase] = read_rules(parse_case(chased()))
    assert timer == f"{chase}\n"
    risky = with_kyc_rule({">": [{"var": "kyc.risk_score"}, 70]})
    [flagged] = read_rules(parse_case(risky))
    assert flag == f"{flagged}\n"
    assert every == f"{EVERY_RULE}\n"


def test_a_reading_says_how_many_approve() -> None:
    # Where a reading mentions a step's approval, it says how many people give it; with one, as
    # before (brief, D45, D47).
    four_eyes = halting()
    four_eyes["steps"]["pay"]["approval"]["count"] = 2
    stop = reading_of(four_eyes, "flag_large")
    assert (
        "Stopping pay cancels a run waiting for its approval by 2 people, or to start, at once; a "
        "running call is only asked to stop, may still finish, and is flagged if it does; a "
        "failed run isn't stopped."
    ) in stop.fine_print
    goodwill = with_goodwill()
    goodwill["steps"]["goodwill"]["approval"]["count"] = 2
    start = reading_of(goodwill, "start_goodwill")
    [said] = [text for text in start.fine_print if text.startswith("Starting goodwill")]
    assert "it is already running or waiting for its approval by 2 people" in said
    assert said.endswith(" It waits for its approval by 2 people when one is needed.")
    one = reading_of(with_goodwill(), "start_goodwill")
    [said] = [text for text in one.fine_print if text.startswith("Starting goodwill")]
    assert "by 2 people" not in said
    assert said.endswith(" It waits for its approval when one is needed.")
    # The run: Sam's approval of two is cancelled with the entry.
    big = ("review", "approve", "ana", {"approved_amount": 250})
    leads = {**PEOPLE, "lee": ["support-lead"]}
    asked = run_case(
        four_eyes,
        file=SMALL,
        answers=[big, ("pay", "approve", "sam"), PORTAL_CANCELS],
        people=leads,
    )
    assert "cancelled pay.approval#1: stopped by flag_large#1, with 1 of 2 approvals given" in (
        asked.history
    )
