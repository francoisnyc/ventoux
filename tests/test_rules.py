"""Rules: on a moment, when a condition holds, then act on the case (layer 11a).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md and docs/guides/cases.md, "Rules".
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import CaseState, Completed, Opened, StartWorkflow
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.policy import only_from
from ventoux.core.validate import Issue
from ventoux.testing import (
    CATALOG,
    START,
    AnswerRefused,
    ProposalRefused,
    RetryRefused,
    close,
    fake_kyc,
    finish,
    later,
    load_definition,
    propose,
    retry,
    run_case,
)

REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "omar": ["operations"]}


def with_rule(**rule: Any) -> dict[str, Any]:
    """The quickstart's refund with a `large` milestone and one rule, `flag_large`, changed by
    `rule`."""
    definition = copy.deepcopy(REFUND)
    definition["milestones"] = {"large": {"display": {"title": "Large refund"}}}
    definition["rules"] = {
        "flag_large": {
            "display": {"title": "Flag a large refund"},
            "on": "opened",
            "when": {">": [{"var": "amount"}, 1000]},
            "then": {"reach": ["large"]},
        }
        | rule
    }
    return definition


# --- Slice 0: the shape ---


def test_a_rule_reaching_an_undeclared_milestone_is_refused() -> None:
    with pytest.raises(CaseInvalid, match="^rules.flag_large.then.reach: lage is not a milestone$"):
        parse_case(with_rule(then={"reach": ["lage"]}))


def test_a_rule_named_like_a_step_or_a_milestone_is_refused() -> None:
    # A rule's firings are entries (`review#1`) beside step runs, so its name is its own.
    for name in ("review", "large"):
        definition = with_rule()
        definition["rules"] = {name: definition["rules"]["flag_large"]}
        with pytest.raises(CaseInvalid, match=f"^rules.{name}: a rule is not named like a "):
            parse_case(definition)


@pytest.mark.parametrize(
    ("on", "message"),
    [
        ({"started": "pai"}, "rules.flag_large.on.started: pai is not a step"),
        ({"reached": "lage"}, "rules.flag_large.on.reached: lage is not a milestone"),
    ],
)
def test_a_rule_on_what_the_case_doesnt_declare_is_refused(
    on: dict[str, str], message: str
) -> None:
    with pytest.raises(CaseInvalid, match=f"^{message}$"):
        parse_case(with_rule(on=on))


@pytest.mark.parametrize("on", [{"started": "pay"}, {"reached": "large"}, "opened"])
def test_a_rule_names_one_of_three_moments(on: object) -> None:
    parse_case(with_rule(on=on))  # the case opened, a step started, a milestone reached


@pytest.mark.parametrize(
    "on", ["closed", {"completed": "review"}, {"started": "pay", "reached": "large"}]
)
def test_an_unknown_moment_is_refused_in_one_line(on: object) -> None:
    # Four moments since 11b: `answered` is one (brief, D39).
    moments = '"opened", {"started": <step>}, {"reached": <milestone>} or {"answered": <task>}'
    with pytest.raises(CaseInvalid, match=f"^rules.flag_large.on: a moment is {moments}$"):
        parse_case(with_rule(on=on))


def test_a_rule_without_a_title_is_refused() -> None:
    # Every rule has a business title, as steps do: people read rules too (brief, D1).
    definition = with_rule()
    del definition["rules"]["flag_large"]["display"]
    with pytest.raises(CaseInvalid, match="^rules.flag_large.display: required$"):
        parse_case(definition)


@pytest.mark.parametrize(
    "then", [{"reach": []}, {}, {"reach": [], "start": []}, {"reach": [], "stop": []}]
)
def test_a_rule_that_does_nothing_is_refused(then: dict[str, Any]) -> None:
    # Since 11b a rule may start steps, and since 11c stop them, instead of reaching milestones
    # (brief, D39, D40): one that does none of them would do nothing, so a typo never hides a rule.
    with pytest.raises(
        CaseInvalid,
        match=(
            "^rules.flag_large.then: a rule reaches a milestone, starts a step or stops one, "
            "at least one$"
        ),
    ):
        parse_case(with_rule(then=then))


# --- 11b, slice 1: the shape of a rule that starts steps ---


def test_answered_names_a_task_and_start_a_step() -> None:
    # `answered` is a task's moment: an activity, a workflow or a plan finishing is not one, so a
    # loop of rules always comes round through a person (brief, D39).
    with pytest.raises(CaseInvalid, match="^rules.flag_large.on.answered: pay is not a task$"):
        parse_case(with_rule(on={"answered": "pay"}))
    with pytest.raises(CaseInvalid, match="^rules.flag_large.on.answered: revew is not a task$"):
        parse_case(with_rule(on={"answered": "revew"}))
    with pytest.raises(CaseInvalid, match="^rules.flag_large.then.start: lage is not a step$"):
        parse_case(with_rule(then={"start": ["lage"]}))
    parse_case(with_rule(on={"answered": "review"}, then={"start": ["pay"]}))
    parse_case(with_rule(then={"reach": ["large"], "start": ["pay"]}))


# --- 11c, slice 1: the shape of a rule that stops steps ---


def test_stop_names_a_step() -> None:
    # `stop` lists steps, and refuses any other name, so a stage named there later is a new
    # meaning, never a changed one (brief, D40; the doors note, row 1).
    with pytest.raises(CaseInvalid, match="^rules.flag_large.then.stop: large is not a step$"):
        parse_case(with_rule(then={"stop": ["large"]}))
    with pytest.raises(CaseInvalid, match="^rules.flag_large.then.stop: revew is not a step$"):
        parse_case(with_rule(then={"stop": ["revew"]}))
    parse_case(with_rule(then={"stop": ["review", "pay"]}))
    parse_case(with_rule(then={"reach": ["large"], "stop": ["review"]}))


def test_a_rule_cant_stop_and_start_one_step() -> None:
    # In one rule it would be a restart whose meaning depends on the step's kind: a task is
    # cancelled at once, so the start opens a new run; an activity runs on, so the start is
    # refused. Refused when read; a restart can come later, as an option (brief, D40).
    with pytest.raises(
        CaseInvalid,
        match=(
            "^rules.flag_large.then: review is both stopped and started: a rule can't restart a "
            "step; stop it here, and start it from another rule$"
        ),
    ):
        parse_case(with_rule(then={"stop": ["review", "pay"], "start": ["review"]}))
    parse_case(with_rule(then={"stop": ["review"], "start": ["pay"]}))


def only_a_rule_starts(**step: Any) -> dict[str, Any]:
    """The refund with a team lead's check of the review, `lead_check`, changed by `step`, which a
    rule starts once the review is approved."""
    definition = with_rule(
        on={"answered": "review"},
        when={"==": [{"var": "review.outcome"}, "approve"]},
        then={"start": ["lead_check"]},
    )
    definition["steps"]["lead_check"] = {
        "kind": "task",
        "display": {"title": "Check the approved review"},
        "roles": ["support-lead"],
        "automatic": False,
        "outcomes": {"ok": {"display": {"title": "The review is right"}}},
    } | step
    return definition


def test_a_step_only_a_rule_starts_is_proposed_by_nobody() -> None:
    # The one loosening of 11b: a step that doesn't start by itself, or is repeatable, needed
    # `proposed_by`, since nothing else could start it; a rule may now (brief, D39).
    parse_case(only_a_rule_starts())
    parse_case(only_a_rule_starts(repeatable=True))
    unstarted = only_a_rule_starts()
    del unstarted["rules"]
    with pytest.raises(CaseInvalid, match="a step that doesn't start by itself names proposed_by"):
        parse_case(unstarted)
    # `proposed_by` still names which people may propose it: with none, nobody may.
    with pytest.raises(ProposalRefused) as refused:
        run_case(
            only_a_rule_starts(),
            file={"order_id": "ord-1", "amount": 40},
            answers=[propose("lead_check", "sam")],
            people=PEOPLE,
        )
    assert str(refused.value) == "lead_check is started only by a rule: nobody proposes it"


# --- 11b, slice 2: starting ---

APPROVED_40 = ("review", "approve", "ana", {"approved_amount": 40})
SMALL = {"order_id": "ord-1", "amount": 40}


def test_a_start_whose_condition_is_false_runs_nothing() -> None:
    # The engine proposes; admission decides, the step's own `when` included. A start it refuses
    # is recorded, and nothing runs (brief, D39).
    definition = only_a_rule_starts(when={"==": [{"var": "amount"}, 0]})
    run = run_case(definition, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert (
        "flag_large#1 on answered review: lead_check not started: lead_check doesn't run now: "
        "amount = 0 is false"
    ) in run.history
    assert not any(line.startswith("started lead_check") for line in run.history)


def test_answered_fires_on_each_answer() -> None:
    # A milestone is reached once; a task is answered on each run, whatever the outcome. So a rule
    # on `answered` fires again when the review is sent back and answered again (brief, D39).
    definition = only_a_rule_starts(repeatable=True)
    definition["rules"]["flag_large"]["when"] = None
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    run = run_case(
        definition,
        file=SMALL,
        answers=[
            ("review", "reject", "ana"),
            propose("review", "ana"),
            ("review", "reject", "ana"),
        ],
        people=PEOPLE,
    )
    assert [line for line in run.history if line.startswith("flag_large#")] == [
        "flag_large#1 on answered review: starting lead_check",
        (
            "flag_large#2 on answered review: lead_check not started: lead_check is already "
            "running: lead_check#1"
        ),
    ]


def test_a_start_whose_requirements_arent_met_runs_nothing() -> None:
    run = run_case(
        only_a_rule_starts(requires=["pay"]), file=SMALL, answers=[APPROVED_40], people=PEOPLE
    )
    assert (
        "flag_large#1 on answered review: lead_check not started: lead_check requires pay, which "
        "hasn't completed"
    ) in run.history


def test_a_refused_start_is_recorded() -> None:
    # Running, or run and not repeatable: recorded, and nothing runs (brief, D39).
    definition = only_a_rule_starts()
    definition["rules"]["flag_large"]["when"] = None
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    reworked = [("review", "reject", "ana"), propose("review", "ana"), ("review", "reject", "ana")]
    running = run_case(definition, file=SMALL, answers=reworked, people=PEOPLE)
    assert (
        "flag_large#2 on answered review: lead_check not started: lead_check is already running: "
        "lead_check#1"
    ) in running.history
    checked = [*reworked[:2], ("lead_check", "ok", "sam"), reworked[2]]
    has_run = run_case(definition, file=SMALL, answers=checked, people=PEOPLE)
    assert (
        "flag_large#2 on answered review: lead_check not started: lead_check has run, and is not "
        "repeatable"
    ) in has_run.history
    # Waiting for its approval: a note answered while the refund's approval is open starts it.
    approval = with_rule(on={"answered": "note"}, then={"start": ["pay"]})
    approval["rules"]["flag_large"]["when"] = None
    approval["steps"]["note"] = {
        "kind": "task",
        "display": {"title": "Note the refund"},
        "roles": ["support"],
        "outcomes": {"noted": {"display": {"title": "Noted"}}},
    }
    waiting = run_case(
        approval,
        file=SMALL,
        answers=[("review", "approve", "ana", {"approved_amount": 250}), ("note", "noted", "ana")],
        people=PEOPLE,
    )
    assert (
        "flag_large#1 on answered note: pay not started: pay is waiting for its approval: "
        "pay.approval#1"
    ) in waiting.history
    # Waiting to start: Ana proposed pay on a stale status, which is being fetched again.
    fresh = copy.deepcopy(approval)
    fresh["steps"]["check_order"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    fresh["steps"]["pay"] |= {
        "automatic": False,
        "proposed_by": ["support"],
        "requires": ["check_order"],
        "when": {"==": [{"var": "check_order.status"}, "delivered"]},
        "max_age": {"check_order.status": "1d"},
    }
    del fresh["steps"]["pay"]["approval"]
    fresh |= closable(fresh, "support") | {"stays_open": True}
    proposed = run_case(
        fresh,
        file=SMALL,
        answers=[
            finish("check_order#1"),
            APPROVED_40,
            later("3d"),
            propose("pay", "ana"),
            ("note", "noted", "ana"),
        ],
        people=PEOPLE,
        held=["check_order"],
        activities={"orders.lookup@2": lambda inputs: {"status": "delivered"}},
    )
    assert (
        "flag_large#1 on answered note: pay not started: pay is already proposed, and waits for "
        "its facts to be fetched again"
    ) in proposed.history


def test_a_rule_starts_nothing_beside_a_failed_run() -> None:
    definition = with_rule(on={"answered": "review"}, then={"start": ["check_order"]})
    definition["rules"]["flag_large"]["when"] = None
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    definition["steps"]["check_order"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "automatic": False,
        "repeatable": True,
    }

    def down(inputs: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("orders system down")

    run = run_case(
        definition,
        file=SMALL,
        answers=[
            ("review", "reject", "ana"),
            propose("review", "ana"),
            ("review", "reject", "ana"),
        ],
        people=PEOPLE,
        activities={"orders.lookup@1": down},
    )
    assert (
        "flag_large#2 on answered review: check_order not started: check_order#1 needs "
        "attention: retry it, or close the case"
    ) in run.history


def test_a_start_that_cant_be_made_needs_attention() -> None:
    # Accepted by admission, and it can't be made: the run fails and waits for a person, as when
    # a step starts by itself (brief, D17) (brief, D39). A condition that can't be read:
    unreadable = only_a_rule_starts(when={">": [{"var": "approved_amount"}, 10]})
    unreadable["rules"]["flag_large"]["when"] = None
    run = run_case(unreadable, file=SMALL, answers=[("review", "reject", "ana")], people=PEOPLE)
    assert run.history[-1] == (
        "lead_check#1 failed: lead_check's condition approved_amount > 10 can't be evaluated: "
        "approved_amount has no value"
    )
    assert run.needs_attention == [run.history[-1].replace(" failed:", ":", 1)]
    # A contract the catalog lacks:
    missing = with_rule(on={"answered": "review"}, then={"start": ["lookup"]})
    missing["rules"]["flag_large"]["when"] = None
    missing["steps"]["lookup"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@9",
        "inputs": {"order_id": {"var": "order_id"}},
        "automatic": False,
    }
    run = run_case(missing, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert run.needs_attention == [
        (
            "lookup#1: orders.lookup@9 is not in the catalog. Registered: orders.lookup@1, "
            "orders.lookup@2. Use a registered version, or register this one first."
        )
    ]
    # An input refused: the letter would go to an address the customer typed.
    typed = with_rule(on={"answered": "review"}, then={"start": ["letter"]})
    typed["rules"]["flag_large"]["when"] = None
    typed["fields"]["email"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The address the customer typed"},
    }
    typed["steps"]["letter"] = {
        "kind": "activity",
        "display": {"title": "Draft a letter"},
        "activity": "letters.draft@2",
        "inputs": {"to_customer": {"var": "email"}, "template": "refund"},
        "automatic": False,
    }
    run = run_case(
        typed, file={**SMALL, "email": "c@example.com"}, answers=[APPROVED_40], people=PEOPLE
    )
    [refused] = run.needs_attention
    assert refused.startswith("letter#1: letters.draft@2 takes to_customer only from a system")
    # A stale fact nothing can fetch again: a person's answer. The retry would fail the same way,
    # so the line says so, as a person's proposal does (the second review).
    stale = only_a_rule_starts(max_age={"review.outcome": "1d"}, when={"exists": "review.outcome"})
    stale["steps"]["lead_check"] |= {"kind": "activity", "activity": "orders.lookup@1"}
    del stale["steps"]["lead_check"]["roles"], stale["steps"]["lead_check"]["outcomes"]
    stale["steps"]["lead_check"]["inputs"] = {"order_id": {"var": "order_id"}}
    stale["rules"]["flag_large"]["on"] = {"answered": "note"}
    stale["steps"]["note"] = {
        "kind": "task",
        "display": {"title": "Note the refund"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"noted": {"display": {"title": "Noted"}}},
    }
    stale |= closable(stale, "support") | {"stays_open": True}
    answers = [APPROVED_40, later("3d"), propose("note", "ana"), ("note", "noted", "ana")]
    run = run_case(stale, file=SMALL, answers=answers, people=PEOPLE)
    assert run.needs_attention == [
        (
            "lead_check#1: review.outcome was obtained 3 days ago, and lead_check needs it at most "
            "1 day old: it came from a person, so it can't be fetched again"
        )
    ]


def stale_notify() -> dict[str, Any]:
    """The refund with a look-up, and `notify`, started by a rule once the review is answered, on
    a status at most a day old."""
    definition = with_rule(on={"answered": "review"}, then={"start": ["notify"]})
    definition["rules"]["flag_large"]["when"] = None
    definition["steps"]["check_order"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    definition["steps"]["notify"] = {
        "kind": "activity",
        "display": {"title": "Look the order up again before the letter"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
        "when": {"==": [{"var": "check_order.status"}, "delivered"]},
        "max_age": {"check_order.status": "1d"},
        "automatic": False,
        "requires": ["check_order"],
    }
    return definition


def test_a_rules_start_never_waits_for_a_refresh() -> None:
    # A refresh lands with no person in it, so a rule's start that waited for one could bring a
    # loop round with nobody in between. It needs attention instead; an operator's retry fetches
    # the fact again, then the step runs (brief, D33) (brief, D39).
    definition = stale_notify()
    looked_up = {"orders.lookup@2": lambda inputs: {"status": "delivered"}}
    stale = [later("3d"), APPROVED_40]
    run = run_case(definition, file=SMALL, answers=stale, people=PEOPLE, activities=looked_up)
    assert run.needs_attention == [
        (
            "notify#1: check_order.status was obtained 3 days ago, and notify needs it at most 1 "
            "day old: a rule's start doesn't wait for it to be fetched again; retry it to fetch it"
        )
    ]
    assert not any(line.startswith("refreshing") for line in run.history)
    retried = run_case(
        definition,
        file=SMALL,
        answers=[*stale, retry("notify#1", "omar")],
        people=PEOPLE,
        activities=looked_up,
    )
    assert "refreshing check_order.status for notify: obtained 3 days ago, at most 1 day" in (
        retried.history
    )
    assert "notify#1 done, giving status from system:orders" in retried.history


def noticed_when_notify_starts(definition: dict[str, Any]) -> dict[str, Any]:
    """`definition` with a rule that marks `noticed` each time a run of `notify` starts."""
    definition["milestones"]["noticed"] = {"display": {"title": "Notify started"}}
    definition["rules"]["notice"] = {
        "display": {"title": "Notice the notification"},
        "on": {"started": "notify"},
        "then": {"reach": ["noticed"]},
    }
    return definition


def test_a_retried_run_that_never_started_fires_started_when_it_starts() -> None:
    # A run that failed before it started (a rule's start on a stale fact) starts for the first
    # time when the operator's retry schedules it: it is the same run, but it starts now, so
    # `started` fires then, once (brief, D38, as amended in 11b). Before the tutor review's fix,
    # it never fired, and a rule on it never heard of the run an operator rescued.
    definition = noticed_when_notify_starts(stale_notify())
    looked_up = {"orders.lookup@2": lambda inputs: {"status": "delivered"}}
    run = run_case(
        definition,
        file=SMALL,
        answers=[later("3d"), APPROVED_40, retry("notify#1", "omar")],
        people=PEOPLE,
        activities=looked_up,
    )
    assert "notify#1 failed" in " ".join(run.history)
    noticed = [line for line in run.history if line.startswith("notice#")]
    assert noticed == ["notice#1 on started notify: reaching noticed"]
    assert run.history.index(noticed[0]) > run.history.index(
        next(line for line in run.history if line.startswith("scheduled notify#1"))
    )


def test_a_retry_of_a_run_that_started_fires_nothing() -> None:
    # notify#1 was scheduled, so it started, and `started` fired; its activity then failed. The
    # operator's retry runs the same run again: it starts nothing again (brief, D26) (brief, D38).
    definition = noticed_when_notify_starts(stale_notify())
    tried: list[str] = []

    def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
        tried.append(inputs["order_id"])
        if len(tried) == 2:  # the first look-up is check_order's, the second notify's
            raise ConnectionError("the orders system is down")
        return {"status": "delivered"}

    run = run_case(
        definition,
        file=SMALL,
        answers=[APPROVED_40, retry("notify#1", "omar")],
        people=PEOPLE,
        activities={"orders.lookup@2": lookup},
    )
    assert "omar retried notify#1 as operations" in run.history
    assert run.history.count("notify#1 done, giving status from system:orders") == 1
    assert [line for line in run.history if line.startswith("notice#")] == [
        "notice#1 on started notify: reaching noticed"
    ]
    assert run.history.index("notice#1 on started notify: reaching noticed") < run.history.index(
        "omar retried notify#1 as operations"
    )


def test_a_rule_starts_a_step_once_per_decision() -> None:
    # Two rules on one moment both start lead_check: the second is refused by the guard, read
    # before admission's other refusals, so its line says why even while the run is open
    # (brief, D39).
    definition = only_a_rule_starts()
    definition["rules"]["again"] = definition["rules"]["flag_large"] | {
        "display": {"title": "Have it checked again"}
    }
    run = run_case(definition, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert [line for line in run.history if " on answered review: " in line] == [
        "flag_large#1 on answered review: starting lead_check",
        (
            "again#1 on answered review: lead_check not started: a rule already started it in this "
            "decision"
        ),
    ]


def with_goodwill(when: object = None) -> dict[str, Any]:
    """The refund, with a team lead's check of an approved review, and a goodwill refund a rule
    starts once the check is answered (when `when` holds), behind a team lead's approval."""
    definition = only_a_rule_starts(repeatable=True)
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    definition["rules"]["start_goodwill"] = {
        "display": {"title": "Make a goodwill refund"},
        "on": {"answered": "lead_check"},
        "then": {"start": ["goodwill"]},
    } | ({} if when is None else {"when": when})
    definition["steps"]["goodwill"] = {
        "kind": "activity",
        "display": {"title": "Refund a goodwill gesture"},
        "activity": "payments.refund@2",
        "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
        "approval": {"roles": ["support-lead"], "display": {"reason": "Goodwill needs a lead"}},
        "automatic": False,
    }
    return definition


