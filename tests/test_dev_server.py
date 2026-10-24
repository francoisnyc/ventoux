"""The tests' dev server, started by the harness with its own deadline (12e, fixed later).

The first start after a container is restored reads the server's 156 MB binary from a cold disk,
longer than the 5 s sdk-core waits (the tutor review of #50). The harness starts the binary itself
and waits 30 s; a start that misses it fails, showing the server's own output. Stand-ins (small
shell scripts) play a slow, a silent and a failing server. See docs/layers/12-releases.md, "12e,
fixed later: the dev server's cold start".
"""

import asyncio
import stat
import time
from pathlib import Path

import pytest
import temporalio.service
from dev_server import DevServerFailed, cli_binary, cli_folder, dev_server
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
from temporalio.testing import WorkflowEnvironment

# The SDK's name for its dev server's binary.
NAME = f"temporal-sdk-python-{temporalio.service.__version__}"


def stand_in(folder: Path, script: str) -> Path:
    """An executable shell script in `folder`, playing the dev server's binary."""
    path = folder / "temporal"
    path.write_text(f"#!/bin/sh\n{script}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_a_server_slower_than_5_s_starts_with_the_harness_and_not_without(tmp_path: Path) -> None:
    # The cause, reproduced: a server that takes 6 s to answer, as one read from a cold disk did.
    real = asyncio.run(cli_binary(cli_folder()))
    slow = stand_in(tmp_path, f'sleep 6\nexec "{real}" "$@"')

    async def without() -> None:
        await WorkflowEnvironment.start_local(dev_server_existing_path=str(slow))

    with pytest.raises(RuntimeError, match="did not start within 5s"):
        asyncio.run(without())

    async def with_it() -> str:
        async with dev_server(slow) as environment:
            service = environment.client.workflow_service
            found = await service.describe_namespace(DescribeNamespaceRequest(namespace="default"))
            return found.namespace_info.name

    assert asyncio.run(with_it()) == "default"


def started(binary: Path, deadline: float) -> str:
    """Why starting `binary` within `deadline` seconds failed; the test fails if it started."""

    async def go() -> None:
        async with dev_server(binary, deadline):
            pass

    with pytest.raises(DevServerFailed) as failure:
        asyncio.run(go())
    return str(failure.value)


def test_a_server_that_never_answers_fails_showing_its_output(tmp_path: Path) -> None:
    # A start that misses even the harness's deadline fails, never skips: with the command and
    # what the server printed, and the process stopped.
    pid = tmp_path / "pid"
    silent = stand_in(tmp_path, f"echo $$ > {pid}\necho 'warming up, slowly'\nexec sleep 60")
    began = time.monotonic()
    said = started(silent, deadline=2)
    assert time.monotonic() - began < 15
    first, second, printed = said.splitlines()
    assert first.startswith(f"the dev server didn't answer within 2 s: {silent} server start-dev")
    assert (second, printed) == ("it printed:", "warming up, slowly")
    assert not running(int(pid.read_text()))


def test_a_server_that_exits_first_fails_at_once_showing_its_output(tmp_path: Path) -> None:
    failing = stand_in(tmp_path, "echo 'port 7233 is in use' >&2\nexit 3")
    began = time.monotonic()
    said = started(failing, deadline=30)
    assert time.monotonic() - began < 5  # at once, never the whole deadline
    assert said.startswith(f"the dev server exited with 3 before it answered: {failing} ")
    assert said.endswith("\nit printed:\nport 7233 is in use")


def test_a_binary_the_sdk_names_otherwise_fails_naming_what_is_there(tmp_path: Path) -> None:
    # An SDK upgrade that renames its download is caught, never started some other way.
    async def renamed(folder: Path) -> None:
        (folder / "temporal-cli-2.0").write_text("")

    with pytest.raises(DevServerFailed) as failure:
        asyncio.run(cli_binary(tmp_path / "cli", download=renamed))
    assert str(failure.value) == (
        f"the SDK's dev server isn't at {tmp_path / 'cli' / NAME} after its download; "
        f"{tmp_path / 'cli'} holds: temporal-cli-2.0. The SDK names it otherwise now: update the "
        "name in tests/dev_server.py"
    )


def running(pid: int) -> bool:
    """Whether the process `pid` is still alive: the stand-in recorded its own, which `exec`
    keeps, so it names the server whatever it runs."""
    return Path(f"/proc/{pid}").exists()
