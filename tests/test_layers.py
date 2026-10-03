"""The layer boundary: `core` and `case` never import Temporal or an LLM SDK.

They must run unchanged inside a Temporal workflow, where replay needs the same decisions every
time, and in a plain test. See docs/layers/00-repository.md.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"

# What each pure layer may not import (a package and everything under it).
LLM_SDKS = {"anthropic", "openai"}
ADAPTERS = {"ventoux.temporal", "ventoux.authoring", "ventoux.tooling"}
CASE_FORBIDDEN = {"temporalio"} | LLM_SDKS | ADAPTERS
FORBIDDEN = {
    "core": CASE_FORBIDDEN | {"ventoux.case"},
    "case": CASE_FORBIDDEN,
}


def is_under(module: str, package: str) -> bool:
    """`temporalio.workflow` is under `temporalio`; `temporalio_helpers` is not."""
    return module == package or module.startswith(package + ".")


def imported_modules(source: str) -> list[str]:
    """The modules `source` imports, by `import X` or `from X import ...`."""
    # Parse, never run: the source is read as data.
    modules: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def forbidden_imports(layer: str, source: str) -> list[str]:
    """Return the modules imported by `source` that `layer` may not import."""
    return [
        name
        for name in imported_modules(source)
        if any(is_under(name, package) for package in FORBIDDEN[layer])
    ]


def test_core_may_not_import_temporal() -> None:
    assert forbidden_imports("core", "import temporalio\n") == ["temporalio"]


def test_from_imports_count_too() -> None:
    assert forbidden_imports("core", "from temporalio import workflow\n") == ["temporalio"]


def test_core_may_not_import_an_llm_sdk_or_its_submodules() -> None:
    assert forbidden_imports("core", "import openai.types\n") == ["openai.types"]


def test_case_may_not_import_temporal() -> None:
    assert forbidden_imports("case", "import temporalio\n") == ["temporalio"]


# Imports point downward: a pure layer may not reach up into the layers built on it.
@pytest.mark.parametrize(
    ("layer", "higher"),
    [
        ("core", "ventoux.case"),
        ("core", "ventoux.temporal"),
        ("core", "ventoux.authoring"),
        ("core", "ventoux.tooling"),
        ("case", "ventoux.temporal"),
        ("case", "ventoux.authoring"),
        ("case", "ventoux.tooling"),
    ],
)
def test_pure_layers_may_not_import_higher_layers(layer: str, higher: str) -> None:
    assert forbidden_imports(layer, f"from {higher} import x\n") == [higher]


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_pure_layers_import_nothing_forbidden(layer: str) -> None:
    files = sorted((SRC / "ventoux" / layer).rglob("*.py"))
    # An empty or missing layer must fail, or this test could pass by checking nothing.
    assert files, f"no source found for ventoux.{layer}"
    violations = [
        f"{path.relative_to(SRC)} imports {name}"
        for path in files
        for name in forbidden_imports(layer, path.read_text())
    ]
    assert violations == [], (
        f"ventoux.{layer} must run inside a Temporal workflow and in a plain test, so it may "
        f"not import {sorted(FORBIDDEN[layer])}. See docs/layers/00-repository.md."
    )


def test_importing_downward_is_allowed() -> None:
    assert forbidden_imports("case", "from ventoux.core import x\n") == []
    assert forbidden_imports("core", "from ventoux.core import x\n") == []


def ruff_check(source: str, path: str) -> subprocess.CompletedProcess[str]:
    """Run `ruff check` with the project's settings on `source`, as if it were the file `path`."""
    return subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--stdin-filename", path, "-"],
        input=source,
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,  # a failing check is what some tests expect; they read the return code
    )


def test_ruff_rejects_relative_imports_in_src() -> None:
    # `from ..temporal import worker` doesn't name its layer, so the boundary check can't see it.
    # The import is used, so the only thing ruff can object to is that it is relative.
    source = "from ..temporal import worker\n\nworker.run()\n"
    result = ruff_check(source, "src/ventoux/core/example.py")
    assert result.returncode == 1
    assert "TID252" in result.stdout
