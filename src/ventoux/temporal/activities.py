"""The code behind a catalog's contracts, as Temporal activities (layer 6).

An activity acts on the world; Temporal retries it as its contract says. Each is registered under
its contract's reference (`payments.refund@2`), the name deployment bindings use (brief, D5).
"""

from collections.abc import Callable, Mapping
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from ventoux.case.runner import Activity
from ventoux.core.catalog import Catalog
from ventoux.core.interpreter import Outcome

# The type of error an activity's declared outcome travels as, from activity to workflow.
OUTCOME = "Outcome"


def plan_activities(
    catalog: Catalog, implementations: Mapping[str, Activity]
) -> list[Callable[..., Any]]:
    """Each implementation as a Temporal activity named by its reference."""
    activities: list[Callable[..., Any]] = []
    for reference, implementation in implementations.items():
        # Fail closed: an implementation for a reference the catalog doesn't hold is refused
        # (NotInCatalog), never served under a name no plan can call.
        catalog.get(reference)
        activities.append(as_activity(reference, implementation))
    return activities


def as_activity(reference: str, implementation: Activity) -> Callable[..., Any]:
    """`implementation`, registered with Temporal under `reference`."""

    def run(inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            return implementation(inputs)
        except Outcome as outcome:
            # A business failure is an answer, not an outage: never retried (brief, D17). The
            # workflow reads it back as the outcome; whether the contract declares it is the
            # interpreter's to check.
            raise ApplicationError(outcome.name, type=OUTCOME, non_retryable=True) from None

    # Temporal: `activity.defn` registers a function as an activity type, here by its reference.
    return activity.defn(name=reference)(run)
