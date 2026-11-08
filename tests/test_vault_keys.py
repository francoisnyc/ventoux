"""The production key provider: Vault's transit engine, a key per case (layer 19c).

Through `VaultKeys`, given a recording of Vault's answers, request by request: no test here
reaches Vault, but the one marked to run where `vault` is installed. See
docs/layers/19-audit-keys.md (19c), docs/guides/audit.md and brief, D78.
"""

import base64
import inspect
import json
import logging
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
from test_audit_export import claim_records

from ventoux.case.definition import parse_case
from ventoux.temporal.audit import exported, sensitive_fields
from ventoux.tooling.audit import FileAudit, read_audit
from ventoux.tooling.keys import FileKeys, KeyRefused, KeyUnavailable
from ventoux.tooling.vault import (
    Answer,
    Exchange,
    Https,
    Recording,
    RecordingRefused,
    TimedOut,
    Unreachable,
    VaultKeys,
    vault_name,
)

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


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


VALUE = '"1 85 05 78 006 084 36"'  # a national ID, as the converter writes it
SEALED = "vault:v1:8SDd3WHDOjf7mq69CyCqYjBXAiQQAVZRkFM13ok481zoCmHnSeDX9vyf7w=="


def test_a_value_is_sealed_for_its_place_and_opens_only_there() -> None:
    # Vault seals and opens; the key never leaves it. The case and the part are sent as the
    # associated data, as FileKeys binds them, so a value moved to another place doesn't open
    # there: Vault refuses it, and so does Ventoux, never guessing (brief, D31) (brief, D78).
    bound = b64("claim-7/sensitive/0")
    sealing = Exchange(
        "POST",
        f"/v1/transit/encrypt/{NAME}",
        {"plaintext": b64(VALUE), "associated_data": bound},
        (200, {"data": {"ciphertext": SEALED, "key_version": 1}}),
    )
    assert vault(no_mark(), key(), sealing).seal("claim-7", VALUE.encode(), "sensitive/0") == (
        SEALED.encode()
    )
    opening = Exchange(
        "POST",
        f"/v1/transit/decrypt/{NAME}",
        {"ciphertext": SEALED, "associated_data": bound},
        (200, {"data": {"plaintext": b64(VALUE)}}),
    )
    keys = vault(no_mark(), key(), opening)
    assert keys.open("claim-7", SEALED.encode(), "sensitive/0") == VALUE.encode()
    moved = Exchange(
        "POST",
        f"/v1/transit/decrypt/{NAME}",
        {"ciphertext": SEALED, "associated_data": b64("claim-7/sensitive/1")},
        (400, {"errors": ["cipher: message authentication failed"]}),
    )
    with pytest.raises(KeyRefused) as refused:
        vault(no_mark(), key(), moved).open("claim-7", SEALED.encode(), "sensitive/1")
    assert str(refused.value) == (
        "a sealed part of claim-7 doesn't open: it was damaged, or sealed for another case or place"
    )


def unavailable(name: str) -> dict[str, tuple[Answer | Exception, str]]:
    """Each way Vault can fail to answer, as the transport meets it, and what the case is told."""
    return {
        "unreachable": (
            Unreachable("connection refused"),
            (
                f"the key service at {ADDRESS} can't be reached: {name}'s sensitive values can't "
                "be read or written now"
            ),
        ),
        "timing out": (
            TimedOut(),
            (
                f"the key service at {ADDRESS} didn't answer within 10 seconds: {name}'s "
                "sensitive values can't be read or written now"
            ),
        ),
        "the token refused": (
            (403, {"errors": ["permission denied"]}),
            f"the key service refused Ventoux's token for {name}: check the token's policy",
        ),
        "a status it doesn't expect": (
            (503, {"errors": ["Vault is sealed"]}),
            f"the key service at {ADDRESS} gave an answer Ventoux can't read for {name}",
        ),
        "a body it can't read": (
            (200, {"warnings": []}),
            f"the key service at {ADDRESS} gave an answer Ventoux can't read for {name}",
        ),
    }


