# Forgets a parent case while it has a change request pending, an activity running on a sensitive input, and an open child case with its own activity running: checks the key outlives every workflow of the family, and that the request's last record is written even though the store is down when the key goes.
"""Run: uv run python reviews/2026-11/probes/p1c_forget_family_in_flight.py

Supported names used: start_case, answer, report, propose_forget, answer_forget, forget_report,
read_audit, FileAudit, FileKeys, case_worker. Past them: `propose_change`, `case_handle`
(ventoux.temporal.cases), `ventoux.testing`, the tests' server harness, subclasses of the
development key file and store that note when the key is destroyed and can be down.
"""

import asyncio
import tempfile
import threading
import time
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal, until
from temporalio.client import WorkflowExecutionStatus

from ventoux.temporal.cases import case_handle, propose_change, start_case
from ventoux.temporal.forget import answer_forget, forget_report, propose_forget
from ventoux.testing import FAKES, DevelopmentCases, DevelopmentForget, release_of
from ventoux.tooling.audit import FileAudit, read_audit

SENSITIVE = {"sensitive": True, "visible_to": ["claims-sensitive"]}
NATIONAL_ID = "NATID-185-05-78-006"
RELEASE = threading.Event()  # set: the slow lookups may end
SEEN: list[tuple[float, object]] = []  # when each lookup ended, and what it had been given


def slow(inputs: dict[str, Any]) -> dict[str, Any]:
    RELEASE.wait(60)
    SEEN.append((time.time(), inputs["order_id"]))
    return {"status": "delivered"}


class Store(FileAudit):
    """The development store; down for the forget request's stream when told."""

    refuse_forget_stream = False
    refused = 0

    def append(self, records: list[dict[str, Any]]) -> None:
        if self.refuse_forget_stream and any(r["stream"].endswith("/forget") for r in records):
            Store.refused += 1
            raise OSError("the audit store is down")
        super().append(records)


def field(title: str, **more: Any) -> dict[str, Any]:
    return {"type": "string", "display": {"title": title}, **more}


def lookup(of: str) -> dict[str, Any]:
    return {
        "kind": "activity",
        "display": {"title": "Look it up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": of}},
    }


def parent() -> dict[str, Any]:
    return {
        "case": "kyc",
        "display": {"title": "Know your customer"},
        "fields": {"national_id": field("National ID", **SENSITIVE)},
        "steps": {
            "look": lookup("national_id"),
            "verify": {
                "kind": "case",
                "display": {"title": "Verify"},
                "case": "verify@1",
                "inputs": {"subject": {"var": "national_id"}},
            },
            "wait": {
                "kind": "task",
                "display": {"title": "Wait"},
                "roles": ["adjuster"],
                "outcomes": {"ok": {"display": {"title": "Fine"}}},
            },
        },
    }


def child() -> dict[str, Any]:
    return {
        "case": "verify",
        "display": {"title": "Verification"},
        "fields": {"subject": field("Subject", **SENSITIVE)},
        "steps": {
            "look": lookup("subject"),
            "check": {
                "kind": "task",
                "display": {"title": "Check"},
                "roles": ["adjuster"],
                "outcomes": {"ok": {"display": {"title": "Fine"}}},
            },
        },
    }


async def ended_at(setup: Setup, id: str) -> float:
    history = await setup.client.get_workflow_handle(id).fetch_history()
    return history.events[-1].event_time.ToMicroseconds() / 1e6


async def scenario(setup: Setup) -> list[str]:
    wrong: list[str] = []
    client = setup.client
    released = release_of(parent(), 1, cases={"verify@1": child()})
    case = await start_case(
        client, DevelopmentCases, released, {"national_id": NATIONAL_ID}, "kyc-1", QUEUE, "olga"
    )
    await until(case, lambda now: "verify#1: case verify, open" in now.waiting_for)
    kid = case_handle(client, DevelopmentCases, "kyc-1/verify#1")
    await until(kid, lambda now: now.waiting_at == ["check#1"])
    await propose_change(
        case, "edit", "national_id", "NATID-EDITED", "kim", ["claims-sensitive", "support"]
    )
    await until(case, lambda now: "case.change#1" in now.waiting_at)
    request = await propose_forget(client, DevelopmentForget, "kyc-1", "pat", ["privacy"], QUEUE)
    await answer_forget(request, "approve", "noor", ["privacy"])
    await until(case, lambda now: now.status in ("closing", "closed"))
    await until(kid, lambda now: now.status in ("closing", "closed"))
    await asyncio.sleep(2)  # real seconds, both lookups still running
    told = await forget_report(request)
    statuses = [(await handle.describe()).status for handle in (case, kid)]
    print(
        "with both lookups running: request",
        repr(told.status),
        "| key",
        setup.keys.state("kyc-1"),
        "| workflows",
        [s.name for s in statuses if s],
    )
    if setup.keys.state("kyc-1") != "kept":
        wrong.append("the key was destroyed while activities of the family were running")
    # The store goes down for the request's own stream; then the lookups end.
    setup.audit.refuse_forget_stream = True
    RELEASE.set()
    for _ in range(400):
        if setup.keys.state("kyc-1") == "destroyed":
            break
        await asyncio.sleep(0.05)
    destroyed = time.time()
    print("lookups were given:", [type(given).__name__ + ":" + str(given) for _, given in SEEN])
    for id in ("kyc-1", "kyc-1/verify#1"):
        status = (await client.get_workflow_handle(id).describe()).status
        print(f"when the key went, {id} was {status.name if status else None}")
        if status != WorkflowExecutionStatus.COMPLETED:
            wrong.append(f"{id} was still {status} when the key was destroyed")
    if any(ended > destroyed for ended, _ in SEEN):
        wrong.append("a lookup ended after the key was destroyed")
    for each in (case, kid):
        closed = await until(each, lambda now: now.status == "closed")
        print(f"{each.id}:", closed.history[-3:])
    # The request's last record ("key destroyed") can't be written yet; then the store is back.
    await asyncio.sleep(3)
    print(
        "the store refused the request's records",
        Store.refused,
        "times; request:",
        (await request.describe()).status.name,
    )
    setup.audit.refuse_forget_stream = False
    done = await asyncio.wait_for(request.result(), timeout=120)
    print("request ended:", done.status, "|", done.history[-1])
    stream = [
        r for r in read_audit(setup.audit, "kyc-1", [], setup.keys) if r["stream"] == "kyc-1/forget"
    ]
    kinds = [r["act"]["kind"] for r in stream]
    print("the request's stream:", kinds)
    if kinds[-1:] != ["key destroyed"]:
        wrong.append(f"the request's last record wasn't written: {kinds}")
    return wrong


store = Store(tempfile.mkdtemp(prefix="p1c-audit-"))
wrong = on_temporal(
    scenario, activities={**FAKES, "orders.lookup@1": slow}, audit=store, timeout=240
)
if wrong:
    print("RESULT: BROKEN - " + "; ".join(wrong))
else:
    print(
        "RESULT: HELD - the key outlived the parent's and the child's running work, both workflows had ended when it went, and the request's last record was written once the store was back"
    )
