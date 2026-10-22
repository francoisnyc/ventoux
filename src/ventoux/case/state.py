"""A case's state, the events that change it, and the commands the runtime gives (layer 8).

Nothing here says where the case is (brief, idea 4): a case holds its case file, the milestones it
has reached and its step runs, and the runtime works out what may start from those.
"""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from ventoux.core.before_activity import Steering
from ventoux.core.provenance import Sourced
from ventoux.core.sensitive import Sensitive


@dataclass
class GivenApproval:
    """An approval given and not yet spent: who gave it, and the digest of the inputs it saw."""

    entry: str
    by: str
    digest: str | Sensitive  # of the step's inputs (brief, D11); sensitive if they are
    # The values its step read when it was asked, by field, as the open approval saw them: a
    # refresh that changes one lapses it (brief, D33).
    seen: dict[str, object] = field(default_factory=dict[str, object])
    # Who else gave it, after `by`, in the order they approved; empty for one approver
    # (brief, D47).
    also: tuple[str, ...] = ()

    @property
    def approvers(self) -> tuple[str, ...]:
        """Everyone who gave it, in the order they approved."""
        return (self.by, *self.also)


@dataclass
class StepRun:
    """One run of a step: `review#1`, open while a task waits, running while an activity runs."""

    entry: str  # the step and its run's number, such as `review#1`
    step: str
    # rejected: its approval was refused; failed: it needs attention, with the reason (brief, D17);
    # retrying: an operator retried it, and it runs again as the same run (brief, D26).
    # cancelled: the case was closed while it waited (brief, D10).
    status: Literal["open", "running", "done", "rejected", "failed", "retrying", "cancelled"]
    reason: str = ""  # why it failed
    approved: GivenApproval | None = None  # the approval spent on it, which a retry keeps
    refresh: bool = (
        False  # run to fetch a stale fact again, not because the case asked (brief, D33)
    )
    # Kept for its retry, which starts the same run again (brief, D26): who may approve nothing in
    # it, and why, and the untrusted values the conditions that let it start read (brief, D25)
    # (brief, D39); kept for every kind of step, since its start passes them on (brief, D43).
    excluded: dict[str, str] = field(default_factory=dict)
    steered: tuple[Steering, ...] = ()
    # Whether it has started: a run that failed before it started hasn't, and starts for the first
    # time when an operator's retry runs it (brief, D38, as amended in 11b).
    started: bool = True
    # The rule's firing that asked to stop it while it runs, such as `withdraw#1`; empty if none.
    # A run whose stop is asked hasn't ended: it runs on, and is never asked twice (brief, D40).
    stop_requested: str = ""
    # An operator's retry made while every `closes_when` milestone was reached, which the close
    # waits for (brief, D34), as its flag says it: `omar's retry, after paid was reached`.
    held_retry: str = ""


@dataclass
class RuleFiring:
    """One time a rule's moment came: `flag_large#1` (brief, D38)."""

    entry: str  # the rule and how many times its moment came, such as `flag_large#1`
    rule: str
    moment: str  # the moment, as the history says it: `opened`, `reached checked`, `started pay`
    # done: it read its condition, and did what it says; failed: its condition couldn't be read,
    # and it waits for a person (brief, D17) (brief, D38); cancelled: the case was closed while it
    # waited (brief, D10).
    status: Literal["done", "failed", "cancelled"]
    reason: str = ""  # why it failed
    # What steered the start of the run its moment came from: untrusted data that let it start
    # counts as read by its condition, for its retry too (brief, D43).
    steered: tuple[Steering, ...] = ()


@dataclass(frozen=True)
class Moment:
    """A moment come in the decision being made, as the history says it, and, for a run's start,
    which run started: what steered it goes with the moment (brief, D38) (brief, D43)."""

    said: str  # `opened`, `started pay`, `reached checked`, `answered review`, `event cancelled`
    run: str = ""  # the run that started, such as `goodbye#1`; empty for any other moment
    # The entry it came from, which names a timer set on it: a run started or answered
    # (`review#1`), an event's arrival (`cancelled#2`); empty for the opening or a milestone.
    entry: str = ""
    # A timer's firing is a moment for its own rule alone, named here; empty for any other moment
    # (brief, D44).
    rule: str = ""


