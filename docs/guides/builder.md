# The Python builder: definitions written as code

> **For workflow developers.** You write a case, and the plans it runs, in Python. Running the
> file writes JSON, and that JSON is what Ventoux checks, releases and runs. This guide shows each
> part of the format as the builder writes it. The JSON itself, and what each part means, is the
> cases guide's and the plans guide's.

## Code that produces data

The builder writes data and decides nothing. Each call writes one entry of the JSON, under the
same name: `claim.task("assess", …)` writes `steps.assess`, `claim.sla("escalate", …)` writes
`rules.escalate`. What it writes is checked later, by `ventoux check` and again by the engine; the
builder refuses only what keeps it from writing the JSON as you gave it:

- a Python value where a runtime expression is required (`when=True`);
- two entries of one name, a second `sequence`, `closes_when` or plan `initial`;
- a number that would read back as another (`Decimal("1E+2")`), a `float`, or `True` as a number;
- a list's or an event's field read as a type it isn't declared with.

Everything else, a high-risk payment with no approval, a plan path chosen by untrusted data, a
sensitive field given to a workflow step, is written as given, and `ventoux check` refuses it,
naming the rule.

**Build time and runtime.** A field is a value each case holds, so `approved > 100` is an
`Expr[bool]`, decided by each case, never `True` or `False` when the file runs. A Python value beside
it (`100`) is a literal, written into the JSON. Where the format needs an expression, the builder's
parameter is typed `Expr`, so mypy refuses a plain value. `if approved > 100:` in your file raises:
use `when=`. `and`, `or` and `not` are `and_`, `or_` and `not_`; the other operators are
`if_`, `in_`, `cat`, `string`, `exists`, `count` and `sum_`. `==` compares the same kind: a number
with a number, a text with a text, an outcome with its name, a reference with a reference. A
mismatched `==`, `review.outcome == 5`, is reported where you use it, not where you write it: Python
falls back to the other side's own `==`, so mypy reads the comparison as a plain `bool`, and says
`incompatible type "bool"; expected "Expr[bool] | None"` at the `when=` it is given to. When the
file runs, the comparison itself raises.

**What the builder can't know** is written as you declare it: a step's output,
`kyc.output("risk_score", Field.number())`, is checked against the contract by `ventoux check`.

## Approvals by several people: `four_eyes`

