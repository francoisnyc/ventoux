# Shows what `report` says of a case that was refused at its opening (its workflow failed): status "open", an empty history, nothing needing attention.
"""Run: uv run python reviews/2026-11/probes/p1c_report_of_refused_opening.py

Supported names used: start_case, report, case_worker, data_converter. Past them:
`ventoux.testing`, the tests' server harness.
"""

import asyncio
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal

from ventoux.temporal.cases import CaseReport, report, start_case
from ventoux.testing import DevelopmentCases


def claim() -> dict[str, Any]:
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {"amount": {"type": "number", "display": {"title": "Amount"}}},
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess"},
                "roles": ["adjuster"],
                "outcomes": {"deny": {"display": {"title": "Deny"}}},
            }
        },
    }


async def scenario(setup: Setup) -> tuple[str, CaseReport]:
    # 40 is an int, and a number is an exact decimal: the case refuses its opening (CaseRefused).
    case = await start_case(
        setup.client, DevelopmentCases, claim(), {"amount": 40}, "claim-1", QUEUE
    )
    for _ in range(100):
        status = (await case.describe()).status
        if status is not None and status.name != "RUNNING":
            break
        await asyncio.sleep(0.05)
    return (status.name if status else "?"), await report(case)


status, told = on_temporal(scenario)
print("Temporal says the case's workflow is:", status)
print("report(case) says:", told)
if status == "FAILED" and told.status == "open":
    print(
        'RESULT: BROKEN - report() says status "open", with no history and nothing needing '
        "attention, of a case whose opening was refused and whose workflow failed"
    )
else:
    print("RESULT: HELD - report() doesn't read a refused opening as an open case")
