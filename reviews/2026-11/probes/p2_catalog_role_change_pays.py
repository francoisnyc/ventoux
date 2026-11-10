# Shows, on a live test server, that a case decides its recorded answers again with the worker's catalog as it is NOW: an approval the case refused and recorded as refused is taken, and the payment made, once a worker with a changed role registration replays the history.
"""History records each answer with the roles its sender stated (brief, D22), so that a replay
decides as the first run did. What a role may do is not in the history: it is read from the
catalog on the workflow class, on every decision, replays included.

1. A case worker whose catalog lets `support-lead` approve low risk only. A large refund is
   reviewed; lee, a support-lead, approves the payment; the case refuses and records the refusal.
2. That worker stops. The platform team registers `support-lead` to approve high risk (the
   development catalog as it is) and a new worker starts: one deployment.
3. The case's history is replayed with that worker's class, as the worker would on its next
   workflow task. Does the refused approval stand? (Shown with Temporal's Replayer: a live second
   worker on the test server did not pick the task up within the probe's bound, so what the
   server then does with the extra command is not shown here.)

Reaches past the supported names for the tests' harness (the time-skipping server, the worker's
threads), `ventoux.testing`'s development catalog, fakes and converter, and p2_time_classes.py."""

import asyncio
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from p2_time_classes import BeforeTheRoleChange  # noqa: E402
from skipping_server import time_skipping  # noqa: E402  (the tests' harness)
from worker_threads import worker_threads  # noqa: E402  (the tests' harness)

from ventoux.temporal.cases import answer, report, start_case  # noqa: E402
from ventoux.temporal.converter import data_converter  # noqa: E402
from ventoux.temporal.worker import case_worker  # noqa: E402
from ventoux.testing import (  # noqa: E402
    FAKES,
    DevelopmentCases,
    DevelopmentPlans,
    load_definition,
)
from ventoux.tooling.audit import FileAudit  # noqa: E402
from ventoux.tooling.keys import FileKeys  # noqa: E402

QUEUE = "cases"
REFUND = load_definition(ROOT / "examples" / "refund" / "refund.json")
paid: list[Any] = []


def paying(inputs: dict[str, Any]) -> dict[str, Any]:
    paid.append(inputs["amount"])
    return {"refund_id": "refund-ord-1"}


async def until(case: Any, holds: Any, tries: int = 200) -> Any:
    now = None
    for _ in range(tries):
        try:
            now = await asyncio.wait_for(report(case), timeout=5)
        except TimeoutError:
            continue
        if holds(now):
            return now
        await asyncio.sleep(0.05)
    return now


async def main() -> Any:
    folder = Path(tempfile.mkdtemp(prefix="p2-roles-"))
    store = FileAudit(folder / "audit")
    activities = {**FAKES, "payments.refund@2": paying}
    async with time_skipping(data_converter(FileKeys(folder / "keys.json"))) as environment:
        client = environment.client

        def worker(cases: Any, threads: Any) -> Any:
            return case_worker(client, QUEUE, cases, DevelopmentPlans, activities,
                               activity_executor=threads, audit=store)

        async with worker_threads() as threads, worker(BeforeTheRoleChange, threads):
            file = {"order_id": "ord-1", "amount": Decimal(250)}
            case = await start_case(client, BeforeTheRoleChange, REFUND, file, "refund-1", QUEUE)
            form = {"approved_amount": Decimal(250)}
            await answer(case, "review#1", "approve", "ana", ["support"], form)
            await until(case, lambda now: now.waiting_at == ["pay.approval#1"])
            await answer(case, "pay.approval#1", "approve", "lee", ["support-lead"])
            before = await until(case, lambda now: any("refused lee" in l for l in now.history))
        print("1. With the catalog where support-lead approves low risk only, the case said:")
        for line in before.history:
            if "pay" in line:
                print(f"     {line}")
        print(f"     waiting at {before.waiting_at}; payments made: {len(paid)}")
        history = await case.fetch_history()
        converter = client.data_converter
    return history, converter


def replay(history: Any, converter: Any) -> bool:
    import json

    from p2_harness import replayed, run

    print("2. The same history, replayed by a worker whose catalog lets support-lead approve "
          "high risk\n   (the development catalog as it is):")
    seen = run(replayed(history, [DevelopmentCases], converter))
    state = json.loads(seen["state"][0])
    for line in state["history"]:
        if "pay" in line:
            print(f"     {line}")
    asked = [each["type"] for each in seen["activities"]]
    print(f"     replay error: {seen['failure']}; waiting at {state['waiting_at']}")
    print(f"     activities the replay asks Temporal for: {asked}")
    return seen["failure"] is None and "payments.refund@2" in asked


if __name__ == "__main__":
    if replay(*asyncio.run(main())):
        print("RESULT: BROKEN - an approval the case refused, and recorded as refused, is taken "
              "on replay under the changed catalog, and the replay asks for the payment, with no "
              "replay error")
    else:
        print("RESULT: HELD - the refused approval stayed refused (or the replay was refused)")
