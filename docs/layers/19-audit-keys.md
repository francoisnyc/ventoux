# Layer 19: Audit export and a production key provider

Status: 2026-11-08, 19a merged (#90, D76); 19b's questions asked. This note starts
from `main` at `ff37fb9`, with layers 0 to 18 merged. The warm-up was asked and recorded (learning question 37). The guide
was written first (curriculum step 2): `docs/guides/audit.md` describes the layer as if it worked;
it was changed with the answers (listed at the end).

**Answered 2026-11-07.** Choices A to C and 1 to 21 as recommended. D76 is written before 19a is
built, with dated amendments under D27 and D51; D77 and D78 are written before 19b and 19c, with
the amendments choice B lists under D15, D17 and D32. The branch is renamed
`layer-19a-audit-records`.

Prior art: none in the prototype (the curriculum names none). Vault's transit engine API, read for
this note: encrypt and decrypt take `associated_data` for AES-GCM keys; deleting a key needs
`deletion_allowed` set on it first; `exportable` and `allow_plaintext_backup`, once set, can never
be unset.

## Warm-up: learning question 37, what the audit keeps after forgetting

Recorded in `docs/LEARNING.md`, entry 37. Asked to be told, a second time running; the status
stays open until "the facts by name and source" and the retention choice (D32) come back from
memory. It is this layer's own check-yourself question, from the other side: 37 asks what an
auditor can still learn, layer 19 builds the copy that must keep it.

## What this layer is for

**An audit trail kept apart from Temporal's history, with its own retention.** Temporal's history
is a replay log: kept for the namespace's retention, then deleted; shaped for the engine (what it
was given and asked for, decisions being code run inside workflow tasks); split by continue-as-new
and by child workflows; readable by anyone with namespace access; and rewritable from an earlier
point by an admin's reset (D19). An auditor needs the opposite on each count. So every decision is
copied, as it is made, to a store the platform team keeps for as long as the business must (D8:
"reporting uses an export").

**Sensitive values leave encrypted and stay so** (D15). Forgetting doesn't delete rows in someone
else's warehouse: it destroys one key, and every sealed value, wherever it was copied, becomes
unreadable at once.

**Keys held by the platform's key service, never by Ventoux.** `FileKeys` is a development stand-in.
The production provider seals, opens and destroys inside the key service, behind the existing
`KeyProvider`.

## What D15 (and D31, D32, D62) already settle

Not asked again:

- **Per-case keys,** through the key provider (create, seal, open, destroy, state); one
  production adapter in v1.0, Vault or a cloud KMS (D15). The provider never hands out a key; each
  sealed value is bound to its case and its place, its `part` (D31).
- **Every copy stays encrypted:** the export carries sensitive values as ciphertext under the same
  case key, *or omits them* (D15). Reports needing such a value open it through the key provider
  while the key exists.
- **What the trail keeps:** every decision, who made it, the rule and the release; only the values
  go (D15, D32).
- **Forgetting** is a request approved by someone else, closing the case first, then destroying the
  key; a destroyed key is never made again, and the check outlives Temporal (D32). A child is
  forgotten only with its parent, under the one key (D75).
- **A provider that talks to a service** is tested from recordings, never the network or a key; its
  credential is read from one environment variable, never logged; anything it can't do is a
  failure saying why, by the setting's name (D62's pattern).

What they leave open is below.

## What I checked in the code before asking

- **The engine has no structured decisions.** `CaseState.history` is `list[str]`, written from 134
  places in `case`. The *acts* that reach `decide` are structured (`Opened`, `Answered`,
  `Proposed`, `Completed`, `Failed`, `Retried`, `CloseAsked` … in `case/state.py`); what the engine
  decides from each is only lines. A plan run's history is structured already (`core/history.py`).
- **An old case can't start calling an activity.** A case workflow that now schedules an export
  activity would issue a command its recorded history doesn't have: every history recorded before
  this layer would fail to replay. So the export is an engine version (D51): version 3, marker
  `ventoux-engine-3`.
- **`KeyRefused` says everything:** a key never made, destroyed, or a damaged part. A provider that
  can't be reached is a new kind: the case must wait for it, never read it as "never made" or
  "destroyed".
- **Forgetting checks `keys.state(case)`** before anyone approves (`temporal/forget.py`); with Vault,
  that state must outlive the key itself.
- **No HTTP client is a dependency.** Vault's transit API is six HTTPS calls with a token header;
  the standard library's `urllib.request` makes them, synchronously, as the codec calls the
  provider.

## The split

| PR | What it builds | Its negative test |
|---|---|---|
| **19a: audit records, in the engine** | `case` makes one structured record per act it decides: the act (who, roles, entry, outcome), each decision it caused (kind, step and entry, rule path, facts read by name, source and value), its lines; numbered from 1; carried across continue-as-new; the in-memory run gives them. A plan run's events too. Engine version 3. | A record never holds a sensitive value unwrapped; every route makes its record (each refused act included). |
| **19b: the export, on Temporal** | The store protocol and `FileAudit`; the worker's export activity, after each workflow task that made records, in order, idempotent by ID; sealing with a `part` naming its place in the export; the store down: waiting, then needs attention, and no close with records unwritten; `read_audit`, filtered by role; the forget request's own records. | **curriculum:** an exported event holding a sensitive value in clear fails the export. Also: a gap or a changed record refused by the store; a case worker without a store refused. |
| **19c: the Vault key provider** | `VaultKeys` behind `KeyProvider`: a key per case, never exportable; destroy; "never made again" outliving the key; the token from `VAULT_TOKEN` alone; an unreachable service told apart, in the codec and in forgetting; tests from recordings. | **curriculum:** a key the provider can't give is an error saying why, never an empty value. Also: an exportable key refused; a destroyed case's ID never made again. |

**Why this order.** 19a is pure and fast to test, and every later part reads what it makes. 19b
puts it on Temporal and is where the curriculum's first negative test lives. 19c touches nothing
in 19a or 19b (it is a `KeyProvider`), so it could go first; I'd keep it last so the export's
sealing is built on the provider protocol everyone already uses, and 19c then proves Vault keeps it.

## Design questions for you

Each answer becomes a decision in the brief, from D76 on, added and never rewriting an earlier one.
A correction to a merged decision is a dated amendment under it.

### For the whole layer

A. **The split:** 19a, 19b, 19c, as in the table, one pull request each. Branches
   `layer-19a-audit-records`, `layer-19b-audit-export`, `layer-19c-vault-keys`. The warm-up, the
   guide and this note sit on `layer-19a-audit-keys`, which I'd rename to `layer-19a-audit-records`.
   *Alternative:* two parts, the records and the export together. *Recommended: three.*

