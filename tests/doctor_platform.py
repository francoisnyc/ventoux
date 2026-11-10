"""A platform module written as the deployment guide writes it (layer 20b2): the key service is
`VaultKeys` with its default transport, which refuses to be made without `VAULT_TOKEN` (19c), so
this module raises as it is imported when the token isn't set. Its address is local and closed:
no test here reaches a Vault."""

from doctor_deployment import AUDIT, CATALOG

from ventoux.tooling.vault import VaultKeys

KEYS = VaultKeys(address="https://127.0.0.1:9", transit_mount="transit", marks_mount="secret")

__all__ = ["AUDIT", "CATALOG", "KEYS"]
