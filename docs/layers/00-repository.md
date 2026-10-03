# Layer 0: repository and conventions

Status: agreed, 2026-10-03.

## What this layer is for

No product code. It sets up the repository so every later layer follows the same rules, and it
turns the brief's layers into Python packages with one rule between them: imports point downward.
`core` and `case` must stay free of Temporal and LLM code, because the interpreter runs inside a
Temporal workflow and must give the same decisions when Temporal replays its history; and because
pure code runs in a plain test in milliseconds.

## Layout

```
pyproject.toml          project, dependencies, ruff, mypy and pytest settings
uv.lock                 committed, so CI installs exactly what we tested
.python-version         3.12
src/ventoux/
  __init__.py
  core/__init__.py      schema, expressions, catalog, provenance, interpreter (pure)
  case/__init__.py      case runtime, rules, validation, migration (pure; may import core)
  temporal/__init__.py  workflows, activities, worker, client (may import core and case)
  authoring/__init__.py AI drafting and the step advisor (may import core and case)
  tooling/__init__.py   CLI, diff, views, builder (may import anything)
tests/
  test_layers.py
.github/workflows/ci.yml
```

Each `__init__.py` holds only a docstring saying what belongs there and what it may import. There
is no `ventoux.testing` yet: the tracer bullet adds it.

## Tools and dependencies

- Python 3.12+ (`requires-python = ">=3.12"`), managed with `uv`; the `src` layout, so tests run
  against the installed package rather than the working directory.
- Runtime: Pydantic v2 (the curriculum's Build line names it; nothing uses it yet).
- Development: pytest, ruff (lint and format), and mypy in strict mode with Pydantic's mypy plugin.
  We chose mypy because the team uses it at work.

## Enforcing the boundary

`tests/test_layers.py` reads the source of each layer with Python's `ast` module (it parses the
code without running it) and fails if a layer imports something it may not:

| Layer | May not import |
|---|---|
| `core` | `temporalio`, LLM SDKs (`anthropic`, `openai`), `ventoux.case`, `ventoux.temporal`, `ventoux.authoring`, `ventoux.tooling` |
| `case` | `temporalio`, LLM SDKs, `ventoux.temporal`, `ventoux.authoring`, `ventoux.tooling` |

The failure message names the file, the import and the rule it breaks. This is also why CI is
green on a suite with no product tests: pytest exits with an error when it collects no tests, and
this gives it a real one. Banning the clock, randomness and I/O in `core` belongs to layer 5 (the
interpreter), not here.

## Seams the tests use

1. The packages: `import ventoux.core` (and each other layer) succeeds once installed.
2. The boundary check: given a layer's source, it returns the forbidden imports it finds. The
   negative test comes first: a snippet in `core` that does `import temporalio` is reported.
   Then `from temporalio import workflow` and `import openai.types` (submodules count); then the
   real source tree, which must report nothing.

## CI

One GitHub Actions workflow on pushes and pull requests, Python 3.12: `uv sync --locked`,
`ruff format --check`, `ruff check`, `mypy`, `pytest`. The same commands run locally, listed in the
README's "Develop" section.

## Done when

CI is green on the pull request, the layout matches the brief's layers, and a `core` module that
imports `temporalio` makes the tests fail with a clear message.
