"""The layer boundary: `core` and `case` never import Temporal or an LLM SDK.

They must run unchanged inside a Temporal workflow, where replay needs the same decisions every
time, and in a plain test. See docs/layers/00-repository.md.
"""

import ast
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"

# What each pure layer may not import (a package and everything under it).
LLM_SDKS = {"anthropic", "openai"}
ADAPTERS = {"ventoux.temporal", "ventoux.authoring", "ventoux.tooling"}
# The clock, randomness and I/O: Temporal's replay needs the same decisions every time, so a pure
# layer may read none of them (docs/layers/05-interpreter.md). Time and outside data reach it only
# as what history recorded: an activity's result, an answer, a timer firing.
CLOCK = {"time", "datetime"}
RANDOMNESS = {"random", "secrets", "uuid"}
IO = {"os", "io", "pathlib", "socket", "subprocess", "urllib", "http"}
# Side doors to all three: asyncio's event loop has a clock; importlib imports any module by its
# name, and builtins reaches any builtin, `open` and `__import__` included (curriculum, layer 6).
SIDE_DOORS = {"asyncio", "importlib", "builtins"}
NOT_REPLAYABLE = CLOCK | RANDOMNESS | IO | SIDE_DOORS
CASE_FORBIDDEN = {"temporalio"} | LLM_SDKS | ADAPTERS | NOT_REPLAYABLE
FORBIDDEN = {
    "core": CASE_FORBIDDEN | {"ventoux.case"},
    "case": CASE_FORBIDDEN,
}
# Builtins a pure layer may not call: `open` reads and writes files with no import at all;
# `__import__` imports any module by its name; `eval`, `exec` and `compile` run text as code.
FORBIDDEN_CALLS = {"open", "__import__", "eval", "exec", "compile"}


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
        elif isinstance(node, ast.ImportFrom):
            # A relative import keeps its dots (`..temporal`, or `..` alone), so it can be reported.
            modules.append("." * node.level + (node.module or ""))
    return modules


def forbidden_calls(source: str) -> list[str]:
    """The forbidden builtins `source` calls by name, such as `open(...)`; `door.open()` is a
    method, not the builtin."""
    return [
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in FORBIDDEN_CALLS
    ]


# Names a pure layer may not use at all: `__builtins__` holds every builtin, so through it
# `__builtins__["open"]` is `open`, which no list of forbidden calls would see.
FORBIDDEN_NAMES = {"__builtins__"}


def forbidden_names(source: str) -> list[str]:
    """The forbidden names `source` uses, such as `__builtins__`."""
    return [
        node.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES
    ]


def forbidden_imports(layer: str, source: str) -> list[str]:
    """Return the modules imported by `source` that `layer` may not import, and relative ones."""
    return [
        name
        for name in imported_modules(source)
        if name.startswith(".") or any(is_under(name, package) for package in FORBIDDEN[layer])
    ]


def test_core_may_not_import_temporal() -> None:
    assert forbidden_imports("core", "import temporalio\n") == ["temporalio"]


def test_from_imports_count_too() -> None:
    assert forbidden_imports("core", "from temporalio import workflow\n") == ["temporalio"]


def test_core_may_not_import_an_llm_sdk_or_its_submodules() -> None:
    assert forbidden_imports("core", "import openai.types\n") == ["openai.types"]


# Replay needs the same decisions every time: no clock, no randomness, no I/O in a pure layer.
@pytest.mark.parametrize("layer", ["core", "case"])
@pytest.mark.parametrize(
    "module",
    [
        "time",  # the clock
        "datetime",
        "random",  # randomness
        "secrets",
        "uuid",
        "os",  # I/O
        "io",
        "pathlib",
        "socket",
        "subprocess",
        "urllib.request",
        "http.client",
    ],
)
def test_pure_layers_may_not_read_the_clock_randomness_or_io(layer: str, module: str) -> None:
    assert forbidden_imports(layer, f"import {module}\n") == [module]


# Side doors: modules that reach the clock, or any module by its name, without naming it.
@pytest.mark.parametrize("layer", ["core", "case"])
@pytest.mark.parametrize(
    "source",
    [
        "import asyncio\n",  # its event loop has a clock: asyncio.get_event_loop().time()
        "import importlib\n",  # importlib.import_module("time") imports what the list forbids
        "from importlib import import_module\n",
        "import builtins\n",  # builtins.open and builtins.__import__ reach any builtin
    ],
)
def test_pure_layers_may_not_import_a_side_door(layer: str, source: str) -> None:
    assert forbidden_imports(layer, source) != []


