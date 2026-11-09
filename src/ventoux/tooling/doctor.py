"""`ventoux doctor ENVIRONMENT`: checks a deployment, with the rights it is given and no more
(layer 20b2) (brief, D81).

Each rule is named `area.rule` and gives one of three verdicts: `passed` (seen to hold), `FAILED`
(seen broken), `unchecked` (couldn't be seen either way, saying why). Every rule runs, whatever the
others give. Doctor changes nothing, and says no secret's value. See docs/guides/deployment.md,
"Checking the deployment".
"""

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from cryptography import x509

from ventoux.case.registry import keeping_problems
from ventoux.tooling.deployment import (
    DEVELOPMENT,
    Configuration,
    Unconfigured,
    catalog_named,
    configuration,
    named,
)
from ventoux.tooling.probes import Probes

Verdict = Literal["passed", "FAILED", "unchecked"]

ALL_PASSED = 0  # nothing failed (and, with --strict, nothing unchecked)
A_RULE_FAILED = 1
CANT_RUN = 2  # doctor couldn't run at all: no configuration it can read


@dataclass(frozen=True)
class Finding:
    """What one rule saw."""

    rule: str  # `area.rule`: `temporal.mtls-required`
    verdict: Verdict
    said: str  # what it saw, and on a failure what to do; never a secret's value


READER = "reader"  # the identity doctor signals as, to see a write refused (brief, D81)

# How long one probe may take before doctor says its rule unchecked: never a hang (#94).
PROBE_BOUND = 10.0  # seconds


@dataclass(frozen=True)
class Context:
    """What a rule reads: the configuration, the environment checked, and the world, asked."""

    found: Configuration
    environment: str  # `production`
    probes: Probes  # what doctor asks Temporal, the registry and the key service
    bound: float  # how long one probe may take, in seconds


class NoAnswer(Exception):
    """A probe that didn't answer within its bound."""


async def asked[T](context: Context, probe: Awaitable[T]) -> T:
    """What `probe` answers within the bound; `NoAnswer` otherwise. Every probe goes through
    here, so none can hang doctor (brief, D81)."""
    try:
        return await asyncio.wait_for(probe, context.bound)
    except TimeoutError:
        raise NoAnswer() from None


Seen = tuple[Verdict, str]  # a rule's verdict, and what it says


@dataclass(frozen=True)
class Rule:
    """One rule doctor checks, or one only the guide can state."""

    name: str  # `area.rule`
    check: Callable[[Context], Awaitable[Seen]] | None  # None: no client can see it
    section: str | None = None  # for a rule no client can see: the guide's section stating it
    why: str = ""  # for such a rule: why it can't be seen


async def catalog_is_named(context: Context) -> Seen:
    """The configuration names the deployment's catalog, not the development one (brief, D59)."""
    name = context.found.catalog
    if name is None:
        return "FAILED", (
            'no catalog is named: name the deployment\'s, [tool.ventoux] catalog = "module:NAME"'
        )
    if name == DEVELOPMENT:
        return "FAILED", f"the catalog is the development one, {DEVELOPMENT}: name the deployment's"
    try:
        catalog_named(name, context.found.root)
    except Unconfigured as refused:
        return "unchecked", str(refused)
    return "passed", f"the catalog is {name}, not the development one"


def provider_is_named(setting: str, what: str) -> Callable[[Context], Awaitable[Seen]]:
    """The rule that the configuration names the deployment's `what` (`key service`, `audit
    store`) under `setting`, and that it says it isn't for development (brief, D81)."""

    async def check(context: Context) -> Seen:
        name = getattr(context.found, setting)
        if name is None:
            return "FAILED", (
                f"no {what} is named: name the deployment's, [tool.ventoux] {setting} = "
                '"module:NAME"'
            )
        try:
            provider = named(
                name, context.found.root, f"the {what}", f"acme_platform:{setting.upper()}"
            )
        except Unconfigured as refused:
            return "unchecked", str(refused)
        kind = type(provider).__name__
        development = getattr(provider, "development", None)
        if development is True:
            return (
                "FAILED",
                f"{name} is {kind}, which is for development: name the deployment's {what}",
            )
        if development is not False:
            # Fail closed: one that doesn't say is never taken for a production one (brief, D81).
            return "FAILED", (
                f"{name} is {kind}, which doesn't say whether it is for development: give it "
                f"`development = False`, or name the deployment's {what}"
            )
        return "passed", f"the {what} is {name}, {kind}"

    return check


