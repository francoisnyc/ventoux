"""The tests' time-skipping test server, started by the harness (fix-flaky-temporal, "The port
race").

`WorkflowEnvironment.start_time_skipping` picks a free port, then starts Temporal's Java test
server on it. Between the two, another process can take the port: in a full run beside another
pytest process, the other process's own test server. The server then prints `Failed to bind to
address` and stays up, listening on nothing; sdk-core waits 5 s for an answer and gives up, and
the test fails before it ran. So the harness starts the binary itself, reads what it prints, and
on a port taken stops the server and starts it on another at once, three ports at most; it waits
30 s for an answer, as `tests/dev_server.py` does for the dev server, and a start that fails says
why, never skipped. The environment it gives skips time as the SDK's does.
"""

import asyncio
import fcntl
import tempfile
import time
from asyncio.subprocess import Process
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO, Any, cast

import temporalio.service
from dev_server import DEADLINE, cli_folder, free_port, said, stop
from google.protobuf.empty_pb2 import Empty
from temporalio.api.testservice.v1 import (
    LockTimeSkippingRequest,
    SleepRequest,
    UnlockTimeSkippingRequest,
)
from temporalio.client import (
    Client,
    Interceptor,
    OutboundInterceptor,
    StartWorkflowInput,
    WorkflowHandle,
)
from temporalio.converter import DataConverter
from temporalio.testing import WorkflowEnvironment

# What the Java test server prints when its port is taken; it stays up afterwards.
TAKEN = "Failed to bind to address"
# How many ports a start may try before it fails: a collision is a moment, not a condition.
PORTS = 3
# How long a probe of a port waits for something to accept, before the server is started on it.
PROBE = 0.5
SERVER = "the test server"


class SkippingServerFailed(RuntimeError):
    """The test server didn't start, or wasn't the harness's own: a test that needs it fails,
    never skips."""


async def sdk_download(folder: Path) -> None:
    """Have the SDK download its test server into `folder`, the only way it can: by starting it
    once."""
    environment = await WorkflowEnvironment.start_time_skipping(download_dest_dir=str(folder))
    await environment.shutdown()


async def server_binary(
    folder: Path, download: Callable[[Path], Awaitable[None]] = sdk_download
) -> Path:
    """The test server's binary in `folder`, downloaded first if it isn't there. Its name is the
    SDK's, as the dev server's is: a name the SDK changes fails here, naming what the folder
    holds, never starts something else."""
    binary = folder / f"temporal-test-server-sdk-python-{temporalio.service.__version__}"
    if not binary.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        await download(folder)
    if not binary.is_file():
        held = ", ".join(sorted(path.name for path in folder.iterdir())) or "nothing"
        raise SkippingServerFailed(
            f"the SDK's test server isn't at {binary} after its download; {folder} holds: {held}. "
            "The SDK names it otherwise now: update the name in tests/skipping_server.py"
        )
    return binary


class TimeSkipping(WorkflowEnvironment):
    """A workflow environment on a test server the harness started: time skips as in the SDK's
    own (`sleep` moves the server's clock; a workflow's `result` awaited lets it run ahead), and
    `shutdown` stops the server."""

    process: Process | None = None  # the server, set once the environment is made
    # What the harness did with each port it was given, in order: `port 51234 is held by another
    # harness`, `port 51235 answers already`, `started on 51236`. For the harness's tests; set
    # with `process`, once the environment is made.
    tried: list[str]

    async def shutdown(self) -> None:
        if self.process is not None:
            await stop(self.process)

    async def sleep(self, duration: timedelta | float) -> None:
        asked = SleepRequest()
        asked.duration.FromTimedelta(
            duration if isinstance(duration, timedelta) else timedelta(seconds=duration)
        )
        await self.client.test_service.unlock_time_skipping_with_sleep(asked)

    async def get_current_time(self) -> datetime:
        answer = await self.client.test_service.get_current_time(Empty())
        return answer.time.ToDatetime().replace(tzinfo=UTC)

    @property
    def supports_time_skipping(self) -> bool:
        return True

    @asynccontextmanager
    async def skipping_unlocked(self) -> AsyncIterator[None]:
        """Let the server skip ahead while a result is awaited, then hold its clock again."""
        await self.client.test_service.unlock_time_skipping(UnlockTimeSkippingRequest())
        try:
            yield None
        finally:
            await self.client.test_service.lock_time_skipping(LockTimeSkippingRequest())


