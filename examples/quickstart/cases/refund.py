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
