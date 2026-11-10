"""`ventoux doctor` against a development server, through `LiveProbes` (layer 20b2) (brief, D81):
the curriculum's test, and doctor changing nothing. The server has no mTLS and no authorizer, so
the Temporal rules fail here; their passed branches are reached only with a stand-in
(`test_doctor.py`)."""

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client, WorkflowHandle
from temporalio.service import RPCError, RPCStatusCode
from test_doctor import IN_DATE, PLATFORM, SECRET, certificate
from test_temporal_registry import in_production

from ventoux.temporal.registry import registry_handle
from ventoux.tooling.deployment import Configuration, read
from ventoux.tooling.doctor import Finding, diagnose
from ventoux.tooling.probes import NEVER_STARTED, LiveProbes


def test_doctor_fails_a_development_server_naming_each_rule_it_breaks(tmp_path: Path) -> None:
    # Curriculum: a deployment that breaks a rule doctor checks fails, naming the rule.
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.ventoux]\ncatalog = "doctor_deployment:CATALOG"\n')
    found = read(path)

    async def scenario(client: Client) -> list[Finding]:
        probes = LiveProbes(
            found, "production", client.service_client.config.target_host, client.namespace
        )
        return await diagnose(found, "production", probes)

    seen = {finding.rule: finding for finding in in_production(scenario)}
    assert seen["temporal.mtls-required"] == Finding(
        "temporal.mtls-required",
        "FAILED",
        "Temporal answered a connection without a client certificate, without TLS: require mTLS "
        "on the namespace's frontend",
    )
    assert seen["temporal.reader-cannot-write"] == Finding(
        "temporal.reader-cannot-write",
        "FAILED",
        "a connection with no identity sent a signal and Temporal let it through (the workflow "
        "doesn't exist, so nothing changed): give people read-only access (brief, D19)",
    )
    # What the server does give, read through the same probes.
    assert seen["environment.exists-production"].verdict == "passed"
    assert seen["environment.workers"].verdict == "passed"
    assert seen["environment.production-providers"] == Finding(
        "environment.production-providers", "passed", "no case worker has published a manifest"
    )


async def settled(registry: WorkflowHandle[Any, Any]) -> int:
    """How many events the registry's history holds once its first workflow task has completed:
    a registry just created is still starting, which is no change of doctor's. Bounded by the
    scenario's own wait."""
    while True:
        events = (await registry.fetch_history()).events
        if events[-1].event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_COMPLETED:
            return len(events)
        await asyncio.sleep(0.05)


def test_doctor_changes_nothing(tmp_path: Path) -> None:
    # Every probe does no harm if allowed: a signal to a workflow that can't exist, the
    # registry's query (never an update), connections opened and closed (brief, D81).
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.ventoux]\ncatalog = "doctor_deployment:CATALOG"\n')
    found = read(path)

    async def scenario(client: Client) -> tuple[int, int, RPCStatusCode | None]:
        registry = registry_handle(client, "production")
        before = await settled(registry)
        probes = LiveProbes(
            found, "production", client.service_client.config.target_host, client.namespace
        )
        await diagnose(found, "production", probes)
        after = len((await registry.fetch_history()).events)
        try:
            await client.get_workflow_handle(NEVER_STARTED).describe()
        except RPCError as error:
            return before, after, error.status
        return before, after, None

    before, after, started = in_production(scenario)
    assert after == before  # nothing written to the registry
    assert started == RPCStatusCode.NOT_FOUND  # no workflow started by the signal


def production_configured(folder: Path, address: str, namespace: str) -> Configuration:
    """The configuration a production deployment has: `[tool.ventoux.temporal]` with `reader` and
    `operator` identities whose files are there, and the key service built as the guide builds
    it. Here the address is a development server's, which has no TLS."""
    identities = ""
    for name in ("reader", "operator"):
        certificate(folder / f"{name}.pem", IN_DATE)
        key = folder / f"{name}.key"
        key.write_text(SECRET)
        key.chmod(0o600)
        identities += (
            f"\n[tool.ventoux.temporal.identities.{name}]\n"
            f'cert = "{folder / name}.pem"\nkey = "{key}"\n'
        )
    path = folder / "pyproject.toml"
    path.write_text(
        PLATFORM
        + f'\n[tool.ventoux.temporal]\naddress = "{address}"\nnamespace = "{namespace}"\n'
        + identities
    )
    return read(path)


def test_doctor_with_a_production_configuration_runs_every_rule_through_live_probes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The production path, never only through stand-ins: a section, identities, and the guide's
    # key service. On a development server the connection without TLS is answered: FAILED.
    monkeypatch.setenv("VAULT_TOKEN", "hvs.never-said-token")
    monkeypatch.delitem(sys.modules, "doctor_platform", raising=False)

    async def scenario(client: Client) -> list[Finding]:
        target = client.service_client.config.target_host
        found = production_configured(tmp_path, target, client.namespace)
        return await diagnose(found, "production", LiveProbes(found, "production"), 3)

    seen = {finding.rule: finding for finding in in_production(scenario)}
    assert seen["temporal.mtls-required"] == Finding(
        "temporal.mtls-required",
        "FAILED",
        "Temporal answered a connection without a client certificate, without TLS: require mTLS "
        "on the namespace's frontend",
    )
    assert seen["temporal.identities"].verdict == "passed"
    assert seen["keys.named"].verdict == "passed"
    assert seen["keys.token-present"].verdict == "passed"
    said = "\n".join(finding.said for finding in seen.values())
    assert "identities.None" not in said
    assert "never-said" not in said
