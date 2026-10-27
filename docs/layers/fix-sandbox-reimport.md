# Fix: a second builder, hung on `ventoux.tooling` by a sandbox

A fix, not a layer: no warm-up. Found in layer 14d, where the whole test suite made
`ventoux check` refuse a `Case` built through `from ventoux import Case`. 14d changed the
re-export to read the builder by name, and left the cause open. Recorded as D62 (brief).

## What was seen

`SANDBOX` (in `ventoux.temporal.worker`) passes `ventoux.tooling` through, and Temporal passes a
module's children through with it. Yet during `tests/test_temporal_forget.py` the builder's
`__init__` ran once at import time, then again for every test, each time from `ventoux.testing`'s
`from ventoux.tooling.builder.case import Case`, under the sandbox's importer. After that,
`ventoux.tooling.builder`, the package's attribute, was not `sys.modules["ventoux.tooling.builder"]`.

## The cause

Two sandboxes were at work, not one. Logging each condition of the sandbox's lazy passthrough
(`_ThreadLocalSysModules._lazily_passthrough_if_available`) showed it:

| Importer | Ventoux modules passed through | `ventoux.tooling.builder` |
|---|---|---|
| the case worker's, on `SANDBOX` | `ventoux.core`, `ventoux.case`, `ventoux.tooling` | passed through, once |
| the second worker's, on Temporal's default runner | none | imported afresh, every test |

The forget tests start a second worker, for `SignalsAnEndedCase`, with no `workflow_runner`.
Temporal then gives it its default runner, whose restrictions pass no Ventoux module through.
The workflow is defined in the test file, so that sandbox imports the test file afresh. The test
file imports `ventoux.testing`, which imports the builder.

What happens next, step by step:

1. `ventoux.testing` imports `ventoux.tooling.keys` inside `imports_passed_through()`, through
   the converter. So `ventoux.tooling`, the parent, is the host's package, shared.
2. `from ventoux.tooling.builder.case import Case` is not passed through: the default runner
   doesn't name `ventoux.tooling`, and the line is outside the block.
3. Python's own import machinery loads the parent `ventoux.tooling.builder` first. It calls
   `importlib._bootstrap._gcd_import` directly, not the sandbox's `__import__`, and asks the
   sandbox's `sys.modules`. That says "not loaded", correctly for this sandbox.
4. Having loaded the fresh builder, Python sets it as the `builder` attribute of its parent. The
   parent is the shared host package, so every later reader of the attribute gets the copy.

Changing only that worker to `SANDBOX` took the builder's runs in the forget tests from 24 to 1.

## The leads, checked

- **The lazy passthrough on the worker's thread.** It applies there: the worker validates and
  runs workflows on the thread that holds the importer, and the conditions held for `SANDBOX`.
  It refused only for the default runner, as it should.
- **CPython's C-level module dict.** Not involved. The parent import reads the Python-level
  `sys.modules`, which Temporal's override answers.
- **Should `ventoux.testing` import the builder at all?** On `SANDBOX` it costs nothing: the
  builder is passed through, never run in the sandbox, which keeps D58. Importing it lazily would
  fix this one module and move the development catalog's cases away from the workflows that
  serve them, so it was set aside.
- **The registry's worker** (`registry_worker`) used the default runner too. With the default
  registry it imports nothing of Ventoux afresh but its own module, which passes `case` through by
  hand. But it takes the registry's class, and the tests pass subclasses defined in a test file.
  A check after every test of the whole suite found the second door: after
  `test_the_registry_crosses_continue_as_new`, a second `ventoux.tooling.builder` and
  `ventoux.tooling.releases` hung on `ventoux.tooling`.

## Decided

1. **Every worker Ventoux builds runs on `SANDBOX`,** and so does any worker serving a module that
   imports Ventoux outside a passthrough block (D62). The forget tests' second worker and
   `registry_worker` now do. `SANDBOX` moved to `ventoux.temporal.sandbox`, its own file, since
   the registry can't import `worker.py`, which imports the registry.
2. **The re-export stays as 14d wrote it.** A deployment may still run its own worker on the
   default runner beside `ventoux.testing`. Ventoux can't prevent that, so `from ventoux import
   Case` keeps importing the builder by name.
3. **One small test helper, `tests/one_copy.py`,** lists each loaded Ventoux module whose package
   holds another module of that name. A package holding a function of the same name, such as
   `ventoux.core.expressions.check`, is not a copy. A test first puts back what earlier tests
   left, so it sees only its own run. Run after every test of the whole suite, it now finds
   nothing.

## Promises

| Promise | Test that fails if it isn't true |
|---|---|
| The forget tests' workers load no second copy of any Ventoux module | `test_the_workers_here_load_no_second_copy_of_ventoux` (forget); failed on `main` with `ventoux.tooling.builder` |
| A registry defined in a module that imports Ventoux loads no second copy of any Ventoux module | `test_the_registry_worker_loads_no_second_copy_of_ventoux` (registry); failed with `ventoux.tooling.builder` and `ventoux.tooling.releases` before `registry_worker` used `SANDBOX` |
| `from ventoux import Case` gives the builder's own class, whatever the package's attribute holds | `test_the_re_export_gives_the_builders_own_class_whatever_the_package_attribute_holds` (layers) |
