# Case data: what goes in the case file

> **For workflow developers.** This guide describes layer 9 as if it already worked; the code that
> makes it true is built test-first, in four parts: references and who sees what (9a), sensitive
> fields (9b), forgetting a person (9c) and fresh facts (9d). Dates are layer 16a's. The "Design
> notes" at the end list what writing it revealed.

**The rule of thumb:** a case file holds the **facts your rules decide on**, and **references** to
everything else. Customers, orders, policies and documents stay in the systems that own them.

## Why

Ventoux isn't a database for your business records, and it isn't meant to be:
- **Your records already have a home.** A second copy in every case goes stale, and then nobody knows
  which version a decision used.
- **Case history is permanent.** Ventoux runs on Temporal, which keeps each case's history. Personal
  data written there can't simply be deleted later.
- **Small case files are easy to change.** When you release a new version of a case, a short list of
  facts is simple to migrate.

## The three kinds of field

A claim, as `ventoux check` writes it:

```json
{
  "case": "claim",
  "display": {"title": "Insurance claim"},
  "fields": {
    "customer_id": {"type": "reference", "system": "crm", "display": {"title": "Customer"}},
    "policy_id": {"type": "reference", "system": "policies", "display": {"title": "Policy"}},
    "estimated_damage": {"type": "number", "display": {"title": "Estimated damage"}},
    "fraud_score": {"type": "number", "visible_to": ["fraud"], "display": {"title": "Fraud score"}}
  },
  "steps": {
    "assess": {
      "kind": "task",
      "display": {"title": "Assess the claim"},
      "roles": ["adjuster"],
      "outcomes": {
        "accept": {"display": {"title": "Accept the claim"}},
        "deny": {"display": {"title": "Deny the claim"}}
      }
    },
    "deny": {
      "kind": "activity",
      "display": {"title": "Draft the denial letter"},
      "activity": "letters.draft@3",
      "requires": ["assess"],
      "when": {"==": [{"var": "assess.outcome"}, "deny"]},
      "inputs": {"customer": {"var": "customer_id"}, "template": "claim-denied"}
    }
  }
}
```

1. **References:** the ID of a record another system owns, typed by that system's name:
   `customer_id` in `crm`, `policy_id` in `policies`.
2. **Decision facts:** values your rules and steps use: `estimated_damage`, `fraud_score`.
3. **Sensitive facts:** needed for a decision, but personal, such as a national ID. They are
   encrypted and can be forgotten (layer 9b and 9c; see below).

A quick test for each value you're tempted to store:

| Question | If yes |
|---|---|
| Is it a record or document that another system owns? | Store a **reference** |
| Does a rule, approval or step condition read it? | Store it as a **fact** |
| Is it needed only by one step (an address for a letter)? | **Don't store it:** let that step fetch it |
| Is it about a person, and needed for a decision? | Store it as a **sensitive** fact |
| Is it free text or large (notes, emails, files)? | Store a **reference** to where it's kept |

## References

A reference names its **system**, and your platform team registers the systems a deployment
knows (`crm`, `policies`, `orders`, `documents`), as it registers roles. A case naming a system
nobody registered is refused when it opens: `customer_id is a reference to sail, which is not a
registered system`.

### Fetching data where it's used

The `deny` step above gets the customer's **reference** and nothing else: `letters.draft@3` looks
up the address in the CRM when it runs, so the letter uses the current address, and the address
never enters the case history.

### A reference goes only where its system is expected

The contract of `letters.draft@3` says its `customer` input is a `crm` reference. Give it the
policy instead, and the step fails before the activity is called, whatever the two IDs look like.
The case needs attention, with the reason:

```
deny#1: letters.draft@3 takes customer as a reference to crm, and is given policy_id, a reference to policies
```

The same for a value that isn't a reference at all: a text field, or a `cat` that builds an ID
(`letters.draft@3 takes customer as a reference to crm, and is given a computed value`). Only a
reference field of the right system passes, read as it is (`{"var": "customer_id"}`).

### Seeing a referenced record

