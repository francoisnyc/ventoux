# Shows what the audit export does with a plan step's inputs, which it records under the PLAN's input names: (A) a `visible_to` value read by every role, (B) a plain value named like a sensitive case field refusing the export for good.
"""Run: uv run python reviews/2026-11/probes/p1c_plan_step_audit_names.py

Supported names used: start_case, answer, retry_export, read_audit, FileAudit, FileKeys,
data_converter, case_worker. Past them: `ventoux.testing` (catalog, workflows, release_of) and the
tests' server harness, through p1c_harness.
"""

import json
from typing import Any

from p1c_harness import QUEUE, ImpatientCases, Setup, on_temporal, until

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.temporal.cases import retry_export, start_case
from ventoux.testing import CATALOG, release_of
from ventoux.tooling.audit import read_audit

SECRET = "WATCHLIST-HIT-9931"

PLAN: dict[str, Any] = {
    "plan": "check-ref",
    "version": 1,
    "display": {"title": "Check a reference"},
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


def case_a() -> dict[str, Any]:
    """`watchlist_ref` is seen by `fraud` only; a plan step is given it."""
    return {
        "case": "screening",
        "display": {"title": "Screening"},
        "fields": {
            "watchlist_ref": {
                "type": "string",
                "visible_to": ["fraud"],
                "display": {"title": "Watchlist reference"},
            },
        },
        "steps": {
            "check": {
                "kind": "plan",
                "display": {"title": "Check the reference"},
                "plan": "check-ref@1",
                "inputs": {"id": {"var": "watchlist_ref"}},
            },
        },
    }


def case_b() -> dict[str, Any]:
    """`order_id` is a sensitive field of the case; the plan step is given another, plain field,
    which the plan passes to its activity's input `order_id`."""
    return {
        "case": "lookup",
        "display": {"title": "Lookup"},
        "fields": {
            "order_id": {
                "type": "string",
                "sensitive": True,
                "visible_to": ["claims-sensitive"],
                "display": {"title": "Order"},
            },
            "public_ref": {"type": "string", "display": {"title": "Public reference"}},
        },
        "steps": {
            "check": {
                "kind": "plan",
                "display": {"title": "Check the reference"},
                "plan": "check-ref@1",
                "inputs": {"id": {"var": "public_ref"}},
            },
        },
    }


async def scenario(setup: Setup) -> tuple[list[str], list[str]]:
    said: list[str] = []
    # Both packages pass case validation (reached past the supported names: validate_case).
    for name, made in (("A", case_a()), ("B", case_b())):
        issues = validate_case(parse_case(made), CATALOG, {"check-ref@1": PLAN})
        errors = [issue.code for issue in issues if issue.severity == "error"]
        print(f"{name}: validation errors: {errors}")
    # --- A ---
    release = release_of(case_a(), 1, plans=[PLAN])
    case = await start_case(
        setup.client, ImpatientCases, release, {"watchlist_ref": SECRET}, "screen-1", QUEUE
    )
    ended = await until(case, lambda now: now.status == "closed")
    print("A: case history:", *ended.history, sep="\n   ")
    for roles in (["adjuster"], [], ["fraud"]):
        rows = read_audit(setup.audit, "screen-1", roles, setup.keys)
        shown = json.dumps(rows)
        print(f"A: read_audit(roles={roles}) shows the value in clear: {SECRET in shown}")
        for row in rows:
            for decision in row["decisions"]:
                for fact in decision["read"]:
                    print(f"   record {row['number']} {decision['kind']:9} read {fact}")
        if roles != ["fraud"] and SECRET in shown:
            said.append(f"read_audit(roles={roles}) shows watchlist_ref's value")
    # --- B ---
    release = release_of(case_b(), 1, plans=[PLAN])
    file = {"order_id": "ord-secret-1", "public_ref": "ref-public-1"}
    case = await start_case(setup.client, ImpatientCases, release, file, "lookup-1", QUEUE)
    stuck = await until(case, lambda now: bool(now.needs_attention))
    print("B: needs attention:", stuck.needs_attention, "unwritten:", stuck.unwritten)
    await retry_export(case, "ops", ["operations"])
    again = await until(
        case, lambda now: sum("audit export" in line for line in now.history) >= 3, tries=200
    )
    print("B: after an operator's retry_export:")
    for line in again.history:
        if "export" in line:
            print("   ", line)
    print("B: status", again.status, "| needs attention:", again.needs_attention)
    described = await case.describe()
    print("B: its workflow is", described.status.name, "(closed in name, never ended)")
    brick = [line for line in again.needs_attention if "in clear" in line]
    return said, brick


said, brick = on_temporal(scenario)
if said or brick:
    print(
        "RESULT: BROKEN - a plan step's inputs are recorded under the plan's input names: "
        f"{'; '.join(said) or 'no leak seen'}; and a plain input named like a sensitive case "
        f"field refuses the export after every retry: {brick}"
    )
else:
    print("RESULT: HELD - plan step inputs were hidden as their case fields are, and exported")