async def identities_are_sound(context: Context) -> Seen:
    """Each configured identity's files are there; its key is readable by its owner only; its
    certificate is in date. A key file is never read: only what it is (brief, D81)."""
    temporal = context.found.temporal
    if temporal is None or not temporal.identities:
        return "unchecked", (
            "no identity is configured in [tool.ventoux.temporal]: commands connect without TLS"
        )
    problems: list[str] = []
    for name, identity in sorted(temporal.identities.items()):
        problems += certificate_problems(
            f"the identity {name}'s cert, {identity.cert},", identity.cert
        )
        problems += key_problems(f"the identity {name}'s key, {identity.key},", identity.key)
    if problems:
        return "FAILED", "; ".join(problems)
    names = ", ".join(sorted(temporal.identities))
    return "passed", (
        f"each identity's files are there ({names}): each key readable by its owner only, each "
        "certificate in date"
    )


def key_problems(what: str, path: str) -> list[str]:
    """What is wrong with a key file: not there, or readable by others (its mode, never its
    contents)."""
    try:
        mode = Path(path).stat().st_mode & 0o777
    except OSError:
        return [f"{what} isn't there"]
    if mode & 0o077:  # any right for the group or others
        return [
            f"{what} can be read by others (mode {mode:o}): make it its owner's only, chmod 600"
        ]
    return []


def certificate_problems(what: str, path: str) -> list[str]:
    """What is wrong with a certificate: not there, not one, or out of date."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return [f"{what} isn't there"]
    try:
        certificate = x509.load_pem_x509_certificate(data)
    except ValueError:
        return [f"{what} isn't a PEM certificate"]
    expires = certificate.not_valid_after_utc
    if expires <= datetime.now(UTC):  # doctor reads the clock: it is tooling, never `core`
        return [f"{what} expired on {expires.date().isoformat()}: renew it"]
    return []


async def mtls_is_required(context: Context) -> Seen:
    """A connection without a client certificate is refused, with TLS and without (brief, D19)."""
    answered = await asked(context, context.probes.unauthenticated())
    if answered:
        return "FAILED", (
            "Temporal answered a connection without a client certificate, "
            f"{' and '.join(answered)}: require mTLS on the namespace's frontend"
        )
    return "passed", "a connection without a client certificate is refused, with TLS and without"


async def reader_cannot_write(context: Context) -> Seen:
    """As `reader`, a signal to a workflow that can't exist is refused: Temporal refuses an
    unauthorized call before it looks for the workflow, so nothing changes either way (brief,
    D19). Without `[tool.ventoux.temporal]`, as the commands connect: with no identity."""
    temporal = context.found.temporal
    if temporal is not None and READER not in temporal.identities:
        return "unchecked", (
            f"no {READER} identity is configured: name one in pyproject.toml, "
            f"[tool.ventoux.temporal.identities.{READER}]"
        )
    who = f"identity {READER}" if temporal is not None else "a connection with no identity"
    if await asked(context, context.probes.reader_signal()) == "refused":
        return "passed", f"{who} is refused a signal (PermissionDenied)"
    return "FAILED", (
        f"{who} sent a signal and Temporal let it through (the workflow doesn't exist, so nothing "
        "changed): give people read-only access (brief, D19)"
    )


async def environment_is_production(context: Context) -> Seen:
    """The environment's registry exists, and is production: doctor never hardens (brief, D81)."""
    here = context.environment
    registry = await asked(context, context.probes.registry())
    if registry is None:
        return "FAILED", (
            f"{here}'s registry doesn't exist: create it, ventoux environment create {here}"
        )
    if registry.development:
        return "FAILED", (
            f"{here} is a development environment, where drafts run: make it production, ventoux "
            f"environment harden {here} --by NAME"
        )
    return "passed", f"{here}'s registry exists and is production"


async def workers_can_run(context: Context) -> Seen:
    """`environment_check`, as `ventoux environment check` runs it: every release active or with
    open cases can run on its queue (brief, D54)."""
    problems = await asked(context, context.probes.environment_problems())
    if problems:
        return "FAILED", "; ".join(problems)
    return "passed", "every release active or with open cases can run (environment check)"