The case file holds `cus-7`; a person wants to see the customer. The inbox asks the CRM, through
a **resolver** your platform team registers for `crm`, **on behalf of the person looking**: the
CRM applies its own permissions, so you see what the CRM lets you see, and Ventoux can hide more,
never show more (brief, D16). Nothing a resolver returns enters the case file or its history; the
history records only that the record was shown:

```
ana was shown customer_id (crm cus-7)
```

If what you saw matters to a decision, make it a fact: fetched by a step, or confirmed in your
answer to a task (brief, D9).

## Who sees what

Every field is visible to anyone holding a role the case names (here `adjuster` and `fraud`). A
field may narrow that with `visible_to`: `fraud_score` is seen only by `fraud`. A step's outcome
(`assess.outcome`) and outputs (`lookup.status`) are visible like an ordinary field.

The view is filtered by Ventoux, on the server, before anything is sent: a field you can't see is
not in your view at all, and the view says it is hidden and what it needs.

```python
run = run_case(
    claim,
    file={"customer_id": "cus-7", "policy_id": "pol-3", "estimated_damage": 1200, "fraud_score": 12},
    answers=[],
    people=PEOPLE,
)
view = run.view(roles=["adjuster"])
assert view.lines == [
    "Customer: cus-7, from system:opener",
    "Policy: pol-3, from system:opener",
    "Estimated damage: 1200, from system:opener",
    "Fraud score: hidden (needs fraud)",
]
assert "fraud_score" not in view.values
```

On Temporal, `view(case, roles=[...])` from `ventoux.temporal.cases` gives the same view, filtered
inside the worker.

**Hiding is not protection against the Temporal UI.** Anyone with access to your Temporal namespace
sees a case's history, hidden fields included. Only encryption protects a value there, which is
why personal data is a *sensitive* field, not just a hidden one (brief, D16).

