"""The semantic diff, layer 13b: guards on people and runs (brief, D55, as amended in 13b).

Approvals, requirements and conditions, who proposes, answers, sends and closes, freshness,
forgetting, and a plan's approval and wait states. Each judged comparison has a witness, a run
where one version refuses what the other lets through.
See docs/layers/13-diff.md (13b) and docs/guides/releases.md, "What changed: the diff".
"""

import copy
import json
from collections.abc import Callable
from typing import Any

from test_diff import (
    ROOT,
    Definition,
    lines,
    packed,
    refund,
    refund_contract,
    refund_input,
    settling,
    witnessed,
)

from ventoux.case.admission import ProposalRefused
from ventoux.case.answers import AnswerRefused
from ventoux.case.closing import CloseRefused
from ventoux.case.diff import diff
from ventoux.case.memory import CaseRun
from ventoux.case.releases import Package
from ventoux.case.runtime import EventRefused
from ventoux.core.catalog import Catalog
from ventoux.core.policy import trusted_only
from ventoux.temporal.forget import CaseLookup, lookup_refusal
from ventoux.testing import CATALOG, close, later, propose, run_case, send

FOUR_EYES = ROOT / "examples" / "refund" / "refund-four-eyes.json"

PEOPLE = {"ana": ["support"], "sam": ["support-lead"], "lee": ["support-lead"]}

type Witness = tuple[Definition, Definition, Catalog, bool, bool]


def four_eyes() -> dict[str, Any]:
    """The four-eyes refund: a payment over 10,000 needs two team leads (brief, D47)."""
    data: dict[str, Any] = json.loads(FOUR_EYES.read_text())
    return data


def counting(count: int) -> dict[str, Any]:
    """The four-eyes refund, its payment approved by `count` team leads."""
    case = four_eyes()
    case["steps"]["pay"]["approval"]["count"] = count
    return case


def paid(case: dict[str, Any], amount: int, *answers: Any) -> CaseRun:
    """The refund reviewed, `amount` approved, then `answers`."""
    return run_case(
        case,
        file={"order_id": "ord-1", "amount": amount},
        answers=[("review", "approve", "ana", {"approved_amount": amount}), *answers],
        people=PEOPLE,
    )


# --- Slice 0: an approval, its count and its condition -------------------------------------------


def test_an_approvals_count_lowered_is_looser() -> None:
    # The curriculum's negative test for 13b: one character in the JSON, and one team lead pays
    # 20,000 where two had to (brief, D47).
    found = diff(packed(counting(2)), packed(counting(1)), CATALOG)
    assert lines(found) == [
        "looser     steps.pay.approval.count: 2 -> 1 (one person approves pay, where two had to)"
    ]
    assert found.changes[0].comparison == "approval count"


def test_an_approvals_count_raised_is_stricter() -> None:
    found = diff(packed(counting(2)), packed(counting(3)), CATALOG)
    assert lines(found) == [
        "stricter   steps.pay.approval.count: 2 -> 3 (three people approve pay, where two had to)"
    ]


def checking(approved: bool) -> dict[str, Any]:
    """A case looking an order up once support has reviewed it, the lookup approved by a team
    lead or not. A low-risk step: it may run with no approval. A team lead may also close the
    case, so removing the approval doesn't change who the case names."""
    lookup: dict[str, Any] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "requires": ["review"],
    }
    if approved:
        lookup["approval"] = {"roles": ["support-lead"], "display": {"reason": "A lead checks"}}
    return {
        "case": "checked",
        "display": {"title": "An order checked"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}}
        },
        "steps": {
            "review": {
                "kind": "task",
                "display": {"title": "Review it"},
                "roles": ["support"],
                "outcomes": {"done": {"display": {"title": "Done"}}},
            },
            "lookup": lookup,
        },
        "close_reasons": {
            "withdrawn": {"display": {"title": "Withdrawn"}, "roles": ["support-lead"]}
        },
    }


def test_an_approval_removed_is_looser() -> None:
    found = diff(packed(checking(True)), packed(checking(False)), CATALOG)
    assert lines(found) == [
        "looser     steps.lookup.approval: approved by support-lead -> approved by nobody"
    ]
    assert found.changes[0].comparison == "approval"


def test_an_approval_added_is_stricter() -> None:
    found = diff(packed(checking(False)), packed(checking(True)), CATALOG)
    assert lines(found) == [
        "stricter   steps.lookup.approval: approved by nobody -> approved by support-lead"
    ]


def test_a_high_risk_steps_approval_removed_is_not_proven() -> None:
    # A high-risk step with no approval never runs: the runtime refuses it (brief, D11). So
    # removing its approval lets nothing more through, and "looser" would be a false claim.
    after = refund()
    del after["steps"]["pay"]["approval"]
    found = diff(packed(refund()), packed(after), CATALOG)
    assert (
        "not proven steps.pay.approval: approved by support-lead -> approved by nobody "
        "(payments.refund@2 is high risk: without an approval, pay never runs)"
    ) in lines(found)
    assert all(c.comparison != "approval" for c in found.changes)


