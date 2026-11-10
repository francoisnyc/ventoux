# Releasing Ventoux

This is the maintainer's procedure for releasing the `ventoux` package (brief, D82). CI builds the
wheel and checks it on every push, and never publishes. **The tag and the publish are the
maintainer's,** never CI's, and nothing in the repository does either on its own.

## What a release is

- **One version, written once:** `version = "…"` under `[project]` in `pyproject.toml`. `ventoux
  version` reads it from the installed package's metadata, so the two can't differ. Semantic
  versioning, `0.y.z` until v1.0.
- **Three versions, each its own:** the package's, the engine version new cases open at (brief,
  D51) and the schema's `$id` (brief, D60). A release that changes the engine version or the
  schema says so in its changelog entry.
- **What the wheel holds:** the code, `py.typed`, the licence, the two JSON Schemas
  (`ventoux/schema/`), the conformance suite (`ventoux/conformance/`) and `ventoux/public.json`,
  the supported imports. Never the repository's tests, examples, docs or scripts, a key, a
  certificate or a recording. `scripts/check_wheel.py` checks both.

## The steps

1. **Bump the version** in `pyproject.toml` (`version = "0.2.0"`), and run `uv lock`, which
   records it in `uv.lock`.
2. **Write the changelog entry:** a `## 0.2.0` section at the top of `CHANGELOG.md`, saying what
   changed for a team: new features, anything removed from `public.json` (a decision, as a
   contract change is), and a changed engine version or schema.
3. **Open a pull request** with both, and see CI green on it, the `package` job included: it runs
   `uv build`, checks the wheel, installs it into a fresh environment and runs `ventoux version`,
   `ventoux schema --unchanged` and `ventoux conformance --unchanged` from outside the repository.
   A wheel that works only inside the repository fails there.
4. **Merge,** and on `main`, at the merge commit:

   ```
   git tag v0.2.0
   git push origin v0.2.0
   ```

5. **Build and publish** from that tag, from a clean checkout:

   ```
   uv build
   python scripts/check_wheel.py dist/ventoux-0.2.0-py3-none-any.whl
   uv publish
   ```

   `uv publish` reads its token from the environment (`UV_PUBLISH_TOKEN`), or uses PyPI's trusted
   publishing; never write the token into a file or a command line.

## Before raising a dependency's bound

A contract's hash is made from pydantic's JSON Schema of its models, and a new minor version of
pydantic can write that schema differently (2.14 does, for a decimal field). So the package stays
below the next minor (`pydantic>=2.13.5,<2.14`) until the hash no longer depends on it. Raising
the bound is a release of its own: run `ventoux hashes` against the lock and `ventoux conformance
--unchanged` under the new version first; a changed hash refuses every worker serving that
contract (brief, D54).
