"""Layer 12d: migrations. An open case moves to a later release, as one more kind of change
request: proposed, approved by someone else, checked again and applied; names mapped by name, and
refused, never terminated, when something depends on a name the target lacks (brief, D53).

See docs/layers/12-releases.md (12d) and docs/guides/releases.md, "Moving open cases to a later
release".
"""

import copy
import dataclasses
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from test_case import REFUND

from ventoux.case.releases import Written
from ventoux.testing import (
    AnswerRefused,
    ChangeRefused,
    finish,
    migrate,
    propose,
    release_of,
    run_case,
    send,
)

ROOT = Path(__file__).parent.parent
LARGE = {"order_id": "ord-1", "amount": 250}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 250})

# Ana and Sam work the refund, Lee leads the team and runs releases with Pia and Pat; Fay checks
# for fraud.
PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead", "platform"],
    "pia": ["platform"],
    "pat": ["platform"],
    "fay": ["fraud"],
}


def refund_2() -> dict[str, Any]:
    """The refund's second release: a fraud check, which the payment now requires."""
    definition = copy.deepcopy(REFUND)
    definition["steps"]["fraud_check"] = {
        "kind": "task",
        "display": {"title": "Check the refund for fraud"},
        "roles": ["fraud"],
        "outcomes": {"clear": {"display": {"title": "No fraud found"}}},
    }
    definition["steps"]["pay"]["requires"] = ["fraud_check"]
    return definition


REFUND_1 = release_of(REFUND, 1)
REFUND_2 = release_of(refund_2(), 2)


def on_refund_1(answers: list[Any], **options: Any) -> Any:
    """The refund opened on its first release, played with `answers`."""
    return run_case(REFUND, file=LARGE, answers=answers, people=PEOPLE, release=REFUND_1, **options)


# --- Slice 1: the kind ---


def test_a_self_approved_migration_is_refused() -> None:
    # The curriculum's negative test: nobody approves a migration they proposed (brief, D52).
    with pytest.raises(AnswerRefused, match="^pia proposed case.change#1, so cannot approve it$"):
        on_refund_1([REVIEWED, migrate(REFUND_2, {}, "pia"), ("case.change#1", "approve", "pia")])
    waiting = on_refund_1([REVIEWED, migrate(REFUND_2, {}, "pia")])
    assert "approval of case.change#1 (migrate to refund 2) by platform" in waiting.waiting_for
    assert waiting.state.release == "refund 1"


def test_a_migration_moves_the_case() -> None:
    moved = on_refund_1(
        [REVIEWED, migrate(REFUND_2, {}, "pia"), ("case.change#1", "approve", "lee")]
    )
    assert moved.history[-5:] == [
        "pia proposed case.change#1: migrate to refund 2, to be approved by platform",
        "lee answered case.change#1 approve as platform",
        (
            "applied case.change#1: migrated from refund 1, engine 2 to refund 2, engine 2, "
            "proposed by pia, approved by lee"
        ),
        "withdrew pay.approval#1: refund 2 changed pay",
        "started fraud_check#1: waiting for clear by fraud",
    ]
    assert (moved.state.release, moved.state.engine) == ("refund 2", 2)
    # The case now decides as refund 2: the payment waits for the fraud check, then its approval.
    paid = on_refund_1(
        [
            REVIEWED,
            migrate(REFUND_2, {}, "pia"),
            ("case.change#1", "approve", "lee"),
            ("fraud_check", "clear", "fay"),
            ("pay.approval#2", "approve", "sam"),
        ]
    )
    assert paid.closed and paid.reached("pay")


def refused_migration(
    target: Any, engine: int | None = None, by: str = "pia", **options: Any
) -> str:
    """What the engine says when `by` proposes moving the reviewed refund to `target`."""
    proposal = migrate(target, {}, by) if engine is None else migrate(target, {}, by, engine)
    with pytest.raises(ChangeRefused) as refused:
        on_refund_1([REVIEWED, proposal], **options)
    return str(refused.value)