def always_asked() -> dict[str, Any]:
    """The refund, its payment's approval asked on every run."""
    case = refund()
    del case["steps"]["pay"]["approval"]["when"]
    return case


def test_an_approvals_condition_added_is_looser() -> None:
    # Its condition isn't compared, its presence is: asked on no more runs than before, and on
    # fewer wherever it is false (choice 19).
    found = diff(packed(always_asked()), packed(refund()), CATALOG)
    assert lines(found) == [
        (
            "looser     steps.pay.approval.when: asked on every run -> asked only if "
            "approved_amount > 100 (on no more runs, and on fewer wherever that is false)"
        )
    ]
    assert found.changes[0].comparison == "approval condition"


def test_an_approvals_condition_removed_is_stricter() -> None:
    found = diff(packed(refund()), packed(always_asked()), CATALOG)
    assert lines(found) == [
        (
            "stricter   steps.pay.approval.when: asked only if approved_amount > 100 -> asked on "
            "every run"
        )
    ]


def test_an_approvals_condition_changed_is_not_proven() -> None:
    after = refund()
    after["steps"]["pay"]["approval"]["when"] = {">": [{"var": "approved_amount"}, 150]}
    found = diff(packed(refund()), packed(after), CATALOG)
    assert lines(found) == [
        "not proven steps.pay.approval.when: approved_amount > 100 -> approved_amount > 150"
    ]


# --- Slice 1: roles, as the catalog registers them -----------------------------------------------


