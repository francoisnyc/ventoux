# Searches every history (parent across continue-as-new, child case, plan step, forget request), the audit store's files, the key file and the worker's log for the plain text of sensitive values, before and after the family is forgotten.
"""Run: uv run python reviews/2026-11/probes/p1c_plaintext_everywhere.py

One family on Temporal, each sensitive value planted with its own text, through every door a
value has: the opening, a task's form (a text, an option checked by an activity, an attachment
checked by its store), a rule's `set`, an activity's input and its failure's message, a plan
step's input and its plan's activity failing, a child case's opening, an approved edit, and a
form value given under a name that is no field. Then the family is forgotten, and everything is
read again.

Supported names used: start_case, answer, report, propose_forget, answer_forget, forget_report,
read_audit, FileKeys, FileAudit, data_converter, case_worker. Past them: `propose_change`, `view`,
`send_event`, `CaseForgotten` in ventoux.temporal.cases (client functions D79 names); the worker
log filter's logger names; `ventoux.testing`; the tests' server harness.
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from p1c_harness import (
    QUEUE,
    Setup,
    SwitchingCases,
    files_under,
    on_temporal,
    raw_histories,
    until,
    where,
)
from temporalio.exceptions import ApplicationError

from ventoux.temporal.cases import (
    CaseForgotten,
    answer,
    case_handle,
    propose_change,
    report,
    start_case,
    view,
)
from ventoux.temporal.forget import answer_forget, propose_forget
from ventoux.testing import FAKES, DevelopmentForget, release_of
from ventoux.tooling.audit import read_audit

SENSITIVE = {"sensitive": True, "visible_to": ["claims-sensitive"]}
PLANTED = {
    "national_id (opening)": "NATID-185-05-78-006",
    "tax_id (form)": "TAXID-FR-77-4410",
    "branch (sensitive option, form)": "BR-0142",
    "id_scan (sensitive attachment, form)": "doc-7f3a",
    "national_id (approved edit)": "NATID-EDITED-290-01",
    "stray (form value under no field)": "STRAY-1985-05-17",
}
NOT_SENSITIVE = {"notes (plain form field)": "NOTE-PLAIN-CALLBACK"}

PLAN: dict[str, Any] = {
    "plan": "check-id",
    "version": 1,
    "display": {"title": "Check an ID"},
    "fields": {"id": {"type": "string"}},
    "initial": "check",
    "states": {
        "check": {
            "activity": "orders.lookup@1",
            "inputs": {"order_id": {"var": "id"}},
            "on": {"done": "checked"},
        },
        "checked": {"final": "succeeded"},
    },
}


def text(title: str, **more: Any) -> dict[str, Any]:
    return {"type": "string", "display": {"title": title}, **more}


def kyc() -> dict[str, Any]:
    return {
        "case": "kyc",
        "display": {"title": "Know your customer"},
        "fields": {
            "customer_id": {"type": "reference", "system": "crm", "display": {"title": "Customer"}},
            "national_id": text("National ID", **SENSITIVE),
            "tax_id": text("Tax ID", **SENSITIVE),
            "branch": {"type": "option", "system": "branches", "display": {"title": "Branch"}}
            | SENSITIVE,
            "id_scan": {"type": "attachment", "store": "documents", "display": {"title": "Scan"}}
            | SENSITIVE,
            "id_copy": text("Copy of the ID", **SENSITIVE),
            "notes": text("Notes"),
        },
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess"},
                "roles": ["adjuster"],
                "outcomes": {
                    "accept": {
                        "display": {"title": "Accept"},
                        "sets": ["tax_id", "branch", "id_scan", "notes"],
                    }
                },
            },
            "lookup_id": {
                "kind": "activity",
                "display": {"title": "Look the ID up"},
                "activity": "orders.lookup@1",
                "requires": ["assess"],
                "inputs": {"order_id": {"var": "tax_id"}},
            },
            "check_id": {
                "kind": "plan",
                "display": {"title": "Check the ID"},
                "plan": "check-id@1",
                "requires": ["assess"],
                "inputs": {"id": {"var": "national_id"}},
            },
            "verify": {
                "kind": "case",
                "display": {"title": "Verify the person"},
                "case": "verify@1",
                "requires": ["assess"],
                "inputs": {"subject": {"var": "national_id"}},
            },
        },
        "rules": {
            "copy_id": {
                "display": {"title": "Keep a copy of the ID"},
                "on": {"answered": "assess"},
                "then": {"set": {"id_copy": {"var": "national_id"}}},
            }
        },
    }


def verify() -> dict[str, Any]:
    return {
        "case": "verify",
        "display": {"title": "Verification"},
        "fields": {"subject": text("Subject", **SENSITIVE), "result": text("Result")},
        "steps": {
            "check": {
                "kind": "task",
                "display": {"title": "Check"},
                "roles": ["adjuster"],
                "outcomes": {"ok": {"display": {"title": "Fine"}, "sets": ["result"]}},
            }
        },
        "reports": ["result"],
    }


def quoting(inputs: dict[str, Any]) -> dict[str, Any]:
    """A lookup that fails saying what it was given, as a careless system's error would."""
    raise ApplicationError(f"no record for {inputs['order_id']}", non_retryable=True)