CHECKED_OK = {"==": [{"var": "lead_check.outcome"}, "ok"]}
LEADS = {**PEOPLE, "lee": ["support-lead"]}


def test_whoever_a_rules_condition_read_cant_approve_what_it_started() -> None:
    # Sam's answer is what the rule's condition read: it decided that the goodwill refund runs,
    # so Sam can't approve it; Lee can (brief, D11) (brief, D25) (brief, D39).
    checked = [APPROVED_40, ("lead_check", "ok", "sam")]
    with pytest.raises(AnswerRefused) as refused:
        run_case(
            with_goodwill(CHECKED_OK),
            file=SMALL,
            answers=[*checked, ("goodwill.approval#1", "approve", "sam")],
            people=LEADS,
        )
    assert str(refused.value) == (
        "sam set lead_check.outcome, which decided that start_goodwill#1 started goodwill, so "
        "cannot approve it"
    )
    run = run_case(
        with_goodwill(CHECKED_OK),
        file=SMALL,
        answers=[*checked, ("goodwill.approval#1", "approve", "lee")],
        people=LEADS,
    )
    assert "goodwill#1 done, giving refund_id from untrusted:undeclared" in run.history


def test_the_answer_that_brought_the_moment_doesnt_exclude() -> None:
    # With no condition, the rule reads nothing: Sam's answer only brought the moment, as a person
    # whose step another requires does today (brief, D39). Sam may approve.
    run = run_case(
        with_goodwill(),
        file=SMALL,
        answers=[
            APPROVED_40,
            ("lead_check", "ok", "sam"),
            ("goodwill.approval#1", "approve", "sam"),
        ],
        people=LEADS,
    )
    assert "goodwill#1 done, giving refund_id from untrusted:undeclared" in run.history


def test_a_rules_record_outlives_the_case_file_changing() -> None:
    # The rule remembers nothing, so the run keeps what its condition read: Lee answers the check
    # again while the goodwill approval is open, and lead_check.outcome is Lee's now; Sam, whose
    # answer decided it, is still refused (brief, D38) (brief, D39).
    with pytest.raises(AnswerRefused) as refused:
        run_case(
            with_goodwill(CHECKED_OK),
            file=SMALL,
            answers=[
                APPROVED_40,
                ("lead_check", "ok", "sam"),
                propose("review", "ana"),
                APPROVED_40,
                ("lead_check", "ok", "lee"),
                ("goodwill.approval#1", "approve", "sam"),
            ],
            people=LEADS,
        )
    assert str(refused.value).startswith("sam set lead_check.outcome, which decided that")


# --- 11b, slice 3: untrusted data can't choose what is sent (option a) ---


def with_welcome(when: dict[str, Any]) -> dict[str, Any]:
    """The refund with the KYC check, and a welcome letter drafted to the address the case was
    opened with, when `when` holds."""
    definition = with_kyc_rule({">": [{"var": "kyc.risk_score"}, 70]})
    definition["fields"]["email"] = {"type": "string", "display": {"title": "Customer's email"}}
    definition["steps"]["welcome"] = {
        "kind": "activity",
        "display": {"title": "Draft a welcome letter"},
        "activity": "letters.draft@2",
        "requires": ["checked"],
        "when": when,
        "inputs": {"to_customer": {"var": "email"}, "template": "welcome"},
    }
    return definition


def welcome_file() -> dict[str, Any]:
    """The KYC check's first values, and the customer's address."""
    return {**KYC_FILE, "email": "c-1@example.com"}


SAYS_SEND = {"==": [{"var": "kyc.analyst_notes"}, "send welcome"]}


def notes_say_send(inputs: dict[str, Any]) -> dict[str, Any]:
    """The KYC workflow, with a model's notes saying to send the letter."""
    return fake_kyc(inputs) | {"analyst_notes": "send welcome"}


def test_an_untrusted_condition_cant_choose_what_is_sent() -> None:
    # Each input is trusted, but the model's notes chose that the letter is sent: the untrusted
    # sources the condition read are checked against each input's policy, apart from what the
    # input reads, and the run fails naming the field and source, never the value
    # (brief, D38) (brief, D39).
    run = run_case(
        with_welcome(SAYS_SEND),
        file=welcome_file(),
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
    )
    assert run.needs_attention == [
        (
            "welcome#1: letters.draft@2 takes to_customer only from a system or a person, never from "
            "untrusted data, and welcome's condition reads kyc.analyst_notes (untrusted:llm)"
        )
    ]
    assert not any(line.startswith("scheduled welcome") for line in run.history)
    assert not any("send welcome" in line for line in run.history)


def test_a_rules_untrusted_condition_cant_choose_what_is_sent() -> None:
    # A rule that only starts steps acts on untrusted data: what its condition read is kept with
    # the run, and counts for the started step's input policies (brief, D38) (brief, D39).
    definition = with_welcome(SAYS_SEND)
    del definition["steps"]["welcome"]["when"]
    definition["steps"]["welcome"]["automatic"] = False
    definition["rules"]["send_welcome"] = {
        "display": {"title": "Send a welcome letter"},
        "on": {"reached": "checked"},
        "when": SAYS_SEND,
        "then": {"start": ["welcome"]},
    }
    run = run_case(
        definition,
        file=welcome_file(),
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
    )
    assert "send_welcome#1 on reached checked: starting welcome" in run.history
    assert run.needs_attention == [
        (
            "welcome#1: letters.draft@2 takes to_customer only from a system or a person, never from "
            "untrusted data, and send_welcome#1's condition, which started welcome, reads "
            "kyc.analyst_notes (untrusted:llm)"
        )
    ]


class RecordInput(BaseModel):
    amount: Annotated[Decimal, only_from("opener")]  # only an amount the opening system gave


class RecordOutput(BaseModel):
    entry_id: str


def with_ledger() -> Catalog:
    """The development catalog, and `ledger.record@1`, taking only an amount the opener gave."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register(
        ActivityContract(
            name="ledger.record",
            version=1,
            input=RecordInput,
            output=RecordOutput,
            risk="low",
            effect="compute",
            timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
            retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
            idempotency_key=None,
            outcomes=[],
            display=Display(title="Record", description="Record an amount"),
        )
    )
    return catalog


def recording(amount: Any) -> dict[str, Any]:
    """The refund, recording `amount` in the ledger once the review approves: its `when` reads
    Ana's answer."""
    definition = copy.deepcopy(REFUND)
    definition["steps"]["record"] = {
        "kind": "activity",
        "display": {"title": "Record the refund"},
        "activity": "ledger.record@1",
        "requires": ["review"],
        "when": {"==": [{"var": "review.outcome"}, "approve"]},
        "inputs": {"amount": amount},
    }
    return definition


LEDGER = {"ledger.record@1": lambda inputs: {"entry_id": "led-1"}}


def test_a_trusted_condition_changes_nothing() -> None:
    # Only untrusted sources count: the condition read Ana's answer, a person's, so the amount the
    # opener gave still goes to an input that takes it only from the opener (brief, D39).
    run = run_case(
        recording({"var": "amount"}),
        file=SMALL,
        answers=[APPROVED_40],
        people=PEOPLE,
        catalog=with_ledger(),
        activities=LEDGER,
    )
    assert "record#1 done, giving entry_id from untrusted:undeclared" in run.history


def test_a_condition_never_vouches_for_a_literal() -> None:
    # The check is separate: a value written in the definition comes from no system, whatever
    # the condition read, and `only_from` refuses it as before (brief, D39). Merged, the
    # condition's sources would have credited it to Ana.
    run = run_case(
        recording(Decimal(40)),
        file=SMALL,
        answers=[APPROVED_40],
        people=PEOPLE,
        catalog=with_ledger(),
        activities=LEDGER,
    )
    [failed] = run.needs_attention
    assert failed.startswith("record#1: ledger.record@1 takes amount only from opener")


def test_a_rule_that_cant_decide_starts_nothing() -> None:
    # A rule that reaches a milestone decides, so on untrusted data it doesn't act at all, its
    # starts included (brief, D38) (brief, D39).
    definition = with_welcome(SAYS_SEND)
    definition["rules"]["flag_high_risk"] |= {
        "when": SAYS_SEND,
        "then": {"reach": ["high_risk"], "start": ["welcome"]},
    }
    run = run_case(
        definition,
        file=welcome_file(),
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
    )
    assert (
        "flag_high_risk#1 on reached checked: reaches and starts nothing: its condition reads "
        "kyc.analyst_notes, from untrusted:llm, and untrusted data can't decide"
    ) in run.history
    assert "reached high_risk" not in run.history


