"""The production key provider: Vault's transit engine, a key per case (layer 19c).

Through `VaultKeys`, given a recording of Vault's answers, request by request: no test here
reaches Vault, but the one marked to run where `vault` is installed. See
docs/layers/19-audit-keys.md (19c), docs/guides/audit.md and brief, D78.
"""

from typing import Any

import pytest

from ventoux.tooling.keys import KeyRefused
from ventoux.tooling.vault import Exchange, Recording, RecordingRefused, VaultKeys

ADDRESS = "https://vault.internal:8200"
NAME = "ventoux-claim-7"  # claim-7's key, as Vault names it
KEYS = "/v1/transit/keys"
MARKS = "/v1/secret/data/ventoux/forgotten"
NOT_FOUND: tuple[int, dict[str, Any]] = (404, {"errors": []})


def no_mark(name: str = NAME) -> Exchange:
    """Vault's key-value engine, asked for a case's mark, holding none."""
    return Exchange("GET", f"{MARKS}/{name}", None, NOT_FOUND)


def marked(name: str = NAME) -> Exchange:
    """Vault's key-value engine, asked for a case's mark, holding it: the case was forgotten."""
    return Exchange("GET", f"{MARKS}/{name}", None, (200, {"data": {"data": {"forgotten": True}}}))


def no_key(name: str = NAME) -> Exchange:
    """Vault's transit engine, asked for a key it doesn't hold."""
    return Exchange("GET", f"{KEYS}/{name}", None, NOT_FOUND)


def vault(*exchanges: Exchange) -> VaultKeys:
    """A provider answered by `exchanges`, in order, and by nothing else."""
    return VaultKeys(ADDRESS, "transit", "secret", transport=Recording(list(exchanges)))


NEVER_MADE = "there is no key for claim-7, so its sensitive values can't be read or written"
DESTROYED = (
    "the key of claim-7 was destroyed when it was forgotten: its sensitive values can't be read "
    "or written"
)


def test_a_key_the_provider_cant_give_is_an_error_saying_why() -> None:
    # The curriculum's negative test: a case whose key was never made, or whose mark says it was
    # forgotten, gets an error saying so, never an empty value and never a guess. The mark is read
    # first: forgotten, the key itself is never asked for (brief, D31) (brief, D78).
    for use in ("seal", "open"):
        never = vault(no_mark(), no_key())
        with pytest.raises(KeyRefused) as refused:
            getattr(never, use)("claim-7", b'"1 85 05"', "sensitive/0")
        assert str(refused.value) == NEVER_MADE
        forgotten = vault(marked())
        with pytest.raises(KeyRefused) as refused:
            getattr(forgotten, use)("claim-7", b'"1 85 05"', "sensitive/0")
        assert str(refused.value) == DESTROYED


def key(name: str = NAME, **config: Any) -> Exchange:
    """Vault's transit engine, asked for a key, holding it: as Ventoux makes it, unless `config`
    says otherwise."""
    settings = {"type": "aes256-gcm96", "exportable": False, "allow_plaintext_backup": False}
    return Exchange("GET", f"{KEYS}/{name}", None, (200, {"data": settings | config}))


def test_a_key_that_can_leave_vault_or_of_another_type_is_never_used() -> None:
    # Read from the key's configuration before each use, never remembered: Vault lets a key be
    # made exportable later, never the other way. Refused, saying why, and nothing is sealed or
    # opened with it (brief, D15) (brief, D78).
    refused: dict[str, dict[str, Any]] = {
        "the key of claim-7 can leave the key service (exportable): it is not used": {
            "exportable": True
        },
        "the key of claim-7 can leave the key service (plaintext backup allowed): it is not used": {
            "allow_plaintext_backup": True
        },
        "the key of claim-7 is aes128-gcm96, not aes256-gcm96: it is not used": {
            "type": "aes128-gcm96"
        },
    }
    for said, config in refused.items():
        for use in ("seal", "open"):
            keys = vault(no_mark(), key(**config))
            with pytest.raises(KeyRefused) as refusal:
                getattr(keys, use)("claim-7", b'"1 85 05"', "sensitive/0")
            assert str(refusal.value) == said


def test_a_recording_refuses_a_request_it_doesnt_hold() -> None:
    # A request out of place, or past the last one recorded, is refused, saying which, so a test
    # never passes on an answer meant for another request. Never its body: it may hold a value
    # being sealed (brief, D62) (brief, D78).
    recording = Recording([no_mark()])
    with pytest.raises(RecordingRefused) as refused:
        recording("GET", f"{KEYS}/{NAME}", None)
    assert str(refused.value) == (
        f"the recording holds no GET {KEYS}/{NAME} (request 1): record it, or fix what asked"
    )
    recording = Recording([no_mark()])
    recording("GET", f"{MARKS}/{NAME}", None)
    with pytest.raises(RecordingRefused) as refused:
        recording("POST", "/v1/transit/encrypt/ventoux-claim-7", {"plaintext": "MSA4NSAwNQ=="})
    assert str(refused.value) == (
        "the recording holds no POST /v1/transit/encrypt/ventoux-claim-7 (request 2): record it, "
        "or fix what asked"
    )
    # A body other than recorded is another request.
    recording = Recording([Exchange("POST", "/v1/x", {"a": 1}, (204, {}))])
    with pytest.raises(RecordingRefused):
        recording("POST", "/v1/x", {"a": 2})
