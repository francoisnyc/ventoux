"""The catalog: the activities a definition can call, each looked up by its reference."""

from ventoux.core.contract import REFERENCE, ActivityContract
from ventoux.core.contract_hash import contract_hash


class NotInCatalog(LookupError):
    """A reference the catalog doesn't hold."""


class ContractConflict(ValueError):
    """A second, different contract under a reference already in the catalog."""


class Catalog:
    """Contracts by reference. Contracts only, never implementations: `core` runs no I/O."""

    def __init__(self) -> None:
        self._contracts: dict[str, ActivityContract] = {}

    def register(self, contract: ActivityContract) -> None:
        # A name stands for one promise for good (D5): a changed promise needs a new version.
        registered = self._contracts.get(contract.reference)
        if registered is not None and contract_hash(registered) != contract_hash(contract):
            raise ContractConflict(
                f"{contract.reference} is already registered with different content: "
                f"register it as {self.next_reference(contract.name)}."
            )
        # New, the same promise again (a worker restarting), or new wording, which applies at once.
        self._contracts[contract.reference] = contract

    def next_reference(self, name: str) -> str:
        """The reference a changed contract should take: one past the latest version."""
        versions = [c.version for c in self._contracts.values() if c.name == name]
        return f"{name}@{max(versions, default=0) + 1}"

    def contracts(self) -> list[ActivityContract]:
        """Every registered contract, by reference."""
        return sorted(self._contracts.values(), key=lambda c: c.reference)

    def get(self, reference: str) -> ActivityContract:
        if not REFERENCE.fullmatch(reference):
            raise NotInCatalog(
                f"{reference!r} is not a reference: a reference is name@N, such as "
                "payments.refund@1, with a whole-number version."
            )
        if reference in self._contracts:
            return self._contracts[reference]
        # Fail closed: an unknown reference is an error, never None a caller could ignore.
        name = reference.split("@")[0]
        same_name = sorted(
            (c for c in self._contracts.values() if c.name == name), key=lambda c: c.version
        )
        registered = ", ".join(c.reference for c in same_name)
        hint = f" Registered: {registered}." if registered else ""
        raise NotInCatalog(f"{reference} is not in the catalog.{hint}")
