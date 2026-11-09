"""Connecting to Temporal as an identity, named in `pyproject.toml` (layer 20b1) (brief, D81).
See docs/layers/20-deployment.md and docs/guides/deployment.md."""

from pathlib import Path

import pytest

from ventoux.tooling.cli import main
from ventoux.tooling.connecting import Unconnectable, connection
from ventoux.tooling.deployment import Configuration, Identity, Temporal, Unconfigured, read

SECTION = """
[tool.ventoux.temporal]
address = "ventoux-prod.a1b2c.tmprl.cloud:7233"
namespace = "ventoux-prod.a1b2c"
server_ca = "/etc/ventoux/temporal-ca.pem"

[tool.ventoux.temporal.identities.operator]
cert = "/etc/ventoux/operator.pem"
key = "/etc/ventoux/operator.key"
"""


BASE = '[tool.ventoux.temporal]\naddress = "localhost:7233"\nnamespace = "default"\n'
OPERATOR = '[tool.ventoux.temporal.identities.operator]\ncert = "/etc/operator.pem"\n'


def configured(folder: Path, text: str) -> Path:
    path = folder / "pyproject.toml"
    path.write_text(text)
    return path


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (
            '[tool.ventoux.temporal]\nnamespace = "default"\n',
            '[tool.ventoux.temporal] needs address, such as "localhost:7233"',
        ),
        (
            '[tool.ventoux.temporal]\naddress = "localhost:7233"\n',
            '[tool.ventoux.temporal] needs namespace, such as "default"',
        ),
        (
            BASE + "tls = true\n",
            "[tool.ventoux.temporal] has no setting tls",
        ),
        (
            '[tool.ventoux.temporal]\naddress = 7233\nnamespace = "default"\n',
            '[tool.ventoux.temporal] address is a text, such as "localhost:7233"',
        ),
        (
            BASE + '[tool.ventoux.temporal.identities.operator]\ncert = "/etc/operator.pem"\n',
            "[tool.ventoux.temporal.identities.operator] needs cert and key, each a file's path",
        ),
        (
            BASE + OPERATOR + 'key = "/etc/operator.key"\npassword = "x"\n',
            "[tool.ventoux.temporal.identities.operator] has no setting password",
        ),
    ],
    ids=[
        "no address",
        "no namespace",
        "an unknown setting",
        "an address not a text",
        "an identity without its key",
        "an identity with a setting it hasn't",
    ],
)
def test_a_temporal_section_not_as_the_format_says_is_refused_saying_which_key(
    tmp_path: Path, text: str, said: str
) -> None:
    with pytest.raises(Unconfigured, match=f"^{tmp_path / 'pyproject.toml'}: " + escaped(said)):
        read(configured(tmp_path, text))


def escaped(text: str) -> str:
    """`text` matched as it is, never as a pattern."""
    import re

    return re.escape(text)


def test_the_temporal_section_is_read_as_file_paths_never_their_contents(tmp_path: Path) -> None:
    found = read(configured(tmp_path, SECTION))
    assert found.temporal == Temporal(
        address="ventoux-prod.a1b2c.tmprl.cloud:7233",
        namespace="ventoux-prod.a1b2c",
        server_ca="/etc/ventoux/temporal-ca.pem",
        identities={
            "operator": Identity(cert="/etc/ventoux/operator.pem", key="/etc/ventoux/operator.key")
        },
    )


def test_no_temporal_section_is_none_and_commands_connect_as_before(tmp_path: Path) -> None:
    assert read(configured(tmp_path, '[tool.ventoux]\ncatalog = "m:C"\n')).temporal is None


# --- Connecting as an identity ---


SECRET = "-----BEGIN PRIVATE KEY----- never-said -----END PRIVATE KEY-----"


def with_identity(folder: Path, cert: Path, key: Path, ca: Path | None = None) -> Configuration:
    """A configuration whose `operator` is `cert` and `key`, and whose server CA is `ca`."""
    ca_line = f'server_ca = "{ca}"\n' if ca is not None else ""
    text = (
        BASE
        + ca_line
        + f'[tool.ventoux.temporal.identities.operator]\ncert = "{cert}"\nkey = "{key}"\n'
    )
    return read(configured(folder, text))


