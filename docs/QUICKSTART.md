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

### Where the order system comes in

`system="orders"` is a name, not a connection: a case holds no URL and no password. `orders` is a
system your platform team registers in the catalog (the development catalog registers it for you),
and a case naming a system nobody registered is refused when it opens. The case file holds the
order's ID, `ord-1`; the order stays in your order system. Ventoux reaches it in three ways, each
set up by the platform team, never by the case:

- **When the case opens,** whoever opens it gives the ID: your order service, the customer portal,
  or `ventoux start` in step 4. Only the ID enters the case file.
- **When a step runs,** an activity calls the order system. `pay` gives `ord-1` to
  `payments.refund@2`, and the worker that runs the activity holds the connection, its address and
  its credentials. To decide on something about the order, such as whether it was delivered, add a
  step that fetches it (a lookup activity such as `orders.lookup@2`): its answer becomes a fact in
  the case file, saying it came from the order system.
- **When a person looks,** the inbox shows the order through a **resolver** the platform team
  registers for `orders`. It asks the order system as the person looking, so the order system's
  own permissions decide what they see:

```python
from ventoux.tooling.resolvers import Resolvers, Viewer


def show_order(reference: str, viewer: Viewer) -> dict[str, object]:
    # Your order system's client, asked as the person looking.
    return orders_api.order(reference, on_behalf_of=viewer.person)


resolvers = Resolvers(catalog)
resolvers.register("orders", show_order)
```

What a resolver returns is shown, never stored: the case history records only
`ana was shown order_id (orders ord-1)`. If what Ana saw matters to her decision, it belongs in her
answer (`approved_amount`) or in a step that fetches it. The development catalog registers no
resolver, so the local inbox shows the ID and says why there is no more:
`orders has no resolver: register one to show its records`.

A contract can also require a reference to one system. `letters.draft@3` takes its `customer` as
`Annotated[str, reference("crm")]`, so `ventoux check` refuses a policy ID where a customer is
expected (the guide "Activities", "Systems and resolvers"). `payments.refund@2` doesn't: it takes
any order ID a system or a person gave. A production payment contract would declare
`reference("orders")`.

## 3. Check it

```sh
uv run ventoux check
```

```text
✓ refund is valid (3 steps): packages/refund/
```

`ventoux check` runs your Python file, checks the definition it writes against your deployment's
catalog, and writes `packages/refund/case.json`, the definition Ventoux actually runs. You never
edit it by hand: it's generated from your Python file, and you commit both. Nothing is written
unless every case is valid. In CI, `ventoux check --unchanged` generates it again and fails if the
committed JSON isn't what your Python writes. `uv run ventoux map packages/refund` prints what a refund case can
do, and what it will never do.

The catalog is named in your project's `pyproject.toml`, which `ventoux init` writes:

```toml
[tool.ventoux]
catalog = "ventoux.testing:CATALOG"
```

That is the development catalog. In production the platform team names its own, the contracts and
roles your deployment really has, and `ventoux check` refuses to run with no catalog named rather
than guess one.

*Changed 2026-10-25, in layer 14c:* this section showed one line per step, a case map in
`build/refund.md`, and `build/refund.json`. A package is a folder (brief, D50), and `build/` is
ignored by most repositories, so the JSON that runs would never be reviewed: it is
`packages/refund/case.json` now. The case map is `ventoux map`'s.

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
cases/refund.py:19: steps.pay.inputs.amount INPUT_POLICY: payments.refund@2 takes amount only from a system or a person, never from untrusted data, and this value comes from customer_amount (the opener, untrusted:customer): use a value a system or a person gave
✗ refund is refused: 1 error.
Nothing was written.
```

The line is the call that wrote the step, `refund.activity("pay", …)`, and the path and the code
are the check's own: the same rule refuses the release.

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
8. **The payment contract doesn't name its system.** `payments.refund@2` takes `order_id` as any
   trusted text, so the quickstart can describe the check that a reference goes where its system is
   expected (D30) but not show it on its own case. Showing it needs `payments.refund@3`, declaring
   `reference("orders")`: a new contract version, never an edit of `@2` (D5). Left for now: a
   first case meets the idea, and the activities guide shows the refusal.
