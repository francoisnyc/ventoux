# Layer 20: Deployment and the published package

Status: 2026-11-08, questions answered; 20a being built. This note starts from `main` at `cd6e24f`, with
layers 0 to 19 merged. The warm-up was asked and recorded (learning question 9). The guide was
written first (curriculum step 2): `docs/guides/deployment.md` describes the layer as if it
worked, following the recommendations below, each place marked *(open: question N)*; it changes
with the answers.

**Answered 2026-11-08: A, B and 1 to 9 as recommended; 5a `ventoux`; 5b `0.1.0`.** D79 (the
trusted caller, with dated amendments under D19 and "Out of scope for v1.0") and D80 (the
conformance suite, with a dated amendment under D4) are written before 20a is built; D81 before
20b, D82 before 20c. `README.md` and `README-draft.md` follow D79. The branch is renamed
`layer-20a-conformance`.

Prior art: none in the prototype (the curriculum names none).

## Warm-up: learning question 9, D4 and the Python engine

Asked to be told. Given, and recorded in the log: each activity declares the same contract
(`name@version`, input and output models as JSON Schema, an input policy per input field, a
source per output field, `risk`, `effect`, `idempotency_key`, timeouts and retries, declared
outcomes, a display outside the hash), filled in differently; never the task queue, which is the
binding's. The Java developer reads the contract and the definition, never the engine; what the
schema can't tell them is whether a definition is *valid*, which is what this layer's conformance
suite publishes. Kept open until the contents of a contract come back from memory.

## What this layer is for

**What a deployment must lock down.** The engine believes the identity its caller states (D19,
D22): whoever can signal a case can answer as anyone. Nothing in the engine can see that; only
Temporal's mTLS and authorization can enforce it. Some of Ventoux's promises are therefore the
deployment's, not the code's.

**Checking a deployment, not only describing it.** A guide is read once; a deployment drifts (a
certificate reissued wider, a group given write "for a day", a token's policy widened, a worker
deployed with the development catalog). `ventoux doctor` checks what can be seen from outside,
with three verdicts: passed, failed, and *unchecked*, never passed for a rule it couldn't see.

**A conformance suite as the contract other implementations meet.** The schema says what a
definition looks like (D60); the suite says what the engine decides about it, as data: a
definition, its catalog, and the issues it must give. CI runs it, so a change to validation that
alters a result fails until the suite changes with it, on purpose.

**The published package:** a name, a version, what the wheel holds, what may be imported, and how
a release is built. Prepared here; publishing it and pushing its tag are the maintainer's.

## What the brief already settles

Not asked again:

- **The trusted caller, locked down** (D19): mTLS and Temporal's authorization; people read only;
  "the deployment guide says so, and `ventoux doctor` checks what it can". Signed approvals are
  after v1.0.
- **Admin access stays powerful, so small and audited** (D19); resets restricted, since re-running
  a payment step makes a new step run and a new idempotency key (D17).
- **Who answered, and their roles, are stated by the caller,** never looked up by the engine;
  identifiers normalised by the caller, refused otherwise at the answer (D22).
- **The schema:** two files, generated from the parser's models, checked unchanged in CI, named by
  engine version in `$id`; shape only, never a trust boundary (D60).
- **The conformance suite exists to check any implementation,** the prototype included (D4).
- **Activation and environments** (D54): manifests before polling, one registry per environment,
  `create`, `harden` (development to production, never back), `environment check` exiting 1 for
  monitoring. Doctor adds to these, never replaces them.
- **The deployment's catalog is named in configuration, never guessed** (D59); the development
  catalog only when named.
- **Providers behind optional extras; a secret from one environment variable, never logged or
  said, failures by the setting's name, never its value** (D62); the same for `VAULT_TOKEN` (D78).
- **Workers serving Ventoux modules run on `SANDBOX`** (D65).
- **The audit store is the platform team's;** its rows are admin access; a terminated case's
  unwritten records are a known limit (D77). **Vault's settings and policy** are D78's.

## What I checked in the code before asking

