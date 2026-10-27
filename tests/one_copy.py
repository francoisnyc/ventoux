"""Each Ventoux module is loaded once: the module its package holds is the one `sys.modules` holds.

A workflow sandbox that imports a Ventoux module afresh hangs its copy on the shared package, as
that package's attribute; code reaching the module through the package then gets classes that
the rest of the process doesn't recognise (docs/layers/fix-sandbox-reimport.md).
"""

import sys

import pytest


def second_copies() -> list[str]:
    """Each loaded Ventoux module whose package holds another copy of it; empty if none."""
    copies: list[str] = []
    for name, module in list(sys.modules.items()):
        package, _, child = name.rpartition(".")
        if not name.startswith("ventoux.") or package not in sys.modules:
            continue
        if getattr(sys.modules[package], child, module) is not module:
            copies.append(name)
    return sorted(copies)


def put_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hang each module back on its package, so a test sees only the copies its own run makes."""
    for name in second_copies():
        package, _, child = name.rpartition(".")
        monkeypatch.setattr(sys.modules[package], child, sys.modules[name])
