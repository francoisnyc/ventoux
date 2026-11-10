# Shows where an activity failure's parts land in the case's history when the activity's code quotes its sensitive input: the message (sealed), and the failure's `details` and `type` (not sealed).
"""Run: uv run python reviews/2026-11/probes/p1c_failure_details.py

Supported names used: start_case, case_worker, data_converter. Past them: `ventoux.testing`, the
tests' server harness.
"""

from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal, raw_histories, until
from temporalio.exceptions import ApplicationError

from ventoux.temporal.cases import start_case
from ventoux.testing import FAKES, DevelopmentCases

IN_MESSAGE, IN_DETAILS, IN_TYPE = "MSG-185-05", "DETAIL-185-05", "TYPE-185-05"


def quoting(inputs: dict[str, Any]) -> dict[str, Any]:
    """Fails as an integrator's code might: the record it couldn't find goes in the message, in
    the details (Temporal's place for data about a failure) and in the type."""
    given = inputs["order_id"]
    raise ApplicationError(
        f"no record for MSG-{given}",
        {"looked_up": f"DETAIL-{given}"},
        type=f"NoRecord:TYPE-{given}",
        non_retryable=True,
    )


def claim() -> dict[str, Any]:
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {
            "national_id": {
                "type": "string",
                "sensitive": True,
                "visible_to": ["claims-sensitive"],
                "display": {"title": "National ID"},
            }
        },
        "steps": {
            "look": {
                "kind": "activity",
                "display": {"title": "Look the ID up"},
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "national_id"}},
            }
        },
    }


async def scenario(setup: Setup) -> tuple[list[str], dict[str, bytes]]:
    case = await start_case(
        setup.client, DevelopmentCases, claim(), {"national_id": "185-05"}, "claim-1", QUEUE
    )
    failed = await until(case, lambda now: bool(now.needs_attention))
    return failed.needs_attention, await raw_histories(setup.client, "claim-1")


attention, blobs = on_temporal(scenario, activities={**FAKES, "orders.lookup@1": quoting})
print("the case says:", attention)
found = {
    name: any(value.encode() in blob for blob in blobs.values())
    for name, value in (("message", IN_MESSAGE), ("details", IN_DETAILS), ("type", IN_TYPE))
}
for name, clear in found.items():
    print(
        f"the failure's {name}: {'IN PLAIN TEXT in the history' if clear else 'not in the history in plain text'}"
    )
if found["message"]:
    print("RESULT: BROKEN - an activity failure's message is in the history in plain text")
elif found["details"] or found["type"]:
    print(
        "RESULT: BROKEN - an activity failure's message is sealed, but its "
        + " and ".join(name for name in ("details", "type") if found[name])
        + " cross Temporal in plain text, in the history and in the case's own line"
    )
else:
    print("RESULT: HELD - no part of the activity's failure is in the history in plain text")