def roled(**changes: list[str]) -> dict[str, Any]:
    """The refund with every kind of role list: a close reason and an event sent by support, and
    `recheck`, a task proposed by support; `changes` replaces lists by kind (`answers`, `proposes`,
    `sends`, `closes`, `approves`)."""
    case = refund()
    case["steps"]["review"]["roles"] = changes.get("answers", ["support"])
    case["steps"]["recheck"] = {
        "kind": "task",
        "display": {"title": "Review it again"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": changes.get("proposes", ["support"]),
        "outcomes": {"done": {"display": {"title": "Done"}}},
    }
    case["steps"]["pay"]["approval"]["roles"] = changes.get("approves", ["support-lead"])
    case["events"] = {
        "noted": {
            "display": {"title": "A note"},
            "sent_by": {"roles": changes.get("sends", ["support"])},
            "payload": {},
        }
    }
    case["close_reasons"] = {
        "duplicate": {
            "display": {"title": "A duplicate"},
            "roles": changes.get("closes", ["support"]),
        }
    }
    return case


def judged_lines(
    before: dict[str, Any], after: dict[str, Any], catalog: Catalog = CATALOG
) -> list[str]:
    """The changes from `before` to `after`, as printed."""
    return lines(diff(packed(before), packed(after), catalog))


def test_roles_widened_are_looser() -> None:
    # support-lead is named already (it approves pay), so who sees what doesn't change.
    both = ["support", "support-lead"]
    for kind, path in (
        ("answers", "steps.review.roles"),
        ("proposes", "steps.recheck.proposed_by"),
        ("sends", "events.noted.sent_by.roles"),
        ("closes", "close_reasons.duplicate.roles"),
    ):
        assert judged_lines(roled(), roled(**{kind: both})) == [
            f"looser     {path}: support -> support, support-lead"
        ], kind


def test_roles_narrowed_are_stricter() -> None:
    both = ["support", "support-lead"]
    assert judged_lines(roled(answers=both), roled()) == [
        "stricter   steps.review.roles: support, support-lead -> support"
    ]


def test_roles_replaced_are_not_proven() -> None:
    assert judged_lines(roled(closes=["support"]), roled(closes=["support-lead"])) == [
        "not proven close_reasons.duplicate.roles: support -> support-lead"
    ]


def test_a_role_nobody_registered_counts_for_nothing() -> None:
    # A role the catalog doesn't register gives nobody anything (brief, D22).
    found = judged_lines(roled(), roled(closes=["support", "auditor"]))
    assert (
        "not proven close_reasons.duplicate.roles: support -> support, auditor (auditor isn't "
        "registered: it gives nobody anything)"
    ) in found
    # Nor does it see anything: a field without visible_to is seen by the registered roles the
    # case names (fixed in 13b: 13a counted every name).
    assert not any("visible_to" in line for line in found)


def test_a_role_that_may_not_approve_the_risk_changes_no_approver() -> None:
    # support may approve no risk, and pay is high risk: adding it changes nobody (brief, D11).
    found = judged_lines(roled(), roled(approves=["support-lead", "support"]))
    assert found == [
        (
            "not proven steps.pay.approval.roles: support-lead -> support-lead, support (the same "
            "roles may approve payments.refund@2, high risk: support may not)"
        )
    ]


def with_clerks() -> Catalog:
    """The development catalog, with clerks who may approve up to medium risk, and a refund
    contract of medium risk."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register_role("clerk", approves="medium")
    catalog.register(refund_contract(8, refund_input(trusted_only()), risk="medium"))
    return catalog


def test_a_step_moved_to_a_lower_risk_gains_approvers() -> None:
    before = roled(approves=["support-lead", "clerk"])
    after = copy.deepcopy(before)
    after["steps"]["pay"]["activity"] = "payments.refund@8"
    found = judged_lines(before, after, with_clerks())
    assert (
        "looser     steps.pay.approval.roles: approved by support-lead -> approved by clerk or "
        "support-lead (because payments.refund@8 is medium risk)"
    ) in found
    assert (
        "stricter   steps.pay.approval.roles: approved by clerk or support-lead -> approved by "
        "support-lead (because payments.refund@2 is high risk)"
    ) in judged_lines(after, before, with_clerks())


# --- Slice 2: who is excluded from approving -----------------------------------------------------


def excluding(amount: str) -> dict[str, Any]:
    """The refund, its payment sending `amount` and run on every review, whatever its outcome:
    with no `when`, only its inputs decide whose answer it reads."""
    case = refund()
    pay = case["steps"]["pay"]
    pay["inputs"]["amount"] = {"var": amount}
    del pay["when"]
    pay["approval"] = {"roles": ["support-lead"], "display": {"reason": "A lead pays"}}
    return case


def test_a_step_that_stops_reading_an_answer_excludes_nobody_for_it() -> None:
    # The change the JSON diff hides: an input changed, and whoever answers review may now
    # approve the payment, since nobody approves a step their own answer feeds (brief, D11).
    found = judged_lines(excluding("approved_amount"), excluding("amount"))
    assert found == [
        "not proven steps.pay.inputs.amount: approved_amount -> amount",
        (
            "looser     steps.pay.approval: whoever answers review is no longer excluded from "
            "approving pay"
        ),
    ]


def test_a_step_that_starts_reading_an_answer_excludes_its_people() -> None:
    found = judged_lines(excluding("amount"), excluding("approved_amount"))
    assert (
        "stricter   steps.pay.approval: whoever answers review is now excluded from approving pay"
        in found
    )


def test_exclusions_both_added_and_removed_are_not_proven() -> None:
    before = excluding("approved_amount")
    after = excluding("checked_amount")
    after["fields"]["checked_amount"] = {"type": "number", "display": {"title": "Checked"}}
    after["steps"]["check"] = {
        "kind": "task",
        "display": {"title": "Check the amount"},
        "roles": ["support"],
        "outcomes": {"checked": {"display": {"title": "Checked"}, "sets": ["checked_amount"]}},
    }
    assert (
        "not proven steps.pay.approval: excluded from approving pay: whoever answers review -> "
        "whoever answers check"
    ) in judged_lines(before, after)


# --- Slice 3: when a step may run ----------------------------------------------------------------


def following(**step: Any) -> dict[str, Any]:
    """The refund with `follow_up`, a task for support, written with `step`'s keys."""
    case = refund()
    case["steps"]["follow_up"] = {
        "kind": "task",
        "display": {"title": "Follow up"},
        "roles": ["support"],
        "outcomes": {"done": {"display": {"title": "Done"}}},
    } | step
    return case


def test_a_requirement_removed_is_looser() -> None:
    found = judged_lines(following(requires=["review"]), following())
    assert found == ["looser     steps.follow_up.requires: review -> nothing"]
    assert (
        diff(packed(following(requires=["review"])), packed(following()), CATALOG)
        .changes[0]
        .comparison
        == "requirements"
    )


def test_a_requirement_added_is_stricter() -> None:
    found = judged_lines(following(requires=["review"]), following(requires=["review", "pay"]))
    assert found == ["stricter   steps.follow_up.requires: review -> review, pay"]


def test_a_requirement_replaced_is_not_proven() -> None:
    found = judged_lines(following(requires=["review"]), following(requires=["pay"]))
    assert found == ["not proven steps.follow_up.requires: review -> pay"]


def test_a_sequence_is_said_on_each_step_it_changes() -> None:
    # A sequence is a requirement on each step after the first: the steps are judged, the
    # sequence itself is said (13b, choice 24). Without it, pay no longer waits for review.
    after = refund()
    del after["sequence"]
    assert judged_lines(refund(), after) == [
        "looser     steps.pay.requires: review -> nothing",
        "not proven sequence: review, pay -> none",
    ]


def test_a_steps_condition_removed_is_looser() -> None:
    reject = {"==": [{"var": "review.outcome"}, "reject"]}
    found = judged_lines(
        following(requires=["review"], when=reject), following(requires=["review"])
    )
    assert found == [
        (
            'looser     steps.follow_up.when: runs only if review.outcome = "reject" -> runs '
            "whenever it is admitted (on no fewer cases, and on more wherever that was false)"
        )
    ]


def test_a_steps_condition_added_is_stricter() -> None:
    reject = {"==": [{"var": "review.outcome"}, "reject"]}
    found = judged_lines(
        following(requires=["review"]), following(requires=["review"], when=reject)
    )
    assert found == [
        (
            "stricter   steps.follow_up.when: runs whenever it is admitted -> runs only if "
            'review.outcome = "reject"'
        )
    ]


def test_automatic_turned_on_is_looser() -> None:
    proposed = {"proposed_by": ["support"]}
    found = judged_lines(following(automatic=False, **proposed), following(**proposed))
    assert found == [
        "looser     steps.follow_up.automatic: false -> true (it starts by itself once admitted)"
    ]


def test_repeatable_added_is_looser_and_removed_stricter() -> None:
    proposed = {"automatic": False, "proposed_by": ["support"]}
    once, again = following(**proposed), following(repeatable=True, **proposed)
    assert judged_lines(once, again) == [
        "looser     steps.follow_up.repeatable: false -> true (it may run again, when proposed)"
    ]
    assert judged_lines(again, once) == ["stricter   steps.follow_up.repeatable: true -> false"]


# --- Slice 4: close reasons, senders, forgetting and freshness -----------------------------------


def closing(**reasons: list[str]) -> dict[str, Any]:
    """The refund with `roled`'s lists, and each of `reasons` a close reason for its roles."""
    case = roled()
    for name, roles in reasons.items():
        case["close_reasons"][name] = {"display": {"title": name}, "roles": roles}
    return case


def test_a_close_reason_added_is_looser() -> None:
    # A new way for people to close the case.
    assert judged_lines(closing(), closing(withdrawn=["support"])) == [
        "looser     close_reasons.withdrawn: added: closed by support"
    ]
    assert judged_lines(closing(withdrawn=["support"]), closing()) == [
        "stricter   close_reasons.withdrawn: removed: closed by support"
    ]


def test_a_close_reason_renamed_is_not_judged() -> None:
    # The same way to close under another name: neither more nor less (13a, choice 6).
    before = closing()
    after = roled()
    after["close_reasons"] = {"duplicated": before["close_reasons"]["duplicate"]}
    assert judged_lines(before, after) == [
        "not proven close_reasons.duplicate: removed",
        (
            "not proven close_reasons.duplicated: added: behaves as the removed duplicate did: "
            "open cases need a migration mapping duplicate to duplicated (brief, D53)"
        ),
    ]


def test_an_events_sender_replaced_is_not_proven() -> None:
    before = roled()
    after = roled()
    after["events"]["noted"]["sent_by"] = {"system": "portal"}
    assert judged_lines(before, after) == [
        "not proven events.noted.sent_by.system: none -> portal",
        "not proven events.noted.sent_by.roles: support -> none",
    ]


def forgetting(rule: str) -> dict[str, Any]:
    """The refund, its records kept as `rule` says (brief, D32)."""
    case = refund()
    case["forgetting"] = rule
    return case


def test_forgetting_is_ordered() -> None:
    # never < while_open < allowed: toward allowed, a person may erase more.
    assert judged_lines(forgetting("while_open"), forgetting("allowed")) == [
        "looser     forgetting: while_open -> allowed (a closed case may be forgotten too)"
    ]
    assert judged_lines(forgetting("never"), forgetting("while_open")) == [
        "looser     forgetting: never -> while_open (an open case may be forgotten)"
    ]
    assert judged_lines(forgetting("allowed"), forgetting("never")) == [
        "stricter   forgetting: allowed -> never"
    ]


def fresh(age: str | None) -> dict[str, Any]:
    """A case looking an order up once someone confirms it, the order ID read at most `age` old,
    or of any age."""
    lookup: dict[str, Any] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order_id"}},
        "requires": ["confirm"],
    }
    if age is not None:
        lookup["max_age"] = {"order_id": age}
    return {
        "case": "fresh",
        "display": {"title": "A fresh order"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}}
        },
        "steps": {
            "confirm": {
                "kind": "task",
                "display": {"title": "Confirm it"},
                "roles": ["support"],
                "outcomes": {"ok": {"display": {"title": "Confirmed"}}},
            },
            "lookup": lookup,
        },
    }


