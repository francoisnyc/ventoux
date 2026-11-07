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
| **Read with** | the engine's code, replaying it | any tool: one JSON object per record |
| **Per** | workflow run, split by continue-as-new | case, across its runs and child cases |
| **Seen by** | anyone with read access to the namespace | each role as the case file shows it (D30) |

Reports read the export, never running cases (brief, D8): "every claim above 10,000 this quarter"
is a query on your warehouse, not on Temporal.

## What a record holds

Each act that reaches a case (an opening, an answer, an activity's result, an event, a timer, a
close) is one **audit record**: the act as it came, then each decision it caused, in order. Sam
approves `pay` on claim-7, and that starts the payment. The case's history says

```
pay.approval#1 approved by sam (team-lead)
started pay#1: payments.refund@2
```

and the export receives one record:

```json
{
  "stream": "claim-7",
  "number": 41,
  "at": "2026-11-03T14:02:11Z",
  "release": "claim 3",
  "engine": 3,
  "act": {"kind": "answered", "entry": "pay.approval#1", "outcome": "approve",
          "by": "sam", "roles": ["team-lead"]},
  "decisions": [
    {"kind": "approved", "step": "pay", "entry": "pay.approval#1",
     "rule": "steps.pay.approval",
     "read": [
       {"field": "approved_amount", "sources": ["person:ana"], "value": "1250.00"},
       {"field": "national_id", "sources": ["system:intake"], "visible_to": ["claims-officer"],
        "value": {"sealed": "q8Zx…", "part": "audit/claim-7/41/national_id"}}
     ]},
    {"kind": "started", "step": "pay", "entry": "pay#1", "rule": "steps.pay.when",
     "read": [{"field": "approved_amount", "sources": ["person:ana"], "value": "1250.00"}]}
  ],
  "lines": ["pay.approval#1 approved by sam (team-lead)", "started pay#1: payments.refund@2"]
}
```

- **`stream` and `number`** identify it: the workflow that made it (`claim-7`; a child case
  `claim-7/repair#1`; a request to forget `claim-7/forget`) and a number from 1, in order. Never
  the time, never a random ID: a write repeated after a crash carries the same ID, and the store
  keeps one.
- **`at`** is workflow time, the time the act happened on Temporal (D33), never the time it was
  written.
- **`release` and `engine`** say which behaviour decided (D51).
- **`act`** says who did what, as the case received it. A refused act is a record too: its one
  decision is `refused`, with the reason, and nothing else changed.
- **Each decision** says its kind, its step and entry, the **rule** (where in the definition it
  was decided) and each fact it **read**, by name, with its sources (D12) and value: in clear,
  or sealed if the field is sensitive.
- **`lines`** are the history's own lines, for people. Never parse them: every part of them is a
  field.

The kinds of decision follow the case's life: `answered`, `approved`, `rejected`, `refused`,
`admitted`, `started`, `completed`, `failed`, `retried`, `skipped`, `reached` (a milestone), `set`
(a rule updating the case file), `closed`, `stopped`, `edited` and `migrated` (a change request
applied), `forgotten`. A child case's records are its own stream, and its parent's `started` and
`completed` name it. A plan step's events come with the record of the plan step's end.

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

A store is anything with two methods: `append(records)`, which keeps each record once by its
stream and number (a record already kept with the same content is accepted; with other content,
refused), and `read(case)`, which gives a case's records, its children's and its requests', each
stream in order. `FileAudit` is the development store; in
production it is yours (a database table, a bucket), written to that shape. A case worker without
a store is refused: a case would run with no trail.

**Cases export from engine version 3.** A case opened by an earlier version of Ventoux decides and
replays as it always did, and exports nothing: its report says `no audit export: opened at engine
2`, and `ventoux environment check` lists such cases while they are open. Migrating one to engine 3
starts its export there; its first record says that what came before was not recorded.

## Written once, never lost

The case writes its records through an activity the worker registers (never a contract a definition
could call), after each decision, oldest first. So:

- **A retried write duplicates nothing:** the same records carry the same IDs.
- **Nothing is skipped:** a record is written only after every record before it. A store that
  holds `claim-7/40` and is given `claim-7/42` refuses it.
- **A store that is down doesn't stop the case.** The case goes on deciding; its records wait in
  its state, in order, and Temporal retries the write. The case view says so:
  `audit export waiting: attempt 4`. After the write's retries the case **needs attention**
  (`audit export failed: look at the store, then retry`), as any failed step does (D17).
- **A case doesn't close with records unwritten.** Its last records are written before it ends,
  so the export is complete before Temporal's retention starts counting.
