# Shows read_audit handing a value to a reader who holds none of its roles when the stored value's shape is one it doesn't know (the hidden shape plus one more key), instead of refusing it.
"""Run: uv run python reviews/2026-11/probes/p3_audit_unknown_shape_in_clear.py

`shown` in src/ventoux/tooling/audit.py filters a value only when its keys are exactly
`{value, visible_to}` or `{sealed, part, visible_to}`; any other dict "is in clear: seen by whoever
reads the case's records". So a record written in a shape this reader doesn't know (a later
writer's, or a damaged one) is passed on whole. Past the supported names: `ventoux.tooling.audit`
(`FileAudit`, `read_audit`) and `ventoux.tooling.keys.FileKeys`, the development providers.
"""

import json
import tempfile
from pathlib import Path

from ventoux.tooling.audit import FileAudit, read_audit
from ventoux.tooling.keys import FileKeys

VALUE = "fraud score 97"
folder = Path(tempfile.mkdtemp(prefix="p3-audit-"))
keys = FileKeys(folder / "keys.json")
keys.create("claim-7")


def record(number: int, value: object) -> dict[str, object]:
    act = {"kind": "opened", "by": None, "roles": [], "values": {"fraud_score": value}}
    return {"stream": "claim-7", "number": number, "act": act, "decisions": []}


known = {"value": VALUE, "visible_to": ["fraud"]}
unknown = {"value": VALUE, "visible_to": ["fraud"], "written_by": 4}  # one key more
(folder / "audit").mkdir()
(folder / "audit" / "claim-7.jsonl").write_text(
    json.dumps(record(1, known)) + "\n" + json.dumps(record(2, unknown)) + "\n"
)
read = read_audit(FileAudit(folder / "audit"), "claim-7", ["support"], keys)
first, second = (each["act"]["values"]["fraud_score"] for each in read)  # type: ignore[index]
print("a reader holding only `support` reads:")
print("  the known shape  :", first)
print("  the unknown shape:", second)
if VALUE in json.dumps(second):
    print(
        "RESULT: BROKEN - a value whose stored shape read_audit doesn't know is handed to a reader "
        "without its roles, in clear, where the known shape is hidden"
    )
else:
    print("RESULT: HELD - a shape read_audit doesn't know is refused or hidden")