class Kept(logging.Handler):
    """Every log record of the process, formatted as a handler would write it."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(logging.Formatter().format(record))


async def everything(setup: Setup, ids: list[str]) -> dict[str, bytes]:
    blobs: dict[str, bytes] = {}
    for id in ids:
        blobs |= await raw_histories(setup.client, id)
    blobs |= {f"audit store {n}": b for n, b in files_under(setup.audit.folder).items()}
    blobs |= {
        f"key folder {n}": b
        for n, b in files_under(setup.keys.path.parent).items()
        if not n.startswith("audit")
    }
    return blobs


async def scenario(setup: Setup) -> list[str]:
    found: list[str] = []
    client = setup.client
    released = release_of(kyc(), 1, plans=[PLAN], cases={"verify@1": verify()})
    file = {"customer_id": "cus-7", "national_id": PLANTED["national_id (opening)"]}
    case = await start_case(
        client, SwitchingCases, released, file, "kyc-1", QUEUE, "olga", ["adjuster"]
    )
    await until(case, lambda now: now.waiting_at == ["assess#1"])
    form = {
        "tax_id": PLANTED["tax_id (form)"],
        "branch": PLANTED["branch (sensitive option, form)"],
        "id_scan": PLANTED["id_scan (sensitive attachment, form)"],
        "notes": NOT_SENSITIVE["notes (plain form field)"],
    }
    # First an answer with one value under a name that is no field: refused, and recorded.
    stray = form | {"scratch": PLANTED["stray (form value under no field)"]}
    await answer(case, "assess#1", "accept", "ana", ["adjuster"], stray)
    await until(case, lambda now: any(line.startswith("refused ana") for line in now.history))
    await answer(case, "assess#1", "accept", "ana", ["adjuster"], form)
    await until(case, lambda now: "verify#1: case verify, open" in now.waiting_for)
    child = case_handle(client, SwitchingCases, "kyc-1/verify#1")
    await until(child, lambda now: now.waiting_at == ["check#1"])
    seen = await view(child, ["claims-sensitive"])
    print("child view for claims-sensitive holds subject:", "subject" in seen.values)
    # An approved edit of the sensitive field, proposed by one person, approved by another.
    edited = PLANTED["national_id (approved edit)"]
    await propose_change(
        case, "edit", "national_id", edited, "kim", ["claims-sensitive", "support"]
    )
    await until(case, lambda now: "case.change#1" in now.waiting_at)
    await answer(case, "case.change#1", "approve", "lee", ["claims-sensitive", "support-lead"])
    await until(
        case, lambda now: any(line.startswith("applied case.change#1") for line in now.history)
    )
    await answer(child, "check#1", "ok", "ana", ["adjuster"], {"result": "fine"})
    before = await until(
        case,
        lambda now: (
            len(now.needs_attention) == 2
            and "verify#1" not in " ".join(now.waiting_for)
            and now.unwritten == 0
        ),
    )
    print("parent, before forgetting:")
    for line in before.history:
        print("    ", line)
    print("  needs attention:", before.needs_attention)
    ids = ["kyc-1", "kyc-1/verify#1", "kyc-1/check_id#1"]
    for _ in range(100):  # the switch is the worker's to make, in its own time
        info = (await case.describe()).raw_description.workflow_execution_info
        if info.first_run_id != info.execution.run_id:
            break
        await asyncio.sleep(0.05)
    print("parent's first run", info.first_run_id, "| current run", info.execution.run_id)
    blobs = await everything(setup, ids)
    print(f"read {len(blobs)} histories and files before forgetting:", sorted(blobs))
    leaks = where(PLANTED, blobs)
    print("BEFORE forgetting, sensitive values in clear:", leaks or "none")
    found += [f"before forgetting: {leak}" for leak in leaks]
    print("  (not sensitive, expected in clear):", where(NOT_SENSITIVE, blobs))
    for roles in (["adjuster"], ["claims-sensitive"], []):
        shown = json.dumps(read_audit(setup.audit, "kyc-1", roles, setup.keys))
        seen_by = [what for what, value in PLANTED.items() if value in shown]
        print(f"  read_audit(roles={roles}) shows:", seen_by or "none of the planted values")
        if roles != ["claims-sensitive"]:
            found += [
                f"before forgetting: read_audit(roles={roles}) shows {what}" for what in seen_by
            ]

    # --- forget the family ---
    request = await propose_forget(client, DevelopmentForget, "kyc-1", "pat", ["privacy"], QUEUE)
    await answer_forget(request, "approve", "noor", ["privacy"])
    told = await asyncio.wait_for(request.result(), timeout=40)
    print("forget request:", told.status)
    for line in told.history:
        print("    ", line)
    print(
        "key state:", setup.keys.state("kyc-1"), "| key file:", setup.keys.path.read_text().strip()
    )
    blobs = await everything(setup, [*ids, "kyc-1/forget"])
    leaks = where(PLANTED, blobs)
    print("AFTER forgetting, sensitive values in clear:", leaks or "none")
    found += [f"after forgetting: {leak}" for leak in leaks]
    print("  (not sensitive, still in clear):", where(NOT_SENSITIVE, blobs))
    for roles in (["adjuster"], ["claims-sensitive"], []):
        shown = json.dumps(read_audit(setup.audit, "kyc-1", roles, setup.keys), ensure_ascii=False)
        seen_by = [what for what, value in PLANTED.items() if value in shown]
        print(
            f"  read_audit(roles={roles}) after: shows {seen_by or 'none'};",
            f"‹forgotten› {shown.count('‹forgotten›')} times, hidden {shown.count('hidden (needs')} times",
        )
        found += [f"after forgetting: read_audit(roles={roles}) shows {what}" for what in seen_by]
    try:
        await view(case, ["claims-sensitive"])
        found.append("after forgetting: the view was read")
    except CaseForgotten as refused:
        print("view after forgetting:", refused)
    for each in (case, child):
        closed = await report(each)
        print(
            f"report of {each.id} after forgetting: {closed.status}, last line: {closed.history[-1]}"
        )
    return found


kept = Kept()
logging.getLogger().addHandler(kept)
logging.getLogger().setLevel(logging.DEBUG)
# The process's own output too, where Temporal's core writes its warnings: kept in a file while
# the scenario runs, then printed.
output = Path(tempfile.mkdtemp(prefix="p1c-")) / "output.txt"
sys.stdout.flush()
saved = os.dup(1), os.dup(2)
with output.open("wb") as sink:
    os.dup2(sink.fileno(), 1)
    os.dup2(sink.fileno(), 2)
    try:
        found = on_temporal(
            scenario,
            cases=SwitchingCases,
            activities={**FAKES, "orders.lookup@1": quoting},
            timeout=120,
        )
    finally:
        sys.stdout.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        print(output.read_text())
logged = {
    "the worker's log": "\n".join(kept.lines).encode(),
    "the process's output": output.read_bytes(),
}
in_logs = where(PLANTED, logged)
print(
    f"log records kept: {len(kept.lines)}; core warnings in the output: {output.read_text().count(' WARN')};",
    "failed activities logged:",
    sum("Completing activity as failed" in line for line in kept.lines),
)
print("sensitive values in the log or stderr:", in_logs or "none")
found += in_logs
if found:
    print("RESULT: BROKEN - " + "; ".join(found))
else:
    print(
        "RESULT: HELD - no planted sensitive value was found in clear in any history, audit "
        "file, key file or log, before or after forgetting"
    )
