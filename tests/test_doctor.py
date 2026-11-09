"""`ventoux doctor`: checking a deployment, with the rights it is given and no more (layer 20b2)
(brief, D81). See docs/layers/20-deployment.md and docs/guides/deployment.md, "Checking the
deployment"."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from ventoux.tooling.cli import main
from ventoux.tooling.deployment import Configuration, read
from ventoux.tooling.doctor import RULES, Finding, diagnose, outcome, said

# A deployment doctor finds healthy: each setting it reads, named as the platform team would.
HEALTHY = """
[tool.ventoux]
catalog = "doctor_deployment:CATALOG"
keys = "doctor_deployment:KEYS"
audit = "doctor_deployment:AUDIT"
"""


def deployment(folder: Path, text: str = HEALTHY) -> Configuration:
    path = folder / "pyproject.toml"
    path.write_text(text)
    return read(path)


def findings(found: Configuration) -> list[Finding]:
    return asyncio.run(diagnose(found, "production"))


def verdict(found: Configuration, rule: str) -> Finding:
    return next(finding for finding in findings(found) if finding.rule == rule)


def test_a_configuration_doctor_cant_read_exits_2_saying_why_and_runs_no_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.ventoux]\ncatalog = 7\n")
    monkeypatch.chdir(tmp_path)
    assert main(["doctor", "production"]) == 2
    said = capsys.readouterr()
    assert "[tool.ventoux] catalog is a text" in said.err
    assert said.out == ""  # no rule ran, so none is said


def test_a_rule_failed_exits_1_nothing_failed_exits_0_and_strict_fails_an_unchecked_one(
    tmp_path: Path,
) -> None:
    healthy = findings(deployment(tmp_path))
    assert {finding.verdict for finding in healthy} == {"passed", "unchecked"}
    assert outcome(healthy, strict=False) == 0
    assert outcome(healthy, strict=True) == 1  # an unchecked rule fails only with --strict
    lines = said(healthy, "production")
    assert any(line.startswith("unchecked  temporal.retention: ") for line in lines)
    unchecked = sum(finding.verdict == "unchecked" for finding in healthy)
    assert (
        lines[-1]
        == f"production: {len(healthy) - unchecked} passed, 0 failed, {unchecked} unchecked"
    )

    broken = findings(deployment(tmp_path, "[tool.ventoux]\n"))
    assert outcome(broken, strict=False) == 1
    assert any(line.startswith("FAILED     catalog.named: ") for line in said(broken, "production"))


def test_every_rule_runs_whatever_the_others_give(tmp_path: Path) -> None:
    found = deployment(tmp_path, '[tool.ventoux]\ncatalog = "doctor_broken:CATALOG"\n')
    seen = findings(found)
    assert [finding.rule for finding in seen] == [rule.name for rule in RULES]
    assert verdict(found, "catalog.named").verdict == "unchecked"


def test_an_error_a_rule_doesnt_expect_is_unchecked_by_its_kind_never_its_message(
    tmp_path: Path,
) -> None:
    found = deployment(tmp_path, '[tool.ventoux]\ncatalog = "doctor_broken:CATALOG"\n')
    assert verdict(found, "catalog.named") == Finding(
        "catalog.named", "unchecked", "met RuntimeError, which it doesn't expect"
    )


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        (
            "",
            (
                "FAILED",
                'no catalog is named: name the deployment\'s, [tool.ventoux] catalog = "module:NAME"',
            ),
        ),
        (
            'catalog = "ventoux.testing:CATALOG"',
            (
                "FAILED",
                (
                    "the catalog is the development one, ventoux.testing:CATALOG: name the "
                    "deployment's"
                ),
            ),
        ),
        (
            'catalog = "doctor_nowhere:CATALOG"',
            (
                "unchecked",
                "doctor_nowhere can't be imported: No module named 'doctor_nowhere'",
            ),
        ),
        (
            'catalog = "doctor_deployment:CATALOG"',
            ("passed", "the catalog is doctor_deployment:CATALOG, not the development one"),
        ),
    ],
    ids=["none named", "the development one", "unimportable", "the deployment's"],
)
def test_catalog_named(tmp_path: Path, setting: str, expected: tuple[str, str]) -> None:
    found = deployment(tmp_path, f"[tool.ventoux]\n{setting}\n")
    seen = verdict(found, "catalog.named")
    assert (seen.verdict, seen.said) == expected


@pytest.mark.parametrize(
    ("rule", "setting", "expected"),
    [
        (
            "keys.named",
            "",
            (
                "FAILED",
                (
                    "no key service is named: name the deployment's, [tool.ventoux] keys = "
                    '"module:NAME"'
                ),
            ),
        ),
        (
            "keys.named",
            'keys = "doctor_deployment:FILE_KEYS"',
            (
                "FAILED",
                (
                    "doctor_deployment:FILE_KEYS is FileKeys, which is for development: name the "
                    "deployment's key service"
                ),
            ),
        ),
        (
            "keys.named",
            'keys = "doctor_deployment:UNSAID"',
            (
                "FAILED",
                (
                    "doctor_deployment:UNSAID is Unsaid, which doesn't say whether it is for "
                    "development: give it `development = False`, or name the deployment's key service"
                ),
            ),
        ),
        (
            "keys.named",
            'keys = "doctor_nowhere:KEYS"',
            ("unchecked", "doctor_nowhere can't be imported: No module named 'doctor_nowhere'"),
        ),
        (
            "keys.named",
            'keys = "doctor_deployment:KEYS"',
            ("passed", "the key service is doctor_deployment:KEYS, VaultKeys"),
        ),
        (
            "audit.named",
            "",
            (
                "FAILED",
                (
                    "no audit store is named: name the deployment's, [tool.ventoux] audit = "
                    '"module:NAME"'
                ),
            ),
        ),
        (
            "audit.named",
            'audit = "doctor_deployment:FILE_AUDIT"',
            (
                "FAILED",
                (
                    "doctor_deployment:FILE_AUDIT is FileAudit, which is for development: name the "
                    "deployment's audit store"
                ),
            ),
        ),
        (
            "audit.named",
            'audit = "doctor_deployment:UNSAID"',
            (
                "FAILED",
                (
                    "doctor_deployment:UNSAID is Unsaid, which doesn't say whether it is for "
                    "development: give it `development = False`, or name the deployment's audit store"
                ),
            ),
        ),
        (
            "audit.named",
            'audit = "doctor_nowhere:AUDIT"',
            ("unchecked", "doctor_nowhere can't be imported: No module named 'doctor_nowhere'"),
        ),
        (
            "audit.named",
            'audit = "doctor_deployment:AUDIT"',
            ("passed", "the audit store is doctor_deployment:AUDIT, StandInAudit"),
        ),
    ],
    ids=[
        "keys: none named",
        "keys: FileKeys",
        "keys: not saying",
        "keys: unimportable",
        "keys: the deployment's",
        "audit: none named",
        "audit: FileAudit",
        "audit: not saying",
        "audit: unimportable",
        "audit: the deployment's",
    ],
)
def test_keys_and_audit_named(
    tmp_path: Path, rule: str, setting: str, expected: tuple[str, str]
) -> None:
    found = deployment(tmp_path, f"[tool.ventoux]\n{setting}\n")
    seen = verdict(found, rule)
    assert (seen.verdict, seen.said) == expected


def certificate(path: Path, expires: datetime) -> None:
    """A self-signed certificate at `path`, valid until `expires`: made here, never committed."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "operator")])
    made = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(expires - timedelta(days=365))
        .not_valid_after(expires)
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(made.public_bytes(serialization.Encoding.PEM))


