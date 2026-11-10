# Shows which decisions of the brief had lines of their text removed or reworded after the commit on main that first held them (CLAUDE.md: "never renumbered or rewritten").
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = "3edb471"  # the commit the review reads


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def decisions(text: str) -> dict[str, list[str]]:
    """Each decision's lines, by its number, from its `### Dn.` heading to the next heading."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = re.match(r"### (D\d+)\.", line)
        if heading:
            current = heading.group(1)
            found[current] = [line]
        elif line.startswith("## ") or line.startswith("### "):
            current = None
        elif current:
            found[current].append(line)
    return found


def words(lines: list[str]) -> str:
    """The text as one run of words, so re-wrapping a paragraph isn't read as rewriting it."""
    return " ".join(" ".join(lines).split())


# First-parent history: what main held after each merge, oldest first.
commits = git(
    "log",
    "--first-parent",
    "--reverse",
    "--format=%h %ad",
    "--date=short",
    SOURCE,
    "--",
    "docs/BRIEF.md",
).splitlines()
print(f"{len(commits)} commits on main's first-parent line touch docs/BRIEF.md")

rewrites: dict[str, list[str]] = {}
headings_changed: list[str] = []
previous: dict[str, list[str]] = {}
for entry in commits:
    sha, date = entry.split()
    now = decisions(git("show", f"{sha}:docs/BRIEF.md"))
    for number, old_lines in previous.items():
        if number not in now:
            headings_changed.append(f"{number} gone at {sha} ({date})")
            continue
        new_text = words(now[number])
        if old_lines[0] != now[number][0]:
            headings_changed.append(f"{number} heading changed at {sha} ({date})")
        # A sentence of the earlier text that the later text no longer holds, word for word.
        old_sentences = [s for s in re.split(r"(?<=[.:;])\s+", words(old_lines[1:])) if len(s) > 25]
        lost = [s for s in old_sentences if s not in new_text]
        if lost:
            rewrites.setdefault(number, []).append(
                f"{sha} ({date}): {len(lost)} sentence(s) no longer word for word, e.g. "
                f'"{lost[0][:110]}"'
            )
    previous = now

total = len(previous)
print(
    f"decisions at {SOURCE}: {total}; with text removed or reworded after first reaching main: "
    f"{len(rewrites)}"
)
for number in sorted(rewrites, key=lambda n: int(n[1:])):
    for line in rewrites[number]:
        print(f"  {number}: {line}")
for line in headings_changed:
    print("  heading:", line)
if rewrites or headings_changed:
    print(
        f"RESULT: BROKEN - {len(rewrites)} decision(s) had earlier text removed or reworded "
        f"in place on main, and {len(headings_changed)} heading change(s)"
    )
    sys.exit(0)
print("RESULT: HELD - no decision's earlier text was removed or reworded on main")
