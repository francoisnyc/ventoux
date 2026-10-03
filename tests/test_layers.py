"""The layer boundary: `core` and `case` never import Temporal or an LLM SDK.

They must run unchanged inside a Temporal workflow, where replay needs the same decisions every
time, and in a plain test. See docs/layers/00-repository.md.
"""

import ast

# What each pure layer may not import.
FORBIDDEN = {
    "core": {"temporalio"},
}


def forbidden_imports(layer: str, source: str) -> list[str]:
    """Return the modules imported by `source` that `layer` may not import."""
    # Parse, never run: the source is read as data.
    imported = [
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    return [name for name in imported if name in FORBIDDEN[layer]]


def test_core_may_not_import_temporal() -> None:
    assert forbidden_imports("core", "import temporalio\n") == ["temporalio"]