def test_vault_not_answering_is_unavailable_never_a_refusal() -> None:
    # Not now, never final: unreachable, timing out, refusing the token, or answering something
    # it can't read, at any request of any use. A workflow task or an activity meeting it is
    # retried until Vault answers; never read as "never made" or "destroyed" (brief, D17)
    # (brief, D78).
    bound = b64("claim-7/sensitive/0")
    encrypt = {"plaintext": b64(VALUE), "associated_data": bound}
    decrypt = {"ciphertext": SEALED, "associated_data": bound}
    uses: dict[str, tuple[list[Exchange], Callable[[VaultKeys], object]]] = {
        "create": (
            [no_mark(), no_key(), Exchange("POST", f"{KEYS}/{NAME}", MADE, (204, {}))],
            lambda keys: keys.create("claim-7"),
        ),
        "seal": (
            [no_mark(), key(), Exchange("POST", f"/v1/transit/encrypt/{NAME}", encrypt, (200, {}))],
            lambda keys: keys.seal("claim-7", VALUE.encode(), "sensitive/0"),
        ),
        "open": (
            [no_mark(), key(), Exchange("POST", f"/v1/transit/decrypt/{NAME}", decrypt, (200, {}))],
            lambda keys: keys.open("claim-7", SEALED.encode(), "sensitive/0"),
        ),
    }
    for use, (asked, call) in uses.items():
        for kind, (answer, said) in unavailable("claim-7").items():
            for at, failing in enumerate(asked):  # each request in turn, those before answered
                if (use, at, kind) == ("create", 2, "a body it can't read"):
                    continue  # making a key reads nothing back: Vault's 200 says it was made
                keys = vault(*asked[:at], replace(failing, answer=answer))
                with pytest.raises(KeyUnavailable) as failed:
                    call(keys)
                assert str(failed.value) == said, (use, kind, at)


class Vault(BaseHTTPRequestHandler):
    """A stand-in for Vault on this machine, for the HTTPS transport's own test: it notes each
    request, its token, and answers by path."""

    seen: ClassVar[list[tuple[str, str, str | None]]] = []

    def do_GET(self) -> None:
        Vault.seen.append(("GET", self.path, self.headers.get("X-Vault-Token")))
        if "/moved/" in self.path:
            self.send_response(307)
            self.send_header("Location", "http://127.0.0.1:9/v1/elsewhere")
            self.end_headers()
            return
        answer = json.dumps({"errors": []}).encode()
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def log_message(self, format: str, *args: Any) -> None:
        pass  # quiet: a test's server