- **No command can reach a locked-down namespace.** `tooling/environments.py` connects with
  `Client.connect(arguments.address, namespace=…)`: no TLS, no client certificate. Under D19's
  production setup, `ventoux activate`, `retire`, `environment` and `manifest publish` would all
  be refused by Temporal. Doctor needs identities to connect as; so do they.
- **Workers write too.** D19 says "only the API's service identity can write". A worker polls and
  completes tasks, and `environment_worker` publishes its manifest by an Update; operators activate
  and terminate. The rule that holds is narrower: people read only; the caller, the workers and
  named operators write, each its own kind of call.
- **What a worker runs with is invisible from outside.** Keys reach a worker through its client's
  converter (`data_converter(keys)`), the audit store as an argument to `case_worker`. The
  manifest (`case/activation.py`, `Manifest`) says neither: a production worker built with
  `FileKeys` (keys in a file, so forgetting destroys nothing anyone can trust) is
  indistinguishable from one with Vault.
- **The catalog is code; the suite must be data.** A `Contract` holds Pydantic model classes,
  and its input policies are field metadata. But `ventoux promises` already writes each contract
  as plain JSON (`core/promise.py`: everything but `display`, schemas as JSON Schema with
  `x-source`, `x-reference` and the policies). Roles, systems, labels, option checks and document
  stores are not in it.
- **Validation gives what the suite compares:** `Issue(path, code, message, severity)`
  (`core/validate.py`); about sixty codes, written as literals where each check is made, with no
  list of them. A definition refused at *reading* (`parse_case`, Pydantic) gives a path and no
  code.
- **The schema corpus test is the seed** (`tests/test_schema.py`): every committed definition is
  accepted by the schema and the parser, and a fixed set of wrong shapes is refused by both.
  `examples/witnesses/` holds stories with what must happen: a seed for run results, if wanted.
- **The package:** `ventoux` 0.0.0, MIT, `py.typed` present, one extra (`anthropic`), `uv_build`.
  `schema/` sits at the repository's root, outside `src/ventoux/`, so a wheel built today doesn't
  hold it. Nothing says which modules are supported to import. `README.md` (and `README-draft.md`)
  still say Ventoux adds "one small API service with a reference inbox".
