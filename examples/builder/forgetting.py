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
