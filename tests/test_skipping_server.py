"""The tests' time-skipping test server, started by the harness (fix-flaky-temporal, "The port
race").

Two pytest processes on one machine can be given the same free port for their test servers; the
one that loses prints `Failed to bind to address` and stays up on nothing, and sdk-core gives up
after 5 s. The harness reads that line, stops the server and starts it on another port at once.
Stand-ins (small shell scripts) play a server whose port is taken, one that exits, one that never
answers.
"""

import asyncio
import os
import socket
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
import temporalio.service
from dev_server import cli_folder, free_port
from skipping_server import (
    GRACE,
    PORTS,
    SkippingServerFailed,
    server_binary,
    skipping_server,
    time_skipping,
)
from temporalio.testing import WorkflowEnvironment
from test_dev_server import stand_in

NAME = f"temporal-test-server-sdk-python-{temporalio.service.__version__}"


def wildcard_listener() -> socket.socket:
    """A listener on every address, as another process's test server is: IPv6 and IPv4 where
    the machine has IPv6, IPv4 alone where it hasn't (a container without it, where `::` raises
    "address family not supported"); the server prints the line just the same."""
    try:
        held = socket.socket(socket.AF_INET6)
        held.bind(("::", 0))
    except OSError:
        held = socket.socket(socket.AF_INET)
        held.bind(("0.0.0.0", 0))
    held.listen()
    return held


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_port_another_server_holds_is_left_for_the_next(tmp_path: Path) -> None:
    # The cause, reproduced with the real server: its port held by a wildcard listener, it says
    # so and stays up; the harness moves to the next port, and the environment skips time.
    real = asyncio.run(server_binary(cli_folder()))
    with wildcard_listener() as holder:
        taken: int = holder.getsockname()[1]
        given = iter([taken, free_port()])

        async def go() -> tuple[str, timedelta]:
            async with skipping_server(real, ports=lambda: next(given)) as environment:
                before = await environment.get_current_time()
                await environment.sleep(timedelta(days=1))
                target: str = environment.client.service_client.config.target_host
                return target, await environment.get_current_time() - before

        began = time.monotonic()
        target, skipped = asyncio.run(go())
    assert time.monotonic() - began < 15  # the taken port cost a moment, never the 5 s
    assert not target.endswith(f":{taken}")
    assert skipped >= timedelta(days=1)


def test_every_port_taken_fails_showing_what_the_server_said(tmp_path: Path) -> None:
    # A stand-in that says its port is taken and stays up, as the real server does: stopped each
    # time, and after three ports the start fails, never a fourth.
    pids = tmp_path / "pids"
    taken = stand_in(
        tmp_path,
        f"echo $$ >> {pids}\necho 'Exception: java.io.IOException: Failed to bind to address "
        "0.0.0.0/0.0.0.0:'$1\nexec sleep 60",
    )
    asked: list[int] = []

    def ports() -> int:
        asked.append(free_port())
        return asked[-1]

    with pytest.raises(SkippingServerFailed) as failure:
        asyncio.run(started(taken, ports=ports))
    assert len(asked) == PORTS
    first, second, printed = str(failure.value).splitlines()
    assert (
        first
        == f"the test server found every port it was given taken, 3 of them: {taken} {asked[-1]}"
    )
    assert (second, printed) == (
        "it printed:",
        f"Exception: java.io.IOException: Failed to bind to address 0.0.0.0/0.0.0.0:{asked[-1]}",
    )
    assert [alive(int(pid)) for pid in pids.read_text().split()] == [False, False, False]


async def started(binary: Path, deadline: float = 30, ports: Callable[[], int] = free_port) -> None:
    """Start `binary` through the harness and stop it: the test reads why it didn't start."""
    async with skipping_server(binary, deadline, ports=ports):
        pass


def test_a_server_that_exits_first_fails_at_once_showing_its_output(tmp_path: Path) -> None:
    failing = stand_in(tmp_path, "echo 'no such java' >&2\nexit 3")
    began = time.monotonic()
    with pytest.raises(SkippingServerFailed) as failure:
        asyncio.run(started(failing))
    assert time.monotonic() - began < 5
    assert str(failure.value).startswith(
        f"the test server exited with 3 before it answered: {failing} "
    )
    assert str(failure.value).endswith("\nit printed:\nno such java")


def test_a_server_that_never_answers_fails_showing_its_output(tmp_path: Path) -> None:
    pid = tmp_path / "pid"
    silent = stand_in(tmp_path, f"echo $$ > {pid}\necho 'warming up, slowly'\nexec sleep 60")
    with pytest.raises(SkippingServerFailed) as failure:
        asyncio.run(started(silent, deadline=2))
    first, second, printed = str(failure.value).splitlines()
    assert first.startswith(f"the test server didn't answer within 2 s: {silent} ")
    assert (second, printed) == ("it printed:", "warming up, slowly")
    assert not alive(int(pid.read_text()))


