"""The tests' dev server, started by the harness with its own deadline (12e, fixed later).

`WorkflowEnvironment.start_local` waits 5 s for the server, a limit sdk-core fixes. The first start
after a container is restored reads the server's 156 MB binary from a cold disk, which can take
longer (the tutor review of #50). So the harness starts the binary itself, with the flags the SDK
gives it, and waits 30 s for it to answer: a start that misses even that fails, showing the
server's own output, never skipped and never retried. See docs/layers/12-releases.md, "12e, fixed
later: the dev server's cold start". Ready is a client answered, never a port that accepts: the
server accepts TCP before its frontend is healthy (docs/layers/fix-dev-server-ready.md).
"""

import asyncio
import os
import socket
import tempfile
import time
from asyncio.subprocess import Process
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import temporalio.service
from temporalio.client import Client
from temporalio.converter import DataConverter
from temporalio.testing import WorkflowEnvironment

# How long a start may take: five times the cold read the review measured (6 s).
DEADLINE = 30.0


class DevServerFailed(RuntimeError):
    """The dev server didn't start: a test that needs it fails, never skips (12e, choice 77)."""


def cli_folder() -> Path:
    """Where the dev server's binary is kept: `TEMPORAL_CLI_DIR` when set (CI caches it there),
    else the temporary folder, where the SDK downloads it by default."""
    return Path(os.environ.get("TEMPORAL_CLI_DIR") or tempfile.gettempdir())


async def sdk_download(folder: Path) -> None:
    """Have the SDK download its dev server into `folder`, the only way it can: by starting it
    once. A file just written is warm, so this start reads no cold disk."""
    environment = await WorkflowEnvironment.start_local(download_dest_dir=str(folder))
    await environment.shutdown()


async def cli_binary(
    folder: Path, download: Callable[[Path], Awaitable[None]] = sdk_download
) -> Path:
    """The dev server's binary in `folder`, downloaded first if it isn't there. Its name is the
    SDK's (sdk-core names it after the SDK and its version, and documents it nowhere), so a name
    the SDK changes fails here, naming what the folder holds, never starts something else."""
    binary = folder / f"temporal-sdk-python-{temporalio.service.__version__}"
    if not binary.is_file():
        folder.mkdir(parents=True, exist_ok=True)  # the SDK downloads into it, as is
        await download(folder)
    if not binary.is_file():
        held = ", ".join(sorted(path.name for path in folder.iterdir())) or "nothing"
        raise DevServerFailed(
            f"the SDK's dev server isn't at {binary} after its download; {folder} holds: {held}. "
            "The SDK names it otherwise now: update the name in tests/dev_server.py"
        )
    return binary


def flags(port: int) -> list[str]:
    """`server start-dev` as the SDK runs it (read from its running process, temporalio 1.34.0)."""
    configs = (
        "frontend.enableServerVersionCheck=false",
        "frontend.enableUpdateWorkflowExecution=true",
        "frontend.enableUpdateWorkflowExecutionAsyncAccepted=true",
    )
    found = ["server", "start-dev", "--port", str(port), "--namespace", "default"]
    found += ["--ip", "127.0.0.1", "--log-format", "pretty", "--log-level", "warn"]
    for config in configs:
        found += ["--dynamic-config-value", config]
    return [*found, "--headless"]


def free_port() -> int:
    """A port nothing listens on now, as the SDK picks one."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@asynccontextmanager
async def dev_server(
    binary: Path,
    deadline: float = DEADLINE,
    data_converter: DataConverter = DataConverter.default,
) -> AsyncIterator[WorkflowEnvironment]:
    """The dev server `binary` runs, as a workflow environment, stopped on the way out. Its output
    goes to a file, shown if it doesn't start within `deadline` seconds or exits first."""
    port = free_port()
    command = [str(binary), *flags(port)]
    with tempfile.TemporaryDirectory() as logs:
        log = Path(logs) / "server.log"
        with log.open("wb") as output:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=output, stderr=asyncio.subprocess.STDOUT
            )
        try:
            client = await answering(process, port, deadline, command, log, data_converter)
            yield WorkflowEnvironment.from_client(client)
        finally:
            await stop(process)


async def answering(
    process: Process,
    port: int,
    deadline: float,
    command: list[str],
    log: Path,
    data_converter: DataConverter,
) -> Client:
    """A client the server on `port` has answered; fail if it exits first or `deadline` passes.
    Ready is a client answered, never a port that accepts: the dev server accepts TCP before its
    frontend is healthy, and a client that connects then is refused ("Frontend is not healthy
    yet"), as `tests/skipping_server.py` waits for its server (fix-dev-server-ready)."""
    began = time.monotonic()
    why = "nothing accepted a connection"
    while time.monotonic() - began < deadline:
        if (code := process.returncode) is not None:
            raise DevServerFailed(said(f"exited with {code} before it answered", command, log))
        if not await accepts(port):
            why = "nothing accepted a connection"
            await asyncio.sleep(0.05)  # not listening yet
            continue
        try:
            # Temporal: connecting asks the server for its system info, so a client returned
            # is one the frontend answered. Within 2 s, so a deaf listener can't hold the wait.
            return await asyncio.wait_for(
                Client.connect(f"127.0.0.1:{port}", data_converter=data_converter), timeout=2
            )
        except (OSError, RuntimeError, TimeoutError) as error:
            why = f"it accepted connections, but answered no client: {first_line(error)}"
            await asyncio.sleep(0.05)  # listening, not healthy yet
    raise DevServerFailed(said(f"didn't answer within {deadline:g} s ({why})", command, log))


async def accepts(port: int) -> bool:
    """Whether something accepts a TCP connection on `port` now."""
    try:
        _, writer = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        return False
    writer.close()
    await writer.wait_closed()
    return True


def first_line(error: BaseException) -> str:
    """What `error` says, on one line: its kind when it says nothing."""
    lines = str(error).splitlines()
    return lines[0] if lines else type(error).__name__


def said(what: str, command: list[str], log: Path, server: str = "the dev server") -> str:
    """Why `server` didn't start, with the command and everything it printed."""
    printed = log.read_text(errors="replace").strip() or "(nothing)"
    return f"{server} {what}: {' '.join(command)}\nit printed:\n{printed}"


async def stop(process: Process) -> None:
    """Stop the server: asked first, then killed; never left running."""
    if process.returncode is not None:
        return  # it has exited already
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except TimeoutError:
        process.kill()
        await process.wait()