@contextmanager
def serving(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    """A server on this machine, on a free port, for the length of the block: its address."""
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def silent() -> Iterator[str]:
    """A port that accepts and never answers, for the length of the block: its address."""
    listening = socket.socket()
    listening.bind(("127.0.0.1", 0))
    listening.listen()
    try:
        yield f"http://127.0.0.1:{listening.getsockname()[1]}"
    finally:
        listening.close()


def test_the_https_transport_sends_the_token_only_to_vault_and_never_says_it(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The token goes in Vault's header, read as the call is made; a redirect is never followed,
    # so it can't be carried elsewhere; a port that refuses, or a Vault that never answers, is
    # unavailable. And the token is in no message, repr, log or recording (brief, D62) (brief,
    # D78).
    monkeypatch.setenv("VAULT_TOKEN", TOKEN)
    caplog.set_level(logging.DEBUG)
    said: list[str] = []
    Vault.seen.clear()
    with serving(Vault) as address:
        keys = VaultKeys(address, "transit", "secret")
        assert keys.state("claim-7") == "never made"
        assert Vault.seen == [
            ("GET", f"{MARKS}/{NAME}", TOKEN),
            ("GET", f"{KEYS}/{NAME}", TOKEN),
        ]
        moved = VaultKeys(address, "transit", "secret/moved")
        with pytest.raises(KeyUnavailable) as failed:
            moved.state("claim-7")
        assert str(failed.value) == (
            f"the key service at {address} gave an answer Ventoux can't read for claim-7"
        )
        said.append(str(failed.value))
        assert len(Vault.seen) == 3  # the redirect not followed
        said += [repr(keys), repr(vars(keys)), repr(vars(keys.transport))]
    with serving(Vault) as address:
        pass  # a port nothing listens on any more
    with pytest.raises(KeyUnavailable) as failed:
        VaultKeys(address, "transit", "secret").state("claim-7")
    assert str(failed.value) == (
        f"the key service at {address} can't be reached: claim-7's sensitive values can't be read "
        "or written now"
    )
    said.append(str(failed.value))
    with silent() as address, pytest.raises(KeyUnavailable) as failed:
        VaultKeys(address, "transit", "secret", timeout=0.2).state("claim-7")
    assert str(failed.value) == (
        f"the key service at {address} didn't answer within 0.2 seconds: claim-7's sensitive "
        "values can't be read or written now"
    )
    said.append(str(failed.value))
    recording = Recording([no_mark(), no_key()])
    VaultKeys(ADDRESS, "transit", "secret", transport=recording).state("claim-7")
    said.append(repr(recording))
    for each in [*said, caplog.text]:
        assert TOKEN not in each


def test_a_keys_state_is_read_only_from_vaults_answer() -> None:
    # Kept, destroyed, never made: each said only when Vault answered so. The mark says destroyed
    # even with the key still there (a destroy cut short); anything else is unavailable, never
    # read as forgotten or never made (brief, D32) (brief, D78).
    assert vault(no_mark(), key()).state("claim-7") == "kept"
    assert vault(no_mark(), no_key()).state("claim-7") == "never made"
    assert vault(marked()).state("claim-7") == "destroyed"
    for kind, (answer, said) in unavailable("claim-7").items():
        for at, asked in enumerate([no_mark(), key()]):
            keys = vault(*[no_mark(), key()][:at], replace(asked, answer=answer))
            with pytest.raises(KeyUnavailable) as failed:
                keys.state("claim-7")
            assert str(failed.value) == said, (kind, at)


def test_an_answer_of_another_shape_is_unavailable_never_a_value() -> None:
    # A ciphertext that isn't text, or a plaintext that isn't base64 (`TWFu!` reads as `Man` to a
    # decoder that skips what it can't read), is an answer Ventoux can't read: never sealed or
    # opened as something else (brief, D78).
    said = f"the key service at {ADDRESS} gave an answer Ventoux can't read for claim-7"
    bound = b64("claim-7/sensitive/0")
    encrypt = {"plaintext": b64(VALUE), "associated_data": bound}
    sealing = Exchange(
        "POST", f"/v1/transit/encrypt/{NAME}", encrypt, (200, {"data": {"ciphertext": 7}})
    )
    with pytest.raises(KeyUnavailable) as failed:
        vault(no_mark(), key(), sealing).seal("claim-7", VALUE.encode(), "sensitive/0")
    assert str(failed.value) == said
    decrypt = {"ciphertext": SEALED, "associated_data": bound}
    opening = Exchange(
        "POST",
        f"/v1/transit/decrypt/{NAME}",
        decrypt,
        (200, {"data": {"plaintext": "TWFu!"}}),
    )
    with pytest.raises(KeyUnavailable) as failed:
        vault(no_mark(), key(), opening).open("claim-7", SEALED.encode(), "sensitive/0")
    assert str(failed.value) == said
    # A key's configuration missing a setting is unreadable too, never taken as allowed.
    partial = Exchange("GET", f"{KEYS}/{NAME}", None, (200, {"data": {"type": "aes256-gcm96"}}))
    with pytest.raises(KeyUnavailable) as failed:
        vault(no_mark(), partial).seal("claim-7", VALUE.encode(), "sensitive/0")
    assert str(failed.value) == said


MARK = {"data": {"forgotten": True}}  # the mark, as Ventoux writes it


def write_mark(answer: Answer | Exception = (200, {})) -> Exchange:
    return Exchange("POST", f"{MARKS}/{NAME}", MARK, answer)


def allow_deletion(answer: Answer | Exception = (204, {})) -> Exchange:
    return Exchange("POST", f"{KEYS}/{NAME}/config", {"deletion_allowed": True}, answer)


def delete(answer: Answer | Exception = (204, {})) -> Exchange:
    return Exchange("DELETE", f"{KEYS}/{NAME}", None, answer)


def test_destroying_marks_the_case_first_and_destroying_again_finishes() -> None:
    # The mark first, then the key's deletion allowed, then the key deleted: from the mark on the
    # case reads as destroyed, whatever fails after. A destroy cut short at any step is finished by
    # the next, which writes nothing twice it doesn't need and takes a key already gone as deleted
    # (brief, D32) (brief, D78).
    down = Unreachable("connection refused")
    vault(no_mark(), key(), write_mark(), allow_deletion(), delete()).destroy("claim-7")
    # Cut short at the mark: nothing changed, so destroying again does it all.
    with pytest.raises(KeyUnavailable):
        vault(no_mark(), key(), write_mark(down)).destroy("claim-7")
    vault(no_mark(), key(), write_mark(), allow_deletion(), delete()).destroy("claim-7")
    # Cut short after the mark: the case is destroyed already; destroying again finishes.
    for cut in (
        [write_mark(), allow_deletion(down)],
        [write_mark(), allow_deletion(), delete(down)],
    ):
        with pytest.raises(KeyUnavailable):
            vault(no_mark(), key(), *cut).destroy("claim-7")
        assert vault(marked()).state("claim-7") == "destroyed"
        vault(marked(), key(), allow_deletion(), delete()).destroy("claim-7")
    # The key gone already: nothing left to do; gone between its read and its deletion (two
    # destroys overlapping), it counts as deleted.
    vault(marked(), no_key()).destroy("claim-7")
    vault(marked(), key(), allow_deletion(), delete(NOT_FOUND)).destroy("claim-7")
    # No key and no mark: there is no case to forget (as FileKeys says).
    with pytest.raises(KeyRefused) as refused:
        vault(no_mark(), no_key()).destroy("claim-7")
    assert str(refused.value) == (
        "there is no key for claim-7 to destroy: no case was opened with its ID"
    )


def test_read_audit_with_vault_down_fails_never_saying_forgotten(tmp_path: Path) -> None:
    # A reader who may see the national ID asks while Vault doesn't answer: an error saying so,
    # never `‹forgotten›`, which would tell an auditor the case was forgotten when it wasn't
    # (brief, D32) (brief, D78).
    definition, records = claim_records()
    sealing = FileKeys(tmp_path / "keys.json")
    sealing.create("claim-7")
    store = FileAudit(tmp_path / "audit")
    store.append(
        exported("claim-7", records, sensitive_fields(parse_case(definition)), {}, sealing)
    )
    down = vault(replace(no_mark(), answer=Unreachable("connection refused")))
    with pytest.raises(KeyUnavailable) as failed:
        read_audit(store, "claim-7", ["claims-sensitive"], down)
    assert str(failed.value) == (
        f"the key service at {ADDRESS} can't be reached: claim-7's sensitive values can't be read "
        "or written now"
    )


DEVELOPMENT_TOKEN = "ventoux-development-root"  # the development server's own root token
VAULT = shutil.which("vault")


@contextmanager
def development_vault(folder: Path) -> Iterator[str]:
    """A development Vault (`vault server -dev`) on this machine, in memory, with a transit
    engine, for the length of the block: its address. Asked a bounded number of times."""
    assert VAULT is not None
    listening = socket.socket()
    listening.bind(("127.0.0.1", 0))
    port = listening.getsockname()[1]
    listening.close()
    address = f"http://127.0.0.1:{port}"
    with (folder / "vault.log").open("w") as log:
        server = subprocess.Popen(
            [
                VAULT,
                "server",
                "-dev",
                f"-dev-listen-address=127.0.0.1:{port}",
                f"-dev-root-token-id={DEVELOPMENT_TOKEN}",
                "-dev-no-store-token",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            ask = Https(address, 2)
            for _ in range(100):
                try:
                    if ask("GET", "/v1/sys/health", None)[0] == 200:
                        break
                except (Unreachable, TimedOut):
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError(f"the development Vault never answered: {address}")
            status, _ = ask("POST", "/v1/sys/mounts/transit", {"type": "transit"})
            assert status in (200, 204), status
            yield address
        finally:
            server.terminate()
            server.wait(timeout=10)


@pytest.mark.skipif(
    VAULT is None, reason="runs only where vault is installed (a development Vault)"
)
def test_against_a_development_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # What only a real Vault shows: a value sealed for one place doesn't open at another (the
    # part bound as associated data), a key made exportable is refused from then on, and the mark
    # outlives the deleted key, whatever Vault would let be made again. The recordings' answers
    # are checked here against Vault's own (brief, D78).
    monkeypatch.setenv("VAULT_TOKEN", DEVELOPMENT_TOKEN)
    with development_vault(tmp_path) as address:
        keys = VaultKeys(address, "transit", "secret")
        case = "Claim-7.a"  # a capital and a dot: the name escapes them
        assert keys.state(case) == "never made"
        keys.create(case)
        assert keys.state(case) == "kept"
        with pytest.raises(KeyRefused, match="a key was already made for Claim-7.a"):
            keys.create(case)
        sealed = keys.seal(case, VALUE.encode(), "sensitive/0")
        assert sealed.startswith(b"vault:v1:")
        assert VALUE.encode() not in sealed
        assert keys.open(case, sealed, "sensitive/0") == VALUE.encode()
        with pytest.raises(KeyRefused, match="doesn't open"):
            keys.open(case, sealed, "sensitive/1")  # moved to another place
        keys.create("claim-8")
        with pytest.raises(KeyRefused, match="doesn't open"):
            keys.open("claim-8", sealed, "sensitive/0")  # another case's key
        # Made exportable outside Ventoux: never used again.
        ask = Https(address, 2)
        status, _ = ask("POST", f"/v1/transit/keys/{vault_name(case)}/config", {"exportable": True})
        assert status in (200, 204), status
        with pytest.raises(KeyRefused, match=r"can leave the key service \(exportable\)"):
            keys.seal(case, VALUE.encode(), "sensitive/0")
        # Destroyed: the mark, then the key; destroying again does nothing more.
        keys.destroy("claim-8")
        assert keys.state("claim-8") == "destroyed"
        assert ask("GET", f"/v1/transit/keys/{vault_name('claim-8')}", None)[0] == 404
        keys.destroy("claim-8")
        with pytest.raises(KeyRefused, match="was destroyed when it was forgotten"):
            keys.open("claim-8", sealed, "sensitive/0")
        # Vault would make a key of that name again; the mark keeps it unused.
        made_again = {"type": "aes256-gcm96", "exportable": False, "allow_plaintext_backup": False}
        assert ask("POST", f"/v1/transit/keys/{vault_name('claim-8')}", made_again)[0] in (200, 204)
        assert keys.state("claim-8") == "destroyed"
        with pytest.raises(KeyRefused, match="was destroyed when it was forgotten"):
            keys.seal("claim-8", VALUE.encode(), "sensitive/0")
        with pytest.raises(KeyRefused, match="a key was already made for claim-8"):
            keys.create("claim-8")


# The guide's policy for Ventoux's token, word for word (docs/guides/audit.md, "The production key
# service: Vault"), for mounts named `transit` and `secret`.
POLICY = """\
path "transit/keys/ventoux-*" {
  capabilities = ["create", "read", "update", "delete"]
}
path "transit/encrypt/ventoux-*" {
  capabilities = ["update"]
}
path "transit/decrypt/ventoux-*" {
  capabilities = ["update"]
}
path "secret/data/ventoux/forgotten/ventoux-*" {
  capabilities = ["create", "read", "update"]
}
"""


@pytest.mark.skipif(
    VAULT is None, reason="runs only where vault is installed (a development Vault)"
)
def test_the_guides_policy_is_all_ventoux_needs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A token holding only the guide's policy opens, seals, forgets: everything Ventoux asks. And
    # nothing else: no other key, and no deleting a mark, so a forgotten case can't be unmarked
    # with Ventoux's token (brief, D19) (brief, D78).
    assert POLICY in (Path(__file__).parent.parent / "docs" / "guides" / "audit.md").read_text()
    monkeypatch.setenv("VAULT_TOKEN", DEVELOPMENT_TOKEN)
    with development_vault(tmp_path) as address:
        root = Https(address, 2)
        assert root("PUT", "/v1/sys/policies/acl/ventoux", {"policy": POLICY})[0] in (200, 204)
        status, body = root("POST", "/v1/auth/token/create", {"policies": ["ventoux"]})
        assert status == 200, status
        made = {"type": "aes256-gcm96", "exportable": False, "allow_plaintext_backup": False}
        assert root("POST", "/v1/transit/keys/payroll", made)[0] in (200, 204)
        monkeypatch.setenv("VAULT_TOKEN", body["auth"]["client_token"])  # Ventoux's own now
        keys = VaultKeys(address, "transit", "secret")
        keys.create("claim-7")
        sealed = keys.seal("claim-7", VALUE.encode(), "sensitive/0")
        assert keys.open("claim-7", sealed, "sensitive/0") == VALUE.encode()
        keys.destroy("claim-7")
        assert keys.state("claim-7") == "destroyed"
        ventoux = Https(address, 2)
        assert ventoux("GET", "/v1/transit/keys/payroll", None)[0] == 403
        # Deleting a mark, its latest version or all of them: refused.
        for path in (f"{MARKS}/{NAME}", f"/v1/secret/metadata/ventoux/forgotten/{NAME}"):
            assert ventoux("DELETE", path, None)[0] == 403, path
