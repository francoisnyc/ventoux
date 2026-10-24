"""The semantic diff in plain language, and readings of every entry (layer 13c; brief, D55 and
D56, D45 as amended).

See docs/layers/13-diff.md (13c) and docs/guides/releases.md, "What changed: the diff".
"""

import copy
import inspect
import json
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from test_diff import FOUR_EYES, LOOSE, calling, packed, refund, settling
from test_diff_people import fresh

from ventoux.case.answers import AnswerRefused
from ventoux.case.definition import CaseDefinition
from ventoux.case.diff import Diff, diff
from ventoux.case.markdown import text as text_of
from ventoux.case.plain import plain
from ventoux.case.reading import ENTRY_CLAUSES, EntryReading, ReadingRefused, read_entry
from ventoux.case.releases import Package, changed
from ventoux.core.catalog import Catalog
from ventoux.core.plan import Plan
from ventoux.testing import CATALOG, propose, run_case

# --- Slice 0: written otherwise, the same decisions ----------------------------------------------


def test_an_age_written_otherwise_is_no_verdict() -> None:
    # From the review of #48: 1d and 24h decide the same for every case, so nothing suggests a
    # loosening; the history words the age as written, and the line says so (13c, choice 38).
    found = diff(packed(fresh("1d")), packed(fresh("24h")), CATALOG)
    assert found.changes == ()
    assert [str(line) for line in found.rewritten] == [
        (
            "rewritten  steps.lookup.max_age.order_id: 1d -> 24h: the same decisions; the history "
            "says 24 hours where it said 1 day"
        )
    ]
    assert found.summary() == "fresh: no behaviour change; 1 written otherwise; no wording change"
    # Never less than the digest (choice 5): the path it sees is said, as a rewriting.
    seen = changed(packed(fresh("1d")), packed(fresh("24h"))).behaviour
    assert list(seen) == [line.path for line in found.rewritten]


def chasing(rule: dict[str, Any]) -> Package:
    """The quickstart's refund, with `nudge`, a repeatable task, and `rule`, written as `chase`."""
    case = refund()
    case["steps"]["nudge"] = {
        "kind": "task",
        "display": {"title": "Nudge"},
        "roles": ["support"],
        "repeatable": True,
        "outcomes": {"done": {"display": {"title": "Done"}}},
    }
    case["rules"] = {"chase": {"display": {"title": "Chase"}} | rule}
    return packed(case)


def timer(age: str) -> Package:
    """`chase` starts nudge `age` after review starts: a rule's timer (brief, D44)."""
    return chasing(
        {"on": {"after": age, "since": {"started": "review"}}, "then": {"start": ["nudge"]}}
    )


def sla(age: str) -> Package:
    """`chase` starts nudge if a run of review isn't done within `age` (brief, D46)."""
    return chasing({"sla": {"step": "review", "within": age}, "then": {"start": ["nudge"]}})


def reminder(*ages: str) -> Package:
    """`chase` starts nudge after each of `ages` while review is open (brief, D46)."""
    return chasing({"reminder": {"task": "review", "after": list(ages), "start": "nudge"}})


def approval_within(age: str) -> Package:
    """The releases guide's package, its plan's approval waiting at most `age`."""
    case, (plan,) = settling()
    plan["states"]["approve_refund"]["approval"]["timeout"] = age
    return packed(case, [plan])


def wait_within(age: str) -> Package:
    """The releases guide's package, its plan waiting at most `age` for a lead to confirm."""
    case, (plan,) = settling()
    plan["states"]["check_order"]["on"]["done"] = "confirm"
    plan["states"]["confirm"] = {
        "wait": {"outcomes": ["go"], "roles": ["support-lead"], "timeout": age},
        "on": {"go": "approve_refund", "timeout": "failed"},
    }
    return packed(case, [plan])


SAME = ": the same decisions; the history says"
PLAN_STATES = "plans.refund-order@1.states"


