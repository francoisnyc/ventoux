# Shows VaultKeys raising an error that quotes VAULT_TOKEN when the token ends with a line break, and that text reaching the caller, the worker's log and Temporal's history in clear.
"""Run: uv run python reviews/2026-11/probes/p3_vault_token_in_errors.py

A token read from a file or a mounted secret often ends with a line break. The standard library
refuses such a header with `ValueError("Invalid header value b'<the token>\\n'")`, raised inside
`Https.__call__`, which catches only `OSError`, `HTTPException` and timeouts. So the error is
neither `KeyRefused` nor `KeyUnavailable` (D78's "two kinds of error"), and its text holds the
token. The marker below is made up; its value is never printed, only whether it was found.

A stand-in Vault answers on 127.0.0.1 (the real transport, `urllib`, is used). Supported names:
start_case, answer, report, case_worker, data_converter. Past them: `ventoux.tooling.vault`,
`ventoux.testing`, the p1c harness and the tests' server harness.
"""

import asyncio
import http.server
import json
import logging
import os
import threading
from typing import Any

from p1c_harness import QUEUE, Setup, on_temporal, raw_histories, until

from ventoux.temporal.cases import answer, start_case
from ventoux.testing import DevelopmentCases
from ventoux.tooling.vault import VaultKeys

MARKER = "hvs.MARKER-made-up-not-a-token-7731"
MADE: set[str] = set()


class StandInVault(http.server.BaseHTTPRequestHandler):
    """Enough of Vault's transit and key-value answers for a case to open and seal."""

    def reply(self, status: int, body: dict[str, Any] | None = None) -> None:
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        name = self.path.rsplit("/", 1)[1]
        if "/keys/" in self.path and name in MADE:
            config = {"type": "aes256-gcm96", "exportable": False, "allow_plaintext_backup": False}
            return self.reply(200, {"data": config})
        self.reply(404, {"errors": []})

    def do_POST(self) -> None:
        sent = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        name = self.path.rsplit("/", 1)[1]
        if "/keys/" in self.path:
            MADE.add(name)
            return self.reply(204)
        if "/encrypt/" in self.path:
            return self.reply(200, {"data": {"ciphertext": "vault:v1:" + sent["plaintext"]}})
        if "/decrypt/" in self.path:
            return self.reply(200, {"data": {"plaintext": sent["ciphertext"][len("vault:v1:") :]}})
        self.reply(404, {"errors": []})

    def log_message(self, *args: Any) -> None:
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), StandInVault)
threading.Thread(target=server.serve_forever, daemon=True).start()
ADDRESS = f"http://127.0.0.1:{server.server_port}"


def keys(_path: Any) -> VaultKeys:
    return VaultKeys(ADDRESS, "transit", "secret")


def shown(text: str) -> str:
    return text.replace(MARKER, "<THE MARKER>")


# 1. The provider alone, as any caller meets it.
os.environ["VAULT_TOKEN"] = MARKER + "\n"
direct = False
try:
    keys(None).state("claim-1")
except Exception as error:  # noqa: BLE001
    direct = MARKER in str(error)
    print(f"VaultKeys.state raised {type(error).__name__}: {shown(str(error))!r}")
    print("  the token is in the error's text:", direct)


def claim() -> dict[str, Any]:
    return {
        "case": "claim",
        "display": {"title": "Claim"},
        "fields": {
            "national_id": {
                "type": "string",
                "sensitive": True,
                "visible_to": ["claims-sensitive"],
                "display": {"title": "National ID"},
            }
        },
        "steps": {
            "confirm": {
                "kind": "task",
                "display": {"title": "Confirm"},
                "roles": ["support"],
                "outcomes": {"ok": {"display": {"title": "OK"}}},
            },
            "look": {
                "kind": "activity",
                "display": {"title": "Look the ID up"},
                "activity": "orders.lookup@1",
                "inputs": {"order_id": {"var": "national_id"}},
                "requires": ["confirm"],
            },
        },
    }


class Kept(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(logging.Formatter().format(record))


async def scenario(setup: Setup) -> dict[str, bytes]:
    # 2. The trusted caller, opening a case while its token ends with a line break.
    os.environ["VAULT_TOKEN"] = MARKER + "\n"
    try:
        await start_case(
            setup.client, DevelopmentCases, claim(), {"national_id": "x"}, "c-0", QUEUE
        )
    except Exception as error:  # noqa: BLE001
        print(f"start_case raised {type(error).__name__} to the caller;", end=" ")
        print("the token is in its text:", MARKER in str(error))
    # 3. A worker whose token is replaced by one ending with a line break, a case in flight.
    os.environ["VAULT_TOKEN"] = MARKER
    case = await start_case(
        setup.client, DevelopmentCases, claim(), {"national_id": "1 85 05"}, "claim-1", QUEUE
    )
    await until(case, lambda now: "confirm#1" in str(now.waiting_at))
    os.environ["VAULT_TOKEN"] = MARKER + "\n"
    await answer(case, "confirm#1", "ok", "ana", ["support"])  # no value: the client seals nothing
    for _ in range(100):
        blobs = await raw_histories(setup.client, "claim-1")
        if any(MARKER.encode() in blob for blob in blobs.values()):
            break
        await asyncio.sleep(0.1)
    os.environ["VAULT_TOKEN"] = MARKER
    return blobs


kept = Kept()
logging.getLogger().addHandler(kept)
logging.getLogger().setLevel(logging.INFO)
histories = on_temporal(scenario, keys_class=keys)  # type: ignore[arg-type]
in_history = [place for place, blob in histories.items() if MARKER.encode() in blob]
for place in in_history:
    blob = histories[place].decode("utf-8", "replace")
    at = blob.index(MARKER)
    print(f"IN HISTORY ({place}): …{shown(blob[max(0, at - 60) : at + len(MARKER) + 4])!r}…")
logged = [line for line in kept.lines if MARKER in line]
for line in logged[:3]:
    print("LOGGED:", shown(line)[:300].replace("\n", " | "))
print(f"log lines holding the token: {len(logged)}; histories holding it: {len(in_history)}")
if direct or in_history or logged:
    print(
        "RESULT: BROKEN - a VAULT_TOKEN ending with a line break is quoted in a ValueError that is "
        "neither KeyRefused nor KeyUnavailable; it reaches the caller"
        + (", Temporal's history" if in_history else "")
        + (" and the worker's log" if logged else "")
    )
else:
    print("RESULT: HELD - no error, log line or history event holds the token")
