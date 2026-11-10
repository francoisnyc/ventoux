# Shows which commands and code of docs/QUICKSTART.md work as printed when followed to the letter in a fresh folder, and which don't.
"""Run from the repository root: uv run python reviews/2026-11/probes/p5_quickstart_to_the_letter.py

Every code block is taken from docs/QUICKSTART.md itself, so the probe follows the page as it is.
`uv init` / `uv add ventoux` are not run here (they need a package index; from the built wheel,
`uv add ventoux` answers that the requirement is unsatisfiable: the package is not published).
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DOC = Path("docs/QUICKSTART.md").read_text()
PYTHON = re.findall(r"```python\n(.*?)```", DOC, re.S)
VENTOUX = str(Path(sys.executable).parent / "ventoux")
broken: list[str] = []


def run(folder: Path, *args: str) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(list(args), cwd=folder, capture_output=True, text=True)
    last = (done.stdout + done.stderr).strip().splitlines()[-1:] or [""]
    print(f"$ {' '.join(args[1:] if args[0] == VENTOUX else args)}  -> exit {done.returncode}: {last[0][:230]}")
    return done


with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp)
    (folder / "pyproject.toml").write_text('[project]\nname = "refunds"\nversion = "0.1.0"\n')

    # 1. "uv run ventoux init": "creates a cases/ folder and a development catalog"
    if run(folder, VENTOUX, "init").returncode != 0 or not (folder / "cases").exists():
        broken.append("section 1: `ventoux init` is not a command (nothing creates cases/ or names the catalog)")
    (folder / "cases").mkdir(exist_ok=True)
    (folder / "tests").mkdir()
    (folder / "cases/refund.py").write_text(PYTHON[0])
    (folder / "tests/test_refund.py").write_text(PYTHON[1])

    # 3. check: the page says init wrote [tool.ventoux] catalog; it didn't, so write what the page shows
    run(folder, VENTOUX, "check")
    with (folder / "pyproject.toml").open("a") as file:
        file.write('\n[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n')
    check = run(folder, VENTOUX, "check")
    if "refund is valid (3 steps): packages/refund/" not in check.stdout:
        broken.append("section 3: `ventoux check` did not print the line the page shows")
    run(folder, VENTOUX, "check", "--unchanged")
    run(folder, VENTOUX, "map", "packages/refund")

    # 4. dev and start
    if run(folder, VENTOUX, "dev").returncode != 0:
        broken.append("section 4: `ventoux dev` is not a command (no in-memory server, no inbox)")
    if run(folder, VENTOUX, "start", "refund", "--file", "order_id=ord-1", "amount=250").returncode != 0:
        broken.append("section 4: `ventoux start` is not a command")

    # 5. tests: `uv run pytest` is `pytest`, the script, which doesn't put the project folder on the path
    script = run(folder, str(Path(sys.executable).parent / "pytest"), "-q", "-p", "no:cacheprovider")
    if script.returncode != 0:
        broken.append("section 5: `pytest` as shown fails to import `cases.refund` (ModuleNotFoundError: "
                      "No module named 'cases'); `python -m pytest` works")
    module = run(folder, sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    if module.returncode != 0:
        broken.append("section 5: the page's tests fail even with `python -m pytest`")

    # 7. the change, then `ventoux diff`
    with (folder / "cases/refund.py").open("a") as file:
        file.write("\n" + next(block for block in PYTHON if block.startswith("notify = ")))
    after = run(folder, VENTOUX, "check")
    print(after.stdout.strip())
    if after.returncode != 0:
        broken.append("section 7: the page's own `notify_rejection` step is refused by `ventoux check` "
                      "(letters.draft@2 has no input order_id; it needs template and to_customer)")
    if run(folder, VENTOUX, "diff").returncode != 0:
        broken.append("section 7: `ventoux diff` with no arguments is refused (it needs the two folders, old and new)")

print()
for line in broken:
    print("-", line)
if broken:
    print(f"RESULT: BROKEN - {len(broken)} places where the quickstart, followed to the letter, does not work as printed")
else:
    print("RESULT: HELD - every command and code block of the quickstart worked as printed")
