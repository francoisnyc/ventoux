"""The production key provider: Vault's transit engine, a key per case (layer 19c).

Vault seals and opens for Ventoux; a case's key never leaves it (brief, D15). When the case is
forgotten, a mark is written in Vault's key-value engine before the key is deleted, so the case
reads as destroyed from then on, whatever Vault would let be made again (brief, D78). Ventoux
asks Vault through a transport: the standard library's HTTPS in production, a recording of
Vault's answers in tests.
See docs/layers/19-audit-keys.md (19c) and docs/guides/audit.md.
"""

import base64
import binascii
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from ventoux.tooling.keys import FORGOTTEN, KeyRefused, KeyState, KeyUnavailable, place

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
    answer: Answer | Exception  # what Vault answered, or what the transport met instead


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
        if isinstance(held.answer, Exception):
            raise held.answer  # Vault unreachable, or timing out, as recorded
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
        if self.marked(case, name) or self.key_config(case, name) is not None:
            raise KeyRefused(f"a key was already made for {case}: open the case under a new ID")
        settings = {"type": KEY_TYPE, "exportable": False, "allow_plaintext_backup": False}
        self.ask(case, "POST", self.key_path(name), settings, {200, 204})

    def destroy(self, case: str) -> None:
        """Destroy `case`'s key, so nothing sealed with it opens again (brief, D15): the mark
        first, then the key's deletion allowed, then the key deleted. From the mark on the case
        reads as destroyed and no key of its name is used, whatever Vault would let be made again;
        a destroy cut short is finished by the next (brief, D78)."""
        name = vault_name(case)
        if not self.marked(case, name):
            if self.key_config(case, name) is None:
                # Fail closed: no key was made, so there is no case to forget.
                raise KeyRefused(
                    f"there is no key for {case} to destroy: no case was opened with its ID"
                )
            mark = {"data": {"forgotten": True}}
            self.ask(case, "POST", self.mark_path(name), mark, {200, 204})
        elif self.key_config(case, name) is None:
            return  # marked, and the key gone: a destroy that finished, asked again
        config = {"deletion_allowed": True}  # Vault deletes no key that doesn't allow it
        self.ask(case, "POST", f"{self.key_path(name)}/config", config, {200, 204})
        # A key gone since it was read counts as deleted: two destroys may overlap.
        self.ask(case, "DELETE", self.key_path(name), None, {200, 204, 404})

    def state(self, case: str) -> KeyState:
        """Whether `case`'s key is kept, was destroyed (its mark), or was never made: each only
        on Vault's answer. Anything else is `KeyUnavailable`, never read as either (brief, D78)."""
        name = vault_name(case)
        if self.marked(case, name):
            return "destroyed"
        return "never made" if self.key_config(case, name) is None else "kept"

    def seal(self, case: str, data: bytes, part: str) -> bytes:
        """`data` encrypted by Vault with `case`'s key, bound to its place: Vault's ciphertext
        (`vault:v1:…`), as bytes."""
        name = self.usable(case)
        sent = {"plaintext": as_base64(data), "associated_data": as_base64(place(case, part))}
        path = f"/v1/{self.transit_mount}/encrypt/{name}"
        _, body = self.ask(case, "POST", path, sent, {200})
        return self.text(case, body, "data", "ciphertext").encode()

    def open(self, case: str, data: bytes, part: str) -> bytes:
        """What `seal` encrypted for `case` at `part`; refused for anything else."""
        name = self.usable(case)
        sent = {"ciphertext": data.decode(), "associated_data": as_base64(place(case, part))}
        path = f"/v1/{self.transit_mount}/decrypt/{name}"
        status, body = self.ask(case, "POST", path, sent, {200, 400})
        if status == 400:
            # Vault couldn't open it for this place: fail closed, never a guess at what it held.
            raise KeyRefused(
                f"a sealed part of {case} doesn't open: it was damaged, or sealed for another "
                "case or place"
            )
        try:
            return base64.b64decode(self.text(case, body, "data", "plaintext"), validate=True)
        except binascii.Error:
            raise self.unreadable(case) from None

    def usable(self, case: str) -> str:
        """The name of `case`'s key, once Vault says it may be used: no mark, and a key that
        can't leave it, of the type Ventoux makes."""
        name = vault_name(case)
        if self.marked(case, name):
            raise KeyRefused(
                f"the key of {case} {FORGOTTEN}: its sensitive values can't be read or written"
            )
        config = self.key_config(case, name)
        if config is None:
            raise KeyRefused(
                f"there is no key for {case}, so its sensitive values can't be read or written"
            )
        refuse_leaving(case, config)
        return name

    def marked(self, case: str, name: str) -> bool:
        """Whether Vault holds `case`'s mark: it was forgotten."""
        status, body = self.ask(case, "GET", self.mark_path(name), None, {200, 404})
        if status == 404:
            return False
        # Only a mark as Ventoux writes it says the case was forgotten: never just any answer.
        if not isinstance(self.read(case, body, "data", "data"), dict):
            raise self.unreadable(case)
        return True

    def key_config(self, case: str, name: str) -> dict[str, Any] | None:
        """The configuration of `case`'s key, as Vault holds it; None if it holds no key."""
        status, body = self.ask(case, "GET", self.key_path(name), None, {200, 404})
        if status == 404:
            return None
        config = self.read(case, body, "data")
        settings = ("type", "exportable", "allow_plaintext_backup")
        if not isinstance(config, dict) or not all(each in config for each in settings):
            raise self.unreadable(case)
        return config

    def ask(
        self,
        case: str,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        expected: set[int],
    ) -> Answer:
        """Vault's answer to one request about `case`; `KeyUnavailable` for anything but an
        answer with a status in `expected`: never read as a key destroyed or never made."""
        try:
            status, answer = self.transport(method, path, body)
        except Unreachable:
            raise KeyUnavailable(
                f"the key service at {self.address} can't be reached: {self.now(case)}"
            ) from None
        except TimedOut:
            raise KeyUnavailable(
                f"the key service at {self.address} didn't answer within {self.timeout:g} "
                f"seconds: {self.now(case)}"
            ) from None
        if status == 403:
            raise KeyUnavailable(
                f"the key service refused Ventoux's token for {case}: check the token's policy"
            )
        if status not in expected:
            raise self.unreadable(case)
        return status, answer

    def read(self, case: str, body: dict[str, Any], *keys: str) -> Any:
        """The value at `keys` in Vault's answer; `KeyUnavailable` if it isn't there."""
        value: Any = body
        for each in keys:
            if not isinstance(value, dict) or each not in value:
                raise self.unreadable(case)
            value = value[each]
        return value

    def text(self, case: str, body: dict[str, Any], *keys: str) -> str:
        """The text at `keys` in Vault's answer; `KeyUnavailable` if it isn't text."""
        value = self.read(case, body, *keys)
        if not isinstance(value, str):
            raise self.unreadable(case)
        return value

    def unreadable(self, case: str) -> KeyUnavailable:
        # Never what Vault said: an error's text is Vault's, and unread here.
        return KeyUnavailable(
            f"the key service at {self.address} gave an answer Ventoux can't read for {case}"
        )

    @staticmethod
    def now(case: str) -> str:
        return f"{case}'s sensitive values can't be read or written now"

    def key_path(self, name: str) -> str:
        return f"/v1/{self.transit_mount}/keys/{name}"

    def mark_path(self, name: str) -> str:
        return f"/v1/{self.marks_mount}/data/ventoux/forgotten/{name}"


