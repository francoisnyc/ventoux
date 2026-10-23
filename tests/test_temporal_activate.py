"""`ventoux activate`, `retire`, `environment` and `manifest` against Temporal's dev server
(layer 12e).

Only the dev server lists a queue's pollers (`DescribeTaskQueue`): the time-skipping test server
doesn't implement it (choice 77). The SDK downloads the dev server the first time, into
`TEMPORAL_CLI_DIR` if set (CI caches it there); a test that can't start it fails, never skips.
See docs/layers/12-releases.md (12e).
"""

import asyncio
import json
import os
import shutil
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

import pytest
from temporalio import workflow
from temporalio.client import Client
from temporalio.runtime import Runtime, TelemetryConfig
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from test_temporal_case import LARGE, reported
from test_temporal_registry import ProductionCases, refund_timed

from ventoux.case.memory import Activity
from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow, start_case
from ventoux.temporal.manifests import environment_worker
from ventoux.temporal.registry import create_environment, pollers, registry_worker
from ventoux.testing import CATALOG, FAKES, DevelopmentPlans, development_converter
from ventoux.tooling.cli import main
from ventoux.tooling.releases import FolderStore, release

PACKAGE = Path(__file__).parent.parent / "examples" / "packages" / "refund"
QUEUE = "refunds"


def on_dev_server[T](scenario: Callable[[Client, str], Awaitable[T]], create: bool = True) -> T:
    """Run `scenario` against Temporal's dev server, with the registries' worker running and
    production's registry created (unless not `create`); it is given the client and the server's
    address."""

    async def go() -> T:
        folder = os.environ.get("TEMPORAL_CLI_DIR")  # where CI keeps the dev server it caches
        if folder is not None:
            Path(folder).mkdir(parents=True, exist_ok=True)  # the SDK downloads into it, as is
        environment = await WorkflowEnvironment.start_local(
            data_converter=development_converter(), download_dest_dir=folder
        )
        async with environment, registry_worker(environment.client):
            if create:
                await create_environment(environment.client, "production")
            address = environment.client.service_client.config.target_host
            return await asyncio.wait_for(scenario(environment.client, address), timeout=60)

    return asyncio.run(go())


def released(folder: Path) -> Path:
    """The example package released as refund 1 in `folder`, as CI records it."""
    release(PACKAGE, FolderStore(folder), "4f2a9c1", CATALOG)
    return folder


async def ventoux(*argv: str) -> int:
    """The `ventoux` command, run as from a shell: in a thread, with its own event loop."""
    return await asyncio.to_thread(main, list(argv))


async def polling(client: Client, queue: str, *identities: str) -> None:
    """Wait until Temporal lists each of `identities` among `queue`'s pollers."""
    for _ in range(200):
        if set(identities) <= set((await pollers(client, [queue]))[queue]):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"{identities} never polled {queue}")


async def started(
    client: Client,
    identity: str,
    cases: type[CaseWorkflow] = ProductionCases,
    implementations: Mapping[str, Activity] | None = None,
    build: str = "4f2a9c1",
) -> Worker:
    """A production case worker on refunds, its manifest published."""
    return await environment_worker(
        client,
        QUEUE,
        cases,
        DevelopmentPlans,
        implementations or FAKES,
        build,
        identity,
    )


async def second_client(address: str) -> Client:
    """Another client, with a runtime of its own: Temporal's SDK runs one worker per queue in a
    runtime, so a second worker on refunds, as from a second machine, needs its own."""
    return await Client.connect(
        address,
        data_converter=development_converter(),
        runtime=Runtime(telemetry=TelemetryConfig()),
    )


# Temporal: a case workflow whose catalog serves another payments.refund@2.
@workflow.defn(name="ventoux.case")
class OtherBuildCases(ProductionCases):
    catalog = refund_timed(start_to_close=99)  # another timeout: another hash

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


def test_activate_refuses_a_release_no_worker_serves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The curriculum's: the only worker on refunds has no code for payments.refund@2.
    async def scenario(client: Client, address: str) -> int:
        without = {ref: code for ref, code in FAKES.items() if ref != "payments.refund@2"}
        async with await started(client, "refunds-a", implementations=without):
            await polling(client, QUEUE, "refunds-a")
            return await ventoux(
                "activate",
                "refund",
                "1",
                "--environment",
                "production",
                "--task-queue",
                QUEUE,
                "--releases",
                str(released(tmp_path)),
                "--by",
                "pia",
                "--address",
                address,
            )

    assert on_dev_server(scenario) == 1
    assert capsys.readouterr().out.splitlines() == [
        "refund 1 not activated in production:",
        "payments.refund@2: no worker on refunds serves it: deploy a build that does",
    ]