def test_a_target_is_checked() -> None:
    # Fail closed: a role, a package, a digest, a contract or an engine version the case can't
    # vouch for is refused, and nothing is pending (brief, D53).
    assert refused_migration(REFUND_2, by="ana") == (
        "a migration is proposed by platform, and ana has support"
    )
    claim = copy.deepcopy(REFUND)
    claim["case"] = "claim"
    assert refused_migration(release_of(claim, 3)) == (
        "claim 3 is a release of claim, and this case is a refund"
    )
    # The package given with refund 2's digest isn't refund 2's: the case checks the digest, as
    # it does at its opening (brief, D51).
    tampered = copy.deepcopy(refund_2())
    del tampered["steps"]["pay"]["approval"]
    forged = dataclasses.replace(REFUND_2, written=Written(json.dumps(tampered, default=int), {}))
    assert refused_migration(forged) == "what was given as refund 2 doesn't give its digest"
    unknown = copy.deepcopy(refund_2())
    unknown["steps"]["pay"]["activity"] = "payments.refund@3"
    assert refused_migration(release_of(unknown, 3)) == (
        "refund 3 calls payments.refund@3, which this worker's catalog doesn't have"
    )
    assert refused_migration(REFUND_1) == (
        "the case is already on refund 1, engine 2: nothing to move"
    )
    assert refused_migration(REFUND_2, engine=3) == (
        "engine 3 is one this code doesn't know (it knows 2, 1)"
    )
    assert refused_migration(REFUND_2, engine=1) == (
        "engine 1 is older than the case's engine 2: the engine never goes back"
    )


def test_the_engine_moves_forward_only() -> None:
    # A migration may move the engine alone, keeping the release: how an open case adopts a later
    # engine. The version is data in the request, so a replay reads it (brief, D51) (brief, D53).
    moved = on_refund_1(
        [REVIEWED, migrate(REFUND_1, {}, "pia", 2), ("case.change#1", "approve", "lee")],
        engine=1,
    )
    assert (
        "applied case.change#1: migrated from refund 1, engine 1 to refund 1, engine 2, "
        "proposed by pia, approved by lee"
    ) in moved.history
    assert (moved.state.release, moved.state.engine) == ("refund 1", 2)


# --- Slice 2: the mapping, and what depends on a name ---

SMALL = {"order_id": "ord-1", "amount": 40}
SMALL_REVIEW = ("review", "approve", "ana", {"approved_amount": 40})


def renamed() -> dict[str, Any]:
    """Refund 2, its approved amount renamed `amount_approved`, and its payment step `payment`."""
    text = json.dumps(refund_2(), default=int)
    text = text.replace("approved_amount", "amount_approved")
    text = text.replace('"pay"', '"payment"').replace('"pay.outcome"', '"payment.outcome"')
    renaming: dict[str, Any] = json.loads(text)
    return renaming


REFUND_3 = release_of(renamed(), 3)
RENAMES = {"steps": {"pay": "payment"}, "fields": {"approved_amount": "amount_approved"}}


def test_names_map_by_name() -> None:
    # What Ana answered is the same value under its new name, from the same person, and the run
    # keeps its entry, so its key (brief, D53).
    moved = on_refund_1(
        [REVIEWED, migrate(REFUND_3, RENAMES, "pia"), ("case.change#1", "approve", "lee")]
    )
    assert moved.history[-5:] == [
        (
            "applied case.change#1: migrated from refund 1, engine 2 to refund 3, engine 2, "
            "proposed by pia, approved by lee"
        ),
        "withdrew pay.approval#1: refund 3 changed pay",
        "renamed step pay to payment",
        "renamed field approved_amount to amount_approved",
        "started fraud_check#1: waiting for clear by fraud",
    ]
    values, sources = moved.state.values, moved.state.sources
    assert "approved_amount" not in values and values["amount_approved"] == 250
    assert sources["amount_approved"] == frozenset({"person:ana"})
    paid = on_refund_1(
        [
            REVIEWED,
            migrate(REFUND_3, RENAMES, "pia"),
            ("case.change#1", "approve", "lee"),
            ("fraud_check", "clear", "fay"),
            ("payment.approval#2", "approve", "sam"),
        ]
    )
    assert paid.closed and paid.reached("payment")
    assert [run.entry for run in paid.state.runs] == ["review#1", "fraud_check#1", "payment#1"]
    # A run of a renamed step keeps its entry, and so its key, under its new step; what it gave
    # is under the new name.
    moved_done = run_case(
        kept_open(REFUND),
        file=SMALL,
        answers=[
            SMALL_REVIEW,
            migrate(release_of(kept_open(renamed()), 3), RENAMES, "pia"),
            ("case.change#1", "approve", "lee"),
        ],
        people=PEOPLE,
        release=release_of(kept_open(REFUND), 1),
    )
    assert [(run.entry, run.step) for run in moved_done.state.runs] == [
        ("review#1", "review"),
        ("pay#1", "payment"),
        ("fraud_check#1", "fraud_check"),
    ]
    assert moved_done.state.values["payment.outcome"] == "done"
    assert "pay.outcome" not in moved_done.state.values


