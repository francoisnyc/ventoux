"""`ventoux doctor`: checking a deployment, with the rights it is given and no more (layer 20b2)
(brief, D81). See docs/layers/20-deployment.md and docs/guides/deployment.md, "Checking the
deployment"."""

import asyncio
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from test_activation import FILE_AUDIT, FILE_KEYS, STORE, VAULT, keeping, production

from ventoux.case.activation import Provided
from ventoux.case.registry import Registry
from ventoux.tooling import doctor
from ventoux.tooling.cli import main
from ventoux.tooling.connecting import Unconnectable
from ventoux.tooling.deployment import Configuration, read
from ventoux.tooling.doctor import RULES, Finding, diagnose, outcome, said
from ventoux.tooling.vault import VaultKeys

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


FOREVER = object()  # a probe's answer that never comes

# What the deployment guide's policy gives the token, on each path doctor asks about.
MARK_DATA = "secret/data/ventoux/forgotten/ventoux-doctor-never-made"
MARK_METADATA = "secret/metadata/ventoux/forgotten/ventoux-doctor-never-made"
OUTSIDE = "transit/keys/doctor-outside"
ENCRYPT = "transit/encrypt/ventoux-doctor-never-made"
DECRYPT = "transit/decrypt/ventoux-doctor-never-made"
SOUND_POLICY = {
    MARK_DATA: ["create", "read", "update"],
    MARK_METADATA: ["read"],
    OUTSIDE: ["deny"],
    ENCRYPT: ["update"],
    DECRYPT: ["update"],
}


@dataclass
class Answering:
    """Doctor's probes, stood in for: each answers as given, raises what it is given, or never
    answers (`FOREVER`). Healthy unless told otherwise."""

    unauthenticated_answers: object = field(default_factory=list[str])  # both refused
    reader: object = "refused"
    registry_held: object = field(default_factory=lambda: production(keeping(VAULT, STORE)))
    problems: object = field(default_factory=list[str])  # environment_check's
    state: object = "never made"  # the key service's state of a key that can't exist
    policy: object = field(default_factory=lambda: dict(SOUND_POLICY))  # capabilities, by path

    async def answer(self, given: object) -> Any:
        if given is FOREVER:
            await asyncio.Event().wait()  # nothing ever sets it
        if isinstance(given, Exception):
            raise given
        return given

    async def unauthenticated(self) -> list[str]:
        return cast(list[str], await self.answer(self.unauthenticated_answers))

    async def reader_signal(self) -> str:
        return cast(str, await self.answer(self.reader))

    async def registry(self) -> Registry | None:
        return cast(Registry | None, await self.answer(self.registry_held))

    async def environment_problems(self) -> list[str]:
        return cast(list[str], await self.answer(self.problems))

    async def key_state(self, keys: VaultKeys) -> str:
        return cast(str, await self.answer(self.state))

    async def capabilities(self, keys: VaultKeys, paths: list[str]) -> dict[str, list[str]]:
        held = cast(dict[str, list[str]], await self.answer(self.policy))
        assert sorted(held) == sorted(paths)  # asked of exactly these paths
        return held


def findings(
    found: Configuration, probes: Answering | None = None, bound: float = 5
) -> list[Finding]:
    return asyncio.run(diagnose(found, "production", probes or Answering(), bound))


def verdict(found: Configuration, rule: str, probes: Answering | None = None) -> Finding:
    return next(finding for finding in findings(found, probes) if finding.rule == rule)


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VAULT_TOKEN", SECRET)
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


