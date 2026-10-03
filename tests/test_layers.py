"""The layer boundary: `core` and `case` never import Temporal or an LLM SDK.

They must run unchanged inside a Temporal workflow, where replay needs the same decisions every
time, and in a plain test. See docs/layers/00-repository.md.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"

# What each pure layer may not import (a package and everything under it).
LLM_SDKS = {"anthropic", "openai"}
FORBIDDEN = {
    "core": {"temporalio"} | LLM_SDKS,
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
