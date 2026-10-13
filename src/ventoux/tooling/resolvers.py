"""Resolvers: showing a person the record a reference names, asked on their behalf (layer 9a).

A resolver is registered per system by the platform team. It only reads, runs outside the case
(in the inbox, never in a workflow), and nothing it returns enters the case file or its history
(brief, D16). See docs/guides/activities.md, "Systems and resolvers".
"""

from collections.abc import Callable
from dataclasses import dataclass

from ventoux.case.visibility import CaseView
from ventoux.core.catalog import Catalog


@dataclass(frozen=True)
class Viewer:
    """The person looking at a case, and their roles, as the trusted caller states them."""

    person: str
    roles: tuple[str, ...]


# A resolver: a reference and who is looking, to what that system shows them.
type Resolver = Callable[[str, Viewer], dict[str, object]]


class ShowRefused(Exception):
    """A record the inbox won't show: why."""


class Resolvers:
    """The resolver for each system, registered by the platform team."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._resolvers: dict[str, Resolver] = {}

    def register(self, system: str, resolver: Resolver) -> None:
        """Show the records of `system` with `resolver`, which calls it on the viewer's behalf."""
        # A typo would leave references with no resolver nobody notices (brief, D30).
        if system not in self._catalog.systems:
            raise ValueError(
                f"{system} is not a registered system: register it in the catalog first."
            )
        self._resolvers[system] = resolver

    def show(self, view: CaseView, field: str, viewer: Viewer) -> dict[str, object]:
        """What the system behind the reference `field` shows `viewer`, read from their `view`.

        The view is already filtered for them, so a field hidden from them has no reference to
        resolve: Ventoux may hide more than the system, never show more (brief, D16). What the
        resolver returns is handed back unchanged and never stored; recording that it was shown
        is the caller's, with a `shown` event.
        """
        if field in view.hidden:
            needs = " or ".join(view.hidden[field])
            raise ShowRefused(f"{field} is hidden from you: it needs {needs}")
        if field not in view.systems:
            raise ShowRefused(f"{field} is not a reference: there is no record to show")
        reference = view.values.get(field)
        if not isinstance(reference, str):
            raise ShowRefused(f"{field} is not set: there is no record to show")
        system = view.systems[field]
        # Fail closed: a system with no resolver shows nothing, and says so.
        if system not in self._resolvers:
            raise ShowRefused(f"{system} has no resolver: register one to show its records")
        return self._resolvers[system](reference, viewer)
