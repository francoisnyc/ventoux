"""The key provider: a key per case, made once, that seals and opens and never leaves (layer 9b).

Each case's sensitive values are encrypted with its own key, so forgetting a person destroys one
key and nothing else (brief, D15). The provider is the platform team's (Vault's transit engine or
a cloud KMS, after v1.0): it seals and opens for Ventoux, and never hands a key out, so a key
never leaves it. When a case is forgotten its key is destroyed, and never made again (layer 9c).
`FileKeys` is the development provider: keys in a local file.
See docs/layers/09-case-data.md (9b, 9c).
"""

import base64
import json
import os
from pathlib import Path
from typing import Literal, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE = 12  # bytes: AES-GCM's standard nonce, fresh for every seal
DESTROYED = None  # what the key file holds for a case once its key is destroyed (JSON's null)
# What a provider says when asked to use a destroyed key, so a client can tell a forgotten case.
FORGOTTEN = "was destroyed when it was forgotten"

# Where a case's key stands: made and usable, destroyed when the case was forgotten, or never made
# (no case was opened with that ID).
type KeyState = Literal["kept", "destroyed", "never made"]


class KeyRefused(Exception):
    """A key the provider won't make or use: why."""


class KeyProvider(Protocol):
    """Makes a case's key once, seals and opens with it, and destroys it when the case is
    forgotten (brief, D15). `part` names where the data sits in its payload (`sensitive/0`), so
    sealed data moved to another place fails to open."""

    def create(self, case: str) -> None: ...

    def seal(self, case: str, data: bytes, part: str) -> bytes: ...

    def open(self, case: str, data: bytes, part: str) -> bytes: ...

    def destroy(self, case: str) -> None: ...

    def state(self, case: str) -> KeyState: ...


class FileKeys:
    """Development only: a 256-bit key per case, kept in a JSON file, sealing with AES-256-GCM."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def create(self, case: str) -> None:
        """Make `case`'s key. Never made again: a case that had one, even one destroyed later, is
        refused, so a reused ID never inherits or remakes a key (brief, D31)."""
        keys = self._read()
        if case in keys:
            raise KeyRefused(f"a key was already made for {case}: open the case under a new ID")
        keys[case] = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()
        self.path.write_text(json.dumps(keys, indent=2, sort_keys=True))

    def destroy(self, case: str) -> None:
        """Destroy `case`'s key, so nothing sealed with it can be opened again (brief, D15)."""
        keys = self._read()
        if case not in keys:
            # Fail closed: no key was made, so there is no case to forget.
            raise KeyRefused(
                f"there is no key for {case} to destroy: no case was opened with its ID"
            )
        # Its mark stays, holding no key, so `create` refuses the ID forever (brief, D31). A
        # key destroyed already stays destroyed: a retried request does no harm.
        keys[case] = DESTROYED
        self.path.write_text(json.dumps(keys, indent=2, sort_keys=True))

    def state(self, case: str) -> KeyState:
        """Whether `case`'s key is kept, was destroyed, or was never made."""
        keys = self._read()
        if case not in keys:
            return "never made"
        return "destroyed" if keys[case] is DESTROYED else "kept"

    def seal(self, case: str, data: bytes, part: str) -> bytes:
        """`data` encrypted with `case`'s key: a fresh nonce, then the ciphertext and its tag."""
        nonce = os.urandom(NONCE)
        return nonce + AESGCM(self._key(case)).encrypt(nonce, data, place(case, part))

    def open(self, case: str, data: bytes, part: str) -> bytes:
        """What `seal` encrypted for `case` at `part`; refused for anything else."""
        try:
            return AESGCM(self._key(case)).decrypt(data[:NONCE], data[NONCE:], place(case, part))
        except InvalidTag:
            # Fail closed: never a guess at what it held.
            raise KeyRefused(
                f"a sealed part of {case} doesn't open: it was damaged, or sealed for another "
                "case or place"
            ) from None

    def _key(self, case: str) -> bytes:
        """`case`'s key, read here and nowhere else: private, so it never leaves the provider."""
        keys = self._read()
        if case not in keys:
            raise KeyRefused(
                f"there is no key for {case}, so its sensitive values can't be read or written"
            )
        stored = keys[case]
        if stored is DESTROYED:
            raise KeyRefused(
                f"the key of {case} {FORGOTTEN}: its sensitive values can't be read or written"
            )
        return base64.b64decode(stored)

    def _read(self) -> dict[str, str | None]:
        """Each case's key, by case: `DESTROYED` once it was destroyed."""
        if not self.path.exists():
            return {}
        keys: dict[str, str | None] = json.loads(self.path.read_text())
        return keys


def place(case: str, part: str) -> bytes:
    """What a sealed part is bound to, beside its key: the case and where it sits in its payload.
    AES-GCM checks it when opening (its "associated data") without encrypting it."""
    return f"{case}/{part}".encode()
