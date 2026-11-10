# Shows a worker's manifest file and a release record being read with keys nobody declares ignored, and "no" read as false, where every definition refuses an unknown key.
"""Run: uv run python reviews/2026-11/probes/p3_unknown_keys_ignored.py

`ventoux manifest publish FILE` reads the file with `MANIFEST` and `FolderStore` reads a record
with `RECORD` (pydantic `TypeAdapter`s over plain dataclasses, which ignore extra keys and
convert loosely). Past the supported names: those two adapters, as the commands use them.
"""

from ventoux.tooling.environments import MANIFEST
from ventoux.tooling.releases import RECORD

digest = {"method": 1, "sha256": "ab" * 32}
manifest = {
    "environment": "production",
    "task_queue": "cases",
    "build": "b1",
    "identity": "w1",
    "serves": {"payments.refund@2": digest},
    "workflows": ["CaseWorkflow"],
    "case": "CaseWorkflow",
    "keys": {"name": "FileKeys", "development": "no", "address": "somewhere"},
    "audit": {"name": "FileAudit", "development": 0},
    "bindz": {"kyc.check@1": {"workflow": "Kyc", "task_queue": "kyc"}},  # `binds`, misspelt
}
read = MANIFEST.validate_python(manifest)
print("manifest read:", "keys", read.keys, "| audit", read.audit, "| binds", read.binds)
record = {
    "name": "refund",
    "release": 1,
    "wording": 1,
    "digest": digest,
    "commit": "c1",
    "contracts": {},
    "written": {"case": "{}", "plans": {}},
    "retired": True,
    "format": 99,
}
kept = RECORD.validate_python(record)
print("record read:", kept.name, kept.release, "(the keys `retired` and `format` said nothing)")
if read.keys is not None and read.keys.development is False and not read.binds:
    print(
        "RESULT: BROKEN - a manifest's and a record's unknown keys are ignored (a misspelt `binds` "
        'binds nothing), and `"development": "no"` reads as false'
    )
else:
    print("RESULT: HELD - an unknown key in a manifest or a record is refused")
