# Case data: what goes in the case file

> **For workflow developers.** This guide describes layer 9 as if it already worked; the code that
> makes it true is built test-first, in four parts. References and who sees what (9a) are
> described as built. Sensitive fields (9b), forgetting a person (9c) and fresh facts (9d) are
> still design: their sections say so. The "Design notes" at the end list what writing it revealed.

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
policy instead, and the step fails before the activity is called, whatever the two IDs look like:

```
letters.draft@3 takes customer as a crm reference, and deny gives it policy_id, a policies reference
```

The same for a value that isn't a reference at all: a text field, or a `cat` that builds an ID
(`letters.draft@3 takes customer as a crm reference, and deny gives it a computed value`). Only a
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
| a reference reaches an input expecting another system | `letters.draft@3 takes customer as a crm reference, and deny gives it policy_id, a policies reference` |
| a computed value reaches a reference input | `letters.draft@3 takes customer as a crm reference, and deny gives it a computed value` |
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

## Sensitive data and the right to be forgotten

> **Design, built in layers 9b and 9c.**

A field marked `"sensitive": true`, such as `"national_id": {"type": "string", "sensitive": true,
"visible_to": ["claims-sensitive"], …}`:
- is encrypted with a key that belongs to that case, so it never appears in plain text in history;
- is shown only to the roles it lists in `visible_to`, which it must name; others see that it
  exists and is hidden;
- can be **erased**: forgetting a case is proposed by someone with the data protection role and
  approved by someone else with it. Then the case closes (if it was open, running steps finish
  first) and its key is destroyed. The history keeps every decision and who made it, but the
  sensitive values become unreadable everywhere, including copies already exported.

Your platform team runs the key provider (for example Vault or a cloud KMS). In development, keys
are kept in a local file.

## Fresh facts

> **Design, built in layer 9d.**

Every fact records when it was obtained, and by which step. A step may say how fresh the facts it
uses must be: `"max_age": {"lookup.status": "1d"}`. When one is older, Ventoux runs the read-only
step that obtained it again first, then checks the step's condition again. A fact that came from
a person, from the opening, or from a step with side effects can't be fetched again: the case
needs attention instead.

## Reports

To answer questions across cases ("every claim above 10,000 this quarter"), use the **case export**,
which copies case events and facts to your data warehouse or database. Don't query running cases.
Sensitive values stay encrypted in the export, under the case's key, so forgetting a person reaches
the warehouse too.

## Common questions

- **Can I store a document in a case?** No. Store it in your document system and keep its reference.
- **The record changed after the case read it. Which value counts?** The fact in the case file, as
  obtained at that time. If a step must not run on an old value, say so with `max_age` (layer 9d):
  when it's older, Ventoux runs the lookup again first.
- **Can I see the referenced record in the case view?** Yes: the inbox shows referenced records by
  asking their system, on your behalf: you see what that system lets you see. Nothing shown is
  stored in the case. If what you saw matters to your decision, record it as a fact (for example,
  in your answer to the task).
- **I hid a field with `visible_to`. Is it safe from the Temporal UI?** No: hiding is for the
  case view. Mark personal data `sensitive`, which encrypts it.

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
5. **Facts record when they were obtained** (decided: D18). Workflow time, an optional as-of time
   from the source, `max_age` where a step uses a fact, and stale facts refreshed by re-running a
   read-only lookup.
6. **Erasure and audit must coexist.** The audit trail keeps that a decision happened, by whom and
   on which rule, but not the erased values. The audit format must allow that.
7. **The quickstart's `order_id` is a reference.** It uses `refund.reference("order_id",
   system="orders")`, which also makes the quickstart teach the rule of thumb from the start.
8. **No date type yet** (layer 9a). An earlier draft had a sensitive `birth_date` with
   `Field.date()`; expressions have no date type (brief, D20), and adding one is a decision of its
   own. The sensitive example is a `national_id`, a text.
9. **Hiding and encrypting are different promises** (layer 9a). `visible_to` filters the case view;
   only `sensitive` keeps a value out of Temporal's plain history.
