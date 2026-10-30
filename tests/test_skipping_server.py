"""The tests' time-skipping test server, started by the harness (fix-flaky-temporal, "The port
race").

A server whose port is held, by an IPv6 socket the SDK's IPv4 pick didn't see or by another
process in the moment between pick and bind, prints `Failed to bind to address` and stays up on
nothing, and sdk-core gives up after 5 s. The harness picks the port as the server binds it,
reads that line, and stops the server and starts it on another port at once.
Stand-ins (small shell scripts) play a server whose port is taken, one that exits, one that never
answers.
"""

import asyncio
import errno
import inspect
import os
import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar, Self

import pytest
import temporalio.service
from dev_server import cli_folder, free_port
from skipping_server import (
    PORTS,
    SkippingServerFailed,
    server_binary,
    server_port,
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
    # The lock: the second start skips the first's port without starting anything on it, by the
    # lock and not by the probe (the first answers there too), and the second's sleep moves its
    # own clock, never the first's.
    real = asyncio.run(server_binary(cli_folder()))
    port = free_port()

    async def go() -> tuple[timedelta, str, str, list[str]]:
        async with skipping_server(real, ports=lambda: port) as first:
            given = iter([port, free_port()])
            async with skipping_server(real, ports=lambda: next(given)) as second:
                before = await first.get_current_time()
                await second.sleep(timedelta(days=1))
                firsts_clock = await first.get_current_time() - before
                return firsts_clock, target_of(first), target_of(second), second.tried

    firsts_clock, first, second, tried = asyncio.run(go())
    assert first.endswith(f":{port}")
    assert not second.endswith(f":{port}")
    assert tried == [
        f"port {port} is held by another harness",
        f"started on {second.rpartition(':')[2]}",
    ]
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


def test_a_port_something_answers_on_is_skipped_before_any_start(tmp_path: Path) -> None:
    # Another holder answers on the port: the probe sees it, and no server is spawned there.
    # The stand-in records each port it is spawned with; it is a loser on every port, so after
    # three the start fails saying so, never "after the test began": nothing ran on the other
    # server.
    spawned = tmp_path / "spawned"
    loser = stand_in(
        tmp_path,
        f"echo $1 >> {spawned}\necho 'Exception: java.io.IOException: Failed to bind to address "
        "0.0.0.0/0.0.0.0:'$1\nexec sleep 60",
    )

    async def go() -> tuple[int, str]:
        async with await other_server() as other:
            held = sdk_port(other)
            given = iter([held, free_port(), free_port()])
            with pytest.raises(SkippingServerFailed) as failure:
                async with skipping_server(loser, ports=lambda: next(given)):
                    pass  # never reached
            return held, str(failure.value)

    held, said = asyncio.run(go())
    assert said.startswith(
        f"the test server found every port it was given taken, {PORTS} of them: {loser} "
    )
    assert str(held) not in spawned.read_text().split()
    assert len(spawned.read_text().split()) == PORTS - 1


async def other_server() -> WorkflowEnvironment:
    """The SDK's own test server, a holder the lock doesn't see; its binary from the CLI folder,
    where CI caches it, never downloaded again."""
    return await WorkflowEnvironment.start_time_skipping(download_dest_dir=str(cli_folder()))


# When the late line comes, in seconds after the loser's spawn: past the most the other server's
# start can take and succeed (0.2 s, then the SDK's own 5 s wait for its server), so it answers
# first, cold or warm. A cold read of its binary once took 3.84 s (fix-carried-checks, choice 2).
LATE = 6


def test_a_line_printed_late_fails_the_test_on_the_way_out(tmp_path: Path) -> None:
    # The last guard, for a holder that took the port in the moment between the probe and the
    # bind: the body ran on another process's server, which the line says only afterwards; its
    # results aren't its own, so the test fails, saying so. The other server starts after the
    # probe here, to be that holder.
    loser = late_line(tmp_path, LATE)

    async def taking(port: int) -> WorkflowEnvironment:
        await asyncio.sleep(0.2)  # after the probe, before the loser's line
        return await WorkflowEnvironment.start_time_skipping(
            port=port, download_dest_dir=str(cli_folder())
        )

    async def go() -> tuple[str, list[str], int, bool]:
        port = free_port()
        other = asyncio.create_task(taking(port))
        tried: list[str] = []
        ran = False
        try:
            with pytest.raises(SkippingServerFailed) as failure:
                async with skipping_server(loser, ports=lambda: port) as environment:
                    tried = environment.tried
                    await environment.sleep(timedelta(seconds=1))  # on the other server
                    await asyncio.sleep(LATE + 0.5)  # a body long enough for the line to come
                    ran = True
        finally:
            await (await other).shutdown()
        return str(failure.value), tried, port, ran

    said, tried, port, ran = asyncio.run(go())
    assert ran
    # One start, on the first try: a line printed before the other server answered would have the
    # harness start the loser again, and the test pass without being the case it is about.
    assert tried == [f"started on {port}"]
    assert said.startswith(
        f"the test server said its port was taken after the test began on it: {loser}\n"
    )


# --- From fix-test-server-port: the holder found, an IPv6 socket the IPv4 pick doesn't see ---


@contextmanager
def held_where_the_next_pick_lands(count: int = 20) -> Iterator[set[int]]:
    """The next `count` ports the system would hand out, held by IPv6-only sockets, as long as
    the block runs: as macOS's daemons hold theirs. macOS hands ports out one after the other, and
    binding a port by its number doesn't move its counter, so an IPv4 pick lands on the first held
    port every time. (Linux hands them out at random, so there the stretch is rarely met; a machine
    without IPv6 holds nothing, and the set is empty.)"""
    try:
        with socket.socket(socket.AF_INET6) as probe:
            probe.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            probe.bind(("::", 0))  # where the system's counter is now
            last: int = probe.getsockname()[1]
    except OSError:
        yield set()  # no IPv6 here, so no IPv6 socket can hold a port
        return
    holders: list[socket.socket] = []
    try:
        for port in range(last + 1, min(last + 1 + count, 65536)):
            holder = socket.socket(socket.AF_INET6)
            holders.append(holder)
            holder.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            try:
                holder.bind(("::", port))
            except OSError:
                continue  # something else has it already: held either way
            holder.listen()
        yield set(range(last + 1, last + 1 + count))
    finally:
        for holder in holders:
            holder.close()


def test_the_first_port_is_never_one_an_ipv6_socket_holds() -> None:
    # The cause: the IPv4 pick is handed a port an IPv6 socket holds, the server is refused and
    # the harness has to move. Picked as the server binds, the first port is free on both.
    async def go() -> list[str]:
        async with time_skipping() as environment:
            return environment.tried

    with held_where_the_next_pick_lands() as held:
        tried = asyncio.run(go())
    assert len(tried) == 1, f"the harness had to move: {tried}"
    assert int(tried[0].removeprefix("started on ")) not in held


def test_without_ipv6_the_port_is_picked_on_ipv4(monkeypatch: pytest.MonkeyPatch) -> None:
    # A container without IPv6 (decision 8): `::` raises, and the server binds IPv4 alone there,
    # which an IPv4 pick sees whole.
    real = socket.socket

    def without_ipv6(family: int = socket.AF_INET, *args: Any, **kwargs: Any) -> socket.socket:
        if family == socket.AF_INET6:
            raise OSError(errno.EAFNOSUPPORT, "Address family not supported by protocol")
        return real(family, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", without_ipv6)
    port = server_port()
    monkeypatch.undo()
    with socket.socket() as attempt:
        attempt.bind(("0.0.0.0", port))  # a port the IPv4 server can take


class Recorded:
    """A socket that records how it was made and used, and gives the port `PICKED`; nothing is
    bound. Each one made is kept in `made`."""

    made: ClassVar[list["Recorded"]] = []

    def __init__(self, family: int = socket.AF_INET, *args: Any, **kwargs: Any) -> None:
        self.family = family
        self.options: list[tuple[int, int, int]] = []
        self.bound: tuple[str, int] | None = None
        Recorded.made.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))

    def bind(self, address: tuple[str, int]) -> None:
        self.bound = address

    def getsockname(self) -> tuple[str, int, int, int]:
        return ("::", PICKED, 0, 0)


