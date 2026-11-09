# Running Ventoux in production

For the platform team: what a production deployment of Ventoux is made of, what it must lock
down, and how `ventoux doctor` checks it. The other guides say what each part does; this one says
how they are put together, and which of the deployment's promises hold only because you keep them.

> Written first (layer 20, step 2) and changed with the answers in `docs/layers/20-deployment.md`;
> each section is true once the part that builds it (20a, 20b, 20c) is merged.

## What you deploy

Ventoux adds no server of its own to Temporal. A production deployment is:

| Part | What it is | Who runs it |
|---|---|---|
| **Temporal** | your namespace, self-hosted or Temporal Cloud; cases are its workflows | you, as today |
| **The trusted caller** | your service: the one that starts cases and sends every answer, stating who answered and their roles (D19, D22, D79) | you |
| **Case workers** | your processes running `environment_worker`, with your catalog's activities | you |
| **The registry worker** | `registry_worker(client)`, one per namespace; it may share a process with a case worker | you |
| **The key service** | Vault's transit engine, a key per case (D78) | you |
| **The audit store** | append-only, yours; Ventoux writes to it and never deletes (D77) | you |
| **Your activity workers** | Python or Java, on their own task queues, as today | the teams that own them |

Install the package where your workers and your caller run:

```
pip install "ventoux==0.1.0"
```

Pin the version. `ventoux version` says the package's version, the engine version new cases open
on (D51), and the schema's `$id`:

```
$ ventoux version
ventoux 0.1.0, engine 3, schema https://ventoux.dev/schema/engine-3/case.schema.json
```

The live step advisor needs `ventoux[anthropic]`; nothing else is an extra. Vault is reached with
the standard library.

## The rule everything rests on: one caller writes

The engine believes the identity the caller states: `answer(person="sam", roles=["support-lead"],
...)` is Sam's answer, as a support lead, whoever sent it. So whoever can send a signal to a case
can approve a payment as anyone. The engine can't tell; only Temporal's access control can.

**The caller is your service** (D79): Ventoux ships no API in v1.0. Your service calls Ventoux's
client functions (`start_case`, `answer`, `close`, `propose_change` and the others in
`ventoux.temporal.cases`; `propose_forget` and `answer_forget`), and is the one identity that
writes on behalf of people. No code of Ventoux's can check how it does that, so it must:

- **authenticate each person** before acting for them;
- **write their identifier one way,** lowercase, as D22 says (`ana.lee@example.com`, never
  `Ana.Lee@Example.com`): the engine refuses any other spelling, since "someone else" compares
  identifiers exactly;
- **take their roles from your identity provider,** as they are when the person acts;
- **never let a person name who answered, or their roles:** a form field saying `person` is how
  anyone becomes Sam.

**Give each identity only what it needs:**

| Identity | May | May never |
|---|---|---|
| **the caller** (one service identity) | start cases and forget requests, send signals and updates, query | terminate, reset, delete, change the namespace |
| **case and registry workers** (one identity per deployment) | poll their task queues, complete tasks | start cases, signal a case from outside its workflow |
| **operators** (people, few, named) | read; terminate, and reset only as below | — |
| **everyone else** (people, support, auditors) | read: list and describe workflows, read histories, through Temporal's UI | any write |