class SkipOnResult(Interceptor):
    """Temporal: a client interceptor sees every call the client makes. This one gives each
    handle `start_workflow` returns a `result` that lets time skip, as the SDK's environment does
    (temporalio.testing, `_TimeSkippingClientInterceptor`)."""

    environment: TimeSkipping | None = None  # set once the environment is made

    def intercept_client(self, next: OutboundInterceptor) -> OutboundInterceptor:
        return SkipOnResultOutbound(next, self)


class SkipOnResultOutbound(OutboundInterceptor):
    def __init__(self, next: OutboundInterceptor, skipping: SkipOnResult) -> None:
        super().__init__(next)
        self.skipping = skipping

    async def start_workflow(self, input: StartWorkflowInput) -> WorkflowHandle[Any, Any]:
        handle = await super().start_workflow(input)
        # The handle's class is the SDK's; changed here to one whose `result` skips time, the
        # way the SDK's own environment does it: a handle offers no other hook.
        handle.__class__ = SkippingHandle
        cast(SkippingHandle, handle).environment = self.skipping.environment
        return handle


class SkippingHandle(WorkflowHandle[Any, Any]):
    environment: TimeSkipping | None = None

    async def result(
        self,
        *,
        follow_runs: bool = True,
        rpc_metadata: Mapping[str, str | bytes] = {},
        rpc_timeout: timedelta | None = None,
    ) -> Any:
        if self.environment is None:
            return await super().result(
                follow_runs=follow_runs, rpc_metadata=rpc_metadata, rpc_timeout=rpc_timeout
            )
        async with self.environment.skipping_unlocked():
            return await super().result(
                follow_runs=follow_runs, rpc_metadata=rpc_metadata, rpc_timeout=rpc_timeout
            )


@asynccontextmanager
async def skipping_server(
    binary: Path,
    deadline: float = DEADLINE,
    data_converter: DataConverter = DataConverter.default,
    ports: Callable[[], int] = free_port,
) -> AsyncIterator[TimeSkipping]:
    """The test server `binary` runs, as a time-skipping environment, stopped on the way out. Its
    output goes to a file, shown if it doesn't start. `ports` gives each port to try."""
    skipping = SkipOnResult()
    with tempfile.TemporaryDirectory() as logs:
        tried: list[str] = []
        process, client, log, lock = await started(
            binary, deadline, ports, Path(logs), connecting(skipping, data_converter), tried
        )
        try:
            environment = TimeSkipping.from_client(client)
            environment.process = process
            environment.tried = tried
            skipping.environment = environment
            yield environment
        finally:
            await stop(process)
            lock.close()  # the port is another harness's to take now
            # Fail closed: a server that said its port was taken, however late, wasn't the one
            # the test talked to; another process's was. Its results aren't its own.
            if TAKEN in log.read_text(errors="replace"):
                raise SkippingServerFailed(
                    said(
                        "said its port was taken after the test began on it",
                        [str(binary)],
                        log,
                        SERVER,
                    )
                )


def connecting(
    skipping: SkipOnResult, data_converter: DataConverter
) -> Callable[[int], Awaitable[Client]]:
    """How the harness reaches a port: a client connected, its first call answered, within 2 s."""

    async def connect(port: int) -> Client:
        return await asyncio.wait_for(
            Client.connect(
                f"127.0.0.1:{port}", data_converter=data_converter, interceptors=[skipping]
            ),
            timeout=2,
        )

    return connect