def test_an_untrusted_approval_condition_asks_anyway() -> None:
    # Untrusted data may add an approval, never remove one: an approval whose condition read it
    # is asked whatever it gave, saying why (brief, D11) (brief, D39).
    definition = copy.deepcopy(REFUND)
    definition["fields"]["approved_amount"]["source"] = "untrusted:customer"
    run = run_case(definition, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert run.history[-1] == (
        "asked pay.approval#1: approval of pay by support-lead: its condition reads "
        "approved_amount, from untrusted:customer, and untrusted data can't remove an approval"
    )
    # Read first: one that can't be read stops the step, never asks in silence (fail closed).
    unreadable = copy.deepcopy(REFUND)
    unreadable["fields"]["bonus"] = {
        "type": "number",
        "source": "untrusted:customer",
        "display": {"title": "A bonus the customer asks for"},
    }
    unreadable["steps"]["pay"]["approval"]["when"] = {">": [{"var": "bonus"}, 100]}
    run = run_case(unreadable, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert run.needs_attention == [
        "pay#1: pay's approval condition bonus > 100 can't be evaluated: bonus has no value"
    ]


def test_an_unrecognised_condition_source_counts_as_untrusted() -> None:
    # Fail closed: a source the engine doesn't recognise counts as untrusted, never as trusted.
    # A value's sources are only ever stamped by the engine; here one is changed by hand, to an
    # origin Ventoux has never heard of, and the letter is still refused (brief, D39).
    definition = with_welcome({"==": [{"var": "region"}, "north"]})
    definition["fields"]["region"] = {"type": "string", "display": {"title": "Region"}}
    case = parse_case(definition)
    opened, commands = decide(
        case,
        CATALOG,
        CaseState("t"),
        Opened({**welcome_file(), "amount": Decimal(40), "region": "north"}, None, at=START),
    )
    [kyc] = [command for command in commands if isinstance(command, StartWorkflow)]
    opened.sources["region"] = frozenset({"rumour:somewhere"})
    done, _ = decide(case, CATALOG, opened, Completed(kyc.entry, fake_kyc(kyc.inputs), at=START))
    assert done.history[-1] == (
        "welcome#1 failed: letters.draft@2 takes to_customer only from a system or a person, "
        "never from untrusted data, and welcome's condition reads region (rumour:somewhere)"
    )


def test_an_unset_field_in_a_steps_condition_counts_its_writers() -> None:
    # The welcome letter is drafted when the customer left no notes: a field nobody has set, and
    # untrusted whoever writes it. It counts what its writers could give (brief, D39).
    definition = with_welcome({"!": [{"exists": "notes"}]})
    definition["fields"]["notes"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The customer's notes"},
    }
    run = run_case(definition, file=welcome_file(), answers=[], people=PEOPLE)
    assert run.needs_attention == [
        (
            "welcome#1: letters.draft@2 takes to_customer only from a system or a person, never from "
            "untrusted data, and welcome's condition reads notes (untrusted:customer)"
        )
    ]


# --- 11b, from the code review ---


def closing_on_checked(rules: dict[str, Any]) -> dict[str, Any]:
    """The refund closing on `checked`, with a look-up that requires it, and `rules`."""
    definition = copy.deepcopy(REFUND)
    definition["milestones"] = {"checked": {"display": {"title": "Checked"}}}
    definition["closes_when"] = ["checked"]
    definition["steps"]["lookup"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "automatic": False,
        "requires": ["checked"],
    }
    definition["rules"] = rules
    return definition


def test_a_rule_starts_nothing_once_the_case_closes() -> None:
    # Once every closes_when milestone is reached, nothing new starts (layer 8b), a rule's start
    # included, even one decided on the same moment (brief, D34) (brief, D39). Validation said
    # lookup never runs; before the review's fix, a rule ran it, and the case was flagged.
    one = {
        "wrap": {
            "display": {"title": "Wrap up"},
            "on": {"answered": "review"},
            "then": {"reach": ["checked"], "start": ["lookup"]},
        }
    }
    two = {
        "begin": {
            "display": {"title": "Look it up"},
            "on": {"answered": "review"},
            "then": {"start": ["lookup"]},
        },
        "finish": {
            "display": {"title": "Checked"},
            "on": {"answered": "review"},
            "then": {"reach": ["checked"]},
        },
    }
    for rules, entry in ((one, "wrap#1"), (two, "begin#1")):
        definition = closing_on_checked(rules)
        assert [i.code for i in issues(definition)] == ["NEVER_RUNS"]
        run = run_case(definition, file=SMALL, answers=[("review", "reject", "ana")], people=PEOPLE)
        assert (
            f"{entry} on answered review: lookup not started: checked is reached, so the case "
            "closes and nothing new starts"
        ) in run.history
        assert not any(line.startswith("scheduled lookup") for line in run.history)
        assert run.closed and run.flags == []
    # A rule retried after it failed reaches checked, and the case begins closing before any
    # start is decided: its start is recorded too, never dropped in silence (the second review).
    retried = closing_on_checked(copy.deepcopy(one))
    retried["rules"]["wrap"]["when"] = {"==": [{"var": "note.outcome"}, "noted"]}
    retried["steps"]["note"] = {
        "kind": "task",
        "display": {"title": "Note the refund"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"noted": {"display": {"title": "Noted"}}},
    }
    answers = [
        ("review", "reject", "ana"),
        propose("note", "ana"),
        ("note", "noted", "ana"),
        retry("wrap#1", "omar"),
    ]
    run = run_case(retried, file=SMALL, answers=answers, people=PEOPLE)
    assert run.history[run.history.index("omar retried wrap#1 as operations") + 1 :] == [
        "wrap#1 on answered review: reaching checked",
        "reached checked",
        (
            "wrap#1 on answered review: lookup not started: checked is reached, so the case "
            "closes and nothing new starts"
        ),
        "closed: checked reached",
    ]


def test_a_failed_rule_holding_the_close_is_named() -> None:
    # checked is reached, and a rule on the same answer fails: the close waits for it (brief, D26)
    # (brief, D38), and what is refused meanwhile says which failed run or rule it waits for.
    # Before the third review's fix, a failed rule alone made it "closes once nothing are
    # retried".
    definition = closing_on_checked(
        {
            "note_it": {
                "display": {"title": "Note a large refund"},
                "on": {"answered": "review"},
                "when": {">": [{"var": "approved_amount"}, 1000]},
                "then": {"reach": ["checked"]},
            },
            "begin": {
                "display": {"title": "Look it up"},
                "on": {"answered": "review"},
                "then": {"start": ["lookup"]},
            },
            "finish": {
                "display": {"title": "Checked"},
                "on": {"answered": "review"},
                "then": {"reach": ["checked"]},
            },
        }
    )
    definition["steps"]["lookup"]["proposed_by"] = ["support"]
    held = (
        "checked is reached, so the case closes once note_it#1 is retried, or a person closes it: "
        "nothing new starts"
    )
    run = run_case(definition, file=SMALL, answers=[("review", "reject", "ana")], people=PEOPLE)
    assert f"begin#1 on answered review: lookup not started: {held}" in run.history
    with pytest.raises(ProposalRefused) as refused:
        run_case(
            definition,
            file=SMALL,
            answers=[("review", "reject", "ana"), propose("lookup", "ana")],
            people=PEOPLE,
        )
    assert str(refused.value) == held


def welcome_on_a_fresh_status() -> dict[str, Any]:
    """The welcome letter started by a rule on the model's notes, once the review is answered,
    drafted only on an order status at most a day old."""
    definition = with_welcome({"==": [{"var": "check_order.status"}, "delivered"]})
    definition["steps"]["welcome"] |= {
        "automatic": False,
        "requires": ["checked", "check_order"],
        "max_age": {"check_order.status": "1d"},
    }
    definition["steps"]["check_order"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@2",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    definition["rules"]["send_welcome"] = {
        "display": {"title": "Send a welcome letter"},
        "on": {"answered": "review"},
        "when": SAYS_SEND,
        "then": {"start": ["welcome"]},
    }
    return definition


def test_a_rules_record_survives_a_start_that_fails() -> None:
    # A rule's start that fails before its run starts (a stale fact, a condition not readable
    # yet) is retried by an operator: what the rule read is kept with the run until it starts,
    # so it still counts for the inputs and still excludes (brief, D38) (brief, D39). Before the
    # review's fix, the retry drafted the letter the model's notes chose.
    run = run_case(
        welcome_on_a_fresh_status(),
        file=welcome_file(),
        answers=[later("3d"), ("review", "reject", "ana"), retry("welcome#1", "omar")],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
        activities={"orders.lookup@2": lambda inputs: {"status": "delivered"}},
    )
    assert "omar retried welcome#1 as operations" in run.history
    assert not any(line.startswith("scheduled welcome") for line in run.history)
    assert run.needs_attention == [
        (
            "welcome#1: letters.draft@2 takes to_customer only from a system or a person, never "
            "from untrusted data, and send_welcome#1's condition, which started welcome, reads "
            "kyc.analyst_notes (untrusted:llm)"
        )
    ]
    # The goodwill refund fails on a condition not readable yet: retried once the note is in,
    # Sam, whose check the rule read, still can't approve it.
    definition = with_goodwill(CHECKED_OK)
    definition["steps"]["note"] = {
        "kind": "task",
        "display": {"title": "Note the refund"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"noted": {"display": {"title": "Noted"}}},
    }
    definition["steps"]["goodwill"]["when"] = {"==": [{"var": "note.outcome"}, "noted"]}
    noted = [
        APPROVED_40,
        ("lead_check", "ok", "sam"),
        propose("note", "ana"),
        ("note", "noted", "ana"),
        retry("goodwill#1", "omar"),
    ]
    with pytest.raises(AnswerRefused) as refused:
        run_case(
            definition,
            file=SMALL,
            answers=[*noted, ("goodwill.approval#1", "approve", "sam")],
            people=LEADS,
        )
    assert str(refused.value) == (
        "sam set lead_check.outcome, which decided that start_goodwill#1 started goodwill, so "
        "cannot approve it"
    )


def test_a_rule_on_the_opening_that_may_fail_keeps_the_case_open() -> None:
    # A rule on the opening whose condition can't be read fails, and the case waits for a
    # person instead of closing, whatever the check says of the value it reads: the opener may
    # leave a field out, and a value read only once a dead step ran is never set. So a condition
    # there makes CLOSES_AT_OPENING unproven (brief, D34). A gap from 11a, found in 11b's review.
    unopened = with_rule()
    unopened["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    assert not [i for i in issues(unopened) if i.code == "CLOSES_AT_OPENING"]
    run = run_case(unopened, file={"order_id": "ord-1"}, answers=[], people=PEOPLE)
    assert not run.closed
    assert run.needs_attention == [
        "flag_large#1: flag_large's condition amount > 1000 can't be evaluated: amount has no value"
    ]
    dead = copy.deepcopy(REFUND)
    dead["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    dead["milestones"] = {
        "noted": {"display": {"title": "Noted"}},
        "never": {"display": {"title": "Never reached"}},
    }
    dead["steps"]["call_customer"]["requires"] = ["never"]
    dead["rules"] = {
        "note_call": {
            "display": {"title": "Note the call"},
            "on": "opened",
            "when": {"==": [{"var": "call_customer.outcome"}, "called"]},
            "then": {"reach": ["noted"]},
        }
    }
    assert [i.code for i in issues(dead)] == ["NEVER_RUNS"]
    run = run_case(dead, file=SMALL, answers=[propose("review", "ana")], people=PEOPLE)
    assert run.waiting_for == ["review by support"] and not run.closed


def test_a_rules_start_sees_the_approvals_that_stand() -> None:
    # The review is answered again with a new amount: the goodwill refund's open approval reads it,
    # so it is withdrawn in this decision, before the rule's start is decided, which then asks
    # again (brief, D25) (brief, D39). Before the second review's fix, the start was refused by
    # the approval being withdrawn, and nothing was asked.
    definition = with_goodwill()
    del definition["rules"]["flag_large"], definition["steps"]["lead_check"]
    definition["rules"]["start_goodwill"]["on"] = {"answered": "review"}
    definition["steps"]["goodwill"]["inputs"]["amount"] = {"var": "approved_amount"}
    reworked = ("review", "approve", "ana", {"approved_amount": 30})
    run = run_case(
        definition,
        file=SMALL,
        answers=[APPROVED_40, propose("review", "ana"), reworked],
        people=LEADS,
    )
    second = run.history.index("review#2 done")
    assert run.history[second + 1 : second + 4] == [
        "withdrew goodwill.approval#1: approved_amount changed",
        "start_goodwill#2 on answered review: starting goodwill",
        "asked goodwill.approval#2: approval of goodwill by support-lead",
    ]


def test_a_new_proposal_replaces_a_withdrawn_one() -> None:
    # The rule's start of the goodwill refund waits for its approval, which is withdrawn when the
    # amount changes; the start is over. Ana then proposes it herself: hers is the proposal now,
    # and Sam, whose check the rule read, may approve it (brief, D25) (brief, D39). Before the
    # second review's fix, the rule's record stayed, and refused Sam naming a rule that no longer
    # proposed anything.
    definition = with_goodwill(CHECKED_OK)
    definition["steps"]["goodwill"]["inputs"]["amount"] = {"var": "approved_amount"}
    definition["steps"]["goodwill"]["proposed_by"] = ["support"]
    run = run_case(
        definition,
        file=SMALL,
        answers=[
            APPROVED_40,
            ("lead_check", "ok", "sam"),
            propose("review", "ana"),
            ("review", "approve", "ana", {"approved_amount": 30}),
            propose("goodwill", "ana"),
            ("goodwill.approval#2", "approve", "sam"),
        ],
        people=LEADS,
    )
    assert "withdrew goodwill.approval#1: approved_amount changed" in run.history
    assert "sam answered goodwill.approval#2 approve as support-lead" in run.history
    assert run.reached("goodwill")
    # The other way round: Sam proposes it, his approval is withdrawn, and then the rule starts
    # it, on Lee's check. The rule's is the proposal now, and Sam may approve it.
    run = run_case(
        definition,
        file=SMALL,
        answers=[
            APPROVED_40,
            propose("goodwill", "sam"),
            propose("review", "ana"),
            ("review", "approve", "ana", {"approved_amount": 30}),
            ("lead_check", "ok", "lee"),
            ("goodwill.approval#2", "approve", "sam"),
        ],
        people=LEADS,
    )
    assert "withdrew goodwill.approval#1: approved_amount changed" in run.history
    assert "start_goodwill#1 on answered lead_check: starting goodwill" in run.history
    assert "sam answered goodwill.approval#2 approve as support-lead" in run.history


def failing_goodwill_once() -> dict[str, Any]:
    """The refund's payments, the goodwill refund's first run failing once."""
    failed: list[str] = []

    def refund(inputs: dict[str, Any]) -> dict[str, Any]:
        if inputs["idempotency_key"].endswith("goodwill#1") and not failed:
            failed.append(inputs["idempotency_key"])
            raise ConnectionError("the provider is down")
        return {"refund_id": "refund-ord-1"}

    return {"payments.refund@2": refund}


def test_a_retried_run_keeps_who_may_not_approve_it() -> None:
    # A retry is the same run (brief, D26): whoever could not approve it still can't, though its
    # approval is asked only now, when the rejected review makes it needed. Sam checked the review,
    # which decided that the rule started it (brief, D39); in the second case, he proposed it
    # (brief, D25). Before the third review's fix, a retried activity forgot both.
    rejected = [propose("review", "ana"), ("review", "reject", "ana"), retry("goodwill#1", "omar")]
    by_a_rule = with_goodwill(CHECKED_OK)
    by_a_rule["steps"]["goodwill"]["approval"]["when"] = {
        "==": [{"var": "review.outcome"}, "reject"]
    }
    proposed = copy.deepcopy(by_a_rule)
    del proposed["rules"]["start_goodwill"]
    proposed["steps"]["goodwill"]["proposed_by"] = ["support"]
    proposed |= closable(proposed, "support") | {"stays_open": True}
    cases: list[tuple[dict[str, Any], list[Any], str]] = [
        (
            by_a_rule,
            [("lead_check", "ok", "sam")],
            (
                "sam set lead_check.outcome, which decided that start_goodwill#1 started goodwill, so "
                "cannot approve it"
            ),
        ),
        (
            proposed,
            [("lead_check", "ok", "lee"), propose("goodwill", "sam")],
            "sam proposed goodwill, so cannot approve it",
        ),
    ]
    for definition, started, refusal in cases:
        with pytest.raises(AnswerRefused) as refused:
            run_case(
                definition,
                file=SMALL,
                answers=[
                    APPROVED_40,
                    *started,
                    *rejected,
                    ("goodwill.approval#1", "approve", "sam"),
                ],
                people=LEADS,
                activities=failing_goodwill_once(),
            )
        assert str(refused.value) == refusal


# --- 11b, slice 4: validation ---


def starting_at_opening(step: str, **rule: Any) -> dict[str, Any]:
    """The guide's rework loop, with a rule `start_<step>` that starts `step` as the case opens,
    changed by `rule`."""
    definition = guide_rework()
    definition["rules"][f"start_{step}"] = {
        "display": {"title": "Start it at once"},
        "on": "opened",
        "then": {"start": [step]},
    } | rule
    return definition


def test_a_start_refused_every_time_is_never_starts() -> None:
    # A rule on the opening fires once, before anything is done: a step requiring what the opening
    # can't reach is refused, and the rule never fires again. Only proven when its condition can't
    # fail: a failed firing is retried later, on the case file as it is then (brief, D34)
    # (brief, D39).
    assert [i for i in issues(starting_at_opening("pay")) if i.code == "NEVER_STARTS"] == [
        Issue(
            "rules.start_pay.then.start",
            "NEVER_STARTS",
            "start_pay can never start pay: it fires on opened, and pay requires lead_checked, "
            "which nothing can reach by then: start it on a later moment, or remove the "
            "requirement",
        )
    ]
    run = run_case(starting_at_opening("pay"), file=SMALL, answers=[], people=PEOPLE)
    assert [line for line in run.history if line.startswith("start_pay#1")] == [
        (
            "start_pay#1 on opened: pay not started: pay requires lead_checked, which hasn't "
            "been reached"
        )
    ]
    may_fail = starting_at_opening("pay", when={"exists": "approved_amount"})
    assert not [i for i in issues(may_fail) if i.code == "NEVER_STARTS"]
    # A step whose every start is refused never runs, and says which rule can't start it.
    only_at_opening = starting_at_opening("lead_check")
    del only_at_opening["rules"]["check_review"]
    only_at_opening["steps"]["lead_check"]["requires"] = ["review"]
    assert [i for i in issues(only_at_opening) if i.path.startswith("steps.lead_check")] == [
        Issue(
            "steps.lead_check",
            "NEVER_RUNS",
            "lead_check can never run: it starts only when a rule starts it, and start_lead_check "
            "can never start it: fix start_lead_check first",
        )
    ]
    # Or the rule fires on the step's own run, which isn't repeatable: refused every time too.
    own_run = guide_rework()
    own_run["rules"]["again"] = {
        "display": {"title": "Pay again"},
        "on": {"started": "pay"},
        "then": {"start": ["pay"]},
    }
    assert [i for i in issues(own_run) if i.code == "NEVER_STARTS"] == [
        Issue(
            "rules.again.then.start",
            "NEVER_STARTS",
            "again can never start pay: it fires on started pay, while pay is running: start it "
            "on another moment",
        )
    ]
    # Unless its condition may fail and the step is repeatable: the retry may come once the step
    # is done.
    may_retry = guide_rework()
    may_retry["rules"]["again"] = {
        "display": {"title": "Review it again"},
        "on": {"started": "review"},
        "when": {">": [{"var": "approved_amount"}, 10]},
        "then": {"start": ["review"]},
    }
    assert not [i for i in issues(may_retry) if i.code == "NEVER_STARTS"]
    # Each half alone still proves it: a condition on a step that can't run again, or no
    # condition on one that can.
    once = copy.deepcopy(own_run)
    once["rules"]["again"]["when"] = {">": [{"var": "approved_amount"}, 10]}
    no_condition = copy.deepcopy(may_retry)
    del no_condition["rules"]["again"]["when"]
    for proven, step in ((once, "pay"), (no_condition, "review")):
        assert [i.message for i in issues(proven) if i.code == "NEVER_STARTS"] == [
            (
                f"again can never start {step}: it fires on started {step}, while {step} is running: "
                "start it on another moment"
            )
        ]
    # On its own answer, a step that isn't repeatable has run by then.
    answered = with_rule(on={"answered": "review"}, when=None, then={"start": ["review"]})
    del answered["milestones"]
    assert [i for i in issues(answered) if i.code == "NEVER_STARTS"] == [
        Issue(
            "rules.flag_large.then.start",
            "NEVER_STARTS",
            "flag_large can never start review: it fires on answered review, once review has "
            "run, and review is not repeatable: make review repeatable, or start it on another "
            "moment",
        )
    ]
    run = run_case(answered, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert (
        "flag_large#1 on answered review: review not started: review has run, and is not repeatable"
    ) in run.history


def test_a_step_started_only_on_its_own_moment_gets_one_issue() -> None:
    # Nothing starts lead_check but a rule on its own answer: it never runs, and the rule never
    # fires, for one cause. One issue names the circle, with no NEVER_FIRES beside it (brief, D39).
    circle = only_a_rule_starts()
    circle["rules"]["flag_large"] |= {"on": {"answered": "lead_check"}, "when": None}
    del circle["milestones"]  # `large`, which nothing reaches here
    assert issues(circle) == [
        Issue(
            "steps.lead_check",
            "NEVER_RUNS",
            "lead_check can never run: it starts only when a rule starts it, and flag_large fires "
            "on answered lead_check, which comes only once lead_check has run: start it from a "
            "rule on another moment",
        )
    ]
    run = run_case(circle, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert not any(line.startswith(("flag_large", "started lead_check")) for line in run.history)


def test_a_step_a_rule_on_the_opening_starts_keeps_the_case_open() -> None:
    # The review starts only when proposed, and nothing starts by itself, but a rule on the
    # opening starts it: the case waits for it instead of closing at once (brief, D39).
    definition = copy.deepcopy(REFUND)
    definition["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    definition["rules"] = {
        "ask_review": {
            "display": {"title": "Ask for a review"},
            "on": "opened",
            "then": {"start": ["review"]},
        }
    }
    assert issues(definition) == []
    run = run_case(definition, file=SMALL, answers=[], people=PEOPLE)
    assert run.waiting_for == ["review by support"] and not run.closed


def test_answered_waits_for_its_task() -> None:
    # A task's answer comes once the task has ended: a rule on it reads its outcome set, as a step
    # requiring the task does (brief, D39). Before, the check read it as the opening.
    assert issues(guide_rework()) == []
    # What only one of its outcomes sets may still be unset.
    amount = guide_rework()
    amount["rules"]["check_review"]["when"] = {">": [{"var": "approved_amount"}, 100]}
    assert issues(amount) == [
        Issue(
            "rules.check_review.when",
            "MAY_BE_UNSET",
            "check_review reads approved_amount, which may not be set when answered review "
            "comes: then check_review fails and needs attention: read it only when it is set, or "
            "fire it on another moment",
            "warning",
        )
    ]
    run = run_case(amount, file=SMALL, answers=[("review", "reject", "ana")], people=PEOPLE)
    [failed] = run.needs_attention
    assert failed.startswith("check_review#1: ") and failed.endswith("approved_amount has no value")


def test_an_unknown_moment_fails_closed() -> None:
    # `parse_case` refuses a moment Ventoux doesn't know. One that comes another way is refused
    # wherever a moment is read: never read as the opening, nor as one that can come (fail
    # closed).
    refused = "^'closed' is not a moment Ventoux knows$"
    case = parse_case(with_rule(when=None))
    rule = case.rules["flag_large"].model_copy(update={"on": "closed"})
    unknown = case.model_copy(update={"rules": {"flag_large": rule}})
    with pytest.raises(ValueError, match=refused):
        validate_case(unknown, CATALOG)
    with pytest.raises(ValueError, match=refused):
        decide(
            unknown,
            CATALOG,
            CaseState("t"),
            Opened({**SMALL, "amount": Decimal(40)}, None, at=START),
        )


def endless_rework() -> dict[str, Any]:
    """The guide's rework loop with its rules' conditions removed: each answer starts the other
    task again."""
    definition = guide_rework()
    for rule in definition["rules"].values():
        del rule["when"]
    return definition


ENDLESS = "check_review and send_back start lead_check and review again on every answer, and "


def test_a_loop_of_starts_never_closes() -> None:
    # The review starts as the case opens, and each answer starts the other task again: nothing in
    # the case ends it, and it has no close reason, so only a forget request could close it
    # (brief, D10) (brief, D39).
    assert [i for i in issues(endless_rework()) if i.severity == "error"] == [
        Issue(
            "rules.check_review.then.start",
            "NEVER_CLOSES",
            ENDLESS + "nothing ends it: refund has no close reason, and closes_when never closes "
            "it, so nothing but a forget request could close it: give one of the rules a when "
            "that ends the loop",
        )
    ]
    reviewed = ("review", "approve", "ana", {"approved_amount": 40})
    run = run_case(
        endless_rework(),
        file=SMALL,
        answers=[reviewed, ("lead_check", "ok", "sam"), reviewed, ("lead_check", "ok", "sam")],
        people=PEOPLE,
    )
    assert run.reached("pay") and not run.closed
    assert run.waiting_for == ["review by support"]


def closable(definition: dict[str, Any], *roles: str) -> dict[str, Any]:
    """`definition` with the guide's `duplicate` close reason ("Closing a case"), for `roles`."""
    reason = {"display": {"title": "Duplicate request"}, "roles": list(roles)}
    return definition | {"close_reasons": {"duplicate": reason}}


def test_a_loop_of_one_rule_says_it_starts() -> None:
    # The tutor's probe: one rule restarts the review on every answer. Its message agrees with
    # one rule, "send_back starts review", as with several, "check_review and send_back start",
    # and its fix names the rule: "give send_back a when".
    definition = copy.deepcopy(REFUND)
    definition["steps"]["review"]["repeatable"] = True
    definition["rules"] = {
        "send_back": {
            "display": {"title": "Send the review back"},
            "on": {"answered": "review"},
            "then": {"start": ["review"]},
        }
    }
    looping = "send_back starts review again on every answer, and nothing ends it: refund "
    assert [i for i in issues(definition) if i.code == "NEVER_CLOSES"] == [
        Issue(
            "rules.send_back.then.start",
            "NEVER_CLOSES",
            looping + "has no close reason, and closes_when never closes it, so nothing but a "
            "forget request could close it: give send_back a when that ends the loop",
        )
    ]
    warned = [i.message for i in issues(closable(definition, "support"))]
    assert warned == [
        looping + "closes only through a close reason or closes_when: give send_back a when "
        "that ends the loop"
    ]


def test_a_loop_a_close_can_end_is_warned() -> None:
    # A person can still close it with a reason, or closes_when can: a warning (brief, D10:
    # "a step that can always be restarted").
    warned = Issue(
        "rules.check_review.then.start",
        "LOOPS_UNTIL_CLOSED",
        ENDLESS + "nothing ends it: refund closes only through a close reason or closes_when: "
        "give one of the rules a when that ends the loop",
        "warning",
    )
    assert issues(closable(endless_rework(), "support")) == [warned]
    closing_on_paid = endless_rework() | {"closes_when": ["paid"]}
    closing_on_paid["milestones"]["paid"] = {"display": {"title": "Refund paid"}}
    closing_on_paid["steps"]["pay"]["reaches"] = ["paid"]
    assert issues(closing_on_paid) == [warned]
    # A misspelt role beside a registered one is still said: it closes nothing (brief, D22).
    misspelt = [i.code for i in issues(closable(endless_rework(), "support", "supprt"))]
    assert misspelt == ["LOOPS_UNTIL_CLOSED", "UNKNOWN_ROLE"]
    run = run_case(
        closable(endless_rework(), "support"),
        file=SMALL,
        answers=[APPROVED_40, ("lead_check", "ok", "sam"), close("duplicate", "ana")],
        people=PEOPLE,
    )
    assert run.closed


def test_a_loop_a_requirement_ends_gets_no_issue() -> None:
    # A refused start ends a loop: lead_check needs the refund flagged large, which only a rule
    # on the opening may reach, so for a small refund the loop never comes round (brief, D39).
    definition = endless_rework()
    definition["milestones"]["large"] = {"display": {"title": "Large refund"}}
    definition["rules"]["flag_large"] = {
        "display": {"title": "Flag a large refund"},
        "on": "opened",
        "when": {">": [{"var": "amount"}, 1000]},
        "then": {"reach": ["large"]},
    }
    definition["steps"]["lead_check"]["requires"] = ["large"]
    assert not [i for i in issues(definition) if i.path.startswith("rules.check_review")]
    run = run_case(definition, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    assert (
        "check_review#1 on answered review: lead_check not started: lead_check requires large, "
        "which hasn't been reached"
    ) in run.history
    assert run.closed
    # A task that can't run again ends it too.
    once = endless_rework()
    once["steps"]["review"]["repeatable"] = False
    assert not [i for i in issues(once) if i.code in ("NEVER_CLOSES", "LOOPS_UNTIL_CLOSED")]
    # And a loop only a person's proposal enters may never be entered: nothing is claimed.
    proposed = closable(endless_rework(), "support") | {"stays_open": True}
    proposed["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    assert issues(proposed) == []


def test_what_rules_that_start_steps_dont_claim() -> None:
    # The check claims less, never more (brief, D34). A value whose writer only a rule on the
    # reader's own moment starts is never set when it is read, but only MAY_BE_UNSET says so,
    # never SET_AFTER.
    noted = guide_rework()
    noted["milestones"]["noted"] = {"display": {"title": "Noted"}}
    noted["rules"]["note_check"] = {
        "display": {"title": "Note the check"},
        "on": {"answered": "review"},
        "when": {"==": [{"var": "lead_check.outcome"}, "ok"]},
        "then": {"reach": ["noted"]},
    }
    assert [i.code for i in issues(noted)] == ["MAY_BE_UNSET"]
    # A circle through `started` gets nothing: a rule's start never waits, so it can't come
    # round by itself, and each round begins with a person's event (brief, D39).
    started = endless_rework()
    started["rules"]["check_review"]["on"] = {"started": "review"}
    started["rules"]["send_back"]["on"] = {"started": "lead_check"}
    assert issues(started) == []
    run = run_case(started, file=SMALL, answers=[], people=PEOPLE)
    assert (
        "send_back#1 on started lead_check: review not started: review is already running: review#1"
    ) in run.history


def test_no_start_line_or_issue_quotes_a_value() -> None:
    # What the case file holds reaches people who may not see it: start lines, failures and the
    # check's messages name values, never quote them (brief, D30). The values are distinctive, so
    # a quoted one would show; "send welcome" is what the model's notes say.
    values = ["ord-77401", "77403", "77404", "c-77402", "send welcome"]
    file = {"order_id": "ord-77401", "amount": Decimal(77403)}
    reviewed = ("review", "approve", "ana", {"approved_amount": Decimal(77404)})
    rework = [reviewed, ("lead_check", "send_back", "sam"), reviewed, ("lead_check", "ok", "sam")]
    runs: list[tuple[dict[str, Any], dict[str, Any], list[Any], dict[str, Any]]] = [
        (guide_rework(), file, rework, {}),
        (endless_rework(), file, rework, {}),
        (starting_at_opening("pay"), file, [], {}),
        (only_a_rule_starts(requires=["pay"]), file, [reviewed], {}),
        (
            with_welcome(SAYS_SEND),
            {**welcome_file(), **file, "email": "c-77402@example.com"},
            [],
            {"kyc.check@1": notes_say_send},
        ),
    ]
    for definition, opened_with, answers, workflows in runs:
        run = run_case(
            definition, file=opened_with, answers=answers, people=PEOPLE, workflows=workflows
        )
        said = run.history + run.needs_attention + [i.message for i in issues(definition)]
        assert not [line for line in said if any(value in line for value in values)]


# --- Slice 1: reaching ---


def test_a_false_condition_reaches_nothing() -> None:
    run = run_case(
        with_rule(), file={"order_id": "ord-1", "amount": 250}, answers=[], people=PEOPLE
    )
    assert "flag_large#1 on opened: its condition is false" in run.history
    assert "reached large" not in run.history


def test_a_rule_on_the_opening_reaches_its_milestone_once() -> None:
    run = run_case(
        with_rule(), file={"order_id": "ord-1", "amount": 5000}, answers=[], people=PEOPLE
    )
    assert run.history[:3] == [
        "opened by system:opener, with amount and order_id",
        "flag_large#1 on opened: reaching large",
        "reached large",
    ]
    assert run.history.count("reached large") == 1


def test_a_rule_fires_on_each_run_of_its_step() -> None:
    # Two runs of the review: the rule fires on each, and reaches its milestone once.
    definition = with_rule(on={"started": "review"}, when=None)
    definition["steps"]["review"].update({"repeatable": True, "proposed_by": ["support"]})
    definition["stays_open"] = True  # so the review can be proposed again once rejected
    definition["close_reasons"] = {"done": {"display": {"title": "Done"}, "roles": ["support"]}}
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 250},
        answers=[("review", "reject", "ana"), propose("review", "ana")],
        people=PEOPLE,
    )
    assert [line for line in run.history if line.startswith("flag_large#")] == [
        "flag_large#1 on started review: reaching large",
        "flag_large#2 on started review: reaching large",
    ]
    assert run.history.count("reached large") == 1


def test_a_milestone_a_rule_reaches_starts_what_requires_it() -> None:
    # A rule on a milestone another rule reached: rules follow rules, and the step requiring the
    # last one starts in the same decision.
    definition = with_rule()
    definition["milestones"]["escalated"] = {"display": {"title": "Escalated"}}
    definition["rules"]["escalate"] = {
        "display": {"title": "Escalate a large refund"},
        "on": {"reached": "large"},
        "then": {"reach": ["escalated"]},
    }
    definition["steps"]["check_large"] = {
        "kind": "task",
        "display": {"title": "Check a large refund"},
        "roles": ["support-lead"],
        "requires": ["escalated"],
        "outcomes": {"checked": {"display": {"title": "Checked"}}},
    }
    run = run_case(
        definition, file={"order_id": "ord-1", "amount": 5000}, answers=[], people=PEOPLE
    )
    assert run.history[1:6] == [
        "flag_large#1 on opened: reaching large",
        "reached large",
        "escalate#1 on reached large: reaching escalated",
        "reached escalated",
        "started review#1: waiting for approve or reject by support",
    ]
    assert run.waiting_for == ["review by support", "check_large by support-lead"]


def test_rules_on_one_moment_fire_in_the_order_written() -> None:
    definition = with_rule()
    rule = definition["rules"].pop("flag_large")
    definition["rules"] = {"second_in_name": rule, "first_in_name": rule | {"when": None}}
    run = run_case(
        definition, file={"order_id": "ord-1", "amount": 5000}, answers=[], people=PEOPLE
    )
    assert [line for line in run.history if " on opened" in line] == [
        "second_in_name#1 on opened: reaching large",
        "first_in_name#1 on opened: reaching large",
    ]


# --- Slice 2: fail closed ---

UNREAD = (
    "flag_large#1: flag_large's condition approved_amount > 1000 can't be evaluated: "
    "approved_amount has no value"
)


def unreadable() -> dict[str, Any]:
    """A rule on the opening reading the amount the review sets, which nobody has set yet."""
    return with_rule(when={">": [{"var": "approved_amount"}, 1000]})


def test_a_rule_that_cant_be_read_needs_attention() -> None:
    # Fail closed: never read as false. The rejected review leaves nothing else to do, and the
    # case still doesn't close: the failed rule waits for a person (brief, D17, D38).
    run = run_case(
        unreadable(),
        file={"order_id": "ord-1", "amount": 250},
        answers=[("review", "reject", "ana")],
        people=PEOPLE,
    )
    assert run.needs_attention == [UNREAD]
    assert f"flag_large#1 failed: {UNREAD.split(': ', 1)[1]}" in run.history
    assert not run.closed


def test_a_misspelt_outcome_fails_the_rule_never_reads_false() -> None:
    # Checked over the case's values before it is read, as a step's are (brief, D35).
    definition = with_rule(
        on={"started": "pay"}, when={"==": [{"var": "review.outcome"}, "aprove"]}
    )
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 40},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
    )
    assert run.needs_attention == [
        (
            "flag_large#1: flag_large.when can't be read: ==[1]: review.outcome has no outcome "
            '"aprove"; its outcomes are approve, reject'
        )
    ]


def test_a_rule_still_unreadable_is_not_retried() -> None:
    with pytest.raises(
        RetryRefused, match=f"^flag_large#1 can't be retried: {UNREAD.split(': ', 1)[1]}$"
    ):
        run_case(
            unreadable(),
            file={"order_id": "ord-1", "amount": 250},
            answers=[retry("flag_large#1", "omar")],
            people=PEOPLE,
        )


def test_a_retried_rule_reads_its_condition_again() -> None:
    # Read on the case file as it is when retried: the review has set the amount since.
    run = run_case(
        unreadable(),
        file={"order_id": "ord-1", "amount": 250},
        answers=[
            ("review", "approve", "ana", {"approved_amount": 5000}),
            retry("flag_large#1", "omar"),
        ],
        people=PEOPLE,
    )
    assert run.needs_attention == []
    at = run.history.index("omar retried flag_large#1 as operations")
    assert run.history[at + 1 : at + 3] == [
        "flag_large#1 on opened: reaching large",
        "reached large",
    ]


# --- Slice 3: untrusted data can't decide ---


def with_kyc_rule(when: dict[str, Any]) -> dict[str, Any]:
    """The refund with the cases guide's KYC check, reaching `checked`, and a rule on it."""
    definition = copy.deepcopy(REFUND)
    definition["fields"]["customer_id"] = {
        "type": "reference",
        "system": "crm",
        "display": {"title": "Customer"},
    }
    definition["milestones"] = {
        "checked": {"display": {"title": "Customer checked"}},
        "high_risk": {"display": {"title": "High-risk customer"}},
    }
    definition["steps"]["kyc"] = {
        "kind": "workflow",
        "display": {"title": "Check the customer"},
        "workflow": "kyc.check@1",
        "inputs": {"customer_id": {"var": "customer_id"}},
        "reaches": ["checked"],
    }
    definition["rules"] = {
        "flag_high_risk": {
            "display": {"title": "Flag a high-risk customer"},
            "on": {"reached": "checked"},
            "when": when,
            "then": {"reach": ["high_risk"]},
        }
    }
    return definition


KYC_FILE = {"order_id": "ord-1", "amount": 40, "customer_id": "c-1"}


def test_untrusted_data_cant_decide() -> None:
    # A model wrote the notes (untrusted:llm), and the condition holds on them: still, reaching a
    # milestone decides for the case, so the rule reaches nothing (brief, D38). It names the value
    # and its source, never what the notes say (brief, D30).
    when = {"!=": [{"var": "kyc.analyst_notes"}, ""]}
    run = run_case(with_kyc_rule(when), file=KYC_FILE, answers=[], people=PEOPLE)
    assert (
        "flag_high_risk#1 on reached checked: reaches nothing: its condition reads "
        "kyc.analyst_notes, from untrusted:llm, and untrusted data can't decide"
    ) in run.history
    assert "reached high_risk" not in run.history
    assert not any("No concerns" in line for line in run.history)


def test_an_unset_untrusted_field_still_cant_decide() -> None:
    # The customer's notes are declared untrusted, and the case opens without them. The condition
    # reads a field nobody has set: it still counts the sources any of its writers could give,
    # here untrusted:customer, so it decides nothing (brief, D38) (brief, D39). Until 11b, the
    # runtime skipped a field with no sources and reached the milestone, though validation said
    # the rule never acts: the two now agree.
    definition = with_rule(
        on="opened",
        when={"!": [{"exists": "notes"}]},
        then={"reach": ["large"]},
    )
    definition["fields"]["notes"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The customer's notes"},
    }
    run = run_case(definition, file={"order_id": "ord-1", "amount": 40}, answers=[], people=PEOPLE)
    assert (
        "flag_large#1 on opened: reaches nothing: its condition reads notes, from "
        "untrusted:customer, and untrusted data can't decide"
    ) in run.history
    assert "reached large" not in run.history
    assert [issue.code for issue in validate_case(parse_case(definition), CATALOG)] == [
        "UNTRUSTED_TRIGGER"
    ]


def test_a_trusted_value_decides() -> None:
    # risk_score comes from system:kyc, which the KYC team's contract declares (brief, D29).
    run = run_case(
        with_kyc_rule({">": [{"var": "kyc.risk_score"}, 5]}),
        file=KYC_FILE,
        answers=[],
        people=PEOPLE,
    )
    assert "flag_high_risk#1 on reached checked: reaching high_risk" in run.history
    assert "reached high_risk" in run.history


def test_untrusted_data_beside_trusted_data_still_cant_decide() -> None:
    when = {
        "and": [
            {">": [{"var": "kyc.risk_score"}, 5]},
            {"!=": [{"var": "kyc.analyst_notes"}, ""]},
        ]
    }
    run = run_case(with_kyc_rule(when), file=KYC_FILE, answers=[], people=PEOPLE)
    assert "reached high_risk" not in run.history
    assert any(
        "its condition reads kyc.analyst_notes, from untrusted:llm" in line for line in run.history
    )


# --- Slice 4: the close ---


def closing_on_paid(**rule: Any) -> dict[str, Any]:
    """The refund closing once `pay` reaches `paid`, with `flag_large` changed by `rule`."""
    definition = with_rule(**rule)
    definition["milestones"]["paid"] = {"display": {"title": "Refund paid"}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["closes_when"] = ["paid"]
    return definition


def test_rules_stop_with_the_close() -> None:
    # The rule's moment is the very one that completes closes_when: nothing new is decided once
    # it is reached, and the history says why the rule did nothing (brief, D34, D38).
    run = run_case(
        closing_on_paid(on={"reached": "paid"}, when=None),
        file={"order_id": "ord-1", "amount": 40},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
    )
    assert (
        "flag_large#1 on reached paid: not applied: paid is reached, so the case closes and "
        "nothing new is decided"
    ) in run.history
    assert "reached large" not in run.history
    assert run.closed


def test_a_rule_reaching_closes_when_closes_the_case() -> None:
    # Reached by a rule or by a step, closes_when closes the case the same way (brief, D10).
    definition = with_rule()
    definition["closes_when"] = ["large"]
    run = run_case(
        definition, file={"order_id": "ord-1", "amount": 5000}, answers=[], people=PEOPLE
    )
    assert run.history[-1] == "closed: large reached"


def test_a_failed_rule_holds_the_close() -> None:
    # As a failed step does: paid is reached, and the case waits for an operator instead of
    # closing over the failed rule. Nothing is skipped automatically (brief, D17, D26).
    run = run_case(
        closing_on_paid(when={">": [{"var": "approved_amount"}, 1000]}),
        file={"order_id": "ord-1", "amount": 40},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
    )
    assert "reached paid" in run.history
    assert run.status == "open"
    assert run.needs_attention == [UNREAD]


def test_a_failed_rule_retried_while_it_holds_the_close_lets_the_case_close() -> None:
    # Read again, it decides nothing: paid is reached. Done, it holds nothing, and the case closes.
    run = run_case(
        closing_on_paid(when={">": [{"var": "approved_amount"}, 1000]}),
        file={"order_id": "ord-1", "amount": 40},
        answers=[
            ("review", "approve", "ana", {"approved_amount": 40}),
            retry("flag_large#1", "omar"),
        ],
        people=PEOPLE,
    )
    at = run.history.index("omar retried flag_large#1 as operations")
    assert run.history[at + 1] == (
        "flag_large#1 on opened: not applied: paid is reached, so the case closes and nothing new "
        "is decided"
    )
    assert run.closed and run.needs_attention == []


def test_a_person_closing_the_case_cancels_a_failed_rule() -> None:
    definition = unreadable()
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate"}, "roles": ["support"]}
    }
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 250},
        answers=[close("duplicate", "ana")],
        people=PEOPLE,
    )
    assert "cancelled flag_large#1: closed as duplicate by ana" in run.history
    assert run.closed and run.needs_attention == []


def test_rules_dont_act_while_a_failed_step_holds_the_close() -> None:
    # A lookup beside the review fails and needs attention; paid is then reached, and the close
    # waits for it (brief, D26, D34). The rule on paid decides nothing meanwhile.
    def down(inputs: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("orders unreachable")

    definition = closing_on_paid(on={"reached": "paid"}, when=None)
    definition["steps"]["look_up"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
    }
    run = run_case(
        definition,
        file={"order_id": "ord-1", "amount": 40},
        answers=[("review", "approve", "ana", {"approved_amount": 40})],
        people=PEOPLE,
        activities={"orders.lookup@1": down},
    )
    assert run.status == "open" and "reached paid" in run.history
    assert (
        "flag_large#1 on reached paid: not applied: paid is reached, so the case closes and "
        "nothing new is decided"
    ) in run.history
    assert "reached large" not in run.history


# --- Slice 5: validation stays true ---


def issues(definition: dict[str, Any]) -> list[Issue]:
    return validate_case(parse_case(definition), CATALOG)


def test_a_rule_on_a_milestone_nothing_reaches_never_fires() -> None:
    definition = with_rule(on={"reached": "large"}, when=None)
    definition["milestones"]["escalated"] = {"display": {"title": "Escalated"}}
    definition["rules"]["flag_large"]["then"] = {"reach": ["escalated"]}
    assert [i for i in issues(definition) if i.code == "NEVER_FIRES"] == [
        Issue(
            "rules.flag_large.on",
            "NEVER_FIRES",
            "flag_large can never fire: it fires on reached large, which no step or rule "
            "reaches: reach large from a step or a rule, or fire it on another moment",
        )
    ]


def test_a_rule_on_a_step_that_never_runs_never_fires() -> None:
    definition = with_rule(on={"started": "pay"})
    definition["steps"]["pay"]["requires"] = ["nowhere"]
    definition["milestones"]["nowhere"] = {"display": {"title": "Nowhere"}}
    assert [i.message for i in issues(definition) if i.code == "NEVER_FIRES"] == [
        "flag_large can never fire: it fires on started pay, which can never run: fix pay first"
    ]


def test_a_rule_waiting_on_a_rule_that_never_fires_never_fires() -> None:
    # A milestone only a rule that can never fire reaches: one cause, said at the first.
    definition = with_rule(on={"reached": "nowhere"}, when=None)
    definition["milestones"] |= {
        "nowhere": {"display": {"title": "Nowhere"}},
        "later": {"display": {"title": "Later"}},
    }
    definition["rules"]["then_later"] = {
        "display": {"title": "Then later"},
        "on": {"reached": "large"},
        "then": {"reach": ["later"]},
    }
    assert [i.message for i in issues(definition) if i.code == "NEVER_FIRES"] == [
        (
            "flag_large can never fire: it fires on reached nowhere, which no step or rule "
            "reaches: reach nowhere from a step or a rule, or fire it on another moment"
        ),
        (
            "then_later can never fire: it fires on reached large, which only flag_large "
            "reaches, and it can never happen: fix flag_large first"
        ),
    ]


def test_a_rule_on_the_last_closes_when_milestone_never_acts() -> None:
    assert [
        i.message
        for i in issues(closing_on_paid(on={"reached": "paid"}, when=None))
        if i.code == "NEVER_FIRES"
    ] == [
        (
            "flag_large can never act: it fires on reached paid, and refund closes once paid is "
            "reached, when nothing new is decided: fire it on an earlier moment, or remove paid "
            "from closes_when"
        )
    ]


def test_a_rule_reading_untrusted_data_is_refused() -> None:
    # The curriculum's negative test: what a model wrote is untrusted whoever runs the check, so
    # the rule could never act; the runtime refuses it every time (brief, D38).
    when = {"!=": [{"var": "kyc.analyst_notes"}, ""]}
    assert [i for i in issues(with_kyc_rule(when)) if i.code == "UNTRUSTED_TRIGGER"] == [
        Issue(
            "rules.flag_high_risk.when",
            "UNTRUSTED_TRIGGER",
            "flag_high_risk's condition reads kyc.analyst_notes, which comes from untrusted:llm "
            "whoever writes it, and untrusted data can't decide, so it never reaches high_risk: "
            "read a value a person or a trusted system gives, such as a task's answer",
        )
    ]


def test_a_rule_reading_trusted_data_is_not_refused() -> None:
    when = {">": [{"var": "kyc.risk_score"}, 70]}
    assert [i for i in issues(with_kyc_rule(when)) if i.code == "UNTRUSTED_TRIGGER"] == []


def test_a_milestone_only_a_rule_reaches_is_reachable() -> None:
    # Requires it, closes on it, or nothing waits for it: none is NEVER_RUNS, CLOSE_UNREACHABLE
    # or UNREACHABLE_MILESTONE, since the rule can reach it (brief, D34, D38).
    definition = with_rule()
    definition["steps"]["check_large"] = {
        "kind": "task",
        "display": {"title": "Check a large refund"},
        "roles": ["support-lead"],
        "requires": ["large"],
        "outcomes": {"checked": {"display": {"title": "Checked"}}},
    }
    assert issues(definition) == []
    del definition["steps"]["check_large"]
    assert issues(definition) == []
    definition["closes_when"] = ["large"]
    assert issues(definition) == []


def test_a_rule_breaks_a_deadlock() -> None:
    # review waits for pay (through approved), pay for review: a deadlock, unless a rule on the
    # opening can reach what review waits for.
    definition = with_rule(when=None)
    definition["steps"]["review"]["requires"] = ["large"]
    definition["steps"]["pay"]["reaches"] = ["large"]
    definition["rules"]["flag_large"]["on"] = {"started": "pay"}
    assert [i.code for i in issues(definition)][:1] == ["DEADLOCK"]
    definition["rules"]["flag_large"]["on"] = "opened"
    assert [i.code for i in issues(definition) if i.code in ("DEADLOCK", "NEVER_RUNS")] == []


def test_a_milestone_nothing_reaches_says_no_step_or_rule_reaches_it() -> None:
    definition = with_rule()
    definition["milestones"]["nowhere"] = {"display": {"title": "Nowhere"}}
    definition["steps"]["pay"]["requires"] = ["nowhere"]
    assert next(i.message for i in issues(definition) if i.code == "NEVER_RUNS") == (
        "pay can never run: it requires nowhere, which no step or rule reaches: reach nowhere "
        "from a step or a rule, or remove the requirement"
    )


def approved_first(**rule: Any) -> dict[str, Any]:
    """The refund paying once `approved` is reached, which only the review's approve reaches,
    and approve sets approved_amount: so pay surely has it, unless a rule reaches approved too."""
    definition = with_rule(**rule)
    definition["milestones"]["approved"] = {"display": {"title": "Refund approved"}}
    definition["steps"]["review"]["outcomes"]["approve"]["reaches"] = ["approved"]
    definition["steps"]["pay"]["requires"] = ["approved"]
    del definition["steps"]["pay"]["when"]
    definition["sequence"] = []
    return definition


def test_a_milestone_a_rule_may_reach_proves_nothing_about_values() -> None:
    # Reached by the rule, approved says nothing about approved_amount: pay may read it unset
    # (brief, D37, D38).
    assert [i.code for i in issues(approved_first(then={"reach": ["large"]}))] == []
    reached_by_rule = approved_first(then={"reach": ["approved"]})
    assert [i.path for i in issues(reached_by_rule) if i.code == "MAY_BE_UNSET"] == [
        "steps.pay.approval.when"
    ]


def test_a_rule_may_let_a_writer_run_first_so_set_after_becomes_a_warning() -> None:
    # notify reads pay's refund_id, and pay waits for what notify reaches: SET_AFTER, proven. A
    # rule on the opening reaching it too lets pay run first: then it may be set, not surely.
    definition = with_rule(when=None, then={"reach": ["large"]})
    definition["milestones"]["notified"] = {"display": {"title": "Customer notified"}}
    definition["steps"]["notify"] = {
        "kind": "activity",
        "display": {"title": "Tell the customer"},
        "activity": "letters.draft@2",
        "requires": ["review"],
        "inputs": {"to_customer": {"var": "order_id"}, "template": {"var": "pay.refund_id"}},
        "reaches": ["notified"],
    }
    definition["steps"]["pay"]["requires"] = ["notified"]
    codes = {i.code for i in issues(definition)}
    assert "SET_AFTER" in codes
    definition["rules"]["flag_large"]["then"] = {"reach": ["notified"]}
    codes = {i.code for i in issues(definition)}
    assert "SET_AFTER" not in codes and "MAY_BE_UNSET" in codes


def test_a_rules_condition_is_type_checked() -> None:
    # The runtime fails it (slice 2); the check says so first (brief, D35).
    definition = with_rule(
        on={"started": "pay"}, when={"==": [{"var": "review.outcome"}, "aprove"]}
    )
    assert [i for i in issues(definition) if i.code == "EXPRESSION_INVALID"] == [
        Issue(
            "rules.flag_large.when",
            "EXPRESSION_INVALID",
            '==[1]: review.outcome has no outcome "aprove"; its outcomes are approve, reject',
        )
    ]


def test_a_rule_reading_an_outcome_tells_it_apart() -> None:
    # Without call_customer, nothing reads pay's declined: OUTCOME_UNREAD. A rule that tells it
    # from done reads it, as a step's condition would (brief, D37).
    definition = with_rule(
        on={"reached": "large"}, when={"==": [{"var": "pay.outcome"}, "declined"]}
    )
    del definition["steps"]["call_customer"]
    definition["milestones"]["told"] = {"display": {"title": "Told"}}
    definition["rules"]["flag_large"]["then"] = {"reach": ["told"]}
    definition["steps"]["pay"]["reaches"] = ["large"]
    assert "OUTCOME_UNREAD" not in {i.code for i in issues(definition)}


def test_a_rule_reading_on_the_opening_what_only_a_person_sets_fails_every_time() -> None:
    # Nothing has run when the case opens: approved_amount, which only the review sets, is never
    # set then, so the rule fails each time it fires: proven, an error (brief, D34, D37).
    assert [i for i in issues(unreadable()) if i.code in ("SET_AFTER", "MAY_BE_UNSET")] == [
        Issue(
            "rules.flag_large.when",
            "SET_AFTER",
            "flag_large reads approved_amount when the case opens, and only review sets it, "
            "later: flag_large fails every time it fires: fire it on a moment after review",
        )
    ]


def test_a_rule_reading_what_may_not_be_set_yet_is_warned() -> None:
    # On pay's start the review has ended, but approved_amount is set only by approve.
    definition = with_rule(on={"started": "pay"}, when={">": [{"var": "approved_amount"}, 1000]})
    assert [i for i in issues(definition) if i.code in ("SET_AFTER", "MAY_BE_UNSET")] == [
        Issue(
            "rules.flag_large.when",
            "MAY_BE_UNSET",
            "flag_large reads approved_amount, which may not be set when started pay comes: then "
            "flag_large fails and needs attention: read it only when it is set, or fire it on "
            "another moment",
            "warning",
        )
    ]


def test_a_rule_reading_what_its_moment_ensures_is_not_warned() -> None:
    definition = with_rule(
        on={"started": "pay"}, when={"==": [{"var": "review.outcome"}, "approve"]}
    )
    assert [i for i in issues(definition) if i.code in ("SET_AFTER", "MAY_BE_UNSET")] == []


# --- Slice 7: the guide, as the engine does it ---

GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "cases.md").read_text()
RULES_SECTION = GUIDE.split("## Rules\n")[1].split("\n## ")[0]


def guide_blocks(language: str) -> list[str]:
    """The Rules section's code blocks in `language` (`""` for plain ones), in order."""
    found: list[str] = []
    opened: str | None = None
    body: list[str] = []
    for line in RULES_SECTION.splitlines():
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
    loaded: dict[str, Any] = json.loads("{" + guide_json_text(index) + "}", parse_float=Decimal)
    return loaded


def guide_json_text(index: int) -> str:
    return guide_blocks("json")[index]


def guide_case() -> dict[str, Any]:
    """The refund with the guide's KYC check reaching checked, its rule and its fraud review."""
    definition = with_kyc_rule({">": [{"var": "kyc.risk_score"}, 70]})
    definition |= guide_json(0)  # the rules block
    definition["steps"] |= guide_json(1)  # review_risk
    return definition


def risky(inputs: dict[str, Any]) -> dict[str, Any]:
    """The KYC workflow, scoring the customer 85."""
    return fake_kyc(inputs) | {"risk_score": Decimal(85)}


def shown(index: int) -> list[str]:
    """The section's plain block `index`, as history lines."""
    return guide_blocks("")[index].splitlines()


def appears_in_order(lines: list[str], history: list[str]) -> bool:
    """Whether `lines` appear in `history` one after the other."""
    return any(history[at : at + len(lines)] == lines for at in range(len(history)))


def test_the_guides_rule_runs_as_shown() -> None:
    run = run_case(
        guide_case(),
        file=KYC_FILE,
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": risky},
    )
    assert appears_in_order(shown(0), run.history)
    assert run.waiting_for == ["review by support", "review_risk by fraud"]


def test_the_guides_false_condition_says_so() -> None:
    # The development KYC fake scores the customer 12.
    run = run_case(guide_case(), file=KYC_FILE, answers=[], people=PEOPLE)
    assert "flag_high_risk#1 on reached checked: its condition is false" in run.history


def test_the_guides_unreadable_rule_is_shown() -> None:
    definition = guide_case()
    definition["rules"]["flag_high_risk"]["on"] = "opened"
    run = run_case(definition, file=KYC_FILE, answers=[], people=PEOPLE)
    assert appears_in_order(shown(1), run.history)
    assert run.needs_attention == [shown(1)[0].replace(" failed: ", ": ", 1)]


def test_the_guides_untrusted_rule_is_shown() -> None:
    definition = guide_case()
    definition["rules"]["flag_high_risk"] |= guide_json(2)
    run = run_case(definition, file=KYC_FILE, answers=[], people=PEOPLE)
    assert appears_in_order(shown(2), run.history)


def test_the_guides_rule_stopped_by_the_close_is_shown() -> None:
    definition = guide_case()
    definition["closes_when"] = ["checked"]
    run = run_case(
        definition, file=KYC_FILE, answers=[], people=PEOPLE, workflows={"kyc.check@1": risky}
    )
    assert appears_in_order(shown(3), run.history)


def guide_rework() -> dict[str, Any]:
    """The refund with the guide's rules sending the review back, its team lead's check, the
    review repeatable, the milestone declared, and `pay` requiring it ("Rules that start
    steps")."""
    definition = copy.deepcopy(REFUND)
    definition |= guide_json(3)  # the rules block
    definition["steps"] |= guide_json(4)  # lead_check
    definition["steps"]["review"]["repeatable"] = True
    definition["milestones"] = {"lead_checked": {"display": {"title": "Checked by a team lead"}}}
    definition["steps"]["pay"]["requires"] = ["lead_checked"]
    return definition


def test_the_guides_rework_loop_runs_as_shown() -> None:
    approved = ("review", "approve", "ana", {"approved_amount": 40})
    run = run_case(
        guide_rework(),
        file={"order_id": "ord-1", "amount": 40},
        answers=[
            approved,
            ("lead_check", "send_back", "lee"),
            approved,
            ("lead_check", "ok", "lee"),
        ],
        people={**PEOPLE, "lee": ["support-lead"]},
    )
    assert appears_in_order(shown(4), run.history)
    assert run.reached("pay") and run.closed


def guide_says(line: str) -> bool:
    """Whether the Rules section quotes `line` as code, line breaks aside."""
    return f"`{line}`" in " ".join(RULES_SECTION.split())


def test_the_guides_start_lines_are_what_the_engine_says() -> None:
    approved = ("review", "approve", "ana", {"approved_amount": 40})
    people = {**PEOPLE, "lee": ["support-lead"]}
    # Without `repeatable` on lead_check, the rule's second start is refused, and recorded.
    once = guide_rework()
    once["steps"]["lead_check"]["repeatable"] = False
    answers = [approved, ("lead_check", "send_back", "lee"), approved]
    run = run_case(once, file=SMALL, answers=answers, people=people)
    has_run = (
        "check_review#2 on answered review: lead_check not started: lead_check has run, and is "
        "not repeatable"
    )
    assert has_run in run.history and guide_says(has_run)
    # The per-decision guard: the guide gives the end of its line.
    guard = only_a_rule_starts()
    guard["rules"]["again"] = guard["rules"]["flag_large"] | {"display": {"title": "Again"}}
    run = run_case(guard, file=SMALL, answers=[APPROVED_40], people=PEOPLE)
    said = " not started: a rule already started it in this decision"
    assert any(line.endswith(said) for line in run.history) and guide_says(f"… review{said}")
    # The welcome letter on a model's notes, with the guide's condition.
    run = run_case(
        with_welcome(guide_json(5)["when"]),
        file=welcome_file(),
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
    )
    assert appears_in_order(shown(5), run.history)


def guide_rules_table() -> list[tuple[str, str, str]]:
    table = RULES_SECTION.split("| Code | Kind |")[1].split("\n\n")[0]
    rows = [line.split("|") for line in table.splitlines() if line.startswith("| `")]
    return [(c.strip().strip("`"), k.strip(), m.strip().strip("`")) for _, c, k, _, m, _ in rows]


def test_the_guides_table_of_rule_codes_is_what_validate_case_says() -> None:
    closing_on_checked = guide_case() | {"closes_when": ["checked"]}
    untrusted = guide_case()
    untrusted["rules"]["flag_high_risk"] |= guide_json(2)
    examples = {
        "NEVER_FIRES": closing_on_checked,
        "UNTRUSTED_TRIGGER": untrusted,
        "NEVER_STARTS": starting_at_opening("pay"),
        "LOOPS_UNTIL_CLOSED": closable(endless_rework(), "support"),
    }
    rows = guide_rules_table()
    assert [code for code, _, _ in rows] == list(examples)
    for code, kind, message in rows:
        found = [i for i in issues(examples[code]) if i.code == code]
        assert [(i.severity, i.message) for i in found] == [(kind, message)]


def test_no_rule_line_or_issue_quotes_a_value_from_the_case_file() -> None:
    # What the case file holds reaches people who may not see it: rule lines and the check's
    # messages name values, never quote them (brief, D30). The values here are distinctive, so a
    # quoted one would show.
    values = ["ord-77401", "c-77402", "77403", "77404", "No concerns in the documents."]
    file = {"order_id": "ord-77401", "amount": 77403, "customer_id": "c-77402"}

    def scored(inputs: dict[str, Any]) -> dict[str, Any]:
        return fake_kyc(inputs) | {"risk_score": Decimal(77404)}

    variants = [guide_case(), guide_case() | {"closes_when": ["checked"]}]
    for rule in ({"on": "opened"}, guide_json(2)):
        variant = guide_case()
        variant["rules"]["flag_high_risk"] |= rule
        variants.append(variant)
    for definition in variants:
        run = run_case(
            definition, file=file, answers=[], people=PEOPLE, workflows={"kyc.check@1": scored}
        )
        said = [line for line in run.history if line.startswith("flag_high_risk")]
        said += run.needs_attention + [issue.message for issue in issues(definition)]
        assert said
        assert not [line for line in said if any(value in line for value in values)]


# --- From the tutor review: what the opening may reach ---


def triaged_first(**rule: Any) -> dict[str, Any]:
    """The review's probe: the refund's review requires `triaged`, which only a rule on the
    opening reaches; no step starts by itself with nothing required."""
    definition = copy.deepcopy(REFUND)
    definition["milestones"] = {"triaged": {"display": {"title": "Triaged"}}}
    definition["steps"]["review"]["requires"] = ["triaged"]
    definition["rules"] = {
        "triage": {
            "display": {"title": "Triage the refund"},
            "on": "opened",
            "then": {"reach": ["triaged"]},
        }
        | rule
    }
    return definition


def test_a_step_a_rule_on_the_opening_admits_keeps_the_case_open() -> None:
    # The rule reaches triaged as the case opens, and the review starts in the same decision:
    # the case doesn't close at opening, so CLOSES_AT_OPENING would not be a proof.
    assert issues(triaged_first()) == []
    run = run_case(
        triaged_first(), file={"order_id": "ord-1", "amount": 250}, answers=[], people=PEOPLE
    )
    assert run.waiting_for == ["review by support"] and not run.closed


def test_a_rule_on_the_opening_whose_when_may_be_false_gives_no_issue() -> None:
    # Whether the case closes at opening then depends on the amount: a value, never proven.
    assert issues(triaged_first(when={">": [{"var": "amount"}, 1000]})) == []


def test_a_rule_on_the_opening_admitting_nothing_leaves_closes_at_opening() -> None:
    # Nothing starts by itself, and the milestone the rule reaches is one no step requires.
    definition = with_rule(when=None)
    definition["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    without_rule = copy.deepcopy(definition)
    del without_rule["rules"]
    del without_rule["milestones"]

    def closing(d: dict[str, Any]) -> list[Issue]:
        return [i for i in issues(d) if i.code == "CLOSES_AT_OPENING"]

    assert closing(definition) == closing(without_rule) != []


def test_a_rule_on_the_opening_with_its_own_error_gets_no_closes_at_opening_beside_it() -> None:
    # The rule fails as the case opens, so the case needs attention instead of closing; its own
    # SET_AFTER says why: one cause, one issue.
    definition = triaged_first(when={">": [{"var": "approved_amount"}, 1000]})
    definition["steps"]["review"]["requires"] = []
    definition["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    assert [i.code for i in issues(definition)] == ["SET_AFTER"]


# --- 11c, slice 2: stopping ---

WITHDRAWAL_TASK = {
    "kind": "task",
    "display": {"title": "Log the customer's withdrawal"},
    "roles": ["support"],
    "automatic": False,
    "proposed_by": ["support"],
    "outcomes": {"logged": {"display": {"title": "Withdrawn"}, "reaches": ["withdrawn"]}},
}


def withdrawable(*stopped: str, **rule: Any) -> dict[str, Any]:
    """The refund, with a support task that logs the customer's withdrawal, and a rule that stops
    `stopped` (the review and the payment, unless said) once the withdrawal is logged."""
    definition = copy.deepcopy(REFUND)
    definition["milestones"] = {"withdrawn": {"display": {"title": "Withdrawn"}}}
    definition["steps"]["log_withdrawal"] = copy.deepcopy(WITHDRAWAL_TASK)
    definition["rules"] = {
        "withdraw": {
            "display": {"title": "Stop the refund when the customer withdraws"},
            "on": {"reached": "withdrawn"},
            "then": {"stop": list(stopped or ("review", "pay"))},
        }
        | rule
    }
    return definition


WITHDRAWS = [propose("log_withdrawal", "ana"), ("log_withdrawal", "logged", "ana")]
DUPLICATE = {"display": {"title": "Duplicate request"}, "roles": ["support"]}
SMALL_REVIEW = ("review", "approve", "ana", {"approved_amount": 40})


def unreachable(inputs: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("provider unreachable")


def test_a_failed_run_is_never_stopped() -> None:
    # A failed run waits for a person: a stop would skip it by another name (brief, D17, D26).
    # The stop is recorded, and the run still needs attention (brief, D40).
    run = run_case(
        withdrawable(),
        file=SMALL,
        answers=[SMALL_REVIEW, *WITHDRAWS],
        people=PEOPLE,
        activities={"payments.refund@2": unreachable},
    )
    assert "withdraw#1 on reached withdrawn: stopping review and pay" in run.history
    assert (
        "withdraw#1 on reached withdrawn: pay not stopped: pay#1 needs attention, and a failed "
        "run is never stopped"
    ) in run.history
    assert [line.split(":")[0] for line in run.needs_attention] == ["pay#1"]
    assert run.status == "open"


def test_a_stop_cancels_an_open_task() -> None:
    # The customer withdraws while the review waits: the review is cancelled, saying which rule's
    # entry stopped it, never a value; nothing is left to do, so the case closes (brief, D40).
    run = run_case(withdrawable(), file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    assert run.history[-5:] == [
        "reached withdrawn",
        "withdraw#1 on reached withdrawn: stopping review and pay",
        "cancelled review#1: stopped by withdraw#1",
        "withdraw#1 on reached withdrawn: pay not stopped: no run of pay is going on",
        "closed: nothing left to do",
    ]
    assert run.waiting_for == [] and run.needs_attention == []
    # In a case that stays open, an answer to the cancelled review is refused: it is closed.
    staying = withdrawable() | {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}
    with pytest.raises(AnswerRefused, match="^review#1 is closed$"):
        late = ("review#1", "approve", "ana", {"approved_amount": 40})
        run_case(staying, file=SMALL, answers=[*WITHDRAWS, late], people=PEOPLE)


LARGE = {"order_id": "ord-1", "amount": 250}
LARGE_REVIEW = ("review", "approve", "ana", {"approved_amount": 250})


def test_a_stop_withdraws_an_approval() -> None:
    # The refund waits for a team lead's approval when the customer withdraws: the approval is
    # withdrawn and the coming run recorded cancelled, so the step doesn't start by itself again,
    # and an answer to the approval is refused (brief, D25, D40).
    staying = withdrawable() | {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}
    run = run_case(staying, file=LARGE, answers=[LARGE_REVIEW, *WITHDRAWS], people=PEOPLE)
    assert run.history[-4:] == [
        "withdraw#1 on reached withdrawn: stopping review and pay",
        "withdraw#1 on reached withdrawn: review not stopped: no run of review is going on",
        "cancelled pay.approval#1: stopped by withdraw#1",
        "pay#1 cancelled: stopped by withdraw#1",
    ]
    assert run.waiting_for == [] and not run.reached("pay")
    with pytest.raises(
        AnswerRefused, match="^pay.approval#1 was withdrawn: stopped by withdraw#1$"
    ):
        run_case(
            staying,
            file=LARGE,
            answers=[LARGE_REVIEW, *WITHDRAWS, ("pay.approval#1", "approve", "sam")],
            people=PEOPLE,
        )


def test_a_stopped_activity_finishes_and_is_flagged() -> None:
    # The payment is already running when the customer withdraws: a side effect can't be cut off
    # halfway, so it finishes; it is recorded as done, its outputs landing, and the case is
    # flagged for a person to decide on a reversal (brief, D10, D40).
    run = run_case(
        withdrawable(),
        file=SMALL,
        answers=[SMALL_REVIEW, *WITHDRAWS, finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    stopped = run.history.index("pay#1: stop requested by withdraw#1")
    assert run.history[stopped:] == [
        "pay#1: stop requested by withdraw#1",
        "pay#1 done, giving refund_id from untrusted:undeclared",
        "flagged: pay#1 completed after its stop was requested by withdraw#1",
        "closed: nothing left to do",
    ]
    assert run.flags == ["pay#1 completed after its stop was requested by withdraw#1"]
    assert run.reached("pay")


def test_a_stop_with_nothing_to_stop_is_recorded() -> None:
    # A second rule stopping the same running payment asks nothing again: a run's stop is asked
    # once, so a child is never cancelled twice (brief, D40).
    twice = withdrawable("pay")
    twice["rules"]["withdraw_again"] = twice["rules"]["withdraw"] | {
        "display": {"title": "Stop the payment again"}
    }
    run = run_case(
        twice, file=SMALL, answers=[SMALL_REVIEW, *WITHDRAWS], people=PEOPLE, held=["pay"]
    )
    assert run.history[-4:] == [
        "withdraw#1 on reached withdrawn: stopping pay",
        "pay#1: stop requested by withdraw#1",
        "withdraw_again#1 on reached withdrawn: stopping pay",
        "withdraw_again#1 on reached withdrawn: pay not stopped: its stop is already requested",
    ]
    # Nothing to stop: the review is done, and no run of pay ever started.
    run = run_case(withdrawable(), file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    assert "withdraw#1 on reached withdrawn: pay not stopped: no run of pay is going on" in (
        run.history
    )


def test_untrusted_data_cant_stop() -> None:
    # Stopping decides for the case: an injected note could cancel every review. A rule whose
    # condition reads untrusted data stops nothing, naming the value and its source, never the
    # value (brief, D38, D40). Through run_case alone: the runtime refuses it, on nothing
    # validation did (brief, D34).
    definition = withdrawable("review", when={"==": [{"var": "notes"}, "withdraw"]})
    definition["fields"]["notes"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The customer's notes"},
    }
    run = run_case(definition, file=SMALL | {"notes": "withdraw"}, answers=WITHDRAWS, people=PEOPLE)
    assert (
        "withdraw#1 on reached withdrawn: stops nothing: its condition reads notes, from "
        "untrusted:customer, and untrusted data can't decide"
    ) in run.history
    assert "cancelled review#1: stopped by withdraw#1" not in run.history
    assert run.waiting_for == ["review by support"]
    assert not any('"withdraw"' in line for line in run.history)  # the value is never quoted


def test_stop_then_reach_then_start() -> None:
    # Inside one `then`, the stop acts first, then the milestone is reached, then the start is
    # proposed; and a rule after it on the same moment sees the stopped run: the review, stopped,
    # may be started again, as a new run (brief, D40).
    definition = withdrawable(
        "review", then={"start": ["notify"], "reach": ["noted"], "stop": ["review"]}
    )
    definition["milestones"]["noted"] = {"display": {"title": "Withdrawal noted"}}
    definition["steps"]["review"]["repeatable"] = True
    definition["steps"]["review"]["proposed_by"] = ["support"]
    definition["steps"]["notify"] = {
        "kind": "task",
        "display": {"title": "Tell the customer"},
        "roles": ["support"],
        "automatic": False,
        "outcomes": {"told": {"display": {"title": "Told"}}},
    }
    definition["rules"]["ask_again"] = {
        "display": {"title": "Review again"},
        "on": {"reached": "withdrawn"},
        "then": {"start": ["review"]},
    }
    run = run_case(definition, file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    first = run.history.index("withdraw#1 on reached withdrawn: stopping review")
    assert run.history[first:] == [
        "withdraw#1 on reached withdrawn: stopping review",
        "cancelled review#1: stopped by withdraw#1",
        "withdraw#1 on reached withdrawn: reaching noted",
        "reached noted",
        "withdraw#1 on reached withdrawn: starting notify",
        "started notify#1: waiting for told by support",
        "ask_again#1 on reached withdrawn: starting review",
        "started review#2: waiting for approve or reject by support",
    ]


def test_a_stop_once_the_close_is_due_is_not_applied() -> None:
    # Rules stop with the close: once every closes_when milestone is reached, no rule acts, a
    # stop included; the close itself cancels what waits (brief, D38, D40).
    definition = withdrawable("review") | {"closes_when": ["withdrawn"]}
    run = run_case(definition, file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    assert (
        "withdraw#1 on reached withdrawn: not applied: withdrawn is reached, so the case closes "
        "and nothing new is decided"
    ) in run.history
    assert "cancelled review#1: the case closes when withdrawn is reached" in run.history
    assert "cancelled review#1: stopped by withdraw#1" not in run.history


def reviewed_again(**rule: Any) -> dict[str, Any]:
    """The withdrawable refund whose review may be proposed again, and a team lead's check that
    requires it, proposed by support."""
    definition = withdrawable("review", **rule)
    definition["steps"]["review"] |= {"repeatable": True, "proposed_by": ["support"]}
    definition["steps"]["pay"]["automatic"] = False
    definition["steps"]["pay"]["proposed_by"] = ["support"]
    definition["steps"]["lead_check"] = {
        "kind": "task",
        "display": {"title": "Check the review"},
        "roles": ["support-lead"],
        "automatic": False,
        "proposed_by": ["support"],
        "requires": ["review"],
        "outcomes": {"ok": {"display": {"title": "Right"}}},
    }
    return definition | {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}


def test_a_stopped_run_is_not_done() -> None:
    # review#1 was done; review#2, asked again, is stopped. Its latest run is cancelled, neither
    # done nor failed, so a step requiring the review waits for a later run of it to be done
    # (brief, D40).
    answers = [SMALL_REVIEW, propose("review", "ana"), *WITHDRAWS, propose("lead_check", "ana")]
    with pytest.raises(
        ProposalRefused, match="^lead_check requires review, which hasn't completed$"
    ):
        run_case(reviewed_again(), file=SMALL, answers=answers, people=PEOPLE)


def test_a_stopped_step_may_start_again_only_if_asked() -> None:
    # A stop ends the run going on now, and doesn't keep the step from starting later: proposed
    # again, the review runs again. A step that starts by itself does so at most once: stopped, it
    # doesn't start by itself again (brief, D40).
    run = run_case(
        reviewed_again(), file=SMALL, answers=[*WITHDRAWS, propose("review", "ana")], people=PEOPLE
    )
    assert run.history[-2:] == [
        "ana proposed review as support",
        "started review#2: waiting for approve or reject by support",
    ]
    run = run_case(reviewed_again(), file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    assert run.history[-1] == "cancelled review#1: stopped by withdraw#1"
    assert run.waiting_for == []


def test_stop_and_start_on_one_moment_end() -> None:
    # Two rules on the review's start, one stopping it and one starting it: each decision still
    # ends. The second start of the review in the decision is refused (brief, D39, D40).
    definition = reviewed_again(on={"started": "review"})
    definition["rules"]["restart"] = {
        "display": {"title": "Start the review again"},
        "on": {"started": "review"},
        "then": {"start": ["review"]},
    }
    run = run_case(definition, file=SMALL, answers=[], people=PEOPLE)
    assert run.history[1:] == [
        "started review#1: waiting for approve or reject by support",
        "withdraw#1 on started review: stopping review",
        "cancelled review#1: stopped by withdraw#1",
        "restart#1 on started review: starting review",
        "started review#2: waiting for approve or reject by support",
        "withdraw#2 on started review: stopping review",
        "cancelled review#2: stopped by withdraw#2",
        (
            "restart#2 on started review: review not started: a rule already started it in this "
            "decision"
        ),
    ]


# --- 11c, slice 3: after a stop ---


def test_a_run_failing_after_its_stop_needs_attention() -> None:
    # The payment, stopped while it runs, fails past its retries: nobody knows whether it paid, so
    # it needs attention like any failure, never cancelled as a close would. A later run would get
    # a new key (brief, D17, D39, D40).
    answers = [SMALL_REVIEW, *WITHDRAWS, finish("pay#1")]
    run = run_case(
        withdrawable("pay"),
        file=SMALL,
        answers=answers,
        people=PEOPLE,
        held=["pay"],
        activities={"payments.refund@2": unreachable},
    )
    assert run.history[-1] == (
        "pay#1 failed after its stop was requested by withdraw#1: payments.refund@2 failed with "
        "RuntimeError: ‹sensitive›"
    )
    assert run.needs_attention == ["pay#1: payments.refund@2 failed with RuntimeError: ‹sensitive›"]
    assert run.status == "open" and run.flags == []
    # An operator retries it, with the same key: a person decided to try again, so it is no longer
    # a run whose stop was asked, and completing is not flagged.
    calls: list[str] = []

    def fails_once(inputs: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs["idempotency_key"])
        if len(calls) == 1:
            raise RuntimeError("provider unreachable")
        return {"refund_id": "refund-ord-1"}

    retried = run_case(
        withdrawable("pay"),
        file=SMALL,
        answers=[*answers, retry("pay#1", "omar"), finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
        activities={"payments.refund@2": fails_once},
    )
    assert calls == ["memory/pay#1", "memory/pay#1"]  # the same key: the same run (brief, D26)
    assert retried.history[-4:] == [
        "omar retried pay#1 as operations",
        (
            "scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from "
            "person:ana), key memory/pay#1"
        ),
        "pay#1 done, giving refund_id from untrusted:undeclared",
        "closed: nothing left to do",
    ]
    assert retried.flags == []


# --- 11c, slice 5: validation stays a proof ---


def withdrawable_loop(*stopped: str) -> dict[str, Any]:
    """The endless rework loop, with the support task logging a withdrawal and a rule that stops
    `stopped` once it is logged."""
    definition = endless_rework()
    definition["milestones"]["withdrawn"] = {"display": {"title": "Withdrawn"}}
    definition["steps"]["log_withdrawal"] = copy.deepcopy(WITHDRAWAL_TASK)
    definition["rules"]["withdraw"] = {
        "display": {"title": "Stop the rework when the customer withdraws"},
        "on": {"reached": "withdrawn"},
        "then": {"stop": list(stopped)},
    }
    return definition


def test_a_loop_a_rule_can_stop_gets_no_issue() -> None:
    # D39's "nothing can end it" includes "no rule stopping it", which the check didn't read: a
    # rule that may stop a task of the loop can end it, and the case closes. Claimed only when no
    # rule that can fire stops a step of the loop (brief, D39, D40). A run shows it.
    definition = withdrawable_loop("review", "lead_check")
    run = run_case(definition, file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    assert "cancelled review#1: stopped by withdraw#1" in run.history and run.closed
    codes = [issue.code for issue in validate_case(parse_case(definition), CATALOG)]
    assert "NEVER_CLOSES" not in codes
    closing = validate_case(parse_case(closable(definition, "support")), CATALOG)
    assert "LOOPS_UNTIL_CLOSED" not in [issue.code for issue in closing]
    # A rule that stops something else ends nothing: the loop is still claimed.
    unrelated = withdrawable_loop("pay")
    assert "NEVER_CLOSES" in [i.code for i in validate_case(parse_case(unrelated), CATALOG)]


def test_never_starts_isnt_claimed_when_a_rule_may_stop_the_step() -> None:
    # "Refused while it runs" stops being a proof once a rule may stop the task first: the
    # restart below opens review#2, though validation said it never could. Claimed only when no
    # rule that can fire stops the step (brief, D39, D40). A run shows it.
    restarting = reviewed_again(on={"started": "review"})
    restarting["rules"]["restart"] = {
        "display": {"title": "Start the review again"},
        "on": {"started": "review"},
        "then": {"start": ["review"]},
    }
    run = run_case(restarting, file=SMALL, answers=[], people=PEOPLE)
    assert "started review#2: waiting for approve or reject by support" in run.history
    issues = validate_case(parse_case(restarting), CATALOG)
    assert "rules.restart.then.start" not in [issue.path for issue in issues]
    # With no rule stopping the review, the start is refused every time, and still claimed.
    del restarting["rules"]["withdraw"]
    issues = validate_case(parse_case(restarting), CATALOG)
    assert [i.code for i in issues if i.path == "rules.restart.then.start"] == ["NEVER_STARTS"]


def test_a_rule_stopping_on_untrusted_data_is_refused() -> None:
    # A rule that only stops steps, on a model's notes: the runtime stops nothing, every time, so
    # validation says so, as for a rule that reaches (brief, D38, D40). Until now a rule that
    # didn't reach got no UNTRUSTED_TRIGGER. A run shows it.
    definition = with_kyc_rule(SAYS_SEND)
    definition["rules"]["flag_high_risk"]["then"] = {"stop": ["review"]}
    run = run_case(
        definition,
        file=KYC_FILE,
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
    )
    assert (
        "flag_high_risk#1 on reached checked: stops nothing: its condition reads "
        "kyc.analyst_notes, from untrusted:llm, and untrusted data can't decide"
    ) in run.history
    assert run.waiting_for == ["review by support"]
    found = validate_case(parse_case(definition), CATALOG)
    assert [issue for issue in found if issue.code == "UNTRUSTED_TRIGGER"] == [
        Issue(
            "rules.flag_high_risk.when",
            "UNTRUSTED_TRIGGER",
            "flag_high_risk's condition reads kyc.analyst_notes, which comes from untrusted:llm "
            "whoever writes it, and untrusted data can't decide, so it never stops review: read "
            "a value a person or a trusted system gives, such as a task's answer",
        )
    ]


def test_a_rule_that_stops_and_starts_on_untrusted_data_gets_one_issue() -> None:
    # A rule that stops and starts doesn't act at all on untrusted data, its starts included: the
    # welcome letter never starts, so it never fails on its inputs either. One cause, one issue:
    # UNTRUSTED_TRIGGER, never INPUT_POLICY at the rule's start, which no run shows (brief, D40).
    definition = with_welcome(SAYS_SEND)
    del definition["steps"]["welcome"]["when"]
    definition["steps"]["welcome"]["automatic"] = False
    definition["rules"]["send_welcome"] = {
        "display": {"title": "Send a welcome letter"},
        "on": {"reached": "checked"},
        "when": SAYS_SEND,
        "then": {"start": ["welcome"], "stop": ["review"]},
    }
    run = run_case(
        definition,
        file=KYC_FILE,
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
    )
    assert any(
        "send_welcome#1 on reached checked: starts and stops nothing" in line
        for line in run.history
    )
    assert not any(line.startswith("welcome#1") for line in run.history)
    found = validate_case(parse_case(definition), CATALOG)
    assert [(issue.path, issue.code) for issue in found] == [
        ("rules.send_welcome.when", "UNTRUSTED_TRIGGER")
    ]
    assert found[0].message.endswith(
        "so it never starts welcome or stops review: read a value a person or a trusted system "
        "gives, such as a task's answer"
    )


def codes_of(definition: dict[str, Any]) -> list[str]:
    """The codes validation gives `definition`, in order."""
    return [issue.code for issue in validate_case(parse_case(definition), CATALOG)]


def test_what_validation_claims_stays_true_with_stops() -> None:
    # A stop only takes paths away: it reaches no milestone, completes no run, sets no value and
    # starts nothing. So each check that claims something never or always happens stays a proof
    # once rules stop steps; each is shown here with a run that does what it says (brief, D34,
    # D40). The two that stopped being proofs are above (the loop, NEVER_STARTS), and so are the
    # trust checks.
    #
    # NEVER_RUNS after the close: thank requires paid, and the case closes once paid is reached,
    # even when the payment, stopped while it runs, finishes and reaches it.
    after = withdrawable("pay") | {"closes_when": ["paid"]}
    after["milestones"]["paid"] = {"display": {"title": "Paid"}}
    after["steps"]["pay"]["reaches"] = ["paid"]
    after["steps"]["thank"] = {
        "kind": "task",
        "display": {"title": "Thank the customer"},
        "roles": ["support"],
        "requires": ["paid"],
        "outcomes": {"thanked": {"display": {"title": "Thanked"}}},
    }
    assert "NEVER_RUNS" in codes_of(after)
    run = run_case(
        after,
        file=SMALL,
        answers=[SMALL_REVIEW, *WITHDRAWS, finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    assert run.closed and not any(line.startswith("started thank") for line in run.history)
    # NEVER_CLOSES from the case's settings: a case that stays open, with no close reason a
    # registered role holds, never closes, whatever a stop cancels.
    stuck = withdrawable("review") | {
        "stays_open": True,
        "close_reasons": {"duplicate": DUPLICATE | {"roles": ["supprt"]}},
    }
    assert "NEVER_CLOSES" in codes_of(stuck)
    run = run_case(stuck, file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    assert "cancelled review#1: stopped by withdraw#1" in run.history and not run.closed
    # CLOSES_AT_OPENING: a stop on the opening finds nothing running, and the case closes at once.
    opening = copy.deepcopy(REFUND)
    opening["steps"]["review"] |= {"automatic": False, "proposed_by": ["support"]}
    opening["rules"] = {
        "halt": {"display": {"title": "Halt"}, "on": "opened", "then": {"stop": ["review"]}}
    }
    assert "CLOSES_AT_OPENING" in codes_of(opening)
    run = run_case(opening, file=SMALL, answers=[], people=PEOPLE)
    assert run.history[-1] == "closed: nothing left to do"
    # No MAY_BE_UNSET for pay, which reads review.outcome: a stopped review is not done, so pay,
    # which requires it, never starts and never reads it unset.
    assert "MAY_BE_UNSET" not in codes_of(withdrawable("review"))
    run = run_case(withdrawable("review"), file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    assert run.closed and run.needs_attention == []


def test_a_rule_that_stops_is_checked_like_any_rule() -> None:
    # Its moment, its condition type-checked and read like any rule's (brief, D35, D38, D40).
    never = withdrawable("review", on={"reached": "lost"})
    never["milestones"]["lost"] = {"display": {"title": "Lost"}}
    assert "NEVER_FIRES" in codes_of(never)
    misspelt = withdrawable("review", when={"==": [{"var": "review.outcome"}, "aprove"]})
    assert "EXPRESSION_INVALID" in codes_of(misspelt)
    early = withdrawable("review", on="opened", when={">": [{"var": "approved_amount"}, 0]})
    assert "SET_AFTER" in codes_of(early)
    run = run_case(early, file=SMALL, answers=[], people=PEOPLE)
    assert run.needs_attention[0].startswith("withdraw#1: withdraw's condition")


def guide_withdraw() -> dict[str, Any]:
    """The refund with the guide's `withdraw` rule, as "Rules that stop steps" writes it, and the
    support task that reaches `withdrawn`."""
    [text] = [block for block in guide_blocks("json") if block.lstrip().startswith('"withdraw"')]
    definition = withdrawable()
    definition["rules"] = json.loads("{" + text + "}", parse_float=Decimal)
    return definition


def test_the_guides_stop_lines_are_what_the_engine_says() -> None:
    # Every line the guide's "Rules that stop steps" quotes, made by a run of its own rule.
    run = run_case(guide_withdraw(), file=SMALL, answers=WITHDRAWS, people=PEOPLE)
    [block] = [block for block in guide_blocks("") if "stopping review and pay" in block]
    assert appears_in_order(block.splitlines(), run.history)
    lines = list(run.history)
    staying = guide_withdraw() | {"stays_open": True, "close_reasons": {"duplicate": DUPLICATE}}
    lines += run_case(
        staying, file=LARGE, answers=[LARGE_REVIEW, *WITHDRAWS], people=PEOPLE
    ).history
    held = [SMALL_REVIEW, *WITHDRAWS, finish("pay#1")]
    lines += run_case(
        guide_withdraw(), file=SMALL, answers=held, people=PEOPLE, held=["pay"]
    ).history
    failing = run_case(
        guide_withdraw(),
        file=SMALL,
        answers=held,
        people=PEOPLE,
        held=["pay"],
        activities={"payments.refund@2": unreachable},
    )
    lines += failing.history
    failed_first = run_case(
        guide_withdraw(),
        file=SMALL,
        answers=[SMALL_REVIEW, *WITHDRAWS],
        people=PEOPLE,
        activities={"payments.refund@2": unreachable},
    )
    lines += failed_first.history
    twice = guide_withdraw()
    twice["rules"]["again"] = twice["rules"]["withdraw"] | {"display": {"title": "Again"}}
    lines += run_case(
        twice, file=SMALL, answers=[SMALL_REVIEW, *WITHDRAWS], people=PEOPLE, held=["pay"]
    ).history
    quoted = [
        "cancelled review#1: stopped by withdraw#1",
        "pay#1 cancelled: stopped by withdraw#1",
        "pay#1: stop requested by withdraw#1",
        "flagged: pay#1 completed after its stop was requested by withdraw#1",
    ]
    for line in quoted:
        assert line in lines and guide_says(line), line
    ends = [
        "pay not stopped: pay#1 needs attention, and a failed run is never stopped",
        "pay not stopped: no run of pay is going on",
        "pay not stopped: its stop is already requested",
    ]
    for end in ends:
        assert any(line.endswith(end) for line in lines) and guide_says(f"… {end}"), end
    started = "pay#1 failed after its stop was requested by withdraw#1: "
    assert any(line.startswith(started) for line in lines) and guide_says(f"{started}…")
    # The refusal of a restart, and an untrusted condition's line.
    with pytest.raises(CaseInvalid) as refused:
        parse_case(withdrawable(then={"stop": ["review"], "start": ["review"]}))
    restart = str(refused.value).removeprefix("rules.withdraw.then: ")
    assert guide_says(restart)
    untrusted = with_kyc_rule(SAYS_SEND)
    untrusted["rules"]["flag_high_risk"]["then"] = {"stop": ["review"]}
    run = run_case(
        untrusted,
        file=KYC_FILE,
        answers=[],
        people=PEOPLE,
        workflows={"kyc.check@1": notes_say_send},
    )
    said = (
        " stops nothing: its condition reads kyc.analyst_notes, from untrusted:llm, and untrusted "
        "data can't decide"
    )
    assert any(line.endswith(said) for line in run.history) and guide_says(f"…{said}")


def test_no_stop_line_or_issue_quotes_a_value() -> None:
    # A stop's lines and issues name entries, steps, fields and sources, never a value from the
    # case file: they reach people who may not see it (brief, D30, D40).
    definition = withdrawable(when={"==": [{"var": "notes"}, "withdraw"]})
    definition["fields"]["notes"] = {
        "type": "string",
        "source": "untrusted:customer",
        "display": {"title": "The customer's notes"},
    }
    file = {"order_id": "ord-7731", "amount": 4321}
    review = ("review", "approve", "ana", {"approved_amount": 4321})
    runs = [
        run_case(
            definition,
            file=file | {"notes": "withdraw"},
            answers=[review, *WITHDRAWS],
            people=PEOPLE,
        ),
        run_case(withdrawable(), file=file | {"amount": 43}, answers=[*WITHDRAWS], people=PEOPLE),
        run_case(
            withdrawable("pay"),
            file=file | {"amount": 43},
            answers=[("review", "approve", "ana", {"approved_amount": 43}), *WITHDRAWS],
            people=PEOPLE,
            held=["pay"],
        ),
    ]
    issues = validate_case(parse_case(definition), CATALOG)
    said = [line for run in runs for line in run.history if "stop" in line or "cancelled" in line]
    said += [issue.message for issue in issues]
    assert said  # the runs stopped something, and said so
    for value in ("ord-7731", "4321", '"withdraw"', " 43"):
        assert not any(value in line for line in said), value


def test_a_stop_while_closing_is_not_applied() -> None:
    # From the review: choice 16's other half. Ana closes the case while the payment runs; the
    # payment finishes and reaches paid, whose rule would stop the letter. The case is closing,
    # so no rule acts, a stop included: the close stops what runs itself (brief, D38, D40).
    definition = withdrawable("review", on={"reached": "paid"})
    definition["milestones"]["paid"] = {"display": {"title": "Paid"}}
    definition["steps"]["pay"]["reaches"] = ["paid"]
    definition["close_reasons"] = {"duplicate": DUPLICATE}
    run = run_case(
        definition,
        file=SMALL,
        answers=[SMALL_REVIEW, close("duplicate", "ana"), finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    assert (
        "withdraw#1 on reached paid: not applied: the case is closing, so nothing new is decided"
    ) in run.history
    assert run.history[-1] == "closed: duplicate, by ana"


def test_never_starts_on_its_own_start_stays_claimed_for_what_a_stop_leaves_running() -> None:
    # From the review: a stop lets a start on the step's own start through only for a task,
    # cancelled at once. An activity, stopped, runs on in that decision, so the start is still
    # refused every time, and the check still says so (brief, D39, D40).
    definition = copy.deepcopy(REFUND)
    definition["steps"]["pay"] |= {"repeatable": True}
    definition["rules"] = {
        "hold_pay": {
            "display": {"title": "Hold the payment"},
            "on": {"started": "pay"},
            "then": {"stop": ["pay"]},
        },
        "pay_again": {
            "display": {"title": "Pay again"},
            "on": {"started": "pay"},
            "then": {"start": ["pay"]},
        },
    }
    issues = validate_case(parse_case(definition), CATALOG)
    assert [i.code for i in issues if i.path == "rules.pay_again.then.start"] == ["NEVER_STARTS"]
    run = run_case(definition, file=SMALL, answers=[SMALL_REVIEW], people=PEOPLE, held=["pay"])
    assert "pay_again#1 on started pay: pay not started: pay is already running: pay#1" in (
        run.history
    )


def test_a_loop_is_claimed_unless_a_rule_that_can_fire_stops_it() -> None:
    # From the review: the loop fix's two promises. A stop by a rule that can never fire ends no
    # loop, so the loop is still claimed; and a loop through a task a rule may stop never hides
    # another loop, found later, that no rule stops (brief, D39, D40).
    never = withdrawable_loop("review", "lead_check")
    never["rules"]["withdraw"]["on"] = {"reached": "lost"}
    never["milestones"]["lost"] = {"display": {"title": "Lost"}}
    assert "NEVER_CLOSES" in codes_of(never)
    # review and lead_check restart each other, and each restarts check_again, which a rule may
    # stop: the loops through check_again prove nothing, the one between review and lead_check
    # still does.
    hidden = withdrawable_loop("check_again")
    hidden["steps"]["check_again"] = hidden["steps"]["lead_check"] | {
        "display": {"title": "Check again"}
    }
    hidden["rules"] = {
        "again_from_review": {
            "display": {"title": "Check again"},
            "on": {"answered": "review"},
            "then": {"start": ["check_again"]},
        },
        "review_from_again": {
            "display": {"title": "Review again"},
            "on": {"answered": "check_again"},
            "then": {"start": ["review"]},
        },
        **hidden["rules"],
    }
    assert "NEVER_CLOSES" in codes_of(hidden)