def test_a_fact_allowed_older_is_looser() -> None:
    # Ages compared as durations, never as text: 2d is longer than 12h.
    assert judged_lines(fresh("12h"), fresh("2d")) == [
        "looser     steps.lookup.max_age.order_id: 12h -> 2d"
    ]
    assert judged_lines(fresh("2d"), fresh("12h")) == [
        "stricter   steps.lookup.max_age.order_id: 2d -> 12h"
    ]
    assert judged_lines(fresh("1d"), fresh("24h")) == [
        "not proven steps.lookup.max_age.order_id: 1d -> 24h (the same age)"
    ]


def test_a_fact_no_longer_required_fresh_is_looser() -> None:
    assert judged_lines(fresh("1d"), fresh(None)) == [
        "looser     steps.lookup.max_age.order_id: 1d -> any age"
    ]
    assert judged_lines(fresh(None), fresh("1d")) == [
        "stricter   steps.lookup.max_age.order_id: any age -> 1d"
    ]


# --- Slice 5: a plan's approval and wait states --------------------------------------------------


def lookup_plan(approved: bool, wait_roles: list[str] | None = None) -> dict[str, Any]:
    """`lookup-order@1`: look an order up (low risk), approved first by a team lead or not, and
    confirmed first by `wait_roles` if given."""
    states: dict[str, Any] = {
        "look": {
            "activity": "orders.lookup@1",
            "inputs": {"order_id": {"var": "order_id"}},
            "on": {"done": "done", "not_found": "done"},
        },
        "done": {"final": "succeeded"},
    }
    initial = "look"
    if approved:
        states["approve_lookup"] = {
            "approval": {"of": "look", "roles": ["support-lead"]},
            "on": {"approve": "look", "reject": "done"},
        }
        initial = "approve_lookup"
    if wait_roles is not None:
        states["confirm"] = {
            "wait": {"outcomes": ["ok"], "roles": wait_roles},
            "on": {"ok": initial},
        }
        initial = "confirm"
    return {
        "plan": "lookup-order",
        "version": 1,
        "display": {"title": "Look an order up"},
        "fields": {"order_id": {"type": "reference", "system": "orders"}},
        "initial": initial,
        "states": states,
    }


