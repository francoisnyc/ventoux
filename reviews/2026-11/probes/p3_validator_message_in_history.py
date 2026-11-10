# Shows a sensitive value written in clear in a case's history, its needs-attention line and its audit record when a contract's own validator refuses it and its message quotes it.
"""Run: uv run python reviews/2026-11/probes/p3_validator_message_in_history.py

An activity's failure is recorded as `‹sensitive›`, since "it may quote a sensitive value, and
Ventoux can't tell" (src/ventoux/core/interpreter.py, citing D31). A contract's model is the same
team's code: a validator on it (`@field_validator`) raising `ValueError(f"{value!r} is not …")`
is accepted at registration, and its message is copied by `one_line` into the refusal
(src/ventoux/core/before_activity.py) and the failed output's reason (src/ventoux/case/runtime.py).

Supported names: ActivityContract, Display, RetryPolicy, Timeouts. Past them: `Catalog`,
and `ventoux.testing.run_case`, the in-memory engine teams' tests use.
"""

from typing import Any

from pydantic import BaseModel, field_validator

from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.testing import run_case

NATIONAL_ID = "1 85 05 78 006 084 36"
DIAGNOSIS = "diagnosis F32.1"


class Asked(BaseModel):
    national_id: str

    @field_validator("national_id")
    @classmethod
    def shaped(cls, value: str) -> str:
        if " " in value:
            raise ValueError(f"{value!r} is not a national ID: write it without spaces")
        return value


class Found(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def known(cls, value: str) -> str:
        if value not in ("open", "closed"):
            raise ValueError(f"{value!r} is not a status")
        return value


class Plain(BaseModel):
    national_id: str


def contract(name: str, asked: type[BaseModel]) -> ActivityContract:
    return ActivityContract(
        name=name,
        version=1,
        input=asked,
        output=Found,
        risk="low",
        effect="read",
        timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
        retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
        idempotency_key=None,
        outcomes=[],
        display=Display(title="Look a person up", description="Reads a person's record."),
    )


catalog = Catalog()
catalog.register(contract("people.lookup", Asked))
catalog.register(contract("people.status", Plain))
catalog.register_role("claims-sensitive")


def claim(activity: str) -> dict[str, Any]:
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
                "display": {"title": "Look the person up"},
                "activity": activity,
                "inputs": {"national_id": {"var": "national_id"}},
            }
        },
    }


def places(run: Any, value: str) -> list[str]:
    found = []
    for name in ("history", "needs_attention", "audit"):
        if value in str(getattr(run, name)):
            found.append(name)
    return found


# 1. The input's validator refuses the sensitive value the step gives it.
first = run_case(claim("people.lookup@1"), {"national_id": NATIONAL_ID}, [], {}, catalog=catalog)
print("an input refused by the contract's validator:")
print("  history:", [line.replace(NATIONAL_ID, "<THE NATIONAL ID>") for line in first.history][-1])
print("  the national ID is in clear in:", places(first, NATIONAL_ID))

# 2. The output's validator refuses what the activity gave (a system's answer about the person).
second = run_case(
    claim("people.status@1"),
    {"national_id": "185057800608436"},
    [],
    {},
    catalog=catalog,
    activities={"people.status@1": lambda inputs: {"status": DIAGNOSIS}},
)
print("an output refused by the contract's validator:")
print(
    "  history:", [line.replace(DIAGNOSIS, "<WHAT THE SYSTEM GAVE>") for line in second.history][-1]
)
print("  what the system gave is in clear in:", places(second, DIAGNOSIS))


# 3. The same value quoted by the activity's own failure, for comparison.
def failing(inputs: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError(f"no record for {inputs['national_id']}")


third = run_case(
    claim("people.status@1"),
    {"national_id": NATIONAL_ID},
    [],
    {},
    catalog=catalog,
    activities={"people.status@1": failing},
)
print("the activity's own failure quoting it:", third.history[-1])

if places(first, NATIONAL_ID) or places(second, DIAGNOSIS):
    print(
        "RESULT: BROKEN - a contract validator's message is copied into the history, the "
        "needs-attention line and the audit record in clear, a sensitive field's value with it; "
        "an activity's failure quoting the same value reads ‹sensitive›"
    )
else:
    print("RESULT: HELD - a validator's message is never recorded")
