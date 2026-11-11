from ventoux import Case, Field, Outcome

claim = Case("claim", title="Insurance claim")

branch = claim.field("branch", Field.option("branches"), title="Branch handling the claim")

claim.task(
    "assess",
    title="Assess the claim",
    roles=["adjuster"],
    outcomes={
        "accept": Outcome("Accept the claim", sets=[branch]),
        "deny": Outcome("Deny the claim"),
    },
)
