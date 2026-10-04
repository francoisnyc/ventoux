# Project context for coding agents

This repository builds Ventoux layer by layer, as a teaching project. Read `docs/BRIEF.md` (what we
are building and why) and `docs/CURRICULUM.md` (the layers, in order) before doing anything else.

## Teaching mode (how to work here)

- **One layer at a time.** Work only on the layer the user names. Never start the next layer, and
  never build ahead "because it will be needed".
- **Warm up first.** Start every layer with one earlier check-yourself question from
  `docs/LEARNING.md`, answered from memory before anything else (an open one first; otherwise one
  closed at least two layers ago). Discuss the answer and record it in the log.
- **Explain before building.** Start each layer by explaining the concept and the design choice with
  a small example, then agree a short design note in `docs/layers/NN-name.md` with the user.
- **Test first, one slice at a time.** Agree the seams (public interfaces) the tests will use with
  the user. Then loop: one failing test (the negative test first), shown failing for the right
  reason → the least code that passes it → the next test. Never write all the tests up front, and
  never test internals. Build only what the layer's "Build" line needs; prefer fewer files and plain
  code over abstractions.
- **Walk through after building.** Explain the code you wrote, file by file, and answer questions.
  End by asking the layer's "Check yourself" questions.
- **Stop and wait** after each step above for the user to confirm. Don't chain steps silently.
- **Tracer code is temporary.** Code marked `# TRACER:` is a crude stand-in from the tracer bullet;
  replace it in the layer it names, and never build on it. The quickstart's acceptance tests must
  stay green in every layer.
- **One layer per pull request.** Small commits with clear messages inside it.
- **Ask before adding a dependency.** Say what it is for and what the alternative is.

## Reference implementation

The `chartering` repository is the prototype, written in TypeScript. Read it to understand an idea,
and say which file you are drawing on. Don't translate it line by line: rebuild each part
deliberately in Python, smaller and clearer.

## Non-negotiables

- Definitions (plans and case definitions) are data. Never `eval`, `exec`, `compile`, `importlib` or
  `pickle` anything from them.
- Expressions are structured JSON using only the operators listed in decision D3, evaluated as pure
  functions of the case file. No operator reads the clock, randomness or I/O. Reject anything else
  at validation; at runtime a missing field, a wrong type or an unknown operator is an error. Adding
  an operator is a design decision recorded in the brief, never just a code change.
- Every side effect goes through a registered activity. Definitions reference capabilities; they
  never define them.
- The interpreter is deterministic so it can run as a Temporal workflow and survive replay: no clock,
  randomness or I/O in `core` or `case`.
- Every value carries provenance tags; sink policies are checked before an activity is scheduled.
- Anything that talks to people drafts by default; it never sends on its own.
- Policies can be made stricter downstream, never looser (a case tightening a contract, untrusted
  data adding an approval, a view hiding more than its source).
- Nothing is skipped automatically: a failed step waits for a person.
- Fail closed: anything the engine can't evaluate or doesn't recognise is an error, never a
  permissive default ("false", "not needed", "no approval"). Every evaluator has a negative test
  for an input it doesn't know.

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
