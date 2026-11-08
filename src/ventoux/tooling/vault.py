"""The production key provider: Vault's transit engine, a key per case (layer 19c).

Vault seals and opens for Ventoux; a case's key never leaves it (brief, D15). When the case is
forgotten, a mark is written in Vault's key-value engine before the key is deleted, so the case
reads as destroyed from then on, whatever Vault would let be made again (brief, D78). Ventoux
asks Vault through a transport: the standard library's HTTPS in production, a recording of
Vault's answers in tests.
See docs/layers/19-audit-keys.md (19c) and docs/guides/audit.md.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from ventoux.tooling.keys import FORGOTTEN, KeyRefused

# What Vault answered: its HTTP status, and its JSON body (empty when it had none).
type Answer = tuple[int, dict[str, Any]]
# How Ventoux asks Vault: a method, a path under the address (`/v1/transit/keys/…`), and a JSON
# body or None; given back Vault's answer.
type Transport = Callable[[str, str, dict[str, Any] | None], Answer]

PREFIX = "ventoux-"  # every key and mark Ventoux makes is named so, for the token's policy


# What a name keeps as it is: lowercase letters, digits and `-`. Everything else is escaped.
KEPT = frozenset(b"abcdefghijklmnopqrstuvwxyz0123456789-")
LONGEST = 128  # characters in a name, the prefix included


def vault_name(case: str) -> str:
    """The name of `case`'s key in Vault, and of its mark: lowercase letters, digits and `-` as
    they are, every other byte of its UTF-8 as `_` and two hex digits (`refund-A-1001` is
    `ventoux-refund-_41-1001`). `_` only ever starts an escape, so no two IDs share a name, even
    with capitals folded; and no name holds what a URL reads as a path, a query or a fragment
    (`.`, `/`, `%`, `?`, `#`) (brief, D78)."""
    if not case:
        raise KeyRefused("a case ID can't be empty")
    name = PREFIX + "".join(chr(byte) if byte in KEPT else f"_{byte:02x}" for byte in case.encode())
    if len(name) > LONGEST:
        raise KeyRefused(
            f"a case ID names a key in the key service, and its name can't pass {LONGEST} "
            "characters"
        )
    return name


@dataclass(frozen=True)
class Exchange:
    """One request a recording holds, and Vault's answer to it."""

    method: str  # GET, POST or DELETE
    path: str  # under the address: `/v1/transit/keys/ventoux-claim-7`
    body: dict[str, Any] | None  # the JSON sent, or None
    answer: Answer  # what Vault answered


@dataclass
class Recording:
    """Vault's answers, request by request, in the order they were recorded: a test's transport.
    A request it doesn't hold, in that place, is refused, saying which."""

    exchanges: list[Exchange]
    asked: list[Exchange] = field(default_factory=list[Exchange])  # what it was asked, in order

    def __call__(self, method: str, path: str, body: dict[str, Any] | None) -> Answer:
        number = len(self.asked) + 1  # this request's place, from 1
        held = self.exchanges[number - 1] if number <= len(self.exchanges) else None
        if held is None or (held.method, held.path, held.body) != (method, path, body):
            # Never the body: it may hold a value being sealed.
            raise RecordingRefused(
                f"the recording holds no {method} {path} (request {number}): record it, or fix "
                "what asked"
            )
        self.asked.append(held)
        return held.answer


class RecordingRefused(Exception):
    """A request a recording doesn't hold in that place: a test's mistake, never Vault's
    answer, so it is never read as Vault being down."""