def refused_mapping(mapping: dict[str, dict[str, str]]) -> str:
    with pytest.raises(ChangeRefused) as refused:
        on_refund_1([REVIEWED, migrate(REFUND_3, mapping, "pia")])
    return str(refused.value)


def test_a_bad_mapping_is_refused() -> None:
    # The mapping is data, read strictly: nothing in it is guessed (brief, D53).
    assert refused_mapping({**RENAMES, "tasks": {}}) == (
        "the mapping has no section tasks: its sections are steps, milestones, fields, rules and "
        "events"
    )
    # Every problem at once.
    assert refused_mapping({**RENAMES, "milestones": {"paid": "settled"}}) == (
        "milestones.paid: refund 1 has no milestone paid\n"
        "milestones.paid: refund 3 has no milestone settled"
    )
    assert refused_mapping({**RENAMES, "steps": {"pay": "settle"}}) == (
        "steps.pay: refund 3 has no step settle"
    )
    assert (
        refused_mapping({**RENAMES, "steps": {"pay": "payment", "call_customer": "payment"}})
        == "steps: pay and call_customer are both mapped to payment"
    )


def test_an_unmapped_rename_running_work_depends_on_is_refused() -> None:
    # The curriculum's negative test. Refund 3 renames pay, the mapping doesn't say so, and pay#1
    # is running: refused, never terminated (brief, D53). When proposed:
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            REFUND,
            file=SMALL,
            answers=[SMALL_REVIEW, migrate(REFUND_3, {"fields": RENAMES["fields"]}, "pia")],
            people=PEOPLE,
            release=REFUND_1,
            held=["pay"],
        )
    assert str(refused.value) == (
        "pay#1 is running, and refund 3 has no step pay: map it, or migrate after it finishes"
    )
    # And when applied: proposed while nothing depended on it, pay#1 started since.
    started = run_case(
        REFUND,
        file=SMALL,
        answers=[
            migrate(REFUND_3, {"fields": RENAMES["fields"]}, "pia"),
            SMALL_REVIEW,
            ("case.change#1", "approve", "lee"),
        ],
        people=PEOPLE,
        release=REFUND_1,
        held=["pay"],
    )
    assert started.history[-1] == (
        "case.change#1 not applied: pay#1 is running, and refund 3 has no step pay: map it, or "
        "migrate after it finishes"
    )
    assert started.state.release == "refund 1"


def kept_open(definition: dict[str, Any]) -> dict[str, Any]:
    """`definition`, open until a person closes it, so a case can migrate once its work is done."""
    definition = copy.deepcopy(definition)
    definition["stays_open"] = True
    definition["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    return definition


def refused_on(
    source: dict[str, Any],
    target: dict[str, Any],
    answers: list[Any],
    file: dict[str, Any] = SMALL,
    activities: dict[str, Any] | None = None,
) -> str:
    """What the engine says when Pia proposes moving a case of `source`, after `answers`, to
    `target`, nothing renamed."""
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            source,
            file=file,
            answers=[*answers, migrate(release_of(target, 2), {}, "pia")],
            people=PEOPLE,
            release=release_of(source, 1),
            activities=activities or {},
        )
    return str(refused.value)


def without(definition: dict[str, Any], change: Any) -> dict[str, Any]:
    """A copy of `definition`, changed by `change`."""
    changed = copy.deepcopy(definition)
    change(changed)
    return changed


