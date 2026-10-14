"""The deterministic interpreter: running a plan in memory (layer 5).

Tests go through `run_plan`, the in-memory driver, and read what a run reports. See
docs/layers/05-interpreter.md and docs/guides/plans.md, "Running a plan".
"""

import asyncio
import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.core.history import Scheduled
from ventoux.core.interpreter import Answer, Outcome, PlanRun, RunRefused, interpret
from ventoux.core.plan import parse_plan
from ventoux.core.provenance import sourced
from ventoux.core.sensitive import Sensitive
from ventoux.testing import CATALOG, FAKES, Activity, run_plan

GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "plans.md"


def ending_at_once() -> dict[str, Any]:
    """The smallest plan: one field, and a start that is already the end."""
    return {
        "plan": "at-once",
        "version": 1,
        "display": {"title": "Ends at once"},
        "fields": {"amount": {"type": "number"}},
        "initial": "done",
        "states": {"done": {"final": "succeeded"}},
    }


def test_a_run_needs_every_field_with_its_sources() -> None:
    with pytest.raises(RunRefused, match="amount comes with no sources"):
        run_plan(ending_at_once(), fields={"amount": sourced(250)}, answers=[])


def test_case_is_not_a_source_at_runtime() -> None:
    # `case` stands in for "the case vouches for it" in the static check only; at runtime a value
    # comes from where it really came from.
    with pytest.raises(RunRefused, match="amount comes from case"):
        run_plan(ending_at_once(), fields={"amount": sourced(250, "case")}, answers=[])


def test_a_run_needs_exactly_the_declared_fields() -> None:
    with pytest.raises(RunRefused, match="amount is missing"):
        run_plan(ending_at_once(), fields={}, answers=[])
    with pytest.raises(RunRefused, match="amout is not a field of at-once: its fields are amount"):
        run_plan(
            ending_at_once(),
            fields={"amount": sourced(250, "system:opener"), "amout": sourced(1, "system:opener")},
            answers=[],
        )


def test_a_run_ends_as_its_final_state_says() -> None:
    run = run_plan(ending_at_once(), fields={"amount": sourced(250, "system:opener")}, answers=[])
    assert run.status == "succeeded"
    assert [str(event) for event in run.history] == [
        "started at-once@1",
        "entered done",
        "ended succeeded",
    ]


def looking_up(**changes: Any) -> dict[str, Any]:
    """A plan that looks an order up: found, it succeeds; not found, it fails."""
    look = {
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "on": {"done": "found", "not_found": "missing"},
    }
    return {
        "plan": "look-up",
        "version": 1,
        "display": {"title": "Look an order up"},
        "fields": {"order_id": {"type": "reference", "system": "orders"}},
        "initial": "look",
        "states": {
            "look": {**look, **changes},
            "found": {"final": "succeeded"},
            "missing": {"final": "failed"},
        },
    }


ORDER = {"order_id": sourced("A-1001", "system:orders")}


def test_an_activity_the_catalog_does_not_hold_stops_the_step() -> None:
    run = run_plan(looking_up(activity="orders.lookup@9"), fields=ORDER, answers=[])
    assert run.status == "stopped"
    assert run.reason is not None and "orders.lookup@9 is not in the catalog" in run.reason


