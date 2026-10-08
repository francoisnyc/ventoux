"""A run's history: what happened, one event at a time, in order (layer 5).

Each event reads as one line (`str(event)`). No event has a time: the interpreter reads no clock
(Temporal's own history adds them, layer 6). See docs/layers/05-interpreter.md.
"""

from dataclasses import dataclass


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


type Event = Started | Entered | Ended