def test_a_module_raising_as_it_is_imported_is_said_by_its_kind_never_its_message(
    tmp_path: Path,
) -> None:
    found = deployment(tmp_path, '[tool.ventoux]\ncatalog = "doctor_broken:CATALOG"\n')
    assert verdict(found, "catalog.named") == Finding(
        "catalog.named", "unchecked", "doctor_broken can't be imported: it raised RuntimeError"
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


# The rules that ask the world, each with the stand-in's field its probe answers from.
PROBING = {
    "temporal.mtls-required": "unauthenticated_answers",
    "temporal.reader-cannot-write": "reader",
    "environment.exists-production": "registry_held",
    "environment.workers": "problems",
    "environment.production-providers": "registry_held",
    "keys.reachable": "state",
    "keys.policy": "policy",
}


@pytest.mark.parametrize("rule", sorted(PROBING))
def test_a_probe_raising_what_its_rule_doesnt_expect_is_unchecked(
    tmp_path: Path, rule: str
) -> None:
    probes = Answering(**{PROBING[rule]: RuntimeError(SECRET)})
    assert verdict(deployment(tmp_path), rule, probes) == Finding(
        rule, "unchecked", "met RuntimeError, which it doesn't expect"
    )


def test_a_probe_that_never_answers_is_unchecked_naming_the_bound(tmp_path: Path) -> None:
    # Every probe bounded: one that never answers is unchecked, never a hang (#94).
    never = Answering(**{field: FOREVER for field in PROBING.values()})
    started = time.monotonic()
    seen = asyncio.run(
        asyncio.wait_for(diagnose(deployment(tmp_path), "production", never, 0.2), timeout=10)
    )
    assert time.monotonic() - started < 0.2 * len(PROBING) + 2
    for rule in PROBING:
        assert Finding(rule, "unchecked", "no answer within 0.2 s") in seen


def test_temporal_mtls_required(tmp_path: Path) -> None:
    rule, found = "temporal.mtls-required", deployment(tmp_path)
    assert verdict(found, rule) == Finding(
        rule, "passed", "a connection without a client certificate is refused, with TLS and without"
    )
    answered = Answering(unauthenticated_answers=["without TLS"])
    assert verdict(found, rule, answered) == Finding(
        rule,
        "FAILED",
        "Temporal answered a connection without a client certificate, without TLS: require "
        "mTLS on the namespace's frontend",
    )


def test_temporal_reader_cannot_write(tmp_path: Path) -> None:
    rule, found = "temporal.reader-cannot-write", deployment(tmp_path)
    # Without [tool.ventoux.temporal], doctor connects as the commands do: with no identity.
    assert verdict(found, rule) == Finding(
        rule, "passed", "a connection with no identity is refused a signal (PermissionDenied)"
    )
    assert verdict(found, rule, Answering(reader="allowed")) == Finding(
        rule,
        "FAILED",
        "a connection with no identity sent a signal and Temporal let it through (the workflow "
        "doesn't exist, so nothing changed): give people read-only access (brief, D19)",
    )
    operator_only = with_operator(tmp_path, IN_DATE)
    assert verdict(operator_only, rule) == Finding(
        rule,
        "unchecked",
        "no reader identity is configured: name one in pyproject.toml, "
        "[tool.ventoux.temporal.identities.reader]",
    )
    with_reader = deployment(
        tmp_path,
        (tmp_path / "pyproject.toml").read_text()
        + '[tool.ventoux.temporal.identities.reader]\ncert = "r.pem"\nkey = "r.key"\n',
    )
    assert verdict(with_reader, rule) == Finding(
        rule, "passed", "identity reader is refused a signal (PermissionDenied)"
    )


def test_environment_exists_production(tmp_path: Path) -> None:
    rule, found = "environment.exists-production", deployment(tmp_path)
    assert verdict(found, rule) == Finding(
        rule, "passed", "production's registry exists and is production"
    )
    assert verdict(found, rule, Answering(registry_held=None)) == Finding(
        rule,
        "FAILED",
        "production's registry doesn't exist: create it, ventoux environment create production",
    )
    development = Answering(registry_held=Registry("production", development=True))
    assert verdict(found, rule, development) == Finding(
        rule,
        "FAILED",
        "production is a development environment, where drafts run: make it production, ventoux "
        "environment harden production --by NAME",
    )


def test_environment_workers(tmp_path: Path) -> None:
    rule, found = "environment.workers", deployment(tmp_path)
    assert verdict(found, rule) == Finding(
        rule, "passed", "every release active or with open cases can run (environment check)"
    )
    problems = ["refund 2: no worker polls refunds", "claim 1: payments.refund@2 isn't served"]
    assert verdict(found, rule, Answering(problems=problems)) == Finding(
        rule, "FAILED", "refund 2: no worker polls refunds; claim 1: payments.refund@2 isn't served"
    )


@pytest.mark.parametrize(
    ("keys", "audit", "said"),
    [
        (
            FILE_KEYS,
            STORE,
            (
                "refunds-a keeps its keys with FileKeys, which is for development: production keeps "
                "them in the deployment's key service; deploy the worker with it"
            ),
        ),
        (
            VAULT,
            FILE_AUDIT,
            (
                "refunds-a writes its audit records to FileAudit, which is for development: production "
                "writes them to the deployment's audit store; deploy the worker with it"
            ),
        ),
        (
            None,
            None,
            (
                "refunds-a doesn't say what keeps its keys: a case worker in production must; deploy a "
                "build that does; refunds-a doesn't say where it writes its audit records: a case "
                "worker in production must; deploy a build that does"
            ),
        ),
    ],
    ids=["FileKeys", "FileAudit", "saying neither (accepted before the patch)"],
)
def test_environment_production_providers_fails_a_worker_the_registry_holds(
    tmp_path: Path, keys: Provided | None, audit: Provided | None, said: str
) -> None:
    # Held by a registry that accepted it before ventoux-registry-keeping (brief, D81).
    held = Registry("production", manifests={"refunds-a": keeping(keys, audit)})
    rule = "environment.production-providers"
    assert verdict(deployment(tmp_path), rule, Answering(registry_held=held)) == Finding(
        rule, "FAILED", said
    )


def test_environment_production_providers(tmp_path: Path) -> None:
    rule, found = "environment.production-providers", deployment(tmp_path)
    assert verdict(found, rule) == Finding(
        rule, "passed", "each case worker's manifest (refunds-a) says production providers"
    )
    development = Answering(registry_held=Registry("production", development=True))
    assert verdict(found, rule, development) == Finding(
        rule,
        "unchecked",
        "production is a development environment: its workers may use development providers",
    )
    assert verdict(found, rule, Answering(registry_held=None)) == Finding(
        rule, "unchecked", "production's registry doesn't exist"
    )


def test_keys_token_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rule, found = "keys.token-present", deployment(tmp_path)
    monkeypatch.setenv("VAULT_TOKEN", SECRET)
    assert verdict(found, rule) == Finding(rule, "passed", "VAULT_TOKEN is set")
    monkeypatch.delenv("VAULT_TOKEN")
    assert verdict(found, rule) == Finding(
        rule,
        "FAILED",
        "VAULT_TOKEN is not set: set it in the environment of each worker, the caller and the "
        "shell doctor runs in",
    )
    file_keys = deployment(tmp_path, '[tool.ventoux]\nkeys = "doctor_deployment:FILE_KEYS"\n')
    assert verdict(file_keys, rule) == Finding(
        rule, "unchecked", "the key service named isn't VaultKeys: keys.named says what it is"
    )


def test_keys_reachable(tmp_path: Path) -> None:
    rule, found = "keys.reachable", deployment(tmp_path)
    assert verdict(found, rule) == Finding(
        rule,
        "passed",
        "the key service at https://vault.internal:8200 answers: a key that can't exist was "
        "never made",
    )
    assert verdict(found, rule, Answering(state="kept")) == Finding(
        rule,
        "FAILED",
        "the key service at https://vault.internal:8200 says a key that can't exist is kept: "
        "check it is the deployment's Vault, its transit mount transit",
    )
    file_keys = deployment(tmp_path, '[tool.ventoux]\nkeys = "doctor_deployment:FILE_KEYS"\n')
    assert verdict(file_keys, rule).verdict == "unchecked"


@pytest.mark.parametrize(
    ("path", "given", "said"),
    [
        (
            MARK_METADATA,
            ["read", "delete"],
            f"the token can delete a mark ({MARK_METADATA}): never allow delete on the marks",
        ),
        (
            MARK_DATA,
            ["root"],
            f"the token can delete a mark ({MARK_DATA}): never allow delete on the marks",
        ),
        (
            OUTSIDE,
            ["read"],
            f"the token isn't denied a key not named ventoux-* ({OUTSIDE}): deny it",
        ),
        (
            ENCRYPT,
            ["read"],
            f"the token can't use a ventoux-* key ({ENCRYPT}): allow update on it",
        ),
    ],
    ids=["delete on a mark's metadata", "root on a mark", "outside not denied", "no encrypt"],
)
def test_keys_policy_fails(tmp_path: Path, path: str, given: list[str], said: str) -> None:
    policy = {**SOUND_POLICY, path: given}
    rule = "keys.policy"
    assert verdict(deployment(tmp_path), rule, Answering(policy=policy)) == Finding(
        rule, "FAILED", said
    )


def test_keys_policy(tmp_path: Path) -> None:
    rule, found = "keys.policy", deployment(tmp_path)
    assert verdict(found, rule) == Finding(
        rule,
        "passed",
        "the token can't delete a mark, is denied a key not named ventoux-*, and can encrypt "
        "and decrypt with ventoux-* keys",
    )
    file_keys = deployment(tmp_path, '[tool.ventoux]\nkeys = "doctor_deployment:FILE_KEYS"\n')
    assert verdict(file_keys, rule).verdict == "unchecked"


def test_advisor_key_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rule = "advisor.key-present"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert verdict(deployment(tmp_path), rule) == Finding(
        rule, "passed", "no model is configured: no key is needed"
    )
    advising = deployment(tmp_path, HEALTHY + 'model = "the-model"\n')
    assert verdict(advising, rule) == Finding(
        rule,
        "FAILED",
        "a model is configured, and ANTHROPIC_API_KEY is not set: set it where ventoux advise "
        "and the step advisor run",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    assert verdict(advising, rule) == Finding(
        rule, "passed", "ANTHROPIC_API_KEY is set, for the model configured"
    )


GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "deployment.md"


def test_a_rule_no_client_can_see_is_unchecked_naming_a_section_the_guide_has(
    tmp_path: Path,
) -> None:
    sections = {line[3:] for line in GUIDE.read_text().splitlines() if line.startswith("## ")}
    seen = {finding.rule: finding for finding in findings(deployment(tmp_path))}
    unseen = [rule for rule in RULES if rule.check is None]
    assert {rule.name for rule in unseen} == {
        "temporal.only-caller-writes",
        "temporal.resets-restricted",
        "temporal.retention",
        "audit.no-deletes",
        "keys.other-tokens",
    }
    for rule in unseen:
        assert rule.section in sections, f"{rule.name} names no section of the guide"
        assert seen[rule.name].verdict == "unchecked"
        assert seen[rule.name].said.endswith(f'the deployment guide, "{rule.section}"')


def test_an_identity_that_cant_connect_is_unchecked_saying_which_file(tmp_path: Path) -> None:
    said = "the identity reader's key, /etc/r.key, can't be read (FileNotFoundError): nothing was connected"
    rule = "temporal.reader-cannot-write"
    assert verdict(deployment(tmp_path), rule, Answering(reader=Unconnectable(said))) == Finding(
        rule, "unchecked", said
    )


def test_no_secret_is_said_a_failure_included(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token, api_key = "hvs.never-said-token", "sk-ant-never-said-key"
    monkeypatch.setenv("VAULT_TOKEN", token)
    monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)
    with_operator(tmp_path, datetime(2020, 1, 1, tzinfo=UTC), mode=0o644)  # key file: SECRET
    found = deployment(
        tmp_path,
        '[tool.ventoux]\ncatalog = "doctor_broken:CATALOG"\nkeys = "doctor_deployment:KEYS"\n'
        'model = "m"\n'
        + IDENTITIES.format(cert=tmp_path / "operator.pem", key=tmp_path / "operator.key"),
    )
    leaking = RuntimeError(f"{token} {api_key} {SECRET}")  # what an error's message may hold
    probes = Answering(**{field: leaking for field in PROBING.values()})
    text = "\n".join(said(findings(found, probes), "production"))
    assert "FAILED" in text and "unchecked" in text  # through failing branches
    for secret in (token, api_key, SECRET, "never-said"):
        assert secret not in text


def guide_rules() -> list[str]:
    """The rules the deployment guide's table lists, in its order: the first cell of each row,
    under "Checking the deployment"."""
    section = GUIDE.read_text().split("## Checking the deployment", 1)[1].split("\n## ", 1)[0]
    return [
        line.split("|")[1].strip().strip("`")
        for line in section.splitlines()
        if line.startswith("| `")
    ]


def test_the_guide_lists_every_rule_doctor_checks_and_no_other() -> None:
    assert guide_rules() == [rule.name for rule in RULES]


def test_the_guides_example_output_names_only_rules_doctor_has() -> None:
    section = GUIDE.read_text().split("## Checking the deployment", 1)[1].split("\n## ", 1)[0]
    names = {rule.name for rule in RULES}
    for line in section.splitlines():
        words = line.split()
        if words and words[0] in ("passed", "FAILED", "unchecked") and len(words) > 1:
            assert words[1].rstrip(":") in names, line


def test_the_guides_failed_example_is_what_doctor_says(tmp_path: Path) -> None:
    section = GUIDE.read_text().split("## Checking the deployment", 1)[1]
    example = section.split("FAILED     temporal.reader-cannot-write: ", 1)[1].split("```")[0]
    reader = deployment(
        tmp_path,
        HEALTHY
        + IDENTITIES.format(cert="o.pem", key="o.key")
        + '[tool.ventoux.temporal.identities.reader]\ncert = "r.pem"\nkey = "r.key"\n',
    )
    seen = verdict(reader, "temporal.reader-cannot-write", Answering(reader="allowed"))
    assert " ".join(example.split()) == seen.said


def test_the_command_says_each_finding_and_exits_as_its_verdicts_say(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deployment(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VAULT_TOKEN", SECRET)
    monkeypatch.setattr(doctor, "LiveProbes", lambda found, environment: Answering())
    assert main(["doctor", "production"]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert (
        len(printed) == len(RULES) + 1
        and printed[-1] == "production: 12 passed, 0 failed, 6 unchecked"
    )
    assert main(["doctor", "production", "--strict"]) == 1  # 6 unchecked
    monkeypatch.delenv("VAULT_TOKEN")
    assert main(["doctor", "production"]) == 1  # keys.token-present failed


# A deployment configured as the guide says: one platform module, its VaultKeys built as the guide
# builds it (no transport given).
PLATFORM = """
[tool.ventoux]
catalog = "doctor_platform:CATALOG"
keys = "doctor_platform:KEYS"
audit = "doctor_platform:AUDIT"
"""


def test_without_vault_token_the_guides_key_service_fails_token_present_and_doctor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.delitem(sys.modules, "doctor_platform", raising=False)  # imported afresh
    seen = findings(deployment(tmp_path, PLATFORM))
    by_rule = {finding.rule: finding for finding in seen}
    # The key service can't be loaded, so doctor can't know it is Vault: it says the token is
    # needed if it is (the tutor's review of #96, optional; carried into 20c).
    assert by_rule["keys.token-present"] == Finding(
        "keys.token-present",
        "FAILED",
        "VAULT_TOKEN is not set, and the key service can't be loaded (keys.named says why): if it "
        "is VaultKeys, set VAULT_TOKEN in the environment of each worker, the caller and the "
        "shell doctor runs in",
    )
    # The module raised as it was imported: said by its name and the error's kind.
    for rule in ("catalog.named", "keys.named", "audit.named"):
        assert by_rule[rule] == Finding(
            rule, "unchecked", "doctor_platform can't be imported: it raised ValueError"
        )
    for rule in ("keys.reachable", "keys.policy"):
        assert by_rule[rule] == Finding(
            rule, "unchecked", "the key service can't be loaded: keys.named says why"
        )
    assert outcome(seen, strict=False) == 1


def test_with_vault_token_the_guides_key_service_is_named_and_its_token_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VAULT_TOKEN", SECRET)
    monkeypatch.delitem(sys.modules, "doctor_platform", raising=False)
    found = deployment(tmp_path, PLATFORM)
    assert verdict(found, "keys.named") == Finding(
        "keys.named", "passed", "the key service is doctor_platform:KEYS, VaultKeys"
    )
    assert verdict(found, "keys.token-present").verdict == "passed"
