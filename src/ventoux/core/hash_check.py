"""The hash check CI runs: each contract in the catalog against `contracts.lock.json`.

The lockfile's hashes carry no method: each is hash method 1, the method release records name
(`"method": 1`). A second method would be its own decision, and the lockfile would then say which
it uses (brief, D50). A contract changed without a new version says what changed, path by path,
when given the promise it had before, from the base commit's own code (brief, D57).
"""

from collections.abc import Mapping

from ventoux.core.catalog import Catalog
from ventoux.core.contract import Contract
from ventoux.core.contract_hash import contract_hash, promise_hash
from ventoux.core.promise import PromiseUnreadable, promise_changes, promise_of

# Where the promises before come from: printed by the base commit's own code.
GIVE_THEM = "to see what changed, give the base commit's promises (`ventoux promises`)"


def check_hashes(
    catalog: Catalog, recorded: Mapping[str, str], before: Mapping[str, object] | None = None
) -> list[str]:
    """What CI reports: contracts changed without a new version (brief, D5), each with what
    changed if `before` gives its earlier promise, and unrecorded ones."""
    problems: list[str] = []
    for contract in catalog.contracts():
        digest = contract_hash(contract)
        if contract.reference not in recorded:
            problems.append(
                f'{contract.reference} is not recorded yet: add "{contract.reference}": "{digest}".'
            )
        elif digest != recorded[contract.reference]:
            line = (
                f"{contract.reference} changed without a new version: "
                f"register it as {catalog.next_reference(contract.name)}."
            )
            said = what_changed(contract, recorded[contract.reference], before)
            problems.append("\n".join([line, *(f"  {each}" for each in said)]))
    return problems


def what_changed(
    contract: Contract, recorded: str, before: Mapping[str, object] | None
) -> list[str]:
    """What changed in `contract` since the promise the lockfile records as `recorded`, path by
    path; or why it can't be said. A promise given is compared only if it is the one the lockfile
    records: anything else would describe someone else's promise (fail closed)."""
    reference = contract.reference
    if before is None:
        return [GIVE_THEM]
    if reference not in before:
        return [f"what changed can't be said: no promise was given for {reference}"]
    earlier = before[reference]
    if not isinstance(earlier, dict) or promise_hash(earlier) != recorded:
        return [
            (
                f"what changed can't be said: the promise given for {reference} isn't the one "
                "contracts.lock.json records"
            )
        ]
    try:
        return promise_changes(earlier, promise_of(contract))
    except PromiseUnreadable as unreadable:
        return [f"what changed can't be said: {unreadable}"]
