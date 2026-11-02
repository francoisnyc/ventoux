from ventoux import Case, Field, Outcome

claim = Case("claim", title="Insurance claim")

receipt = claim.field("receipt", Field.attachment("documents"), title="The receipt")

claim.task(
    "assess",
    title="Assess the claim",
    roles=["adjuster"],
    outcomes={
        "accept": Outcome("Accept the claim", sets=[receipt]),
        "deny": Outcome("Deny the claim"),
    },
)
