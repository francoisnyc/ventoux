# Shows three ordinary acts whose audit record the export refuses for good ("a sensitive field, in clear"), so the case can never end nor be forgotten: an event's payload key, an activity's output name, a refused unsealed answer.
"""Run: uv run python reviews/2026-11/probes/p1c_export_refused_for_good.py

The export checks a record's values by NAME against the case's sensitive fields (D77: "read from
the definition, never from the wrapper"). But a record's names are not all case fields: an event's
payload keys, an activity's output fields, an assignment's `to`. And a refused answer's values are
recorded as they came.

Supported names used: start_case, answer, retry_export, propose_forget, answer_forget,
forget_report. Past them: `ventoux.temporal.cases.send_event` (the client function D79 names for
events), a raw `answer` signal for scenario 3, `ventoux.testing`, the tests' server harness.
"""

import asyncio
from typing import Any

from p1c_harness import QUEUE, ImpatientCases, Setup, on_temporal, until

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.temporal.cases import retry_export, send_event, start_case
from ventoux.temporal.forget import answer_forget, forget_report, propose_forget
from ventoux.testing import CATALOG, DevelopmentForget

SENSITIVE = {"sensitive": True, "visible_to": ["claims-sensitive"]}


def claim(sets: bool = False, **fields: dict[str, Any]) -> dict[str, Any]:
    """A claim an adjuster assesses; with `sets`, accepting it gives the national ID."""
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {
            "customer_id": {"type": "reference", "system": "crm", "display": {"title": "Customer"}},
            **fields,
        },
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess"},
                "roles": ["adjuster"],
                "outcomes": {
                    "accept": {"display": {"title": "Accept"}, "sets": ["national_id"]}
                    if sets
                    else {"display": {"title": "Accept"}},
                    "deny": {"display": {"title": "Deny"}},
                },
            }
        },
    }


NATIONAL = {"national_id": {"type": "string", "display": {"title": "National ID"}, **SENSITIVE}}


def with_lookup() -> dict[str, Any]:
    """A case whose sensitive field is named `status`, and which calls `orders.lookup@1`, whose
    output is named `status` too."""
    definition = claim(status={"type": "string", "display": {"title": "Status"}, **SENSITIVE})
    definition["fields"]["order"] = {"type": "string", "display": {"title": "Order"}}
    definition["steps"]["look"] = {
        "kind": "activity",
        "display": {"title": "Look the order up"},
        "activity": "orders.lookup@1",
        "inputs": {"order_id": {"var": "order"}},
    }
    return definition


async def stuck(case: Any, label: str) -> bool:
    """Whether the case's export is refused, and refused again after an operator's retry."""
    first = await until(case, lambda now: any("in clear" in each for each in now.needs_attention))
    await retry_export(case, "omar", ["operations"])
    again = await until(
        case, lambda now: sum("audit export failed" in line for line in now.history) >= 2
    )
    print(f"{label}: history:")
    for line in again.history:
        print("    ", line)
    print(f"{label}: needs attention: {again.needs_attention}")
    return bool(first.needs_attention) and bool(again.needs_attention)


async def scenario(setup: Setup) -> list[str]:
    broken: list[str] = []
    for name, made in (("1/3", claim(**NATIONAL)), ("2", with_lookup())):
        issues = validate_case(parse_case(made), CATALOG)
        print(
            f"definition {name}: validation errors:",
            [i.code for i in issues if i.severity == "error"],
        )

    # 1. An event the case doesn't even declare, whose payload has a key named like the case's
    # sensitive field. The event is refused, rightly; its record then refuses the export.
    file = {"customer_id": "cus-7", "national_id": "1 85 05 78 006 084 36"}
    case = await start_case(setup.client, ImpatientCases, claim(**NATIONAL), file, "claim-1", QUEUE)
    await send_event(case, "ping", {"national_id": "x"}, "system:portal")
    if await stuck(case, "1 event"):
        broken.append("an event's payload key")
    # ... and so the person can't be forgotten: the request waits for a case that never ends.
    request = await propose_forget(
        setup.client, DevelopmentForget, "claim-1", "pat", ["privacy"], QUEUE
    )
    await answer_forget(request, "approve", "kim", ["privacy"])
    await until(case, lambda now: now.status == "closed")  # closed as forgotten, in name
    await asyncio.sleep(3)  # real seconds: the request's activity asks Temporal again and again
    told = await forget_report(request)
    now = await until(case, lambda now: True)
    print("1 forget request, approved:", told.status, "|", told.history[-1])
    print(
        "1 case:",
        now.status,
        "| unwritten",
        now.unwritten,
        "| workflow",
        (await case.describe()).status.name,
        "| key",
        setup.keys.state("claim-1"),
    )
    print("1 needs attention:", now.needs_attention)

    # 2. No outside input at all: an activity whose output field is named like a sensitive field.
    file2 = {"customer_id": "cus-7", "status": "vip", "order": "ord-1"}
    case = await start_case(setup.client, ImpatientCases, with_lookup(), file2, "claim-2", QUEUE)
    if await stuck(case, "2 activity output"):
        broken.append("an activity's output name")

    # 3. A raw `answer` signal whose sensitive value was not sealed: refused, as D31 says, and
    # then its record can never be written.
    file3 = {"customer_id": "cus-7"}
    asking = claim(sets=True, **NATIONAL)
    case = await start_case(setup.client, ImpatientCases, asking, file3, "claim-3", QUEUE)
    raw = {
        "entry": "assess#1",
        "outcome": "accept",
        "by": "ana",
        "roles": ["adjuster"],
        "form": {"national_id": "2 90 01 75 111 222 33"},
        "wording": None,
    }
    await setup.client.get_workflow_handle("claim-3").signal("answer", raw)
    if await stuck(case, "3 unsealed answer"):
        broken.append("a refused unsealed answer")
    return broken


broken = on_temporal(scenario, cases=ImpatientCases)
if broken:
    print(
        "RESULT: BROKEN - the audit export is refused for good, the case never ends and can't be "
        f"forgotten, after: {', '.join(broken)}"
    )
else:
    print("RESULT: HELD - each record was written or its act refused without stopping the export")
