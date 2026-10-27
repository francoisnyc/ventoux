# Fix: the test server's port, picked the way the server binds it

A fix, not a layer: no warm-up, and nothing new to build. It finishes what
`docs/layers/fix-flaky-temporal.md` ("The port race") left open: which socket held the test
server's port when a start failed with

```
RuntimeError: Failed starting test server: ephemeral server at 127.0.0.1:57948 did not start
within 5s. Make sure another download isn't stuck and delete the temp file.
```

That note's harness (`tests/skipping_server.py`) already keeps the failure out of the suite: it
reads the server's `Failed to bind to address` and moves to another port. Its correction of
2026-10-26 says the holder "answered nothing: a socket bound or listening on every address, with
no Temporal behind it", and stops there. This note names the holder, and has the harness stop
picking its ports.

## The cause

**What the SDK does.** `WorkflowEnvironment.start_time_skipping` (`temporalio/testing/_workflow.py`)
hands a `TestServerConfig` to sdk-core (`crates/sdk-core/src/ephemeral_server/mod.rs`, at the
commit sdk-python 1.34.0 pins, `e163abd`), which:

1. finds or downloads the server's binary, `temporal-test-server-sdk-python-1.34.0` in the system's
   temporary folder (here since 15 October; no `.downloading` file ever appeared);
2. picks a port, unless given one: `get_free_port("0.0.0.0")` binds an **IPv4** socket to port 0,
   reads the port the system chose, and closes it;
3. starts the binary with that port, its output inherited, and tries to connect every 100 ms, 50
   times ("Try to connect every 100ms for 5s"). After the 50th try it kills the process and raises
   the error above, whose advice about a download is the only cause its author had in mind.

The harness does steps 2 and 3 itself, but until this fix picked its port the same way:
`free_port` in `tests/dev_server.py` binds an IPv4 socket, on `127.0.0.1`.

**What the server does.** The binary is Temporal's Java test server, compiled to a native image.
`Grpc.newServerBuilderForPort(port, …)` (`TestServer.java:65`) binds the **wildcard address on
both families**: `lsof` shows it as `*:port` on IPv6, and it serves `127.0.0.1` through that.
Alone it listens 0.06 s after it starts. When the bind is refused it prints a stack trace and
stays up, listening on nothing (checked again here: still running after 3 s, no listening
socket), as "The port race" found:

```
Exception in thread "main" java.lang.RuntimeException: java.io.IOException: Failed to bind to
address 0.0.0.0/0.0.0.0:57948
	…
Caused by: java.net.BindException: Address already in use
```

**Who holds the port.** Each port the server was refused was held, and was still held hours
later, by an IPv6 connection of one of macOS's own daemons over the Mac's internal link
(`netstat -anv`):

```
tcp6  fe80::aede:48ff:….57948  fe80::aede:48ff:….49219  ESTABLISHED  mobileactivation
```

This machine has about 300 such connections (mobileactivationd most of them, PowerChime and
others). Each has a local port in the range the system hands out, spread across all of it (9 to
36 in every thousand ports), and they stay established for days. None of them accepts a
connection, which is why the harness's probe (decision 9) can't see them.

**Why an IPv4 pick doesn't see them.** The kernel hands out ports in order, one after the other
(six binds to port 0 in a row: 56612 to 56617; `net.inet.tcp.randomize_ports: 0`), skipping the
ones in use. For an IPv4 socket, "in use" means in use by an IPv4 socket: `in_pcbbind` checks each
candidate with `in_pcblookup_local`, which skips every socket that isn't IPv4 (xnu,
`bsd/netinet/in_pcb.c`, `if (!(inp->inp_vflag & INP_IPV4)) continue;`). So the IPv4 pick is given
port 57948 as free, although an IPv6 connection holds it. The server then binds the IPv6 wildcard,
which the kernel checks against IPv6 sockets, and is refused. Which of `in6_pcbbind`'s rules
refuses it here wasn't pinned. A connection made in the test's own name over another link didn't
refuse the bind, while an IPv6-only listener does every time, by the same path. The chance of a
pick landing on a held port is the holders over the range, about 300 in 16 384, near one in
fifty.

**Why it looked like the other process's doing.** The ports go in order, so a run walks a stretch
of the range while the holders sit still. A run fails when its walk crosses a holder and the pick,
rather than one of the client connections made between picks, lands on it. So runs fail in streaks
(two in a row at 12:31:18 and 12:31:33 on 2026-10-25) and then not at all, whatever else is
running. Five starts in a row succeeding alone proves nothing: the chance of that is 90 %.

**Not the cause, checked.**
- **The download and its lock:** no temporary file, and the binary had been in place for ten
  days.
- **Two processes picking the same port:** the ports never went backwards in 150 picks, and the
  refused port was always the next number after the previous start's.
- **A slow start:** all 297 successful SDK starts took 0.11 to 0.14 s, with and without load, with
  9.3 of 10 GB of swap in use.