def looking(plan: dict[str, Any]) -> Package:
    """A case running `plan` as its one step."""
    case = {
        "case": "looking",
        "display": {"title": "An order looked up"},
        "fields": {
            "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}}
        },
        "steps": {
            "look_up": {
                "kind": "plan",
                "display": {"title": "Look it up"},
                "plan": "lookup-order@1",
                "inputs": {"order_id": {"var": "order_id"}},
            }
        },
    }
    return packed(case, [plan])


def test_a_plans_approval_removed_is_looser() -> None:
    found = lines(diff(looking(lookup_plan(True)), looking(lookup_plan(False)), CATALOG))
    assert (
        "looser     plans.lookup-order@1.states.look: approved by approve_lookup -> approved by "
        "no approval state"
    ) in found
    reverse = lines(diff(looking(lookup_plan(False)), looking(lookup_plan(True)), CATALOG))
    assert (
        "stricter   plans.lookup-order@1.states.look: approved by no approval state -> approved "
        "by approve_lookup"
    ) in reverse


def test_a_plans_high_risk_approval_removed_is_not_proven() -> None:
    # A high-risk activity no approval state approves stops the plan (brief, D11): nothing more
    # runs, so "looser" would be false.
    case, plans = settling()
    after = copy.deepcopy(plans)
    del after[0]["states"]["approve_refund"]
    after[0]["states"]["check_order"]["on"]["done"] = "pay"
    found = lines(diff(packed(case, plans), packed(case, after), CATALOG))
    assert (
        "not proven plans.refund-order@1.states.pay: approved by approve_refund -> approved by no "
        "approval state (payments.refund@2 is high risk: without an approval, pay never runs)"
    ) in found


def test_a_plans_approvers_are_compared_as_its_risk_allows() -> None:
    case, plans = settling()
    widened = copy.deepcopy(plans)
    widened[0]["states"]["approve_refund"]["approval"]["roles"] = ["support-lead", "finance"]
    found = lines(diff(packed(case, plans), packed(case, widened), with_finance()))
    assert found == [
        (
            "looser     plans.refund-order@1.states.approve_refund.approval.roles: support-lead -> "
            "support-lead, finance"
        )
    ]
    supported = copy.deepcopy(plans)
    supported[0]["states"]["approve_refund"]["approval"]["roles"] = ["support-lead", "support"]
    assert lines(diff(packed(case, plans), packed(case, supported), CATALOG)) == [
        (
            "not proven plans.refund-order@1.states.approve_refund.approval.roles: support-lead -> "
            "support-lead, support (the same roles may approve payments.refund@2, high risk: "
            "support may not)"
        )
    ]