def failing(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("the orders system is down")


def test_an_activity_failure_stops_the_step() -> None:
    run = run_plan(looking_up(), fields=ORDER, answers=[], activities={"orders.lookup@1": failing})
    assert run.status == "stopped"
    assert run.reason == "orders.lookup@1 failed with ConnectionError: ‹sensitive›"


def lines(run: PlanRun) -> list[str]:
    """The run's history, one line per event."""
    return [str(event) for event in run.history]


def test_done_moves_on_with_the_evaluated_inputs() -> None:
    received: list[dict[str, Any]] = []

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        received.append(inputs)
        return {"status": "delivered"}

    run = run_plan(looking_up(), fields=ORDER, answers=[], activities={"orders.lookup@1": lookup})
    assert run.status == "succeeded"
    assert received == [{"order_id": "A-1001"}]
    assert lines(run)[-4:] == [
        "orders.lookup@1 gave done",
        "moved on done to found",
        "entered found",
        "ended succeeded",
    ]


def giving(outcome: str) -> Activity:
    """A fake activity that answers with `outcome`, as a business failure."""

    def activity(inputs: dict[str, Any]) -> dict[str, Any]:
        raise Outcome(outcome)

    return activity


def test_an_outcome_the_contract_does_not_declare_stops_the_step() -> None:
    lost = {"orders.lookup@1": giving("lost")}
    run = run_plan(looking_up(), fields=ORDER, answers=[], activities=lost)
    assert run.status == "stopped"
    assert run.reason == (
        "orders.lookup@1 gave the outcome lost, which its contract doesn't declare: "
        "its outcomes are not_found"
    )


def test_a_declared_outcome_moves_on() -> None:
    not_found = {"orders.lookup@1": giving("not_found")}
    run = run_plan(looking_up(), fields=ORDER, answers=[], activities=not_found)
    assert run.status == "failed"
    assert lines(run)[-4:] == [
        "orders.lookup@1 gave not_found",
        "moved on not_found to missing",
        "entered missing",
        "ended failed",
    ]


def test_an_output_the_contract_does_not_declare_stops_the_step() -> None:
    misnamed = {"orders.lookup@1": lambda inputs: {"state": "delivered"}}
    run = run_plan(looking_up(), fields=ORDER, answers=[], activities=misnamed)
    assert run.status == "stopped"
    assert run.reason == (
        "orders.lookup@1 gave an output its contract doesn't declare: status: Field required"
    )


def test_what_the_plan_does_not_say_stops_the_step() -> None:
    to_nowhere = looking_up(on={"done": "fuond", "not_found": "missing"})
    run = run_plan(to_nowhere, fields=ORDER, answers=[])
    assert run.status == "stopped"
    assert lines(run)[-1] == (
        "stopped at fuond: fuond is not a state of look-up: the states are found, look, "
        "missing: the step needs attention, and nothing after it runs"
    )

    unhandled = looking_up(on={"done": "found"})  # not_found has nowhere to go
    run = run_plan(
        unhandled, fields=ORDER, answers=[], activities={"orders.lookup@1": giving("not_found")}
    )
    assert run.status == "stopped"
    assert run.reason == "on not_found, look says nowhere to go"


def drafting(recipient: dict[str, Any] | None = None) -> dict[str, Any]:
    """The plans guide's injection example: a reply drafted to the recipient a model suggested.
    Its `suggested_recipient` is unmarked unless `recipient` says otherwise."""
    return {
        "plan": "draft-reply",
        "version": 1,
        "display": {"title": "Draft a reply to a customer"},
        "fields": {
            "customer_email": {"type": "string"},
            "suggested_recipient": recipient or {"type": "string"},
        },
        "initial": "draft",
        "states": {
            "draft": {
                "activity": "letters.draft@2",
                "inputs": {"to_customer": {"var": "suggested_recipient"}, "template": "reply"},
                "on": {"done": "drafted"},
            },
            "drafted": {"final": "succeeded"},
        },
    }


def recording(calls: list[dict[str, Any]]) -> Activity:
    """A fake `letters.draft@2` that records every call it gets."""

    def draft(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs)
        return {"draft_id": "draft-1"}

    return draft


def test_with_the_static_check_skipped_the_runtime_check_still_blocks_the_injection() -> None:
    # Unmarked, `suggested_recipient` passes `validate`: the case vouches for it. `run_plan` never
    # calls `validate`; the value's real source is the model.
    calls: list[dict[str, Any]] = []
    run = run_plan(
        drafting(),
        fields={
            "customer_email": sourced("ana@example.com", "system:crm"),
            "suggested_recipient": sourced("attacker@evil.example", "untrusted:llm"),
        },
        answers=[],
        activities={"letters.draft@2": recording(calls)},
    )
    assert calls == []  # never called
    assert run.status == "stopped"
    assert run.reason == (
        "letters.draft@2 takes to_customer only from a system or a person, never from untrusted "
        "data, and this value comes from suggested_recipient (untrusted:llm)"
    )


def test_a_mark_adds_distrust_never_removes_it() -> None:
    marked = drafting(recipient={"type": "string", "source": "untrusted:llm"})
    calls: list[dict[str, Any]] = []
    run = run_plan(
        marked,
        fields={
            "customer_email": sourced("ana@example.com", "system:crm"),
            "suggested_recipient": sourced("attacker@evil.example", "system:crm"),
        },
        answers=[],
        activities={"letters.draft@2": recording(calls)},
    )
    assert calls == []
    assert run.reason is not None
    assert run.reason.endswith("comes from suggested_recipient (system:crm, untrusted:llm)")


def test_an_input_that_does_not_fit_the_contract_stops_the_step() -> None:
    calls: list[dict[str, Any]] = []
    run = run_plan(
        looking_up(),
        fields={"order_id": sourced(Decimal(1001), "system:orders")},  # a number, not a text
        answers=[],
        activities={"orders.lookup@1": recording(calls)},
    )
    assert calls == []
    assert run.status == "stopped"
    assert run.reason == (
        "orders.lookup@1 doesn't take these inputs: order_id: Input should be a valid string"
    )


def test_trusted_values_pass_with_the_key_the_engine_fills() -> None:
    calls: list[dict[str, Any]] = []
    run = run_plan(
        drafting(),
        fields={
            "customer_email": sourced("ana@example.com", "system:crm"),
            "suggested_recipient": sourced("ana@example.com", "person:sam"),
        },
        answers=[],
        activities={"letters.draft@2": recording(calls)},
    )
    assert run.status == "succeeded"
    # The key is the run, the state and how many times the run has entered it (brief, D17).
    assert calls == [
        {"to_customer": "ana@example.com", "template": "reply", "idempotency_key": "memory/draft#1"}
    ]


def test_an_input_that_cannot_be_evaluated_stops_the_step() -> None:
    dividing = looking_up(inputs={"order_id": {"string": [{"/": [1, 0]}]}})
    run = run_plan(dividing, fields=ORDER, answers=[])
    assert run.status == "stopped"
    assert run.reason is not None
    assert run.reason.startswith("order_id can't be evaluated: division by zero")


def test_an_input_the_contract_does_not_take_stops_the_step() -> None:
    calls: list[dict[str, Any]] = []
    extra = looking_up(inputs={"order_id": {"var": "order_id"}, "note": "rush"})
    run = run_plan(
        extra, fields=ORDER, answers=[], activities={"orders.lookup@1": recording(calls)}
    )
    assert calls == []
    assert run.reason == "orders.lookup@1 doesn't take these inputs: note: not an input it takes"


def guide_plan() -> dict[str, Any]:
    """The plans guide's example plan, its first JSON block, as stored data."""
    example = GUIDE.read_text().split("```json\n")[1].split("```")[0]
    plan: dict[str, Any] = json.loads(example, parse_float=Decimal)
    return plan


def guide_fork() -> dict[str, Any]:
    """The guide's plan with its second JSON block: `check_order` forks on `amount > 100`, to the
    approval if it holds, else straight to `pay`. `validate` refuses it; the runtime never sees
    whether it did."""
    block = GUIDE.read_text().split("```json\n")[2].split("```")[0]
    plan = copy.deepcopy(guide_plan())
    plan["states"] |= json.loads("{" + block + "}", parse_float=Decimal)
    return plan


def test_a_condition_that_cannot_be_evaluated_stops_instead_of_skipping_the_approval() -> None:
    refunds: list[dict[str, Any]] = []
    run = run_plan(
        guide_fork(),
        fields={
            "order_id": sourced("A-1001", "system:orders"),
            "amount": sourced("250", "system:opener"),  # a text, so `amount > 100` can't be read
        },
        answers=[],
        activities={**FAKES, "payments.refund@2": recording(refunds)},
    )
    assert refunds == []  # the next transition, straight to pay, is never tried
    assert lines(run)[-1] == (
        "stopped at check_order: on done, amount > 100 can't be evaluated: `>` compares numbers, "
        "and it was given a string: the step needs attention, and nothing after it runs"
    )


def test_a_condition_must_give_a_boolean() -> None:
    # Nothing is truthy: a text is neither true nor false, so neither transition is taken.
    text_as_condition = looking_up(
        on={
            "done": [{"when": {"var": "order_id"}, "target": "missing"}, {"target": "found"}],
            "not_found": "missing",
        }
    )
    run = run_plan(text_as_condition, fields=ORDER, answers=[])
    assert run.status == "stopped"
    assert run.reason == (
        "on done, the condition order_id gives a string: a condition gives true or false"
    )


def order_is(order_id: str) -> dict[str, Any]:
    return {"==": [{"var": "order_id"}, order_id]}


def test_no_transition_holding_stops_the_step() -> None:
    none_holds = looking_up(
        on={"done": [{"when": order_is("B-2"), "target": "found"}], "not_found": "missing"}
    )
    run = run_plan(none_holds, fields=ORDER, answers=[])
    assert run.status == "stopped"
    assert run.reason == "on done, no transition holds"


def test_transitions_are_tried_in_order() -> None:
    both = looking_up(
        on={
            "done": [
                {"when": order_is("B-2"), "target": "missing"},
                {"when": order_is("A-1001"), "target": "found"},
                {"target": "missing"},
            ],
            "not_found": "missing",
        }
    )
    run = run_plan(both, fields=ORDER, answers=[])
    assert run.status == "succeeded"
    assert "moved on done to found" in lines(run)


GUIDE_FIELDS = {
    "order_id": sourced("A-1001", "system:orders"),
    "amount": sourced(Decimal(250), "system:opener"),
}
# The guide's people: Ana is in support, Sam is a team lead too (brief, D22).
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"]}


def test_an_answer_the_wait_does_not_offer_is_refused() -> None:
    run = run_plan(
        guide_plan(),
        fields=GUIDE_FIELDS,
        answers=[("approve_refund", "edit", "ana"), ("approve_refund", "approve", "sam")],
        people=PEOPLE,
    )
    assert "refused ana's answer edit: approve_refund offers approve or reject" in lines(run)
    assert run.status == "succeeded"  # the wait went on, and took sam's answer


def test_a_wait_takes_only_answers_it_can_be_given() -> None:
    no_timeout = copy.deepcopy(guide_plan())
    no_timeout["states"]["approve_refund"] = {
        "approval": {"of": "pay", "roles": ["support-lead"]},
        "on": {"approve": "pay", "reject": "failed"},
    }
    run = run_plan(
        no_timeout,
        fields=GUIDE_FIELDS,
        answers=[
            ("approve_refund", "timeout"),  # this wait has no timeout
            ("approve_refund", "timeout", "ana"),  # and a person never sends one
            ("approve_refund", "approve"),  # an outcome comes from a person
        ],
    )
    assert [line for line in lines(run) if line.startswith("refused")] == [
        "refused the answer timeout: approve_refund has no timeout",
        "refused ana's answer timeout: a timeout comes from the wait's timer, never from a person",
        "refused the answer approve: an answer comes from a person, and this one names nobody",
    ]


def asking(**wait: Any) -> dict[str, Any]:
    """A plan that asks one question, `confirm`, then ends as the answer says."""
    return {
        "plan": "asking",
        "version": 1,
        "display": {"title": "Asks one question"},
        "fields": {"order_id": {"type": "reference", "system": "orders"}},
        "initial": "confirm",
        "states": {
            "confirm": {
                "wait": {
                    "outcomes": ["accept", "decline"],
                    "roles": ["support"],
                    "timeout": "48h",
                    **wait,
                },
                "on": {"accept": "accepted", "decline": "declined", "timeout": "declined"},
            },
            "accepted": {"final": "succeeded"},
            "declined": {"final": "failed"},
        },
    }


def test_a_run_without_its_answer_waits() -> None:
    run = run_plan(asking(), fields=ORDER, answers=[])
    assert run.status == "waiting"  # not ended: the answer may still come
    # The line names the entry, as an answer and a refusal do (layer 6's tutor review).
    assert lines(run)[-1] == "waiting at confirm#1 for accept or decline by support, at most 48h"


def test_a_declared_timeout_moves_on() -> None:
    run = run_plan(guide_plan(), fields=GUIDE_FIELDS, answers=[("approve_refund", "timeout")])
    assert run.status == "failed"
    assert lines(run)[-4:] == [
        "the wait timed out",
        "moved on timeout to failed",
        "entered failed",
        "ended failed",
    ]


def test_the_key_is_the_state_and_its_run() -> None:
    # Declined, the refund goes back through the approval, so each pass is approved.
    again = copy.deepcopy(guide_plan())
    again["states"]["pay"]["on"]["declined"] = "approve_refund"
    keys: list[str] = []

    def declines_once(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        if len(keys) == 1:
            raise Outcome("declined")
        return {"refund_id": "refund-1"}

    run = run_plan(
        again,
        fields=GUIDE_FIELDS,
        answers=[("approve_refund", "approve", "sam"), ("approve_refund", "approve", "lee")],
        activities={**FAKES, "payments.refund@2": declines_once},
        people={**PEOPLE, "lee": ["support-lead"]},
    )
    assert run.status == "succeeded"
    # A retry would reuse a key; a second run of the step never does (brief, D17).
    assert keys == ["memory/pay#1", "memory/pay#2"]


def test_two_runs_never_share_a_key() -> None:
    # The same plan, run twice: a key naming only the state would be `pay#1` both times, and the
    # payment system would hand the second run the first one's refund (brief, D17).
    keys: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        return {"refund_id": "refund-1"}

    for name in ("refund-1", "refund-2"):
        run_plan(
            guide_plan(),
            fields=GUIDE_FIELDS,
            answers=[("approve_refund", "approve", "sam")],
            activities={**FAKES, "payments.refund@2": refund},
            run=name,
            people=PEOPLE,
        )
    assert keys == ["refund-1/pay#1", "refund-2/pay#1"]


def test_a_run_is_the_same_every_time() -> None:
    # No clock, no randomness, no I/O: what Temporal's replay needs (layer 6).
    answers = [("approve_refund", "edit", "ana"), ("approve_refund", "approve", "sam")]
    first, second = (
        run_plan(guide_plan(), fields=GUIDE_FIELDS, answers=list(answers), people=PEOPLE)
        for _ in range(2)
    )
    assert first.history == second.history


def guide_block(after: str) -> str:
    """The guide's first fenced block after the text `after`, without its language tag."""
    rest = GUIDE.read_text().split(after, 1)[1]
    return rest.split("```", 1)[1].split("```", 1)[0].removeprefix("python").strip("\n")


def test_the_guides_run() -> None:
    # Our own documentation, run so it can't drift from the code; never a definition (data).
    namespace: dict[str, Any] = {"refund_order": guide_plan()}
    exec(guide_block("## Running a plan"), namespace)  # noqa: S102 -- our guide, as in layer 1
    assert namespace["run"].status == "succeeded"


def test_the_guides_history() -> None:
    run = run_plan(
        guide_plan(),
        fields=GUIDE_FIELDS,
        answers=[("approve_refund", "approve", "sam")],
        people=PEOPLE,
    )
    assert lines(run) == guide_block("says what happened, one event per line").splitlines()


def one_line(block: str) -> str:
    """A message the guide wraps over several lines, as the one line the engine writes."""
    return " ".join(line.strip() for line in block.splitlines() if line.strip())


def test_the_guides_stopped_messages() -> None:
    # The injection example with `suggested_recipient` left unmarked, given the model's value.
    injection = json.loads(GUIDE.read_text().split("```json\n")[3].split("```")[0])
    del injection["fields"]["suggested_recipient"]["source"]
    run = run_plan(
        injection,
        fields={
            "customer_email": sourced("ana@example.com", "system:crm"),
            "suggested_recipient": sourced("attacker@evil.example", "untrusted:llm"),
        },
        answers=[],
    )
    assert lines(run)[-1] == one_line(guide_block("is ever called:"))

    run = run_plan(
        guide_fork(),
        fields={**GUIDE_FIELDS, "amount": sourced("250", "system:opener")},
        answers=[],
    )
    assert lines(run)[-1] == one_line(guide_block("to `pay`:"))


def test_a_value_its_policy_refuses_is_never_evaluated() -> None:
    # The policy is checked on where the value comes from; what it would be doesn't matter.
    poisoned = drafting()
    poisoned["states"]["draft"]["inputs"]["to_customer"] = {
        "cat": [{"var": "suggested_recipient"}, {"string": [{"/": [1, 0]}]}]
    }
    run = run_plan(
        poisoned,
        fields={
            "customer_email": sourced("ana@example.com", "system:crm"),
            "suggested_recipient": sourced("attacker@evil.example", "untrusted:llm"),
        },
        answers=[],
    )
    assert run.reason is not None
    assert run.reason.startswith("letters.draft@2 takes to_customer only from")


def test_the_engines_key_replaces_any_a_plan_gives() -> None:
    calls: list[dict[str, Any]] = []
    keyed = drafting()
    keyed["states"]["draft"]["inputs"]["idempotency_key"] = "mine"  # validate: ENGINE_INPUT
    run_plan(
        keyed,
        fields={
            "customer_email": sourced("ana@example.com", "system:crm"),
            "suggested_recipient": sourced("ana@example.com", "person:sam"),
        },
        answers=[],
        activities={"letters.draft@2": recording(calls)},
    )
    assert [call["idempotency_key"] for call in calls] == ["memory/draft#1"]


def test_a_state_of_a_kind_the_engine_does_not_know_stops_the_step() -> None:
    # A fourth kind of state can't be written (parse_plan refuses it); `model_copy` skips every
    # check (learning question 31), so it is the side door this test comes through.
    plan = parse_plan(ending_at_once())
    odd = plan.model_copy(update={"states": {"done": "a fourth kind"}})

    async def call(reference: str, inputs: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("nothing is called")

    async def wait(
        state: str, entry: str, outcomes: tuple[str, ...], timeout: str | None
    ) -> Answer | None:
        raise AssertionError("nothing is waited for")

    run = asyncio.run(
        interpret(
            odd, {"amount": sourced(250, "system:opener")}, CATALOG, call, wait, run_name="memory"
        )
    )
    assert run.status == "stopped"
    assert run.reason == "done is a kind of state this engine doesn't know: str"


def test_a_loop_that_never_waits_is_stopped() -> None:
    # From the tutor review: it validates (it can end through not_found), and looked up forever.
    looping = looking_up(on={"done": "look", "not_found": "missing"})
    run = run_plan(looping, fields=ORDER, answers=[])
    assert run.status == "stopped"
    assert run.reason == (
        "entered 1,000 states without waiting for anyone: a plan that loops needs a wait or an end"
    )


def test_a_loop_through_a_wait_does_not_count_against_the_bound() -> None:
    # Each pass looks the order up, then asks a person: 600 passes enter 1,200 states.
    asking = looking_up(on={"done": "ask", "not_found": "missing"})
    asking["states"]["ask"] = {
        "wait": {"outcomes": ["again", "enough"], "roles": ["support"]},
        "on": {"again": "look", "enough": "found"},
    }
    run = run_plan(
        asking, fields=ORDER, answers=[("ask", "again", "sam")] * 600, people={"sam": ["support"]}
    )
    assert lines(run).count("entered look") == 601
    assert run.status == "waiting"  # the script ran out; nothing was stopped


# Layer 9a, slice 1: a plan's references name registered systems (brief, D30).


def test_a_plan_reference_to_an_unregistered_system_is_refused() -> None:
    plan = ending_at_once()
    plan["fields"]["order_id"] = {"type": "reference", "system": "sail"}
    with pytest.raises(RunRefused, match="order_id is a reference to sail, which is not a regist"):
        run_plan(
            plan,
            fields={
                "amount": sourced(Decimal(250), "system:opener"),
                "order_id": sourced("ord-1", "system:opener"),
            },
            answers=[],
        )


def lettering(customer: str) -> dict[str, Any]:
    """A plan drafting a letter to the reference in its field `customer`, of its system."""
    return {
        "plan": "write-to",
        "version": 1,
        "display": {"title": "Write to a customer"},
        "fields": {
            "customer_id": {"type": "reference", "system": "crm"},
            "policy_id": {"type": "reference", "system": "policies"},
        },
        "initial": "draft",
        "states": {
            "draft": {
                "activity": "letters.draft@3",
                "inputs": {"customer": {"var": customer}, "template": "hello"},
                "on": {"done": "done"},
            },
            "done": {"final": "succeeded"},
        },
    }


def test_a_plan_gives_a_reference_input_only_its_system() -> None:
    fields = {
        "customer_id": sourced("cus-7", "system:opener"),
        "policy_id": sourced("pol-3", "system:opener"),
    }
    calls: list[dict[str, Any]] = []
    run = run_plan(
        lettering("policy_id"),
        fields=fields,
        answers=[],
        activities={"letters.draft@3": recording(calls)},
    )
    assert calls == []
    assert run.status == "stopped"
    assert run.reason == (
        "letters.draft@3 takes customer as a reference to crm, and is given policy_id, a "
        "reference to policies"
    )
    assert run_plan(lettering("customer_id"), fields=fields, answers=[]).status == "succeeded"


# Layer 9b: a plan field given a sensitive value stays sensitive for the run, its activity's
# code gets the plain value, and its own message is never recorded (brief, D31).
def checking_an_id() -> dict[str, Any]:
    """A plan given a national ID: a person adds a note, then the ID is looked up."""
    return {
        "plan": "check-id",
        "version": 1,
        "display": {"title": "Check an ID"},
        "fields": {"id": {"type": "string"}, "note": {"type": "string"}},
        "initial": "confirm",
        "states": {
            "confirm": {
                "wait": {
                    "outcomes": ["confirm"],
                    "roles": ["support"],
                    "sets": {"confirm": ["note"]},
                },
                "on": {"confirm": "check"},
            },
            "check": {
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"cat": [{"var": "id"}, {"var": "note"}]}},
                "on": {"done": "noted"},
            },
            "noted": {
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "note"}},
                "on": {"done": "checked"},
            },
            "checked": {"final": "succeeded"},
        },
    }


