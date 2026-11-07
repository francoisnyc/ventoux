# Layer 19: Audit export and a production key provider

Status: 2026-11-07, answered; 19a's seams proposed. This note starts from `main` at `ff37fb9`,
with layers 0 to 18 merged. The warm-up was asked and recorded (learning question 37). The guide
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
   refusal today (19b); a test calls it with the refusal `decide` raised.
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
