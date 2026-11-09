"""Connecting to Temporal as an identity, named in `pyproject.toml` (layer 20b1) (brief, D81).
See docs/layers/20-deployment.md and docs/guides/deployment.md."""

from pathlib import Path

import pytest

from ventoux.tooling.deployment import Identity, Temporal, Unconfigured, read

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
