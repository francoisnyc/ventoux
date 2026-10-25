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
