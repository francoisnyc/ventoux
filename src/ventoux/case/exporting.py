"""The audit export, as the case decides about it: failed, then retried by an operator
(layer 19b).

The export itself runs outside the case, in its driver (`ventoux.temporal.cases`), which tells the
case when it has failed. A failed export needs attention, as a failed step does, and only an
operating role retries it (brief, D17) (brief, D26) (brief, D77).
See docs/layers/19-audit-keys.md (19b).
"""

from ventoux.case.admission import RetryRefused
from ventoux.case.audit import Decision
from ventoux.case.state import CaseState, ExportFailed, ExportRetried
from ventoux.core.catalog import Catalog
from ventoux.core.person import identifier_problem

# What the export is named as, wherever a decision or a line names it.
EXPORT = "audit export"


def export_failed(state: CaseState, event: ExportFailed) -> None:
    """The export failed after its retries: the records wait, and an operator looks."""
    state.export_failed = event.reason
    state.history.append(f"audit export failed: {event.reason}")
    state.deciding.append(Decision("failed", target=EXPORT, reason=event.reason))


def export_retried(catalog: Catalog, state: CaseState, event: ExportRetried) -> None:
    """An operator retries the failed export; refused for anyone else, or for an export that
    hasn't failed (brief, D26)."""
    # Who retried is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise RetryRefused(wrong)
    if not state.export_failed:
        raise RetryRefused("the audit export hasn't failed: nothing to retry")
    counted = sorted(role for role in event.roles if role in catalog.operators)
    if not counted:
        registered = sorted(role for role in event.roles if role in catalog.roles)
        has = ", ".join(registered) or "no role"
        operators = ", ".join(catalog.operators) or "none registered"
        raise RetryRefused(
            f"the audit export is retried by an operating role ({operators}), and {event.by} "
            f"has {has}"
        )
    state.export_failed = ""
    state.history.append(f"{event.by} retried the audit export as {counted[0]}")
    state.deciding.append(Decision("retried", target=EXPORT))
