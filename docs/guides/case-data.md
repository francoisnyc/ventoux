# Case data: what goes in the case file

> **Design draft.** This guide describes how Ventoux is meant to work; none of it is built yet. The
> "Design notes" at the end list what writing it revealed.

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

```python
from ventoux import Case, Field

claim = Case("claim", title="Insurance claim")

# 1. References: the ID of a record that lives elsewhere.
policy = claim.reference("policy_id", system="policies", title="Policy")
customer = claim.reference("customer_id", system="crm", title="Customer")
documents = claim.reference_list("document_ids", system="documents", title="Documents")

# 2. Decision facts: values your rules and steps use.
damage = claim.field("estimated_damage", Field.number(), title="Estimated damage")
decision = claim.field("decision", Field.choice("approved", "denied"), title="Decision")
payout = claim.field("payout", Field.number(), title="Payout")

# 3. Sensitive facts: needed for a decision, but personal.
birth_date = claim.field("birth_date", Field.date(), title="Date of birth", sensitive=True)
```

A quick test for each value you're tempted to store:

| Question | If yes |
|---|---|
| Is it a record or document that another system owns? | Store a **reference** |
| Does a rule, approval or step condition read it? | Store it as a **fact** |
| Is it needed only by one step (an address for a letter)? | **Don't store it:** let that step fetch it |
| Is it about a person, and needed for a decision? | Store it as a **sensitive** fact |
| Is it free text or large (notes, emails, files)? | Store a **reference** to where it's kept |

## Fetching data where it's used

A step that needs a customer's postal address gets the **reference** and fetches the address itself:

```python
deny = claim.activity(
    "deny", "letters.draft@2",
    title="Draft the denial letter",
    inputs={"customer": customer, "claim": claim.id},
    when=decision == "denied",
)
```

`letters.draft@2` looks up the address in the CRM when it runs, so the letter always uses the
current address, and the address never enters the case history. Activities that work this way take
references as inputs; the platform team designs them so.

## Where values come from

Every fact remembers where it came from, and when. You rarely need to think about it, but it's why
Ventoux can stop an unsafe step:

| A value that comes from… | is… |
|---|---|
| the system that opened the case | trusted |
| a person's answer to a task | trusted |
| a registered system, through an activity | trusted if its contract says so |
| a customer's message, a document's text, an AI | **untrusted**: it can inform people, never decide |

You declare a field's source only when it's untrusted, using a label your platform team registered
(`customer`, `llm`, `document`…). You can't declare a field trusted: trust comes from a contract or a
person's answer.

```python
claim.field("customer_estimate", Field.number(), title="Customer's own estimate",
            source="untrusted:customer")
```

## Sensitive data and the right to be forgotten

A field marked `sensitive=True`:
- is encrypted with a key that belongs to that case, so it never appears in plain text in history;
- is shown only to people whose roles may see it (`visible_to=["claims-sensitive"]`); others see
  that it exists and is hidden;
- can be **erased**: `ventoux forget claim CLM-7` asks to forget the case's person. Once someone with
  the data protection role approves, the case closes (if it was open, running steps finish first)
  and its key is destroyed. The history and the export keep every decision and who made it, but
  the sensitive values become unreadable everywhere, including copies already exported.

Your platform team runs the key provider (for example Vault or a cloud KMS). In development, keys
are kept in a local file.

## Reports

To answer questions across cases ("every claim above 10,000 this quarter"), use the **case export**,
which copies case events and facts to your data warehouse or database. Don't query running cases.
Sensitive values stay encrypted in the export, under the case's key, so forgetting a person reaches
the warehouse too.

## Common questions

- **Can I store a document in a case?** No. Store it in your document system and keep its reference.
- **The record changed after the case read it. Which value counts?** The fact in the case file, as
  obtained at that time; it records when. If a step must not run on an old value, say so with
  `max_age={"policy_status": days(1)}`: when it's older, Ventoux runs the lookup again first.
- **Can I see the referenced record in the case view?** Yes: the inbox shows referenced records by
  asking their system, on your behalf: you see what that system lets you see. Nothing shown is
  stored in the case. If what you saw matters to your decision, record it as a fact (for example,
  in your answer to the task).

---

## Design notes: what writing this revealed

1. **References need a type of their own** (`claim.reference(…, system=…)`), not a plain text field.
   The `system` name links them to how views and activities resolve them (decided: D16).
2. **Activities should take references, not copies.** That's guidance for the platform team when
   designing contracts; it belongs in the "Add your own activity" guide.
3. **Views need resolvers.** To show a referenced record, the inbox must call something per system
   (`policies`, `crm`, `documents`). That's a new extension point for the platform team (decided:
   D16: read-only, called on behalf of the viewer, never stored).
4. **Erasure needs a key service** (decided: D15). Per-case keys through a key provider, in v1.0;
   forgetting is a change request that closes an open case first; exports carry ciphertext.
5. **Facts record when they were obtained** (decided: D18). Workflow time, an optional as-of time
   from the source, `max_age` where a step uses a fact, and stale facts refreshed by re-running a
   read-only lookup.
6. **Erasure and audit must coexist.** The audit trail keeps that a decision happened, by whom and
   on which rule, but not the erased values. The audit format must allow that.
7. **The quickstart's `order_id` is a reference.** It should use `refund.reference("order_id",
   system="orders")`, which also makes the quickstart teach the rule of thumb from the start.