def test_a_binary_the_sdk_names_otherwise_fails_naming_what_is_there(tmp_path: Path) -> None:
    async def renamed(folder: Path) -> None:
        (folder / "temporal-test-server-2.0").write_text("")

    with pytest.raises(SkippingServerFailed) as failure:
        asyncio.run(server_binary(tmp_path / "cli", download=renamed))
    assert str(failure.value) == (
        f"the SDK's test server isn't at {tmp_path / 'cli' / NAME} after its download; "
        f"{tmp_path / 'cli'} holds: temporal-test-server-2.0. The SDK names it otherwise now: "
        "update the name in tests/skipping_server.py"
    )


def test_the_tests_environment_is_the_harness_s() -> None:
    # `time_skipping`, what every Temporal test uses: the binary from the SDK's folder, time
    # standing where the test leaves it until `sleep` moves it.
    async def go() -> timedelta:
        async with time_skipping() as environment:
            before = await environment.get_current_time()
            await environment.sleep(timedelta(hours=2))
            return await environment.get_current_time() - before

    assert timedelta(hours=2) <= asyncio.run(go()) < timedelta(hours=3)


# --- From the tutor review of #60: a harness never shares a port, and any other holder is seen ---


def test_two_harness_servers_given_one_port_never_share_it() -> None:
    # The lock: the second start skips the first's port without starting anything on it, and the
    # second's sleep moves its own clock, never the first's.
    real = asyncio.run(server_binary(cli_folder()))
    port = free_port()

    async def go() -> tuple[timedelta, str, str]:
        async with skipping_server(real, ports=lambda: port) as first:
            given = iter([port, free_port()])
            async with skipping_server(real, ports=lambda: next(given)) as second:
                before = await first.get_current_time()
                await second.sleep(timedelta(days=1))
                firsts_clock = await first.get_current_time() - before
                return firsts_clock, target_of(first), target_of(second)

    firsts_clock, first, second = asyncio.run(go())
    assert first.endswith(f":{port}")
    assert not second.endswith(f":{port}")
    assert firsts_clock < timedelta(minutes=1)


def target_of(environment: WorkflowEnvironment) -> str:
    target: str = environment.client.service_client.config.target_host
    return target


def sdk_port(environment: WorkflowEnvironment) -> int:
    """The port the SDK's own test server answers on: another holder the lock doesn't see."""
    return int(target_of(environment).rpartition(":")[2])


def late_line(folder: Path, delay: float) -> Path:
    """A stand-in printing the server's line `delay` seconds after its spawn, then staying up:
    a loser that was slow to say so, while another server answered on its port."""
    return stand_in(
        folder,
        f"sleep {delay}\necho 'Exception: java.io.IOException: Failed to bind to address "
        "0.0.0.0/0.0.0.0:'$1\nexec sleep 60",
    )


def test_a_line_printed_within_the_grace_moves_the_harness_off_a_port_that_answered(
    tmp_path: Path,
) -> None:
    # Another holder answers on the port before the loser prints: the harness reads the line
    # again after the grace and leaves the port. The stand-in is a loser on every port, so after
    # three the start fails saying so, never "after the test began": nothing ran on the other
    # server.
    loser = late_line(tmp_path, GRACE / 3)

    async def go() -> str:
        async with await WorkflowEnvironment.start_time_skipping() as other:
            given = iter([sdk_port(other), free_port(), free_port()])
            with pytest.raises(SkippingServerFailed) as failure:
                async with skipping_server(loser, ports=lambda: next(given)):
                    pass  # never reached
            return str(failure.value)

    assert asyncio.run(go()).startswith(
        f"the test server found every port it was given taken, {PORTS} of them: {loser} "
    )


def test_a_line_printed_after_the_grace_fails_the_test_on_the_way_out(tmp_path: Path) -> None:
    # The last guard: the body ran on another process's server, which the line says only
    # afterwards; its results aren't its own, so the test fails, saying so.
    loser = late_line(tmp_path, GRACE + 1)

    async def go() -> tuple[str, bool]:
        async with await WorkflowEnvironment.start_time_skipping() as other:
            port = sdk_port(other)
            ran = False
            with pytest.raises(SkippingServerFailed) as failure:
                async with skipping_server(loser, ports=lambda: port) as environment:
                    await environment.sleep(timedelta(seconds=1))  # on the other server
                    await asyncio.sleep(GRACE + 1.5)  # a body long enough for the line to come
                    ran = True
            return str(failure.value), ran

    said, ran = asyncio.run(go())
    assert ran
    assert said.startswith(
        f"the test server said its port was taken after the test began on it: {loser}\n"
    )