@pytest.mark.parametrize(
    ("before", "after", "line"),
    [
        (timer("2d"), timer("48h"), f"rules.chase.on.after: 2d -> 48h{SAME} 48h where it said 2d"),
        (sla("2d"), sla("48h"), f"rules.chase.sla.within: 2d -> 48h{SAME} 48h where it said 2d"),
        (
            reminder("1d", "2d"),
            reminder("24h", "48h"),
            (
                f"rules.chase.reminder.after: 1d, 2d -> 24h, 48h{SAME} 24h, 48h where it said "
                "1d, 2d, and names its rules chase_24h and chase_48h where it named chase_1d and "
                "chase_2d"
            ),
        ),
        (
            approval_within("2d"),
            approval_within("48h"),
            f"{PLAN_STATES}.approve_refund.approval.timeout: 2d -> 48h{SAME} 48h where it said 2d",
        ),
        (
            wait_within("60m"),
            wait_within("3600s"),
            f"{PLAN_STATES}.confirm.wait.timeout: 60m -> 3600s{SAME} 3600s where it said 60m",
        ),
    ],
)
def test_every_age_written_otherwise_is_no_verdict(
    before: Package, after: Package, line: str
) -> None:
    # The review of #49: every age the format holds is compared as a duration, as max_age is
    # (13c, choice 50): the same duration decides the same for every case.
    found = diff(before, after, CATALOG)
    assert found.changes == ()
    assert [str(rewritten) for rewritten in found.rewritten] == [f"rewritten  {line}"]
    assert found.summary() == "refund: no behaviour change; 1 written otherwise; no wording change"
    assert list(changed(before, after).behaviour) == [
        rewritten.path for rewritten in found.rewritten
    ]


def test_an_age_of_another_duration_is_still_not_proven() -> None:
    # What a timer or a timeout leads to decides whether sooner is looser: never judged.
    found = diff(timer("2d"), timer("3d"), CATALOG)
    assert [str(change) for change in found.changes] == [
        "not proven rules.chase.on.after: 2d -> 3d"
    ]
    found = diff(reminder("1d", "2d"), reminder("2d", "1d"), CATALOG)
    assert found.rewritten == ()


# --- Slice 1: every entry read (D45, as amended by D56) ------------------------------------------


def read(path: str, case: dict[str, Any], plans: list[dict[str, Any]] | None = None) -> str:
    """The reading of the entry at `path` in the package of `case` and `plans`, as printed."""
    found = packed(case, plans)
    reading = read_entry(path, found.case, found.plans, CATALOG)
    assert reading is not None
    return str(reading)


def test_a_call_step_reads_as_what_it_calls_and_when_it_starts() -> None:
    assert read("steps.pay", refund()) == (
        "pay calls payments.refund@2 (high risk, it writes), giving order_id from order_id and "
        "amount from approved_amount. It starts by itself once review is done, if "
        'review.outcome = "approve". One support-lead approves it, when approved_amount > 100.\n'
        "- Where approved_amount > 100 is false, it runs with no approval."
    )


def test_a_task_reads_as_who_answers_and_what_each_answer_does() -> None:
    assert read("steps.review", refund()) == (
        "review is a task for support, answered approve or reject. It starts by itself when the "
        "case opens. Answered approve, it sets approved_amount."
    )


def test_a_proposed_step_reads_as_who_proposes_it() -> None:
    case = refund()
    case["steps"]["call_customer"] |= {"automatic": False, "proposed_by": ["support"]}
    case["steps"]["call_customer"]["repeatable"] = True
    assert read("steps.call_customer", case) == (
        "call_customer is a task for support, answered called. It starts only when support "
        'proposes it, once pay is done, if pay.outcome = "declined"; it may run again when '
        "proposed."
    )


def test_a_field_reads_as_its_type_and_who_sees_it() -> None:
    assert read("fields.amount", refund()) == (
        "amount is a number, seen by support and support-lead."
    )
    case = refund()
    case["fields"]["amount"] |= {
        "visible_to": ["support"],
        "sensitive": True,
        "source": "untrusted:customer",
    }
    assert read("fields.amount", case) == (
        "amount is a number, seen by support. It is sensitive: wrapped, and never given to a "
        "workflow step. It is marked untrusted:customer, whoever writes it."
    )
    assert read("fields.order_id", refund()) == (
        "order_id is a reference to orders, seen by support and support-lead."
    )
    # A role the catalog doesn't register sees nothing (brief, D22): it isn't said to.
    audited = refund()
    audited["fields"]["amount"]["visible_to"] = ["support", "auditor"]
    assert read("fields.amount", audited) == "amount is a number, seen by support."


def test_an_event_a_close_reason_and_the_closing_read() -> None:
    case = refund()
    case["events"] = {
        "cancelled": {
            "display": {"title": "Cancelled"},
            "sent_by": {"system": "portal"},
            "payload": {
                "note": {
                    "type": "string",
                    "display": {"title": "Note"},
                    "source": "untrusted:customer",
                }
            },
        }
    }
    case["close_reasons"] = {"duplicate": {"display": {"title": "Dup"}, "roles": ["support"]}}
    assert read("events.cancelled", case) == (
        "cancelled is sent by portal, carrying note (a text, marked untrusted:customer)."
    )
    assert read("close_reasons.duplicate", case) == (
        "duplicate: support may close the case with it."
    )
    assert read("closing", case) == (
        "It closes when nothing is left to do. Its records may be forgotten, open or closed."
    )


