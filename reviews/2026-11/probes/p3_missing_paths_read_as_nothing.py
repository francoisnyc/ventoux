# Shows three CI commands ending 0 having compared nothing when a path they are given isn't there: `ventoux summary --packages`, `ventoux conformance --since`, `ventoux check [--unchanged]`.
"""Run: uv run python reviews/2026-11/probes/p3_missing_paths_read_as_nothing.py

Each runs in a temporary project holding the repository's refund package, changed in the head so
that `ventoux release` refuses it. Named rightly, the summary fails the step (exit 1). With the
packages folder misspelt, it prints an empty "Packages" section and exits 0. Only the `ventoux`
command is used.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VENTOUX = Path(sys.executable).parent / "ventoux"
CONFIGURED = '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n'
silent: list[str] = []

with tempfile.TemporaryDirectory() as folder:
    project = Path(folder)

    def run(*arguments: str, cwd: Path = project) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(VENTOUX), *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    (project / "pyproject.toml").write_text(CONFIGURED)
    for tree in ("base", "head"):
        shutil.copytree(ROOT / "examples" / "packages", project / tree / "packages")
        shutil.copy(ROOT / "contracts.lock.json", project / tree / "contracts.lock.json")
        (project / tree / "pyproject.toml").write_text(CONFIGURED)
    plan = project / "head" / "packages" / "refund" / "plans" / "refund-order.json"
    plan.write_text(plan.read_text().replace('"support-lead"', '"support"'))  # release refuses it
    (project / "before.json").write_text(run("promises").stdout)

    def summary(packages: str) -> subprocess.CompletedProcess[str]:
        return run(
            "summary", "--base", "base", "--head", "head", "--packages", packages,
            "--lock", "head/contracts.lock.json", "--base-lock", "base/contracts.lock.json",
            "--before", "before.json", "--summary-file", f"summary-{packages}.md",
        )  # fmt: skip

    right, wrong = summary("packages"), summary("package")
    print(f"ventoux summary --packages packages: exit {right.returncode}")
    print(f"ventoux summary --packages package (no such folder): exit {wrong.returncode}")
    print("  its Packages section:", repr(wrong.stdout.split("## Packages")[1].split("##")[0]))
    if right.returncode == 1 and wrong.returncode == 0:
        silent.append("summary --packages")

    since = run("conformance", "--since", "no-such-folder")
    print(
        f"ventoux conformance --since no-such-folder: exit {since.returncode}: {since.stdout.strip()}"
    )
    if since.returncode == 0:
        silent.append("conformance --since")

    # `ventoux check`: both folders misnamed in the configuration, then a builder file whose case
    # isn't at its top level.
    work = project / "work"
    shutil.copytree(ROOT / "examples" / "cases", work / "cases")
    shutil.copytree(project / "head" / "packages", work / "packages")  # the refused package
    (work / "pyproject.toml").write_text(CONFIGURED + 'cases = "casez"\npackages = "pkgs"\n')
    for arguments in (("check",), ("check", "--unchanged")):
        checked = run(*arguments, cwd=work)
        print(
            f"ventoux {' '.join(arguments)}, cases and packages misnamed: exit {checked.returncode}, output {checked.stdout + checked.stderr!r}"
        )
        if checked.returncode == 0:
            silent.append(" ".join(arguments))
    guarded = work / "guarded"
    guarded.mkdir()
    builder = (ROOT / "examples" / "cases" / "refund.py").read_text().splitlines()
    (guarded / "refund.py").write_text(
        'if __name__ == "__main__":\n' + "\n".join(f"    {line}" for line in builder) + "\n"
    )
    (work / "pyproject.toml").write_text(CONFIGURED + 'cases = "guarded"\npackages = "out"\n')
    checked = run("check", cwd=work)
    print(
        f"ventoux check, a builder file defining no case at its top level: exit {checked.returncode}, output {checked.stdout + checked.stderr!r}"
    )
    if checked.returncode == 0 and not checked.stdout:
        silent.append("check (a file defining no case)")

if silent:
    print(
        "RESULT: BROKEN - a path that isn't there, or a file that defines nothing, reads as "
        f"nothing to compare, exit 0: {'; '.join(silent)}"
    )
else:
    print("RESULT: HELD - each command refuses a path that isn't there")
