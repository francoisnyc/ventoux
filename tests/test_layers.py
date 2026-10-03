"""The layer boundary: `core` and `case` never import Temporal or an LLM SDK.

They must run unchanged inside a Temporal workflow, where replay needs the same decisions every
time, and in a plain test. See docs/layers/00-repository.md.
"""

import ast

# What each pure layer may not import.
FORBIDDEN = {
    "core": {"temporalio"},
}


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
    return [name for name in imported_modules(source) if name in FORBIDDEN[layer]]


def test_core_may_not_import_temporal() -> None:
    assert forbidden_imports("core", "import temporalio\n") == ["temporalio"]


def test_from_imports_count_too() -> None:
    assert forbidden_imports("core", "from temporalio import workflow\n") == ["temporalio"]
