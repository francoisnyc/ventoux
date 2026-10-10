"""How Temporal runs an activity: the retry policy and timeouts its contract declares (brief, D17).

Used by plan and case workflows alike. A contract's values are the platform team's, who know the
system's limits; a workflow never picks its own.
"""

from datetime import timedelta
from typing import Any

from temporalio.common import RetryPolicy

from ventoux.core.contract import ActivityContract


def activity_options(contract: ActivityContract) -> dict[str, Any]:
    """The arguments `workflow.execute_activity` takes for `contract`'s timeouts and retries."""
    return {
        "start_to_close_timeout": timedelta(seconds=contract.timeouts.start_to_close),
        "schedule_to_start_timeout": timedelta(seconds=contract.timeouts.schedule_to_start),
        "retry_policy": RetryPolicy(
            maximum_attempts=contract.retry.maximum_attempts,
            initial_interval=timedelta(seconds=contract.retry.initial_interval),
            backoff_coefficient=contract.retry.backoff_coefficient,
        ),
    }
