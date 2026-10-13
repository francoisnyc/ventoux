"""The key provider: a key per case, made once, that seals and opens and never leaves (layer 9b).

Each case's sensitive values are encrypted with its own key, so forgetting a person destroys one
key and nothing else (brief, D15). The provider is the platform team's (Vault's transit engine or
a cloud KMS, after v1.0): it seals and opens for Ventoux, and never hands a key out, so a key
never leaves it. `FileKeys` is the development provider: keys in a local file.
See docs/layers/09-case-data.md (9b).
"""

import base64
import json
import os
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE = 12  # bytes: AES-GCM's standard nonce, fresh for every seal


class KeyRefused(Exception):
    """A key the provider won't make or use: why."""


class KeyProvider(Protocol):
    """Makes a case's key once, and seals and opens with it. `part` names where the data sits in
    its payload (`sensitive/0`), so sealed data moved to another place fails to open."""

    def create(self, case: str) -> None: ...

    def seal(self, case: str, data: bytes, part: str) -> bytes: ...

    def open(self, case: str, data: bytes, part: str) -> bytes: ...


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
        stored = self._read().get(case)
        if stored is None:
            raise KeyRefused(
                f"there is no key for {case}, so its sensitive values can't be read or written"
            )
        return base64.b64decode(stored)

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        keys: dict[str, str] = json.loads(self.path.read_text())
        return keys


def place(case: str, part: str) -> bytes:
    """What a sealed part is bound to, beside its key: the case and where it sits in its payload.
    AES-GCM checks it when opening (its "associated data") without encrypting it."""
    return f"{case}/{part}".encode()