- **A slow health check:** the server was never listening.

## Decided

1. **The harness picks the port the way the server binds it.** `server_port` in
   `tests/skipping_server.py` binds an IPv6 socket that takes IPv4 too (dual-stack, as the
   server) to port 0. The kernel then checks both families and hands out a port nothing holds on
   either. Where the machine has no IPv6, `::` raises and the server binds IPv4 alone, so the
   pick falls back to IPv4, which sees it whole (the containers of "The port race", decision 8).
   It is the default `ports` of `skipping_server`, so every Temporal test gets it through
   `time_skipping`. Recorded there as decision 10.
2. **The recovery stays.** The lock (decision 7), the probe (9) and the printed line (1) still
   catch a holder that comes in the moment between the pick and the bind. They no longer carry a
   standing condition, and they couldn't carry a dense one: with twenty held ports in a row, the
   harness on its old pick tried three of them and gave up ("found every port it was given
   taken").
3. **The dev server stays as it is.** `tests/dev_server.py` picks on `127.0.0.1` with IPv4, and the
   CLI binds `127.0.0.1` exactly (`--ip 127.0.0.1`): one address on one family, checked against
   that family. It can't meet this.
4. **Not a retry.** The cause is one pick to change, and a retry would hide the next one.
5. **An SDK issue is worth filing.** It is not filed from here, and the text below is a draft.
   Any macOS user with such connections hits this at the same rate, and the SDK's start can't
   recover:
   - `get_free_port("0.0.0.0")` probes IPv4 while the test server binds the dual-stack wildcard.
     It should probe with the family the server binds. Or the server could choose its own port
     and report it; the `TODO(cretz)` in `EphemeralServer::start` asks for a better signal than
     connecting.
   - A server refused its port prints the reason and stays up, so the 5 s wait ends with advice
     about a download. Reading the server's output for `Failed to bind`, as the harness does,
     would say why at once.

## Checked

- **Reproduced with the SDK's own start, before either fix:** 150 starts of
  `start_time_skipping(data_converter=development_converter())` in a loop, each start's stderr in
  its own file, beside the non-Temporal tests in another pytest process. 3 failed, each after
  5.10 s, each with the Java trace above. The other 147 took 0.11 to 0.13 s. The three ports,
  57948, 58364 and 58569, were each the next number after the previous start's, and all three
  were held by `fe80::…` connections ten minutes later.
- **The whole Temporal suite on the SDK's start, alone:** 3 of 208 tests failed this way, each with
  the trace in its "Captured stderr call". Of their ports, 63954 and 49170 were held by such
  connections an hour later. The third, 63651, no longer was, so a shorter-lived IPv6 connection
  had held it.
- **The mechanism, without the SDK:** a probe made the SDK's pick (IPv4 wildcard, port 0, closed)
  and then the server's bind (IPv6 dual-stack wildcard, the same port, 60 ms later). 5 of 552 were
  refused in one minute, and 17 of 530 in another stretch of the range. Each refused port took an
  IPv4 wildcard bind and a bind on `127.0.0.1` or `::1`, and refused the IPv6 wildcard, v6-only
  too. The same probe picking as the server binds, at the same time, had 0 refused of 560.
- **The harness on `main`, before this fix:** 300 starts, 5 moved to another port. Every one of
  those 5 ports was held by an `fe80::…` daemon connection.
- **The harness with this fix:** 300 starts, none moved to another port, beside the full suite
  running.
- **The full suite with this fix,** run beside that loop: 3796 passed and 1 failed, with no
  `Failed to bind` and no start-up error. The failure was
  `test_the_registry_knows_each_releases_open_cases`, a `TimeoutError`. "The port race" already
  saw it time out under doubled load. Run alone, it failed 2 of 3 times with this fix and 1 of 4 on
  `main`'s harness, so it fails with or without the change. Other sessions' tests were running on
  the machine at the time. It is left for its own fix (below).
- The two new tests broken on purpose. With `free_port` back as the default, the first fails as the
  harness on its old pick fails, every port it tried taken. With the fallback removed, the second
  fails with "Address family not supported by protocol". Ruff, `ruff format --check` and mypy are
  clean.

## Not in this fix

- **`test_the_registry_knows_each_releases_open_cases` times out now and then, alone too**, on
  `main` as on this branch: its own investigation.

## Promises

| Promise | Test that would fail |
|---|---|
| The harness's first port is never one an IPv6 socket holds | `test_the_first_port_is_never_one_an_ipv6_socket_holds` (`tests/test_skipping_server.py`). The next twenty ports the system would hand out are held by IPv6-only sockets (binding a port by its number doesn't move macOS's counter), and the harness must start on its first try, on none of them. Seen failing with the old pick. It bites on macOS only, since Linux hands ports out at random. |
| Where the machine has no IPv6, the port is picked on IPv4 | `test_without_ipv6_the_port_is_picked_on_ipv4`, IPv6 sockets refused for the test. Seen failing without the fallback. |
