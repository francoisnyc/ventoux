# Shows, for commands the guides print with their output, whether running them on the committed examples prints what the guide says.
import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def block_after(guide: str, command_line: str) -> list[str]:
    """The lines the guide prints under `command_line`, to the end of its fenced block (or the
    next fenced block, when the command sits alone in a `sh` block)."""
    text = (ROOT / guide).read_text()
    start = text.index(command_line) + len(command_line)
    rest = text[start:]
    body = rest[: rest.index("```")]
    if not body.strip():  # command alone in its block: the output is the next block
        rest = rest[rest.index("```") + 3 :]
        rest = rest[rest.index("```") :]
        rest = rest[rest.index("\n") + 1 :]
        body = rest[: rest.index("```")]
    return body.strip("\n").splitlines()


def run(args: list[str]) -> list[str]:
    done = subprocess.run(
        ["uv", "run", "ventoux", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return (done.stdout + done.stderr).strip("\n").splitlines()


def clean(lines: list[str]) -> list[str]:
    return [line for line in lines if "UV_NATIVE_TLS" not in line]


broken: list[str] = []
with tempfile.TemporaryDirectory() as tmp:
    cases = [
        ("docs/guides/deployment.md", "$ ventoux version", ["version"]),
        (
            "docs/guides/cases.md",
            "$ ventoux map examples/packages/refund",
            ["map", "examples/packages/refund"],
        ),
        (
            "docs/guides/cases.md",
            "uv run ventoux simulate examples/refund/stories/nobody-reviews.json",
            ["simulate", "examples/refund/stories/nobody-reviews.json"],
        ),
        (
            "docs/guides/releases.md",
            "$ ventoux release examples/packages/refund --releases releases --commit 4f2a9c1",
            ["release", "examples/packages/refund", "--releases", tmp, "--commit", "4f2a9c1"],
        ),
    ]
    for guide, line, args in cases:
        said = block_after(guide, line)
        seen = clean(run(args))
        # The guide may print only the beginning of a long output: compare what it prints.
        prefix = seen[: len(said)]
        same = said == prefix
        print(f"\n{guide}: {line}")
        print(f"  guide prints {len(said)} line(s); the command printed {len(seen)}")
        if not same:
            for d in list(difflib.unified_diff(said, prefix, "guide", "observed", lineterm=""))[
                :14
            ]:
                print("   ", d)
            broken.append(f"{guide}: `{line.lstrip('$ ')}`")
        else:
            print("  same")

if broken:
    print(
        f"\nRESULT: BROKEN - {len(broken)} guide output(s) differ from what the command prints: "
        + "; ".join(broken)
    )
else:
    print("\nRESULT: HELD - each guide output is what the command prints")
