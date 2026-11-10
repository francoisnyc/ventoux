# Records the idempotency key a payment activity is given on each attempt: Temporal's own retry, then an operator's retry made after the case continued as new: all must be `<case ID>/<first run ID>/pay#1`.
"""Run: uv run python reviews/2026-11/probes/p1c_idempotency_keys.py

Supported names used: start_case, answer, report, case_worker. Past them:
`ventoux.temporal.cases.retry` (a client function D79 names), `ventoux.testing`, the tests' server
harness, the quickstart's refund from examples/.
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

from p1c_harness import QUEUE, Setup, SwitchingCases, on_temporal, until
from temporalio.exceptions import ApplicationError

from ventoux.temporal.cases import answer, retry, start_case
from ventoux.testing import FAKES, load_definition

REFUND = load_definition(
    Path(__file__).resolve().parents[3] / "examples" / "refund" / "refund.json"
)
KEYS: list[str] = []  # the key the payment's code was given, on each attempt


def paying(inputs: dict[str, Any]) -> dict[str, Any]:
    KEYS.append(inputs["idempotency_key"])
    if len(KEYS) == 1:
        raise RuntimeError("the payment provider timed out")  # Temporal retries it
    if len(KEYS) == 2:
        raise ApplicationError("the payment provider is closed", non_retryable=True)
    return {"refund_id": "rf-1"}


async def scenario(setup: Setup) -> tuple[str, str, list[str]]:
    file = {"order_id": "ord-1", "amount": Decimal(40)}
    case = await start_case(setup.client, SwitchingCases, REFUND, file, "refund-1", QUEUE)
    await until(case, lambda now: now.waiting_at == ["review#1"])
    info = (await case.describe()).raw_description.workflow_execution_info
    first = info.first_run_id
    await answer(case, "review#1", "approve", "ana", ["support"], {"approved_amount": Decimal(40)})
    failed = await until(case, lambda now: bool(now.needs_attention))
    print("needs attention:", failed.needs_attention)
    # Until the case has continued as new at least once since it opened.
    for _ in range(200):
        info = (await case.describe()).raw_description.workflow_execution_info
        if info.execution.run_id != first:
            break
        await asyncio.sleep(0.05)
    current = info.execution.run_id
    await retry(case, "pay#1", "omar", ["operations"])
    done = await until(case, lambda now: now.status == "closed")
    print("history lines naming a key:")
    for line in done.history:
        if "key " in line or "retried" in line:
            print("    ", line)
    return first, current, list(KEYS)


first, current, keys = on_temporal(
    scenario, cases=SwitchingCases, activities={**FAKES, "payments.refund@2": paying}
)
print("first run:", first, "| run that took the operator's retry:", current)
for n, key in enumerate(keys, start=1):
    print(f"attempt {n}: key {key}")
expected = f"refund-1/{first}/pay#1"
if len(keys) == 3 and set(keys) == {expected} and first != current:
    print(
        "RESULT: HELD - Temporal's retry and the operator's retry after a continue-as-new all carried "
        + expected
    )
else:
    print(
        f"RESULT: BROKEN - expected three attempts with {expected} across a switch; got {keys}, switch: {first != current}"
    )