def test_activate_refuses_a_worker_serving_another_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The curriculum's: two workers poll refunds; one serves payments.refund@2 as its catalog
    # hashes it, differently from the record. Temporal would give it refunds all the same.
    async def scenario(client: Client, address: str) -> int:
        another = await second_client(address)
        async with (
            await started(client, "refunds-a"),
            await started(another, "refunds-b", OtherBuildCases, build="7b0e311"),
        ):
            await polling(client, QUEUE, "refunds-a", "refunds-b")
            return await ventoux(
                "activate",
                "refund",
                "1",
                "--environment",
                "production",
                "--task-queue",
                QUEUE,
                "--releases",
                str(released(tmp_path)),
                "--by",
                "pia",
                "--address",
                address,
            )

    assert on_dev_server(scenario) == 1
    assert capsys.readouterr().out.splitlines() == [
        "refund 1 not activated in production:",
        (
            "payments.refund@2: worker refunds-b (build 7b0e311) serves it with hash a3773f495606, "
            "and refund 1 needs b2f325e171c6: deploy the build that serves the released contract"
        ),
    ]


GUIDE = (Path(__file__).parent.parent / "docs" / "guides" / "releases.md").read_text()
ACTIVATING = GUIDE.split("## Activating a release in an environment\n")[1].split("\n## What")[0]


def shell_blocks(text: str) -> list[tuple[str, list[str]]]:
    """Each shell example in `text`: its command, without the `$ `, and the lines it prints."""
    blocks: list[tuple[str, list[str]]] = []
    for block in text.split("```\n$ ")[1:]:
        command, *printed = block.split("\n```")[0].splitlines()
        blocks.append((command, printed))
    return blocks


def test_the_guides_activation_example_runs_as_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The releases guide's commands, in order, against the dev server: production created; a
    # second worker from another build refused; the same worker deployed again from the release's
    # build, activated; the environment checked; refund 1 not retired while active. Our own
    # documentation, run as the guide says, with the server's address added.
    blocks = shell_blocks(ACTIVATING)
    assert [command.split()[1] for command, _ in blocks] == [
        "environment",
        "activate",
        "activate",
        "environment",
        "retire",
    ]
    store = released(tmp_path / "releases")

    async def run(command: str, address: str) -> list[str]:
        argv = command.replace("--releases releases", f"--releases {store}").split()[1:]
        capsys.readouterr()
        await ventoux(*argv, "--address", address)
        out = capsys.readouterr()
        return (out.out + out.err).splitlines()

    async def scenario(client: Client, address: str) -> list[list[str]]:
        seen = [await run(blocks[0][0], address)]
        another = await second_client(address)
        async with await started(client, "refunds-a"):
            async with await started(another, "refunds-b", OtherBuildCases, build="7b0e311"):
                await polling(client, QUEUE, "refunds-a", "refunds-b")
                seen.append(await run(blocks[1][0], address))
            async with await started(another, "refunds-b"):
                seen.append(await run(blocks[2][0], address))
                seen.append(await run(blocks[3][0], address))
                seen.append(await run(blocks[4][0], address))
        return seen

    assert on_dev_server(scenario, create=False) == [printed for _, printed in blocks]


def reworded_and_released(store: Path) -> None:
    """Refund 2: the example package with its plan's approval given 72 hours, as the guide's
    behaviour change, released after refund 1."""
    package = store.parent / "refund-2"
    shutil.copytree(PACKAGE, package)
    plan = package / "plans" / "refund-order.json"
    plan.write_text(plan.read_text().replace('"48h"', '"72h"'))
    release(package, FolderStore(store), "c90d4e2", CATALOG)