- **The dev server can show doctor failing, never passing, on Temporal's rules.** The test
  environment (`WorkflowEnvironment.start_local`, Temporal's dev server) has no TLS and no
  authorizer: a connection without a certificate is accepted, and any write is allowed. So
  doctor's negative tests can run against a real server; its *passed* branches need a recorded or
  fake transport, as `VaultKeys`'s tests do.
- **One assumption to confirm before 20b:** that Temporal's frontend checks authorization before
  it looks for the workflow, so a signal to an ID that can't exist answers `PermissionDenied` to an
  identity without write and "not found" to one with it. It is how the frontend's interceptor
  chain is built, read from Temporal's server documentation; no CI here runs an authorizer to
  prove it.

## The split

| PR | What it builds | Its negative test |
|---|---|---|
| **20a: the conformance suite** | The suite as data (definitions, catalogs, expected issues); the catalog exported as data from the Python catalog, checked unchanged; the runner in CI, each entry both ways; changes to a result recorded. This note, the guide and the warm-up ride in it. | **curriculum:** a change to validation that alters a result fails CI. Also: an entry expecting a refusal that validation passes fails; an expected issue missing or an extra one fails. |
| **20b: connecting as an identity, and `ventoux doctor`** | `[tool.ventoux.temporal]`: address, namespace, server CA, identities by file path, used by every command that talks to Temporal; doctor's rules (configuration and live), three verdicts, exit codes; the manifest saying what a worker runs with, if question 7 says so; D19 amended. | **curriculum:** doctor fails on a deployment that breaks a rule it checks, naming the rule (against the dev server: no mTLS, a reader that can write). Also: a rule it can't check said unchecked, never passed; no secret's value in its output. |
| **20c: the published package** | Name, version scheme, the wheel's contents (code, `py.typed`, schemas, suite), the supported imports locked by a test, `ventoux version`, a CI job building the wheel and running the suite against it installed; the release procedure written. Never published. | A wheel missing the schemas or the suite, or holding a file it mustn't (tests, examples, keys), fails; a supported name removed fails. |

**Why this order.** 20a is pure and fast (no Temporal), and 20c ships what it makes. 20b is the
largest and touches every Temporal command; it doesn't depend on 20a. 20c last, since the wheel
holds 20a's suite and 20b's commands.

## Design questions for you

Each answer becomes a decision in the brief, from D79 on, added and never rewriting an earlier one.
A correction to a merged decision is a dated amendment under it.

### For the whole layer

**A. The split:** 20a, 20b, 20c as above, one pull request each, on `layer-20a-conformance`,
`layer-20b-doctor`, `layer-20c-package`. The current branch, `layer-20a-deployment`, is renamed.
*Recommended.*

**B. The decisions:** D79 the trusted caller (question 1, with a dated amendment under D19 and
under "Out of scope for v1.0" if (c) is chosen); D80 the conformance suite (20a, with an
amendment under D4 if run histories are deferred); D81 connecting and doctor (20b, with an
amendment under D54 if question 7 changes the manifest); D82 the published package (20c). Each
written before its part is built. *Recommended.*

### 1. The trusted caller

D19 makes the Ventoux API the engine's only caller, and "Out of scope for v1.0" says v1.0 ships
the API and a reference inbox. Neither exists, and no layer builds them. What every part of D19
needs is *one identity that writes on behalf of people*; which program holds it is the question.

- **(a) Build the API in this layer.** An HTTP service (a framework dependency: Starlette or
  FastAPI), people's sign-in (OIDC), roles from the identity provider, and the reference inbox
  in TypeScript (D4). A layer's worth of work on its own, twice this one, and the inbox is a
  second language. Doctor would check the same rules either way.
- **(b) Add a layer for it,** "the API and the reference inbox", before 21 or after it, keeping
  v1.0's promise. This layer writes doctor and the guide for "the caller identity", which hold for
  the API unchanged. Cost: v1.0 is a layer further away; the curriculum and brief gain a layer.
- **(c) In v1.0 the caller is the integrator's own service,** calling Ventoux's client functions
  (`start_case`, `answer`, `close`, `propose_change`, … in `ventoux.temporal.cases`), which exist
  and are tested. D19 amended: the trusted caller is whatever service holds the caller identity;
  the guide states what it must do (authenticate people, normalise identifiers as D22 says, take
  roles from its identity provider, never let a person name who answered). The API and inbox move
  to "Beyond v1.0", and "Out of scope", `README.md` and `README-draft.md` are amended to say so.
  Cost: each integrator writes the caller and owns getting D22 right; v1.0's promise shrinks.

*Recommended: (c).* The engine's guarantees don't depend on which program is the caller, only on
there being one writer that states people truthfully, and that is what doctor can check. The
client functions are already the caller's surface. An HTTP service and an inbox are a product of
their own, with dependencies and a second language; building them in passing would be building
ahead. If you want v1.0 to keep the API, (b), placed after 21, keeps this layer the same size.

**1b. D19's wording.** Whatever 1 says, amend D19 (dated) to the rule that holds: people read only;
the caller writes on behalf of people; workers write only their own task completions and
manifests; named operators activate, terminate and reset. *Recommended.*

### 2. Connecting as an identity

- **2a.** `[tool.ventoux.temporal]` in `pyproject.toml`: `address`, `namespace`, `server_ca`
  (optional, for a private CA), and named identities, each `cert` and `key` as **file paths**,
  never contents. Every command that talks to Temporal reads it; `--address` and `--namespace`
  still win; `--identity NAME` chooses one, `operator` by default for the environment commands.
  With no `[tool.ventoux.temporal]`, the commands connect as today (localhost, no TLS), so
  development is unchanged. *Recommended.*
- **2b.** mTLS only in v1.0. Temporal Cloud's API keys would be a second way to authenticate, read
  from an environment variable as D62 does; left for later. *Recommended.*
- **2c.** Doctor never holds the caller's key. Checking that the caller *can* write proves nothing
  about safety, and an identity able to write as the caller is the thing D19 guards; doctor needs
  only a reader's identity, to see it refused. *Recommended.*

### 3. What `ventoux doctor` checks, and how

Both configuration and the live deployment, with the rights it is given and no more. Each rule
named `area.rule`, each line saying what it saw and, on a failure, what to do.

| Rule | How | Verdict when it can't run |
|---|---|---|
| `catalog.named` | the configuration names a catalog, and not `ventoux.testing:CATALOG` | — (it can always read the file) |
| `temporal.identities` | each configured identity's files exist; the key file is readable by its owner only; the certificate hasn't expired (read with `cryptography`, a dependency already) | unchecked when none is configured |
| `temporal.mtls-required` | a connection with no client certificate is refused | unchecked if Temporal can't be reached at all |
| `temporal.reader-cannot-write` | as `reader`, a signal to `ventoux-doctor/<random-free ID>`: `PermissionDenied` passes, "not found" fails (the write was allowed, nothing changed) | unchecked with no `reader` identity |
| `environment.exists-production` | the registry answers its query, and is production | unchecked if the registry can't be queried |
| `environment.workers` | `environment_check`, as `ventoux environment check` runs it | as above |
| `environment.production-providers` | every case worker's manifest names a key provider and audit store that aren't development ones (question 7) | unchecked if manifests don't say |
| `keys.token-present` | `VAULT_TOKEN` is set (never read out) | — |
| `keys.reachable` | the key service answers a read of a key that can't exist with "never made" | unchecked with no key provider named |
| `keys.policy` | Vault's `sys/capabilities-self`: no `delete` on a mark's metadata; `deny` on a key not named `ventoux-*`; `update` on encrypt and decrypt of `ventoux-*` | as above |
| `advisor.key-present` | `ANTHROPIC_API_KEY` set, only when a `model` is configured | — |
| `temporal.only-caller-writes`, `temporal.resets-restricted`, `audit.no-deletes`, `temporal.retention` | can't be seen from a client | always unchecked, naming the guide's section |

- **3a. The list above.** Add, drop or reword rules. *Recommended as it stands.*
- **3b. How doctor learns the key service.** The key provider is constructed in the workers' code.
  Name it as the catalog is (D59): `[tool.ventoux] keys = "module:NAME"`, imported by that name,
  never from a definition; doctor checks the object it gets (a `VaultKeys`: its address `https`,
  the policy, reachable; `FileKeys`: failed in production). Likewise `audit = "module:NAME"`,
  checked only to be named and not `FileAudit`. *Recommended.* The alternative is flags on the
  command line each time.
- **3c. Verdicts and exit codes:** `passed`, `FAILED`, `unchecked`; exit 0 when nothing failed,
  1 when a rule failed, 2 when doctor couldn't run at all (no configuration it can read).
  `unchecked` lines are printed every time and don't fail the command; `--strict` makes them
  fail. *Recommended.* The alternative, `unchecked` always failing, makes doctor fail for ever on
  rules nobody can check, and a command that always fails is one people stop reading.
- **3d. Relation to D54's commands.** One command to check a deployment: doctor runs
  `environment_check` as its `environment.workers` rule, from the same function, so they can't
  disagree; `ventoux environment check` stays, for monitoring that already calls it. `harden` is
  an act, never a check: doctor never hardens, and fails `environment.exists-production` on a
  development environment, saying `ventoux environment harden NAME --by …` is the fix.
  *Recommended.*
- **3e. A check never drops an issue it found.** Every rule runs, whatever the others say; one
  that raises something unexpected is said `unchecked` with the error's type, never dropped and
  never passed. *Recommended* (and each branch tested).
- **3f. Without changing anything.** Every probe is one that does no harm if allowed (a signal to
  an ID that can't exist; Vault's capabilities asked, never used). Doctor never starts a workflow,
  writes to the registry, makes a key or appends to the audit store. *Recommended.*

### 4. The conformance suite

- **4a. What it holds.** D4 says definitions, expected validation results and run histories; the
  curriculum says definitions with their expected validation results.
  - (i) **Validation only,** with a dated amendment under D4: run results after v1.0, seeded by
    `examples/witnesses/` when they come. *Recommended:* a run's history is Temporal's format and
    the engine version's, and another implementation of *validation* (an inbox, a Java builder)
    is the one v1.0 needs.
  - (ii) Also stories with what must happen (`ventoux simulate`'s format, data already).
- **4b. Its format,** JSON, in `conformance/`:
  - `suite.json`: `{"engine": 3, "entries": [...]}`; each entry `name`, `kind` (`case` or `plan`),
    `definition` (a file), `catalog` (a file), `plans` and `cases` supplied (files, by reference),
    and `expected`: either `{"read": "refused", "at": ["steps.review.automatic"]}` (refused when
    read, by path alone, since reading gives no code) or `{"issues": [{"path", "code",
    "severity"}]}` (an empty list: valid).
  - Compared as a multiset of `(path, code, severity)`: in any order, none missing, none extra.
    Messages are wording and never compared. Warnings are compared too.
  *Recommended.*
- **4c. The catalog as data.** (i) The Python catalog is the source, and its JSON is generated
  (`ventoux conformance --write`), checked unchanged in CI as the schema is: contracts as
  `ventoux promises` writes them, plus roles (with what each may approve and operate), systems,
  labels, option checks and document stores. (ii) The JSON is the source, and Python builds
  contracts from it: Pydantic models made from JSON Schema at runtime, input policies rebuilt from
  their JSON; much more code, and a second way to make a contract. *Recommended: (i).*
- **4d. Which catalogs and entries.** One catalog, the development one (`ventoux.testing`), which
  the examples already use. Entries: every committed definition (each valid, as the corpus test
  reads them), the corpus test's wrong shapes, and at least one refusing entry per issue code.
  For "per code" to be checkable, the codes become a list (`ISSUE_CODES`, in `core/validate.py`),
  and a test fails when validation gives a code not in it or the suite lacks an entry for one.
  *Recommended.* The alternative, no list, leaves "every code is covered" a promise without a test.
- **4e. How CI fails, and how a change on purpose is recorded.** The runner is a pytest test, an
  entry per case, run both ways (a definition that must validate does; one that must be refused
  is, with the issues expected). A change to validation that alters a result fails it. A result
  changed on purpose changes the entry's `expected` in the same pull request **and** adds a line to
  the suite's `changes` list (`{"entry", "was", "now", "why", "date"}`); CI compares the suite
  with the base branch's, as it does for `ventoux promises`, and fails a changed `expected` with
  no `changes` line naming it. *Recommended.* The simpler alternative, the pull request's diff as
  the only record, leaves nothing for an implementer reading the suite later.
- **4f. Where it lives.** In the package, so it ships in the wheel (question 5c), and is written
  out by `ventoux conformance --export DIR` for an implementer who doesn't install Python.

### 5. The published package

- **5a. Name:** `ventoux` on PyPI, as `pyproject.toml` says. Whether it is free there is yours to
  check; nothing here reaches PyPI. *Ask.*
- **5b. Version scheme.** The package's version is its own, apart from the engine version (D51)
  and the schema's `$id` (D60); `ventoux version` says all three. Semantic versioning: `0.y.z`
  until v1.0 (after layer 21), `1.0.0` then. This layer prepares the first release, `0.20.0` (the
  layer it was built in) or `0.1.0` (the first one published). *Ask which; recommended 0.1.0*, since
  a version number promising a layer count would read as twenty releases.
- **5c. What the wheel holds:** the code, `py.typed`, the two schemas and the conformance suite as
  package data. Both move under `src/ventoux/` (`src/ventoux/schema/`,
  `src/ventoux/conformance/`), since a wheel holds only the package; the schemas' `$id` is
  unchanged, `ventoux schema --unchanged` reads the new place, and `schema/` at the root goes (or
  stays as a copy checked equal: *recommended: goes*, one place). Never: `tests/`, `examples/`,
  `docs/`, a key file, a recording with a token. `ventoux.testing` stays in the wheel: teams'
  tests use it; the guide says it is for tests.
- **5d. Extras:** `anthropic` only, unchanged. Vault needs none. *Recommended.*
- **5e. The public surface.** Supported to import: `ventoux` (the builder), `ventoux.testing`,
  and named functions of `ventoux.temporal.worker`, `.cases`, `.client`, `.converter`, `.registry`,
  `.manifests`, `.forget`, `ventoux.tooling.vault`, and the protocols a deployment implements
  (`KeyProvider`, `AuditStore`). Everything else is internal: importable, unsupported, free to
  change. Recorded in the guide and in a committed list (`public.json`), and a test fails when a
  listed name disappears (a removal is then a decision, as a contract change is). No renaming of
  internals with underscores. *Recommended;* the exact list is proposed in 20c's seams.
- **5f. How a release is built:** `uv build`, then a CI job installs the wheel in a fresh
  environment and runs `ventoux version`, `ventoux schema --unchanged` against the installed
  schemas, and the conformance suite from the installed package. The procedure (bump, changelog,
  tag, publish) is written in `docs/guides/releasing-ventoux.md`; the tag and the publish are the
  maintainer's, never this layer's. No new dependency (no `twine`). *Recommended.*

### 6. What the guide states, and what doctor checks

The guide's "What only this guide can state" and doctor's always-unchecked rules are one list,
kept equal by a test (each unchecked rule names a guide section that exists): no identity but
the caller, workers and operators writes; resets and terminations are a named group's, logged by
Temporal; the audit store deletes nothing; Vault's other tokens; retention. *Recommended.*

### 7. Should a worker's manifest say what it runs with?

- (i) **Doctor only:** the manifest gains `keys` and `audit`, each the provider's kind
  (`development` or `production`, from a class attribute that `FileKeys` and `FileAudit` set,
  never their settings); doctor fails `environment.production-providers` on a development one.
- (ii) **The registry refuses too:** in a production environment, a manifest naming a development
  provider is refused, so the worker never polls (D54's pattern: refused before it starts).
- (iii) Neither: the rule stays unchecked, the guide states it.

*Recommended: (ii).* A production worker with `FileKeys` makes forgetting meaningless and the audit
export unsealed by any key service; refusing it at start is what activation already does for a
wrong contract hash. A manifest from an earlier worker, or from another language, without the
fields, is said unchecked by doctor and accepted by the registry only for a non-case worker (a
case worker must say). Cost: an amendment under D54 and a manifest field.

### 8. Secrets in deployment

`VAULT_TOKEN`, `ANTHROPIC_API_KEY` and Temporal's client keys: never in a file the package ships
(the wheel test refuses `*.key`, `*.pem` and `keys.json`), never in configuration (paths only),
never logged or said. Doctor checks presence and file permissions, never values; a test sets each
to a known value and asserts doctor's whole output, failures included, never holds it.
*Recommended.*

### 9. The items carried from 18c and 18d

- **18d: a parent terminated with a child running, then forgotten.** Finding the family needs
  Temporal's visibility queries; it is admin access (a termination) by nature. *Recommended: out of
  scope, as D77's known limit;* the guide's "Resets and terminations" says what an operator does
  (list `WorkflowId STARTS_WITH "claim-7/"` in Temporal's UI, terminate them before forgetting).
  No doctor rule: it is about one case, not the deployment.
- **18c's three:** a child's conditions and rules read with the sources its parent gives; whether
  a person answering a wait inside a plan is excluded from what the plan's outcome decides; the
  diff's `excluded` reading through a child's report. Each changes validation, so each would change
  a conformance result. *Recommended: out of scope here,* carried on as said, each a decision when
  it comes; the suite records whatever they change when they do.

## Seams and tests for 20a (curriculum step 4, proposed)

**What an entry is.** The one check (`issues_of`, `case/checked.py`, D50) reads a *package*: a
case, its plans and its child cases. So an entry is a package or a plan alone, and the runner
gives it exactly what `ventoux check` and `ventoux release` refuse on, never a second set of rules:

```json
{ "name": "a condition reads a field the case doesn't declare",
  "kind": "package",
  "case": "cases/unknown-field.json",
  "plans": ["plans/refund-order.json"],
  "cases": {},
  "catalog": "development",
  "expected": { "issues": [{ "path": "steps.pay.when", "code": "UNKNOWN_FIELD", "severity": "error" }] } }
```

A plan entry has `"kind": "plan"` and `"plan": "plans/…"`. `"catalog"` names a file,
`catalogs/development.json`. A definition refused when read gives `{"read": "refused", "at":
[paths]}`: the paths `parse_case` or `parse_plan` refuse, case and plans each read on its own
first. A package that reads but can't be put together (a plan named twice, a plan step's plan
missing) is a broken entry, said as one, never a result: those refusals have no path or code.

**The seams the tests use:**

| Seam | What it is |
|---|---|
| `ventoux.core.validate.ISSUE_CODES` | every code validation can give, a `frozenset[str]` |
| `CaseInvalid.paths`, `PlanInvalid.paths` | the paths of the problems, as their lines say them, so a read refusal is compared without reading its wording |
| `ventoux.tooling.conformance.SUITE` | the suite's folder in the package |
| `catalog_data(catalog)` | the catalog as data: contracts as `ventoux promises` writes them, roles, systems, labels, option checks, document stores |
| `given(entry, folder)` | what this engine gives for one entry: the issues, or the paths refused when read |
| `mismatches(folder)` | every problem with a suite, each a line naming the entry and both sides; empty means this engine conforms. Also: a code given that `ISSUE_CODES` doesn't list, a listed code no entry expects, a file an entry names that isn't there, a catalog file not as generated |
| `unrecorded(base, head)` | each result changed or removed between two `suite.json`s with no `changes` line naming it |
| `ventoux conformance --write` | writes the catalog files only, never an `expected`: those are written by a person |
| `ventoux conformance --unchanged` | exit 1 and every mismatch, or 0 |
| `ventoux conformance --since BASE` | exit 1 on each change `unrecorded` finds against the base's `suite.json` |
| `ventoux conformance --export DIR` | the suite's files, as the package holds them |

The catalog an entry names is mapped to Python's catalog in the runner (`development` is
`ventoux.testing:CATALOG`), never named by the suite: the data says nothing about Python.

**The tests, in the order they would be written** (each watched failing first):

1. **Negative first:** a suite in a temporary folder whose entry expects `UNKNOWN_FIELD` where the
   definition is valid: `mismatches` names the entry, what it expected and that it was given none.
2. Both ways: an entry expected valid whose definition gives an issue is a mismatch; an extra
   issue and a missing one are each said; the order of issues and their messages change nothing.
3. A read refusal, both ways: expected refused and read fine; expected at one path and refused at
   another.
4. **The committed suite conforms,** one test per entry (`given` against `expected`), so a failure
   names its entry; and `mismatches(SUITE)` is empty as a whole.
5. **The curriculum's negative test:** a copy of the committed suite with one result changed makes
   `ventoux conformance --unchanged` exit 1 naming it; and CI runs `ventoux conformance
   --unchanged` in its `check` job. A change to validation is the same mismatch seen from the
   other side.
6. `ISSUE_CODES`, both ways: a code given that isn't listed is a mismatch; a listed code no entry
   expects is one.
7. The catalog: `--write` writes it; `--unchanged` fails when the file differs from what
   `catalog_data` gives, naming the file and the first line that differs, and writes nothing.
8. `unrecorded`: a changed result with no line, said; with a line naming it, nothing; a new entry,
   nothing; a removed entry, said. CI's `changes` job runs `--since` against the base.
9. Every committed definition (the schema corpus's list) is an entry, its file equal.
10. The guide's example entry runs (docs/guides/deployment.md), as written there.
11. `--export` writes every file of the suite, byte for byte, and nothing else.

**Files:** `src/ventoux/conformance/` (data: `suite.json`, `catalogs/`, `cases/`, `plans/`);
`src/ventoux/tooling/conformance.py`; the command in `cli.py`; `tests/test_conformance.py`; two
lines in `ci.yml`. **Size, said now:** about sixty refusing entries (one per code at least, each
a small definition written by hand), the committed examples, and the schema corpus's wrong shapes.
