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
