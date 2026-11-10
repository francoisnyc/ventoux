"""The published package: what its wheel holds, what it says, and what a team may import (layer
20c) (brief, D82). See docs/layers/20-deployment.md, "20c", and docs/guides/releasing-ventoux.md.
Nothing here publishes: wheels are built and read in temporary folders."""

import ast
import importlib
import json
import subprocess
import sys
import textwrap
import tomllib
import zipfile
from importlib import metadata
from pathlib import Path
from typing import cast

import pytest

from ventoux.case.engine import ENGINE
from ventoux.tooling.cli import main

ROOT = Path(__file__).parent.parent
CHECK_WHEEL = ROOT / "scripts" / "check_wheel.py"
LICENCE = "ventoux-0.1.0.dist-info/licenses/LICENSE"


def complete() -> list[str]:
    """Every file a wheel must hold, as the repository's package has them."""
    package = ROOT / "src" / "ventoux"
    suite = sorted(
        f"ventoux/{path.relative_to(package).as_posix()}"
        for path in (package / "conformance").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    return [
        "ventoux/__init__.py",
        "ventoux/py.typed",
        "ventoux/testing.py",
        "ventoux/public.json",
        "ventoux/schema/case.schema.json",
        "ventoux/schema/plan.schema.json",
        *suite,
        LICENCE,
    ]


def wheel(folder: Path, names: list[str]) -> Path:
    """A wheel holding `names`, each with some bytes: made here, by zip."""
    path = folder / "ventoux-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as made:
        for name in names:
            made.writestr(name, b"{}")
    return path


def checked(path: Path) -> tuple[int, str]:
    """What `scripts/check_wheel.py` says of the wheel at `path`, and its exit code."""
    ran = subprocess.run(
        [sys.executable, str(CHECK_WHEEL), str(path)], capture_output=True, text=True, check=False
    )
    return ran.returncode, ran.stdout + ran.stderr


@pytest.mark.parametrize(
    "missing",
    [
        "ventoux/schema/plan.schema.json",
        "ventoux/conformance/suite.json",
        "ventoux/py.typed",
        LICENCE,
    ],
    ids=["a schema", "the suite's index", "py.typed", "the licence"],
)
def test_a_wheel_missing_a_file_it_must_hold_is_refused_naming_it(
    tmp_path: Path, missing: str
) -> None:
    names = [name for name in complete() if name != missing]
    code, said = checked(wheel(tmp_path, names))
    assert code == 1
    shown = "the licence (LICENSE in .dist-info/licenses)" if missing == LICENCE else missing
    assert f"missing: {shown}" in said


@pytest.mark.parametrize(
    ("extra", "why"),
    [
        ("tests/test_doctor.py", "the repository's tests/"),
        ("examples/quickstart/cases/refund.py", "the repository's examples/"),
        ("docs/BRIEF.md", "the repository's docs/"),
        ("ventoux/operator.key", "a key"),
        ("ventoux/temporal-ca.pem", "a certificate or key"),
        ("ventoux/keys.json", "a key file"),
        (
            "ventoux/advisor-recording.json",
            "a recording, which may hold what a model or Vault was sent",
        ),
        ("ventoux/__pycache__/cli.cpython-312.pyc", "a build's leftovers"),
    ],
    ids=["tests", "examples", "docs", "a key", "a pem", "keys.json", "a recording", "bytecode"],
)
def test_a_wheel_holding_a_file_it_never_may_is_refused_naming_it(
    tmp_path: Path, extra: str, why: str
) -> None:
    code, said = checked(wheel(tmp_path, [*complete(), extra]))
    assert code == 1
    assert f"must never ship: {extra} ({why})" in said


def test_a_complete_wheel_passes_its_suite_examples_included(tmp_path: Path) -> None:
    assert any("/conformance/examples/" in name for name in complete())  # the suite's own
    code, said = checked(wheel(tmp_path, complete()))
    assert (code, said.strip()) == (
        0,
        "✓ ventoux-0.1.0-py3-none-any.whl holds what it must, and nothing it never may",
    )


def test_the_wheel_uv_builds_holds_what_it_must_and_its_files_as_the_repository_has_them(
    tmp_path: Path,
) -> None:
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(ROOT)],
        check=True,
        capture_output=True,
    )
    (built,) = tmp_path.glob("ventoux-*.whl")
    code, said = checked(built)
    assert code == 0, said
    package = ROOT / "src" / "ventoux"
    with zipfile.ZipFile(built) as held:
        for name in held.namelist():
            if name.startswith(("ventoux/schema/", "ventoux/conformance/")) and not name.endswith(
                "/"
            ):
                local = package / name.removeprefix("ventoux/")
                assert held.read(name) == local.read_bytes(), name


