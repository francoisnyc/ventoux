# Shows whether the review's six in-memory findings about people (1b.1, 1b.2, 1b.3, 1b.5, 1b.6, 1b.8: who may approve, see and stop across plan steps and child cases) reproduce in case workflows on Temporal.
"""Run: uv run python reviews/2026-11/probes/p7a_people_on_temporal.py

The definitions and people are the in-memory probes' own (`p1b_*.py`, imported). Each case runs
as a `ventoux.case` workflow on the time-skipping test server; a plan step is a `ventoux.plan`
child workflow and a case step's child a `ventoux.case` child workflow (D28, D75), answered by
signals as the Ventoux API would send them. Read on Temporal: each case's `report`, the `view`
query by role, the `advisor_view` query, and what the activity worker was really given. Reaches
past the supported names as `p7a_harness.py` says.
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from p1c_harness import Setup, on_temporal
from p7a_harness import (
    Received,
    Verdicts,
    answer_plan,
    child_of,
    open_case,
    pass_time,
    quiet,
    quietly,
    said,
    show,
    wait_for,
)
from temporalio import activity

from ventoux.temporal.cases import (
    answer,
    propose,
    propose_change,
    send_event,
    shown_to_advisor,
    view,
)
from ventoux.testing import FAKES

answerer = quietly("p1b_plan_wait_answerer_approves")
changes = quietly("p1b_child_change_request_by_parents_opener")
named = quietly("p1b_child_report_named_outcome")
hidden = quietly("p1b_hidden_value_into_child")
closing = quietly("p1b_parent_auto_close_cancels_childs_failed_run")
decider = quietly("p1b_when_decider_crosses_into_plan_and_child")

PEOPLE: dict[str, list[str]] = answerer.PEOPLE
# The in-memory probes' file, its number as an exact decimal: given as the integer 250, as they
# give it to `run_case`, the case workflow refuses to open (its start fails) (D20).
FILE: dict[str, Any] = {**answerer.FILE, "amount": Decimal(250)}
received = Received()
verdicts = Verdicts()
DOWN = ("down-",)  # cases (and their children) whose providers are unreachable


def reachable(fake: Any) -> Any:
    """`fake`, unreachable for the cases named in DOWN: the in-memory probes' `down`."""

    def called(inputs: dict[str, Any]) -> dict[str, Any]:
        # Temporal: inside an activity, `activity.info()` says which workflow scheduled it.
        if activity.info().workflow_id.startswith(DOWN):
            raise ConnectionError("provider unreachable")
        return fake(inputs)

    return called


async def says(case: Any, entry: str, outcome: str, who: str, form: Any = None) -> None:
    """`who` answers `entry`, once it is open, with their roles as the API would state them."""
    await wait_for(case, lambda now: entry in now.waiting_at)
    await answer(case, entry, outcome, who, PEOPLE[who], form)


async def failed(setup: Setup, case: Any, entry: str) -> Any:
    """The case's report once `entry` has failed for good: Temporal retries it first (five
    attempts, backing off), so time is skipped until it has."""
    for _ in range(40):
        now = await quiet(case, still=0.5)
        if any(line.startswith(entry) for line in now.needs_attention):
            return now
        await pass_time(setup, 1 / 24)
    raise AssertionError(f"{entry} never failed: {now.history}")


async def in_plan(
    setup: Setup, case: Any, id: str, entry: str, wait: str, outcome: str, who: str
) -> Any:
    """`who` answers `wait` inside the plan `entry` started, asked again until the plan has
    opened it; then the case's report once the plan step has ended."""
    for _ in range(40):
        try:
            await answer_plan(setup, id, entry, wait, outcome, who, PEOPLE[who])
        except Exception:  # noqa: BLE001, S110 (the plan isn't started yet, or has ended)
            pass
        now = await quiet(case, still=0.5)
        if said(now, f"{entry} done") or said(now, f"{entry} failed"):
            return now
    raise AssertionError(f"the plan {id}/{entry} never ended: {now.history}")


