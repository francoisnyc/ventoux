# Quickstart: your first case in 15 minutes

> **Design draft.** This page describes how Ventoux is meant to work; none of it is built yet. It is
> written first, on purpose: if a step here is hard to explain, the design changes. The "Design notes"
> at the end list what writing it revealed.

You'll build a refund process: a support agent reviews the request, and the refund is paid. Refunds
over 100 also need a team lead's approval. On the way you'll meet five ideas: a **case**, its
**case file**, **steps**, **approvals** and **rules**.

## 1. Install and create a project

```sh
uv init refunds && cd refunds
uv add ventoux
uv run ventoux init
```

`ventoux init` creates a `cases/` folder and a development catalog with example activities, such as
`payments.refund@2`, which runs against a fake payment system.

## 2. Describe the case

A **case** is one piece of work that runs until it's done, like one customer's refund. Its **case
file** holds the data. Its **steps** are the work: a person's task, or a call to a system.

Create `cases/refund.py`:

```python
from ventoux import Approval, Case, Field, Outcome

refund = Case("refund", title="Customer refund")

order_id = refund.reference("order_id", system="orders", title="Order")
amount = refund.field("amount", Field.number(), title="Amount requested")
approved = refund.field("approved_amount", Field.number(), title="Amount approved")

review = refund.task(
    "review",
    title="Review the refund request",
    roles=["support"],
    outcomes={
        "approve": Outcome("Approve the refund", sets=[approved]),
        "reject": Outcome("Reject the refund"),
    },
)

pay = refund.activity(
    "pay",
    "payments.refund@2",
    title="Refund the customer",
    inputs={"order_id": order_id, "amount": approved},
    when=review.outcome == "approve",
    approval=Approval(
        when=approved > 100,
        roles=["support-lead"],
        reason="Refunds over 100 need a team lead",
    ),
)

refund.sequence(review, pay)

call_customer = refund.task(
    "call_customer",
    title="Call the customer about the declined refund",
    roles=["support"],
    requires=[pay],
    when=pay.outcome == "declined",
    outcomes={"called": Outcome("Customer called")},
)
```

What this says:
- `order_id` is a **reference** to an order kept in your order system; `amount` and
  `approved_amount` are facts the case decides on. Case files hold facts and references, not copies
  of your records (see the guide "Case data").
- `review` is a **task** for someone with the `support` role, who answers with one of two
  **outcomes**: *approve*, entering the amount approved, or *reject*. The inbox draws the form from
  the outcome. A misspelled outcome (`"aprove"`) is caught by `ventoux check`.
- `pay` calls the `payments.refund@2` activity with the order and the approved amount, the value a
  person confirmed.
- `when=…` is a **rule**: `pay` only runs if the review was approved.
- `approval=…`: when the amount actually paid is above 100, someone with the `support-lead` role must approve the payment, and it
  can't be the person who reviewed it, since the reviewer set the amount being paid.
- `sequence(review, pay)`: the steps run in this order, each starting by itself when the previous
  one is done.
- `call_customer`: the payment provider may decline a refund, an outcome `payments.refund@2`
  declares. Then someone in support calls the customer. Without this step a declined refund would
  close the case with nobody told, and `ventoux check` would warn you about it.
- The case closes when nothing is left to do: after the payment, after a rejected review, or once
  the customer has been called about a declined refund. While it waits for the team lead's
  approval, it stays open.

## 3. Check it

```sh
uv run ventoux check
```

```text
✓ refund is valid (3 steps)
  review         task for support · outcomes: approve (sets approved_amount), reject
  pay            runs payments.refund@2 · only after review = approve
                 · needs approval by support-lead when approved_amount > 100
  call_customer  task for support · only after pay = declined
  Case map: build/refund.md
```

`ventoux check` also writes `build/refund.json`, the definition Ventoux actually runs. You never edit
it by hand: it's generated from your Python file, and you commit both.

## 4. Run it

```sh
uv run ventoux dev
```

This starts Ventoux in memory with a local inbox at http://localhost:8090. Open a case:

```sh
uv run ventoux start refund --file order_id=ord-1 amount=250
```

In the inbox, sign in as `ana` (role `support`), approve the review and enter 250 as the approved
amount. Because the amount is over
100, a task appears for `sam` (role `support-lead`). Approve it, and the fake payment system records
a refund. The case history shows who did what, and when.

## 5. Test it

Create `tests/test_refund.py`:

