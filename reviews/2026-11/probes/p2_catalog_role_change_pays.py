# Shows, on a live test server, that a case decides its recorded answers again with the worker's catalog as it is NOW: an approval the case refused and recorded as refused is taken, and the payment made, once a worker with a changed role registration replays the history.
"""History records each answer with the roles its sender stated (brief, D22), so that a replay
decides as the first run did. What a role may do is not in the history: it is read from the
catalog on the workflow class, on every decision, replays included.

1. A case worker whose catalog lets `support-lead` approve low risk only. A large refund is
   reviewed; lee, a support-lead, approves the payment; the case refuses and records the refusal.
2. That worker stops. The platform team registers `support-lead` to approve high risk (the
   development catalog as it is) and a new worker starts: one deployment.
3. Any later signal makes the new worker replay the case. Does the refused approval stand?

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

from p2_time_classes import BeforeTheRoleChange  # noqa: E402
from skipping_server import time_skipping  # noqa: E402  (the tests' harness)
from worker_threads import worker_threads  # noqa: E402  (the tests' harness)

from ventoux.temporal.cases import answer, report, shown, start_case  # noqa: E402
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


async def main() -> bool:
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
        events_before = len((await case.fetch_history()).events)

        print("2. The worker is replaced by one whose catalog lets support-lead approve high risk.")
        async with worker_threads() as threads, worker(DevelopmentCases, threads):
            # 3. An unrelated act reaches the case: ana is shown a field. The worker replays.
            await shown(case, "order_id", "ana", ["support"])
            # Temporal: the task first waits for the worker that is gone (its sticky queue, 10 s);
            # the test server's clock is moved past that.
            await environment.sleep(20)
            after = await until(case, lambda now: now.status == "closed" or len(paid) > 0, 12)
            if after is not None and after.status != "closed":
                after = await until(case, lambda now: now.status == "closed", 12) or after
            history = await case.fetch_history()
        print("3. After one unrelated signal (a field shown to ana), the same case says:")
        for line in [] if after is None else after.history:
            if "pay" in line:
                print(f"     {line}")
        if after is None:
            print("     nothing: its report is no longer answered")
        else:
            print(f"     status {after.status}; waiting at {after.waiting_at}")
        print(f"     payments made: {len(paid)} ({[str(each) for each in paid]})")
        failures = [
            e.workflow_task_failed_event_attributes.failure.message[:300]
            for e in history.events
            if e.HasField("workflow_task_failed_event_attributes")
        ]
        print(f"     history: {events_before} events before, {len(history.events)} now; "
              f"workflow tasks failed: {len(failures)} {failures[:1]}")
        from temporalio.api.enums.v1 import EventType

        new = [EventType.Name(e.event_type).removeprefix("EVENT_TYPE_")
               for e in history.events[events_before:]]
        print(f"     the events since: {new}")
    return len(paid) > 0


if __name__ == "__main__":
    if asyncio.run(main()):
        print("RESULT: BROKEN - an approval the case refused, and recorded as refused, was taken "
              "on replay under the changed catalog, and the payment was made: no error, nobody "
              "asked again")
    else:
        print("RESULT: HELD - the refused approval stayed refused (or the replay was refused)")
