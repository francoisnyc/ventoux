"""Connecting to Temporal as an identity, named in `pyproject.toml` (layer 20b1) (brief, D81).

A deployment locks Temporal down with mTLS and its authorization: only the caller writes for
people (brief, D79), workers write their own tasks, named operators do the rest, people read
(brief, D19).
So every command that talks to Temporal connects as one of the identities
`[tool.ventoux.temporal]` names, each a certificate and a key as file paths. Without that section,
a command connects as before, to `localhost:7233` without TLS: development is unchanged.
A file is read only to connect with, and never said: a failure names the file and the error's
kind, never what it holds. See docs/guides/deployment.md.
"""

from dataclasses import dataclass
from pathlib import Path

from temporalio.client import Client
from temporalio.converter import DataConverter
from temporalio.service import TLSConfig

from ventoux.tooling.deployment import Configuration

DEVELOPMENT_ADDRESS = "localhost:7233"  # the development server, with no section
DEVELOPMENT_NAMESPACE = "default"


class Unconnectable(Exception):
    """A connection that can't be made as configured: nothing was connected."""


@dataclass(frozen=True)
class Connection:
    """Where a command connects, and how: what `connect` gives Temporal's client."""

    target: str  # Temporal's frontend: `ventoux-prod.a1b2c.tmprl.cloud:7233`
    namespace: str
    tls: TLSConfig | None  # the identity's certificate and key, and the server's CA; None: no TLS


def chosen(found: Configuration, flag: str | None, default: str) -> str | None:
    """The identity a command connects as: `--identity`, or with `[tool.ventoux.temporal]` the
    command's own default (`operator` for the environment commands, `reader` for `advise`, which
    only reads); without the section, none."""
    if flag is not None:
        return flag
    return default if found.temporal is not None else None


def connection(
    found: Configuration, identity: str | None, address: str | None, namespace: str | None
) -> Connection:
    """How to connect as `identity` (None: the command's default with a section, none without),
    `address` and `namespace` winning over the configuration's when given."""
    temporal = found.temporal
    if temporal is None:
        if identity is not None:
            raise Unconnectable(
                f"--identity {identity} names an identity, and pyproject.toml has no "
                "[tool.ventoux.temporal]: name it there, with its cert and key"
            )
        return Connection(address or DEVELOPMENT_ADDRESS, namespace or DEVELOPMENT_NAMESPACE, None)
    if identity is None or identity not in temporal.identities:
        raise Unconnectable(
            f"the identity {identity} isn't configured: name its cert and key in pyproject.toml, "
            f"[tool.ventoux.temporal.identities.{identity}]"
        )
    chosen = temporal.identities[identity]
    tls = TLSConfig(
        server_root_ca_cert=(
            None
            if temporal.server_ca is None
            else read_file(f"the server CA, {temporal.server_ca},", temporal.server_ca)
        ),
        client_cert=read_file(f"the identity {identity}'s cert, {chosen.cert},", chosen.cert),
        client_private_key=read_file(f"the identity {identity}'s key, {chosen.key},", chosen.key),
    )
    return Connection(address or temporal.address, namespace or temporal.namespace, tls)


def read_file(what: str, path: str) -> bytes:
    """The bytes of the file at `path`; one that can't be read is said by its path and the
    error's kind, never its contents."""
    try:
        return Path(path).read_bytes()
    except OSError as error:
        raise Unconnectable(
            f"{what} can't be read ({type(error).__name__}): nothing was connected"
        ) from None


async def connect(
    found: Configuration,
    identity: str | None,
    address: str | None,
    namespace: str | None,
    converter: DataConverter,
) -> Client:
    """A Temporal client as `identity`, with `converter` (the keys, for a case's values)."""
    settings = connection(found, identity, address, namespace)
    return await Client.connect(
        settings.target,
        namespace=settings.namespace,
        tls=settings.tls if settings.tls is not None else False,
        data_converter=converter,
    )
