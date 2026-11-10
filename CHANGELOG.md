# Changelog

What changes for a team using the `ventoux` package, release by release. The procedure is in
`docs/guides/releasing-ventoux.md`.

## 0.1.0 (not yet released)

The first release: case definitions and plans as data, the engine on Temporal, the builder, the
command line (`ventoux check`, `simulate`, `release`, `doctor`, `version` and the others), the
JSON Schemas and the conformance suite. Engine version 3; schemas
`https://ventoux.dev/schema/engine-3/`. The supported imports are listed in `ventoux/public.json`.
pydantic is bounded below 2.14, since contracts hash from its JSON Schema.
