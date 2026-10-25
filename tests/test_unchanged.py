"""`ventoux check --unchanged`: the same run, writing nothing, every package compared with the
committed files byte for byte (layer 14d, choices 40 to 45). The curriculum's negative test:
regenerated output that differs from the committed JSON fails CI.
See docs/layers/14-builder.md and docs/guides/builder.md, "In CI: --unchanged".
"""

import shutil
from pathlib import Path

import pytest

from ventoux.tooling.cli import main

ROOT = Path(__file__).parent.parent
QUICKSTART = ROOT / "examples" / "quickstart"
CONFIGURATION = '[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n'


def a_project(folder: Path, configuration: str = CONFIGURATION) -> Path:
    """The quickstart's project in `folder`: its builder file, and its committed package."""
    shutil.copytree(QUICKSTART / "cases", folder / "cases")
    shutil.copytree(QUICKSTART / "packages", folder / "packages")
    (folder / "pyproject.toml").write_text(configuration)
    return folder


def snapshot(folder: Path) -> dict[str, bytes]:
    """Every file under `folder`, by path, with its bytes: what `--unchanged` must leave alone.
    Python's bytecode caches are left out: Python writes them when a builder file is imported,
    and git ignores them; they are no package's file."""
    return {
        str(p.relative_to(folder)): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def test_a_committed_file_that_differs_fails_naming_it_and_the_first_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The curriculum's negative test: the committed JSON was edited by hand (or the Python
    # changed and nobody regenerated): CI fails, naming the file and the first line that differs.
    monkeypatch.chdir(a_project(tmp_path))
    committed = tmp_path / "packages" / "refund" / "case.json"
    text = committed.read_text()
    line = text.splitlines().index("            100") + 1  # the approval's threshold
    committed.write_text(text.replace("            100\n", "            1000\n"))
    before = snapshot(tmp_path)
    assert main(["check", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert (
        f"packages/refund/case.json differs from what cases/refund.py writes, first at line {line}:"
        in said
    )
    assert "  committed: 1000" in said
    assert "  written:   100" in said
    assert "✗ refund: 1 file differs." in said
    assert "Run `ventoux check` and commit what it writes." in said
    assert snapshot(tmp_path) == before  # nothing written


def test_a_missing_committed_file_fails_saying_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 14a's lesson: a committed JSON that was never committed. Missing counts as different.
    monkeypatch.chdir(a_project(tmp_path))
    (tmp_path / "packages" / "refund" / "case.json").unlink()
    before = snapshot(tmp_path)
    assert main(["check", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert "packages/refund/case.json is missing: cases/refund.py writes it" in said
    assert "✗ refund: 1 file differs." in said
    assert snapshot(tmp_path) == before


def test_a_committed_file_the_builder_no_longer_writes_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path))
    stale = tmp_path / "packages" / "refund" / "plans" / "refund-order.json"
    stale.parent.mkdir()
    stale.write_text("{}")
    before = snapshot(tmp_path)
    assert main(["check", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert "packages/refund/plans/refund-order.json: no builder case writes it any more" in said
    assert snapshot(tmp_path) == before


def test_a_folder_no_builder_case_defines_is_refused_unless_listed_by_hand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Stale output of a removed case and a hand-written package look the same on disk (choice 42).
    monkeypatch.chdir(a_project(tmp_path))
    shutil.copytree(ROOT / "examples" / "packages" / "refund", tmp_path / "packages" / "legacy")
    legacy = tmp_path / "packages" / "legacy" / "case.json"
    legacy.write_text(legacy.read_text().replace('"case": "refund"', '"case": "legacy"'))
    before = snapshot(tmp_path)
    assert main(["check", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert (
        "packages/legacy: no builder file defines it and by_hand doesn't list it: stale output "
        "of a removed case, or a hand-written package not yet listed"
    ) in said
    assert snapshot(tmp_path) == before
    (tmp_path / "pyproject.toml").write_text(CONFIGURATION + 'by_hand = ["legacy"]\n')
    assert main(["check", "--unchanged"]) == 0
    assert "✓ legacy is valid (3 steps): written by hand, checked, not compared" in (
        capsys.readouterr().out
    )
    assert snapshot(tmp_path)["pyproject.toml"] != before["pyproject.toml"]
    assert {k: v for k, v in snapshot(tmp_path).items() if k != "pyproject.toml"} == {
        k: v for k, v in before.items() if k != "pyproject.toml"
    }


def test_a_by_hand_package_is_still_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path, CONFIGURATION + 'by_hand = ["legacy"]\n'))
    shutil.copytree(ROOT / "examples" / "packages" / "refund", tmp_path / "packages" / "legacy")
    legacy = tmp_path / "packages" / "legacy" / "case.json"
    text = legacy.read_text().replace('"case": "refund"', '"case": "legacy"')
    legacy.write_text(text.replace('"support"', '"nobody"', 1))  # the review's roles
    assert main(["check", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert "packages/legacy/case.json: steps.review.roles UNKNOWN_ROLE: " in said
    assert "✗ legacy is refused: 1 error." in said


def test_a_name_both_a_builder_defines_and_by_hand_lists_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path, CONFIGURATION + 'by_hand = ["refund"]\n'))
    assert main(["check", "--unchanged"]) == 2
    assert "refund is listed in by_hand, and cases/refund.py defines it: one or the other" in (
        capsys.readouterr().err
    )


def test_a_file_that_raises_or_exits_is_refused_through_unchanged_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 14c's rule holds: the same `built`, so a file that raises or exits is refused at its line.
    monkeypatch.chdir(a_project(tmp_path))
    before = snapshot(tmp_path)
    (tmp_path / "cases" / "exits.py").write_text("import sys\n\nsys.exit(0)\n")
    assert main(["check", "--unchanged"]) == 2
    assert "cases/exits.py:3: SystemExit: 0" in capsys.readouterr().err
    (tmp_path / "cases" / "exits.py").write_text("raise RuntimeError('no')\n")
    assert main(["check", "--unchanged"]) == 2
    assert "cases/exits.py:1: RuntimeError: no" in capsys.readouterr().err
    (tmp_path / "cases" / "exits.py").unlink()
    assert snapshot(tmp_path) == before


def test_a_refused_package_fails_through_unchanged_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path))
    builder = tmp_path / "cases" / "refund.py"
    builder.write_text(builder.read_text().replace('roles=["support-lead"]', 'roles=["nobody"]'))
    before = snapshot(tmp_path)
    assert main(["check", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert "UNKNOWN_ROLE" in said
    assert "✗ refund is refused: 1 error." in said
    assert snapshot(tmp_path) == before


def test_a_run_that_passes_writes_nothing_either(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(a_project(tmp_path))
    before = snapshot(tmp_path)
    assert main(["check", "--unchanged"]) == 0
    assert "✓ refund is unchanged: packages/refund/ is what cases/refund.py writes" in (
        capsys.readouterr().out
    )
    assert snapshot(tmp_path) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cases", "packages", "pyproject.toml"]


# --- The CI step (choices 44 and 45) -------------------------------------------------------------

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def ci_runs(line: str) -> bool:
    """Whether the `check` job runs `line`, read from the workflow as text, comments left out."""
    job = WORKFLOW.read_text().split("  check:")[1].split("\n  changes:")[0]
    return any(l.strip() == line for l in job.splitlines() if not l.strip().startswith("#"))


def this_repositorys_project(folder: Path) -> Path:
    """A copy of this repository's own project: its configuration, builder files and packages."""
    shutil.copy(ROOT / "pyproject.toml", folder / "pyproject.toml")
    shutil.copytree(ROOT / "examples" / "cases", folder / "examples" / "cases")
    shutil.copytree(ROOT / "examples" / "packages", folder / "examples" / "packages")
    return folder


def test_ci_runs_the_regeneration_check_against_the_configured_catalog() -> None:
    # One line in `check`, after pytest; and once more in the quickstart's own project.
    assert ci_runs("- run: uv run ventoux check --unchanged")
    assert ci_runs(
        "- run: cd examples/quickstart && uv run --project ../.. ventoux check --unchanged"
    )
    text = WORKFLOW.read_text()
    doing = [l for l in text.splitlines() if not l.strip().startswith("#")]  # comments left out
    assert text.count("permissions:") == 1  # 13e's: read-only, at the top, unchanged
    assert "  contents: read" in doing
    assert not any("pull_request_target" in l for l in doing)


def test_the_curriculums_negative_test_end_to_end_through_the_ci_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The command the workflow runs, on this repository's own project, with one committed byte
    # changed, then with the Python changed and the JSON left stale: each fails CI.
    assert ci_runs("- run: uv run ventoux check --unchanged")
    monkeypatch.chdir(this_repositorys_project(tmp_path))
    assert main(["check", "--unchanged"]) == 0
    committed = tmp_path / "examples" / "packages" / "refund" / "case.json"
    committed.write_text(committed.read_text().replace('"Customer refund"', '"Customer refunds"'))
    before = snapshot(tmp_path)
    assert main(["check", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert (
        "examples/packages/refund/case.json differs from what examples/cases/refund.py writes"
        in said
    )
    assert '  committed: "title": "Customer refunds"' in said
    assert snapshot(tmp_path) == before
    committed.write_text(committed.read_text().replace('"Customer refunds"', '"Customer refund"'))
    builder = tmp_path / "examples" / "cases" / "refund.py"
    builder.write_text(builder.read_text().replace('title="Customer refund"', 'title="Refund"'))
    assert main(["check", "--unchanged"]) == 1
    assert '  written:   "title": "Refund"' in capsys.readouterr().out