async def finding_1b1(setup: Setup) -> None:
    print("\n=== 1b.1 the answerer of a plan step's wait approves the step its answer decided")
    control = await open_case(setup, answerer.with_task(), FILE, "ans-task")
    await says(control, "review#1", "approve", "sam")
    await says(control, "pay.approval#1", "approve", "sam")
    control_now = await quiet(control)
    show("control, the decision is a task: sam answers, then approves pay", control_now, -3)
    case = await open_case(
        setup, answerer.with_plan(), FILE, "ans-plan", plans=[answerer.TRIAGE]
    )
    await in_plan(setup, case, "ans-plan", "triage#1", "decide#1", "yes", "sam")
    await says(case, "pay.approval#1", "approve", "sam")
    now = await wait_for(case, lambda now: now.status == "closed")
    show("the decision is a wait in a plan step: sam answers, then approves pay", now, 1)
    paid = received.by("ans-plan", "payments.refund@2")
    print("    the worker was given:", paid, "| in the control:", received.by("ans-task", "payments.refund@2"))
    refused = not said(control_now, "scheduled pay#1")
    if refused and paid and said(now, "sam answered pay.approval#1 approve"):
        verdicts.say(
            "1b.1",
            "REPRODUCED",
            "as a task, sam's approval of pay is refused and nothing is paid; with the decision "
            "in the plan child workflow, sam's signal answered decide#1, sam approved "
            f"pay.approval#1 and the worker ran payments.refund@2 ({paid[0]['amount']})",
        )
    else:
        verdicts.say("1b.1", "NOT REPRODUCED", f"control refused: {refused}; paid: {paid}")


async def finding_1b2(setup: Setup) -> None:
    print("\n=== 1b.2 the parent's opener, or the case step's proposer, approves a change in the child")
    reviewed = {"approved_amount": Decimal(900)}
    solo = await open_case(setup, changes.refund(), FILE, "chg-solo", opened_by="lee", opener_roles=PEOPLE["lee"])
    await says(solo, "review#1", "approve", "ana", reviewed)
    await wait_for(solo, lambda now: said(now, "review#1 done"))
    await propose_change(solo, "edit", "approved_amount", Decimal(5), "kim", PEOPLE["kim"])
    await says(solo, "case.change#1", "approve", "lee")
    solo_now = await quiet(solo)
    show("control, one case lee opened: kim proposes an edit, lee approves", solo_now, -3)

    async def attack(id: str, opener: str | None, proposer: str | None, kind: str, by: str, approver: str) -> bool:
        parent = await open_case(
            setup,
            changes.claim(proposer is not None),
            FILE,
            id,
            cases={"repair@3": changes.repair()},
            opened_by=opener,
            opener_roles=PEOPLE[opener] if opener else (),
        )
        await says(parent, "review#1", "approve", "ana", reviewed)
        if proposer:
            await wait_for(parent, lambda now: said(now, "review#1 done"))
            await propose(parent, "repair", proposer, PEOPLE[proposer])
        await wait_for(parent, lambda now: said(now, "started repair#1"))
        child = child_of(setup, id, "repair#1")
        await says(child, "fix#1", "fixed", "ana", {"cost": Decimal(600), "email": "a@example.com"})
        if kind == "edit":
            await wait_for(child, lambda now: said(now, "fix#1 done"))
            await propose_change(child, "edit", "cost", Decimal(700), by, PEOPLE[by])
        else:
            await failed(setup, child, "tell#1")
            await propose_change(child, "skip", "tell#1", None, by, PEOPLE[by])
        await says(child, "case.change#1", "approve", approver)
        now = await quiet(child)
        show(f"{id}: the child, the workflow {id}/repair#1", now, -3)
        return said(now, "applied case.change#1")

    applied = {
        "an edit, approved by the parent's opener": await attack("chg-a1", "lee", None, "edit", "kim", "lee"),
        "a skip of a failed run, approved by the parent's opener": await attack("down-a2", "olga", None, "skip", "omar", "olga"),
        "an edit, approved by the case step's proposer": await attack("chg-a3", None, "kim", "edit", "lee", "kim"),
        "a skip, approved by the case step's proposer": await attack("down-a4", None, "olga", "skip", "omar", "olga"),
    }
    refused = not said(solo_now, "applied case.change#1")
    done = [what for what, yes in applied.items() if yes]
    if refused and done:
        verdicts.say(
            "1b.2",
            "REPRODUCED",
            "in one case the opener's approval is refused; in the child workflow these were "
            "approved and applied: " + "; ".join(done),
        )
    else:
        verdicts.say("1b.2", "NOT REPRODUCED", f"control refused: {refused}; applied: {applied}")


