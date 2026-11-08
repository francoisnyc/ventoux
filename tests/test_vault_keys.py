"""The production key provider: Vault's transit engine, a key per case (layer 19c).

Through `VaultKeys`, given a recording of Vault's answers, request by request: no test here
reaches Vault, but the one marked to run where `vault` is installed. See
docs/layers/19-audit-keys.md (19c), docs/guides/audit.md and brief, D78.
"""

import inspect
from pathlib import Path
from typing import Any

import pytest

from ventoux.tooling.keys import KeyRefused
from ventoux.tooling.vault import Exchange, Recording, RecordingRefused, VaultKeys, vault_name

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


TOKEN = "hvs.ventoux-test-token-6Qm2"  # a token a test sets, searched for where it must never be


def test_settings_are_named_the_token_comes_from_vault_token_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Fail closed: no default address or mount, plain http only for a development server on this
    # machine, and the token read from VAULT_TOKEN alone: never a file (Vault's own CLI keeps one
    # in ~/.vault-token), an argument, or the object, so it is in no repr (brief, D62) (brief, D78).
    for address in ("http://vault.internal:8200", "ftp://vault.internal"):
        with pytest.raises(ValueError) as refused:
            VaultKeys(address, "transit", "secret", transport=Recording([]))
        assert str(refused.value) == (
            f"the key service is reached over https: {address} is only for a development server "
            "on localhost"
        )
    for local in ("http://localhost:8200", "http://127.0.0.1:8200"):
        VaultKeys(local, "transit", "secret", transport=Recording([]))  # accepted
    for missing, settings in (
        ("address", ("", "transit", "secret")),
        ("transit_mount", (ADDRESS, "", "secret")),
        ("marks_mount", (ADDRESS, "transit", "")),
    ):
        with pytest.raises(ValueError) as refused:
            VaultKeys(*settings, transport=Recording([]))
        assert str(refused.value) == (
            f"VaultKeys needs an address, a transit mount and a marks mount: {missing} is empty"
        )
    # No VAULT_TOKEN: refused, whatever else holds a token.
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".vault-token").write_text(TOKEN)
    with pytest.raises(ValueError) as refused:
        VaultKeys(ADDRESS, "transit", "secret")
    assert str(refused.value) == "VAULT_TOKEN is not set: the key service can't be asked"
    assert "token" not in inspect.signature(VaultKeys).parameters
    # Set, it is read as each call is made: never kept, so never in a repr.
    monkeypatch.setenv("VAULT_TOKEN", TOKEN)
    keys = VaultKeys(ADDRESS, "transit", "secret")
    assert TOKEN not in repr(keys) + repr(vars(keys)) + repr(vars(keys.transport))


def test_each_case_id_has_one_name_no_url_reads_as_a_path() -> None:
    # Lowercase letters, digits and `-` stay; every other byte is `_` and two hex digits. So no two
    # IDs share a name, whether Vault folds capitals or not, and no name holds what a URL reads as
    # a path, a query or a fragment (brief, D78).
    assert vault_name("refund-A-1001") == "ventoux-refund-_41-1001"
    assert vault_name("claim 7") == "ventoux-claim_207"
    awkward = ["claim-7", "Claim-7", "claim.7", "..", ".", "claim%2F7", "a?b", "a#b", "a_b", "é"]
    names = [vault_name(each) for each in awkward]
    assert len(set(names)) == len(awkward)  # one name each
    assert len({name.lower() for name in names}) == len(awkward)  # with capitals folded too
    for name in names:
        assert set(name) <= set("abcdefghijklmnopqrstuvwxyz0123456789-_"), name
    assert vault_name("..") == "ventoux-_2e_2e"
    # Refused, saying why: no name at all, or one past what the provider names (128 characters).
    with pytest.raises(KeyRefused) as refused:
        vault_name("")
    assert str(refused.value) == "a case ID can't be empty"
    assert len(vault_name("a" * 120)) == 128
    with pytest.raises(KeyRefused) as refused:
        vault_name("a" * 121)
    assert str(refused.value) == (
        "a case ID names a key in the key service, and its name can't pass 128 characters"
    )


MADE = {"type": "aes256-gcm96", "exportable": False, "allow_plaintext_backup": False}


def test_a_key_is_made_once_never_able_to_leave_vault() -> None:
    # Made with each setting stated, never left to Vault's defaults; refused for a case with a key,
    # or with a mark: an ID once forgotten never opens a case again (brief, D31) (brief, D78).
    keys = vault(no_mark(), no_key(), Exchange("POST", f"{KEYS}/{NAME}", MADE, (204, {})))
    keys.create("claim-7")
    for held in (marked(), key()):
        exchanges = [held] if held == marked() else [no_mark(), held]
        with pytest.raises(KeyRefused) as refused:
            vault(*exchanges).create("claim-7")
        assert (
            str(refused.value) == "a key was already made for claim-7: open the case under a new ID"
        )
    with pytest.raises(KeyRefused):
        vault().create("")  # no name: refused before Vault is asked