In Temporal this means **mTLS on the frontend**, every client presenting a certificate, and
**an authorizer that maps each certificate's identity to a role** in your namespace. In Temporal
Cloud: API keys or certificates per identity, with namespace permissions `write` for the caller and
the workers, `read` for people. Self-hosted: a `ClaimMapper` and `Authorizer` (the default
authorizer with a claim mapper from the certificate's subject is enough).

**Resets and terminations are admin access** (D17, D19): they can stop a case, re-run a payment
step under a new idempotency key, or end a case with its audit records unwritten (D77's known
limit). Keep them to a named group of operators, and keep Temporal's own audit log of who did
them. Prefer a Ventoux operation where one exists: `retry`, `close`, a change request.

## Temporal

- **One namespace per environment** (production, staging). The registry is created once in each,
  on purpose: `ventoux environment create production`.
- **Retention** is how long Temporal keeps a closed case's history. The audit store is the record
  that outlives it (D77), so retention is about operations, not audit. Set it long enough to
  investigate a closed case: 30 days is common.
- **Every command connects as an identity,** with the settings in `pyproject.toml`; file paths
  only, never their contents:

  ```toml
  [tool.ventoux.temporal]
  address = "ventoux-prod.a1b2c.tmprl.cloud:7233"
  namespace = "ventoux-prod.a1b2c"
  server_ca = "/etc/ventoux/temporal-ca.pem"   # omit for Temporal Cloud's public CA

  [tool.ventoux.temporal.identities.operator]
  cert = "/etc/ventoux/operator.pem"
  key = "/etc/ventoux/operator.key"

  [tool.ventoux.temporal.identities.reader]     # for doctor's checks only
  cert = "/etc/ventoux/doctor-reader.pem"
  key = "/etc/ventoux/doctor-reader.key"
  ```

  `ventoux activate`, `retire`, `environment` and `manifest publish` connect as `operator`;
  `--identity NAME` chooses another. Without `[tool.ventoux.temporal]`, commands connect to
  `localhost:7233` without TLS, as in development.

## Workers

- **Every case worker is an `environment_worker`,** naming its environment, its build and its
  identity, so it publishes its manifest before it polls (the releases guide, "Activating a
  release in an environment"). A worker the registry refuses never starts.
- **Every worker serving a module that imports Ventoux runs on `SANDBOX`** (D65). Ventoux's own
  workers do; yours must too.
- **Each case worker is given the production key service and audit store:**

  ```python
  keys = VaultKeys(address="https://vault.internal:8200", transit_mount="transit",
                   marks_mount="secret")
  client = await Client.connect(..., tls=tls, data_converter=data_converter(keys))
  worker = await environment_worker(client, "refunds", RefundCases, RefundPlans, activities,
                                    build="4f2a9c1", identity="refunds-a",
                                    audit=YourAuditStore(...), activity_executor=executor)
  ```

  The keys reach the worker through its client's converter, the audit store as an argument. The
  manifest says which kind of key provider and audit store the worker was built with (never
  their settings). In a production environment, the registry refuses a worker built with
  `FileKeys` or `FileAudit`, so it never polls.
- **Task queues:** a release is activated on its case queue; every poller there must serve the
  release's contracts with their released hashes (D54). One stray worker is enough to run other
  code, so `ventoux environment check production` belongs in your monitoring.

## The key service

As the audit guide says ("The production key service: Vault"): `VaultKeys`, the token from
`VAULT_TOKEN` alone, and the policy given there, which allows `ventoux-*` keys and reading and
writing the marks, never deleting one. Keep Vault near your workers: a replay opens every
sensitive value in the case's history, three calls each.

## The audit store

Yours, behind two methods, `append` and `read` (the audit guide). In production it must:

- keep what it is given for as long as your audit policy says, beyond Temporal's retention;
- refuse a record whose stream and number it holds with other content, and one whose previous
  number it doesn't hold;
- allow no one to delete or change a record: its rows are admin access (D19).

Ventoux can check the first two by asking; the last is your store's setting, which only this
guide can state.

## Secrets

| Secret | Where it comes from | Never |
|---|---|---|
| `VAULT_TOKEN` | the environment of each worker, the caller and the operator's shell | in a file this package ships, in a definition, on a command line |
| `ANTHROPIC_API_KEY` | the environment of whoever runs `ventoux advise` or the step advisor | as above; needed only with `ventoux[anthropic]` |
| Temporal's client keys | files named in `[tool.ventoux.temporal]`, readable by their owner only | committed; their paths are configuration, their contents are not |

Nothing Ventoux writes says a secret's value: not a log, an error, a `repr`, a recording or
`ventoux doctor`'s output. Doctor checks that each is there, never what it is.

## Checking the deployment: `ventoux doctor`

Run it after every change to the deployment, and from your monitoring:

```
$ ventoux doctor production
passed     temporal.mtls-required: a connection without a client certificate is refused
passed     temporal.reader-cannot-write: identity reader is refused a signal (PermissionDenied)
passed     temporal.operator-connects: identity operator reaches namespace ventoux-prod.a1b2c
passed     environment.production: production's registry exists and is production
passed     environment.workers: every release active or with open cases can run (environment check)
passed     environment.production-providers: every case worker's manifest names Vault and an audit store other than FileAudit
passed     keys.token-present: VAULT_TOKEN is set
passed     keys.reachable: the key service at https://vault.internal:8200 answers
passed     keys.policy: the token can't delete a mark, and can't read a key not named ventoux-*
passed     catalog.named: the catalog is acme_platform.catalog:CATALOG, not the development one
unchecked  temporal.only-caller-writes: the identities doctor holds are refused, but Temporal
           doesn't tell a client who else may write: keep the table in "One caller writes"
unchecked  temporal.resets-restricted: who may reset or terminate is Temporal's authorizer's, which
           a client can't read: keep it to named operators
unchecked  audit.no-deletes: whether the audit store lets anyone delete is the store's setting
unchecked  temporal.retention: how long closed histories are kept is yours to choose
production: 10 passed, 0 failed, 4 unchecked
```

**Three verdicts, never two.** `passed` means doctor saw the rule hold. `FAILED` means it saw it
broken. `unchecked` means it couldn't see either way: a rule doctor can't check is never said
passed, and a check that can't run (Temporal unreachable, a file missing) says `unchecked` with
why, never `passed`. Each line names its rule, so a failure says what to fix:

```
FAILED     temporal.reader-cannot-write: identity reader sent a signal and Temporal accepted it
           (the case doesn't exist, so nothing changed): give people read-only access (D19)
```

**Exit codes:** 0 when every rule it checks passed; 1 when one failed; 2 when it couldn't run at
all. `unchecked` alone doesn't fail the command: those rules are this guide's, and doctor lists
them every time so they are never forgotten. `--strict` makes `unchecked` fail too, for a
deployment that wants every rule it can't see written down somewhere else.

**How it checks without changing anything:** every write it tries is one that can't do harm if
it is allowed. To see that the reader can't write, it signals a workflow ID that can't exist
(`ventoux-doctor/…`): Temporal refuses an unauthorized call before it looks for the workflow, so
`PermissionDenied` is a pass, and "not found" means the write was allowed, a failure. To see the
token's policy, it asks Vault what the token *could* do on a path (`sys/capabilities-self`),
never doing it.

**What it reads, and with which rights:** your `pyproject.toml`, the environment's variables (by
name), Temporal as the identities you configured, the registry by a query, and Vault with
`VAULT_TOKEN`. It needs no admin rights, and holds none.

`ventoux environment check` stays: doctor runs it as one of its rules, and monitoring that
already calls it doesn't change.

## What only this guide can state

Doctor checks what can be seen from outside. These can't be, and stay your promises:

- no identity but the caller (and the workers, for their own tasks) can write to the namespace;
- resets and terminations are a small, named group's, and Temporal's audit log keeps who did them;
- the audit store keeps every record, and no one can delete one;
- Vault's own access (who else holds a token that can read `ventoux-*` keys) is as narrow as
  Ventoux's;
- the machines running workers and the caller are the ones you think they are.

## Another implementation: the conformance suite

The JSON Schema says what a definition looks like (D60); the **conformance suite** says what the
engine decides about it. It ships in the package, as data, in `ventoux/conformance/`:

```
catalogs/development.json     a catalog: its contracts as `ventoux promises` writes them, roles,
                              systems, labels, option checks, document stores
cases/…, plans/…              the definitions, each a file
examples/…                    every definition committed in the repository, as committed
suite.json                    the engine version; each entry: a definition, its catalog, and what
                              it must give; and the changes made to results, each saying why
```

```json
{
  "name": "a condition reads a field the case doesn't declare",
  "kind": "package",
  "case": "cases/a-condition-reads-an-undeclared-field.json",
  "plans": [],
  "cases": {},
  "catalog": "development",
  "expected": {
    "issues": [{ "path": "steps.pay.when", "code": "EXPRESSION_INVALID", "severity": "error" }]
  }
}
```

An implementation conforms when, for every entry, it gives exactly the expected issues: the same
paths, codes and severities, in any order, and none more. Messages are wording and are never
compared. A definition refused when read is expected as `{"read": "refused", "at": [paths]}`, by
path alone. Run results (what a case does, not only whether it is valid) come after v1.0.

`ventoux conformance --export DIR` writes the suite out. CI runs `ventoux conformance --unchanged`
on every change, so a change that alters a result fails until the suite is changed with it, in
the same pull request, with a line in its `changes` list saying why. Lines are only ever added:
one removed or rewritten later fails CI too.
