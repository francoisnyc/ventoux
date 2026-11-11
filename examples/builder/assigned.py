from ventoux import Approval, Assign, Case, Field, Outcome

refund = Case("refund", title="Customer refund")

order_id = refund.reference("order_id", system="orders", title="Order")
approved = refund.field("approved_amount", Field.number(), title="Amount approved")

# Asked of whoever opened the request: `"assign": {"to": "opener"}` in the JSON (brief, D71).
confirm = refund.task(
    "confirm",
    title="Confirm the request's details",
    roles=["support"],
    outcomes={"confirmed": Outcome("Details confirmed")},
    assign=Assign.opener(),
)

review = refund.task(
    "review",
    title="Review the refund request",
    roles=["support"],
    requires=[confirm],
    outcomes={
        "approve": Outcome("Approve the refund", sets=[approved]),
        "reject": Outcome("Reject the refund"),
    },
)

# A team lead picks who approves; their answer reaches nothing the payment reads.
triage = refund.task(
    "triage",
    title="Take the refund for approval",
    roles=["support-lead"],
    requires=[review],
    outcomes={"taken": Outcome("Taken")},
)

pay = refund.activity(
    "pay",
    "payments.refund@2",
    title="Refund the customer",
    inputs={"order_id": order_id, "amount": approved},
    requires=[triage],
    when=review.outcome == "approve",
    # Asked of whoever took it: `"assign": {"to": "answered", "step": "triage"}`.
    approval=Approval(
        roles=["support-lead"],
        reason="Refunds need a team lead",
        assign=Assign.answered(triage),
    ),
)

# Asked of whoever did the review.
refund.task(
    "follow_up",
    title="Follow up with the customer",
    roles=["support"],
    requires=[pay],
    outcomes={"done": Outcome("Done")},
    assign=Assign.answered(review),
)
