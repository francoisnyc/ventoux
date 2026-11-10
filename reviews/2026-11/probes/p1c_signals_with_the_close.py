# Sends a burst of proposals at the same moment as the answer that closes a case, many times over, and checks that every signal whose send succeeded has its line in the closed case's report and its record in the audit store.
"""Run: uv run python reviews/2026-11/probes/p1c_signals_with_the_close.py

Supported names used: start_case, answer, FileAudit (read), case_worker. Past them:
`ventoux.temporal.cases.propose` (a client function D79 names), `ventoux.testing`, the tests' server
harness.
"""

import asyncio
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal, until
from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError

from ventoux.temporal.cases import answer, propose, report, start_case
from ventoux.testing import DevelopmentCases

CASES, BURST = 12, 8


def definition() -> dict[str, Any]:
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {},
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess"},
                "roles": ["adjuster"],
                "outcomes": {"deny": {"display": {"title": "Deny"}}},
            }
        },
    }


async def sent(case: Any, who: str) -> bool:
    """Whether Temporal took the signal: False once the workflow has ended (the sender is told)."""
    try:
        await propose(case, "nothing", who, ["adjuster"])
    except RPCError:
        return False
    return True


async def scenario(setup: Setup) -> list[str]:
    lost: list[str] = []
    taken_after_close = told = 0
    for n in range(CASES):
        id = f"claim-{n}"
        case = await start_case(setup.client, DevelopmentCases, definition(), {}, id, QUEUE)
        await until(case, lambda now: now.waiting_at == ["assess#1"])
        people = [f"p{n}x{i}" for i in range(BURST)]
        # Half the burst before the close, half after, all at once.
        results = await asyncio.gather(
            *(sent(case, who) for who in people[: BURST // 2]),
            answer(case, "assess#1", "deny", "ana", ["adjuster"]),
            *(sent(case, who) for who in people[BURST // 2 :]),
        )
        taken = [
            who
            for who, ok in zip(people, [*results[: BURST // 2], *results[BURST // 2 + 1 :]])
            if ok
        ]
        told += BURST - len(taken)
        # Until its workflow has ended (asked of Temporal, a bounded number of times), then
        # the report it returned.
        for _ in range(600):
            if (await case.describe()).status == WorkflowExecutionStatus.COMPLETED:
                break
            await asyncio.sleep(0.05)
        else:
            lost.append(f"{id}: its workflow never ended")
            continue
        ended = await report(case)
        text = "\n".join(ended.history)
        records = setup.audit.read(id)
        written = {record["act"]["by"] for record in records}
        for who in taken:
            if who not in text:
                lost.append(f"{id}: {who}'s proposal has no line in the closed case's report")
            if who not in written:
                lost.append(f"{id}: {who}'s proposal has no record in the audit store")
        taken_after_close += sum(
            f"refused {who}'s proposal of nothing: the case is closed" in text for who in taken
        )
        if len(records) != len({record["number"] for record in records}) or [
            record["number"] for record in records
        ] != list(range(1, len(records) + 1)):
            lost.append(f"{id}: its records aren't numbered 1..{len(records)}")
    print(
        f"{CASES} cases, {CASES * BURST} proposals (of a step that doesn't exist) sent with the close: {told} were refused to "
        f"their sender by Temporal (the workflow had ended); {taken_after_close} reached the "
        "case after it closed and were refused and recorded"
    )
    return lost


lost = on_temporal(scenario, timeout=300)
for line in lost:
    print("LOST:", line)
if lost:
    print(f"RESULT: BROKEN - {len(lost)} signals taken by Temporal left no line or no record")
else:
    print(
        "RESULT: HELD - every signal Temporal took has its line in the closed case's report and its record in the store, numbered without a gap"
    )
