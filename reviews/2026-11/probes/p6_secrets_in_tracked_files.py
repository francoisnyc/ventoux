# Counts key-like and certificate-like strings in the files git tracks (project files only, not reviews/), by file name; never prints a matched string.
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PATTERNS = {
    # A whole block: the marker, then at least 100 characters of base64 body on the next lines.
    "private-key block (with a body)": re.compile(
        rb"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*\n[A-Za-z0-9+/=\s]{100,}"
    ),
    "certificate block (with a body)": re.compile(
        rb"-----BEGIN CERTIFICATE-----\s*\n[A-Za-z0-9+/=\s]{100,}"
    ),
    "sk- style key": re.compile(rb"\bsk-[A-Za-z0-9_\-]{20,}"),
    "Vault token (hvs./hvb./s.)": re.compile(rb"\bhv[sb]\.[A-Za-z0-9_\-]{20,}"),
    "AWS access key id": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "x-api-key / authorization header with a value": re.compile(
        rb"(?i)(x-api-key|authorization)\"?\s*[:=]\s*\"?(Bearer\s+)?[A-Za-z0-9_\-\.]{16,}"
    ),
    "long base64 (44+ chars, a 32-byte key or more)": re.compile(
        rb"(?<![A-Za-z0-9+/=_\-])[A-Za-z0-9+/]{43,}={0,2}(?![A-Za-z0-9+/=_\-])"
    ),
}
# Markers alone, as a test writes one to search for it where it must never appear: counted apart.
MARKER = re.compile(rb"-----BEGIN [A-Z ]*(PRIVATE KEY|CERTIFICATE)-----")
HEX64 = re.compile(
    rb"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])"
)  # digests look like this: counted apart

tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout
files = [f for f in tracked.splitlines() if not f.startswith("reviews/") and f != "uv.lock"]
hits: dict[str, dict[str, int]] = {}
hex_files = 0
for name in files:
    data = (ROOT / name).read_bytes()
    if HEX64.search(data):
        hex_files += 1
    for label, pattern in PATTERNS.items():
        found = pattern.findall(data)
        if found:
            hits.setdefault(label, {})[name] = len(found)

print(f"tracked project files read: {len(files)} (uv.lock left out: its hashes are digests)")
print(f"files holding a 64-hex string (digests and hashes; not listed): {hex_files}")
for label in PATTERNS:
    by_file = hits.get(label, {})
    print(f"\n{label}: {sum(by_file.values())} in {len(by_file)} file(s)")
    by_folder: dict[str, int] = {}
    for name, count in by_file.items():
        folder = name.rsplit("/", 1)[0] if "/" in name else "."
        by_folder[folder] = by_folder.get(folder, 0) + count
    for folder, count in sorted(by_folder.items()):
        print(f"   {folder}/: {count}")

key_files = [f for f in files if f.endswith(".keys.json")]
print(f"\n*.keys.json files tracked: {len(key_files)}")
for folder in sorted({f.rsplit("/", 1)[0] for f in key_files}):
    print(f"   {folder}/: {sum(1 for f in key_files if f.startswith(folder + '/'))}")
recordings = [f for f in files if "/recordings/" in f]
print(f"recordings tracked: {len(recordings)}")

markers = {f: len(MARKER.findall((ROOT / f).read_bytes())) for f in files}
markers = {f: n for f, n in markers.items() if n}
print(
    f"\nBEGIN markers with no key body after them (a made-up secret a test searches for): "
    f"{sum(markers.values())} in {sorted(markers)}"
)
held = 0
empty = 0
import json  # noqa: E402

for name in key_files:
    for value in json.loads((ROOT / name).read_text()).values():
        held += value is not None
        empty += value is None
print(f"fixture key files: {held} development key(s) held, {empty} marked destroyed")

HARD = [k for k in PATTERNS if not k.startswith(("long base64", "Vault token"))]
vault = hits.get("Vault token (hvs./hvb./s.)", {})
print(f"token-shaped literals in tests (a constant a test sets and searches for): {sorted(vault)}")
hard = sum(sum(hits.get(k, {}).values()) for k in HARD)
if hard:
    print(
        f"RESULT: BROKEN - {hard} key-, token- or certificate-like string(s) outside fixture "
        "key files; see the counts above"
    )
else:
    print(
        "RESULT: HELD - no private-key or certificate block, provider key, token or "
        "authorization header value in tracked project files; the only key material is the "
        f"{len(key_files)} development fixture key file(s) counted above"
    )
