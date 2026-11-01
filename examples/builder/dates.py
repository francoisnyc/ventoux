from datetime import date

from ventoux import Case, Field, Outcome, and_

claim = Case("claim", title="Insurance claim")

policy_start = claim.field("policy_start", Field.date(), title="Policy start")
incident = claim.field("incident_date", Field.date(), title="Date of the incident")

assess = claim.task(
    "assess",
    title="Assess the claim",
    roles=["adjuster"],
    outcomes={
        "accept": Outcome("Accept the claim", sets=[incident]),
        "deny": Outcome("Deny the claim"),
    },
)

claim.task(
    "settle",
    title="Settle the claim",
    roles=["adjuster"],
    requires=[assess],
    # Two dates the case file holds, compared: the same answer on every replay (brief, D20).
    when=and_(
        assess.outcome == "accept",
        incident >= policy_start,
        incident < date(2027, 1, 1),
    ),
    outcomes={"settled": Outcome("Claim settled")},
)
