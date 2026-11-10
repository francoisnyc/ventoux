# Shows the live provider's errors saying the SDK error's kind only, never ANTHROPIC_API_KEY, for a refused request, a key ending with a line break and a key that isn't ASCII.
"""Run: uv run python reviews/2026-11/probes/p3_provider_key_never_said.py

The SDK's client is pointed at a stand-in on 127.0.0.1 (nothing leaves this machine) and given to
`Anthropic(…, client=…)`, as the repository's tests give a fake. The key is a made-up marker.
Past the supported names: `ventoux.authoring.anthropic`, `ventoux.authoring.provider`.
"""

import asyncio
import http.server
import os
import threading
import traceback
from typing import Any

for name in list(os.environ):
    if name.lower() in ("http_proxy", "https_proxy", "all_proxy"):
        del os.environ[name]  # the stand-in is on this machine

from anthropic import AsyncAnthropic

from ventoux.authoring.anthropic import Anthropic
from ventoux.authoring.provider import Message, ProviderFailed, Request

MARKER = "sk-ant-MARKER-made-up-5512"


class StandIn(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = b'{"type":"error","error":{"type":"invalid_request_error","message":"no"}}'
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


server = http.server.HTTPServer(("127.0.0.1", 0), StandIn)
threading.Thread(target=server.serve_forever, daemon=True).start()
said: list[str] = []


async def ask(key: str) -> None:
    client = AsyncAnthropic(
        api_key=key, base_url=f"http://127.0.0.1:{server.server_port}", max_retries=0
    )
    provider = Anthropic("a-model", env={"ANTHROPIC_API_KEY": key}, client=client)
    try:
        await provider.complete(Request("instructions", (Message("user", "{}"),)))
    except ProviderFailed as failed:
        said.append("".join(traceback.format_exception(failed)))
        print("ProviderFailed:", failed)
    except Exception as other:  # noqa: BLE001
        said.append("".join(traceback.format_exception(other)))
        print("another error:", type(other).__name__)


for key in (MARKER, MARKER + "\n", MARKER + "é"):
    asyncio.run(ask(key))
leaked = [text for text in said if MARKER in text]
if leaked or len(said) != 3:
    print("RESULT: BROKEN - an error of the live provider holds the key, or none was raised")
else:
    print(
        "RESULT: HELD - each failure is ProviderFailed naming the SDK error's kind; none holds the key"
    )
