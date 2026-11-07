# Audit: the case export and the key service

> **For the platform team,** who run the audit store and the key service, and for whoever answers
> an auditor's questions. This guide describes layer 19 as if it already worked; the code that
> makes it true is built test-first in that layer. Decisions: brief D8 and D15, with D30 to D32 and
> D75. The "Design notes" at the end list what writing it revealed, and what is still to decide.

**The rule of thumb:** Temporal's history is how a case *runs*; the audit export is how a case is
*explained*, years later. Every decision the engine makes is copied, as it is made, to a store you
keep, with its own retention. Sensitive values are copied as ciphertext under the case's key, so
forgetting a case reaches your copy too, without anyone deleting a row.

## Why a second copy

| | Temporal's history | The audit export |
|---|---|---|
| **Kept** | for your namespace's retention, then deleted | for as long as you keep it: Ventoux never deletes from it |
| **Holds** | what the engine was given and asked for, for replay | each decision the engine made, as data |
| **Read with** | the engine's code, replaying it | any tool: one JSON object per event |
| **Per** | workflow run, split by continue-as-new | case, across its runs and child cases |
| **Seen by** | anyone with read access to the namespace | each role as the case file shows it (D30) |

Reports read the export, never running cases (brief, D8): "every claim above 10,000 this quarter"
is a query on your warehouse, not on Temporal.

## What an event holds

Sam approves `pay` on claim-7. The case's history says
`pay.approval#1 approved by sam (team-lead)`, and the export receives:

```json
{
  "id": "claim-7/41",
  "case": "claim-7",
  "seq": 41,
  "at": "2026-11-03T14:02:11Z",
  "release": "claim 3",
  "engine": 2,
  "kind": "approved",
  "entry": "pay.approval#1",
  "by": "sam",
  "roles": ["team-lead"],
  "rule": "steps.pay.approval",
  "read": [
    {"field": "approved_amount", "sources": ["person:ana"], "value": "1250.00"},
    {"field": "national_id", "sources": ["system:intake"], "visible_to": ["claims-officer"],
     "value": {"sealed": "q8Zx…", "part": "audit/41/national_id"}}
  ],
  "line": "pay.approval#1 approved by sam (team-lead)"
}
```

- **`id`** is the case and a number the case gives each event, in order, from 1. Never the time,
  never a random ID: a write repeated after a crash carries the same ID, and the store keeps one.
- **`at`** is workflow time, the time the event happened on Temporal (D33), never the time it was
  written.
- **`release` and `engine`** say which behaviour decided (D51); **`rule`** says where in the
  definition the decision was made.
- **`read`** names each fact the decision rested on, with its sources (D12), and its value: a
  value in clear, a sensitive one sealed.
- **`line`** is the history's own line, for people. Never parse it: every part of it is a field.

The kinds of event follow the case's life: `opened`, `answered`, `approved` and `rejected`,
`proposed`, `admitted`, `started`, `completed`, `failed`, `retried`, `reached` (a milestone),
`set` (a rule updating the case file), `event` (from outside), `edited` and `migrated` (a change
request applied), `closed`, `forgotten`. A child case's events are its own, under its own ID
(`claim-7/repair#1`), and its parent's `started` and `completed` name it.

## Turning it on

Give the case worker a store:

```python
from ventoux.temporal.worker import case_worker
from ventoux.tooling.audit import FileAudit

worker = case_worker(
    client, "claims", ClaimCase, PlanRun, implementations,
    audit=FileAudit("audit/"),  # development only: one JSON Lines file per case
    activity_executor=executor,
)
```

A store is anything with two methods: `append(events)`, which keeps each event once by its `id`
(an event already kept with the same content is accepted; with other content, refused), and
`read(case)`, which gives a case's events in order. `FileAudit` is the development store; in
production it is yours (a database table, a bucket), written to that shape. A case worker without
a store is refused: a case would run with no trail.

## Written once, never lost

The case writes its events through an activity the worker registers (never a contract a definition
could call), after each decision, oldest first. So:

- **A retried write duplicates nothing:** the same events carry the same IDs.
- **Nothing is skipped:** an event is written only after every event before it. A store that holds
  `claim-7/40` and is given `claim-7/42` refuses it.
- **A store that is down doesn't stop the case.** The case goes on deciding; its events wait in
  its state, in order, and Temporal retries the write. The case view says so:
  `audit export waiting: attempt 4`. After the write's retries the case **needs attention**
  (`audit export failed: look at the store, then retry`), as any failed step does (D17).
- **A case doesn't close with events unwritten.** Its last events are written before it ends, so
  the export is complete before Temporal's retention starts counting.

## Sensitive values: sealed, or not written

A sensitive field's value is sealed by the key service under the case's key, with a part naming
its place in the export (`audit/41/national_id`). Sealed for that place, it opens only there: moved
into another event, another case or Temporal's history, it doesn't open.

Every form value in an answer is sealed too, as on Temporal (D31), and so is every failure's
message: the export knows no more than Temporal what an activity's error says.

An event holding a sensitive field's value in clear is never written, whatever let it through:

```
audit event claim-7/41 holds national_id, a sensitive field, in clear: nothing was written
```