def test_pure_layers_may_not_open_a_file() -> None:
    assert forbidden_calls("with open('plan.json') as f:\n    f.read()\n") == ["open"]


# Definitions are data: nothing in a pure layer runs code it is given as text (non-negotiables).
@pytest.mark.parametrize(
    ("source", "name"),
    [
        ("__import__('random').random()\n", "__import__"),  # imports by name, with no import
        ("eval('1 + 1')\n", "eval"),
        ("exec('x = 1')\n", "exec"),
        ("compile('1', '<plan>', 'eval')\n", "compile"),
    ],
)
def test_pure_layers_may_not_run_text_as_code(source: str, name: str) -> None:
    assert forbidden_calls(source) == [name]


def test_a_method_named_compile_is_not_the_builtin() -> None:
    assert forbidden_calls("re.compile('[a-z]+')\n") == []


def test_pure_layers_may_not_reach_the_builtins_by_name() -> None:
    # `__builtins__` is there in every module, with no import: `__builtins__["open"]` is `open`.
    assert forbidden_names("__builtins__['open']('plan.json')\n") == ["__builtins__"]


def test_a_method_named_open_is_not_the_builtin() -> None:
    assert forbidden_calls("door.open()\n") == []


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
    violations = (
        [
            f"{path.relative_to(SRC)} imports {name}"
            for path in files
            for name in forbidden_imports(layer, path.read_text())
        ]
        + [
            f"{path.relative_to(SRC)} calls {name}()"
            for path in files
            for name in forbidden_calls(path.read_text())
        ]
        + [
            f"{path.relative_to(SRC)} uses {name}"
            for path in files
            for name in forbidden_names(path.read_text())
        ]
    )
    assert violations == [], (
        f"ventoux.{layer} must run inside a Temporal workflow and in a plain test, and Temporal's "
        "replay needs the same decisions every time: so it reads no clock, no randomness and no "
        f"I/O, and may not import {sorted(FORBIDDEN[layer])}, call {sorted(FORBIDDEN_CALLS)} or "
        f"use {sorted(FORBIDDEN_NAMES)}; and every import must name its layer (no relative "
        "imports). See docs/layers/00-repository.md, 01-catalog.md, 05-interpreter.md and "
        "06-temporal.md."
    )


# Fail closed: a relative import doesn't say which layer it reaches, so it is reported, never skipped.
def test_relative_imports_are_reported() -> None:
    assert forbidden_imports("core", "from ..temporal import worker\n") == ["..temporal"]


def test_relative_imports_without_a_module_are_reported() -> None:
    assert forbidden_imports("case", "from .. import temporal\n") == [".."]


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


def test_importing_ventoux_brings_no_temporal() -> None:
    # The builder's names are re-exported from `ventoux`, and Python runs `ventoux/__init__.py`
    # before any `ventoux.core` import: so the builder must import no Temporal (layer 14a, choice 2).
    loaded = subprocess.run(
        [sys.executable, "-c", "import sys, ventoux.core; print('temporalio' in sys.modules)"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert loaded.stdout.strip() == "False"


def test_the_re_export_gives_the_builders_own_class_whatever_the_package_attribute_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Temporal's workflow sandbox imports the builder afresh for every run and hangs its copy on
    # the shared `ventoux.tooling` package, as its `builder` attribute. `from ventoux import Case`
    # must still give the class `ventoux check` looks for: the module by name, never the attribute
    # (found by the whole test suite, layer 14d).
    import ventoux
    import ventoux.tooling
    from ventoux.tooling.builder.case import Case

    monkeypatch.setattr(ventoux.tooling, "builder", types.ModuleType("a sandbox's copy"))
    assert ventoux.Case is Case


def test_the_engines_processes_never_load_the_builder() -> None:
    # The builder never runs inside the engine (brief, D58): `ventoux` re-exports its names
    # lazily, so a worker that imports the engine never imports the builder (layer 14a).
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, ventoux.temporal.worker; print('ventoux.tooling.builder' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert loaded.stdout.strip() == "False"