class Unreachable(Exception):
    """The transport couldn't reach Vault: refused, reset, or no such host."""


class TimedOut(Exception):
    """Vault didn't answer within the transport's timeout."""


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
        token = os.environ.get("VAULT_TOKEN")
        if not token:
            raise KeyUnavailable(NO_TOKEN)  # unset since: said so, never asked without one
        sent = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.address.rstrip("/") + path,
            data=sent,
            method=method,
            headers={"X-Vault-Token": token, "Content-Type": "application/json"},
        )
        try:
            with NEVER_REDIRECTED.open(request, timeout=self.timeout) as response:
                return response.status, as_json(response.read())
        except urllib.error.HTTPError as error:
            # Vault's answer with an error's status (404, 403, 400): an answer, read as such.
            return error.code, as_json(error.read())
        except urllib.error.URLError as error:
            # No connection made, even one that timed out connecting: Vault can't be reached.
            raise Unreachable(type(error.reason).__name__) from None
        except TimeoutError:
            raise TimedOut() from None  # connected, and no answer in time
        except OSError as error:  # a connection reset as Vault answered
            raise Unreachable(type(error).__name__) from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is never followed: it would carry the token to another address. Its status
    comes back as Vault's answer, which Ventoux doesn't expect, and says so."""

    def redirect_request(self, *args: Any) -> None:
        return None


# The standard library's opener, following no redirect.
NEVER_REDIRECTED = urllib.request.build_opener(NoRedirect())


def as_json(data: bytes) -> dict[str, Any]:
    """Vault's body as JSON; empty if it had none, or none Ventoux can read (said by the caller
    when it needs what isn't there)."""
    try:
        parsed = json.loads(data) if data else {}
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def as_base64(data: bytes) -> str:
    """`data` as Vault takes bytes in JSON: base64 text."""
    return base64.b64encode(data).decode()