class VaultKeys:
    """A key per case in Vault's transit engine; the marks of forgotten cases in a key-value
    engine (version 2)."""

    def __init__(
        self,
        address: str,
        transit_mount: str,
        marks_mount: str,
        *,
        timeout: float = 10,
        transport: Transport | None = None,
    ) -> None:
        # Fail closed: each is named by the platform team; none has a default (brief, D78).
        for name, value in (
            ("address", address),
            ("transit_mount", transit_mount),
            ("marks_mount", marks_mount),
        ):
            if not value:
                raise ValueError(
                    f"VaultKeys needs an address, a transit mount and a marks mount: {name} is "
                    "empty"
                )
        refuse_plain_http(address)
        self.address = address  # where Vault answers: `https://vault.internal:8200`
        self.transit_mount = transit_mount  # the transit engine's mount: `transit`
        self.marks_mount = marks_mount  # the key-value engine's mount: `secret`
        self.timeout = timeout  # how long one call may take, in seconds
        # How Vault is asked: over HTTPS, with the token, unless a test gives a recording.
        self.transport = transport or Https(address, timeout)

    def create(self, case: str) -> None:
        """Make `case`'s key, each setting stated: never exportable, no plaintext backup, AES-256
        in GCM. Never made again: refused for a case with a key, or with a mark, so a reused ID
        never inherits or remakes a key (brief, D31)."""
        name = vault_name(case)
        made_already = f"a key was already made for {case}: open the case under a new ID"
        status, _ = self.transport("GET", self.mark_path(name), None)
        if status == 200:
            raise KeyRefused(made_already)
        status, _ = self.transport("GET", self.key_path(name), None)
        if status == 200:
            raise KeyRefused(made_already)
        settings = {"type": KEY_TYPE, "exportable": False, "allow_plaintext_backup": False}
        self.transport("POST", self.key_path(name), settings)

    def seal(self, case: str, data: bytes, part: str) -> bytes:
        self.usable(case)
        raise NotImplementedError

    def open(self, case: str, data: bytes, part: str) -> bytes:
        self.usable(case)
        raise NotImplementedError

    def usable(self, case: str) -> str:
        """The name of `case`'s key, once Vault says it may be used: no mark, and a key."""
        name = vault_name(case)
        status, _ = self.transport("GET", self.mark_path(name), None)
        if status == 200:
            raise KeyRefused(
                f"the key of {case} {FORGOTTEN}: its sensitive values can't be read or written"
            )
        status, body = self.transport("GET", self.key_path(name), None)
        if status == 404:
            raise KeyRefused(
                f"there is no key for {case}, so its sensitive values can't be read or written"
            )
        refuse_leaving(case, body["data"])
        return name

    def key_path(self, name: str) -> str:
        return f"/v1/{self.transit_mount}/keys/{name}"

    def mark_path(self, name: str) -> str:
        return f"/v1/{self.marks_mount}/data/ventoux/forgotten/{name}"


KEY_TYPE = "aes256-gcm96"  # AES-256 in GCM: the part a value is sealed for binds as in FileKeys


def refuse_leaving(case: str, config: dict[str, Any]) -> None:
    """Refuse a key Vault would let leave it, or of another type: read from its configuration on
    every use, since Vault lets a key be made exportable later, never the other way (brief, D78)."""
    for setting, said in (("exportable", "exportable"), ("allow_plaintext_backup", PLAINTEXT)):
        if config[setting] is not False:
            raise KeyRefused(
                f"the key of {case} can leave the key service ({said}): it is not used"
            )
    if config["type"] != KEY_TYPE:
        raise KeyRefused(f"the key of {case} is {config['type']}, not {KEY_TYPE}: it is not used")


PLAINTEXT = "plaintext backup allowed"


# The hosts an `http://` address may name: a development server on this machine.
LOCAL = ("localhost", "127.0.0.1")


def refuse_plain_http(address: str) -> None:
    """Refuse an address the token would cross in clear: only `https`, or `http` to this machine."""
    parts = urlsplit(address)
    if parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOCAL):
        return
    raise ValueError(
        f"the key service is reached over https: {address} is only for a development server on "
        "localhost"
    )


NO_TOKEN = "VAULT_TOKEN is not set: the key service can't be asked"


class Https:
    """Asks Vault over HTTPS, with the standard library, adding Ventoux's token. The token is read
    from `VAULT_TOKEN` as each call is made, never kept here, so it is in no repr (brief, D62)."""

    def __init__(self, address: str, timeout: float) -> None:
        if not os.environ.get("VAULT_TOKEN"):
            raise ValueError(NO_TOKEN)  # never another place a token may be kept
        self.address = address
        self.timeout = timeout

    def __call__(self, method: str, path: str, body: dict[str, Any] | None) -> Answer:
        raise NotImplementedError
