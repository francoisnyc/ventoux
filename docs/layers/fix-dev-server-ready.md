# Fix: the dev server is ready when a client is answered

A fix, not a layer: no warm-up, and nothing new to build. The tutor's review of #66 found a full
run failing in `tests/test_temporal_activate.py` with

```
RuntimeError: Failed client connect: `get_system_info` call error after connection: Status {
code: Unavailable, message: "Frontend is not healthy yet", ... }
```

in the dev-server harness `tests/dev_server.py`, which the pull request didn't touch. It is the
second race in that harness's start; the first was the cold start (12e, fixed later).

## The cause

`answering()` waited until something accepted a TCP connection on the server's port, then the
harness called `Client.connect`, which asks the server for its system info at once. The dev
server accepts TCP before its frontend is healthy: a client that connects in between is refused
with "Frontend is not healthy yet", and the harness raised it. Idle, the gap is too short to hit;
under load it widens.

The time-skipping harness (`tests/skipping_server.py`) has waited for a client answered since #60
(fix-flaky-temporal), so it never had this race.

## Decided

1. **Ready is a client answered, never a port that accepts.** `answering()` returns a client:
   connected, its first call (`get_system_info`) answered, each try within 2 s, retried every
   50 ms until the same 30 s deadline. A client refused, cut off or unanswered is retried, never
   raised, until the deadline.
2. **A start that fails says why, and is never skipped.** The deadline's message names which half
   was missing: "nothing accepted a connection", or "it accepted connections, but answered no
   client: <the client's error, its first line>". A server that exits first still fails at once.
   So `answering()` probes TCP before it connects, which also keeps the reason honest: a client
   connecting to a port nothing listens on fails with a transport error, not a refusal.
3. **The time-skipping harness is left as it is.** It already waits for a client answered, and it
   also reads what its server prints, which this server doesn't need.

## Checked

**Reproduced before the change, gone after, under the same load.** The script below starts the
harness's dev server again and again, beside busy loops (`while True: pass`) on several times
the machine's 4 cores (`LOOPS`), each start the full `dev_server` context, client connected. Run
from the repository's root, as `LOOPS=4 uv run python repro.py 120 tests`; given a copy of
`main`'s `tests/` folder instead, it runs `main`'s harness:

```python
"""Start the harness's dev server N times beside busy loops on LOOPS times the cores; count failures."""
import asyncio, os, subprocess, sys, time
sys.path.insert(0, sys.argv[2] if len(sys.argv) > 2 else "tests")
from dev_server import cli_binary, cli_folder, dev_server

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20

async def once(binary):
    async with dev_server(binary) as environment:
        pass  # connected: Client.connect has asked get_system_info
    return None

def main():
    binary = asyncio.run(cli_binary(cli_folder()))
    loops = [subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(int(os.environ.get("LOOPS", 2)) * os.cpu_count())]
    failures = []
    try:
        for i in range(N):
            began = time.monotonic()
            try:
                asyncio.run(once(binary))
                print(f"{i}: ok in {time.monotonic() - began:.1f}s", flush=True)
            except Exception as error:
                line = str(error).splitlines()[0][:160]
                failures.append(line)
                print(f"{i}: FAILED {type(error).__name__}: {line}", flush=True)
    finally:
        for loop in loops:
            loop.kill()
    print(f"{len(failures)} of {N} failed")

main()
```


| Harness | Busy loops | Starts | Failed ("Frontend is not healthy yet") |
|---|---|---|---|
| `main` | 2 × cores | 20 | 2 |
| `main` | 2 × cores | 30, then 60 | 0, 0 |
| `main` | 4 × cores | 40 | 1 |
| `main` | 4 × cores | 120 | 4 |
| this fix | 4 × cores | 120 | 0 (the slowest start 4.0 s, well inside the 30 s deadline) |

The race is rare on this machine at twice the cores (2 in 110), as the tutor saw (1 in 10); at four
times it shows in every batch.

**The tests.** Two new ones, each seen failing on `main`'s harness, with `Client.connect`'s
error raised out of the harness, and passing with the fix. A third test's expected message changed
(it now says why).

## Not in this fix

- **`test_the_registry_knows_each_releases_open_cases` times out now and then.** It runs on the
  time-skipping server, so it isn't this race. It is tracked for its own fix.

## Promises

| Promise | Test that would fail |
|---|---|
| A server that accepts TCP before it answers a client is waited for, and the environment works | `test_a_server_that_accepts_before_it_answers_is_waited_for` (`tests/test_dev_server.py`): a stand-in accepts on the server's port for 3 s and answers nothing, then hands the port to the real server. Seen failing on `main`'s harness, which called the accept ready and raised `Client.connect`'s error. |
| A server that accepts but never answers fails at the deadline, saying it answered no client, and is stopped | `test_a_server_that_accepts_but_never_answers_fails_saying_why`. Seen failing on `main`'s harness, which raised `Client.connect`'s error at once instead. |
| A server that never accepts fails at the deadline, saying nothing accepted a connection | `test_a_server_that_never_answers_fails_showing_its_output`, its expected message updated. |
| A server that exits first fails at once, showing its output | `test_a_server_that_exits_first_fails_at_once_showing_its_output`, unchanged. |
| Each connect is bounded at 2 s: a server that accepts and holds every connection open, answering nothing, fails within the deadline and one try, saying it answered no client (`TimeoutError`), and is stopped | `test_a_server_that_holds_connections_unanswered_fails_within_the_deadline`: a stand-in keeps each accepted socket open; deadline 3 s, failed in 4.2 s. From the tutor's review. Seen failing with the bound removed: one connect waited about 27 s, and the start failed in 30.1 s. |