def test_a_plans_states_read() -> None:
    case, plans = settling()
    assert read("plans.refund-order@1.states.approve_refund", case, plans) == (
        "approve_refund: one support-lead approves pay, within 48h. On approve, pay; on reject, "
        "failed; on timeout, failed."
    )
    assert read("plans.refund-order@1.states.check_order", case, plans) == (
        "check_order calls orders.lookup@1 (low risk, it reads), giving order_id from order_id. "
        "On done, approve_refund; on not_found, failed."
    )
    assert read("plans.refund-order@1.states.paid", case, plans) == (
        "paid ends the plan: succeeded."
    )


def test_a_shape_the_reader_doesnt_know_is_refused() -> None:
    # Fail closed: never read with a part left out (brief, D45).
    found = packed(refund())
    odd = found.case.model_copy(update={"steps": {"pay": object()}})
    with pytest.raises(ReadingRefused, match="can't read pay"):
        read_entry("steps.pay", odd, found.plans, CATALOG)


def test_readings_are_given_no_case_file() -> None:
    given = [p.annotation for p in inspect.signature(read_entry).parameters.values()]
    assert given == [str, CaseDefinition, Mapping[str, Plan], Catalog]


# Each entry clause, with the test that shows the engine doing what it says (brief, D56).
ENTRY_WITNESSED: set[str] = set()


def witness(clause: str) -> Callable[[Callable[[], None]], Callable[[], None]]:
    """Mark a test as `clause`'s witness: it reads an entry saying it, and runs a case where the
    engine does what it says."""

    def marked(test: Callable[[], None]) -> Callable[[], None]:
        ENTRY_WITNESSED.add(clause)
        return test

    return marked


def step_reading(case: dict[str, Any], step: str) -> EntryReading:
    """The reading of `step` in `case`."""
    reading = read_entry(f"steps.{step}", packed(case).case, {}, CATALOG)
    assert isinstance(reading, EntryReading)
    return reading


PEOPLE = {"ana": ["support"], "sam": ["support-lead"], "lee": ["support-lead"]}


def reviewed(amount: int) -> tuple[str, str, str, dict[str, int]]:
    """Ana approves the review, setting the amount approved."""
    return ("review", "approve", "ana", {"approved_amount": amount})


@witness("unapproved where its condition is false")
def test_a_step_runs_unapproved_where_its_approvals_condition_is_false() -> None:
    reading = step_reading(refund(), "pay")
    assert "unapproved where its condition is false" in reading.clauses
    # 50 is not over 100: the high-risk payment runs, and nobody is asked (brief, D11).
    run = run_case(
        refund(), file={"order_id": "ord-1", "amount": 50}, answers=[reviewed(50)], people=PEOPLE
    )
    assert run.reached("pay")
    assert not any(line.startswith("asked pay.approval") for line in run.history)


@witness("approvers are distinct people")
def test_several_approvers_are_distinct_and_one_rejection_rejects() -> None:
    four_eyes = json.loads(FOUR_EYES.read_text())
    reading = step_reading(four_eyes, "pay")
    assert "approvers are distinct people" in reading.clauses
    file = {"order_id": "ord-1", "amount": 20000}
    approved = ("pay.approval#1", "approve", "sam")
    with pytest.raises(AnswerRefused, match="sam has already approved pay.approval#1"):
        run_case(four_eyes, file=file, answers=[reviewed(20000), approved, approved], people=PEOPLE)
    rejected = run_case(
        four_eyes,
        file=file,
        answers=[reviewed(20000), approved, ("pay.approval#1", "reject", "lee")],
        people=PEOPLE,
    )
    assert not rejected.reached("pay") and rejected.waiting_for == []


@witness("the proposer never approves")
def test_whoever_proposes_a_run_never_approves_it() -> None:
    case = refund()
    case["steps"]["pay"] |= {"automatic": False, "proposed_by": ["support-lead"]}
    # Kept open for the proposal: with pay proposed, nothing is left to do once reviewed.
    case |= {
        "stays_open": True,
        "close_reasons": {"done": {"display": {"title": "Done"}, "roles": ["support"]}},
    }
    assert "the proposer never approves" in step_reading(case, "pay").clauses
    with pytest.raises(AnswerRefused, match="sam proposed pay, so cannot approve it"):
        run_case(
            case,
            file={"order_id": "ord-1", "amount": 250},
            answers=[reviewed(250), propose("pay", "sam"), ("pay.approval#1", "approve", "sam")],
            people=PEOPLE,
        )


def test_every_entry_clause_has_a_witness() -> None:
    assert ENTRY_WITNESSED == set(ENTRY_CLAUSES)


# --- Slice 2: the plain form renders the one change list ----------------------------------------


def plain_of(before: Package, after: Package, catalog: Catalog = CATALOG) -> str:
    """The plain form of the diff from `before` to `after`."""
    return plain(diff(before, after, catalog), before, after, catalog)