def with_operator(folder: Path, expires: datetime, mode: int = 0o600) -> Configuration:
    """A deployment whose `operator` identity is a certificate valid until `expires`, and a key
    file with `mode`."""
    certificate(folder / "operator.pem", expires)
    key = folder / "operator.key"
    key.write_text(SECRET)
    key.chmod(mode)
    return deployment(
        folder,
        HEALTHY + IDENTITIES.format(cert=folder / "operator.pem", key=key),
    )


SECRET = "-----BEGIN PRIVATE KEY----- never-said -----END PRIVATE KEY-----"
IDENTITIES = """
[tool.ventoux.temporal]
address = "localhost:7233"
namespace = "default"

[tool.ventoux.temporal.identities.operator]
cert = "{cert}"
key = "{key}"
"""
IN_DATE = datetime(2099, 1, 1, tzinfo=UTC)


def test_temporal_identities(tmp_path: Path) -> None:
    rule = "temporal.identities"
    assert verdict(deployment(tmp_path), rule) == Finding(
        rule,
        "unchecked",
        "no identity is configured in [tool.ventoux.temporal]: commands connect without TLS",
    )
    seen = verdict(with_operator(tmp_path, IN_DATE), rule)
    assert seen == Finding(
        rule,
        "passed",
        "each identity's files are there (operator): each key readable by its owner only, each "
        "certificate in date",
    )
    seen = verdict(with_operator(tmp_path, IN_DATE, mode=0o640), rule)
    assert seen == Finding(
        rule,
        "FAILED",
        f"the identity operator's key, {tmp_path / 'operator.key'}, can be read by others (mode "
        "640): make it its owner's only, chmod 600",
    )
    seen = verdict(with_operator(tmp_path, datetime(2020, 1, 1, tzinfo=UTC)), rule)
    assert seen == Finding(
        rule,
        "FAILED",
        f"the identity operator's cert, {tmp_path / 'operator.pem'}, expired on 2020-01-01: "
        "renew it",
    )
    certificate(tmp_path / "operator.pem", IN_DATE)
    (tmp_path / "operator.key").unlink()
    found = deployment(
        tmp_path,
        HEALTHY + IDENTITIES.format(cert=tmp_path / "operator.pem", key=tmp_path / "operator.key"),
    )
    assert verdict(found, rule) == Finding(
        rule, "FAILED", f"the identity operator's key, {tmp_path / 'operator.key'}, isn't there"
    )
    assert SECRET not in "".join(finding.said for finding in findings(found))
