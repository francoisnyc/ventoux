# Counts AI model names and personal details in tracked files and in main's commit messages, printing counts and file names only.
"""Prints no name, no address and no matching line: only how many, and where."""

import re
import subprocess


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


# Product and model family words; `CLAUDE.md` (a file's name) is counted apart.
MODEL = re.compile(r"claude|sonnet|opus\b|haiku|gpt-?\d|gemini|chatgpt|copilot", re.I)
files = [f for f in git("ls-files").splitlines() if not f.startswith("reviews/") and f != "uv.lock"]
print("tracked files naming an AI product or model (the file name CLAUDE.md apart):")
found = 0
for name in files:
    try:
        text = open(name, encoding="utf-8").read()
    except (UnicodeDecodeError, IsADirectoryError):
        continue
    hits = [
        m.group(0)
        for line in text.splitlines()
        for m in MODEL.finditer(line.replace("CLAUDE.md", ""))
    ]
    if hits and not name.startswith("tests/histories/"):  # a history's hit is ciphertext
        found += len(hits)
        print(f"  {name}: {len(hits)}")
bodies = git("log", "main", "--format=%b")
total = int(git("rev-list", "--count", "main"))
co = re.findall(r"(?im)^co-authored-by:\s*(.*?)\s*<", bodies)
with_model = [c for c in co if re.search(r"\d", c)]
sessions = len(re.findall(r"/code/session_", bodies))
emails = git("log", "main", "--format=%ae").splitlines()
personal = [e for e in emails if "noreply" not in e]
print(f"commits on main: {total}")
print(
    f"  with a Co-Authored-By line: {len(co)}, of which naming a model version: {len(with_model)}"
)
print(f"  with a session link: {sessions}")
print(
    f"  distinct author identities: {len(set(emails))}; commits under an address that isn't a no-reply one: {len(personal)}"
)
licence = open("LICENSE", encoding="utf-8").read().splitlines()[2]
print(
    f"LICENSE names a copyright holder: {'yes' if licence.lower().startswith('copyright') else 'no'}"
)
broken = found or with_model or personal
print(
    f"RESULT: {'BROKEN' if broken else 'HELD'} - {found} mentions in files, {len(with_model)} commit messages naming a model version, {len(personal)} commits under a personal address"
)
