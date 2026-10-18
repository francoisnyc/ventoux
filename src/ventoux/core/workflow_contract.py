"""A workflow contract: what an existing Temporal workflow promises, run as one step (brief, D6).

The workflow may be written by another team, in any SDK language; the case only names its contract,
and the deployment binds it to a workflow type and task queue. See docs/guides/activities.md.
"""

from typing import Any, Self

from pydantic import Field, model_validator

from ventoux.core.contract import Contract

# What an activity contract has and a workflow contract doesn't, and why (brief, D29).
NOT_A_WORKFLOWS = {
    "retry": "a workflow contract has no retry policy: Temporal doesn't retry a workflow step as "
    "a whole (its own activities retry inside it), and an operator retries a failed one.",
    "outcomes": "a workflow contract has no outcomes: a business result is part of its output, "
    "with its source.",
    "timeouts": "a workflow contract has one timeout, the longest the workflow may run.",
}


class WorkflowContract(Contract):
    """What one workflow promises: the parts every contract has, and how long it may run."""

    # Pydantic: `Field(gt=0)` adds a check to the type: an int, and greater than 0.
    timeout: int = Field(gt=0)  # in seconds: the longest the workflow may run, so one that hangs,
    # or waits for a person, fails loudly
    # The team's promise that it stops cleanly when cancelled: after the request it schedules
    # nothing new, it ends only once all it started has ended, and it ends cancelled only if
    # nothing it started completed after the request. A step running it is then cancelled when
    # its case closes or a rule stops it; otherwise it runs to its end, like an activity
    # (brief, D40). Checked by the contract test, never assumed.
    cancellable: bool = False

    # Pydantic: a validator with `mode="before"` runs first, on the raw input (here a dict), before
    # any field is checked; this one runs before the one every contract has.
    @model_validator(mode="before")
    @classmethod
    def no_activity_parts(cls, data: Any) -> Any:
        # An activity's parts are refused with why, rather than as fields nobody knows.
        if isinstance(data, dict):
            for name, why in NOT_A_WORKFLOWS.items():
                if name in data:
                    raise ValueError(why)
        return data

    @model_validator(mode="after")
    def no_outcome_titles(self) -> Self:
        # A title for an outcome nobody can give is a mistake, as it is on an activity.
        if self.display.outcomes:
            raise ValueError(NOT_A_WORKFLOWS["outcomes"])
        return self
