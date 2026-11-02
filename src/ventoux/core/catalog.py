"""The catalog: the activities a definition can call, each looked up by its reference."""

from ventoux.core.contract import ActivityContract, Contract, is_reference
from ventoux.core.contract_hash import contract_hash
from ventoux.core.options import option_check_problem
from ventoux.core.output_sources import UNDECLARED_LABEL, declared_sources
from ventoux.core.provenance import is_label
from ventoux.core.references import references
from ventoux.core.roles import checked_role
from ventoux.core.workflow_contract import WorkflowContract


class NotInCatalog(LookupError):
    """A reference the catalog doesn't hold, or holds as the other kind of contract."""


class ContractConflict(ValueError):
    """A second, different contract under a reference already in the catalog."""


class Catalog:
    """Contracts by reference, activities' and workflows' in one namespace, so a reference names
    one promise. Contracts only, never implementations: `core` runs no I/O."""

    def __init__(self) -> None:
        self._contracts: dict[str, Contract] = {}  # by reference, `payments.refund@1`
        self._labels: set[str] = set()  # the labels a field may be declared untrusted with
        self._roles: dict[str, str | None] = {}  # each role, and the highest risk it may approve
        self._operators: set[str] = set()  # the roles that may act on a failed step (brief, D26)
        self._forgetters: set[str] = set()  # the roles that may forget a case (brief, D32)
        self._editors: set[str] = set()  # the roles that may edit a case file (brief, D52)
        self._migrators: set[str] = set()  # the roles that may migrate a case (brief, D53)
        self._systems: set[str] = set()  # the systems a reference may name (brief, D30)
        # Each system's option check, by its reference: one per system (brief, D67).
        self._option_checks: dict[str, str] = {}

    def register_label(self, label: str) -> None:
        """Let fields be declared `untrusted:<label>`. Registered by the platform team, like roles,
        so a developer's typo is caught (brief, D12)."""
        if not is_label(label):
            raise ValueError(
                f"{label!r} is not a label: a label is lowercase, such as llm or customer-portal."
            )
        # Nobody can declare a value `untrusted:undeclared` and blur what it means (brief, D29).
        if label == UNDECLARED_LABEL:
            raise ValueError(
                f"{label} is the engine's label for an output nobody declared a source for: "
                "register another."
            )
        self._labels.add(label)

    @property
    def labels(self) -> list[str]:
        """The registered labels, in order."""
        return sorted(self._labels)

    def register_system(self, name: str) -> None:
        """Let references name the system `name`, such as `crm`. Registered by the platform team,
        like labels, so a typo in a case or a contract is caught (brief, D30)."""
        # A system is written as a label is: `crm`, `claims-archive`.
        if not is_label(name):
            raise ValueError(
                f"{name!r} is not a system name: a system is lowercase, such as crm or "
                "claims-archive."
            )
        self._systems.add(name)

    @property
    def systems(self) -> list[str]:
        """The registered systems, in order."""
        return sorted(self._systems)

    def register_option_check(self, system: str, check: str) -> None:
        """Name `check`, a registered contract's reference, as how to ask `system` whether it
        holds a value: an option of `system` is checked by it when a person gives one
        (brief, D67)."""
        problem = option_check_problem(system, self.get(check))
        if problem is not None:
            raise ValueError(problem)
        # One way to ask a system, so two cases never check one option two ways (brief, D67).
        if system in self._option_checks:
            raise ValueError(
                f"{system} has an option check already, {self._option_checks[system]}: "
                "a system has one"
            )
        self._option_checks[system] = check

    def option_check(self, system: str) -> str | None:
        """The reference of `system`'s option check, or None if it has none: then nothing can
        check an option of it, and a definition holding one is refused (brief, D67)."""
        return self._option_checks.get(system)

    def register_role(
        self,
        name: str,
        approves: str | None = None,
        operates: bool = False,
        forgets: bool = False,
        edits: bool = False,
        migrates: bool = False,
    ) -> None:
        """Let waits and approvals name the role `name`, which may approve activities up to the
        risk `approves` (none by default); if `operates`, act on a case's failed steps, skipping
        one included (brief, D26) (brief, D52); if `forgets`, propose or approve forgetting a case
        (brief, D32); if `edits`, propose or approve an edit of a case file (brief, D52); if
        `migrates`, propose or approve moving a case to another release (brief, D53). Registered
        by the platform team, like labels, so a typo is caught (brief, D22)."""
        checked_role(name, approves)
        self._roles[name] = approves
        if operates:
            self._operators.add(name)
        if forgets:
            self._forgetters.add(name)
        if edits:
            self._editors.add(name)
        if migrates:
            self._migrators.add(name)

    @property
    def operators(self) -> list[str]:
        """The registered roles that may act on a failed step, in order (brief, D26)."""
        return sorted(self._operators)

    @property
    def forgetters(self) -> list[str]:
        """The registered roles that may propose or approve forgetting a case, in order
        (brief, D32)."""
        return sorted(self._forgetters)

    @property
    def editors(self) -> list[str]:
        """The registered roles that may propose or approve an edit of a case file, in order
        (brief, D52)."""
        return sorted(self._editors)

    @property
    def migrators(self) -> list[str]:
        """The registered roles that may propose or approve a migration, in order (brief, D53)."""
        return sorted(self._migrators)

    @property
    def roles(self) -> dict[str, str | None]:
        """The registered roles, in order, each with the highest risk it may approve."""
        return dict(sorted(self._roles.items()))

    def register(self, contract: Contract) -> None:
        # Every rule runs again on what is registered: a copy made with `model_copy` skipped them all
        # (learning question 31). Fail closed: a contract that breaks a rule never enters the catalog.
        # Pydantic: `model_validate` checks its input, raising `ValidationError` if a rule fails. The
        # checked copy it returns isn't needed: the contract passed, and being frozen, can't change.
        # Checked as its own kind: a workflow contract by a workflow contract's rules.
        type(contract).model_validate(contract)
        self.check_output_labels(contract)
        self.check_reference_systems(contract)
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

    def check_output_labels(self, contract: Contract) -> None:
        """Every `untrusted:` label an output declares is registered, as a field's must be
        (brief, D12): a typo in a label is caught, never a new kind of untrusted. Every `system:`
        it declares names a registered system, as a reference must (brief, D29) (brief, D30)."""
        for name, declared in declared_sources(contract.output).items():
            origin, _, label = declared.partition(":")
            if origin == "untrusted" and label not in self._labels:
                registered = ", ".join(self.labels) or "none yet"
                raise ValueError(
                    f"{contract.reference}: output {name} is {declared}, and {label} is not a "
                    f"registered label. Register it first, or use one of: {registered}."
                )
            if origin == "system" and label not in self._systems:
                registered = ", ".join(self.systems) or "none yet"
                raise ValueError(
                    f"{contract.reference}: output {name} is {declared}, and {label} is not a "
                    f"registered system. Register it first, or use one of: {registered}."
                )

    def check_reference_systems(self, contract: Contract) -> None:
        """Every system an input's reference names is registered: a typo is caught, never a
        system nobody runs (brief, D30)."""
        for name, system in references(contract.input).items():
            if system not in self._systems:
                registered = ", ".join(self.systems) or "none yet"
                raise ValueError(
                    f"{contract.reference}: input {name} is a reference to {system}, which is not "
                    f"a registered system. Register it first, or use one of: {registered}."
                )

    def next_reference(self, name: str) -> str:
        """The reference a changed contract should take: one past the latest version."""
        versions = [c.version for c in self._contracts.values() if c.name == name]
        return f"{name}@{max(versions, default=0) + 1}"

    def contracts(self) -> list[Contract]:
        """Every registered contract, of both kinds, by reference."""
        return sorted(self._contracts.values(), key=lambda c: c.reference)

    def get(self, reference: str) -> ActivityContract:
        """The activity contract `reference` names. Plans and activity steps call activities, so a
        workflow contract is refused, never handed over (fail closed)."""
        contract = self.lookup(reference)
        if not isinstance(contract, ActivityContract):
            raise NotInCatalog(
                f"{reference} is a workflow contract, not an activity: run it as a workflow step."
            )
        return contract

    def workflow(self, reference: str) -> WorkflowContract:
        """The workflow contract `reference` names; an activity contract is refused."""
        contract = self.lookup(reference)
        if not isinstance(contract, WorkflowContract):
            raise NotInCatalog(
                f"{reference} is an activity contract, not a workflow: run it as an activity step."
            )
        return contract

    def lookup(self, reference: str) -> Contract:
        """The contract `reference` names, of either kind."""
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
