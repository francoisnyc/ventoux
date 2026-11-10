# Shows whether every relative Markdown link (file and #anchor) in the README files, the quickstart, the changelog and the guides points at something that exists.
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = [
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
    ROOT / "docs/QUICKSTART.md",
    ROOT / "docs/README-draft.md",
    ROOT / "docs/CURRICULUM.md",
    *sorted((ROOT / "docs/guides").glob("*.md")),
]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def anchors(path: Path) -> set[str]:
    """GitHub's anchor for each heading: lowercase, punctuation dropped, spaces to hyphens."""
    found: set[str] = set()
    fenced = False
    for line in path.read_text().splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if fenced or not line.startswith("#"):
            continue
        title = line.lstrip("#").strip().lower()
        title = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
        found.add(title)
    return found


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`(?!\])", lambda m: m.group(0) if "](" in m.group(0) else "", text)


broken: list[str] = []
checked = 0
for file in FILES:
    for target in LINK.findall(strip_code(file.read_text())):
        if re.match(r"[a-z]+:", target):
            continue  # http:, https:, mailto:
        checked += 1
        path_part, _, anchor = target.partition("#")
        dest = (file.parent / path_part).resolve() if path_part else file
        if not dest.exists():
            broken.append(f"{file.relative_to(ROOT)}: ({target}) -> no such file")
        elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
            broken.append(f"{file.relative_to(ROOT)}: ({target}) -> no heading '#{anchor}'")

print(f"relative links checked: {checked} in {len(FILES)} files")
for line in broken:
    print("  broken:", line)
if broken:
    print(f"RESULT: BROKEN - {len(broken)} relative link(s) point at nothing")
    sys.exit(0)
print("RESULT: HELD - every relative link resolves to a file, and every anchor to a heading")
