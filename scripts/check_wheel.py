"""Check what a built wheel of Ventoux holds: every file it must, and nothing it never may (layer
20c) (brief, D82). CI runs it on the wheel it builds; nothing here publishes.

    python scripts/check_wheel.py dist/ventoux-0.1.0-py3-none-any.whl

Each problem is said, naming the file; exit 1 on any, 0 when there is none.
"""

import sys
import zipfile
from pathlib import Path, PurePosixPath

PACKAGE = Path(__file__).parent.parent / "src" / "ventoux"

# What a team needs from the wheel beside the code: the types, its tests' helpers, the supported
# imports, the two schemas (brief, D60). The suite's files are added from the repository.
MUST_HOLD = [
    "ventoux/py.typed",
    "ventoux/testing.py",
    "ventoux/public.json",
    "ventoux/schema/case.schema.json",
    "ventoux/schema/plan.schema.json",
]
LICENCE = "the licence (LICENSE in .dist-info/licenses)"

# Never shipped: the repository's own folders, at the wheel's top (the suite has an `examples/`
# of its own, which ships), and anything holding a secret or a build's leftovers.
NEVER_FOLDERS = {"tests", "examples", "docs", "scripts"}
NEVER_SUFFIXES = {".key": "a key", ".pem": "a certificate or key", ".pyc": "compiled bytecode"}


def suite_files() -> list[str]:
    """Every file of the conformance suite, as the wheel names them (brief, D80)."""
    return sorted(
        f"ventoux/{path.relative_to(PACKAGE).as_posix()}"
        for path in (PACKAGE / "conformance").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def problems(names: list[str]) -> list[str]:
    """Every file the wheel lacks, then every one it holds and never may, one line each."""
    held = set(names)
    found = [f"missing: {name}" for name in [*MUST_HOLD, *suite_files()] if name not in held]
    if not any(_is_licence(name) for name in names):
        found.append(f"missing: {LICENCE}")
    found += [f"must never ship: {name} ({why})" for name in names if (why := forbidden(name))]
    return found


def _is_licence(name: str) -> bool:
    path = PurePosixPath(name)
    return path.name == "LICENSE" and path.parent.name == "licenses"


def forbidden(name: str) -> str | None:
    """Why the wheel may never hold `name`; None when it may."""
    path = PurePosixPath(name)
    if path.parts[0] in NEVER_FOLDERS:
        return f"the repository's {path.parts[0]}/"
    if "__pycache__" in path.parts:
        return "a build's leftovers"
    if path.suffix in NEVER_SUFFIXES:
        return NEVER_SUFFIXES[path.suffix]
    if path.name == "keys.json":
        return "a key file"
    if "recording" in path.name and path.suffix != ".py":  # `case/recording.py` is code
        return "a recording, which may hold what a model or Vault was sent"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python scripts/check_wheel.py WHEEL", file=sys.stderr)
        return 2
    with zipfile.ZipFile(argv[0]) as wheel:
        names = [name for name in wheel.namelist() if not name.endswith("/")]
    found = problems(names)
    for problem in found:
        print(problem)
    if found:
        return 1
    print(f"✓ {Path(argv[0]).name} holds what it must, and nothing it never may")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