def test_a_plans_wait_roles_widened_are_looser() -> None:
    before = looking(lookup_plan(False, ["support"]))
    after = looking(lookup_plan(False, ["support", "support-lead"]))
    assert lines(diff(before, after, CATALOG)) == [
        (
            "looser     plans.lookup-order@1.states.confirm.wait.roles: support -> support, "
            "support-lead"
        )
    ]


def test_a_plans_timeout_is_not_proven() -> None:
    case, plans = settling()
    after = copy.deepcopy(plans)
    after[0]["states"]["approve_refund"]["approval"]["timeout"] = "72h"
    assert lines(diff(packed(case, plans), packed(case, after), CATALOG)) == [
        "not proven plans.refund-order@1.states.approve_refund.approval.timeout: 48h -> 72h"
    ]


def test_an_output_source_on_a_plans_state_is_said_never_judged() -> None:
    # A plan keeps no activity's outputs (brief, D28): a widening there no case can meet
    # (found in the review of #47).
    case, plans = settling()
    after = copy.deepcopy(plans)
    after[0]["states"]["check_order"]["activity"] = "orders.lookup@2"
    found = diff(packed(case, plans), packed(case, after), CATALOG)
    assert lines(found)[0] == (
        "not proven plans.refund-order@1.states.check_order.activity: orders.lookup@1 -> "
        "orders.lookup@2: output status: was untrusted:undeclared; now system:orders (a plan "
        "keeps no activity's outputs)"
    )
    assert all(change.comparison is None for change in found.changes)


# --- Witnesses -----------------------------------------------------------------------------------


def waits_for_approval(run: CaseRun, waiting: str = "approval of pay by support-lead") -> bool:
    """Whether the payment hasn't run, waiting for its approval."""
    return not run.reached("pay") and run.waiting_for == [waiting]


def count_witness() -> Witness:
    """With two to approve, one team lead's approval leaves 20,000 waiting; with one, it pays."""
    approved = ("pay.approval#1", "approve", "sam")
    refused = waits_for_approval(
        paid(counting(2), 20000, approved), "approval of pay by support-lead: 1 of 2 given"
    )
    return (
        counting(2),
        counting(1),
        CATALOG,
        refused,
        paid(counting(1), 20000, approved).reached("pay"),
    )


def checked(case: dict[str, Any], *answers: Any) -> CaseRun:
    """The order reviewed, then `answers`."""
    return run_case(
        case,
        file={"order_id": "ord-1"},
        answers=[("review", "done", "ana"), *answers],
        people=PEOPLE,
    )


def approval_witness() -> Witness:
    """The lookup waits for a team lead; with no approval, it runs."""
    old = checked(checking(True))
    refused = not old.reached("lookup") and old.waiting_for == [
        "approval of lookup by support-lead"
    ]
    taken = checked(checking(False)).reached("lookup")
    return checking(True), checking(False), CATALOG, refused, taken


def condition_witness() -> Witness:
    """50 waits for a team lead while every run is asked; asked only over 100, it pays."""
    refused = waits_for_approval(paid(always_asked(), 50))
    return always_asked(), refund(), CATALOG, refused, paid(refund(), 50).reached("pay")


def attempted(
    case: dict[str, Any], catalog: Catalog = CATALOG, *script: Any, reviewed: bool = True
) -> str | CaseRun:
    """The refund reviewed by Ana (250 approved), unless not `reviewed`, then `script`: the run,
    or why it was refused."""
    people = PEOPLE | {"fin": ["finance"]}
    review = [("review", "approve", "ana", {"approved_amount": 250})] if reviewed else []
    try:
        return run_case(
            case,
            file={"order_id": "ord-1", "amount": 250},
            answers=[*review, *script],
            people=people,
            catalog=catalog,
        )
    except (AnswerRefused, CloseRefused, EventRefused, ProposalRefused) as refused:
        return str(refused)


def with_finance() -> Catalog:
    """The development catalog, with a finance role that may approve high risk."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register_role("finance", approves="high")
    return catalog


def approvers_witness() -> Witness:
    """A finance approver is refused while only team leads approve pay, and pays once finance
    may. Finance may close the case in both, so who the case names doesn't change."""
    closes = ["support", "finance"]
    before = roled(closes=closes)
    after = roled(closes=closes, approves=["support-lead", "finance"])
    approval = ("pay.approval#1", "approve", "fin")
    old, new = (
        attempted(before, with_finance(), approval),
        attempted(after, with_finance(), approval),
    )
    refused = old == "pay.approval#1 is answered by support-lead, and fin has finance"
    return before, after, with_finance(), refused, isinstance(new, CaseRun) and new.reached("pay")


