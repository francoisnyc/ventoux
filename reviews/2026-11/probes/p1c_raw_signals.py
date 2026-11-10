# Sends malformed signals straight to a case workflow with Temporal's client (bypassing ventoux.temporal.cases) and says, for each, whether the case recorded a refusal, dropped it without a trace, accepted it, or stopped deciding.
"""Run: uv run python reviews/2026-11/probes/p1c_raw_signals.py

Each signal goes to its own fresh case. Afterwards a well-formed answer is sent: a case that no
longer decides it was poisoned by the signal before it.

Supported names used: start_case, answer, report, case_worker, data_converter. Past them: raw
signals through `temporalio`'s client and `RawValue`, `ventoux.testing`, the tests' harness.
"""

import asyncio
import json
from decimal import Decimal
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal, until
from temporalio.api.common.v1 import Payload
from temporalio.api.enums.v1 import EventType
from temporalio.common import RawValue

from ventoux.temporal.cases import answer, report, start_case
from ventoux.testing import DevelopmentCases


def refund() -> dict[str, Any]:
    return {
        "case": "refund",
        "display": {"title": "Refund"},
        "fields": {
            "amount": {"type": "number", "display": {"title": "Amount"}},
            "note": {"type": "string", "display": {"title": "Note"}},
            "due": {"type": "date", "display": {"title": "Due"}},
            "paid": {"type": "number", "display": {"title": "Paid"}},
            "national_id": {
                "type": "string",
                "sensitive": True,
                "visible_to": ["claims-sensitive"],
                "display": {"title": "National ID"},
            },
        },
        "events": {
            "cancelled": {
                "display": {"title": "The customer cancels"},
                "sent_by": {"system": "portal"},
                "payload": {
                    "why": {
                        "type": "string",
                        "display": {"title": "Why"},
                        "source": "untrusted:customer",
                    }
                },
            }
        },
        "steps": {
            "review": {
                "kind": "task",
                "display": {"title": "Review"},
                "roles": ["support"],
                "outcomes": {
                    "approve": {
                        "display": {"title": "Approve"},
                        "sets": ["note", "due", "paid", "national_id"],
                    },
                    "reject": {"display": {"title": "Reject"}},
                },
            }
        },
    }


def ans(**changes: Any) -> dict[str, Any]:
    base = {"entry": "review#1", "outcome": "reject", "by": "ana", "roles": ["support"],
            "form": None, "wording": None}
    return base | changes


def req(what: str, **changes: Any) -> dict[str, Any]:
    return {"what": what, "by": "ana", "roles": ["support"], "suggested_by": None} | changes


GOOD_FORM = {"note": "n", "due": "2026-12-01", "paid": 1.5, "national_id": "x"}
MIGRATION = {"name": "refund", "release": 2, "method": 1, "sha256": "00", "case": {}, "plans": {},
             "mapping": {}, "engine": 3, "by": "pat", "roles": ["platform"], "cases": {}}