async def providers_are_production(context: Context) -> Seen:
    """Every case worker's manifest the registry holds says production providers: one accepted
    before the registry's rule (`ventoux-registry-keeping`) is seen here (brief, D81)."""
    here = context.environment
    registry = await asked(context, context.probes.registry())
    if registry is None:
        return "unchecked", f"{here}'s registry doesn't exist"
    if registry.development:
        return "unchecked", (
            f"{here} is a development environment: its workers may use development providers"
        )
    case_workers = sorted(m.identity for m in registry.manifests.values() if m.case is not None)
    # The registry's own rule, as it refuses a manifest: so the two can't disagree.
    problems = [
        problem
        for identity in case_workers
        for problem in keeping_problems(registry.manifests[identity])
    ]
    if problems:
        return "FAILED", "; ".join(problems)
    if not case_workers:
        return "passed", "no case worker has published a manifest"
    return "passed", (
        f"each case worker's manifest ({', '.join(case_workers)}) says production providers"
    )


RULES: tuple[Rule, ...] = (
    Rule("catalog.named", catalog_is_named),
    Rule("keys.named", provider_is_named("keys", "key service")),
    Rule("audit.named", provider_is_named("audit", "audit store")),
    Rule("temporal.identities", identities_are_sound),
    Rule("temporal.mtls-required", mtls_is_required),
    Rule("temporal.reader-cannot-write", reader_cannot_write),
    Rule("environment.exists-production", environment_is_production),
    Rule("environment.workers", workers_can_run),
    Rule("environment.production-providers", providers_are_production),
    Rule(
        "temporal.only-caller-writes",
        None,
        "The rule everything rests on: one caller writes",
        "the identities doctor holds are refused, but Temporal doesn't tell a client who else "
        "may write",
    ),
    Rule(
        "temporal.resets-restricted",
        None,
        "What only this guide can state",
        "who may reset or terminate is Temporal's authorizer's, which a client can't read",
    ),
    Rule(
        "temporal.retention",
        None,
        "Temporal",
        "how long closed histories are kept is the namespace's setting, yours to choose",
    ),
    Rule(
        "audit.no-deletes",
        None,
        "The audit store",
        "whether the audit store lets anyone delete a record is the store's setting",
    ),
    Rule(
        "keys.other-tokens",
        None,
        "What only this guide can state",
        "who else holds a token that can read ventoux-* keys is Vault's to say, not this token's",
    ),
)


async def diagnose(
    found: Configuration, environment: str, probes: Probes, bound: float = PROBE_BOUND
) -> list[Finding]:
    """Every rule's finding, in `RULES`' order: each runs whatever the others give."""
    context = Context(found, environment, probes, bound)
    findings: list[Finding] = []
    for rule in RULES:
        findings.append(await finding_of(rule, context))
    return findings


async def finding_of(rule: Rule, context: Context) -> Finding:
    """One rule's finding. A rule no client can see is unchecked, naming the guide's section."""
    if rule.check is None:
        return Finding(
            rule.name, "unchecked", f'{rule.why}: the deployment guide, "{rule.section}"'
        )
    try:
        verdict, said = await rule.check(context)
    except NoAnswer:
        return Finding(rule.name, "unchecked", f"no answer within {context.bound:g} s")
    except Exception as error:  # noqa: BLE001 (every kind: none may pass or vanish)
        # Fail closed, and say no secret: an error a rule doesn't expect is unchecked, by its kind
        # alone (its message may hold anything), never passed and never dropped (brief, D81).
        return Finding(
            rule.name, "unchecked", f"met {type(error).__name__}, which it doesn't expect"
        )
    return Finding(rule.name, verdict, said)


def said(findings: Sequence[Finding], environment: str) -> list[str]:
    """The lines doctor prints: one per finding, then the count of each verdict."""
    lines = [f"{finding.verdict:<10} {finding.rule}: {finding.said}" for finding in findings]
    counts = {verdict: 0 for verdict in ("passed", "FAILED", "unchecked")}
    for finding in findings:
        counts[finding.verdict] += 1
    lines.append(
        f"{environment}: {counts['passed']} passed, {counts['FAILED']} failed, "
        f"{counts['unchecked']} unchecked"
    )
    return lines


def outcome(findings: Sequence[Finding], strict: bool) -> int:
    """1 when a rule failed, or with `strict` when one is unchecked; else 0 (brief, D81)."""
    failing = {"FAILED", "unchecked"} if strict else {"FAILED"}
    return A_RULE_FAILED if any(f.verdict in failing for f in findings) else ALL_PASSED


def doctor_command(arguments: argparse.Namespace) -> int:
    """Check the deployment of `arguments.environment`, print each finding, and say how it ended."""
    try:
        found = configuration(Path.cwd())
    except Unconfigured as refused:
        print(refused, file=sys.stderr)
        return CANT_RUN
    findings = asyncio.run(diagnose(found, arguments.environment))
    for line in said(findings, arguments.environment):
        print(line)
    return outcome(findings, arguments.strict)