def exclusions_witness() -> Witness:
    """Ana reviews and is also a team lead: refused as the payment's approver while it sends the
    amount she set, accepted once it sends the amount the case opened with."""
    before, after = excluding("approved_amount"), excluding("amount")
    people = {"ana": ["support", "support-lead"]}

    def approving(case: dict[str, Any]) -> str | CaseRun:
        try:
            return run_case(
                case,
                file={"order_id": "ord-1", "amount": 250},
                answers=[
                    ("review", "approve", "ana", {"approved_amount": 250}),
                    ("pay.approval#1", "approve", "ana"),
                ],
                people=people,
            )
        except AnswerRefused as refused:
            return str(refused)

    old, new = approving(before), approving(after)
    refused = old == "ana set approved_amount, which pay uses, so cannot approve it"
    return before, after, CATALOG, refused, isinstance(new, CaseRun) and new.reached("pay")


def answerers_witness() -> Witness:
    """A team lead may not review while support alone answers it; then may."""
    review = ("review", "approve", "sam", {"approved_amount": 250})
    before, after = roled(), roled(answers=["support", "support-lead"])
    old = attempted(before, CATALOG, review, reviewed=False)
    new = attempted(after, CATALOG, review, reviewed=False)
    refused = old == "review#1 is answered by support, and sam has support-lead"
    return before, after, CATALOG, refused, isinstance(new, CaseRun)


def proposers_witness() -> Witness:
    """A team lead may not propose a second review while support alone proposes it; then may."""
    before, after = roled(), roled(proposes=["support", "support-lead"])
    old = attempted(before, CATALOG, propose("recheck", "sam"))
    new = attempted(after, CATALOG, propose("recheck", "sam"))
    refused = old == "recheck is proposed by support, and sam has support-lead"
    taken = isinstance(new, CaseRun) and any("recheck#1" in line for line in new.history)
    return before, after, CATALOG, refused, taken


def senders_witness() -> Witness:
    """A team lead's note is refused while support alone sends it; then arrives."""
    before, after = roled(), roled(sends=["support", "support-lead"])
    old = attempted(before, CATALOG, send("noted", {}, "sam"))
    new = attempted(after, CATALOG, send("noted", {}, "sam"))
    refused = old == "noted is sent by support, and sam has support-lead"
    return before, after, CATALOG, refused, isinstance(new, CaseRun)


def closers_witness() -> Witness:
    """A team lead may not close the case as a duplicate while support alone may; then may."""
    before, after = roled(), roled(closes=["support", "support-lead"])
    old = attempted(before, CATALOG, close("duplicate", "sam"))
    new = attempted(after, CATALOG, close("duplicate", "sam"))
    refused = old == "duplicate is closed by support, and sam has support-lead"
    return before, after, CATALOG, refused, isinstance(new, CaseRun) and new.closed


def followed(case: dict[str, Any], *script: Any) -> CaseRun | str:
    """The refund, 50 asked, then `script`: the run, or why a proposal was refused."""
    try:
        return run_case(
            case, file={"order_id": "ord-1", "amount": 50}, answers=list(script), people=PEOPLE
        )
    except ProposalRefused as refused:
        return str(refused)


def started(run: CaseRun | str, entry: str = "follow_up#1") -> bool:
    """Whether `entry` started in `run`."""
    return isinstance(run, CaseRun) and any(
        line.startswith(f"started {entry}") for line in run.history
    )


def requirements_witness() -> Witness:
    """Before review is answered, a follow-up that requires it waits; requiring nothing, it
    starts at the opening."""
    before, after = following(requires=["review"]), following()
    return before, after, CATALOG, not started(followed(before)), started(followed(after))


def step_condition_witness() -> Witness:
    """A review approved: a follow-up only on a rejection doesn't start; without its condition,
    it does."""
    reject = {"==": [{"var": "review.outcome"}, "reject"]}
    before = following(requires=["review"], when=reject)
    after = following(requires=["review"])
    approved = ("review", "approve", "ana", {"approved_amount": 50})
    old, new = followed(before, approved), followed(after, approved)
    return before, after, CATALOG, not started(old), started(new)


def automatic_witness() -> Witness:
    """A follow-up nobody proposed doesn't start; made automatic, it starts by itself."""
    proposed = {"proposed_by": ["support"]}
    before, after = following(automatic=False, **proposed), following(**proposed)
    return before, after, CATALOG, not started(followed(before)), started(followed(after))


def repeatable_witness() -> Witness:
    """A follow-up done is refused a second proposal; made repeatable, it runs again."""
    proposed = {"automatic": False, "proposed_by": ["support"]}
    before, after = following(**proposed), following(repeatable=True, **proposed)
    script = (
        propose("follow_up", "ana"),
        ("follow_up", "done", "ana"),
        propose("follow_up", "ana"),
    )
    old, new = followed(before, *script), followed(after, *script)
    refused = old == "follow_up has run, and is not repeatable"
    return before, after, CATALOG, refused, started(new, "follow_up#2")


