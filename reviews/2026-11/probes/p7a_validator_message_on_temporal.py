# Shows whether finding 3.3 (a contract validator's message quoting a sensitive value, recorded in clear) reproduces on Temporal: in the case's report, in the raw workflow history bytes, and in the audit store's files.
"""Run: uv run python reviews/2026-11/probes/p7a_validator_message_on_temporal.py

The catalog, the contracts with their validators, the definition and the two values are those of
`p3_validator_message_in_history.py`. The case runs as a `ventoux.case` workflow naming that
catalog (`p7a_workflows.ValidatedCases`), on the time-skipping test server, with the supported
converter (`data_converter`, a case key per case) and a `FileAudit` store in a temporary folder.
The raw history is searched as the pass 1c probes search it (`p1c_harness.raw_histories`).
Reaches past the supported names as `p7a_harness.py` says, and for `Catalog`.
"""

import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from p1c_harness import Setup, files_under, on_temporal, raw_histories, where
from p7a_harness import Verdicts, open_case, pass_time, quiet, quietly
from p7a_workflows import ValidatedCases
from temporalio import activity
from temporalio.api.enums.v1 import EventType

from ventoux.tooling.audit import FileAudit

in_memory = quietly("p3_validator_message_in_history")
NATIONAL_ID: str = in_memory.NATIONAL_ID  # the sensitive field's value, with spaces
DIAGNOSIS: str = in_memory.DIAGNOSIS  # what the system answers about the person
PLANTED = {"the national ID": NATIONAL_ID, "what the system gave": DIAGNOSIS}
given: list[tuple[str, dict[str, Any]]] = []  # what the activity worker was really given
verdicts = Verdicts()


def lookup(inputs: dict[str, Any]) -> dict[str, Any]:
    given.append((activity.info().workflow_id, dict(inputs)))
    return {"status": "open"}


def status(inputs: dict[str, Any]) -> dict[str, Any]:
    # Temporal: inside an activity, `activity.info()` says which workflow scheduled it.
    case = activity.info().workflow_id
    given.append((case, dict(inputs)))
    if case == "val-fails":  # the comparison: the activity's own failure quotes the value
        raise RuntimeError(f"no record for {inputs['national_id']}")
    return {"status": DIAGNOSIS}


def redacted(text: str) -> str:
    return text.replace(NATIONAL_ID, "<THE NATIONAL ID>").replace(DIAGNOSIS, "<WHAT THE SYSTEM GAVE>")


async def failed(setup: Setup, case: Any) -> Any:
    """The case's report once its step has failed for good (Temporal's retries skipped)."""
    for _ in range(40):
        now = await quiet(case, still=0.7)
        if now.needs_attention and not now.unwritten:
            return now
        await pass_time(setup, 1 / 24)
    return now


async def events_holding(setup: Setup, id: str, value: str) -> list[str]:
    """Each event of the case's history whose bytes hold `value` in clear."""
    history = await setup.client.get_workflow_handle(id).fetch_history()
    found = []
    for event in history.events:
        if value.encode() in event.SerializeToString():
            kind = EventType.Name(event.event_type).removeprefix("EVENT_TYPE_")
            activity_type = event.activity_task_scheduled_event_attributes.activity_type.name
            found.append(f"event {event.event_id} {kind} {activity_type}".strip())
    return found


async def scenario(setup: Setup) -> dict[str, dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    runs = (
        ("val-input", "people.lookup@1", NATIONAL_ID, NATIONAL_ID),
        ("val-output", "people.status@1", "185057800608436", DIAGNOSIS),
        ("val-fails", "people.status@1", NATIONAL_ID, NATIONAL_ID),
    )
    for id, contract, national_id, marker in runs:
        definition = in_memory.claim(contract)
        case = await open_case(setup, definition, {"national_id": national_id}, id, workflow=ValidatedCases)
        now = await failed(setup, case)
        raw = await raw_histories(setup.client, id)
        seen[id] = {
            "report": [name for name in ("history", "needs_attention") if marker in str(getattr(now, name))],
            "raw": where({"marker": marker}, raw),
            "events": await events_holding(setup, id, marker),
            "unwritten": now.unwritten,
            "last": redacted(now.history[-1]),
            "worker": [inputs for case_id, inputs in given if case_id == id],
        }
    return seen


folder = Path(tempfile.mkdtemp(prefix="p7a-audit-"))
seen = on_temporal(
    scenario,
    cases=ValidatedCases,
    activities={"people.lookup@1": lookup, "people.status@1": status},
    audit=FileAudit(folder),
    timeout=300,
)
files = files_under(folder)
titles = {
    "val-input": "an input refused by the contract's validator (the sensitive field's value)",
    "val-output": "an output refused by the contract's validator (what the system gave)",
    "val-fails": "comparison: the activity's own failure quoting the sensitive value",
}
in_audit = {}
for id, title in titles.items():
    marker = DIAGNOSIS if id == "val-output" else NATIONAL_ID
    in_audit[id] = [name for name, blob in files.items() if id in name and marker.encode() in blob]
    one = seen[id]
    print(f"=== {title} (case {id})")
    print("    last line of the report's history:", one["last"])
    print("    in clear in the case's report:", one["report"] or "nowhere")
    print("    in clear in the raw workflow history:", one["raw"] or "nowhere", "|", one["events"] or "no event")
    print("    in clear in the audit store's files:", in_audit[id] or "nowhere", f"(records not yet written: {one['unwritten']})")
    print("    the activity worker was called", len(one["worker"]), "times")
print("audit files written:", sorted(files))

places = []
for id in ("val-input", "val-output"):
    one = seen[id]
    for name, found in (("report", one["report"]), ("raw history", one["raw"]), ("audit file", in_audit[id])):
        if found:
            places.append(f"{id}: {name}")
compared = seen["val-fails"]
clean = not compared["report"] and not in_audit["val-fails"]
if places:
    verdicts.say(
        "3.3",
        "REPRODUCED",
        "the validator's message, the value in clear, is in: " + "; ".join(places)
        + f". The activity's own failure quoting the same value reads ‹sensitive› in the report "
        f"and the audit file ({clean}); in its raw history the value is at: "
        f"{compared['events'] or 'no event'}",
    )
else:
    verdicts.say("3.3", "NOT REPRODUCED", "neither value is in clear in a report, a raw history or an audit file")
verdicts.result()
