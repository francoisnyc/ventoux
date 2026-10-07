"""Input policies: which sources an activity's input accepts (brief, D21).

A policy is written on the input field it guards, in the activity's input model. See
docs/guides/activities.md.
"""

from dataclasses import dataclass

from ventoux.core.provenance import is_trusted, is_untrusted


@dataclass(frozen=True)
class TrustedOnly:
    """Only from a system or a person, never from untrusted data."""

    def refuses(self, sources: frozenset[str]) -> str | None:
        """Why a value with these sources can't go in, or None if it can."""
        # Fail closed: a source that is neither trusted nor declared untrusted is unknown, and an
        # unknown source is refused, never taken as trusted.
        refused = [
            source if is_untrusted(source) else f"{source}, a source Ventoux doesn't recognise"
            for source in sorted(sources)
            if not is_trusted(source)
        ]
        return f"it comes from {'; '.join(refused)}" if refused else None

    def describe(self) -> str:
        """The policy as people read it, after the input's name."""
        return "only from a system or a person, never from untrusted data"


def trusted_only() -> TrustedOnly:
    return TrustedOnly()


@dataclass(frozen=True)
class OnlyFrom:
    """Only from the systems named."""

    systems: tuple[str, ...]  # the system names a value must come from, such as "payments"

    # Dataclass: `__post_init__` runs once the fields are set, every time an object is built.
    def __post_init__(self) -> None:
        if not self.systems:
            raise ValueError(
                "only_from names at least one system: with none, no value could ever pass."
            )

    def refuses(self, sources: frozenset[str]) -> str | None:
        """Why a value with these sources can't go in, or None if it can."""
        # A value with no source comes from no system, so from none of those named.
        if not sources:
            return "it comes from no system"
        # Every source must be one of the named systems: one other source is enough to refuse.
        allowed = {f"system:{system}" for system in self.systems}
        refused = sorted(sources - allowed)
        return f"it comes from {', '.join(refused)}" if refused else None

    def describe(self) -> str:
        """The policy as people read it, after the input's name."""
        return f"only from {' or '.join(self.systems)}"


def only_from(*systems: str) -> OnlyFrom:
    return OnlyFrom(systems)