async def finding_1b3(setup: Setup) -> None:
    print("\n=== 1b.3 a child's reported field named `outcome` replaces the step's outcome")
    parent = await open_case(setup, named.claim(), FILE, "out-1", cases={"repair@3": named.repair()})
    await says(parent, "review#1", "approve", "ana", {"approved_amount": Decimal(900)})
    await wait_for(parent, lambda now: said(now, "started repair#1"))
    child = child_of(setup, "out-1", "repair#1")
    await says(child, "fix#1", "fixed", "sam", {"outcome": named.CANARY})
    now = await wait_for(parent, lambda now: said(now, "repair#1 done"))
    now = await quiet(parent)
    show("the parent", now, -4)
    child_now = await quiet(child, still=0.5)
    print("    the child's own ending:", child_now.history[-1])
    seen = await view(parent, PEOPLE["sam"])
    held = seen.values.get("repair.outcome")
    print("    repair.outcome, by the `view` query:", repr(held), "from", seen.sources.get("repair.outcome"))
    at = int((await setup.environment.get_current_time()).timestamp())
    shown = await shown_to_advisor(parent, "ana", PEOPLE["ana"], at)
    to_model = named.CANARY in str(shown)
    print("    the `advisor_view` query's answer holds the person's text:", to_model)
    paid = received.by("out-1", "payments.refund@2")
    if held == named.CANARY and not paid and not said(now, "pay"):
        verdicts.say(
            "1b.3",
            "REPRODUCED",
            f"the child workflow closed by itself ({child_now.history[-1]!r}), yet the parent's "
            f"repair.outcome is the text sam typed (from {list(seen.sources['repair.outcome'])}), "
            f"so pay (when repair.outcome == 'done') never starts and the worker is given no "
            f"payment; the step advisor's view holds the text: {to_model}",
        )
    else:
        verdicts.say("1b.3", "NOT REPRODUCED", f"repair.outcome is {held!r}; paid: {paid}")


async def finding_1b5(setup: Setup) -> None:
    print("\n=== 1b.5 a hidden value given to a child, and a child's hidden value reported back")
    parent = await open_case(
        setup, hidden.claim(), FILE | {"fraud_score": Decimal(77)}, "hid-1", cases={"repair@3": hidden.repair()}
    )
    await says(parent, "review#1", "approve", "ana", {"approved_amount": Decimal(900)})
    await wait_for(parent, lambda now: said(now, "started repair#1"))
    child = child_of(setup, "hid-1", "repair#1")
    await says(child, "price#1", "priced", "fay", {"margin": Decimal(41)})
    await wait_for(child, lambda now: said(now, "price#1 done"))
    child_view = await view(child, ["support"])  # while the child is open
    await says(child, "look#1", "ok", "ana")
    await wait_for(parent, lambda now: said(now, "repair#1 done"))
    parent_view = await view(parent, ["support"])
    for title, seen in (("parent", parent_view), ("child", child_view)):
        lines = [line for line in seen.lines if "score" in line.lower() or "margin" in line.lower()]
        print(f"    the {title}, by the `view` query as support:", lines, "| hidden:", dict(seen.hidden))
    print("    the parent's values for support hold repair.margin:", parent_view.values.get("repair.margin"))
    broken = []
    if "fraud_score" not in parent_view.values and str(child_view.values.get("score")) == "77":
        broken.append("support, who may not see fraud_score, reads 77 as the child's `score`")
    if "margin" not in child_view.values and str(parent_view.values.get("repair.margin")) == "41":
        broken.append("support, who may not see the child's margin, reads 41 as the parent's repair.margin")
    if broken:
        verdicts.say("1b.5", "REPRODUCED", "by the `view` query on each workflow: " + "; ".join(broken))
    else:
        verdicts.say("1b.5", "NOT REPRODUCED", "the `view` query hides both values from support")


