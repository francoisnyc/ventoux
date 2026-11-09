"""What `ventoux doctor` asks the world (layer 20b2) (brief, D81).

Each probe changes nothing if it is allowed: a connection opened and closed, a signal to a
workflow that can't exist, a query, Vault asked what a token could do. Doctor bounds each one; a
probe raises on anything it can't read as an answer, which doctor says unchecked.
"""

from typing import Protocol

from ventoux.case.registry import Registry
from ventoux.tooling.vault import VaultKeys


class Probes(Protocol):
    """What doctor asks Temporal, the registry and the key service."""

    async def unauthenticated(self) -> list[str]:
        """How a connection without a client certificate was answered (`without TLS`, `with TLS
        and no client certificate`); empty when each was refused. Raises when Temporal can't be
        reached at all, so a refusal is never read from silence."""
        ...

    async def reader_signal(self) -> str:
        """`refused` when the reader is refused a signal to a workflow that can't exist;
        `allowed` when it was let through (the workflow not found, or the signal taken)."""
        ...

    async def registry(self) -> Registry | None:
        """The environment's registry, as its query gives it; None when it doesn't exist."""
        ...

    async def environment_problems(self) -> list[str]:
        """What `environment_check` says, one problem a line; empty when every release can run."""
        ...

    async def key_state(self, keys: VaultKeys) -> str:
        """The state `keys` gives of the key of a case that can't exist: reads only."""
        ...

    async def capabilities(self, keys: VaultKeys, paths: list[str]) -> dict[str, list[str]]:
        """What Vault says the token could do on each of `paths` (`sys/capabilities-self`)."""
        ...