def test_an_identity_not_configured_is_refused_naming_it(tmp_path: Path) -> None:
    found = with_identity(tmp_path, tmp_path / "c.pem", tmp_path / "k.pem")
    with pytest.raises(Unconnectable) as refused:
        connection(found, "reader", None, None)
    assert str(refused.value) == (
        "the identity reader isn't configured: name its cert and key in pyproject.toml, "
        "[tool.ventoux.temporal.identities.reader]"
    )


def test_a_file_that_cant_be_read_is_refused_naming_it_never_its_contents(
    tmp_path: Path,
) -> None:
    cert = tmp_path / "operator.pem"
    cert.write_text(SECRET)
    found = with_identity(tmp_path, cert, tmp_path / "missing.key")
    with pytest.raises(Unconnectable) as refused:
        connection(found, "operator", None, None)
    said = str(refused.value)
    assert said == (
        f"the identity operator's key, {tmp_path / 'missing.key'}, can't be read "
        "(FileNotFoundError): nothing was connected"
    )
    assert "never-said" not in said
    folder = tmp_path / "a-folder.key"
    folder.mkdir()
    with pytest.raises(Unconnectable, match="key, .*a-folder.key, can't be read"):
        connection(with_identity(tmp_path, cert, folder), "operator", None, None)


def test_an_identity_connects_with_its_certificate_its_key_and_the_server_ca(
    tmp_path: Path,
) -> None:
    for name in ("operator.pem", "operator.key", "ca.pem"):
        (tmp_path / name).write_bytes(name.encode())
    found = with_identity(
        tmp_path, tmp_path / "operator.pem", tmp_path / "operator.key", tmp_path / "ca.pem"
    )
    settings = connection(found, "operator", None, None)
    assert (settings.target, settings.namespace) == ("localhost:7233", "default")
    assert settings.tls is not None
    assert settings.tls.client_cert == b"operator.pem"
    assert settings.tls.client_private_key == b"operator.key"
    assert settings.tls.server_root_ca_cert == b"ca.pem"
    flagged = connection(found, "operator", "temporal.internal:7233", "ventoux")
    assert (flagged.target, flagged.namespace) == ("temporal.internal:7233", "ventoux")


def test_no_temporal_section_connects_as_before_and_refuses_an_identity_named(
    tmp_path: Path,
) -> None:
    found = read(configured(tmp_path, '[tool.ventoux]\ncatalog = "m:C"\n'))
    plain = connection(found, None, None, None)
    assert (plain.target, plain.namespace, plain.tls) == ("localhost:7233", "default", None)
    with pytest.raises(Unconnectable) as refused:
        connection(found, "operator", None, None)
    assert str(refused.value) == (
        "--identity operator names an identity, and pyproject.toml has no "
        "[tool.ventoux.temporal]: name it there, with its cert and key"
    )


# --- Every command that talks to Temporal connects as an identity ---


COMMANDS = [
    ["environment", "create", "production"],
    ["environment", "harden", "staging", "--by", "pia"],
    ["environment", "check", "production"],
    [
        "activate",
        "refund",
        "1",
        "--environment",
        "production",
        "--releases",
        "r",
        "--by",
        "pia",
        "--task-queue",
        "refunds",
    ],
    ["retire", "refund", "1", "--environment", "production", "--releases", "r", "--by", "pia"],
    ["manifest", "publish", "manifest.json"],
    ["advise", "claim-7", "--by", "ana", "--role", "support", "--recording", "r.json"],
]


@pytest.mark.parametrize("command", COMMANDS, ids=lambda command: " ".join(command[:2]))
def test_every_command_that_connects_takes_an_identity_and_refuses_one_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    configured(tmp_path, BASE)
    monkeypatch.chdir(tmp_path)
    assert main([*command, "--identity", "nope"]) == 2
    said = capsys.readouterr()
    assert "the identity nope isn't configured" in said.out + said.err
