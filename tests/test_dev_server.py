"""The tests' dev server, started by the harness with its own deadline (12e, fixed later).

The first start after a container is restored reads the server's 156 MB binary from a cold disk,
longer than the 5 s sdk-core waits (the tutor review of #50). The harness starts the binary itself
and waits 30 s; a start that misses it fails, showing the server's own output. Stand-ins (small
shell scripts) play a slow, a silent and a failing server. See docs/layers/12-releases.md, "12e,
fixed later: the dev server's cold start".
"""

import asyncio
import stat
import sys
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
    assert first.startswith(
        f"the dev server didn't answer within 2 s (nothing accepted a connection): {silent} "
        "server start-dev"
    )
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


def accepting_first(folder: Path, seconds: float, then: str) -> Path:
    """A stand-in that accepts TCP connections on the server's port for `seconds`, answering
    nothing, as the dev server does before its frontend is healthy; then runs `then`."""
    listener = (
        "import socket, sys, time\n"
        "s = socket.socket()\n"
        "s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        "s.bind(('127.0.0.1', int(sys.argv[1])))\n"
        "s.listen()\n"
        "s.settimeout(0.05)\n"
        "began = time.monotonic()\n"
        f"while time.monotonic() - began < {seconds}:\n"
        "    try:\n"
        "        s.accept()[0].close()\n"
        "    except TimeoutError:\n"
        "        pass\n"
        "s.close()\n"
    )
    (folder / "listener.py").write_text(listener)
    # `server start-dev --port N`: the port is the fourth argument. With nothing after it, the
    # listener takes the stand-in's place (`exec`), so stopping the stand-in stops it.
    listen = f'"{sys.executable}" "{folder / "listener.py"}" "$4"'
    return stand_in(folder, f"{listen}\n{then}" if then else f"exec {listen}")


def test_a_server_that_accepts_before_it_answers_is_waited_for(tmp_path: Path) -> None:
    # The race: the dev server accepts TCP before its frontend is healthy, and a client that
    # connects then is refused ("Frontend is not healthy yet"). Ready is a client answered.
    real = asyncio.run(cli_binary(cli_folder()))
    early = accepting_first(tmp_path, 3, f'exec "{real}" "$@"')

    async def go() -> str:
        async with dev_server(early) as environment:
            service = environment.client.workflow_service
            found = await service.describe_namespace(DescribeNamespaceRequest(namespace="default"))
            return found.namespace_info.name

    assert asyncio.run(go()) == "default"


def test_a_server_that_accepts_but_never_answers_fails_saying_why(tmp_path: Path) -> None:
    pid = tmp_path / "pid"
    deaf = accepting_first(tmp_path, 60, "")
    deaf.write_text(deaf.read_text().replace("#!/bin/sh\n", f"#!/bin/sh\necho $$ > {pid}\n", 1))
    said = started(deaf, deadline=3)
    first = said.splitlines()[0]
    assert first.startswith(
        "the dev server didn't answer within 3 s (it accepted connections, but answered no client: "
    )
    assert f": {deaf} server start-dev" in first
    assert not running(int(pid.read_text()))
