"""A case's state, the events that change it, and the commands the runtime gives (layer 8).

Nothing here says where the case is (brief, idea 4): a case holds its case file, the milestones it
has reached and its step runs, and the runtime works out what may start from those.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class StepRun:
    """One run of a step: `review#1`, open while a task waits, running while an activity runs."""

    entry: str  # the step and its run's number, such as `review#1`
    step: str
    status: Literal["open", "running", "done", "rejected"]  # rejected: its approval was refused


@dataclass
class OpenApproval:
    """An approval asked and not yet answered: `pay.approval#1`."""

    entry: str  # the step, `approval`, and how many times it was asked: `pay.approval#1`
    step: str  # the step it guards
    seen: dict[str, object]  # the values its step read when it was asked, by field (brief, D25)


@dataclass
class GivenApproval:
    """An approval given and not yet spent: who gave it, and the digest of the inputs it saw."""

    entry: str
    by: str
    digest: str  # of the step's inputs (brief, D11)


@dataclass
class CaseState:
    """Everything a case knows: its case file, milestones and step runs, and its history."""

    case: str  # names the case in its keys, such as `memory/pay#1`
    values: dict[str, object] = field(default_factory=dict[str, object])  # the case file
    # Where each value came from (brief, D12): `system:opener`, `person:ana`, `untrusted:llm`.
    sources: dict[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    milestones: list[str] = field(default_factory=list[str])  # reached, in order; never undone
    runs: list[StepRun] = field(default_factory=list[StepRun])  # every step run, in order
    approvals: dict[str, OpenApproval] = field(default_factory=dict[str, OpenApproval])  # by step
    given: dict[str, GivenApproval] = field(default_factory=dict[str, GivenApproval])  # by step
    asked: dict[str, int] = field(default_factory=dict[str, int])  # approvals asked, by step
    withdrawn: dict[str, str] = field(default_factory=dict[str, str])  # entry: why
    # Who proposed each step's coming run, until it runs or is rejected (brief, D25).
    proposers: dict[str, str] = field(default_factory=dict[str, str])
    # What waits on people, in the order it opened: entry, and how it reads (brief, D24).
    waiting: dict[str, str] = field(default_factory=dict[str, str])
    opened_by: str | None = None  # the person who opened the case, if a person did
    closed: bool = False
    history: list[str] = field(default_factory=list[str])  # what happened, one line each


@dataclass(frozen=True)
class Opened:
    """A case opens with the first values of its case file."""

    file: Mapping[str, object]  # each value, read by its field's type
    by: str | None  # the person who opened it, as the trusted caller states; None: a system


@dataclass(frozen=True)
class Answered:
    """A person answers an open entry: a task's run, or an approval."""

    entry: str  # the entry, `review#1` or `pay.approval#1`, or a step for its open entry
    outcome: str
    by: str  # who answered, as the trusted caller states (brief, D19)
    roles: frozenset[str]  # their roles, stated with the answer (brief, D22)
    form: Mapping[str, object] | None = None  # the values the outcome sets


@dataclass(frozen=True)
class Proposed:
    """A person proposes starting a step: admission accepts it or refuses it."""

    step: str
    by: str  # who proposed it, as the trusted caller states (brief, D19)
    roles: frozenset[str]  # their roles, stated with the proposal (brief, D22)


@dataclass(frozen=True)
class Completed:
    """A scheduled activity finished: its run, and what it gave."""

    entry: str
    output: Mapping[str, object]


type Event = Opened | Answered | Proposed | Completed


@dataclass(frozen=True)
class Schedule:
    """Run one activity: the step run, its contract and its checked inputs, key included."""

    entry: str
    activity: str  # its reference, such as `payments.refund@2`
    inputs: dict[str, object]