- **Known limit: a terminated case.** An admin who terminates a case's workflow (D19) ends it with
  whatever it hadn't written yet. Keep that access small and audited.

## Sensitive values: sealed, or not written

A sensitive field's value is sealed by the key service under the case's key, with a part naming
its place in the export (`audit/claim-7/41/national_id`). Sealed for that place, it opens only there: moved
into another record, another case or Temporal's history, it doesn't open.

A value a person typed into a form is in the export as the case file holds it: sealed if its
field is sensitive, in clear otherwise. A failure is exported by its type alone
(`failed with ConnectionError`), never its message: no one knows what an activity's error says, so
it stays in Temporal's failure, under the case's key, for operators.

A record holding a sensitive field's value in clear is never written, whatever let it through:

```
audit record claim-7/41 holds national_id, a sensitive field, in clear: nothing was written
```

The write fails, and the case needs attention. The check reads the definition (which fields are
sensitive), not the value's wrapper, so a value unwrapped by mistake is still caught. It names the
record and the field, never the value.

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

When a case is forgotten (D32), the request writes its own stream to the export
(`claim-7/forget`: who proposed it, who approved it, the case closed, the key destroyed), so the
act of forgetting is in the trail too. After that, the case's export still says:

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
- **Never made again:** before it deletes a key, `VaultKeys` writes a mark in Vault's key-value
  engine, `ventoux/forgotten/claim-7`. A case ID with a mark can never open a case again, and its
  key is never used, even if Vault would let a key of that name be made again.

Give Ventoux's token a policy that allows only `ventoux-*` keys (creating, configuring,
encrypting, decrypting, reading and deleting them) and reading and writing the marks under
`ventoux/forgotten/`. Ventoux talks to Vault over HTTPS with the standard library: nothing to
install.

**Why not a cloud KMS in v1.0:** a KMS never destroys a key at once. It schedules the deletion, 7 to
30 days ahead, and the key can be restored until then. A case would be "forgotten" only weeks after
the request was approved. And a key per case costs money every month, for every case ever opened.

## A key the service can't give

Never an empty value, never a guess: an error that says why.

| The key | What is said | What the case does |
|---|---|---|
| was never made | `there is no key for claim-7, so its sensitive values can't be read or written` | refused at the opening; anywhere else, an error |
| was destroyed | `the key of claim-7 was destroyed when it was forgotten: its sensitive values can't be read or written` | `read_audit` says `‹forgotten›`; a replay fails, the worker carries on (D32) |
| Vault can't be reached | `the key service at https://vault.internal:8200 can't be reached: claim-7's sensitive values can't be read or written now` | waits: the workflow task, or the activity, is retried until Vault answers; a request to forget is refused, saying so |
| Vault refuses Ventoux's token | `the key service refused Ventoux's token for claim-7: check the token's policy` | waits, as above |
| is one Vault would let leave | `the key of claim-7 can leave the key service (exportable): it is not used` | waits, needing a platform fix |

## In tests

Tests never reach Vault. `VaultKeys` is given a recording of Vault's answers, as the step advisor's
tests replay a model's (D62): a request the recording doesn't hold is refused, saying which.

## What is refused

| Refused when | Example |
|---|---|
| a case worker has no audit store | `a case worker needs an audit store: give case_worker audit=…` |
| a record holds a sensitive value in clear | `audit record claim-7/41 holds national_id, a sensitive field, in clear: nothing was written` |
| a record skips one | `audit record claim-7/42 can't be kept: claim-7/41 is missing` |
| a record's ID is kept with other content | `audit record claim-7/41 is already kept, with other content` |
| the token is missing | `VAULT_TOKEN is not set: the key service can't be asked` |
| a key can leave the key service | `the key of claim-7 can leave the key service (exportable): it is not used` |

---

## Design notes: what writing this revealed

Decided in layer 19's design note (`docs/layers/19-audit-keys.md`), answered 2026-11-07 as
recommended; this guide was changed to match.

1. **The engine had no structured decisions:** `CaseState.history` is lines of text. Records are
   made in `case`, one per act, beside the lines (brief, D76).
2. **The export carries values,** in clear where not sensitive, sealed where sensitive, and is
   filtered where read (D76).
3. **A store that is down** lets the case go on but never close with records unwritten (D77).
4. **"Never made again" on Vault** is a mark in Vault's key-value engine, written before the key
   is deleted (D78).
5. **No client library:** Vault over HTTPS with the standard library (D78).
6. **A parent terminated with a child still running, then forgotten** (carried from layer 18d)
   stays a known limit, for layer 20's deployment guide.