PICKED = 54321


def test_the_port_is_picked_on_one_dual_stack_ipv6_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    # How the pick is made, on any machine: one IPv6 socket that takes IPv4 too, bound to the
    # wildcard, port 0, as the server binds. The macOS test above bites only where ports are
    # handed out in order; this one bites on CI's Linux too (fix-test-server-port).
    Recorded.made = []
    monkeypatch.setattr(socket, "socket", Recorded)
    assert server_port() == PICKED
    [probe] = Recorded.made
    assert probe.family == socket.AF_INET6
    assert probe.options == [(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)]
    assert probe.bound == ("::", 0)


def test_the_harness_picks_its_ports_as_the_server_binds_by_default() -> None:
    assert inspect.signature(skipping_server).parameters["ports"].default is server_port


def test_an_ipv6_failure_but_no_ipv6_is_raised_never_picked_on_ipv4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only "no IPv6 here" falls back: anything else is a failure, said, never a quiet return to
    # the IPv4 pick the fix replaced (fail closed).
    real = socket.socket

    def refused(family: int = socket.AF_INET, *args: Any, **kwargs: Any) -> socket.socket:
        if family == socket.AF_INET6:
            raise OSError(errno.EMFILE, "Too many open files")
        return real(family, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", refused)
    with pytest.raises(OSError) as raised:
        server_port()
    assert raised.value.errno == errno.EMFILE
