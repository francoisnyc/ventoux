"""A deployment's own modules, as `[tool.ventoux]` names them, for doctor's tests (layer 20b2):
the platform team's catalog, key service and audit store, stood in for."""

import tempfile
from pathlib import Path

from production_stand_ins import StandInAudit

from ventoux.testing import CATALOG as DEVELOPMENT_CATALOG
from ventoux.tooling.audit import FileAudit
from ventoux.tooling.keys import FileKeys
from ventoux.tooling.vault import Recording, VaultKeys

CATALOG = DEVELOPMENT_CATALOG  # stands for the platform team's, named otherwise

# The deployment's key service: Vault, asked through a recording (no test here reaches Vault).
KEYS = VaultKeys("https://vault.internal:8200", "transit", "secret", transport=Recording([]))
FILE_KEYS = FileKeys(Path(tempfile.mkdtemp()) / "keys.json")  # for development only
AUDIT = StandInAudit(tempfile.mkdtemp())  # stands for the deployment's audit store
FILE_AUDIT = FileAudit(tempfile.mkdtemp())  # for development only


class Unsaid:
    """A provider that doesn't say whether it is for development."""


UNSAID = Unsaid()
