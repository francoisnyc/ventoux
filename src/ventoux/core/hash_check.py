"""The hash check CI runs: each contract in the catalog against `contracts.lock.json`."""

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
