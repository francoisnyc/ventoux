# Shows VaultKeys reading a 404 from any web server as Vault's answer "never made" (a final KeyRefused), and `ventoux doctor` saying keys.reachable passed against a server that is not Vault.
"""Run: uv run python reviews/2026-11/probes/p3_any_404_is_never_made.py

A plain web server on 127.0.0.1 answers every request `404` with an HTML page, as an ingress with
no backend, a wrong address or a wrong mount path would. Nothing here is Vault. The real transport
(`Https`, urllib) is used. Past the supported names: `ventoux.tooling.vault`, and the `ventoux`
command run in a temporary project. The token is a made-up marker; only whether it shows is said.
"""

import http.server
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from ventoux.tooling.keys import KeyRefused, KeyUnavailable
from ventoux.tooling.vault import VaultKeys

MARKER = "hvs.MARKER-made-up-not-a-token-4410"


class NotVault(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        page = b"<html><body>404 page not found</body></html>"
        self.send_response(404)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    do_POST = do_DELETE = do_GET

    def log_message(self, *args: Any) -> None:
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), NotVault)
threading.Thread(target=server.serve_forever, daemon=True).start()
address = f"http://127.0.0.1:{server.server_port}"
os.environ["VAULT_TOKEN"] = MARKER
keys = VaultKeys(address, "transit", "secret")

state = keys.state("refund-1001")
print(f"state of refund-1001, asked of a server that isn't Vault: {state!r}")
kinds = []
for what, call in (
    ("seal", lambda: keys.seal("refund-1001", b"x", "sensitive/0")),
    ("open", lambda: keys.open("refund-1001", b"vault:v1:abc", "sensitive/0")),
    ("destroy", lambda: keys.destroy("refund-1001")),
):
    try:
        call()
    except (KeyRefused, KeyUnavailable) as error:
        kinds.append(type(error).__name__)
        print(f"{what}: {type(error).__name__} (final: {isinstance(error, KeyRefused)}): {error}")

with tempfile.TemporaryDirectory() as folder:
    project = Path(folder)
    (project / "pyproject.toml").write_text(
        '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\nkeys = "platform_keys:KEYS"\n'
    )
    (project / "platform_keys.py").write_text(
        "from ventoux.tooling.vault import VaultKeys\n"
        f'KEYS = VaultKeys("{address}", "transit", "secret")\n'
    )
    ventoux = Path(sys.executable).parent / "ventoux"
    ran = subprocess.run(
        [str(ventoux), "doctor", "production"],
        cwd=project,
        capture_output=True,
        text=True,
        env={**os.environ, "VAULT_TOKEN": MARKER},
        timeout=120,
        check=False,
    )
    out = ran.stdout + ran.stderr
    for line in out.splitlines():
        if line.split()[1:2] and line.split()[1].startswith("keys."):
            print("doctor:", line[:230])
    print("doctor's output holds the token:", MARKER in out)
    reachable = [line for line in out.splitlines() if " keys.reachable:" in line]

passed = bool(reachable) and reachable[0].startswith("passed")
if state == "never made" and passed:
    print(
        "RESULT: BROKEN - a 404 from a server that isn't Vault reads as Vault's answer: the key "
        f"is 'never made', seal/open/destroy end in {sorted(set(kinds))} for good, and doctor "
        "says keys.reachable passed"
    )
else:
    print("RESULT: HELD - an answer that isn't Vault's is KeyUnavailable, and doctor doesn't pass")