async def finding_1b6(setup: Setup) -> None:
    print("\n=== 1b.6 a parent closing by itself, or its rule's stop, cancels its child's failed run")
    reviewed = {"approved_amount": Decimal(900)}
    solo = await open_case(setup, closing.solo, FILE, "down-solo")
    await says(solo, "pay.approval#1", "approve", "lee")
    await failed(setup, solo, "pay#1")
    await says(solo, "review#1", "approve", "ana", reviewed)
    await wait_for(solo, lambda now: said(now, "reached reviewed"))
    solo_now = await quiet(solo)
    show("control, one case: pay#1 failed, then closes_when is reached", solo_now, -3)

    async def attack(id: str, definition: dict[str, Any], by_event: bool) -> tuple[Any, Any]:
        parent = await open_case(setup, definition, FILE, id, cases={"repair@3": closing.repair()})
        await wait_for(parent, lambda now: said(now, "started repair#1"))
        child = child_of(setup, id, "repair#1")
        await says(child, "parts.approval#1", "approve", "lee")
        before = await failed(setup, child, "parts#1")
        print(f"    {id}/repair#1 before: needs attention {before.needs_attention}")
        if by_event:
            await send_event(parent, "cancelled", {}, "system:portal")
        else:
            await says(parent, "review#1", "approve", "ana", reviewed)
        await wait_for(child, lambda now: now.status == "closed")
        parent_now, child_now = await quiet(parent), await quiet(child, still=0.5)
        show(f"{id}: the parent", parent_now, -3)
        show(f"{id}: the child", child_now, -4)
        return parent_now, child_now

    results = {
        "the parent's closes_when": await attack("down-auto", closing.by_itself, False),
        "a parent's rule's stop": await attack("down-rule", closing.by_rule, True),
    }
    waits = solo_now.status != "closed" and bool(solo_now.needs_attention)
    broken = []
    for label, (parent_now, child_now) in results.items():
        cancelled = said(child_now, "cancelled parts#1")
        if child_now.status == "closed" and cancelled and not child_now.needs_attention:
            flags = parent_now.flags + child_now.flags
            broken.append(f"{label} (flags: {flags or 'none'})")
    calls = len(received.by("down-auto/repair#1", "payments.refund@2"))
    if waits and broken:
        verdicts.say(
            "1b.6",
            "REPRODUCED",
            "in one case the failed pay#1 keeps the case open; in a child workflow the failed "
            f"parts#1 (payments.refund@2, tried {calls} times by the worker, each unreachable) "
            "was cancelled and the child closed with no person and nothing needing attention, by: "
            + "; ".join(broken),
        )
    else:
        verdicts.say("1b.6", "NOT REPRODUCED", f"control waits: {waits}; cancelled by: {broken}")


async def finding_1b8(setup: Setup) -> None:
    print("\n=== 1b.8 whoever a step's `when` read approves inside its plan or child")
    call = await open_case(setup, decider.call, FILE, "dec-call")
    await says(call, "review#1", "approve", "sam")
    await says(call, "pay.approval#1", "approve", "sam")
    call_now = await quiet(call)
    show("control, a call step: sam reviews, then approves pay", call_now, -3)
    plan = await open_case(setup, decider.plan, FILE, "dec-plan", plans=[decider.PLAN])
    await says(plan, "review#1", "approve", "sam")
    await wait_for(plan, lambda now: said(now, "started settle#1"))
    plan_now = await in_plan(setup, plan, "dec-plan", "settle#1", "approve_refund#1", "approve", "sam")
    show("a plan step with the same `when`: sam approves inside the plan", plan_now, -3)
    child_case = await open_case(setup, decider.child, FILE, "dec-child", cases={"repair@3": decider.CHILD})
    await says(child_case, "review#1", "approve", "sam")
    await wait_for(child_case, lambda now: said(now, "started repair#1"))
    child = child_of(setup, "dec-child", "repair#1")
    await says(child, "parts.approval#1", "approve", "sam")
    child_now = await quiet(child)
    show("a case step with the same `when`: sam approves inside the child", child_now, -4)
    in_plan_paid = received.by("dec-plan/settle#1", "payments.refund@2")
    in_child_paid = received.by("dec-child/repair#1", "payments.refund@2")
    print("    the worker was given: by the plan", in_plan_paid, "| by the child", in_child_paid)
    refused = not said(call_now, "scheduled pay#1") and not received.by("dec-call", "payments.refund@2")
    where = [w for w, yes in (("a plan step", in_plan_paid), ("a case step", in_child_paid)) if yes]
    if refused and where:
        verdicts.say(
            "1b.8",
            "REPRODUCED",
            "as a call step sam's approval is refused and nothing is paid; wrapped in "
            f"{' and in '.join(where)} sam's approval is taken in the child workflow and the "
            "worker ran payments.refund@2",
        )
    else:
        verdicts.say("1b.8", "NOT REPRODUCED", f"control refused: {refused}; paid in: {where}")


async def scenario(setup: Setup) -> None:
    findings = (
        ("1b.1", finding_1b1),
        ("1b.2", finding_1b2),
        ("1b.3", finding_1b3),
        ("1b.5", finding_1b5),
        ("1b.6", finding_1b6),
        ("1b.8", finding_1b8),
    )
    only = sys.argv[1:]
    for name, finding in findings:
        if only and name not in only:
            continue
        try:
            await asyncio.wait_for(finding(setup), timeout=150)
        except Exception as error:  # noqa: BLE001 (a probe says what stopped it, and goes on)
            print(f"    {name} stopped: {type(error).__name__}: {str(error)[:1500]}")
            said_so = f"the run stopped: {type(error).__name__}: {str(error)[:300]}"
            verdicts.say(name, "NOT REPRODUCED (see above)", said_so)


on_temporal(
    scenario,
    activities=received.wrap({name: reachable(fake) for name, fake in FAKES.items()}),
    timeout=900,
)
verdicts.result()