def test_what_depends_on_a_name_refuses() -> None:
    # Each is said, with what to map or wait for; values are never converted, and nothing
    # loosens (brief, D53).
    paid = kept_open(REFUND)
    paid["milestones"] = {"paid": {"display": {"title": "Refund paid"}}}
    paid["steps"]["pay"]["reaches"] = ["paid"]
    unpaid = without(paid, lambda d: (d.pop("milestones"), d["steps"]["pay"].pop("reaches")))
    assert refused_on(paid, unpaid, [SMALL_REVIEW]) == (
        "paid is reached, and refund 2 has no milestone paid: map it, since a milestone reached "
        "is never undone"
    )
    # A value, of the same type, in a field that doesn't loosen.
    noted = kept_open(REFUND)
    noted["fields"]["note"] = {
        "type": "string",
        "display": {"title": "A note"},
        "sensitive": True,
        "visible_to": ["support"],
    }
    with_note = {**SMALL, "note": "call after 5"}
    assert refused_on(noted, kept_open(REFUND), [], with_note) == (
        "note holds a value, and refund 2 has no field note: map it"
    )
    as_number = without(noted, lambda d: d["fields"]["note"].update(type="number"))
    assert refused_on(noted, as_number, [], with_note) == (
        "note is a string in refund 1, and note is a number in refund 2: values are never converted"
    )
    plain = without(noted, lambda d: d["fields"]["note"].update(sensitive=False))
    assert refused_on(noted, plain, [], with_note) == (
        "note is sensitive in refund 1, and note isn't in refund 2: a migration never loosens it"
    )
    wider = without(noted, lambda d: d["fields"]["note"].update(visible_to=["support", "fraud"]))
    assert refused_on(noted, wider, [], with_note) == (
        "note is seen by more roles in refund 2 than note in refund 1: a migration never loosens it"
    )
    # What a finished run recorded: its outcome, its outputs.
    accepting = without(
        kept_open(REFUND),
        lambda d: d["steps"]["review"]["outcomes"].update(
            accept=d["steps"]["review"]["outcomes"].pop("approve")
        ),
    )
    assert refused_on(kept_open(REFUND), accepting, [SMALL_REVIEW]) == (
        "review.outcome is approve, which refund 2's review doesn't declare: values are never "
        "converted"
    )
    looking_up = without(
        kept_open(REFUND),
        lambda d: d["steps"]["pay"].update(
            activity="orders.lookup@1", inputs={"order_id": {"var": "order_id"}}
        ),
    )
    assert refused_on(kept_open(REFUND), looking_up, [SMALL_REVIEW]) == (
        "pay.refund_id was given by payments.refund@2, and refund 2's pay calls orders.lookup@1, "
        "which doesn't give refund_id as it was: values are never converted"
    )
    # What an arrival carried.
    cancellable = kept_open(REFUND)
    cancellable["events"] = {
        "cancelled": {
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
    }
    cancel = send("cancelled", {"note": "changed my mind"}, "system:portal")
    as_count = without(
        cancellable, lambda d: d["events"]["cancelled"]["payload"]["note"].update(type="number")
    )
    assert refused_on(cancellable, as_count, [cancel]) == (
        "cancelled.note was carried by cancelled, and refund 2's cancelled doesn't carry note as "
        "it was: values are never converted"
    )
    assert refused_on(cancellable, without(cancellable, lambda d: d.pop("events")), [cancel]) == (
        "cancelled has arrived, and refund 2 has no event cancelled: map it"
    )
    # A rule whose firing waits for a person.
    flagging = kept_open(REFUND)
    flagging["milestones"] = {"large": {"display": {"title": "A large refund"}}}
    flagging["rules"] = {
        "flag_large": {
            "display": {"title": "Mark a large refund"},
            "on": "opened",
            "when": {">": [{"var": "approved_amount"}, 1000]},
            "then": {"reach": ["large"]},
        }
    }
    assert refused_on(flagging, without(flagging, lambda d: d.pop("rules")), []) == (
        "flag_large#1 failed, and refund 2 has no rule flag_large: map it, or retry it first"
    )


def test_what_waits_on_a_step_refuses_its_removal() -> None:
    # An approval asked, a person's proposal, a rule's start: each waits on the step (brief, D53).
    no_payment = without(
        kept_open(REFUND),
        lambda d: (
            d["steps"].pop("pay"),
            d["steps"].pop("call_customer"),
            d.update(sequence=["review"]),
        ),
    )
    proposed = without(
        kept_open(REFUND),
        lambda d: d["steps"]["pay"].update(automatic=False, proposed_by=["support"]),
    )
    assert refused_on(proposed, no_payment, [REVIEWED, propose("pay", "sam")], LARGE) == (
        "pay.approval#1 is open, and refund 2 has no step pay: map it\n"
        "pay waits on sam's proposal, and refund 2 has no step pay: map it"
    )
    started = without(kept_open(REFUND), lambda d: d["steps"]["pay"].update(automatic=False))
    started["rules"] = {
        "start_pay": {
            "display": {"title": "Pay once reviewed"},
            "on": {"answered": "review"},
            "then": {"start": ["pay"]},
        }
    }
    assert refused_on(started, no_payment, [REVIEWED], LARGE) == (
        "pay.approval#1 is open, and refund 2 has no step pay: map it\n"
        "pay waits on start_pay#1, and refund 2 has no step pay: map it\n"
        "pay waits on start_pay#1, and refund 2 has no rule start_pay: map it"
    )


# --- Slice 3: running work, open tasks, waits and failed runs ---


def looking_up() -> dict[str, Any]:
    """The refund kept open, its payment step calling another contract than the payment."""
    return without(
        kept_open(REFUND),
        lambda d: d["steps"]["pay"].update(
            activity="orders.lookup@1", inputs={"order_id": {"var": "order_id"}}
        ),
    )


def account_closed(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("account closed")


def test_running_work_finishes_on_its_contract() -> None:
    # A running run's result is checked against the contract that ran it: a target whose step
    # calls another is refused until it finishes (brief, D10) (brief, D53).
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            kept_open(REFUND),
            file=SMALL,
            answers=[SMALL_REVIEW, migrate(release_of(looking_up(), 2), {}, "pia")],
            people=PEOPLE,
            release=release_of(kept_open(REFUND), 1),
            held=["pay"],
        )
    assert str(refused.value) == (
        "pay#1 is running on payments.refund@2, and refund 2's pay calls orders.lookup@1: "
        "migrate after it finishes"
    )
    # The same contract: the run finishes under the target, keeping its entry and its key.
    with_check = without(kept_open(refund_2()), lambda d: d["steps"]["pay"].pop("requires"))
    finished = run_case(
        kept_open(REFUND),
        file=SMALL,
        answers=[
            SMALL_REVIEW,
            migrate(release_of(with_check, 2), {}, "pia"),
            ("case.change#1", "approve", "lee"),
            finish("pay#1"),
        ],
        people=PEOPLE,
        release=release_of(kept_open(REFUND), 1),
        held=["pay"],
    )
    assert "pay#1 done, giving refund_id from untrusted:undeclared" in finished.history
    assert finished.state.release == "refund 2"
    # A failed run is retried as the same run, with the same key (brief, D26): its contract too.
    with pytest.raises(ChangeRefused) as failed:
        run_case(
            kept_open(REFUND),
            file=SMALL,
            answers=[SMALL_REVIEW, migrate(release_of(looking_up(), 2), {}, "pia")],
            people=PEOPLE,
            release=release_of(kept_open(REFUND), 1),
            activities={"payments.refund@2": account_closed},
        )
    assert str(failed.value) == (
        "pay#1 is failed on payments.refund@2, and refund 2's pay calls orders.lookup@1: "
        "migrate after it is retried or skipped"
    )


def plan_package() -> tuple[dict[str, Any], dict[str, Any]]:
    """The example package: the refund, its payment made by the `refund-order@1` plan."""
    folder = ROOT / "examples" / "packages" / "refund"
    case = json.loads((folder / "case.json").read_text(), parse_float=Decimal)
    plan = json.loads((folder / "plans" / "refund-order.json").read_text(), parse_float=Decimal)
    return case, plan


def test_a_running_plan_finishes_on_its_plan() -> None:
    # Plans don't migrate (brief, D28): a target running another plan waits for this one.
    case, plan = plan_package()
    target = without(case, lambda d: d["steps"]["settle"].update(plan="refund-order@2"))
    later_plan = {**plan, "version": 2}
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            case,
            file=LARGE,
            answers=[REVIEWED, migrate(release_of(target, 2, [later_plan]), {}, "pia")],
            people=PEOPLE,
            release=release_of(case, 1, [plan]),
            plans={"refund-order@1": plan},
        )
    assert str(refused.value) == (
        "settle#1 is running on refund-order@1, and refund 2's settle runs refund-order@2: "
        "migrate after it finishes"
    )