The write fails, and the case needs attention. The check reads the definition (which fields are
sensitive), not the value's wrapper, so a value unwrapped by mistake is still caught.

## Reading it

```python
from ventoux.tooling.audit import read_audit

for line in read_audit(store, "claim-7", roles=["claims-officer"], keys=keys):
    print(line)
```

- **Filtered by role, as the case file is** (D30): a field whose `visible_to` excludes every role
  given is said hidden, with the roles that would see it. A sensitive value is opened through the
  key service, only for a role in its `visible_to`, while the key exists.
- **The store itself is admin access.** Whoever reads its rows directly sees every value in clear
  and every sealed one as ciphertext. Keep that access small and audited (D19), as you do
  Temporal's.

## Retention and forgetting

Ventoux never deletes from the store. How long you keep it is yours, as Temporal's retention is.

When a case is forgotten (D32), the request writes a `forgotten` event to the export, then the key
is destroyed. After that, the case's export still says:

- every decision, who made it, in which role, under which rule and release, and when;
- every fact each decision rested on, **by name and source**;
- every value that wasn't sensitive, where it was used.

What no one can read: every sealed value. It is ciphertext under a key that no longer exists, and
never will again, in your store, in any copy of it, and in every backup. `read_audit` says
`‹forgotten›` where such a value was.

A child case is forgotten with its parent, under the one key (D75).

## The production key service: Vault

`FileKeys` is for development. In production, keys are held by HashiCorp Vault's transit engine:

```python
from ventoux.tooling.vault import VaultKeys

keys = VaultKeys(address="https://vault.internal:8200", mount="transit")
```

- **The token is read from `VAULT_TOKEN` alone,** never from a definition, a file or the command
  line, and is never logged or said (as D62 reads a model's key).
- **A key per case,** named `ventoux-claim-7`, `aes256-gcm96`, made when the case opens. Vault
  seals and opens for Ventoux; the key never leaves it. A key Vault would let leave (`exportable`,
  or a plaintext backup allowed) is refused, never used.
- **Destroying is immediate:** Vault deletes the key, and every value sealed with it is
  unreadable from then on.
- **Never made again:** a case ID whose key was destroyed can never open a case again, whatever
  Vault remembers.

Give Ventoux's token a policy that allows only `ventoux-*` keys: creating, configuring,
encrypting, decrypting, reading and deleting them.

**Why not a cloud KMS in v1.0:** a KMS never destroys a key at once. It schedules the deletion, 7 to
30 days ahead, and the key can be restored until then. A case would be "forgotten" only weeks after
the request was approved. And a key per case costs money every month, for every case ever opened.

## A key the service can't give

Never an empty value, never a guess: an error that says why.

| The key | What is said | What the case does |
|---|---|---|
| was never made | `there is no key for claim-7, so its sensitive values can't be read or written` | refused at the opening; anywhere else, an error |
| was destroyed | `the key of claim-7 was destroyed when it was forgotten: its sensitive values can't be read or written` | `read_audit` says `‹forgotten›`; a replay fails, the worker carries on (D32) |
| Vault can't be reached | `the key service at https://vault.internal:8200 can't be reached: claim-7's sensitive values can't be read or written now` | waits: the workflow task is retried until Vault answers |
| Vault refuses Ventoux's token | `the key service refused Ventoux's token for claim-7: check the token's policy` | waits, as above |
| is one Vault would let leave | `the key of claim-7 can leave the key service (exportable): it is not used` | waits, needing a platform fix |

## In tests

Tests never reach Vault. `VaultKeys` is given a recording of Vault's answers, as the step advisor's
tests replay a model's (D62): a request the recording doesn't hold is refused, saying which.

## What is refused

| Refused when | Example |
|---|---|
| a case worker has no audit store | `a case worker needs an audit store: give case_worker audit=…` |
| an event holds a sensitive value in clear | `audit event claim-7/41 holds national_id, a sensitive field, in clear: nothing was written` |
| an event skips one | `audit event claim-7/42 can't be kept: claim-7/41 is missing` |
| an event's ID is kept with other content | `audit event claim-7/41 is already kept, with other content` |
| the token is missing | `VAULT_TOKEN is not set: the key service can't be asked` |
| a key can leave the key service | `the key of claim-7 can leave the key service (exportable): it is not used` |

---

## Design notes: what writing this revealed

To decide in layer 19's design note (`docs/layers/19-audit-keys.md`); this guide shows my
recommendation for each, and changes with the answers.

1. **The engine has no structured events today.** `CaseState.history` is lines of text. The
   export needs the decisions as data, made in `case` beside each line, deterministic.
2. **Values in the export.** Reports need them ("every claim above 10,000"), but D30 keeps them out
   of history lines. The export carries them, sealed where sensitive, and filtered where read.
3. **When the store is down,** the case goes on but doesn't close: is that right, or should a step
   with side effects wait until the decision admitting it is written?
4. **"Never made again" on Vault.** Vault may let a deleted key's name be made again; Ventoux needs
   its own mark that a case was forgotten, kept somewhere that outlives Temporal's retention.
5. **A client library for Vault** (`hvac`, an optional extra) or the standard library's HTTP: a
   dependency to ask for.
6. **The carried item from 18d:** a parent terminated with a child still running, then forgotten.