```python
from ventoux.testing import run_case
from cases.refund import refund

# Who has which role. In production the Ventoux API states each person's roles with their answer;
# in tests, this plays that part.
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"]}


def test_small_refund_needs_no_team_lead():
    run = run_case(refund, file={"order_id": "ord-1", "amount": 40},
                   answers=[("review", "approve", "ana", {"approved_amount": 40})],
                   people=PEOPLE)
    assert run.closed
    assert run.reached("pay")


def test_large_refund_waits_for_a_team_lead():
    run = run_case(refund, file={"order_id": "ord-2", "amount": 250},
                   answers=[("review", "approve", "ana", {"approved_amount": 250})],
                   people=PEOPLE)
    assert run.waiting_for == ["approval of pay by support-lead"]
    assert not run.reached("pay")
    assert not run.closed


def test_rejected_review_closes_without_paying():
    run = run_case(refund, file={"order_id": "ord-3", "amount": 250},
                   answers=[("review", "reject", "ana")],
                   people=PEOPLE)
    assert run.closed
    assert not run.reached("pay")
```

```sh
uv run pytest
```

Tests run in memory, in milliseconds, with no Temporal server. A case nobody has answered yet says
what it waits for: with `answers=[]`, `run.waiting_for == ["review by support"]`.

## 6. When Ventoux says no

Suppose you let customers write a message with their request, and you pay the amount they typed:

```python
message_amount = refund.field("customer_amount", Field.number(), title="Amount the customer asked for",
                              source="untrusted:customer")
# …
inputs={"order_id": order_id, "amount": message_amount}
```

```text
✗ refund: pay.inputs.amount comes from customer_amount, which the customer typed (untrusted).
  payments.refund@2 takes amount only from a system or a person, never from untrusted data.
  Use a value a person confirmed, for example `approved_amount`, set by the reviewer.
```

You didn't write any security rule: the platform team set it once on `payments.refund@2`, as an
input policy on `amount`. Ventoux checks it for every case that uses the activity.

Ventoux also says no to people. Sam is a team lead, but suppose Sam reviewed the request too:

```python
run_case(refund, file={"order_id": "ord-4", "amount": 250},
         answers=[("review", "approve", "sam", {"approved_amount": 250}),
                  ("pay", "approve", "sam")],
         people=PEOPLE)
```

```text
AnswerRefused: sam set approved_amount, which pay uses, so cannot approve it
```

You never listed who may not approve: Sam's answer set the amount `pay` sends, so the approval
must come from someone else. A team lead's *reject* is an answer too: `pay` doesn't run, and the
case closes.

## 7. Change it

Finance now wants the customer told when a refund is rejected. Add a step and a rule:

```python
notify = refund.activity(
    "notify_rejection", "letters.draft@2",
    title="Draft a rejection letter",
    inputs={"order_id": order_id},
    requires=[review],
    when=review.outcome == "reject",
)
```

`requires=[review]`: the condition reads the review's answer, which exists only once the review is
done. Reading a value nobody has given yet is an error, never "false", so the step says what it
waits for.

```sh
uv run ventoux diff
```

```text
refund: changes since the last release
+ step "Draft a rejection letter" (letters.draft@2), runs when the review is rejected
  No change to approvals or to where values come from.
  This change creates a new release.
```

Open a pull request: the same summary appears there, for your reviewers and your business owner.

## Next

- **Deploy on Temporal:** run Ventoux on your own Temporal, release and activate a case.
- **Add your own activity:** register a system call with its contract (for the platform team; the
  guide "Activities").
- **Use an existing Temporal workflow as a step** (the guide "Cases", "Workflow steps"; its
  contract in the guide "Activities").
- **Change cases that are already open:** migration.
- **When things fail:** retries, declined payments and the "needs attention" queue.
- **Case data:** references, sensitive fields and forgetting a person (the guide "Case data").

---

## Design notes: what writing this revealed

Writing the page surfaced decisions the brief doesn't make yet:

1. **Task outcomes are core, not an extra** (decided: D9). The first example already needs a task
   with named outcomes and rules that read them. Writing the example also showed that an approval
   must read the value its step uses: guarding `amount` while paying `approved_amount` would let a
   reviewer's 250 slip past the team lead on an 80 request.
2. **Closing needs a default** (decided: D10). "No step can run any more" was too loose: a case
   waiting for an approval can't run a step either. The default is now "nothing is left to do": no
   running step, no open task or approval, no timer set, no explicit wait.
3. **Approvals need roles and a "not the same person" rule by default** (decided: D11). "Someone
   else" is computed from provenance: whoever's answer flows into the step can't approve it, and an
   approval lapses if the values it saw change.
4. **The builder reads best as Python objects, not strings.** `amount > 100` and
   `review.outcome == "approve"` work through operator overloading on field and step objects; this
   settles how typed expressions look in Python.
5. **Untrusted fields need a short way to say so.** `source="untrusted:customer"` on a field is the
   first place a developer meets provenance. Decided in D12: three origins (system, person,
   untrusted), registered labels, and fields can be declared untrusted, never trusted.
6. **`ventoux init` must ship a working catalog**, or step 2 fails. That's the platform team's job in
   production, but the quickstart needs it out of the box.
7. **Plans never appeared.** A first case needs tasks and activities only. This supports
   presenting plans as an advanced concept (multi-step plans, AI drafting), not a day-one one
   (decided: D13).
