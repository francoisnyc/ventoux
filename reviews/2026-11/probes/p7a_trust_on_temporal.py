# Shows whether the review's four in-memory trust findings (1a.1 to 1a.4: steering and an untrusted mark lost by repeated steps, case steps, a child's opening and a max_age refresh) reproduce in case workflows on Temporal.
"""Run: uv run python reviews/2026-11/probes/p7a_trust_on_temporal.py

The definitions are the in-memory probes' own (`p1a_*.py`, imported). Each case runs as a
`ventoux.case` workflow on the time-skipping test server; a case step's child is a real child
workflow (D75). Read on Temporal: the case's `report` (its history lines say each value's
sources; the `view` query hides these definitions' fields from every role, since they declare no
`visible_to`), and what the activity worker was really given. Reaches past the supported names
as `p7a_harness.py` says.
"""

import copy
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from p1c_harness import Setup, on_temporal
from p7a_harness import (
    Received,
    Verdicts,
    child_of,
    fakes_with,
    open_case,
    pass_time,
    quiet,
    quietly,
    said,
    show,
    wait_for,
)

from ventoux.temporal.cases import answer, send_event

repeated = quietly("p1a_repeated_step_steering_lost")
stepped = quietly("p1a_case_step_steering_lost")
marked = quietly("p1a_child_field_mark_dropped")
refreshed = quietly("p1a_refresh_launders_steered_run")

received = Received()
verdicts = Verdicts()


async def finding_1a1(setup: Setup) -> None:
    print("\n=== 1a.1 a repeated step (for_each) and what steered it")
    plain = await open_case(setup, repeated.case(False), repeated.FILE, "rep-plain")
    control = await wait_for(plain, lambda now: bool(now.needs_attention))
    show("control, a plain step with the customer's `when`", control, 1)
    own = await open_case(setup, repeated.case(True), repeated.FILE, "rep-own")
    own_now = await wait_for(own, lambda now: now.status == "closed")
    show("1. the same step repeated over lines", own_now, 1)
    ruled = await open_case(setup, repeated.with_rule(True), repeated.FILE, "rep-rule")
    ruled_now = await wait_for(ruled, lambda now: now.status == "closed")
    show("2. a rule on the repeated step's steered start", ruled_now, 1)
    needing = await open_case(setup, repeated.requiring_loose(True), repeated.FILE, "rep-req")
    needing_now = await wait_for(needing, lambda now: now.status == "closed")
    show("3. a step requiring the repeated step's steered runs", needing_now, 1)
    last = await open_case(setup, repeated.required_by_repeated(True), repeated.FILE, "rep-by")
    await wait_for(last, lambda now: said(now, "started listen#1"))
    await send_event(last, "ping", {}, "system:portal")
    last_now = await wait_for(last, lambda now: now.status == "closed")
    show("4. a repeated step requiring a steered wait", last_now, 1)
    letters = received.by("rep-own", "letters.draft@2")
    print("    the worker was given, for rep-own's letters.draft@2:", letters)
    print("    and for rep-plain's:", received.by("rep-plain", "letters.draft@2"))
    shown = [
        name
        for name, yes in (
            ("an untrusted `when` chose a trusted-only send", len(letters) == 2),
            ("a rule on its start reached settled", said(ruled_now, "reached settled")),
            ("a step requiring it reached settled", said(needing_now, "reached settled")),
            ("a repeated step requiring a steered wait sent", said(last_now, "scheduled draft.1")),
        )
        if yes
    ]
    refused = any("untrusted" in line for line in control.needs_attention)
    if refused and len(shown) == 4:
        verdicts.say(
            "1a.1",
            "REPRODUCED",
            "the plain step is refused (untrusted:customer) and nothing reaches the worker; "
            f"repeated, the worker really ran letters.draft@2 {len(letters)} times with "
            f"to_customer {letters[0]['to_customer']!r}, and: " + "; ".join(shown),
        )
    else:
        verdicts.say("1a.1", "NOT REPRODUCED", f"control refused: {refused}; shown: {shown}")


async def finding_1a2(setup: Setup) -> None:
    print("\n=== 1a.2 a case step (a real child workflow) and what steered it")
    as_plan = await open_case(
        setup, stepped.parent("plan"), stepped.FILE, "step-plan", plans=[stepped.PLAN]
    )
    control = await wait_for(as_plan, lambda now: bool(now.needs_attention))
    show("control, `write` as a plan step", control, 1)
    as_case = await open_case(
        setup, stepped.parent("case"), stepped.FILE, "step-case", cases={"write@1": stepped.CHILD}
    )
    now = await wait_for(as_case, lambda now: now.status == "closed")
    show("`write` as a case step", now, 1)
    child = await quiet(child_of(setup, "step-case", "write#1"), still=1.0)
    show("its child, the workflow step-case/write#1", child)
    marks = {
        "as a plan step": [line for line in control.history if line.startswith("mark#1")],
        "as a case step": [line for line in now.history if line.startswith("mark#1")],
    }
    print("    the value a rule set on its start:", marks)
    letters = received.by("step-case/write#1", "letters.draft@2")
    print("    the worker was given, for the child's letters.draft@2:", letters)
    # The second way in: a rule starts the case step on the note, and a timer set on its start.
    timed = await open_case(
        setup, stepped.by_rule, stepped.FILE, "step-timer", cases={"write@1": stepped.OPEN_CHILD}
    )
    await wait_for(timed, lambda now: said(now, "set chase"))
    await pass_time(setup, 2)
    timer_now = await quiet(timed)
    show("a rule starts the case step on the note; a day passes", timer_now, 1)
    reached = [m for m in ("began", "written", "followed") if said(now, f"reached {m}")]
    kept = any("untrusted:customer" in line for line in marks["as a case step"])
    if not said(control, "reached") and reached and letters:
        verdicts.say(
            "1a.2",
            "REPRODUCED",
            f"as a plan step nothing is reached and the plan stops; as a case step the parent "
            f"reached {reached}, the child workflow's letter reached the worker "
            f"({letters[0]['to_customer']!r}), the value a rule set on its start keeps "
            f"untrusted:customer: {kept} ({marks['as a case step'][0]!r}; as a plan step "
            f"{marks['as a plan step'][0]!r}), and the timer on the rule-started step's start "
            f"reached began: {said(timer_now, 'reached began')}",
        )
    else:
        verdicts.say("1a.2", "NOT REPRODUCED", f"reached {reached}; letters {letters}")


