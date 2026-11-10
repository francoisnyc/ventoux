# Shows a role registered twice in a catalog taking the second `approves` in silence, up or down, while what it operates only ever adds; a contract registered twice with other content is refused.
"""Run: uv run python reviews/2026-11/probes/p3_role_registered_twice.py

Past the supported names: `ventoux.core.catalog.Catalog`, the platform team's own.
"""

from ventoux.core.catalog import Catalog

catalog = Catalog()
catalog.register_role("support")
catalog.register_role("support", approves="high")  # a second module's line, or a merge
print("support, then support approving high:", catalog.roles)
catalog.register_role("lead", approves="high", operates=True)
catalog.register_role("lead")
print("lead approving high and operating, then lead alone:", catalog.roles, catalog.operators)
if catalog.roles["support"] == "high":
    print(
        "RESULT: BROKEN - registering a role again rewrites what it may approve, looser included, "
        "with no error; `operates` stays from the first"
    )
else:
    print("RESULT: HELD - a role registered twice with other rights is refused")