def test_open_and_failed_runs_stay() -> None:
    # An open task stays open, answered as the target says: its roles, its outcomes.
    escalating = without(
        kept_open(REFUND),
        lambda d: (
            d["steps"]["review"].update(roles=["support", "support-lead"]),
            d["steps"]["review"]["outcomes"].update(
                escalate={"display": {"title": "Escalate to a team lead"}}
            ),
        ),
    )
    moved = run_case(
        kept_open(REFUND),
        file=SMALL,
        answers=[
            migrate(release_of(escalating, 2), {}, "pia"),
            ("case.change#1", "approve", "lee"),
        ],
        people=PEOPLE,
        release=release_of(kept_open(REFUND), 1),
    )
    assert moved.waiting_for == ["review by support or support-lead"]
    answered = run_case(
        kept_open(REFUND),
        file=SMALL,
        answers=[
            migrate(release_of(escalating, 2), {}, "pia"),
            ("case.change#1", "approve", "lee"),
            ("review#1", "escalate", "lee"),
        ],
        people=PEOPLE,
        release=release_of(kept_open(REFUND), 1),
    )
    # Lee leads the team: only the target lets a support-lead answer the review.
    assert "lee answered review#1 escalate as support-lead" in answered.history
    # A step that changed kind under an open run is refused: answer it first.
    automated = without(
        kept_open(REFUND),
        lambda d: d["steps"].update(
            review={
                "kind": "activity",
                "display": {"title": "Review the refund request"},
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "order_id"}},
            }
        ),
    )
    assert refused_on(kept_open(REFUND), automated, []) == (
        "review#1 is open, and refund 2's review is another kind of step: migrate after it is "
        "answered"
    )