B. **Decisions: one per part,** D76 (19a), D77 (19b), D78 (19c), each written before its part is
   built. Dated amendments under D15 (the adapter chosen; ciphertext, not omission, for sealed
   values), D17 (an export that can't be written needs attention), D27 (records cross
   continue-as-new), D32 (the forget request's records; "never made again" on Vault) and D51
   (engine version 3). *Recommended.*

C. **No new dependency:** Vault through the standard library's HTTP (choice 17). *Recommended.*

### For 19a: audit records

1. **The unit: one record per act, holding the decisions it caused.**
   - (a) **Per act.** Each call of `decide` (an opening, an answer, a proposal, an activity's
     completion or failure, an event, a timer, a close, an edit, a migration) makes one record: the
     act as it came (who, their roles, the entry, the outcome), then each decision it caused, in
     order, then its history lines. An answer that approves `pay` and so starts it is one record:
     `approved`, then `admitted`, then `started`. Who caused a decision is always the act's.
   - (b) Per decision: one record per decision (the guide's example), each repeating its act.
   - (c) Per history line: every one of the 134 places writes a typed record beside its line.

   *Recommended: (a).* It matches how the engine works (one act in, its consequences out), gives an
   auditor "why did this start?" without joining records, and needs typed records only where the
   engine decides, not at every line. The guide's example changes shape to it.

2. **What a decision says.** Its kind (`answered`, `approved`, `rejected`, `refused`, `admitted`,
   `started`, `completed`, `failed`, `retried`, `skipped`, `reached`, `set`, `closed`, `stopped`,
   `edited`, `migrated`, `forgotten`); the step and entry; the **rule**, as the path of what
   decided in the definition (`steps.pay.when`, `steps.pay.approval`, `rules.escalate`); and the
   **facts it read**, each by name with its sources and value, from the same analysis that gives a
   condition's fields (D36). A refusal is a decision too (`refused`, with its reason): an auditor
   asks about the opener who tried to approve. *Recommended.*

3. **Values: in clear where not sensitive, wrapped where sensitive.**
   - (a) **The export carries values.** Reports need them ("every claim above 10,000", D8); a
     history line still never quotes one (D30), and the reader filters them by role (choice 11).
   - (b) Names and sources only, no values: the export then can't answer the reports D8 sends it.

   *Recommended: (a).* In the record, a sensitive value stays `Sensitive`, wrapped as in the state,
   so it can't be read or written by mistake; 19b seals it.

4. **Form values and failure messages.** On Temporal the client seals every form value, since it
   can't tell which are sensitive (D31); the engine can. And a failure's message is always sealed,
   since no one knows what it says.
   - (a) **The record follows the case file:** a form value that isn't sensitive is in the record
     in clear, as it is in the case file (`approved_amount`); a failure is recorded by its type
     only, its message left out (D15's "or omits"). The message stays in Temporal's failure, for
     operators, under the key.
   - (b) Every form value and every failure's message sealed, as on Temporal.

   *Recommended: (a).* A non-sensitive answer value is a decision fact: D32 keeps it after
   forgetting where it was used. A failure's message helps operators, not auditors, and sealing
   text no one can classify into a long-lived store only adds risk. The guide changes with it.

5. **Numbering and streams.** A record's ID is its stream and a number: the stream is the workflow
   that made it (`claim-7`, a child `claim-7/repair#1`, a plan run `claim-7/settle#1`, a request
   `claim-7/forget`), the number counts from 1 in that stream and crosses continue-as-new in the
   state. Never a time, never random: a repeated write carries the same ID. *Recommended.*

6. **A plan run's events.** Its history is structured already (`core/history.py`). Exported as its
   own stream, each event a record, its run naming the step and entry that started it. The
   curriculum says "case and run events". *Recommended: in 19a/19b.*

7. **The engine version.** Version 3: a case opened at 3 makes and exports records; a case opened
   before decides and replays as it did, and exports nothing. Its report says so
   (`no audit export: opened at engine 2`), and `ventoux environment check` lists such open cases. A
   migration that moves a case to engine 3 (D53) starts its export there, its first record saying
   what came before was not exported. Never a partial trail passed off as whole. *Recommended.*

### For 19b: the export on Temporal

8. **How it is written.**
   - (a) **By the case's own workflow,** through an activity the worker registers (never a contract
     a definition could call, as the key's destruction, D32): after each workflow task that made
     records, one call with every record not yet written, oldest first. The store keeps each by its
     ID: the same content again is accepted, other content refused, and a record whose previous
     number it doesn't hold is refused. So a retry duplicates nothing, and nothing is skipped.
   - (b) Outside the workflow: a separate exporter reads histories. It would replay or parse them
     (forbidden: "never history lines parsed"), and run with the keys of every case.

   *Recommended: (a).* One call per workflow task, not per record, keeps the history's growth to
   three events a task.

9. **When the export can't be written** (the store down, refusing, slow).
   - (a) **The case goes on, but never closes with records unwritten.** Records wait in the state,
     in order (crossing continue-as-new); the activity is retried by its own retry policy, and the
     view says `audit export waiting: attempt 4`. After its retries the case **needs attention**
     (`audit export failed: look at the store, then retry`), retried by an operator as a step is
     (D26). A close waits for the export before the case ends, so nothing is unwritten when
     Temporal's retention starts counting.
   - (b) The case waits: no step starts while records are unwritten. Stricter, but a warehouse
     outage would stop every payment.
   - (c) The case goes on and may close; unwritten records are lost with its history.

   *Recommended: (a).* Nothing is lost while the history holds it, nothing is silent, and the
   business isn't stopped by its reporting. **Known limit, said in D77:** a case terminated by an
   admin (D19) ends with whatever it hadn't written; terminating is admin access, small and
   audited.

10. **Sealing, and where the negative test is enforced.** The activity receives records with
    sensitive values wrapped (the codec carries them sealed into the activity and opens them
    there, as for any activity). It seals each with the provider, under the case's key (a child's
    and a plan run's: its case's, D75), with a `part` naming its place in the export:
    `audit/<stream>/<number>/<field>`. Then, before anything is written, it checks every value of a
    field the definition declares sensitive (the record carries the list from the case's
    definition) is sealed: one in clear fails the whole call, nothing written, saying which record
    and field, never the value. Read from the definition, not the wrapper, so a value unwrapped by
    a bug is still caught. *Recommended.*

11. **Who may read it.** `read_audit(store, case, roles, keys)` filters each value as the case view
    does (D30): every role the case names sees the records (decisions, people, rules: D48's
    amendment to D30), a value whose `visible_to` excludes them is said hidden, and a sealed value
    is opened only for a role in its `visible_to`, while the key exists, and said `‹forgotten›`
    after. The store's rows themselves are admin access (D19), said so in the guide. *Recommended.*

12. **Retention and forgetting.** Ventoux never deletes from the store; its retention is the
    platform team's. The forget request writes its own stream (`claim-7/forget`: proposed,
    approved or rejected, closed, key destroyed), so the act of forgetting is in the trail too.
    *Recommended.*

13. **The store.** A protocol of two methods, `append(records)` and `read(stream prefix)`, and
    `FileAudit`, one JSON Lines file per stream, append-only, for development and tests. A
    production store is the platform team's, written to the protocol. A case worker without a
    store is refused. *Recommended.*

### 19b, at its start (2026-11-08): what 19a settled, and what is still to answer

19a is merged (#90, D76). Choices 8 to 13 above stand as answered (D77 writes them down): the
case writes its records through a worker-registered activity, after each workflow task that made
some, oldest first, kept once by ID (8); with the store down it goes on but never closes with
records unwritten, and needs attention after the write's retries (9a); each sensitive value is
sealed with a part naming its place, and a value in clear is refused, read from the definition (10);
`read_audit` filters by role as the view does (11); Ventoux never deletes, and the forget request
writes its own stream (12); a store is two methods, with `FileAudit` for development (13).

**Checked in the code before asking:**

- **A case continues as new only when nothing runs** (`time_to_switch`: `self.running == 0`). An
  export activity retrying for hours would hold the switch, and the run's history would grow; so
  its retries must be bounded, then the case needs attention with nothing running.
- **Forgetting waits for the case's workflow to end, however it ended** (`ForgetActivities.
  case_ended`): a terminated case counts as ended, and its key goes.
- **A closing parent waits for its child's report** (the case step's run is running until the
  child ends, D75); each case writes its own export, so neither waits on the other's.
- **A plan run's events are structured** (`core/history.py`), and two of them carry values: an
  activity's inputs (`Scheduled`) and its output (`Gave`), sensitive ones wrapped. The plan's
  report (`RunReport`) carries only their lines today.
- **The forget request is a workflow of its own** (`ForgetWorkflow`): an activity it starts calling
  would break the replay of every request recorded before.

**The split stays one pull request (19b),** in slices: the engine version and the counter; the
store and `FileAudit`; the export activity, sealing and the negative test; the store down, the
bound and attention; the close and forgetting; `read_audit`; the plan's events; the forget
request's stream; replay.

22. **Opening engine 3** (your question). `ENGINE` becomes 3, so `OPENING` is (3, 2, 1): new
    cases open at 3, writing the marker `ventoux-engine-3`, and a migration to 3 is accepted, the
    guard from #90 then reaching no version (kept: it says what to do the next time a version is
    known before it is run). `run_case`'s default becomes 3.
    - **What changes for a case at 2:** nothing. The export activity is scheduled only when the
      case's state is at engine 3 or above and holds records not yet written: a case at 2 has
      none, so no command it never issued appears in its replay. Tested: every history in
      `tests/histories` replays unchanged, and a case opened at 2 on Temporal schedules no export
      (read from its history: no `ventoux.audit.append` activity).
    - **Pinned:** a history recorded at engine 3 (an opening, an answer, an approval, the payment,
      the close, so several exports), replayed in CI as the others are.
    - **What changes for a case moved to 3:** its export starts with the migration's record (19a's
      "what came before engine 3 was not recorded").

    *Recommended.*

23. **The record number** (your question). A counter in the state, `recorded`: the number of
    records ever made, never lowered; a record is numbered `recorded + 1`. Exported records leave
    `state.audit`; the counter stays, and crosses continue-as-new. A state carried before 19b has
    none: read as the number of records it holds, which 19a numbered from 1 with no gap. A
    record's ID is its stream and its number, so no two ever share one. *Recommended.*

24. **Records waiting while the store is down** (your question). Temporal warns at a payload of
    512 KB and refuses one over 2 MB, and the whole state crosses continue-as-new as one payload.
    - (a) **A bound on what waits, measured, then the case holds.** The size of the records not
      yet written, as the export would write them (JSON, sealed parts counted at their size), is
      worked out in the workflow, deterministically, after each decision. Past 256 KB the case
      **holds**: it decides nothing new, each event waiting in its inbox, still signalled and still
      in Temporal's history, until the export catches up; it says so, `the audit export is 256
      KB behind: the case decides nothing until it is written`, and needs attention (D17). Never
      a dropped record, never an act decided unrecorded, and never a failed switch: the switch
      carries at most the bound. Below it, the case goes on as 9a says.
    - (b) Refuse new acts past the bound. A refused act is a record too (D76), so refusing would
      grow what it bounds.
    - (c) No bound: a long outage ends in a payload Temporal refuses, and a run that can't
      continue as new.

    *Recommended: (a).* Known limit, said in D77: while a case holds, each act sent to it waits as
    a signal in its run's history, which can't switch until the export is back; Temporal's
    history limit bounds that, and the case has needed attention since the hold began.

25. **Forgetting and the export** (your question). **Close, export, then destroy:** the request
    asks the case to close as forgotten; the case writes every record, the forgetting's own
    included, sealed under its key, and only then ends (choice 9a: a case never closes with
    records unwritten); the request destroys the key once the workflow has ended, as today.
    - **The store down at that moment:** the case stays closing, its export retried, needing
      attention; the request waits for the case to end, its report saying `closing the case:
      its audit export is behind`; the key is not destroyed. Never a record left that can't be
      sealed, never a key kept in silence.
    - **A child** is under its parent's key (D75): its records are sealed with the parent's key and
      written by the child's own workflow before it ends; the key goes once both have ended, as
      18d built.
    - **Known limit, said in D77:** a case terminated by an admin (D19) ends with whatever it had
      not written, and forgetting it then destroys the key: those records were never exported.

    *Recommended.*

26. **The close waiting for the export** (your question, choice 9a). It can't deadlock: the export
    depends on nothing but the store, and nothing the store does waits on the case.
    - **A person's close, store down:** the case is closing, the export retried, then attention;
      an operator retries the export once the store is back, and the case ends.
    - **A close by forgetting:** the same, and the request waits for the end (25).
    - **A parent closing a child:** the child closes, writes its own export, then reports; the
      parent waits for that report as for any running step. Neither's export waits on the other.
    - Each is a test, the store down, then back, the case ending.

    *Recommended.*

27. **How an operator retries the export** (mine). Not `retry("audit", ...)`: a step may be called
    `audit`. A signal of its own, `retry_export`, from a person holding an operating role (D26),
    refused otherwise, as a retry is; the case's line says who retried it. The export's own
    retries are bounded (10 attempts, the longest wait 5 minutes), then it has failed: `audit
    export failed: look at the store, then retry the export`. *Recommended.*

28. **A plan run's events** (choice 6, as 19a found it). They ride in the record of the plan
    step's end: `RunReport` gains `events`, the plan's history as data, and each becomes a decision
    in that record (`Scheduled` as `started`, its inputs as facts with their sources; `Gave` as
    `completed`; a wait's answer as `answered`; a refusal as `refused`; `Stopped` as `failed`). A
    result's shape changing replays: Temporal compares commands, never a result's content. A plan
    whose workflow itself fails returns no report, so its events stay in its own history, said
    in D77. *Recommended.*

29. **The forget request's own stream** (choice 12). Its records (proposed, approved or rejected,
    the case closed, the key destroyed) hold no sensitive value, so they are written plain. Behind
    a patch marker, `ventoux-forget-export`, so a request recorded before 19b replays as it was.
    Written before the key is destroyed, since the case's stream must be complete first.
    *Recommended.*

30. **The definition's sensitive fields, for the check** (choice 10). The export activity is given,
    with the records, the case's sensitive fields (names and `visible_to`), read from the
    definition in the workflow; a record holding a value of one in clear fails the whole call,
    and nothing is written. A child's from its own definition. *Recommended.*

**Carried, unchanged:** 18d's terminated parent whose child loses its key; 18c's three items.

**Answered 2026-11-08: 22 to 30 as recommended.** D77 is written before 19b is built, with dated
amendments under D15, D17 and D32; the guide follows the answers.

### Seams and tests for 19b (curriculum step 4, proposed)

**Found while choosing the seams.** A case worker is built in 19 places (the Temporal tests'
harnesses, `forget.py`'s and the manifests' docs, two guides' examples): a required `audit=`
reaches each. And 256 KB of waiting records can't be reached in a test, so the bound is a class
attribute a test's workflow lowers, as `events_per_run` is for continue-as-new.

**The seams,** public only:

1. **The store** (`ventoux.tooling.audit`): `FileAudit(folder)`, with `append(records)` and
   `read(prefix)`, and `AuditRefused` for what it won't keep. A record is the JSON object the
   guide shows.
2. **What is written** (`ventoux.temporal.audit`): `exported(stream, records, sensitive, keys)`,
   the JSON objects the activity appends, every sensitive value sealed; `ExportRefused` for a
   value in clear. The activity is this, then `append`.
3. **The worker:** `case_worker(..., audit=store)`, a required keyword; refused without one.
4. **The case, as callers use it today:** `start_case`, `answer`, `close`, `report`
   (`needs_attention`, `history`, `waiting_for`), `propose_migration`, and the forget request's
   `propose_forget`, `answer_forget` and `forget_report`. New: `retry_export(case, by, roles)`.
5. **Reading:** `read_audit(store, case, roles, keys)`, the case's records, each value filtered by
   role, opened, or said `‹forgotten›`.
6. **From outside:** the Temporal history (`fetch_history`), to read which activities a case
   scheduled; and a test's store that can be taken down and brought back (a `FileAudit` whose
   `append` raises while down), test code only.
7. **Replay:** `tests/histories`, with one history recorded at engine 3, and one forget request.

**The refusals and lines, word for word (proposed):**

| Situation | What is said |
|---|---|
| a value in clear | `audit record claim-7/41 holds national_id, a sensitive field, in clear: nothing was written` |
| a gap | `audit record claim-7/42 can't be kept: claim-7/41 is missing` |
| a record changed | `audit record claim-7/41 is already kept, with other content` |
| no store | `a case worker needs an audit store: give case_worker audit=…` |
| the export failed | `audit export failed: look at the store, then retry the export` (in `needs_attention`) |
| a retry of the export by a non-operator | `the audit export is retried by an operating role (operations), and ana has support` |
| the export retried | `omar retried the audit export as operations` |
| the hold | `the audit export is 256 KB behind: the case decides nothing until it is written` |
| the forget request waiting | `closing the case: its audit export is behind` |

**The tests, in the order I'd write them,** each failing first (the negative first):

1. **(negative, the curriculum's)** A record holding a sensitive value in clear fails the export:
   given plain where the definition says the field is sensitive, whatever wraps it, and nothing is
   written. A sealed value opens only at its own part.
2. **(negative)** The store refuses a gap and a changed record, and keeps the same record again
   once.
3. **(negative)** A case worker without a store is refused.
4. The quickstart's refund on Temporal at engine 3: every record in the store, in order, in its
   stream, the history line for line; a case opened at engine 2 exports nothing and schedules no
   export, read from its history.
5. Numbers never repeat: across continue-as-new, and after written records leave the state.
6. **(negative)** The store down: the case goes on, then needs attention; a retry of the export by
   a non-operator is refused; by an operator, the export is written and the attention cleared; a
   person's close waits for it, then the case ends.
7. **(negative)** The hold: past the bound (lowered in the test), the case decides nothing new,
   says so, and decides what waited once the export is back; it never continues as new over the
   bound.
8. Forgetting: close, export, destroy; the records sealed before the key goes, and unreadable
   after (`‹forgotten›`); the store down at that moment keeps the key, the request waiting, saying
   why; the request's own stream.
9. A child's records: its own stream, under its parent's key; a parent closing its child with the
   store down ends once the store is back, never a deadlock.
10. **(negative)** `read_audit`: a value hidden from a role is said hidden; a sealed value opened
    only for a role in its `visible_to`; `‹forgotten›` once the key is gone.
11. A plan step's events in the record of its end.
12. A migration to engine 3 on Temporal is now accepted, and starts the export.
13. Replay: every history before 19b replays, a forget request's included; the engine 3 history
    replays.

### Decided while building 19b

- **The export's failure and its retry are acts the case decides** (`ExportFailed`,
  `ExportRetried`), each recorded as any act is: the failure's reason is the store's error by its
  type, `the store failed with ConnectionError: ‹sensitive›`, or Ventoux's own refusal whole (a
  value in clear, a gap, a changed record), which never quotes a value. So the attention reads
  `audit export failed: the store failed with ConnectionError: ‹sensitive›: look at the store,
  then retry the export`, and the retry's refusal `the audit export hasn't failed: nothing to
  retry` when there is nothing to retry. The hold is said in `needs_attention` too.
- **Written records leave the state** once the store has them; the counter (`recorded`) gives the
  next number, and crosses continue-as-new. The report says how many wait: `unwritten`.
- **A record sent again is the same when each sealed value has the same place and the same
  `visible_to`:** sealing again uses a fresh nonce, so its bytes differ. Found when a retried write
  was refused as "other content".
- **The export holds the switch, but none starts when a switch is due** (unless the case is closed
  or holding). Letting the switch happen beside a running export stalled the test server's time;
  holding it while an export retries for minutes would grow the run's history. A closed case wakes
  only for its inbox: woken by a switch it can't take, it spun.
- **The forget request writes its stream beside it,** never in its way: a store that is down never
  keeps an answer waiting, nor the key. Its writes retry for as long as the store is down (never
  given up: nothing in them is sensitive, so nothing waits on them), and a store that refuses them
  fails the request. One record per act: the proposal (`admitted`, or `refused` with why), each
  answer (`refused` with why, `rejected`, or `approved` with what the approval did to the case: a
  refusal if it had closed first and keeps closed cases), and `key destroyed` (`forgotten`), whose
  lines are the case's end and the key's. That last record is written after the key is gone, not
  before as D77 first said: it holds no sensitive value, and only the case's records need the key.
  Two act kinds are added for it, `forget proposed` and `key destroyed`; its records name no
  release and the code's engine version.
- **The forget request waiting says `closing the case`,** as before; why is the case's: its report
  needs attention, saying the export failed. The line proposed, `closing the case: its audit export
  is behind`, would need the request to ask the case, which it doesn't; the guide says what is.
- **A sealed value's place is its path in the record:** `audit/<stream>/<number>/act/values/<field>`,
  `…/decisions/<n>/read/<field>`, `…/decisions/<n>/wrote`, not `audit/<stream>/<number>/<field>`:
  a record can hold the same field in several places.
- **A field that narrows who sees it, without being sensitive, is written saying so:**
  `{"value": …, "visible_to": […]}`, so `read_audit` can filter it with no definition at hand.
  `exported` and the activity's input gain `restricted`, beside `sensitive`.
- **`read_audit` opens a sealed value for the place it is found at,** never the `part` written
  beside it: a value moved within the store would otherwise open where it was moved to. It filters
  only what narrows: a value seen by every role the case names is shown to any reader, since
  `read_audit` has no definition to say who those are. The store's readers are admin access (D19).
  Kept as built, on the tutor's answer to this reading of choice 11 (review of #91): giving
  `read_audit` the definition, to refuse a reader holding no role the case names, was the
  alternative.
- **A plan's events become decisions in the plan workflow,** from its history, and its report
  carries them as `decisions` (not `events`); the case names their step and run. A decision gains
  `by` (a person answering a plan's wait) and `outcome` (what an activity gave, the answer given),
  both carried. An activity's output values are not in them: choice 28 promised its inputs.
- **Test 12 needed no new test:** the tutor's test from #90 already moved a case to engine 3 once
  the code opened cases there, and its export starts with the migration's record.
- **Two histories recorded at 19b** (`at_19b_refund_export_retried`, `at_19b_forget_request`),
  replayed from now on. Every history before 19b replays, the forget request recorded before 12c
  included.

### For 19c: the production key provider

14. **Vault's transit engine, or a cloud KMS.**
    - (a) **Vault transit.** A named key per case, free, deleted at once; AES-GCM with associated
      data, so `part` binds as it does in `FileKeys`; keys made non-exportable and checked so.
    - (b) A cloud KMS (AWS). Deletion is only scheduled, 7 to 30 days ahead and cancellable until
      then; a key per case costs about $1 a month and counts against a quota.
    - (c) Both.

    *Recommended: (a).* D15 asks for one; Vault's "destroy" means destroyed.

15. **What "destroy" means, and when a case is forgotten.** With Vault, deletion is immediate:
    the case is forgotten when the request's last activity returns, and the request says so. With a
    KMS it would be "scheduled for deletion on 2026-12-07": the case would say `forgetting, key
    deletion scheduled for …`, refuse cancelling, and be forgotten only then. Recorded so a KMS
    adapter after v1.0 has its answer. *Recommended: Vault, immediate; the KMS reading kept in D78.*

16. **"Never made again", when Vault forgets.** Vault may let a deleted key's name be made again,
    and D32's check must outlive the key.
    - (a) **A mark in Vault's key-value engine,** `ventoux/forgotten/<case>`, written before the key
      is deleted. `create` refuses a case with a mark; `state` reads the mark first; `seal` and
      `open` refuse it. A crash between the two steps leaves "destroyed", and destroying again
      finishes it. Same service, same team, same audit device.
    - (b) Never delete: trim every version and keep the name. Vault keeps a usable latest version,
      so "destroyed" would be a convention, not a fact.
    - (c) A mark in Ventoux's environment registry: a Temporal workflow, a set growing for ever.

    *Recommended: (a).*

17. **The client: no new dependency.** Six HTTPS calls (create, read, configure, encrypt, decrypt,
    delete; and the mark's read and write) through `urllib.request`, synchronous as the codec
    calls the provider. *Alternative:* `hvac`, the usual Python client, as an optional extra
    `ventoux[vault]` (it pulls in `requests`). *Recommended: the standard library.* If you prefer
    `hvac`, this is where I ask for it.

18. **Settings.** The address and mount are named in configuration (`[tool.ventoux] vault` and
    `vault_mount`, or the constructor), no default; the token from `VAULT_TOKEN` alone, never a
    file, a definition or the command line, never logged or said (D62). Only `https` addresses,
    except `localhost` for a development server. *Recommended.*

19. **A key the provider can't give: errors that say why.** Two kinds:
    - **Final** (`KeyRefused`, as today): never made; destroyed; a key that can leave Vault
      (exportable or plaintext backup allowed), never used; a part that doesn't open.
    - **Not now** (a new `KeyUnavailable`): Vault unreachable, timing out, or refusing the token.
      The codec raises it like any error, so a workflow task or an activity is retried until Vault
      answers (D17: the case waits, said by Temporal); forgetting refuses the request with it,
      never reading "unreachable" as "never made".

    Never an empty value, never a guess. *Recommended.*

20. **Tests without the network or a key.** `VaultKeys` takes a transport; tests give it a
    recording of Vault's answers, request by request, as D62's recordings do: a request the
    recording doesn't hold is refused, saying which. The recordings are written by hand from Vault's
    documented answers, and checked once against a development Vault (`vault server -dev`) when one
    is available, with a test marked to run only then. *Recommended.*

### 19c, at its start (2026-11-08): what 19b settled, and what is still to answer

Choices 14 to 20 stand as answered on 2026-11-07: Vault's transit engine; destroyed at once; the
mark in Vault's key-value engine; the standard library, no new dependency; `VAULT_TOKEN` alone;
`KeyRefused` and `KeyUnavailable`; tests from recordings. D78 is written once the questions below
are answered, before any code.

**Checked in the code before asking:**

- **The codec calls the provider synchronously from async code.** `SensitiveCodec.encode` and
  `decode` are `async`, and call `keys.seal` and `keys.open` directly. So do the forget request's
  async activities (`look_up` reads `keys.state`, `destroy_key` calls `keys.destroy`) and the
  client's `start_case` and `start_run` (`keys.create`). With `FileKeys` that is a file read; with
  Vault it is a round trip, on the event loop of the worker or the client.
- **The export's sealing already runs off the loop:** `ExportActivities.append` is a plain
  function, run on the worker's `activity_executor` threads.
- **A failed export is said as the store's** (`export_failure`): anything but Ventoux's own two
  refusals reads `the store failed with <type>`, and the attention line ends `look at the store,
  then retry the export`.
- **Two places read a key's state:** `read_audit` (`‹forgotten›` when `destroyed`) and the forget
  request's `look_up` (`there is no case …` when `never made`).
- **A case ID is refused only for a `/`** (`start_case`, `start_run`); the codec takes the part
  before the first `/`. Every ID in the tests and guides is letters, digits and `-`, with capitals
  (`refund-A-1001`).
- **No Vault here:** none is installed. HashiCorp's release site answers, so a development server
  (`vault server -dev`) can be fetched into a scratch folder for the one check against a real
  Vault: a tool for a check, not a dependency of the project.

**The questions, each with a recommendation:**

31. **The codec's calls, off the event loop.** A Vault call made on the loop blocks every workflow
    and activity on that worker for its round trip, and for its whole timeout while Vault is down.
    - (a) **Every provider call from async code goes through `asyncio.to_thread`:** the codec's
      `encode` and `decode` (one thread hop for the whole list of payloads, not one per part), the
      forget activities' `state` and `destroy`, and the client's `create`. `FileKeys` goes the same
      way: one path, whichever provider. The export activity is already on a thread.
    - **Every Vault call has a timeout:** 10 seconds, connect and answer, a constructor argument; a
      call that runs past it is `KeyUnavailable`, so the worker's thread is never held longer.
    - **The export's sealing:** one call per sensitive value, each with its timeout; the activity's
      own limit (`EXPORT_CALL`, a minute) bounds the whole, and a timeout there is retried as any
      failure of the store is. Batching seals (Vault's `batch_input`) is left for later: said, not
      built.
    - (b) A thread pool of the provider's own. More to own, for nothing `to_thread` doesn't give.

    *Recommended: (a).*

32. **The export's failure names the service that failed,** and a final refusal is never retried.
    - **Which service:** the activity's failure types are sorted three ways. `KeyUnavailable` and
      `KeyRefused` are the key service's, and their message is Ventoux's own (it names the case and
      the service's address, never a value), so it is said whole; `ExportRefused` and
      `AuditRefused` stay Ventoux's refusals, said whole; anything else is the store's, by its type
      alone. `ExportFailed` gains what to look at, `the store` or `the key service`, and the
      attention line ends `look at the key service, then retry the export` when it was Vault.
      Default `the store`, so a state carried from 19b reads as it did.
    - **A final `KeyRefused`** (an exportable key, a mark, the wrong type) is non-retryable: it
      fails the export at once, never 10 times. `KeyUnavailable` is retried, as a store that is down
      is. `EXPORT_RETRIES` gains `KeyRefused`, and its test says so.

    *Recommended.*

33. **Forgotten or unreachable, never confused.** `VaultKeys.state` says `destroyed` only when
    Vault answered with the mark, and `never made` only when Vault answered that neither the key
    nor the mark exists. Anything else (unreachable, a timeout, the token refused, an answer it
    can't read) raises `KeyUnavailable`.
    - **`read_audit`** lets it through: an error, never `‹forgotten›`. A test.
    - **The forget request, before anyone answers** (`look_up`): refused, saying so (choice 19):
      `refused pia's proposal: the key service at https://vault.internal:8200 can't be reached:
      propose again once it answers`. Nothing was decided, so nothing waits. A test that it is
      never `there is no case claim-7`.
    - **After the approval** (`destroy_key`): retried until Vault answers, as today: the approval
      was given, so the request waits, `closing the case`. Said, with a test.

    *Recommended.*

34. **A case ID as a Vault name.** Vault puts a key's name in a URL path, and its key-value engine
    puts the mark's there too: `.`, `..`, `%`, `?`, `#` and spaces would be read as path, query or
    fragment, and two IDs could meet on one name.
    - (a) **One spelling, escaped:** lowercase letters, digits and `-` stay as they are; every
      other byte of the ID's UTF-8, capitals and `_` included, is written `_` and two hex digits.
      `refund-A-1001` is `ventoux-refund-_41-1001`, `claim 7` is `ventoux-claim_207`. Two IDs never
      share a name (`_` only starts an escape, so the mapping reads back), the name holds no path
      character, and it is the same whether Vault folds capitals or not. The mark is
      `ventoux/forgotten/<the same name>`. Refused, with `KeyRefused` at `create`: an empty ID, and
      one whose name would pass 128 characters, saying the limit.
    - (b) Refuse every ID outside lowercase letters, digits and `-`: simplest, but it refuses the
      guide's `refund-A-1001`, and only where Vault is the provider, so development and production
      would accept different IDs.

    *Recommended: (a).* Tests: each awkward character, `..`, a capital against its lowercase twin,
    and the refusals.

35. **The part's binding is Vault's, and the key is checked as it is used.**
    - **The part** is sent as `associated_data`, base64, on every encrypt and decrypt, `<case>/
      <part>` as `FileKeys` binds it. A recording shows it is sent; only a real Vault shows a value
      moved to another place fails to open: a test marked to run only where `vault` is installed,
      run once here against a development server, and the PR says whether it ran, and where.
    - **The key, read on every use:** before each seal or open, its configuration is read, and
      refused unless its type is `aes256-gcm96`, it isn't exportable, and it allows no plaintext
      backup. One more round trip per use; a check made once and remembered would miss a key made
      exportable later (Vault lets that be turned on, never off). Created with all three set
      explicitly.

    *Recommended.*

36. **The mark and the delete.** `destroy` writes the mark, then allows the key's deletion, then
    deletes it. From the mark on, `state` says `destroyed`, and `create`, `seal` and `open` refuse:
    the case is forgotten even if a later step fails. `destroy` again finishes: the mark is written
    again (the same content), and a key already gone counts as deleted. A test for each step
    failing (the mark, the configuration, the deletion), each then finished by a second `destroy`.
    *Recommended.*

**Settings, as choice 18 said, made exact:** `VaultKeys(address, transit_mount, marks_mount)`,
each required, no default (the marks need a key-value engine of version 2, named apart from
transit's); an `http://` address refused unless its host is `localhost` or `127.0.0.1`; the
token read from `VAULT_TOKEN` when each call is made, never kept on the object, so it is in no
`repr`; missing, the constructor refuses, saying to set `VAULT_TOKEN`. The default transport adds
the token; a recording never sees it.

**Answered 2026-11-08: as recommended,** 31 to 36 and the settings. D78 is written, and the guide
follows (the Vault section, its errors and refusals, an export that can't seal).

### Seams and tests for 19c (curriculum step 4, proposed)

**The seams,** public only:

1. **The provider** (`ventoux.tooling.vault`): `VaultKeys(address, transit_mount, marks_mount,
   *, timeout=10, transport=None)`, a `KeyProvider` (`create`, `seal`, `open`, `destroy`,
   `state`); and `vault_name(case)`, the name a case's key has.
2. **The errors** (`ventoux.tooling.keys`): `KeyRefused`, as today, and `KeyUnavailable`, new.
3. **The transport:** a function given a request (method, path, body) and giving Vault's answer
   (status, body). The default one speaks HTTPS through `urllib.request` and adds the token;
   `Recording(exchanges)` answers from a list, in order, and refuses a request it doesn't hold.
   Tests give `VaultKeys` a recording, and read what it was asked.
4. **Callers, as today:** the codec (`SensitiveCodec.encode`, `decode`), the forget request
   (`propose_forget`, `answer_forget`), `start_case`, `read_audit`, and the case's export, seen
   through its report. To see a call made off the loop, a test's provider notes the thread each
   call ran on.
5. **A development Vault,** in one test that runs only where `vault` is installed.

**The refusals and errors, word for word (proposed):**

| Situation | What is said |
|---|---|
| never made | `there is no key for claim-7, so its sensitive values can't be read or written` (as `FileKeys`) |
| destroyed (a mark) | `the key of claim-7 was destroyed when it was forgotten: its sensitive values can't be read or written` (as `FileKeys`) |
| made again | `a key was already made for claim-7: open the case under a new ID` (as `FileKeys`) |
| can leave Vault | `the key of claim-7 can leave the key service (exportable): it is not used`; `(plaintext backup allowed)` |
| another type | `the key of claim-7 is aes128-gcm96, not aes256-gcm96: it is not used` |
| a part that doesn't open | `a sealed part of claim-7 doesn't open: it was damaged, or sealed for another case or place` (as `FileKeys`) |
| an ID that can't be a name | `a case ID names a key in the key service, and its name can't pass 128 characters`; `a case ID can't be empty` |
| unreachable | `the key service at https://vault.internal:8200 can't be reached: claim-7's sensitive values can't be read or written now` |
| timing out | `the key service at https://vault.internal:8200 didn't answer within 10 seconds: claim-7's sensitive values can't be read or written now` |
| the token refused | `the key service refused Ventoux's token for claim-7: check the token's policy` |
| an answer it can't read | `the key service at https://vault.internal:8200 gave an answer Ventoux can't read for claim-7` |
| no token | `VAULT_TOKEN is not set: the key service can't be asked` |
| an `http://` address | `the key service is reached over https: http://vault.internal:8200 is only for a development server on localhost` |
| a setting missing | `VaultKeys needs an address, a transit mount and a marks mount: transit_mount is empty` |
| a request not recorded | `the recording holds no GET /v1/transit/keys/ventoux-claim-7 (request 3): record it, or fix what asked` |
| forgetting, Vault down | `refused pia's proposal: the key service at … can't be reached: …: propose again once it answers` |
| the export, Vault down | `audit export failed: the key service at … can't be reached: …: look at the key service, then retry the export` |

**The tests, in the order I'd write them,** each failing first (the negative first):

1. **(negative, the curriculum's)** A key the provider can't give is an error saying why, never an
   empty value: seal and open for a case never made, and for one with a mark.
2. **(negative)** A key that can leave Vault (exportable, plaintext backup) or of another type is
   refused when used, read from its configuration before each use.
3. **(negative)** A recording refuses a request it doesn't hold, saying which.
4. **(negative)** Settings: an `http://` address other than `localhost` or `127.0.0.1`; a missing
   address or mount; no `VAULT_TOKEN` (a token in `~/.vault-token`, or given any other way, is
   never read). The token is in no message, `repr`, log or recording: searched for.
5. A name per case: each awkward character, `..`, a capital and its lowercase twin; an empty ID
   and one too long refused. `create` makes the key with its three settings; refuses a case with a
   mark or a key.
6. Seal and open: the part sent as associated data; a part that doesn't open refused.
7. **(negative)** `KeyUnavailable` from every call: unreachable, timing out, the token refused, an
   answer it can't read.
8. `state`: kept, destroyed (the mark, even with the key still there), never made; unreachable is
   `KeyUnavailable`, never either.
9. `destroy`: the mark, the configuration, the deletion; each failing, then finished by a second
   `destroy`; the case destroyed from the mark on.
10. Off the loop: the codec, the forget request's activities and `start_case` call the provider on
    a thread, never the event loop's.
11. The export: with the key service down, the attention names it, and it is retried; a final
    `KeyRefused` fails it at once.
12. Forgetting and reading with Vault down: a proposal refused, saying so, never "no case"; an
    approved request waits; `read_audit` fails, never `‹forgotten›`.
13. A development Vault (runs only where `vault` is installed): the whole round trip, and a value
    moved to another place doesn't open.
14. `FileKeys` and its tests unchanged; every recorded history replays.

### Carried from 18d

21. **A parent terminated with a child still running, then forgotten,** loses the key under that
    child: the child's workflow tasks fail until an operator terminates it. Nothing permissive
    happens, and its values were to become unreadable; but the child isn't closed.
    - (a) **Out of scope here, said in D77 as a known limit,** with what an operator does
      (`ventoux` lists the family's workflows still running; terminate them). Finding every child
      from a terminated parent's runs needs Temporal's visibility queries, which the test server
      doesn't serve as the development server does: a deployment question, for layer 20.
    - (b) In scope as a 19d: the forget request lists every workflow whose ID starts with
      `claim-7/`, and destroys the key only once none runs.

    *Recommended: (a).* It is about terminating (admin access), not the export or the keys.

## Seams and tests for 19a (curriculum step 4, proposed)

**Found while choosing the seams.**

- **A refused act never reaches `decide`'s result:** `decide` raises and changes nothing, and each
  driver records the refusal itself (on Temporal, a bare line, `refused …: …`). So the refusal's
  record is made by one function in `case` that the drivers call, beside the line, never by
  `decide`.
- **A case in memory has no ID.** The stream a record belongs to is its workflow's ID, which only
  the driver knows. So a record in `case` carries its number, and the export names its stream
  (19b), as the codec finds a case's key from the workflow ID Temporal gives it.
- **A plan run's events can't be exported by its own workflow:** making the plan workflow call
  an activity would break the replay of every plan run recorded before, and a plan has no engine
  version. They ride in the record of the plan step's end instead, from the run's report, which
  its case already reads (19b). A plan run started outside a case exports nothing: said in D77.

**The seams.** Only what a test of the engine uses today, plus one new field and one function:

1. **`run_case(...)`,** as now: its `CaseRun` gains `audit`, the case's records in order. Its
   `engine` argument, as now (the default becomes 3): `engine=2` makes none.
2. **The record** (`ventoux.case.audit`), read field by field, never through its lines:
   `AuditRecord(number, at, release, engine, act, decisions, lines)`;
   `Act(kind, by, roles, entry, outcome, values)`;
   `Decision(kind, step, entry, rule, read, reason)`; `Fact(field, sources, value)`. A value is as
   the state holds it: an exact decimal, a text, a `Sensitive`.
3. **`record_refused(state, act, refusal)`** (`ventoux.case.audit`): the state with the refused
   act's record added, and nothing else changed. The Temporal driver calls it where it records a
   refusal today (19b); a test calls it with the refusal `decide` raised. *(Changed while
   building: `record_refused(case, state, act, refusal)`, in `ventoux.case.recording`; see
   below.)*
4. **The existing scripts:** answers, proposals, events, `later(…)`, change requests, retries,
   closes, child cases' scripts, plan answers, as `run_case` takes them today.

**The decisions, word for word (proposed):** a decision's `kind` is one of D76's list; `rule` is a
path in the definition (`steps.pay.when`, `steps.pay.approval`, `steps.pay.approval.when`,
`milestones.assessed`, `rules.escalate`, `closes_when`); `reason` is the refusal's or the
failure's own text, which never quotes a value (D30), and a failure's is its type only:
`payments.refund@2 failed with ConnectionError`.

**The tests, in the order I'd write them,** each failing first (the negative first):

1. **(negative)** A refused answer (the opener approving their own refund) is one record, its one
   decision `refused` with the reason, and the state is otherwise unchanged.
2. **(negative)** A sensitive value is never unwrapped in a record: `national_id` in the opening
   act's values, and in the facts read by the step it reaches, is a `Sensitive`.
3. The quickstart's small refund: one record per act, numbered from 1, each with its release,
   engine and time; the opening's record holds `admitted` and `started review#1`; the review's
   answer, its `set` of `approved_amount` and `started pay#1` with `rule: steps.pay.when` and the
   facts read.
4. The guide's example: an approval that approves and starts `pay` is one record, `approved` then
   `started`, each with its rule and facts.
5. A failure is recorded by its type, never its message; a retry's record says `retried`.
6. A form value is in the record as the case file holds it: sensitive wrapped, others in clear.
7. Each route makes its record: an event (and a rule it fires: `set`, `started` by `rules.…`), a
   timer, a close and a stop, an edit and a migration (D52, D53), a claim and an assignment, a
   `shown` line, a plan step's end, a child case (the parent's `started` and `completed` name it;
   the child's records are its own), forgetting approved.
8. A case opened at engine 2 makes no record; migrated to engine 3, its first record says that
   what came before was not recorded.
9. Every record's `lines` are exactly the lines its act added to the history, so the history is
   unchanged: every existing test stays green.

### Decided while building 19a

- **`ENGINE` stays 2 until 19b.** Version 3 is known (`KNOWN = (3, 2, 1)`) and makes records, but
  a new case on Temporal opens only at a version up to `ENGINE` (`OPENING`): opened at 3 before
  the export exists, its records would pile up unwritten. 19b moves `ENGINE`, and `run_case`'s
  default, to 3. Three tests that used 3 as a version this code doesn't know now use 4.
- **Two seams moved.** `record_refused` is in `ventoux.case.recording`, beside the code that makes
  records; the record types stay in `ventoux.case.audit`, data only, so the state holds them
  without an import cycle. And it takes the case, `record_refused(case, state, act, refusal)`: an
  act's values are kept as the case file keeps them, which only the definition says.
- **A refusal names the entry as it was asked,** never a step guessed from it: a refused act may
  name an entry that doesn't exist (`review#9`). A refused proposal names its step, which it gives.
- **`admitted` is an approval asked;** a start needing none is `started` alone. A start reads its
  condition, then its approval's condition (which decided no person had to approve), then its
  inputs. An approval answered reads its condition, then the inputs the approver saw (D11).
- **A decision gains two fields:** `wrote`, a fact for what it wrote (a rule's `set`, an applied
  edit), and `target`, what it reached or stopped (a milestone, a run, an approval). Both cross
  continue-as-new.
- **A failure's reason is its run's reason,** `payments.refund@2 failed with ConnectionError:
  ‹sensitive›`: the message was replaced where the failure was caught (D31), so none is there to
  leave out, and cutting the text to the type would be parsing a line.
- **A change request rejected is `rejected`; approved but no longer applicable, `refused`,** with
  the reason. A migration to engine 3 says `what came before engine 3 was not recorded`.
- **A start's rule is read before its proposal is spent** (found by the timer's test): a task a
  rule started was recorded as its own step's start, since who proposed a run is forgotten as it
  starts.
- **Two small moves, no behaviour changed:** `asked` (a refused act's words) from the Temporal
  driver into `ventoux.case.recording`; `kept` (how the case file keeps a given value) from
  `runtime.py` into `ventoux.case.keeping`, so recording can use it.
- **In memory, a child case opens at its parent's engine,** as on Temporal the same code opens
  both.
- **A record is never renamed:** a migration renaming `pay` to `payment` changes the case; the
  records before it keep `pay`.
- **Experiment, not committed:** with `ENGINE` at 3, every in-memory test of the suite ran with
  records made, and none failed because of them (only wording that names the engine version
  changed). That is how the routes were found; each has its own test.
- **For 19b:** the Temporal driver still writes a refused act's bare line; it calls
  `record_refused` once cases open at 3 there. And a record's number is `len(state.audit) + 1`:
  once exported records are dropped from the state, the next number would repeat one already
  used, so 19b needs a counter in the state that survives trimming and crosses continue-as-new
  (from the tutor's review of #90).

### From the tutor's review of #90

- **No case moves on Temporal to engine 3 before 19b.** `OPENING` kept new cases at 2, but a
  migration's target engine was checked against `KNOWN`, which holds 3: on Temporal a migration to
  refund 2 at engine 3, approved, moved the case to engine 3, which would then keep every record in
  its state with nothing to export it, and decide as an engine 3 that 19b finishes differently
  (D51). Now the Temporal driver refuses, when proposed, a migration to a version this code knows
  but opens no case at: `engine 3 is one this code knows but doesn't run cases at yet (it runs
  them at 2, 1)`. A version it doesn't know at all keeps the case's own refusal. In memory the
  migration stays possible, for the engine's tests. Checked at the proposal only: a request
  reaches a case no other way, and code before 19a, which didn't know 3, refused it there too; so
  no pending request in any history targets it.

## Promises (19a)

Each claim the note, D76 and the guide make about audit records, and the test that would fail if
it weren't true. Tests are in `tests/test_audit_records.py`. Each was watched failing first or,
for a pin of behaviour already built, failing under a mutation (said in each slice's commit).

| Promise | Test |
|---|---|
| One record per act: the act as it came, the decisions it caused in order, its lines | `test_the_quickstarts_small_refund_records_each_act_and_what_it_decided`, `test_an_approval_that_starts_its_step_is_one_record` |
| Each record keeps exactly the lines its act added; numbered from 1 with no gap; the history is unchanged | `test_each_record_keeps_exactly_the_lines_its_act_added` (seven routes), and the whole suite green |
| Each record carries its time, its release and its engine version | `test_a_refused_act_is_one_record_saying_why_and_nothing_else_changes`, `test_the_quickstarts_small_refund_records_each_act_and_what_it_decided` |
| A refused act is one record, `refused` with its reason, and nothing else changes; it names the entry as asked, a proposal its step | `test_a_refused_act_is_one_record_saying_why_and_nothing_else_changes` |
| A decision names its rule and each fact it read, with its sources and value | `test_the_quickstarts_small_refund_records_each_act_and_what_it_decided`, `test_an_approval_that_starts_its_step_is_one_record`, `test_a_rule_that_sets_and_reaches_says_what_it_wrote_on_what_it_read` |
| A start reads its condition, its approval's condition, then its inputs; `admitted` is an approval asked; an approval reads what the approver saw | `test_the_quickstarts_small_refund_records_each_act_and_what_it_decided`, `test_an_approval_that_starts_its_step_is_one_record` |
| A sensitive value is never unwrapped in a record | `test_a_sensitive_value_is_never_unwrapped_in_a_record` |
| A form value is recorded as the case file keeps it: wrapped only if sensitive | `test_a_form_value_is_recorded_as_the_case_file_keeps_it` |
| A failure is recorded by its type, never its message; a retry says `retried` | `test_a_failure_is_recorded_by_its_type_and_a_retry_says_so` |
| A rule's `set` says what it wrote on what it read; a milestone reached says by what | `test_a_rule_that_sets_and_reaches_says_what_it_wrote_on_what_it_read` |
| A stop says what it stopped, by which firing or close, under which rule | `test_a_rules_stop_and_a_persons_close_say_what_they_stopped` |
| A change request says what it changed (`edited`, `skipped`), or why not (`rejected`, `refused`) | `test_a_change_request_says_what_it_changed_or_why_not` |
| Forgetting approved names both people | `test_forgetting_approved_is_recorded_with_both_people` |
| A parent records its child's start and end; the child records its own; in memory it opens at its parent's engine | `test_a_child_case_is_started_and_read_by_its_parent_and_records_its_own` |
| An event, a claim, a timer, a plan step, a proposal and a record shown are each recorded; a timer's start names its rule | `test_an_event_and_a_claim_are_acts_with_what_they_caused`, `test_a_timer_a_plan_a_proposal_and_a_record_shown_are_each_recorded` |
| Records are made from engine 3 only; a migration to 3 says what came before wasn't recorded | `test_a_case_before_engine_3_records_nothing_until_it_migrates_to_it` |
| No case opens or moves on Temporal to a version above `ENGINE`: a migration there is refused when proposed, saying so; one this code doesn't know keeps the case's own refusal; in memory it stays possible | `test_temporal_case_release.py::test_a_draft_is_as_before`, `::test_the_release_and_engine_cross_continue_as_new` (fail with `KNOWN` in place of `OPENING`); `test_temporal_migrations.py::test_no_case_moves_on_temporal_to_an_engine_it_doesnt_open_cases_at` (from the tutor's review of #90); `test_a_case_before_engine_3_records_nothing_until_it_migrates_to_it` (in memory) |
| Records cross continue-as-new as they were: wrapped values, exact decimals, what a decision wrote and reached | `test_records_cross_continue_as_new_as_they_were` |
| A record is never renamed by a later migration | `test_records_keep_the_names_a_migration_later_changes` |

**Not tested, said so:** an assignment, an unassignment and a give-back are mapped to acts as a
claim is, and ran with records made in the experiment, but have no test of their own here; they
decide nothing about the case, as a claim doesn't.

## Routes checked before the pull request (19a)

| Route | What it records | Test |
|---|---|---|
| the opening | `opened`, its values as kept, sensitive ones wrapped; what it started | the quickstart's test, the sensitive value's |
| an answer | `answered` under its outcome's path; what it set, reached and started | the quickstart's, the approval's |
| an approval | `admitted` when asked, `approved` or `rejected` on what the approver saw | the approval's |
| an edit (D52) | `edited`, with what it wrote; `rejected` or `refused` | the change request's |
| a skip (D52) | `skipped`, naming the run | the change request's |
| a migration (D53) | `migrated`; from engine 2 to 3, saying records start there; names never rewritten | the engine test, the rename test |
| an event (D41) | the act, with its payload; the wait it completes | the event's |
| a rule (D38 to D44) | `set` with what it wrote, `reached`, `stopped`, `started` under `rules.…` | the rule's, the stop's, the timer's |
| a timer (D44) | the act, naming its rule; what the rule did | the timer's |
| a plan (D28) | `started` and `completed` for its step (its own events are 19b's) | the plan step's |
| a child case (D74, D75) | the parent's `started` and `completed`; the child's own records | the child case's |
| a close or a stop (D40) | `stopped` for each run, approval, firing or request it ends; `closed` | the stop's |
| a retry (D26) | `retried`, then what started | the failure's |
| forgetting (D32) | the act by its approver; `forgotten` naming both | the forgetting test |
| a refusal | `refused`, its reason; nothing else | the refusal's |
| continue-as-new (D27) | every record not yet exported, as it was | the crossing test |

**State keyed by a step's name:** none. A record is what happened, under the names the case had
then; a migration renames the case, never its records (the rename test).

**Sources across every boundary:** a fact carries its sources as the state holds them; a value a
child was given keeps its parent's sources in the child's own records, since its opening keeps
them (D74). Into the export is 19b's.

**Guards, each watched failing when switched off:** records only from engine 3; a sensitive value
wrapped; a form value kept as the case file keeps it; records carried, and what a decision wrote;
every line in exactly one record; the migration's "not recorded"; a request not applied refused; a
refused proposal's step; no record renamed; `OPENING` (four release tests); on Temporal, a
migration to a version known but not opened, and its branch for a version not known at all.

### From the tutor's review of #91

- **A record sent again, sealed afresh, was accepted but untested.** With `same()` changed to
  `kept == sent`, every export, record and forget test still passed: a promise with no test. Now a
  store test exports the same records twice (the national ID sealed with two nonces) and appends
  both, the second accepted and the first kept; and a case test's store keeps a write, then
  fails as if its answer were lost: the retry, sealed afresh, is accepted, and the case closes.
  Both fail under the mutation, the case test saying `audit export failed: audit record
  claim-7/1 is already kept, with other content`. The guide's store section says what "the same
  content" means, and to compare with `same`: the production store is the platform team's.
- **`test_after_a_switch_a_child_terminated_unheard_is_noticed_within_a_day` failed once,** its
  message lost. What was checked:
  - *The parent's own export, running as the test skips 25 hours:* it can be (a probe logging
    each write and the skip showed the new run's export under way as the skip began), but the
    test server waits for it: with each write delayed at random up to 1.5 s, 32 runs, four at a
    time, all passed. So it isn't this; the test now waits for the parent's records all the same,
    so the skip starts quiet.
  - *The daily check set too late:* it is set in the new run's first workflow task, and the server
    skips no time while a workflow task or an activity is outstanding.
  - *What 19b changed for this test:* the parent's switch now waits for an export under way, and
    `until_switched` gave up after 100 tries 0.05 s apart, about 5 s. A first write slower than
    that fails the test before the skip, `claim-14 never continued as new` (a probe delaying it
    6 s did, every time). On a loaded full run that is the likely cause. Both switch waits
    (`until_switched`, `continued_as_new`) now allow about 15 s, inside the scenario's 20 s.

## Promises (19b)

Each claim the note, D77 and the guide make about the export, and the test that would fail if it
weren't true. Tests are in `tests/test_audit_export.py` unless named otherwise. Each was watched
failing first or, for a guard, failing when switched off (said in each slice's commit).

| Promise | Test |
|---|---|
| A sensitive field's value in clear fails the export, read from the definition, never the wrapper; nothing is written; the refusal names the record and the field, never the value | `test_a_sensitive_value_in_clear_fails_the_export` |
| A sealed value opens only at its own place, under its case's key | `test_a_sensitive_value_in_clear_fails_the_export`, `test_read_audit_opens_a_value_only_for_a_role_that_may_see_it` (a value moved in the store) |
| The store keeps each record once: the same again accepted; a gap or other content refused, saying which; nothing of the call kept; a case's streams read in order | `test_the_store_keeps_each_record_once_in_order` |
| A record sent again, sealed afresh (a write whose completion was lost), is the same record: each sealed value compared by its place; the store accepts it, and the case closes | `test_a_record_sealed_afresh_is_the_same_record`, `test_an_export_whose_completion_was_lost_is_retried_and_the_case_closes` (from the tutor's review of #91) |
| A case worker without a store is refused, saying what to give | `test_a_case_worker_without_a_store_is_refused` |
| A case at engine 3 writes every record, in order, in its stream, before it ends: the history line for line | `test_the_quickstarts_refund_is_exported_on_temporal` |
| A case at engine 2 makes no record, schedules no export, writes nothing | `test_a_case_at_engine_2_schedules_no_export` |
| No two records share a number: across continue-as-new, and after written records leave the state | `test_record_numbers_never_repeat_across_switches` |
| The store down: the case goes on, then needs attention, saying the store's error by its type, never what it said; only an operating role retries the export; once written, the case ends; it never ends with records unwritten | `test_with_the_store_down_the_case_closes_only_once_its_export_is_retried` |
| A retry of an export that hasn't failed is refused, saying so | `test_an_export_that_hasnt_failed_is_never_retried` |
| The export is retried 10 times, at most 5 minutes apart; refusals are never retried; the case holds past 256 KB | `test_a_deployment_retries_the_export_ten_times_and_holds_past_256_kb` |
| Past its bound the case decides nothing new, says so, and decides what waited, in order, once the export catches up | `test_past_its_bound_the_case_holds_until_its_export_catches_up` |
| Forgetting: close, export, then destroy; every record written, sealed, before the key goes, and unreadable after | `test_forgetting_closes_exports_then_destroys` |
| The store down as forgetting is approved: the case closes but doesn't end, needing attention; the key stays until the export is written | `test_with_the_store_down_forgetting_keeps_the_key_until_the_export_is_written` |
| The forget request writes its own stream: one record per act, each line in exactly one record; a refused answer and a rejection each say so | `test_forgetting_closes_exports_then_destroys`, `test_a_refused_answer_and_a_rejection_are_each_recorded_in_the_request_s_stream` |
| A child writes its own stream, under its parent's key; a sensitive value is in clear nowhere in the store | `test_a_childs_records_are_its_own_stream_sealed_under_its_parents_key` |
| A parent closing its child with the store down: each needs attention, nothing deadlocks; once both exports are retried, the child ends, then the parent | `test_with_the_store_down_a_parent_closing_its_child_ends_once_both_exports_are_retried` |
| `read_audit`: a value whose field narrows who sees it is said hidden, with the roles that would, sealed or not; a sealed one opens only for a role in its `visible_to`, says `‹forgotten›` once the key is gone, and is an error if it doesn't open | `test_read_audit_opens_a_value_only_for_a_role_that_may_see_it` |
| A plan step's events are in the record of its end: an activity started on its inputs with their sources, an answer refused or taken by whom, what an activity gave | `test_a_plan_steps_events_are_in_the_record_of_its_end` |
| A migration to engine 3 on Temporal is accepted once the code opens cases there, and the export starts with its record | `test_temporal_migrations.py::test_a_case_moves_on_temporal_only_to_an_engine_it_opens_cases_at` |
| Every history recorded before 19b replays, a forget request's included; those recorded at 19b replay | the replay tests over `tests/histories`, `test_histories_recorded_at_19b_replay` |

**Not tested, said so:** that the case never continues as new while it holds is the switch's own
rule (nothing runs, and a switch due starts no export); no test drives a switch at the bound. A
case terminated by an admin ends with what it hadn't written (D77's known limit).

## Routes checked before the pull request (19b)

| Route | How it reaches the export | Test |
|---|---|---|
| an answer, an edit, a migration, an event, a rule, the opening | each makes its record in the engine (19a); the next workflow task writes it | the quickstart's refund, the switches', the migration's |
| a migration to engine 3 | accepted once the code opens cases there; its record starts the stream | the migration's |
| a plan step | its plan's events, as decisions, in the record of its end | the plan step's |
| a child case | its own stream, under its parent's key; its close waits for its export | the child's, the parent's close |
| a close or a stop | a closed case ends only once every record is written | the store-down tests |
| a retry | `retry_export`, by an operating role, refused otherwise or when nothing failed | the store-down test, the retry's |
| forgetting | close, export, destroy; the request's own stream | the three forgetting tests |
| continue-as-new | the counter crosses; written records leave the state; no export starts when a switch is due | the switches' |
| the export itself | sealed by place, refused in clear, kept once, read by role | the first four tests, `read_audit`'s |
| replay | a case at 2 schedules nothing; the forget stream behind its patch | the engine 2 test, the replay tests |

**Sealing across every boundary:** into a child (its start, 18d's test), out of it (its records,
under its parent's key), into the export (sealed by place, in clear nowhere: the child's test and
the forgetting test search the whole store for the value).

**Guards, each watched failing when switched off:** the in-clear check reading the definition;
the store's gap and changed-record refusals; a worker without a store; the counter; only an
operating role retrying; a close waiting for its export; the hold; the forget stream's lines, one
record each, and its last record; sealing under the parent's key; `read_audit`'s hidden, forgotten
and narrowed branches, and the place it opens at; the plan's decisions, given and recorded; records
only from engine 3; the forget patch, on replay.

## What changed in the guide with the answers

Done, on this branch:

- The example event becomes one record per act (choice 1), its decisions inside it.
- "Every form value in an answer is sealed too … and so is every failure's message" becomes: a
  form value is sealed only if its field is sensitive; a failure is exported by its type only
  (choice 4).
- `audit/41/national_id` becomes `audit/claim-7/41/national_id` (choice 10).
- "Turning it on" says a case exports from engine 3, and what an older case says (choice 7).
- A section on the forget request's own stream (choice 12), and the "never made again" mark
  (choice 16).
- The key table gains the "not now" kind's wording (choice 19).

With what building 19b changed:

- A sealed value's part names where in the record it is (`audit/claim-7/41/decisions/0/read/
  national_id`), and its `visible_to` is inside the sealed value; a key with nothing to say is
  written as `null`.
- The export's failure says the store's error by its type.
- `read_audit` gives records, each value as the reader may read it: hidden, opened, or
  `‹forgotten›`; a value moved in the store doesn't open; a value every role sees is shown to any
  reader.
- The forget request waiting says `closing the case`, and the case says why; its stream holds each
  answer, refused ones too.