@dataclass(frozen=True)
class Timer:
    """A timer set on its moment: it fires once, at its due time, unless its purpose ends first
    (brief, D44)."""

    rule: str  # the rule whose moment it is, such as `chase_review`
    after: str  # how long it waits, as written: `2d`
    since: str  # the moment it was set on, with its entry: `started review#1`, `reached paid`
    due: int  # in whole seconds since the epoch: its moment's event time, plus `after`
    # The run whose start set it, which it lives while; empty if set on any other moment, when it
    # lives until it fires (brief, D44).
    run: str = ""


@dataclass(frozen=True)
class RuleStart:
    """A rule's start of a step: the engine's proposal, with what its condition read, kept until
    the run starts, since the rule itself remembers nothing (brief, D38) (brief, D39)."""

    entry: str  # the firing that proposes it, such as `send_back#1`
    moment: str  # its moment, as the history says it: `answered lead_check`
    step: str  # the step it starts
    # Each person whose answer the rule's condition read, and the field: none of them approves
    # the run it starts (brief, D11) (brief, D25).
    read_from: dict[str, str] = field(default_factory=dict[str, str])
    # Each value the condition read from a source the engine doesn't trust, with those sources:
    # they count for the step's input policies (brief, D38) (brief, D39).
    untrusted: dict[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    # What steered the start its moment came from: it counts for the step's input policies too,
    # and goes on with the run (brief, D43).
    steered: tuple[Steering, ...] = ()


@dataclass
class OpenApproval:
    """An approval asked and not yet answered: `pay.approval#1`."""

    entry: str  # the step, `approval`, and how many times it was asked: `pay.approval#1`
    step: str  # the step it guards
    seen: dict[str, object]  # the values its step read when it was asked, by field (brief, D25)
    count: int = 1  # how many different people must approve it (brief, D47)
    # Each person who has approved it so far, with the role that let them, in the order they
    # did: it is given once there are `count` of them (brief, D47).
    approved: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class Obtained:
    """When a value of the case file was obtained, and by which step run (brief, D33)."""

    at: int  # in whole seconds since the epoch: the time of the event that brought it
    # The step run that gave it, such as `check_order#1`, or the event's arrival, such as
    # `cancelled#1` (brief, D41); None: the opening, a person.
    run: str | None


@dataclass
class CaseState:
    """Everything a case knows: its case file, milestones and step runs, and its history."""

    case: str  # names the case in its keys, such as `memory/pay#1`
    values: dict[str, object] = field(default_factory=dict[str, object])  # the case file
    # Where each value came from (brief, D12): `system:opener`, `person:ana`, `untrusted:llm`.
    sources: dict[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    # When each value was obtained, and by which run (brief, D18) (brief, D33).
    obtained: dict[str, Obtained] = field(default_factory=dict[str, Obtained])
    milestones: list[str] = field(default_factory=list[str])  # reached, in order; never undone
    # Each stale fact being fetched again, and the run fetching it: one refresh per need, never
    # a second for the same one (brief, D33).
    refreshing: dict[str, str] = field(default_factory=dict[str, str])
    runs: list[StepRun] = field(default_factory=list[StepRun])  # every step run, in order
    approvals: dict[str, OpenApproval] = field(default_factory=dict[str, OpenApproval])  # by step
    given: dict[str, GivenApproval] = field(default_factory=dict[str, GivenApproval])  # by step
    asked: dict[str, int] = field(default_factory=dict[str, int])  # approvals asked, by step
    withdrawn: dict[str, str] = field(default_factory=dict[str, str])  # entry: why
    # Who proposed each step's coming run, until it runs or is rejected (brief, D25).
    proposers: dict[str, str] = field(default_factory=dict[str, str])
    # Each step a person proposed whose start waits for a stale fact to be fetched again; admission
    # takes it up once the fact lands (brief, D33) (brief, D39).
    waiting_to_start: list[str] = field(default_factory=list[str])
    # Each step a rule started whose run hasn't started yet (waiting for its approval), with what
    # the rule read: like `proposers`, for the engine (brief, D39).
    proposed_by_rules: dict[str, RuleStart] = field(default_factory=dict[str, RuleStart])
    # How many times each event from outside has arrived, which names its next arrival:
    # `cancelled#2` (brief, D41).
    arrived: dict[str, int] = field(default_factory=dict[str, int])
    # What waits on people, in the order it opened: entry, and how it reads (brief, D24).
    waiting: dict[str, str] = field(default_factory=dict[str, str])
    opened_by: str | None = None  # the person who opened the case, if a person did
    # open; closing: nothing new starts, running activities finish; closed (brief, D10).
    phase: Literal["open", "closing", "closed"] = "open"
    closed_because: str = ""  # why it is closing, as the closed line will say
    flags: list[str] = field(default_factory=list[str])  # what a person should look at
    history: list[str] = field(default_factory=list[str])  # what happened, one line each
    firings: list[RuleFiring] = field(default_factory=list[RuleFiring])  # every rule's, in order
    # The moments that came in the decision being made, waiting for their rules: always empty
    # between events, so nothing about them crosses continue-as-new (brief, D38).
    moments: list[Moment] = field(default_factory=list[Moment])
    # The starts the rules fired in this decision asked for, waiting for admission; and the steps
    # a rule has started in it, which no rule starts again in it (brief, D39). Always empty
    # between events, like `moments`.
    rule_starts: list[RuleStart] = field(default_factory=list[RuleStart])
    started_by_rules: list[str] = field(default_factory=list[str])
    # Each timer set and not yet fired or ended, in the order set: pending work (brief, D10)
    # (brief, D44).
    timers: list[Timer] = field(default_factory=list[Timer])


@dataclass(frozen=True)
class Opened:
    """A case opens with the first values of its case file."""

    file: Mapping[str, object]  # each value, read by its field's type
    by: str | None  # the person who opened it, as the trusted caller states; None: a system
    # When it reached the case, in whole seconds since the epoch: the case reads no clock
    # (brief, D33). Python: `kw_only` makes it a keyword with no default, `Opened(..., at=t)`, so
    # no event is ever made without its time.
    at: int = field(kw_only=True)


@dataclass(frozen=True)
class Answered:
    """A person answers an open entry: a task's run, or an approval."""

    entry: str  # the entry, `review#1` or `pay.approval#1`, or a step for its open entry
    outcome: str
    by: str  # who answered, as the trusted caller states (brief, D19)
    roles: frozenset[str]  # their roles, stated with the answer (brief, D22)
    form: Mapping[str, object] | None = None  # the values the outcome sets
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class Proposed:
    """A person proposes starting a step: admission accepts it or refuses it."""

    step: str
    by: str  # who proposed it, as the trusted caller states (brief, D19)
    roles: frozenset[str]  # their roles, stated with the proposal (brief, D22)
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class Completed:
    """A scheduled activity finished: its run, what it gave, and with which outcome: `done`, or
    one its contract declares, such as `declined` (brief, D17)."""

    entry: str
    output: Mapping[str, object]
    outcome: str = "done"
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class Failed:
    """A scheduled activity failed after its retries: its run, and what went wrong."""

    entry: str
    reason: str
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class Retried:
    """An operator retries a failed step run: the same run, with the same key (brief, D26)."""

    entry: str
    by: str  # who retried it, as the trusted caller states (brief, D19)
    roles: frozenset[str]  # their roles, stated with the retry (brief, D22)
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class CloseAsked:
    """A person closes the case with a declared reason (brief, D10)."""

    reason: str
    by: str  # who closes it, as the trusted caller states (brief, D19)
    roles: frozenset[str]  # their roles, stated with the request (brief, D22)
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class PlanCancelled:
    """A plan step's plan ended early because the case is closing: its open waits were
    cancelled, and nothing new started in it (brief, D28)."""

    entry: str
    # Each activity in it that finished or failed after the close was requested, which the case
    # flags: `payments.refund@2 completed after the close was requested` (brief, D10).
    after_stop: tuple[str, ...] = ()
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class WorkflowCancelled:
    """A cancellable workflow step ended cancelled, after the case asked, closing or stopping it:
    its team's promise is that nothing it started completed after the request (brief, D40)."""

    entry: str  # the step run, such as `kyc#1`
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class Shown:
    """A person was shown the record a reference field names, by its system's resolver: recorded,
    never its content (brief, D16)."""

    field: str  # the reference field, such as `customer_id`
    by: str  # who was shown it, as the trusted caller states (brief, D19)
    roles: frozenset[str]  # their roles, stated with it (brief, D22)
    # When it reached the case, in seconds since the epoch. `dataclasses.field` in full: this
    # class has a field named `field`.
    at: int = dataclasses.field(kw_only=True)


@dataclass(frozen=True)
class ForgetApproved:
    """A request to forget the case was approved: close it as `forgotten`, then its key is
    destroyed outside it (brief, D15) (brief, D32). Both people and their roles come with it, so the
    case checks the request itself."""

    proposed_by: str  # who proposed forgetting it, as the trusted caller states (brief, D19)
    proposer_roles: frozenset[str]  # their roles, stated with the proposal (brief, D22)
    approved_by: str  # who approved it
    approver_roles: frozenset[str]  # their roles, stated with the approval
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class Sent:
    """An event from outside reaches the case: the declared event, what it carries, and who sent
    it, as the Ventoux API states (brief, D19) (brief, D41)."""

    event: str  # the declared event, such as `cancelled`
    payload: Mapping[str, object]  # each value it carries, by its payload field
    by: str  # who sent it: `system:portal`, or a person's identifier, such as `ana`
    roles: frozenset[str]  # a person's roles, stated with it (brief, D22); none for a system
    at: int = field(kw_only=True)  # when it reached the case, in seconds since the epoch


@dataclass(frozen=True)
class TimerDue:
    """A timer's time has come: the rule and the moment it was set on name it, and it is stamped
    with its due time, never the time a driver noticed it (brief, D33) (brief, D44)."""

    rule: str  # the rule whose timer it is, such as `chase_review`
    since: str  # the moment it was set on, with its entry: `started review#1`
    at: int = field(kw_only=True)  # its due time, in seconds since the epoch


type Event = (
    Opened
    | Answered
    | Proposed
    | Completed
    | Failed
    | Retried
    | CloseAsked
    | PlanCancelled
    | WorkflowCancelled
    | Shown
    | ForgetApproved
    | Sent
    | TimerDue
)


@dataclass(frozen=True)
class Schedule:
    """Run one activity: the step run, its contract and its checked inputs, key included."""

    entry: str
    activity: str  # its reference, such as `payments.refund@2`
    inputs: dict[str, object]


@dataclass(frozen=True)
class StartWorkflow:
    """Run an existing workflow as a step (brief, D6): its contract, its checked inputs (key
    included, if its contract takes one), and the run's name, which names its child workflow."""

    entry: str  # the step run, such as `kyc#1`
    workflow: str  # its workflow contract's reference, such as `kyc.check@1`
    inputs: dict[str, object]
    run: str  # `memory/kyc#1`; on Temporal the child workflow is `<case ID>/kyc#1`


@dataclass(frozen=True)
class StartPlan:
    """Run one plan as a step (brief, D28): its reference, its fields with where each value came
    from, the run's name in its keys, and who may approve nothing in it."""

    entry: str  # the step run, such as `settle#1`
    plan: str  # its reference, such as `refund-order@1`
    fields: dict[str, Sourced]  # the plan's fields, read from the case file
    run: str  # names the run in its keys: `memory/settle#1`, so `memory/settle#1/pay#1`
    # Each person who approves nothing in the plan, and why: the case's opener and the step's
    # proposer cross into it (brief, D25).
    excluded: dict[str, str]
    # What each field is given, as a reference: the system of a reference field read as it is, or
    # None; and how a message says it. Only the case sees the expression, so it says (brief, D30).
    references: dict[str, tuple[str | None, str]] = field(default_factory=dict)
    # The untrusted values the conditions that let the step start read: they count for every
    # activity's input policies in the plan, beside its fields (brief, D39).
    steered: tuple[Steering, ...] = ()


# Why a child is stopped when its case closes: the reason a plan's stop signal gives by default,
# so a history recorded before 11c, whose signal gave none, replays the same (brief, D40).
CLOSING = "the case is closing"


@dataclass(frozen=True)
class StopPlan:
    """Stop a plan step's plan, because the case is closing or a rule stops it: cancel its open
    waits, start nothing new in it, and let an activity running inside it finish (brief, D10)
    (brief, D28) (brief, D40)."""

    entry: str  # the step run, such as `settle#1`
    reason: str = CLOSING  # why, naming only the entry that asked: `stopped by withdraw#1`


@dataclass(frozen=True)
class CancelWorkflow:
    """Cancel a workflow step whose contract declares it cancellable, because the case is closing
    or a rule stops it; the case waits for it to end (brief, D40)."""

    entry: str  # the step run, such as `kyc#1`
    reason: str  # why, naming only the entry that asked: `stopped by withdraw#1`


type Command = Schedule | StartWorkflow | StartPlan | StopPlan | CancelWorkflow