def waiting_for_cancellation() -> dict[str, Any]:
    """The refund kept open, waiting for the customer to cancel from the portal."""
    definition = kept_open(REFUND)
    definition["events"] = {
        "cancelled": {
            "display": {"title": "The customer cancels"},
            "sent_by": {"system": "portal"},
            "payload": {},
        }
    }
    definition["steps"]["await_cancel"] = {
        "kind": "wait",
        "display": {"title": "Wait for a cancellation"},
        "event": "cancelled",
    }
    return definition


def test_an_open_wait_stays_on_its_event() -> None:
    # A wait renamed with its event waits on, its line as the target says it; one waiting for
    # another event is refused until it ends (brief, D53).
    renamed_event = json.loads(
        json.dumps(waiting_for_cancellation()).replace("cancelled", "withdrawn")
    )
    moved = run_case(
        waiting_for_cancellation(),
        file=SMALL,
        answers=[
            migrate(release_of(renamed_event, 2), {"events": {"cancelled": "withdrawn"}}, "pia"),
            ("case.change#1", "approve", "lee"),
        ],
        people=PEOPLE,
        release=release_of(waiting_for_cancellation(), 1),
    )
    assert "withdrawn from portal" in moved.waiting_for
    other = without(
        waiting_for_cancellation(),
        lambda d: (
            d["events"].update(withdrawn=d["events"]["cancelled"]),
            d["steps"]["await_cancel"].update(event="withdrawn"),
        ),
    )
    assert refused_on(waiting_for_cancellation(), other, []) == (
        "await_cancel#1 waits for cancelled, and refund 2's await_cancel waits for withdrawn: "
        "migrate after it arrives"
    )
