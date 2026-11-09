"""What `ventoux doctor` asks the world (layer 20b2) (brief, D81).

Each probe changes nothing if it is allowed: a connection opened and closed, a signal to a
workflow that can't exist, a query, Vault asked what a token could do. Doctor bounds each one; a
probe raises on anything it can't read as an answer, which doctor says unchecked.
"""

import asyncio
from typing import Any, Protocol

from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from ventoux.case.registry import Registry
from ventoux.temporal.converter import registry_converter
from ventoux.temporal.registry import RegistryMissing, environment_check, registry_of
from ventoux.tooling.connecting import Unconnectable, answered_without_certificate, connect
from ventoux.tooling.deployment import Configuration
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


# A workflow that can't exist: doctor signals it as the reader, so nothing changes either way.
NEVER_STARTED = "ventoux-doctor/never-started"
NEVER_MADE = "doctor-never-made"  # a case that can't exist: its key is never made
READER = "reader"  # the identity doctor signals as, to see a write refused (brief, D81)


class Unanswered(Exception):
    """A probe that couldn't be answered, said in doctor's own words: no secret is in them."""


class LiveProbes:
    """Doctor's probes, asked of the deployment: Temporal as the configured identities, the
    registry by its query, Vault through the key service's own transport."""

    def __init__(
        self,
        found: Configuration,
        environment: str,
        address: str | None = None,
        namespace: str | None = None,
    ) -> None:
        self.found = found
        self.environment = environment  # `production`
        self.address = address  # Temporal's frontend, when not the configuration's
        self.namespace = namespace

    async def as_identity(self, identity: str | None) -> Client:
        """A client as `identity` (None: as the commands connect without a section)."""
        return await connect(
            self.found, identity, self.address, self.namespace, registry_converter()
        )

    def reading(self) -> str | None:
        """Who doctor reads the registry as: `reader`, else `operator`; with no section, none."""
        temporal = self.found.temporal
        if temporal is None:
            return None
        for identity in (READER, "operator"):
            if identity in temporal.identities:
                return identity
        raise Unconnectable("no reader or operator identity is configured to read the registry as")

    async def unauthenticated(self) -> list[str]:
        if self.found.temporal is not None:
            await self.as_identity(self.reading())  # reached: a refusal below is one
        answered = await answered_without_certificate(self.found, self.address, self.namespace)
        if self.found.temporal is None and not answered:
            raise Unanswered("Temporal can't be reached with no section, so nothing was refused")
        return answered

    async def reader_signal(self) -> str:
        client = await self.as_identity(READER if self.found.temporal is not None else None)
        try:
            await client.get_workflow_handle(NEVER_STARTED).signal("ventoux-doctor")
        except RPCError as error:
            if error.status == RPCStatusCode.PERMISSION_DENIED:
                return "refused"
            if error.status == RPCStatusCode.NOT_FOUND:
                return "allowed"  # looked for: the write was allowed
            raise
        return "allowed"

    async def registry(self) -> Registry | None:
        try:
            return await registry_of(await self.as_identity(self.reading()), self.environment)
        except RegistryMissing:
            return None

    async def environment_problems(self) -> list[str]:
        return await environment_check(await self.as_identity(self.reading()), self.environment)

    async def key_state(self, keys: VaultKeys) -> str:
        # VaultKeys asks over HTTP, blocking, with its own timeout: on a thread, bounded again.
        return await asyncio.to_thread(keys.state, NEVER_MADE)

    async def capabilities(self, keys: VaultKeys, paths: list[str]) -> dict[str, list[str]]:
        status, body = await asyncio.to_thread(
            keys.transport, "POST", "/v1/sys/capabilities-self", {"paths": paths}
        )
        if status != 200:
            raise Unanswered(f"Vault answered sys/capabilities-self with status {status}")
        return {path: capabilities_of(body, path) for path in paths}


def capabilities_of(body: dict[str, Any], path: str) -> list[str]:
    """The capabilities Vault's answer gives on `path`; one it doesn't give is refused, never
    read as none."""
    given = body.get("data", body).get(path)
    if not isinstance(given, list) or not all(isinstance(c, str) for c in given):
        raise Unanswered(f"Vault's answer gives no capabilities on {path}")
    return list(given)