# (label, signal name, the JSON text of its one argument)
ATTACKS: list[tuple[str, str, str]] = [
    ("answer: roles a text, not a list", "answer", json.dumps(ans(roles="support"))),
    ("answer: form a text", "answer", json.dumps(ans(form="x"))),
    ("answer: an extra key", "answer", json.dumps(ans(extra=1))),
    ("answer: no roles key", "answer", json.dumps({"entry": "review#1", "outcome": "reject", "by": "ana"})),
    ("answer: the argument is a list", "answer", "[1, 2]"),
    ("answer: wording a text", "answer", json.dumps(ans(wording="two"))),
    ("answer: wording -7", "answer", json.dumps(ans(wording=-7))),
    ("answer: entry review#x", "answer", json.dumps(ans(entry="review#x"))),
    ("answer: entry #", "answer", json.dumps(ans(entry="#"))),
    ("answer: entry empty", "answer", json.dumps(ans(entry=""))),
    ("answer: by 'Ana Lee'", "answer", json.dumps(ans(by="Ana Lee"))),
    ("answer: by empty", "answer", json.dumps(ans(by=""))),
    ("answer: outcome unknown", "answer", json.dumps(ans(outcome="maybe"))),
    ("answer: roles hold a number", "answer", json.dumps(ans(roles=[1]))),
    ("answer: form values unsealed, wrong kinds", "answer",
     json.dumps(ans(outcome="approve", form={"note": {"a": [1]}, "due": 7, "paid": "1", "national_id": None}))),
    ("answer: form value NaN", "answer",
     '{"entry": "review#1", "outcome": "reject", "by": "ana", "roles": ["support"], '
     '"form": {"note": NaN}, "wording": null}'),
    ("event: payload value Infinity", "event",
     '{"event": "cancelled", "payload": {"why": Infinity}, "by": "system:portal", "roles": []}'),
    ("change: edit amount to NaN", "change",
     '{"kind": "edit", "target": "amount", "value": NaN, "by": "ana", "roles": ["support"]}'),
    ("answer: a sensitive mark naming no part", "answer",
     json.dumps(ans(outcome="approve", form={"note": {"‹sensitive›": 7}}))),
    ("answer: form key that is no field", "answer", json.dumps(ans(outcome="approve", form=GOOD_FORM | {"zzz": 1}))),
    ("answer: due an impossible day", "answer", json.dumps(ans(outcome="approve", form=GOOD_FORM | {"due": "2026-02-31"}))),
    ("event: one the case doesn't declare", "event",
     json.dumps({"event": "exploded", "payload": {}, "by": "system:portal", "roles": []})),
    ("event: payload a list", "event",
     json.dumps({"event": "cancelled", "payload": [1], "by": "system:portal", "roles": []})),
    ("event: payload value an object", "event",
     json.dumps({"event": "cancelled", "payload": {"why": {"a": 1}}, "by": "system:portal", "roles": []})),
    ("event: payload key not declared", "event",
     json.dumps({"event": "cancelled", "payload": {"why": "w", "more": 1}, "by": "system:portal", "roles": []})),
    ("event: from a system nobody registered", "event",
     json.dumps({"event": "cancelled", "payload": {"why": "w"}, "by": "system:nobody", "roles": []})),
    ("event: by empty", "event", json.dumps({"event": "cancelled", "payload": {"why": "w"}, "by": "", "roles": []})),
    ("change: kind delete", "change",
     json.dumps({"kind": "delete", "target": "amount", "value": 1, "by": "ana", "roles": ["support"]})),
    ("change: edit of no field", "change",
     json.dumps({"kind": "edit", "target": "nothing", "value": 1, "by": "ana", "roles": ["support"]})),
    ("change: edit amount to an object, unsealed", "change",
     json.dumps({"kind": "edit", "target": "amount", "value": {"a": 1}, "by": "ana", "roles": ["support"]})),
    ("change: edit a sensitive field, unsealed", "change",
     json.dumps({"kind": "edit", "target": "national_id", "value": "plain", "by": "ana", "roles": ["support", "claims-sensitive"]})),
    ("change: edit due to 'soon'", "change",
     json.dumps({"kind": "edit", "target": "due", "value": "soon", "by": "ana", "roles": ["support"]})),
    ("change: skip a run that isn't one", "change",
     json.dumps({"kind": "skip", "target": "review#zz", "value": None, "by": "ana", "roles": ["support"]})),
    ("change: kind migrate, value a text", "change",
     json.dumps({"kind": "migrate", "target": "refund 2", "value": "x", "by": "pat", "roles": ["platform"]})),
    ("migrate: an empty definition", "migrate", json.dumps(MIGRATION)),
    ("migrate: engine 99", "migrate", json.dumps(MIGRATION | {"engine": 99})),
    ("migrate: engine a text", "migrate", json.dumps(MIGRATION | {"engine": "3"})),
    ("migrate: method 99", "migrate", json.dumps(MIGRATION | {"method": 99})),
    ("migrate: mapping of an unknown kind", "migrate", json.dumps(MIGRATION | {"mapping": {"bogus": {"a": "b"}}})),
    ("migrate: release -1", "migrate", json.dumps(MIGRATION | {"release": -1})),
    ("propose: no such step", "propose", json.dumps(req("nothing"))),
    ("propose: suggested by evil-bot", "propose", json.dumps(req("review", suggested_by="evil-bot"))),
    ("retry: a run that isn't one", "retry", json.dumps(req("review#zz"))),
    ("retry_export: nothing failed", "retry_export", json.dumps(req("audit export", roles=["operations"]))),
    ("claim: entry with two #", "claim", json.dumps(req("review#1#1"))),
    ("give_back: nothing held", "give_back", json.dumps(req("review#1"))),
    ("assign: to 'Bad Name'", "assign",
     json.dumps({"entry": "review#1", "to": "Bad Name", "to_roles": ["support"], "by": "sam", "roles": ["support-lead"]})),
    ("unassign: nothing held", "unassign", json.dumps(req("review#1", by="sam", roles=["support-lead"]))),
    ("close: a reason nobody declared", "close", json.dumps(req("because"))),
    ("shown: no such field", "shown", json.dumps(req("nothing"))),
    ("forget: sent to the case directly, one person both", "forget",
     json.dumps({"proposed_by": "pat", "proposer_roles": ["privacy"], "approved_by": "pat", "approver_roles": ["privacy"]})),
    ("forget: sent to the case directly, without the role", "forget",
     json.dumps({"proposed_by": "pat", "proposer_roles": ["support"], "approved_by": "noor", "approver_roles": ["support"]})),
    ("child_ended: a number", "child_ended", "7"),
    ("child_ended: no such entry", "child_ended", '"zz#1"'),
    ("close_by_parent: to a case with no parent", "close_by_parent", '"mischief"'),
    ("a signal nobody declared", "bogus", '{"x": 1}'),
]


