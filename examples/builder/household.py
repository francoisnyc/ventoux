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