**Approvers see what they approve.** An approval guards the values its step reads (its inputs,
its `when`, the approval's own `when`). A person who can't see one of them can't approve the
step: their answer is refused, saying what they can't see (`lee can't see approved_amount, which
pay reads: it needs support`). Give the approval's roles sight of those fields, or someone else
must approve.

### What the engine refuses

| Refused when | Example |
|---|---|
| a reference names a system nobody registered | `customer_id is a reference to sail, which is not a registered system` |
| a reference reaches an input expecting another system | `letters.draft@3 takes customer as a reference to crm, and is given policy_id, a reference to policies` |
| a computed value reaches a reference input | `letters.draft@3 takes customer as a reference to crm, and is given a computed value` |
| an approver can't see a value the step reads | `lee can't see approved_amount, which pay reads: it needs support` |
| a record is shown to someone who can't see its field | `eve can't see customer_id: it needs adjuster or fraud` |
| a field shown isn't a reference | `estimated_damage is not a reference: there is no record to show` |

## Where values come from

Every fact remembers where it came from. You rarely need to think about it, but it's why Ventoux
can stop an unsafe step:

| A value that comes from… | is… |
|---|---|
| the system that opened the case | trusted |
| a person's answer to a task | trusted |
| a registered system, through an activity | trusted if its contract says so |
| a customer's message, a document's text, an AI | **untrusted**: it can inform people, never decide |

You declare a field's source only when it's untrusted, using a label your platform team registered
(`customer`, `llm`, `document`…). You can't declare a field trusted: trust comes from a contract or a
person's answer.

```json
"customer_estimate": {"type": "number", "source": "untrusted:customer",
                      "display": {"title": "Customer's own estimate"}}
```

## Dates

A `date` field holds a day on the calendar: when the incident happened, when the policy started.
It is written as text, `"2026-10-31"` (`YYYY-MM-DD`), and the type makes it a date: a value that
isn't a real day is refused where it is given, before it reaches the case file.

```json
"fields": {
  "policy_start": {"type": "date", "display": {"title": "Policy start"}},
  "incident_date": {"type": "date", "display": {"title": "Date of the incident"}}
}
```

```text
incident_date should be a date, written YYYY-MM-DD, and "31/10/2026" is not one
```

A date comes from where every value comes from, and carries its source like any other:

| A date given by… | Example | Its source |
|---|---|---|
| the system that opened the case | the policy's start, sent with the claim | trusted, `system:opener` |
| a person's answer to a task | the adjuster's date of the incident | trusted, the person |
| a registered system, through an activity | a contract whose output is a date | as its contract says |
| an event from outside | a payload field declared `date` | as the event declares |
| a customer's message | the date the customer says it happened | **untrusted**: it can inform people, never decide |

**Ventoux never makes a date up.** No field is filled with today's date, and no expression reads
it (see the expressions guide). A date is always a fact someone gave, recorded with who gave it.

**A date has no time zone, and Ventoux never converts a moment into one.** "31 October" is a day;
"23:30 on 31 October in New York" is a moment, and it is already 1 November in Paris. Which day a
moment falls on depends on where you stand, so that choice belongs to whoever gives the date: the
adjuster says which day the incident happened, a contract returns the day its system means. If a
system only has a moment, its activity turns it into the day the business means, and its contract
says it returns a date.

## Sensitive data

A field marked `"sensitive": true` holds something personal a decision needs, such as a national
ID. Add it to the claim:

```json
"national_id": {"type": "string", "sensitive": true, "visible_to": ["claims-sensitive"],
                "display": {"title": "National ID"}}
```

- **It is shown only to the roles its `visible_to` lists,** which it must name: a sensitive field
  without `visible_to` is refused when the definition is read. Everyone else sees that it exists
  and is hidden.
- **It never appears in plain text.** Not in the history's lines, not in a refusal, not in a
  failure: wherever a value would be written, you read `‹sensitive›`. Even a person allowed to
  see it reads `‹sensitive›` in the view's lines; the value itself is in the view's `values`,
  for the inbox to show.
- **Rules, conditions and checks use it as usual.** Inside the worker the value is decrypted, so a
  step's `when`, a form's type check and a contract's input check work on the real value. A
  step's input computed from it (`{"var": "national_id"}`, or a `cat` that reads it) is sensitive
  too, and travels encrypted to the activity, which receives the plain value.

```python
run = run_case(
    claim,
    file={"customer_id": "cus-7", "policy_id": "pol-3", "estimated_damage": 1200,
          "fraud_score": 12, "national_id": "1 85 05 78 006 084 36"},
    answers=[],
    people=PEOPLE,
)
adjuster = run.view(roles=["adjuster"])
assert adjuster.lines[-1] == "National ID: hidden (needs claims-sensitive)"
assert "national_id" not in adjuster.values
officer = run.view(roles=["claims-sensitive"])
assert officer.lines[-1] == "National ID: ‹sensitive›, from system:opener"
assert officer.values["national_id"].value == "1 85 05 78 006 084 36"
```

### On Temporal: encrypted with the case's key

Each case has its own **key**, made when the case opens and never made again. Every sensitive
value crosses Temporal in its own part of a payload, encrypted with that key by Ventoux's payload
codec, outside workflow code; the rest of the payload stays readable in the Temporal UI. That
covers everything a value can travel in: the case's opening, a form's answer, an activity's
inputs, a plan step's fields, the state carried when a long case continues as new, and the
answers to `view`. Failures are covered too: Temporal keeps a failure's message and stack trace
beside the payloads, so Ventoux encrypts both, whoever raised it.

Your platform team runs the **key provider** (Vault or a cloud KMS, after v1.0). It encrypts and
decrypts for Ventoux, so a key never leaves it. In development, keys are kept in a local file. The client and the worker connect with a data converter that
holds it:

```python
from temporalio.client import Client

from ventoux.temporal.converter import data_converter
from ventoux.tooling.keys import FileKeys

keys = FileKeys("keys.json")  # development only: a key per case, in a local file
client = await Client.connect("localhost:7233", data_converter=data_converter(keys))
```

A client or worker without it is refused: a sensitive value would cross in plain text.

What to know:

- **A case's ID has no `/`.** The codec finds a case's key from the workflow ID Temporal gives it,
  and a plan step's child (`claim-7/collect#1`) uses its case's key, the part before the `/`.
- **An ID is used once.** `start_case` makes the key, then starts the case; if starting fails
  after the key was made, that ID is spent: open the case under a new one.
- **The client can't tell which form fields are sensitive,** so `answer` encrypts every value of
  a form; the case keeps encrypted only the sensitive ones.
- **An activity's own error message is never shown.** Ventoux can't know what it says (a CRM
  error may quote the customer's ID), so the history names only the type of what it raised,
  `pay#1: payments.refund@2 failed with ConnectionError: ‹sensitive›`, and the text stays only in
  Temporal's failure, encrypted with the case's key. The worker's log is filtered the same way:
  a failed activity or workflow task is logged with its exception's type, never its message or
  traceback.
- **What your activity logs is yours.** Ventoux filters Temporal's own log lines, not your
  code's: an activity that logs what it was given writes it in plain text. Log references and
  outcomes, never sensitive values.
- **A workflow step can't be given a sensitive value:** its worker belongs to another team and
  doesn't hold the case's key. The step fails before it starts.
- **Replay needs the key,** so a worker replaying a case uses the same key provider, and
  Ventoux's workflow runner, `SANDBOX` from `ventoux.temporal.sandbox`, as `case_worker` does: it
  keeps one copy of Ventoux's own code in Temporal's sandbox.

### What the engine refuses

| Refused when | Example |
|---|---|
| a sensitive field doesn't say who may see it | `national_id is sensitive, so it must say who may see it: add visible_to` |
| a sensitive value arrives in plain text | `national_id is sensitive and was given in plain text: send it through ventoux.temporal.cases, which encrypts it` |
| a sensitive value reaches a workflow step | `kyc.check@1 is a workflow step and can't be given national_id, a sensitive field: its worker doesn't hold the case's key` |
| a case ID has a `/` | `claim/7 can't name a case: a case ID has no "/"` |
| a case's key was already made | `a key was already made for claim-7: open the case under a new ID` |
| a client or worker doesn't encrypt | `this client doesn't encrypt sensitive values: connect it with data_converter(keys) from ventoux.temporal.converter` |
| a case has no key | `there is no key for claim-7, so its sensitive values can't be read or written` |

## Forgetting a person

When a customer asks to be forgotten, you forget their case: its key is destroyed, so every
sensitive value in it becomes unreadable for good, in Temporal's history and in every copy made
of it. Everything else stays, for the audit.

**Who may forget.** Your platform team registers the roles that may, like operating roles:

```python
catalog.register_role("privacy", forgets=True)
```

They also name that catalog in a small workflow, the request to forget, and give it to the case
worker, as they do with the case workflow:

```python
from temporalio import workflow

from ventoux.temporal.forget import ForgetReport, ForgetStart, ForgetWorkflow


@workflow.defn(name="ventoux.forget")
class ClaimForget(ForgetWorkflow):
    catalog = catalog

    @workflow.run
    async def run(self, start: ForgetStart) -> ForgetReport:
        return await self.drive(start)
```

```python
worker = case_worker(client, "claims", ClaimCases, ClaimPlans, implementations,
                     forget=ClaimForget, activity_executor=activity_executor)
```

`activity_executor` is the thread pool the cases guide's `with` block opens, and shuts down once
the worker has stopped.

Forgetting is proposed by one person with such a role and approved by **another**: erasure can
conflict with keeping records, so it is a decision, made by two people. The proposer can't approve
their own request, nor can the person who opened the case, who approves no change to it (the
cases guide, "Changing an open case"); anyone with the role may reject it, the proposer included,
which changes nothing. A case opened before Ventoux's engine version 2 lets its opener approve,
as it did then, so its history replays as it was recorded; a request proposed since refuses
the opener whatever the case's version.

```python
from ventoux.temporal.forget import answer_forget, forget_report, propose_forget

request = await propose_forget(client, ClaimForget, "claim-7", "pia", ["privacy"], "claims")
await answer_forget(request, "approve", "olu", ["privacy"])
assert (await request.result()).status == "forgotten"
```

The request is a small workflow of its own, `claim-7/forget`. Before anyone answers, it checks
that the case exists, wasn't forgotten already, and may be forgotten (below). Then, in order:

1. **The case closes as `forgotten`,** if it was open, as any close does (the cases guide,
   "Closing a case"). Open tasks and approvals are cancelled; an activity already running, or a
   workflow step whose contract isn't cancellable, finishes, since a side effect can't be cut
   off halfway; a plan step stops taking answers, and a cancellable workflow step is cancelled.
   Anything that completes after the close is flagged, as with any close: `pay completed after
   the close was requested`.
2. **Once the case's workflow has ended,** and nothing of it still runs, **the key is destroyed.**
   Work still running needs the key to read its own values, so the key goes last.
3. **The request records it:** `forget_report(request)` reads `forgotten`, with who proposed,
   who approved, how the case ended, what was flagged, and that the key was destroyed. A refused
   or rejected request ends saying why, and a new one may be proposed.

A case that was already closed is forgotten the same way, keeping its own close reason, unless
its definition keeps its records (below).

**Keeping records.** Some cases must be kept: books and records, legal retention. The definition
says so:

```json
"forgetting": "while_open"
```

| `forgetting` | A request to forget the case is |
|---|---|
| `"allowed"` (the default) | accepted, open or closed |
| `"while_open"` | accepted while the case is open, refused once it is closed |
| `"never"` | always refused |

**After forgetting:**

- `report(case)` still works: it reads the report the case made when it closed, which holds
  every line of its history (with `‹sensitive›` where a value would be) and no value to decrypt.
- `view(case, roles)` is refused: the case file can't be read any more.
- A query sent to the case some other way, or a replay of its history, fails with `the key of
  claim-7 was destroyed when it was forgotten`; the worker carries on, and its log names only
  the kind of error.
- Temporal's history and its export keep every decision, who made it and with which role, the
  definition (its rules and release), and every value that wasn't sensitive where it was used.
  Where a sensitive value was, there is ciphertext no one can open. So is every form value in
  the answers people sent, and every failure's message: they crossed encrypted too.
- People's identifiers (`ana`, `pia`) stay: forgetting is about the case's subject, whose
  personal data is in its sensitive fields.
- The case's ID can never open a case again: its key is never made twice.

### What the engine refuses

| Refused when | Example |
|---|---|
| the proposer's roles may not forget | `forgetting claim-7 is proposed by privacy, and lee has support` |
| the approver's roles may not forget | `forgetting claim-7 is approved by privacy, and lee has support` |
| the proposer approves their own request | `pia proposed forgetting claim-7, so cannot approve it` |
| the person who opened the case approves forgetting it | `olu opened claim-7, so cannot approve forgetting it` |
| who opened the case can't be told any more | `who opened claim-7 can't be told: Temporal holds no history of it` |
| no case has that ID | `there is no case claim-9: no key was ever made for it` |
| the case was already forgotten | `claim-7 was already forgotten: its key was destroyed` |
| the case is closed and keeps its records | `claim-7 is closed, and its definition keeps closed cases (forgetting: while_open)` |
| the case is never forgotten | `claim-7 keeps its records (forgetting: never): it can't be forgotten` |
| the case closed before the approval reached it, and keeps closed cases | `claim-7 closed before forgetting was approved, and its definition keeps closed cases (forgetting: while_open)` |
| the case's definition can't be read any more | `claim-7's definition can't be read: Temporal holds no history of it, so whether it keeps its records is unknown` |
| the case's file is viewed after forgetting | `claim-7 was forgotten: its case file can't be read` |
| a forgotten case's history is read or replayed | `the key of claim-7 was destroyed when it was forgotten: its sensitive values can't be read or written` |

## Fresh facts

A case file is a snapshot: "the order is delivered" means *it was, when we looked*. So every
fact records **when it was obtained**, and which step run obtained it: the opening, a person's
answer, or a run such as `check_order#1`. Ventoux never reads a clock to decide anything; the
time comes with each event the case receives, so a case replays the same way (brief, D18).

### Saying how fresh a step needs its facts

Freshness belongs where a fact is **used**, not on the field: a week-old status is fine for a
letter, not for a payment. A step says it with `max_age`, for any field it reads in its inputs,
its `when` or its approval's `when`:

```json
"check_order": {
  "kind": "activity",
  "display": {"title": "Look the order up"},
  "activity": "orders.lookup@2",
  "inputs": {"order_id": {"var": "order_id"}}
},
"pay": {
  "kind": "activity",
  "display": {"title": "Refund the customer"},
  "activity": "payments.refund@2",
  "requires": ["review", "check_order"],
  "when": {"if": [{"==": [{"var": "check_order.outcome"}, "done"]},
                  {"and": [{"==": [{"var": "review.outcome"}, "approve"]},
                           {"==": [{"var": "check_order.status"}, "delivered"]}]},
                  false]},
  "max_age": {"check_order.status": "1d"},
  "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
  "approval": {"when": {">": [{"var": "approved_amount"}, 100]}, "roles": ["support-lead"],
               "display": {"reason": "Refunds above 100 need a team lead"}}
}
```

An age is a whole number and a unit: `30m` (minutes), `12h` (hours) or `1d` (days).

`orders.lookup@2` declares where `status` comes from: the orders system (`system:orders`).
`orders.lookup@1` declares no source for `status`, so it is `untrusted:undeclared` (brief, D29), and
`pay`, whose `when` reads it, would fail on its inputs every time: a value nobody vouched for would
decide whether a payment is sent (the cases guide, "Untrusted data can't choose what is sent").

`pay` reads the status only once the lookup is `done`: a lookup that gives `not_found` gives no
status, and reading a value nobody set fails the step. It pays only an approved review, which
alone sets `approved_amount`. (In a condition, `and` reads all its parts, so only `if` can keep a
part from being read; `ventoux check` warns about a value read before it is surely set: the cases guide,
"What the check warns about".)

### What happens to a stale fact

The age is checked **just before the step would run**: once its `requires` are met, and before
its `when`, its approval's `when`, asking for its approval and starting it. If a fact is older
than its `max_age`:

- **It came from a read-only activity** (its contract's effect is `read`): Ventoux runs that step
  again first. It is a new run, `check_order#2`, with its own key, checked as every run is. Its
  output replaces the old one, with a fresh time, and then `pay` is checked again, its condition
  included: an order returned since the first look now stops the refund. It runs again only if
  it could start now: what it requires is done, its condition holds, and it needs no approval.
  A refresh never asks for an approval itself, so a read behind one (a credit check) needs
  attention instead.
- **It came from anywhere else**, the step needs attention instead (brief, D17): a person's
  answer, the opening, an activity with side effects (`write`, `notify`) or one that computes
  (`compute`), a workflow step or a plan step. Ventoux can't fetch those again. A person decides:
  answer the task again (propose it, if it is repeatable), then retry the step; or close the
  case.

A step a person proposes whose stale fact can be fetched again waits the same way: the proposal
is accepted, the fact is fetched again, then the step starts, or doesn't, on the fresh value. If
the fact can't be fetched again, the proposal is refused, saying why. A rule's start doesn't wait:
the step needs attention, and an operator's retry fetches the fact again, if anything can; if
nothing can, the step's line says why, as a refused proposal does. Nothing proposed runs on a
stale fact.

A fact is fetched again **once for each need**, never in a loop:

- **A refresh that fails** needs attention itself, like any failed run. A step that requires the
  refreshed step waits for it, and once an operator retries the refresh and it succeeds, the
  step runs on the fresh value. A step that only reads the fact needs attention too.
- **A refresh that gives an outcome** such as `not_found` writes no output, so the fact is still
  stale: the step that needed it needs attention.
- **Retrying that step** is a person deciding to try again: the fact may then be fetched again.
- **Two steps that need the same fact** share one refresh, and while it runs, the step it
  refreshes still counts as done for `requires`: an approval waiting on it stays open, unless
  the refresh changes a value it reads.

```python
looked_up = iter(["delivered", "returned"])  # the order was returned in the meantime
run = run_case(
    refund_fresh,
    file={"order_id": "ord-1", "amount": 80},
    answers=[later("3d"), ("review", "approve", "ana", {"approved_amount": 80})],
    people=PEOPLE,
    activities={"orders.lookup@2": lambda inputs: {"status": next(looked_up)}},
)
assert not run.reached("pay")
assert "refreshing check_order.status for pay: obtained 3 days ago, at most 1 day" in run.history
```

**When it is noticed.** Only when an event reaches the case (an answer, a result, a proposal):
a case where nothing happens notices nothing. Timers that would notice sooner come with rules
(layer 11).

### Approvals and fresh facts

- **An approval is asked on fresh facts,** since the age is checked before it is asked.
- **A refresh that changes a value an approval reads** (the step's inputs, its `when`, the
  approval's `when`) withdraws it if it is open, as any change does (brief, D25). If it was
  already given, it **lapses**: `lapsed pay.approval#1: check_order.status changed when
  refreshed`. The step is then checked again from the start: if it should still run and still
  needs an approval, a new one is asked, on the new value.
- **A refresh that changes nothing leaves the approval standing,** open or given.

The **approval sheet** shows the age of every fact the approval depends on, so the approver can
act before, and the audit can explain after. For a refund of 250, whose approval Sam reads three
days after the order was looked up:

```python
run = run_case(
    refund_fresh,
    file={"order_id": "ord-1", "amount": 250},
    answers=[("review", "approve", "ana", {"approved_amount": 250})],
    people=PEOPLE,
    activities={"orders.lookup@2": lambda inputs: {"status": "delivered"}},
)
sheet = run.approval_sheet("pay.approval#1", roles=["support-lead"], at=START + 3 * DAY)
assert "check_order.status: delivered, obtained 3 days ago" in sheet.lines
```

`at` is the time the sheet is read: a sheet is read, never decided on, so the time is the
reader's. On Temporal, `approval_sheet(case, entry, roles)` uses the API's clock unless you give
one. The case view gives each value's time too, in `view.obtained`, as whole seconds since the
epoch. A hidden field's time is hidden with it; a sensitive field's time is not sensitive.

### In tests and on Temporal

- **In tests, time is given.** `run_case` starts at `ventoux.testing.START` (1 January 2026,
  UTC) unless you pass `at=`; `later("3d")` in the script moves time on, and `DAY` is a day in
  seconds. A result arrives at the time of the event that started its run.
- **On Temporal, time is the workflow's.** Each event is stamped as it reaches the case, from
  Temporal's workflow time, which history records: a replay reads the same times, so the case
  decides the same way. Times cross a continue-as-new exactly.

### What the engine refuses

| Refused or stopped when | Example |
|---|---|
| an age has an unknown unit | `steps.pay.max_age.check_order.status: an age looks like "30m", "12h" or "1d"` |
| an age is zero | `steps.pay.max_age.check_order.status: an age is at least 1m` |
| a step's `max_age` names a field it doesn't read | `steps.pay.max_age: pay doesn't read amount in its inputs, its when or its approval: name only what it reads` |
| a stale fact came from a person (needs attention) | `approved_amount was obtained 3 days ago, and pay needs it at most 1 day old: it came from a person, so it can't be fetched again` |
| a stale fact came from the opening (needs attention) | `order_id was obtained 3 days ago, and pay needs it at most 1 day old: it came from the opening, so it can't be fetched again` |
| a stale fact came from a step with side effects (needs attention) | `pay_fee.outcome was obtained 3 days ago, and notify needs it at most 1 day old: pay_fee has side effects (write), so it can't be run again` |
| a stale fact came from a step that computes (needs attention) | `fee.fee was obtained 3 days ago, and pay needs it at most 1 day old: fee computes it from its inputs (compute), so running it again gives nothing new` |
| a stale fact came from a read that needs an approval to run (needs attention) | `check_order.status was obtained 3 days ago, and pay needs it at most 1 day old: check_order needs an approval to run, so it isn't run again unasked` |
| a stale fact came from a workflow or a plan step (needs attention) | `kyc.status was obtained 3 days ago, and pay needs it at most 1 day old: kyc is a workflow step, so it isn't run again unasked` |
| a refresh gave no fresh value (needs attention) | `check_order#2 gave not_found, so check_order.status is still 3 days old, and pay needs it at most 1 day old` |
| a refresh failed, and the step only reads its fact (needs attention) | `check_order#2 failed, so check_order.status is still 3 days old, and pay needs it at most 1 day old` |
| a fact's time is unknown (needs attention) | `check_order.status has no time obtained, so pay can't tell its age` |
| a sheet is asked for an approval that isn't open | `pay.approval#3 is not open: there is no sheet to read` |

## Reports

To answer questions across cases ("every claim above 10,000 this quarter"), use the **case export**,
which copies case events and facts to your data warehouse or database. Don't query running cases.
Sensitive values stay encrypted in the export, under the case's key, so forgetting a person reaches
the warehouse too.

## Common questions

- **Can I store a document in a case?** No. Store it in your document system and keep its reference.
- **The record changed after the case read it. Which value counts?** The fact in the case file, as
  obtained at that time. If a step must not run on an old value, say so with `max_age`: when
  it's older, Ventoux runs the lookup again first.
- **Can I see the referenced record in the case view?** Yes: the inbox shows referenced records by
  asking their system, on your behalf: you see what that system lets you see. Nothing shown is
  stored in the case. If what you saw matters to your decision, record it as a fact (for example,
  in your answer to the task).
- **I hid a field with `visible_to`. Is it safe from the Temporal UI?** No: hiding is for the
  case view. Mark personal data `sensitive`, which encrypts it.
- **Why can't I read why an activity failed?** Its message may quote personal data, so Ventoux
  keeps it only in Temporal's failure, encrypted with the case's key. Reading it takes the key
  (a codec server for the Temporal UI comes with the deployment guide, after v1.0); forgetting
  the case makes it unreadable too.

---

## Design notes: what writing this revealed

1. **References need a type of their own** (`"type": "reference", "system": …`), not a plain text
   field. The `system` name links them to how views and activities resolve them (decided: D16).
2. **Activities should take references, not copies.** That's guidance for the platform team when
   designing contracts; the activities guide shows `letters.draft@3`, which takes a `crm`
   reference and fetches the address itself.
3. **Views need resolvers.** To show a referenced record, the inbox must call something per system
   (`policies`, `crm`, `documents`). That's a new extension point for the platform team (decided:
   D16: read-only, called on behalf of the viewer, never stored).
4. **Erasure needs a key service** (decided: D15). Per-case keys through a key provider, in v1.0;
   forgetting is approved by someone else, and closes an open case first; exports carry ciphertext.
   Since layer 9c, a definition may keep its records: `"forgetting": "while_open"` or `"never"`
   (brief, D32).
5. **Facts record when they were obtained** (decided: D18). Workflow time, an optional as-of time
   from the source, `max_age` where a step uses a fact, and stale facts refreshed by re-running a
   read-only lookup. Since layer 9d, the time is data on each event, never a clock the case
   reads; the as-of time from the source is still to come: nothing needs it yet (brief, D33).
6. **Erasure and audit must coexist.** The audit trail keeps that a decision happened, by whom and
   on which rule, but not the erased values. The audit format must allow that.
7. **The quickstart's `order_id` is a reference.** It uses `refund.reference("order_id",
   system="orders")`, which also makes the quickstart teach the rule of thumb from the start.
8. **No date type yet** (layer 9a). An earlier draft had a sensitive `birth_date` with
   `Field.date()`; expressions have no date type (brief, D20), and adding one is a decision of its
   own. The sensitive example is a `national_id`, a text. *Layer 16a adds the date* (see "Dates").
9. **Hiding and encrypting are different promises** (layer 9a). `visible_to` filters the case view;
   only `sensitive` keeps a value out of Temporal's plain history.
10. **Sensitive values are encrypted one by one, not whole payloads** (layer 9b). Each travels in
    its own part of a payload, so the rest of the history stays readable (brief, D15). An
    activity's own error message is treated as sensitive whatever the case declares: Ventoux
    can't know what it says.
11. **A date is a day, and someone always gives it** (layer 16a). Writing "Dates" showed three
    things to decide: a moment becomes a day only with a time zone, so Ventoux never converts one
    and whoever gives the date chooses the day; a field filled with today's date would be the
    clock by another door, so there is none; and a text date is still a text, so a date literal
    in an expression needs its own form, `{"date": "…"}`.
