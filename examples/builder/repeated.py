from ventoux import Case, Field, ForEach, Outcome, literal

order_return = Case("order-return", title="A returned order")

order_id = order_return.reference("order_id", system="orders", title="Order")
email = order_return.field("email", Field.string(), title="Customer email")
lines = order_return.field(
    "lines", Field.list(sku=Field.string(), amount=Field.number()), title="Returned lines"
)

# One run per line, each told apart by its sku: `"for_each": {"over": "lines", "key": "sku"}` in
# the JSON (brief, D73).
each_line = ForEach(lines, key="sku")

order_return.task(
    "inspect_line",
    title="Inspect a returned line",
    roles=["support"],
    outcomes={"received": Outcome("Received"), "missing": Outcome("Missing")},
    for_each=each_line,
)

order_return.activity(
    "draft_line",
    "letters.draft@2",
    title="Draft a letter about one line",
    inputs={"to_customer": email, "template": literal("line-returned")},
    for_each=each_line,
)
