"""Roles: who may answer a wait, and the highest risk each may approve (layer 7; brief, D22).

Roles are registered in the catalog by the platform team, like source labels. Who has which role
is never looked up here: it comes with each answer, stated by the trusted caller (brief, D19).
"""

from ventoux.core.provenance import is_label

# The risks a contract declares, from least to most (layer 1), so a role that may approve `high`
# may approve `medium` and `low` too.
RISKS = ("low", "medium", "high")


def checked_role(name: str, approves: str | None) -> None:
    """Refuse a role not written as a label, or an `approves` that isn't a risk."""
    if not is_label(name):
        raise ValueError(
            f"{name!r} is not a role: a role is lowercase, such as support or support-lead."
        )
    if approves is not None and approves not in RISKS:
        raise ValueError(
            f"{approves!r} is not a risk: a role approves up to {', '.join(RISKS[:-1])} or "
            f"{RISKS[-1]}, or nothing."
        )


def may_approve(approves: str | None, risk: str) -> bool:
    """Whether a role registered to approve up to `approves` may approve an activity of `risk`."""
    # Fail closed: a role that approves nothing, or a risk this list doesn't know, approves nothing.
    if approves is None or risk not in RISKS:
        return False
    return RISKS.index(risk) <= RISKS.index(approves)