def test_the_environment_check_fails_when_a_contract_has_no_live_worker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Refund 2 is active and a case is still open on refund 1. A worker joins without code for
    # payments.refund@2: the check says so for both, each on its queue, and exits 1 (brief, D5,
    # as answered for choice 76: an open case's release is checked as an active one).
    store = released(tmp_path / "releases")
    reworded_and_released(store)

    async def scenario(client: Client, address: str) -> tuple[int, int]:
        another = await second_client(address)
        common = ["--environment", "production", "--releases", str(store), "--by", "pia"]
        async with await started(client, "refunds-a"):
            await polling(client, QUEUE, "refunds-a")
            assert (
                await ventoux(
                    "activate", "refund", "1", *common, "--task-queue", QUEUE, "--address", address
                )
                == 0
            )
            refund_1 = FolderStore(store).get("refund", 1)
            case = await start_case(client, ProductionCases, refund_1, LARGE, "refund-7", QUEUE)
            await reported(case, lambda now: now.waiting_at == ["review#1"])
            assert (
                await ventoux(
                    "activate", "refund", "2", *common, "--task-queue", QUEUE, "--address", address
                )
                == 0
            )
            capsys.readouterr()
            fine = await ventoux("environment", "check", "production", "--address", address)
            without = {ref: code for ref, code in FAKES.items() if ref != "payments.refund@2"}
            async with await started(
                another, "refunds-b", implementations=without, build="9e1f0aa"
            ):
                await polling(client, QUEUE, "refunds-a", "refunds-b")
                return fine, await ventoux(
                    "environment", "check", "production", "--address", address
                )

    fine, broken = on_dev_server(scenario)
    assert (fine, broken) == (0, 1)
    assert capsys.readouterr().out.splitlines() == [
        "production: every release that is active or has open cases can run",
        (
            "refund 1: payments.refund@2: worker refunds-b (build 9e1f0aa) doesn't serve it: deploy a "
            "build that does"
        ),
        (
            "refund 2: payments.refund@2: worker refunds-b (build 9e1f0aa) doesn't serve it: deploy a "
            "build that does"
        ),
    ]


def test_the_commands_say_what_they_did(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Exit 0 done, 1 refused, 2 unreadable, as `ventoux release`; each line what the registry or
    # the store said.
    store = released(tmp_path / "releases")
    manifest = tmp_path / "kyc-a.json"
    hashed = {"method": 1, "sha256": "cd" * 32}
    manifest.write_text(
        json.dumps(
            {
                "environment": "production",
                "task_queue": "kyc",
                "build": "k-12",
                "identity": "kyc-a",
                "serves": {"kyc.check@1": hashed},
                "workflows": ["KycCheck"],
            }
        )
    )
    broken = tmp_path / "broken.json"
    broken.write_text("{}")

    async def scenario(client: Client, address: str) -> list[tuple[int, list[str]]]:
        at = ["--address", address]
        common = ["--environment", "production", "--releases", str(store), "--by", "pia"]
        runs = [
            ["environment", "create", "production", *at],
            ["environment", "create", "staging", "--development", *at],
            ["environment", "harden", "staging", "--by", "pia", *at],
            ["environment", "harden", "staging", "--by", "pia", *at],
            ["manifest", "publish", str(manifest), *at],
            ["manifest", "publish", str(broken), *at],
            ["activate", "refund", "3", *common, "--task-queue", QUEUE, *at],
            ["activate", "refund", "1", *common, "--task-queue", QUEUE, "--environment", "qa", *at],
            ["retire", "refund", "1", *common, *at],
        ]
        seen: list[tuple[int, list[str]]] = []
        for argv in runs:
            capsys.readouterr()
            code = await ventoux(*argv)
            out = capsys.readouterr()
            seen.append((code, (out.out + out.err).splitlines()))
        return seen

    seen = on_dev_server(scenario)
    assert [code for code, _ in seen] == [1, 0, 0, 0, 0, 2, 1, 1, 1]
    assert [lines[0] for _, lines in seen if lines] == [
        "production exists already: its registry is running",
        "staging created: a development environment, where drafts open",
        "pia made staging a production environment: drafts no longer open",
        "staging is a production environment already",
        "kyc-a serves kyc in production",
        f"{broken} can't be read as a worker's manifest: 6 validation errors for Manifest",
        f"refund 3 isn't released: no record of it in {store / 'refund'}",
        "qa has no registry: create it with `ventoux environment create qa`",
        "refund 1 not retired: production never activated it",
    ]
