"""Rules: on a moment, when a condition holds, then act on the case (layer 11a).

Tests go through `parse_case`, `run_case` and `validate_case`, and read what a run reports.
See docs/layers/11-rules.md and docs/guides/cases.md, "Rules".
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.validate import validate_case
from ventoux.core.validate import Issue
from ventoux.testing import (
    CATALOG,
    RetryRefused,
    close,
    fake_kyc,
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
    "on", ["closed", {"answered": "review"}, {"started": "pay", "reached": "large"}]
)
def test_an_unknown_moment_is_refused_in_one_line(on: object) -> None:
    moments = '"opened", {"started": <step>} or {"reached": <milestone>}'
    with pytest.raises(CaseInvalid, match=f"^rules.flag_large.on: a moment is {moments}$"):
        parse_case(with_rule(on=on))


def test_a_rule_without_a_title_is_refused() -> None:
    # Every rule has a business title, as steps do: people read rules too (brief, D1).
    definition = with_rule()
    del definition["rules"]["flag_large"]["display"]
    with pytest.raises(CaseInvalid, match="^rules.flag_large.display: required$"):
        parse_case(definition)


@pytest.mark.parametrize("then", [{"reach": []}, {}])
def test_a_rule_that_does_nothing_is_refused(then: dict[str, Any]) -> None:
    with pytest.raises(CaseInvalid, match="^rules.flag_large.then.reach: "):
        parse_case(with_rule(then=then))
    if then:
        with pytest.raises(CaseInvalid, match="a rule reaches at least one milestone$"):
            parse_case(with_rule(then=then))


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


def guide_rules_table() -> list[tuple[str, str, str]]:
    table = RULES_SECTION.split("| Code | Kind |")[1].split("\n\n")[0]
    rows = [line.split("|") for line in table.splitlines() if line.startswith("| `")]
    return [(c.strip().strip("`"), k.strip(), m.strip().strip("`")) for _, c, k, _, m, _ in rows]


def test_the_guides_table_of_rule_codes_is_what_validate_case_says() -> None:
    closing_on_checked = guide_case() | {"closes_when": ["checked"]}
    untrusted = guide_case()
    untrusted["rules"]["flag_high_risk"] |= guide_json(2)
    examples = {"NEVER_FIRES": closing_on_checked, "UNTRUSTED_TRIGGER": untrusted}
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
