# Project context for coding agents

This repository builds Ventoux layer by layer, as a teaching project. Read `docs/BRIEF.md` (what we
are building and why) and `docs/CURRICULUM.md` (the layers, in order) before doing anything else.

## Teaching mode (how to work here)

- **One layer at a time.** Work only on the layer the user names. Never start the next layer, and
  never build ahead "because it will be needed".
- **Explain before building.** Start each layer by explaining the concept and the design choice with
  a small example, then agree a short design note in `docs/layers/NN-name.md` with the user.
- **Build the smallest slice** that meets the layer's "Build" line. Prefer fewer files and plain code
  over abstractions.
- **Walk through after building.** Explain the code you wrote, file by file, and answer questions.
  End by asking the layer's "Check yourself" questions.
- **Stop and wait** after each step above for the user to confirm. Don't chain steps silently.
- **One layer per pull request.** Small commits with clear messages inside it.
- **Ask before adding a dependency.** Say what it is for and what the alternative is.

## Reference implementation

The `chartering` repository is the prototype, written in TypeScript. Read it to understand an idea,
and say which file you are drawing on. Don't translate it line by line: rebuild each part
deliberately in Python, smaller and clearer.

## Non-negotiables

- Definitions (plans and case definitions) are data. Never `eval`, `exec`, `compile`, `importlib` or
  `pickle` anything from them.
- Expressions use the JSONata subset in decision D3, evaluated as pure functions of context. Reject
  anything outside it, including non-deterministic functions (`$now`, `$millis`, `$random`, `$uuid`),
  at validation.
- Every side effect goes through a registered activity. Definitions reference capabilities; they
  never define them.
- The interpreter is deterministic so it can run as a Temporal workflow and survive replay: no clock,
  randomness or I/O in `core` or `case`.
- Every value carries provenance tags; sink policies are checked before an activity is scheduled.
- Anything that talks to people drafts by default; it never sends on its own.
- Policies can be made stricter downstream, never looser (a case tightening a contract, untrusted
  data adding an approval, a view hiding more than its source).
- Nothing is skipped automatically: a failed step waits for a person.

## Conventions

- Python 3.12+, managed with `uv`. Schemas with Pydantic (v2); the definition format is also
  published as JSON Schema generated from it. Tests with pytest. Lint and format with ruff. Strict
  type checking (pyright or mypy in strict mode) on all code.
- Keep `ventoux.core` and `ventoux.case` free of Temporal and LLM dependencies; adapters live in
  `ventoux.temporal` and `ventoux.authoring`.
- Every feature lands with tests, including at least one negative test (a definition that must be
  rejected).
- Run the tests, the type checker and ruff before declaring a step done.
- Write for a reader learning the system: short functions, names from the brief's glossary, a comment
  where a design rule is enforced.