The four-eyes refund, `examples/refund/refund-four-eyes.json` in Python. `four_eyes(...)` is an
approval by two different people, `"count": 2` in the JSON (cases guide, "Approvals by several
people").

`examples/builder/four_eyes.py`:

```python
from ventoux import Case, Field, Outcome, four_eyes

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
    # Two different team leads: `"count": 2` in the JSON (brief, D47).
    approval=four_eyes(
        when=approved > 10000,
        roles=["support-lead"],
        reason="Refunds over 10,000 need two team leads",
    ),
)

refund.sequence(review, pay)

refund.task(
    "call_customer",
    title="Call the customer about the declined refund",
    roles=["support"],
    requires=[pay],
    when=pay.outcome == "declined",
    outcomes={"called": Outcome("Customer called")},
)
```

## Patterns: `sla` and `reminder`

An sla measures each run of a step from its own start, and acts when the run isn't done in time.
There is no `since=`: measuring from the first start isn't offered. This is
`examples/claim/claim.json` in Python:

`examples/builder/claim.py`:

```python
from ventoux import Case, Field, Outcome, Then

claim = Case("claim", title="Insurance claim")

claimed = claim.field("claimed", Field.number(), title="Amount claimed")

assess = claim.task(
    "assess",
    title="Assess the claim",
    roles=["adjuster"],
    repeatable=True,
    proposed_by=["adjuster"],
    outcomes={"done": Outcome("Assessed")},
)
lead_review = claim.task(
    "lead_review",
    title="Review an assessment left too long",
    roles=["support-lead"],
    automatic=False,
    repeatable=True,
    outcomes={"reviewed": Outcome("Reviewed")},
)
claim.task(
    "settle",
    title="Settle the claim",
    roles=["support-lead"],
    requires=[assess],
    outcomes={"settled": Outcome("Claim settled")},
)

# Measured from each run's own start: `since=first_start` isn't offered (brief, D46).
claim.sla(
    "escalate",
    title="Escalate an assessment not done within five days",
    step=assess,
    within="5d",
    then=Then(start=[lead_review]),
)
```

A reminder starts a step after each age while a task is open. The reminded refund,
`examples/refund/refund-reminded.json`:

`examples/builder/reminded.py`:

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

refund.task(
    "call_customer",
    title="Call the customer about the declined refund",
    roles=["support"],
    requires=[pay],
    when=pay.outcome == "declined",
    outcomes={"called": Outcome("Customer called")},
)
remind = refund.task(
    "remind",
    title="Remind the reviewer",
    roles=["support-lead"],
    automatic=False,
    repeatable=True,
    outcomes={"reminded": Outcome("Reviewer reminded")},
)

# Each reminder starts `remind` after its age, while the review is open (brief, D46).
refund.reminder(
    "remind_review",
    title="Remind the reviewer of an open review",
    task=review,
    after=["1d", "2d", "4d"],
    start=remind,
)
```

## Every other part: a household claim

One claim using the rest of the format: fields of every type, a list read with `count` and
`sum_`, a sensitive field and fields others can't see, milestones, an event and a step that waits
for it, a workflow step and a plan step, every kind of rule moment, a timer, an sla and a reminder
with a condition, a close reason, and the plan the claim runs. The plan names its states by name,
as the JSON does, since a state may lead back to one made later.

`examples/builder/household.py`:

```python
from ventoux import (
    OPENED,
    Case,
    Field,
    Outcome,
    Payload,
    Plan,
    SentBy,
    Then,
    Transition,
    after,
    and_,
    cat,
    count,
    exists,
    if_,
    in_,
    literal,
    not_,
    or_,
    string,
    sum_,
)

# The plan that settles a claim: run as one step of the case, written beside it in its package.
settle_claim = Plan(
    "settle-claim", 1, title="Settle a claim", description="Check the order, confirm, then pay"
)
order = settle_claim.field("order_id", Field.reference("orders"))
payout = settle_claim.field("payout", Field.number())
remark = settle_claim.field("remark", Field.string(), source="untrusted:customer")
settle_claim.initial("check_order")
settle_claim.activity(
    "check_order",
    "orders.lookup@1",
    inputs={"order_id": order},
    on={"done": "confirm", "not_found": "failed"},
)
settle_claim.wait(
    "confirm",
    outcomes=["confirm", "adjust"],
    roles=["adjuster"],
    sets={"confirm": [payout], "adjust": [payout]},
    timeout="2d",
    on={
        "confirm": [Transition("failed", when=payout <= 0), Transition("approve_payout")],
        "adjust": "approve_payout",
        "timeout": "failed",
    },
)
settle_claim.approval(
    "approve_payout",
    of="pay",
    roles=["support-lead"],
    timeout="48h",
    on={"approve": "pay", "reject": "failed", "timeout": "failed"},
)
settle_claim.activity(
    "pay",
    "payments.refund@2",
    inputs={"order_id": order, "amount": payout},
    on={"done": "paid", "declined": "failed"},
)
settle_claim.final("paid", "succeeded")
settle_claim.final("failed", "failed")

household = Case(
    "household",
    title="Household claim",
    description="Water or fire damage at a customer's home",
    stays_open=False,
    forgetting="while_open",
)

customer = household.reference("customer_id", system="crm", title="Customer")
order_id = household.reference("order_id", system="orders", title="Insured order")
national_id = household.field(
    "national_id",
    Field.string(),
    title="National ID",
    sensitive=True,
    visible_to=["claims-sensitive"],
)
fraud_score = household.field(
    "fraud_score", Field.number(), title="Fraud score", visible_to=["fraud"]
)
estimate = household.field(
    "estimate", Field.number(), title="The customer's estimate", source="untrusted:customer"
)
damage = household.field("damage", Field.outcome("water", "fire"), title="Kind of damage")
urgent = household.field("urgent", Field.boolean(), title="Urgent")
items = household.field(
    "items", Field.list(amount=Field.number(), sku=Field.string()), title="Damaged items"
)
claimed = household.field("claimed", Field.number(), title="Amount claimed")
summary = household.field("summary", Field.string(), title="Summary")
total = household.field("total", Field.number(), title="Total of the items")
large_items = household.field("large_items", Field.number(), title="Items over 100")
adjusted = household.field("adjusted", Field.number(), title="Amount adjusted for urgency")

assessed = household.milestone("assessed", title="Claim assessed")
summarized = household.milestone("summarized", title="Claim summarized")
paid = household.milestone("paid", title="Claim paid", description="The payout was made")

withdrawn = household.event(
    "withdrawn",
    title="Withdrawn by the customer",
    sent_by=SentBy(system="portal"),
    payload={"reason": Payload(Field.string(), title="Reason", source="untrusted:customer")},
)
reopened = household.event("reopened", title="Reopened", sent_by=SentBy(roles=["adjuster"]))

kyc = household.workflow(
    "kyc", "kyc.check@1", title="Check the customer", inputs={"customer_id": customer}
)
lookup = household.activity(
    "lookup", "orders.lookup@2", title="Look up the order", inputs={"order_id": order_id}
)
assess = household.task(
    "assess",
    title="Assess the claim",
    roles=["adjuster"],
    requires=[kyc, lookup],
    when=kyc.output("risk_score", Field.number()) < 50,
    outcomes={
        "done": Outcome("Assessed", sets=[claimed], reaches=[assessed], description="Assessed"),
        "rejected": Outcome("Rejected"),
    },
)
notify = household.activity(
    "notify",
    "letters.draft@3",
    title="Draft a letter to the customer",
    inputs={"customer": customer, "template": literal("claim-received")},
    requires=[lookup],
    when=lookup.output("status", Field.string()) == "delivered",
    max_age={"lookup.status": "1d"},
    automatic=False,
    proposed_by=["adjuster"],
    repeatable=True,
)
settle = household.plan_step(
    "settle",
    settle_claim,
    title="Settle the claim",
    inputs={"order_id": order_id, "remark": summary},
    requires=[assessed],
    when=lookup.output("status", Field.string()) == "delivered",
    max_age={"lookup.status": "1d"},
    reaches=[paid],
)
withdrawal = household.wait("withdrawal", withdrawn, title="Wait for a withdrawal")

household.rule(
    "urgent_letter",
    title="Draft a letter at once for an urgent claim",
    on=OPENED,
    when=urgent,
    then=Then(start=[notify]),
)
household.rule(
    "remind_after_a_month",
    title="Draft a reminder a month after opening",
    on=after("30d", since=OPENED),
    then=Then(start=[notify]),
)
household.rule(
    "count_the_items",
    title="Count the items when the assessment starts",
    on=assess.started,
    then=Then(
        set=[
            (total, sum_(items, value=items.number("amount"), where=items.text("sku") != "")),
            (large_items, count(items, where=items.number("amount") >= 100)),
        ]
    ),
)
household.rule(
    "summarize",
    title="Summarize the assessment",
    on=assess.answered,
    when=and_(
        exists(claimed),
        or_(claimed > 100, not_(claimed <= 10)),
        claimed != 0,
        in_(damage, ["water", "fire"]),
    ),
    then=Then(
        set=[
            (summary, cat("Claim for ", string(order_id), ": ", string(claimed))),
            (adjusted, if_(urgent, claimed * 2 - 1, claimed / 2 + 1)),
        ],
        reach=[summarized],
    ),
)
household.rule(
    "letter_once_assessed",
    title="Draft a letter once the claim is assessed",
    on=assessed.reached,
    then=Then(start=[notify]),
)
household.rule(
    "stop_waiting",
    title="Stop waiting for a withdrawal once reopened",
    on=reopened.arrived,
    then=Then(stop=[withdrawal]),
)
household.rule(
    "withdraw",
    title="Stop settling a withdrawn claim",
    on=withdrawn.arrived,
    then=Then(stop=[settle]),
)
household.sla(
    "assessment_late",
    title="Draft a letter when an urgent assessment takes over two days",
    step=assess,
    within="2d",
    when=urgent,
    then=Then(start=[notify]),
)
household.reminder(
    "remind_assessor",
    title="Remind the assessor of an urgent claim",
    task=assess,
    after=["1d"],
    start=notify,
    when=urgent,
)
household.close_reason("withdrawn_by_customer", title="Withdrawn", roles=["adjuster"])
household.closes_when(paid)
```

`ventoux check` accepts it, with warnings, such as a value read before it is surely set
(cases guide, "What `ventoux check` proves about a case").

## Forgetting

Whether a request may forget a case: `allowed`, `while_open` (the household claim) or `never`.

`examples/builder/forgetting.py`:

```python
from ventoux import Case, Outcome

# Whether a request may forget a case, and so the people in it (brief, D32).
ticket = Case("ticket", title="Support ticket", forgetting="allowed")
ticket.task(
    "answer", title="Answer the ticket", roles=["support"], outcomes={"done": Outcome("Answered")}
)

invoice = Case("invoice", title="Invoice dispute", forgetting="never")
invoice.task(
    "settle",
    title="Settle the dispute",
    roles=["support-lead"],
    outcomes={"done": Outcome("Settled")},
)
```

## A package

A case and the plans its plan steps run are one package (releases guide). `package(case)` gives
its files: `case.json`, and `plans/<plan>.json` for each plan a plan step names. The refund
package, `examples/packages/refund/`, is written from:

`examples/cases/refund.py`:

```python
"""The refund package: the customer refund, settled by a plan (brief, D50). Written in Python; its
JSON, `examples/packages/refund/`, is what is checked, released and run (brief, D58)."""

from ventoux import Case, Field, Outcome, Plan

refund_order = Plan("refund-order", 1, title="Refund an order")
order = refund_order.field("order_id", Field.reference("orders"))
to_refund = refund_order.field("amount", Field.number())
refund_order.initial("check_order")
refund_order.activity(
    "check_order",
    "orders.lookup@1",
    inputs={"order_id": order},
    on={"done": "approve_refund", "not_found": "failed"},
)
refund_order.approval(
    "approve_refund",
    of="pay",
    roles=["support-lead"],
    timeout="48h",
    on={"approve": "pay", "reject": "failed", "timeout": "failed"},
)
refund_order.activity(
    "pay",
    "payments.refund@2",
    inputs={"order_id": order, "amount": to_refund},
    on={"done": "paid", "declined": "failed"},
)
refund_order.final("paid", "succeeded")
refund_order.final("failed", "failed")

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

settle = refund.plan_step(
    "settle",
    refund_order,
    title="Settle the refund",
    inputs={"order_id": order_id, "amount": approved},
    requires=[review],
    when=review.outcome == "approve",
)

refund.task(
    "call_customer",
    title="Call the customer about the declined refund",
    roles=["support"],
    requires=[settle],
    when=settle.outcome == "failed",
    outcomes={"called": Outcome("Customer called")},
)
```

Its JSON is committed beside it, where git keeps it (`packages/`, never `build/`, which most
repositories ignore), and a test regenerates it and compares it byte for byte.

## Checking a builder file

```sh
uv run ventoux check
```

`ventoux check` runs every builder file in `cases/` (or the files you name), checks each case it
finds, with the plans its plan steps run, against your deployment's catalog, and says each problem
at the line of the builder call that wrote it, with the path and the code the check gives:

```text
cases/refund.py:19: steps.pay.inputs.amount INPUT_POLICY: payments.refund@2 takes amount only from …
✗ refund is refused: 1 error.
Nothing was written.
```

The check is the one `ventoux release` refuses on, never a second set of rules. Only if every case
passes are the packages written, each into `packages/<case>/` holding exactly its files, which you
commit. A builder file that raises is refused at the line inside it where it raised, and nothing is
written. Warnings, such as a step untrusted data may keep from starting (`KEPT_FROM_STARTING`), are
printed and refuse nothing.

The catalog is your deployment's, named in `pyproject.toml`:

```toml
[tool.ventoux]
catalog = "acme_platform.catalog:CATALOG"
cases = "cases"
packages = "packages"
```

or with `--catalog`, which wins. It is the platform team's code, imported by that name; with none
named, every command that reads contracts or roles refuses to run. The development catalog is
`ventoux.testing:CATALOG`, used only when named.

A builder file is your team's own code, reviewed like any code: `ventoux check` never runs a file a
definition names, and never what a model wrote. A model's draft is JSON, checked as JSON.