def port_lock(port: int) -> IO[bytes] | None:
    """A lock on `port`, held while this harness's server runs on it, so two harness processes
    never share a port: one file per port in the CLI folder, locked with `flock` (Linux and
    macOS; released when the file is closed, or the process ends). None when another harness
    holds it: that port is in use, whatever it printed."""
    folder = cli_folder() / "ports"
    folder.mkdir(parents=True, exist_ok=True)
    # The file is never removed: unlinking a file another process is about to lock would give
    # two processes two files, and so one port; a few hundred empty files are the safe choice.
    lock = (folder / f"{port}.lock").open("wb")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None
    return lock


async def answers(port: int) -> bool:
    """Whether something accepts a connection on `port` now: another process's server, or any
    listener. Seen before a start, so no server is spawned on a port in use."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), PROBE)
    except (OSError, TimeoutError):
        return False
    writer.close()
    return True


async def started(
    binary: Path,
    deadline: float,
    ports: Callable[[], int],
    logs: Path,
    connect: Callable[[int], Awaitable[Client]],
    tried: list[str],
) -> tuple[Process, Client, Path, IO[bytes]]:
    """The server started on the first port `ports` gives that isn't taken, a client connected
    to it, its log, and the lock held on its port. A port another harness holds, or one something
    answers on, is skipped without a start; one taken in the moment between the probe and the
    bind is seen in what the server prints, and the server is stopped and the next port tried.
    Fails after `PORTS` ports, saying what the last one printed. `tried` gets one line per port."""
    command, log = [str(binary)], logs / "server-0.log"
    for attempt in range(1, PORTS + 1):
        port = ports()
        log = logs / f"server-{attempt}.log"
        lock = port_lock(port)
        if lock is None:
            tried.append(f"port {port} is held by another harness")
            log.write_text(tried[-1] + "\n")
            continue
        if await answers(port):
            lock.close()
            tried.append(f"port {port} answers already")
            log.write_text(tried[-1] + "\n")
            continue
        tried.append(f"started on {port}")
        command = [str(binary), str(port)]
        with log.open("wb") as output:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=output, stderr=asyncio.subprocess.STDOUT
            )
        try:
            client = await answering(process, port, deadline, command, log, connect)
        except BaseException:
            await stop(process)
            lock.close()
            raise
        if client is not None:
            return process, client, log, lock
        await stop(process)  # it says its port is taken, and would stay up on nothing
        lock.close()
    raise SkippingServerFailed(
        said(f"found every port it was given taken, {PORTS} of them", command, log, SERVER)
    )


async def answering(
    process: Process,
    port: int,
    deadline: float,
    command: list[str],
    log: Path,
    connect: Callable[[int], Awaitable[Client]],
) -> Client | None:
    """Wait until a client reaches the server on `port`, or the server says its port is taken
    (None); fail if it exits first or `deadline` passes. The port was probed before the start,
    so what answers is this server, but for a holder that took the port in the moment between:
    that one is caught on the way out, when the line is read again (`skipping_server`)."""
    began = time.monotonic()
    while time.monotonic() - began < deadline:
        if (code := process.returncode) is not None:
            raise SkippingServerFailed(
                said(f"exited with {code} before it answered", command, log, SERVER)
            )
        if TAKEN in log.read_text(errors="replace"):
            return None
        try:
            client = await connect(port)
        except (OSError, RuntimeError, TimeoutError):
            await asyncio.sleep(0.05)  # nothing listens yet, or nothing answered within 2 s
            continue
        return client
    raise SkippingServerFailed(said(f"didn't answer within {deadline:g} s", command, log, SERVER))


@asynccontextmanager
async def time_skipping(
    data_converter: DataConverter = DataConverter.default,
) -> AsyncIterator[TimeSkipping]:
    """A time-skipping environment for a test: the SDK's binary, started by the harness."""
    binary = await server_binary(cli_folder())
    async with skipping_server(binary, data_converter=data_converter) as environment:
        yield environment