def test_ventoux_version_says_the_package_the_engine_and_the_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Three versions, each its own: the package's, from its installed metadata (written once, in
    # pyproject.toml); the engine's (brief, D51); the schema's `$id` (brief, D60, D82).
    assert main(["version"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "ventoux 0.1.0",
        f"engine {ENGINE}",
        f"schema https://ventoux.dev/schema/engine-{ENGINE}/",
    ]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["version"] == metadata.version("ventoux") == "0.1.0"


PUBLIC = ROOT / "src" / "ventoux" / "public.json"


def listed() -> dict[str, list[str]]:
    """The supported imports, by module (brief, D82)."""
    return cast(dict[str, list[str]], json.loads(PUBLIC.read_text()))


def unimportable(supported: dict[str, list[str]]) -> list[str]:
    """Each listed name that doesn't import, as `module.name`."""
    found: list[str] = []
    for module, names in supported.items():
        try:
            loaded = importlib.import_module(module)
        except ImportError:
            found += [f"{module}.{name}" for name in names]
            continue
        found += [f"{module}.{name}" for name in names if not importable(loaded, module, name)]
    return found


def importable(loaded: object, module: str, name: str) -> bool:
    """Whether `from module import name` works: an attribute, or else a submodule, as Python
    looks for one."""
    if hasattr(loaded, name):
        return True
    try:
        importlib.import_module(f"{module}.{name}")
    except ImportError:
        return False
    return True


def test_a_supported_name_that_doesnt_import_is_said_naming_it() -> None:
    assert unimportable({"ventoux": ["Case", "Nope"], "ventoux.gone": ["x"]}) == [
        "ventoux.Nope",
        "ventoux.gone.x",
    ]


def test_every_supported_name_imports() -> None:
    # A removed name fails here: removing one is a decision, as a contract change is (brief, D82).
    assert listed(), "public.json lists nothing"
    assert unimportable(listed()) == []


def imported_by_the_docs() -> set[str]:
    """Every `module.name` the guides, the README and the examples import from Ventoux: from the
    Python code blocks of each Markdown file, and from each Python file under examples/."""
    sources = (
        [
            textwrap.dedent(block.split("\n", 1)[1])  # a block in a list is indented
            for path in [ROOT / "README.md", *(ROOT / "docs" / "guides").glob("*.md")]
            for block in path.read_text().split("```")[1::2]
            if block.startswith("python")
        ]
        + [path.read_text() for path in (ROOT / "examples").rglob("*.py")]
    )
    found: set[str] = set()
    for source in sources:
        try:
            tree = ast.parse(source)
        except SyntaxError:  # a block showing part of a file: its import lines read alone
            lines = [line.strip() for line in source.splitlines()]
            tree = ast.parse("\n".join(line for line in lines if line.startswith("from ")))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("ventoux"):
                found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def test_every_name_the_docs_import_is_supported() -> None:
    supported = {f"{module}.{name}" for module, names in listed().items() for name in names}
    assert sorted(imported_by_the_docs() - supported) == []


def test_pydantic_is_bounded_to_the_minor_version_the_hashes_were_made_with() -> None:
    # A contract's hash is made from pydantic's JSON Schema of its models (core/promise.py), and
    # pydantic 2.14 writes a decimal field's differently from 2.13: under another minor version,
    # contracts would hash otherwise and the lock and the registry refuse them (brief, D54). So
    # the package stays on the minor its hashes were made with, until the hash no longer depends
    # on pydantic's rendering (brief, D82, as amended).
    major, minor = (int(part) for part in metadata.version("pydantic").split(".")[:2])
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    (pydantic,) = [d for d in project["dependencies"] if d.startswith("pydantic")]
    assert f"<{major}.{minor + 1}" in pydantic, pydantic


WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def package_job() -> list[str]:
    """The `package` job's lines, comments left out, read from the workflow as text."""
    text = WORKFLOW.read_text()
    assert "\n  package:\n" in text, "ci.yml has no package job"
    job = text.split("\n  package:\n", 1)[1]
    job = job.split("\n\n  ", 1)[0]  # up to the next job
    return [line.strip() for line in job.splitlines() if not line.strip().startswith("#")]


def test_ci_builds_the_wheel_installs_it_fresh_and_runs_it_from_outside_the_repository() -> None:
    lines = package_job()
    steps = [
        "- run: uv build --out-dir dist",
        "- run: uv run --no-project python scripts/check_wheel.py dist/ventoux-*.whl",
        "- run: uv venv /tmp/installed",
        "- run: uv pip install --python /tmp/installed dist/ventoux-*.whl",
        "- run: /tmp/installed/bin/ventoux version",
        "- run: /tmp/installed/bin/ventoux schema --unchanged",
        "- run: /tmp/installed/bin/ventoux conformance --unchanged",
    ]
    found = [lines.index(step) for step in steps]  # each there,
    assert found == sorted(found)  # in this order
    # The installed commands run outside the repository: only what the wheel installed is read.
    for step in steps[4:]:
        assert lines[lines.index(step) + 1] == "working-directory: /tmp", step
    # Built and checked, never published (brief, D82).
    assert not any(word in line for line in lines for word in ("publish", "pypi", "git tag"))


RELEASING = ROOT / "docs" / "guides" / "releasing-ventoux.md"


def test_the_release_guide_names_each_step_and_leaves_the_tag_and_publish_to_the_maintainer() -> (
    None
):
    guide = RELEASING.read_text()
    for step in (
        'version = "',  # the bump, in pyproject.toml
        "CHANGELOG.md",
        "`package` job",
        "uv build",
        "git tag v",
        "uv publish",
    ):
        assert step in guide, step
    prose = " ".join(guide.replace("**", "").split())  # as read, not as wrapped
    assert "The tag and the publish are the maintainer's, never CI's" in prose


def test_the_changelog_has_an_entry_for_the_version_being_released() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    headings = [l for l in (ROOT / "CHANGELOG.md").read_text().splitlines() if l.startswith("## ")]
    assert headings and headings[0].startswith(f"## {version}"), headings[:1]