NATIONAL_ID = "1 85 05 78 006 084 36"


def test_a_plan_input_from_a_sensitive_value_stays_sensitive() -> None:
    given: list[dict[str, Any]] = []

    def check(inputs: dict[str, Any]) -> dict[str, Any]:
        given.append(inputs)
        return {"status": "known"}

    run = run_plan(
        checking_an_id(),
        fields={"id": sourced(Sensitive(NATIONAL_ID), "system:opener")},
        # The script wraps every form value, as the client does; the plan keeps the note plain.
        answers=[("confirm", "confirm", "ana", {"note": "/2"})],
        activities={**FAKES, "orders.lookup@1": check},
        people={"ana": ["support"]},
    )
    assert run.status == "succeeded"
    with_id, note_only = [event for event in run.history if isinstance(event, Scheduled)]
    assert with_id.inputs["order_id"] == Sensitive(f"{NATIONAL_ID}/2")
    assert note_only.inputs["order_id"] == "/2"
    assert given == [{"order_id": f"{NATIONAL_ID}/2"}, {"order_id": "/2"}]
    assert NATIONAL_ID not in "\n".join(map(str, run.history))


def test_a_plan_records_no_activity_message() -> None:
    def failing(inputs: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(f"no order {inputs['order_id']}")

    run = run_plan(
        checking_an_id(),
        fields={"id": sourced(Sensitive(NATIONAL_ID), "system:opener")},
        answers=[("confirm", "confirm", "ana", {"note": "/2"})],
        activities={**FAKES, "orders.lookup@1": failing},
        people={"ana": ["support"]},
    )
    assert run.status == "stopped"
    assert run.reason == "orders.lookup@1 failed with RuntimeError: ‹sensitive›"
    assert "no order" not in "\n".join(map(str, run.history))
