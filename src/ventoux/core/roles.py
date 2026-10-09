"""Roles: who may answer a wait, and the highest risk each may approve (brief, D22).

Roles are registered in the catalog by the platform team, like source labels. Who has which role
is never looked up here: it comes with each answer, stated by the trusted caller (brief, D19).
"""

from collections.abc import Mapping

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


def role_that_counts(
    allowed: tuple[str, ...], stated: frozenset[str], registered: Mapping[str, str | None]
) -> str | None:
    """The role that lets a person answer: the first, in order, of the roles they have that the
    wait allows and the catalog registered. None: no role of theirs counts."""
    # Fail closed: a role the catalog doesn't know counts for nothing, whoever states it.
    counting = sorted(role for role in stated if role in allowed and role in registered)
    return counting[0] if counting else None


def no_role(
    entry: str,
    allowed: tuple[str, ...],
    by: str,
    stated: frozenset[str],
    registered: Mapping[str, str | None],
) -> str:
    """Why `by` may not answer `entry`: the roles it needs, and the ones they have."""
    known = ", ".join(sorted(role for role in stated if role in registered)) or "no role"
    return f"{entry} is answered by {' or '.join(allowed)}, and {by} has {known}"


def what_it_approves(approves: str | None) -> str:
    """What a role may approve, as a message says it: `no risk`, `up to medium risk`."""
    return "no risk" if approves is None else f"up to {approves} risk"
