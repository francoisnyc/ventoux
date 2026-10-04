# Ventoux

**Case management and human-in-the-loop workflows for Temporal.**

Ventoux adds cases, approvals and human tasks to your existing [Temporal](https://temporal.io)
server. Definitions are data: reviewed in pull requests, checked before they run, changeable for open
cases, and safe for an AI to draft. Agents propose plans, Ventoux checks them, people approve.

## Where it runs: on your Temporal server

Ventoux is not a separate platform installed next to Temporal. It runs on the Temporal server your
team already operates, self-hosted or Temporal Cloud:

- **Cases are Temporal workflows** in your namespace: their history is Temporal history, with no
  new engine and no new database.
- **The Ventoux engine is a Python library** inside a worker you deploy like any other.
- **Your activities and workflows stay where they are** (Python or Java workers); cases call them.
- **Operations are Temporal's:** the same UI, metrics, alerting and access control.
- **What Ventoux adds:** one small API service with a reference inbox (the only way into the engine),
  resolvers to show records from your systems, and a key provider (such as Vault or a cloud KMS)
  for sensitive fields.

## Status

Design stage. There is no code yet: Ventoux is being built in Python, one layer at a time, starting
from the design documents below. Nothing here is ready to use.

## Read

- [`docs/BRIEF.md`](docs/BRIEF.md): what we are building and why, and every design decision so far.
- [`docs/QUICKSTART.md`](docs/QUICKSTART.md): a first case in 15 minutes, written before the code
  as the test of how easy Ventoux is to adopt.
- [`docs/guides/case-data.md`](docs/guides/case-data.md): what goes in a case file, and what doesn't.
- [`docs/CURRICULUM.md`](docs/CURRICULUM.md): the order the layers are built in.
- [`docs/README-draft.md`](docs/README-draft.md): the README this one will grow into. It still
  describes the TypeScript prototype.

## Develop

You need [uv](https://docs.astral.sh/uv/); it installs Python 3.12 if you don't have it.

```bash
uv sync                    # create .venv with Ventoux and the development tools
uv run pytest              # tests
uv run mypy                # strict type checking
uv run ruff check          # lint
uv run ruff format         # format (CI runs `ruff format --check`)
```

CI runs the same commands on every push and pull request. The code is split into the brief's
layers, under `src/ventoux/`:

| Package | What it holds | May import |
|---|---|---|
| `core` | schema, expressions, catalog, provenance, interpreter | nothing else in Ventoux |
| `case` | case runtime, rules, validation, migration | `core` |
| `temporal` | workflows, activities, worker, client | `core`, `case` |
| `authoring` | AI drafting and the step advisor | `core`, `case` |
| `tooling` | CLI, diff, business views, builder | anything |

`core` and `case` never import Temporal or an LLM SDK: they must run unchanged inside a Temporal
workflow, where replay needs the same decisions every time, and in a plain test. A test
(`tests/test_layers.py`) fails if they do. See [`docs/layers/`](docs/layers/) for the design note of
each layer.

## Background

Ventoux builds on [`chartering`](https://github.com/francoisnyc/chartering), a TypeScript prototype
used as a reference, and on ideas credited in the brief's prior art.

## License

[MIT](LICENSE)
