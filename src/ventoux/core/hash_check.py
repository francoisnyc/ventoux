"""The hash check CI runs: each contract in the catalog against `contracts.lock.json`.

The lockfile's hashes carry no method: each is hash method 1, the method release records name
(`"method": 1`). A second method would be its own decision, and the lockfile would then say which
it uses (brief, D50).
"""

from ventoux.core.catalog import Catalog
from ventoux.core.contract_hash import contract_hash


def check_hashes(catalog: Catalog, recorded: dict[str, str]) -> list[str]:
    """What CI reports: contracts changed without a new version (brief, D5), and unrecorded ones."""
    problems: list[str] = []
    for contract in catalog.contracts():
        digest = contract_hash(contract)
        if contract.reference not in recorded:
            problems.append(
                f'{contract.reference} is not recorded yet: add "{contract.reference}": "{digest}".'
            )
        elif digest != recorded[contract.reference]:
            problems.append(
                f"{contract.reference} changed without a new version: "
                f"register it as {catalog.next_reference(contract.name)}."
            )
    return problems