def one_lead() -> dict[str, Any]:
    """The four-eyes refund, back to one team lead."""
    case: dict[str, Any] = json.loads(FOUR_EYES.read_text())
    case["steps"]["pay"]["approval"]["count"] = 1
    return case


def test_the_plain_form_reads_each_entry_before_and_after() -> None:
    four_eyes = json.loads(FOUR_EYES.read_text())
    assert plain_of(packed(four_eyes), packed(one_lead())) == (
        "## refund: what changes\n"
        "\n"
        "1 behaviour change: 1 may loosen (1 looser, 0 not proven), 0 stricter; no wording "
        "change.\n"
        "\n"
        "### steps.pay\n"
        "\n"
        "- Before: pay calls payments.refund@2 (high risk, it writes), giving order\\_id from "
        "order\\_id and amount from approved\\_amount. It starts by itself once review is done, if "
        'review.outcome = "approve". Two people approve it, each a support-lead, when '
        "approved\\_amount &gt; 10000.\n"
        "  - Where approved\\_amount &gt; 10000 is false, it runs with no approval.\n"
        "  - The 2 approvers are different people, each someone else; one rejection rejects the "
        "approval.\n"
        "- After: pay calls payments.refund@2 (high risk, it writes), giving order\\_id from "
        "order\\_id and amount from approved\\_amount. It starts by itself once review is done, if "
        'review.outcome = "approve". One support-lead approves it, when approved\\_amount &gt; '
        "10000.\n"
        "  - Where approved\\_amount &gt; 10000 is false, it runs with no approval.\n"
        "- **Looser** (`steps.pay.approval.count`): 2 -&gt; 1 (one person approves pay, where two "
        "had to).\n"
    )


def test_every_verdict_word_is_its_changes() -> None:
    # The plain form judges nothing again: each change is said once, in its verdict's words, in
    # the change list's order (13c, choices 33 and 34).
    after = calling("payments.refund@3")
    after["steps"]["pay"]["approval"]["when"] = {">": [{"var": "approved_amount"}, 150]}
    after["fields"]["approved_amount"]["source"] = "untrusted:customer"
    found = diff(packed(refund()), packed(after), LOOSE)
    said = [
        line
        for line in plain(found, packed(refund()), packed(after), LOOSE).splitlines()
        if line.startswith("- **")
    ]
    words = {
        "looser": "Looser",
        "stricter": "Stricter",
        "not proven": "Changed, not proven either way (read it as possibly looser)",
    }
    # Each said as the change says it, shown, never rendered (brief, D56, as amended in 13e).
    assert said == [
        f"- **{words[change.verdict]}** (`{change.path}`): {text_of(change.said)}."
        for change in found.changes
    ]


def test_an_entry_added_reads_after_only() -> None:
    after = refund()
    after["close_reasons"] = {"duplicate": {"display": {"title": "Dup"}, "roles": ["support"]}}
    text = plain_of(packed(refund()), packed(after))
    assert (
        "### close\\_reasons.duplicate\n"
        "\n"
        "- After: duplicate: support may close the case with it.\n"
        "- **Looser** (`close_reasons.duplicate`): added: closed by support.\n"
    ) in text
    assert "- Before:" not in text


def test_written_otherwise_and_wording_are_listed_apart() -> None:
    before, after = fresh("1d"), fresh("24h")
    after["steps"]["lookup"]["display"]["title"] = "Find the order"
    text = plain_of(packed(before), packed(after))
    assert text.endswith(
        "### Written otherwise, the same decisions\n"
        "\n"
        "- `steps.lookup.max_age.order_id`: 1d -&gt; 24h: the same decisions; the history says 24 "
        "hours where it said 1 day.\n"
        "\n"
        "### Wording\n"
        "\n"
        '- `steps.lookup.display.title`: "Look the order up" -> "Find the order".\n'
    )


def test_a_plans_approved_activity_moved_says_the_known_limit() -> None:
    # 13b compares a plan's approval roles on their own leaf, never again for a new contract's
    # risk: the plain form says so where it applies (13c, choice 37).
    case, plans = settling()
    after = copy.deepcopy(plans)
    after[0]["states"]["pay"]["activity"] = "payments.refund@3"
    text = plain_of(packed(case, plans), packed(case, after), LOOSE)
    assert (
        "- Note: who may approve pay in the plan was compared by approve\\_refund's roles, not "
        "again for payments.refund@3's risk: read approve\\_refund's roles.\n"
    ) in text


def test_a_plain_form_is_given_no_case_file() -> None:
    given = [p.annotation for p in inspect.signature(plain).parameters.values()]
    assert given == [Diff, Package, Package, Catalog]