def close_reasons_witness() -> Witness:
    """Support may not close the case as withdrawn before the reason exists; then may."""
    before, after = closing(), closing(withdrawn=["support"])
    old = attempted(before, CATALOG, close("withdrawn", "ana"))
    new = attempted(after, CATALOG, close("withdrawn", "ana"))
    refused = old == "refund has no close reason 'withdrawn': its reasons are duplicate"
    return before, after, CATALOG, refused, isinstance(new, CaseRun) and new.closed


def freshness_witness() -> Witness:
    """The order ID, three days old, is refused at most a day old (it can't be fetched again, so
    the lookup needs attention); allowed a week, the lookup runs."""
    before, after = fresh("1d"), fresh("7d")

    def looked_up(case: dict[str, Any]) -> CaseRun:
        return run_case(
            case,
            file={"order_id": "ord-1"},
            answers=[later("3d"), ("confirm", "ok", "ana")],
            people=PEOPLE,
        )

    old, new = looked_up(before), looked_up(after)
    refused = not old.reached("lookup") and any(
        "order_id was obtained 3 days ago, and lookup needs it at most 1 day old" in line
        for line in old.needs_attention
    )
    return before, after, CATALOG, refused, new.reached("lookup")


def forgetting_witness() -> Witness:
    """A closed case is refused forgetting while its definition keeps closed cases; allowed, it
    may be forgotten (brief, D32)."""
    refused = lookup_refusal("refund-1", CaseLookup("kept", False, "while_open"))
    taken = lookup_refusal("refund-1", CaseLookup("kept", False, "allowed")) is None
    expected = "refund-1 is closed, and its definition keeps closed cases (forgetting: while_open)"
    return forgetting("while_open"), forgetting("allowed"), CATALOG, refused == expected, taken


def plan_done(version: Package, catalog: Catalog = CATALOG, *answers: tuple[str, str, str]) -> bool:
    """Whether the case's plan step is done, its plan's waits answered by `answers`. A refused
    answer to a plan's wait leaves the plan waiting: the same script, refused in one version and
    taken in the other, shows the difference."""
    case = json.loads(version.written.case)
    (step,) = case["steps"]
    plans = {reference: json.loads(text) for reference, text in version.written.plans.items()}
    run = run_case(
        case,
        file={"order_id": "ord-1"},
        answers=[],
        people=PEOPLE | {"fin": ["finance"]},
        catalog=catalog,
        plans=plans,
        plan_answers={step: list(answers)},
    )
    return run.reached(step)


def plan_approvals_witness() -> Witness:
    """The lookup waits for its approval; with none, the plan runs it at once."""
    before, after = looking(lookup_plan(True)), looking(lookup_plan(False))
    return before, after, CATALOG, not plan_done(before), plan_done(after)


def plan_approvers_witness() -> Witness:
    """Finance's approval of the plan's lookup is refused while only team leads approve it, and
    taken once finance may."""
    plan = lookup_plan(True)
    widened = copy.deepcopy(plan)
    widened["states"]["approve_lookup"]["approval"]["roles"] = ["support-lead", "finance"]
    before, after = looking(plan), looking(widened)
    answer = ("approve_lookup", "approve", "fin")
    refused = not plan_done(before, with_finance(), answer)
    return before, after, with_finance(), refused, plan_done(after, with_finance(), answer)


def plan_answerers_witness() -> Witness:
    """A team lead's confirmation is refused while support alone confirms; then taken."""
    before = looking(lookup_plan(False, ["support"]))
    after = looking(lookup_plan(False, ["support", "support-lead"]))
    answer = ("confirm", "ok", "sam")
    return (
        before,
        after,
        CATALOG,
        not plan_done(before, CATALOG, answer),
        plan_done(after, CATALOG, answer),
    )


# Each of 13b's comparisons, and its witness, in the order of COMPARISONS.
WITNESSES: dict[str, Callable[[], Witness]] = {
    "approval": approval_witness,
    "approval condition": condition_witness,
    "approval count": count_witness,
    "approvers": approvers_witness,
    "approval exclusions": exclusions_witness,
    "answerers": answerers_witness,
    "proposers": proposers_witness,
    "senders": senders_witness,
    "closers": closers_witness,
    "requirements": requirements_witness,
    "step condition": step_condition_witness,
    "automatic": automatic_witness,
    "repeatable": repeatable_witness,
    "close reasons": close_reasons_witness,
    "freshness": freshness_witness,
    "forgetting": forgetting_witness,
    "plan approvals": plan_approvals_witness,
    "plan approvers": plan_approvers_witness,
    "plan answerers": plan_answerers_witness,
}


def test_each_comparison_has_a_witness() -> None:
    for comparison, witness in WITNESSES.items():
        witnessed(comparison, *witness())
