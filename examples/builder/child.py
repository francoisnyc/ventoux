from ventoux import Approval, Case, Field, Outcome

# The cases guide's repair, a case of its own: a garage lead fixes the vehicle and says the cost.
repair = Case("repair", title="Vehicle repair")

repair.field("vehicle", Field.string(), title="Vehicle")
repair.field("budget", Field.number(), title="Budget")
cost = repair.field("cost", Field.number(), title="Cost")
fixed = repair.milestone("fixed", title="Vehicle fixed")

repair.task(
    "fix",
    title="Fix the vehicle",
    roles=["support-lead"],
    outcomes={"fixed": Outcome("Fixed", sets=[cost], reaches=[fixed])},
)

# What it says to the case that opened it, when it closes: `"reports": ["cost"]` (brief, D74).
repair.reports(cost)

# The claim that opens it, pinning its release 3: `"case": "repair@3"` in the JSON.
claim = Case("claim", title="Insurance claim")

order_id = claim.reference("order_id", system="orders", title="Order")
vehicle = claim.field("vehicle", Field.string(), title="Vehicle")
payout = claim.field("payout", Field.number(), title="Payout")
assessed = claim.milestone("assessed", title="Claim assessed")

claim.task(
    "assess",
    title="Assess the claim",
    roles=["support"],
    outcomes={"accept": Outcome("Accept the claim", sets=[payout], reaches=[assessed])},
)

fixing = claim.child_case(
    "repair",
    repair,
    release=3,
    title="Repair the vehicle",
    requires=[assessed],
    inputs={"vehicle": vehicle, "budget": payout},
)

# What the child reports is read as the step's outputs, with where each came from.
claim.activity(
    "pay_garage",
    "payments.refund@2",
    title="Pay the garage",
    requires=[fixing],
    inputs={"order_id": order_id, "amount": fixing.output("cost", Field.number())},
    approval=Approval(roles=["support-lead"], reason="Every payout needs a team lead"),
)

# A claim whose repair opens only on a payout set within the last 30 days: a case step reads its
# facts fresh, as a call does (brief, D18).
recent = Case("recent-claim", title="A recent insurance claim")

recent_payout = recent.field("payout", Field.number(), title="Payout")

recent.child_case(
    "repair",
    repair,
    release=3,
    title="Repair the vehicle",
    inputs={"budget": recent_payout},
    max_age={"payout": "30d"},
)
