"""Stand-ins for a deployment's production key service and audit store, for the tests that run a
production environment (layer 20b1) (brief, D81).

A production environment's registry refuses a case worker whose keys or audit records are kept by
a development provider, so these tests' workers say they are not. Underneath, they are the
development ones: keys in a file, records in local files. They live in `tests/` only, never in
`ventoux.testing`, so no deployment can import one and pass a file for a key service.
"""

import tempfile
from pathlib import Path

from temporalio.converter import DataConverter

from ventoux.temporal.converter import data_converter
from ventoux.tooling.audit import FileAudit
from ventoux.tooling.keys import FileKeys


class StandInKeys(FileKeys):
    """Stands for a deployment's key service: `FileKeys`, saying it isn't for development."""

    development = False


class StandInAudit(FileAudit):
    """Stands for a deployment's audit store: `FileAudit`, saying it isn't for development."""

    development = False


def production_converter() -> DataConverter:
    """Ventoux's data converter with stand-in production keys, in a fresh file."""
    return data_converter(StandInKeys(Path(tempfile.mkdtemp()) / "keys.json"))


def production_audit() -> StandInAudit:
    """A stand-in production audit store, in a fresh temporary folder."""
    return StandInAudit(tempfile.mkdtemp(prefix="ventoux-audit-"))
