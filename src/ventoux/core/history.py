"""A run's history: what happened, one event at a time, in order (layer 5).

Each event reads as one line (`str(event)`). No event has a time: the interpreter reads no clock
(Temporal's own history adds them, layer 6). See docs/layers/05-interpreter.md.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Started:
    """The run started."""

    plan: str  # the plan's name
    version: int  # the plan's version

    def __str__(self) -> str:
        return f"started {self.plan}@{self.version}"


@dataclass(frozen=True)
class Entered:
    """The run entered a state."""

    state: str

    def __str__(self) -> str:
        return f"entered {self.state}"


@dataclass(frozen=True)
class Ended:
    """The run reached a final state."""

    outcome: str  # succeeded or failed, as the final state says

    def __str__(self) -> str:
        return f"ended {self.outcome}"


@dataclass(frozen=True)
class Gave:
    """An activity answered: `done`, with its output, or one of its declared outcomes."""

    activity: str  # the activity's reference, such as `orders.lookup@1`
    event: str  # `done`, or the outcome, such as `declined`
    output: dict[str, Any] | None  # what it returned, with `done`; None with an outcome

    def __str__(self) -> str:
        return f"{self.activity} gave {self.event}"


@dataclass(frozen=True)
class Moved:
    """The run took a transition."""

    event: str  # what happened in the state it left
    target: str  # the state it goes to

    def __str__(self) -> str:
        return f"moved on {self.event} to {self.target}"


@dataclass(frozen=True)
class Stopped:
    """The engine refused to go on: the step needs a person, and nothing after it runs."""

    state: str  # where the run stopped
    reason: str  # what went wrong

    def __str__(self) -> str:
        return f"stopped at {self.state}: {self.reason}: {AFTER_A_STOP}"


# What happens after a stop, said in every one: nothing is skipped automatically (brief, D17).
AFTER_A_STOP = "the step needs attention, and nothing after it runs"

type Event = Started | Entered | Gave | Moved | Ended | Stopped