async def failed_tasks(setup: Setup, id: str) -> int:
    history = await setup.client.get_workflow_handle(id).fetch_history()
    return sum(event.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED for event in history.events)


async def one(setup: Setup, n: int, label: str, signal: str, text: str) -> tuple[str, str]:
    id = f"refund-{n}"
    case = await start_case(setup.client, DevelopmentCases, refund(), {"amount": Decimal(40)}, id, QUEUE)
    opened = await until(case, lambda now: now.waiting_at == ["review#1"])
    raw = RawValue(Payload(metadata={"encoding": b"json/plain"}, data=text.encode()))
    await setup.client.get_workflow_handle(id).signal(signal, raw)
    # Then a well-formed answer: whether the case still decides.
    await answer(case, "review#1", "reject", "ana", ["support"])
    now = None
    for _ in range(10):
        try:
            now = await asyncio.wait_for(report(case), timeout=1)
        except Exception:  # noqa: BLE001 (whatever a case that no longer answers says)
            now = None
            continue
        if now.status == "closed":
            break
        await asyncio.sleep(0.05)
    failures = await failed_tasks(setup, id)
    if now is None or now.status != "closed":
        return "POISONED", (
            f"the case no longer decides nor answers: {failures} failed workflow tasks so far, "
            "and the well-formed answer sent after it is never decided"
        )
    added = now.history[len(opened.history) :]
    mine = "ana answered review#1 reject as support"
    closed_first = any("the case is closed" in line for line in added)
    others = [line for line in added if line != mine and not line.startswith(("review#1 done", "closed: nothing"))]
    if failures:
        return "TASK FAILED", f"{failures} failed workflow tasks, then: {others}"
    # A doorbell for no open child is recorded and changes nothing, as D75 says.
    noted = ("refused", "child_ended for")
    if closed_first or any(not line.startswith(noted) for line in others):
        return "ACCEPTED", "; ".join(others)
    if others:
        return "refused, recorded", others[0]
    return "DROPPED, no trace", "the send succeeded; the history gained no line and no record"


async def scenario(setup: Setup) -> dict[str, list[str]]:
    counts: dict[str, list[str]] = {}
    for n, (label, signal, text) in enumerate(ATTACKS, start=1):
        try:
            verdict, detail = await asyncio.wait_for(one(setup, n, label, signal, text), timeout=30)
        except Exception as error:  # noqa: BLE001
            verdict, detail = "PROBE ERROR", f"{type(error).__name__}: {error}"
        counts.setdefault(verdict, []).append(label)
        print(f"{verdict:18} | {label:48} | {detail[:230]}")
    return counts


counts = on_temporal(scenario, timeout=900)
print()
for verdict, labels in counts.items():
    print(f"{verdict}: {len(labels)}")
bad = {v: l for v, l in counts.items() if v != "refused, recorded"}
if bad:
    print("RESULT: BROKEN - " + "; ".join(f"{v}: {', '.join(l)}" for v, l in bad.items()))
else:
    print("RESULT: HELD - every malformed signal was refused and recorded, and the case went on")
