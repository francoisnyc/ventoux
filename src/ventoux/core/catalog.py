"""The catalog: the activities a definition can call, each looked up by its reference."""

from ventoux.core.contract import ActivityContract, is_reference
from ventoux.core.contract_hash import contract_hash
from ventoux.core.provenance import is_label
from ventoux.core.roles import checked_role


class NotInCatalog(LookupError):
    """A reference the catalog doesn't hold."""


class ContractConflict(ValueError):
    """A second, different contract under a reference already in the catalog."""


class Catalog:
    """Contracts by reference. Contracts only, never implementations: `core` runs no I/O."""

    def __init__(self) -> None:
        self._contracts: dict[str, ActivityContract] = {}  # by reference, `payments.refund@1`
        self._labels: set[str] = set()  # the labels a field may be declared untrusted with
        self._roles: dict[str, str | None] = {}  # each role, and the highest risk it may approve
        self._operators: set[str] = set()  # the roles that may act on a failed step (brief, D26)

    def register_label(self, label: str) -> None:
        """Let fields be declared `untrusted:<label>`. Registered by the platform team, like roles,
        so a developer's typo is caught (brief, D12)."""
        if not is_label(label):
            raise ValueError(
                f"{label!r} is not a label: a label is lowercase, such as llm or customer-portal."
            )
        self._labels.add(label)

    @property
    def labels(self) -> list[str]:
        """The registered labels, in order."""
        return sorted(self._labels)

    def register_role(self, name: str, approves: str | None = None, operates: bool = False) -> None:
        """Let waits and approvals name the role `name`, which may approve activities up to the
        risk `approves` (none by default), and, if `operates`, act on a case's failed steps.
        Registered by the platform team, like labels, so a typo is caught (brief, D22, D26)."""
        checked_role(name, approves)
        self._roles[name] = approves
        if operates:
            self._operators.add(name)

    @property
    def operators(self) -> list[str]:
        """The registered roles that may act on a failed step, in order (brief, D26)."""
        return sorted(self._operators)

    @property
    def roles(self) -> dict[str, str | None]:
        """The registered roles, in order, each with the highest risk it may approve."""
        return dict(sorted(self._roles.items()))

    def register(self, contract: ActivityContract) -> None:
        # Every rule runs again on what is registered: a copy made with `model_copy` skipped them all
        # (learning question 31). Fail closed: a contract that breaks a rule never enters the catalog.
        # Pydantic: `model_validate` checks its input, raising `ValidationError` if a rule fails. The
        # checked copy it returns isn't needed: the contract passed, and being frozen, can't change.
        ActivityContract.model_validate(contract)
        # A reference stands for one promise for good: a changed promise needs a new version
        # (brief, D5).
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
        if not is_reference(reference):
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
        hint = (
            f" Registered: {registered}. Use a registered version, or register this one first."
            if registered
            else " Register its contract first, or check the name."
        )
        raise NotInCatalog(f"{reference} is not in the catalog.{hint}")