async def finding_1a3(setup: Setup) -> None:
    print("\n=== 1a.3 a child's field declared untrusted:llm, given by its parent")
    alone = await open_case(setup, marked.CHILD, {"summary": "urgent"}, "mark-alone")
    control = await wait_for(alone, lambda now: bool(now.needs_attention))
    show("control, the child opened on its own", control)
    parent = await open_case(
        setup, marked.PARENT, {"text": "urgent"}, "mark-parent", cases={"intake@1": marked.CHILD}
    )
    now = await wait_for(parent, lambda now: now.status == "closed" or bool(now.needs_attention))
    show("the parent", now)
    child = await quiet(child_of(setup, "mark-parent", "intake#1"), still=1.0)
    show("the same child, as the workflow mark-parent/intake#1", child)
    marked_alone = said(control, "summary (system:opener, untrusted:llm)")
    letter = [line for line in child.history if line.startswith("scheduled letter#1")]
    reply = [line for line in now.history if line.startswith("scheduled reply#1")]
    marked_child = any("untrusted:llm" in line for line in child.history)
    in_child = received.by("mark-parent/intake#1", "letters.draft@2")
    in_parent = received.by("mark-parent", "letters.draft@2")
    print("    the worker was given: by the child", in_child, "| by the parent", in_parent)
    if marked_alone and not marked_child and in_child:
        verdicts.say(
            "1a.3",
            "REPRODUCED",
            "alone, summary is from system:opener, untrusted:llm and the letter is refused; as "
            f"the child workflow no line names untrusted:llm, the child reached urgent "
            f"({said(child, 'reached urgent')}), the worker ran its letter with to_customer "
            f"{in_child[0]['to_customer']!r} ({letter[0][:95]!r}), and the parent sent the "
            f"reported value on to the worker ({bool(in_parent)}; {reply[0][:100]!r})",
        )
    else:
        verdicts.say(
            "1a.3", "NOT REPRODUCED", f"marked as a child: {marked_child}; worker: {in_child}"
        )


async def finding_1a4(setup: Setup) -> None:
    print("\n=== 1a.4 a max_age refresh of a run the customer's text started")
    people = refreshed.PEOPLE

    async def timeline(id: str, text: bool, days: float) -> Any:
        case = await open_case(setup, copy.deepcopy(refreshed.CASE), {"order_id": "ord-1"}, id)
        await wait_for(case, lambda now: now.waiting_at == ["review#1"])
        if text:
            await send_event(case, "said", {"text": "go"}, "system:portal")
            await wait_for(case, lambda now: said(now, "check#1 done"))
        if days:
            await pass_time(setup, days)
        await answer(case, "review#1", "ok", "ana", people["ana"])
        await wait_for(case, lambda now: said(now, "confirm#1"))
        now = await quiet(case, still=1.0)
        show(id, now, 1)
        return now

    at_once = await timeline("fresh-at-once", True, 0)
    later_on = await timeline("fresh-three-days", True, 3)
    never = await timeline("fresh-no-text", False, 3)
    sent = received.by("fresh-three-days", "letters.draft@2")
    print("    the worker was given, three days later:", sent)
    print("    at once:", received.by("fresh-at-once", "letters.draft@2"))
    refused = said(at_once, "confirm#1 failed") and said(never, "confirm#1 failed")
    reached = [m for m in ("began", "checked", "confirmed") if said(later_on, f"reached {m}")]
    if refused and reached and sent:
        verdicts.say(
            "1a.4",
            "REPRODUCED",
            "answered at once, and with no text, confirm#1 fails and the worker is given "
            f"nothing; after three skipped days check#2 runs clean, the case reached {reached} "
            f"and the worker ran letters.draft@2 with to_customer {sent[0]['to_customer']!r}",
        )
    else:
        verdicts.say("1a.4", "NOT REPRODUCED", f"refused: {refused}; reached {reached}; {sent}")


async def scenario(setup: Setup) -> None:
    for name, finding in (
        ("1a.1", finding_1a1),
        ("1a.2", finding_1a2),
        ("1a.3", finding_1a3),
        ("1a.4", finding_1a4),
    ):
        try:
            await finding(setup)
        except Exception as error:  # noqa: BLE001 (a probe says what stopped it, and goes on)
            print(f"    {name} stopped: {type(error).__name__}: {str(error)[:1500]}")
            said_so = f"the run stopped: {type(error).__name__}: {str(error)[:300]}"
            verdicts.say(name, "NOT REPRODUCED (see above)", said_so)


on_temporal(
    scenario,
    activities=fakes_with(received, {"orders.lookup@2": lambda inputs: {"status": "delivered"}}),
    timeout=400,
)
verdicts.result()
