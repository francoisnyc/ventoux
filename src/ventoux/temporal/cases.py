"""A case as a Temporal workflow, one per case for as long as it lives; and its client (layer 8c).

The workflow is a driver around `decide`, as `case/memory.py` is in tests: every event (the opening,
a person's signal, an activity's result) goes into one inbox, and the loop decides them one at a
time, in the order history records them, then starts what `decide` asks for. `decide` reads no
clock, randomness or I/O, so replay rebuilds the same case. See docs/layers/08-case.md (8c).
"""

import asyncio
import json
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar, Literal

from temporalio import workflow
from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
    WorkflowHandle,
    WorkflowQueryFailedError,
)
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import (
    ActivityError,
    ApplicationError,
    CancelledError,
    ChildWorkflowError,
    FailureError,
    TerminatedError,
)
from temporalio.exceptions import TimeoutError as TemporalTimeout  # not Python's own TimeoutError
from temporalio.service import RPCError, RPCStatusCode

# Temporal: the workflow sandbox imports a workflow's modules afresh for every run; modules passed
# through are imported once and shared. `core` and `case` are deterministic (the boundary test
# holds them to that), so they are shared.
with workflow.unsafe.imports_passed_through():
    from ventoux.case.admission import ProposalRefused, RetryRefused
    from ventoux.case.advising import AdvisorView, advisor_view
    from ventoux.case.answers import AnswerRefused
    from ventoux.case.audit import AuditRecord, Decision
    from ventoux.case.called import unbound
    from ventoux.case.claims import ClaimRefused, assignees
    from ventoux.case.closing import CloseRefused, needs_attention
    from ventoux.case.definition import CaseInvalid, CaseStep, PlanStep, parse_case
    from ventoux.case.ending import ending_of
    from ventoux.case.engine import ENGINE, KNOWN, OPENING, opening_engine
    from ventoux.case.forgetting import ForgetRefused, family_says
    from ventoux.case.freshness import TimeRefused
    from ventoux.case.migrations import all_plans, migration_of
    from ventoux.case.owing import attention, waiting_for
    from ventoux.case.plan_step import PlanNotSupplied, supplied, wrong_references
    from ventoux.case.recording import RECORDS_FROM, record_refused
    from ventoux.case.registry import Answer, Moving, Opening, Released
    from ventoux.case.releases import Hash, Record, behaviour_digest, is_release
    from ventoux.case.requests import ChangeRefused
    from ventoux.case.runtime import (
        CaseRefused,
        EventRefused,
        ShownRefused,
        decide,
        preview_migration,
        proposal_refused,
    )
    from ventoux.case.state import (
        Answered,
        Assigned,
        CancelWorkflow,
        CaseState,
        ChangeProposed,
        ChildNotEnded,
        ChildRang,
        Claimed,
        CloseAsked,
        CloseCase,
        ClosedByParent,
        Command,
        Completed,
        Event,
        ExportFailed,
        ExportRetried,
        Failed,
        ForgetApproved,
        GivenBack,
        Migration,
        OpenCase,
        Opened,
        PlanCancelled,
        Proposed,
        ReadChild,
        Retried,
        Schedule,
        Sent,
        Shown,
        StartPlan,
        StartWorkflow,
        StopPlan,
        Unassigned,
        UseRelease,
        WorkflowCancelled,
    )
    from ventoux.case.timers import next_due, set_timers, soonest
    from ventoux.case.types import case_types
    from ventoux.case.visibility import ApprovalSheet, CaseView, SheetRefused, case_view, sheet_of
    from ventoux.core.catalog import Catalog
    from ventoux.core.plan import parse_plan
    from ventoux.core.sensitive import Sensitive
    from ventoux.core.workflow_contract import WorkflowContract
    from ventoux.temporal.activities import OUTCOME
    from ventoux.temporal.audit import ExportSent, restricted_fields, sensitive_fields
    from ventoux.temporal.bindings import Binding
    from ventoux.temporal.carried import (
        decision_from_data,
        record_as_data,
        state_as_data,
        state_from_data,
    )
    from ventoux.temporal.children import (
        SETTLE,
        ChildAsked,
        ChildEnding,
        ChildRead,
        ParentStart,
        ending_data,
        event_of,
    )
    from ventoux.temporal.converter import keys_of
    from ventoux.temporal.options import activity_options
    from ventoux.temporal.registry import CALL, Asked
    from ventoux.temporal.workflow import Given, PlanStart, RunReport, raised
    from ventoux.tooling.keys import FORGOTTEN


# The patch marker a case in an environment records at its opening, once 12e asks its registry: a
# history without it, recorded before, replays without asking (brief, D51).
REGISTRY_PATCH = "ventoux-registry"

# How often a case asks how each open child stands, which bounds how long a child that ended
# without ringing goes unnoticed (brief, D75).
CHILD_CHECK = timedelta(days=1)

# What a person's request may be refused with: recorded, and the case waits on.
REFUSALS = (
    AnswerRefused,
    ProposalRefused,
    RetryRefused,
    ClaimRefused,
    CloseRefused,
    ShownRefused,
    ForgetRefused,
    EventRefused,
    ChangeRefused,
)


class StartUnread(Exception):
    """A run continued as new whose start, read and checked when the case opened, no longer reads
    or no longer gives its release's digest: a change of code. Not a refusal of the case: it fails
    the workflow task, retried until code that reads it is deployed (brief, D17) (brief, D51)."""


class CaseForgotten(Exception):
    """A forgotten case read for what it held: its key is gone (brief, D32)."""


@dataclass
class ReleaseStart:
    """The release a case opens on: which, its digest, and its plans (brief, D51)."""

    name: str  # the package: `refund`
    release: int  # its number
    digest: Hash  # its behaviour digest, which the case checks what it was given against
    # Its plans, as stored data, by reference (`refund-order@1`): its children's too, since one
    # reference is one plan (brief, D74).
    plans: dict[str, Any]
    # The child cases it pins, as stored data, by reference (`repair@3`); none before 18d.
    cases: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class CaseStart:
    """What a case opens with."""

    definition: dict[str, Any]  # the case definition, as stored data
    file: dict[str, Any]  # the case file's first values, each of its field's type
    opened_by: str | None = None  # the person who opened it, as the API states; None: a system
    # The state of the case, when it continues as new: the new run decides from it alone
    # (brief, D27). None: the case opens now.
    carried: dict[str, Any] | None = None
    # The release it opens on, crossing every continue-as-new with the definition; None: a draft,
    # as every case before 12b (brief, D51).
    release: ReleaseStart | None = None
    # The environment whose registry it asked as it opened, and asks as it moves and closes,
    # crossing every continue-as-new; None: none, as every case opened before 12e (brief, D5).
    environment: str | None = None
    # The opener's roles, as the API states them, so a rule asking the opener judges them; none
    # for a system, or a start from before 17c (brief, D71).
    opener_roles: list[str] = field(default_factory=list[str])
    # For a child case: its parent, which it rings as its last act; None: no parent opened it
    # (brief, D75). Crosses every continue-as-new.
    parent: ParentStart | None = None


@dataclass
class CaseReport:
    """How a case is going: what `run_case` reports in memory, and the entries open."""

    status: str  # open; closing: nothing new starts; closed (brief, D10)
    waiting_for: list[str]  # open tasks and approvals, in the order they opened (brief, D24)
    # The open entries' names, in the same order, to answer: `review#1`. An owed step, listed
    # after them, has none (brief, D72).
    waiting_at: list[str]
    needs_attention: list[str]  # failed step runs, each with its reason (brief, D17)
    flags: list[str]  # what completed after the close was requested
    history: list[str]  # what happened, one line each
    # Each timer still set, soonest first, with its due time: never in `waiting_for` (brief, D24)
    # (brief, D44). Empty from a worker before 11f.
    timers: list[str] = field(default_factory=list[str])
    release: str = "draft"  # the release it runs, `refund 1`; a draft's says so (brief, D51)
    engine: int = 1  # the engine version it decides as; 1 from a worker before 12b
    # Each held open entry and its holder, in the order the entries opened; an entry in its
    # queue is absent (brief, D69). Empty from a worker before 17a.
    assignees: dict[str, str] = field(default_factory=dict[str, str])
    # A closed child case's report, which its parent reads; None for any other (brief, D75).
    ending: ChildEnding | None = None
    # How many of its audit records are not yet written to its store (brief, D77).
    unwritten: int = 0
    # What its family's definitions say of forgetting, as it is now (the strictest of its own
    # and its pinned children's: allowed, while_open or never), and whether it took an approved
    # request to forget it. A request reads both from the report the case returns as it ends,
    # never from Temporal's word that it runs (brief, D32). Empty from a worker before the fix.
    forgetting: str = ""
    forget_taken: bool = False


@dataclass
class CaseAnswer:
    """An answer, as a person sends it to a case."""

    entry: str  # the entry it answers: `review#1` or `pay.approval#1`
    outcome: str  # one of the entry's outcomes, such as `approve`
    by: str  # who answered
    # Their roles, as the Ventoux API states them; recorded in history with the signal, so a
    # replay decides as the first run did, whatever their roles are now (brief, D22).
    roles: list[str]
    form: dict[str, Any] | None = None  # the values the outcome sets, if any
    # The wording revision of the case's release its person read; None: not said (brief, D51).
    wording: int | None = None


@dataclass
class CaseEvent:
    """An event from outside, as the Ventoux API sends it to a case: one shape for every event,
    whoever sends it (brief, D41)."""

    event: str  # the declared event, such as `cancelled`
    payload: dict[str, Any]  # each value it carries, by its payload field
    by: str  # who sent it: `system:portal`, or a person's identifier, such as `ana`
    roles: list[str]  # a person's roles, as the API states them (brief, D22); none for a system


@dataclass
class CaseForget:
    """An approved request to forget the case, from `<case ID>/forget` (brief, D32)."""

    proposed_by: str  # who proposed it
    proposer_roles: list[str]  # their roles, stated with the proposal (brief, D22)
    approved_by: str  # who approved it
    approver_roles: list[str]  # their roles, stated with the approval


@dataclass
class CaseChange:
    """A change request, as a person proposes it to a case: an edit of a field's value, or a
    skip of a failed run; someone else approves it (brief, D52)."""

    kind: str  # `edit` or `skip`
    target: str  # the field to edit, or the run to skip (`pay#1`)
    # An edit's new value, sealed: the client can't tell which fields are sensitive (brief, D31);
    # None for a skip.
    value: Any
    by: str  # who proposes it, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles, stated with the proposal (brief, D22)


@dataclass
class CaseMigration:
    """A migration, as a person proposes it to a case: the target release as its record gives it,
    the names it maps, and the engine version it moves to; someone else approves it
    (brief, D53)."""

    name: str  # the package: `refund`
    release: int  # its number
    method: int  # the hash method of its digest
    sha256: str  # its behaviour digest, which the case checks the package gives (brief, D51)
    case: dict[str, Any]  # its case definition, as stored data
    plans: dict[str, Any]  # its plans, as stored data, by reference
    mapping: dict[str, dict[str, str]]  # each kind of name renamed, old to new
    engine: int  # the engine version it moves to
    by: str  # who proposes it, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles, stated with the proposal (brief, D22)
    # The child cases it pins, as stored data, by reference, which its digest covers; none in a
    # migration sent before 18d (brief, D75).
    cases: dict[str, Any] = field(default_factory=dict[str, Any])

    def migration(self) -> Migration:
        return Migration(
            self.name,
            self.release,
            self.method,
            self.sha256,
            self.case,
            self.plans,
            self.mapping,
            self.engine,
            self.cases,
        )


@dataclass
class MigrationAsked:
    """A migration to preview on a case at the reader's time, never recorded (brief, D53)."""

    target: CaseMigration  # what it would move the case to; its `by` and `roles` aren't read
    at: int  # the reader's time, in seconds since the epoch


@dataclass
class PreviewAnswer:
    """What a migration would do to a case: every problem refusing it, or the lines its history
    would gain."""

    refused: list[str]
    lines: list[str]


@dataclass
class CaseAssignment:
    """An assignment, as a person whose role assigns sends it: who is asked, and who asks
    (brief, D70)."""

    entry: str  # the open entry, `review#1`
    to: str  # who is asked to answer it, as the trusted caller states (brief, D19)
    to_roles: list[str]  # their roles, as the Ventoux API states them (brief, D22)
    by: str  # who assigns it
    roles: list[str]  # the assigner's roles


@dataclass
class CaseRequest:
    """A person's request to a case: propose a step, retry a failed run, close it, or claim or
    give back an open entry."""

    what: str  # the step proposed, the run retried (`pay#1`), the close reason, or the entry
    by: str  # who asks, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles, stated with the request (brief, D22)
    # Who suggested a proposal: the step advisor, or nobody. Text as it crosses Temporal, so the
    # case, never the client, refuses any other value (brief, D61).
    suggested_by: str | None = None


@dataclass
class AdvisorAsked:
    """The step advisor asked for a person: who, with which roles, at what time."""

    by: str  # the person it is asked for, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles (brief, D22)
    at: int  # the asker's time, in seconds since the epoch, against which facts' ages are told


@dataclass
class ProposalAsked:
    """Whether a person's proposal of a step would be admitted now."""

    step: str
    by: str  # the person, as the trusted caller states (brief, D19)
    roles: list[str]  # their roles (brief, D22)
    at: int  # the asker's time, in seconds since the epoch


@dataclass
class Refusal:
    """Why a proposal would be refused, or None if admission would accept it."""

    reason: str | None


@dataclass
class Wording:
    """A wording revision of a release, to show a case in: its package as written (brief, D51)."""

    name: str  # the package: `refund`
    release: int
    wording: int  # 1: the release's own wording
    case: str  # case.json's text
    plans: dict[str, str]  # each plan's text, by reference

    def __str__(self) -> str:
        return f"{self.name} {self.release}, wording {self.wording}"


@dataclass
class SheetAsked:
    """A person reading an open approval's sheet: which, with which roles, at what time."""

    entry: str  # the open approval, such as `pay.approval#1`
    roles: list[str]  # the reader's roles, as the trusted caller states them (brief, D22)
    at: int  # the reader's time, in seconds since the epoch, against which ages are told
    # The wording to show it in: a revision of the case's release; None: the case's own.
    wording: Wording | None = None


@dataclass
class ViewAsked:
    """A person reading the case file in a wording revision of its release."""

    roles: list[str]  # the reader's roles, as the trusted caller states them (brief, D22)
    wording: Wording


@dataclass
class ViewAnswer:
    """What a worded view answers: the view, or why it can't be read in that wording."""

    view: CaseView | None
    refused: str = ""  # why not, naming the wording, never a value


class WordingRefused(Exception):
    """A wording that isn't a revision of the case's release: never shown in its place."""


@dataclass
class SheetAnswer:
    """What a sheet query answers: the sheet, or why it can't be read."""

    sheet: ApprovalSheet | None
    refused: str = ""  # why not, naming the entry, never a value
    # Why the wording it was asked in was refused, naming the wording; then `refused` is empty.
    wording_refused: str = ""


# The export's own call, and how often it is tried before the case is told it failed: a store
# down for a while is waited for, a refusal (a value in clear, a gap) never retried (brief, D77).
EXPORT_CALL = timedelta(minutes=1)
EXPORT_RETRIES = RetryPolicy(
    maximum_attempts=10,
    maximum_interval=timedelta(minutes=5),
    # Refusals are final: retried, they would be refused again. A key the key service refuses for
    # good (one that can leave it) is one too; one it can't give now is retried (brief, D78).
    non_retryable_error_types=["ExportRefused", "AuditRefused", "KeyRefused"],
)


class CaseWorkflow:
    """The code of a case workflow. A deployment subclasses it to name its catalog and plans, and
    registers the subclass (Temporal's SDK wants `@workflow.run` on the class it registers), as
    the cases guide shows."""

    catalog: ClassVar[Catalog]  # the contracts this deployment's cases may call
    plans: ClassVar[Mapping[str, Any]] = {}  # the plans its plan steps may run, by reference
    # The plan workflow a plan step runs as, by the name its worker registers it under.
    plan_workflow: ClassVar[str] = "ventoux.plan"
    # Where each workflow contract runs, in this deployment (brief, D5): its workflow type and
    # task queue. A workflow step whose contract isn't bound here fails (brief, D29).
    workflows: ClassVar[Mapping[str, Binding]] = {}
    # The environment its cases run in, whose registry each case asks as it opens, moves and
    # closes (brief, D5); None: none, where drafts run and no registry is asked, as before 12e.
    environment: ClassVar[str | None] = None
    # How many events one run decides before the case continues as new: a count, never a clock,
    # so replay switches at the same place (brief, D27). Temporal warns at about 10,000 history
    # events; a case's event makes a few.
    events_per_run: ClassVar[int] = 1000
    # How much of the case's records may wait unwritten, measured as data, before the case holds:
    # well under Temporal's 512 KB warning for one payload, which the switch's state is
    # (brief, D77). A test's workflow lowers it, as `events_per_run`.
    audit_bound: ClassVar[int] = 256 * 1024
    # How often the export is tried before the case is told it failed: 10 times, at most 5 minutes
    # apart (brief, D77). A test's workflow lowers it, as `audit_bound`.
    export_retries: ClassVar[RetryPolicy] = EXPORT_RETRIES
    # How often the case asks how each open child stands: a day (brief, D75). A test's workflow
    # shortens it, as `export_retries`, to see a check fire without skipping a day.
    child_check: ClassVar[timedelta] = CHILD_CHECK

    def __init__(self) -> None:
        self.state = CaseState("")  # named when the case opens
        self.case: Any = None  # the case definition, once read
        self.definition: dict[str, Any] = {}  # the same, as stored data
        # The plans its plan steps run: its release's, for a released case; the deployment's,
        # for a draft (brief, D51).
        self.its_plans: Mapping[str, Any] = self.plans
        self.release: ReleaseStart | None = None  # the release it runs; None: a draft
        # The environment whose registry it asks; None: none (brief, D5).
        self.registered: str | None = None
        self.inbox: list[Event] = []  # events not yet decided, in the order they came
        self.decided = 0  # events this run has decided
        self.running = 0  # activities and child plans started and not yet back
        # Each child running, a plan or a workflow step, by its step run, to stop it if the case
        # closes or a rule stops it (brief, D28) (brief, D40).
        self.children: dict[str, workflow.ChildWorkflowHandle[Any, Any]] = {}
        # Each step run the case has asked to stop, and why: asked once, never twice (brief, D40).
        self.stopping: dict[str, str] = {}
        # Each child case this run is starting, by its entry: a close waits until its start is
        # recorded. A child another run started has started (brief, D75).
        self.starting: set[str] = set()
        # Whether this run's daily check of its open children is set: one at a time (brief, D75).
        self.checking = False
        # An engine bug raised in a task beside the loop, which the loop raises in its turn.
        self.broken: Exception | None = None
        self.exporting = False  # whether this run's export of the case's records is under way
        self.woken = False  # whether an export just ended: the loop looks again (brief, D77)

    # Temporal: a signal is a message into a running workflow, recorded in its history, so replay
    # delivers it again at the same point.
    @workflow.signal(name="answer")
    def answer(self, sent: CaseAnswer) -> None:
        form = None if sent.form is None else dict(sent.form)
        roles = frozenset(sent.roles)
        answered = Answered(sent.entry, sent.outcome, sent.by, roles, form, at=now())
        self.inbox.append(replace(answered, wording=sent.wording))

    @workflow.signal(name="propose")
    def propose(self, sent: CaseRequest) -> None:
        roles = frozenset(sent.roles)
        suggested: Any = sent.suggested_by  # any text: `propose` refuses all but the advisor
        self.inbox.append(Proposed(sent.what, sent.by, roles, at=now(), suggested_by=suggested))

    @workflow.signal(name="retry")
    def retry(self, sent: CaseRequest) -> None:
        self.inbox.append(Retried(sent.what, sent.by, frozenset(sent.roles), at=now()))

    # An operator retries the case's failed audit export (brief, D26) (brief, D77).
    @workflow.signal(name="retry_export")
    def retry_export(self, sent: CaseRequest) -> None:
        self.inbox.append(ExportRetried(sent.by, frozenset(sent.roles), at=now()))

    @workflow.signal(name="claim")
    def claim(self, sent: CaseRequest) -> None:
        self.inbox.append(Claimed(sent.what, sent.by, frozenset(sent.roles), at=now()))

    @workflow.signal(name="give_back")
    def give_back(self, sent: CaseRequest) -> None:
        self.inbox.append(GivenBack(sent.what, sent.by, frozenset(sent.roles), at=now()))

    @workflow.signal(name="assign")
    def assign(self, sent: CaseAssignment) -> None:
        to_roles, roles = frozenset(sent.to_roles), frozenset(sent.roles)
        self.inbox.append(Assigned(sent.entry, sent.to, to_roles, sent.by, roles, at=now()))

    @workflow.signal(name="unassign")
    def unassign(self, sent: CaseRequest) -> None:
        self.inbox.append(Unassigned(sent.what, sent.by, frozenset(sent.roles), at=now()))

    @workflow.signal(name="close")
    def close(self, sent: CaseRequest) -> None:
        self.inbox.append(CloseAsked(sent.what, sent.by, frozenset(sent.roles), at=now()))

    @workflow.signal(name="forget")
    def forget(self, sent: CaseForget) -> None:
        self.inbox.append(
            ForgetApproved(
                sent.proposed_by,
                frozenset(sent.proposer_roles),
                sent.approved_by,
                frozenset(sent.approver_roles),
                at=now(),
            )
        )

    @workflow.signal(name="change")
    def change(self, sent: CaseChange) -> None:
        roles = frozenset(sent.roles)
        self.inbox.append(
            ChangeProposed(sent.kind, sent.target, sent.value, sent.by, roles, at=now())
        )

    @workflow.signal(name="migrate")
    def migrate(self, sent: CaseMigration) -> None:
        roles = frozenset(sent.roles)
        migration = sent.migration()
        self.inbox.append(
            ChangeProposed("migrate", migration.label, migration, sent.by, roles, at=now())
        )

    @workflow.signal(name="shown")
    def shown(self, sent: CaseRequest) -> None:
        self.inbox.append(Shown(sent.what, sent.by, frozenset(sent.roles), at=now()))

    # One signal for every event, whoever sends it: the sender is data (brief, D41).
    @workflow.signal(name="event")
    def event(self, sent: CaseEvent) -> None:
        self.inbox.append(
            Sent(sent.event, dict(sent.payload), sent.by, frozenset(sent.roles), at=now())
        )

    # A doorbell: a child case's workflow rings as its last act, with its entry only. Anyone may
    # send a signal, so it carries nothing the case would take: the case reads the child's end
    # itself (brief, D75).
    @workflow.signal(name="child_ended")
    def child_ended(self, entry: str) -> None:
        self.inbox.append(ChildRang(entry, at=now()))

    # A child case's parent closes it, saying why, as a person's close does (brief, D40). Sent
    # only by its parent's workflow, as other signals by the trusted API (brief, D19).
    @workflow.signal(name="close_by_parent")
    def close_by_parent(self, reason: str) -> None:
        self.inbox.append(ClosedByParent(reason, at=now()))

    # Temporal: a query reads a workflow's state without changing it, and isn't recorded.
    @workflow.query(name="report")
    def report(self) -> CaseReport:
        state = self.state
        # What waits for an operator, and what is owed and can't start, as in memory
        # (brief, D72).
        attention_now = needs_attention(state) if self.case is None else attention(self.case, state)
        if self.holding():
            attention_now.append(
                f"the audit export is {self.audit_bound // 1024} KB behind: the case decides "
                "nothing until it is written"
            )
        return CaseReport(
            state.phase,
            # What it waits for, and what it owes, as in memory (brief, D72); none before the
            # definition is read.
            [] if self.case is None else waiting_for(self.case, state),
            list(state.waiting),
            attention_now,
            list(state.flags),
            list(state.history),
            set_timers(state),
            state.release or "draft",
            state.engine,
            assignees(state),
            unwritten=len(state.audit) if state.engine >= RECORDS_FROM else 0,
            forgetting="" if self.case is None else family_says(self.case, state),
            forget_taken=state.forget_taken,
        )

    @workflow.query(name="view")
    def view(self, roles: list[str]) -> CaseView:
        """The case file as a person holding `roles` sees it, filtered here, in the worker, so
        nothing hidden from them leaves it (brief, D30)."""
        return case_view(self.case, self.state, roles, self.catalog.roles)

    @workflow.query(name="advisor_view")
    def advisor_view(self, asked: AdvisorAsked) -> AdvisorView:
        """What the step advisor is shown, asked for a person: computed here, in the worker,
        from the case's state, so no value leaves it (brief, D30) (brief, D62)."""
        roles = frozenset(asked.roles)
        return advisor_view(self.case, self.catalog, self.state, asked.by, roles, asked.at)

    @workflow.query(name="proposal_refused")
    def proposal_refused(self, asked: ProposalAsked) -> Refusal:
        """Why a person's proposal of a step would be refused now, decided on a copy of the
        state: a query, so nothing is decided or recorded (brief, D61)."""
        roles = frozenset(asked.roles)
        why = proposal_refused(
            self.case, self.catalog, self.state, asked.step, asked.by, roles, asked.at
        )
        return Refusal(why)

    @workflow.query(name="worded_view")
    def worded_view(self, asked: ViewAsked) -> ViewAnswer:
        """The view, in a wording revision of the case's release: its titles, the case's
        decisions. A refusal comes back as data, as a sheet's does (brief, D31) (brief, D51)."""
        try:
            case = self.worded(asked.wording)
        except WordingRefused as refused:
            return ViewAnswer(None, str(refused))
        return ViewAnswer(case_view(case, self.state, asked.roles, self.catalog.roles))

    def worded(self, wording: Wording | None) -> Any:
        """The case definition to show the case in: its own, or `wording`'s, once it is checked to
        be a revision of the release the case runs, with that release's digest. Only `display`
        can differ, so nothing it shows is decided differently (brief, D51)."""
        if wording is None:
            return self.case
        if self.release is None:
            raise WordingRefused(f"{wording} isn't a wording of this case: it is a draft")
        runs = f"{self.release.name} {self.release.release}"
        refused = WordingRefused(f"{wording} isn't a wording of {runs}, which this case runs")
        if (wording.name, wording.release) != (self.release.name, self.release.release):
            raise refused
        try:
            case = parse_case(json.loads(wording.case, parse_float=Decimal))
            plans = {
                ref: json.loads(text, parse_float=Decimal) for ref, text in wording.plans.items()
            }
        except (CaseInvalid, ValueError):
            raise refused from None
        if not is_release(case, plans, self.release.digest):
            raise refused
        return case

    @workflow.query(name="approval_sheet")
    def approval_sheet(self, asked: SheetAsked) -> SheetAnswer:
        """An open approval's sheet, with each fact's age at the reader's time, filtered here as
        the view is (brief, D18). A query changes nothing, so the time it is given decides
        nothing. A refusal comes back as data: a failure's message is sealed whoever raised it
        (brief, D31), and the reader must learn why; it names the entry, never a value."""
        try:
            case = self.worded(asked.wording)
            sheet = sheet_of(
                case, self.state, asked.entry, asked.roles, asked.at, self.catalog.roles
            )
            return SheetAnswer(sheet)
        except WordingRefused as refused:
            return SheetAnswer(None, wording_refused=str(refused))
        except (SheetRefused, TimeRefused) as refused:
            return SheetAnswer(None, str(refused))

    @workflow.query(name="migration_preview")
    def migration_preview(self, asked: MigrationAsked) -> PreviewAnswer:
        """What the migration would do to the case now, decided as its apply would be, on a copy
        of its state: a query changes nothing, and isn't recorded (brief, D53)."""
        seen = preview_migration(
            self.case, self.catalog, self.state, asked.target.migration(), asked.at
        )
        return PreviewAnswer(list(seen.refused), list(seen.lines))

    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)

    async def drive(self, start: CaseStart) -> CaseReport:
        """Open the case, then decide each event as it comes, until the case is closed."""
        info = workflow.info()  # recorded in history, so the same on replay
        # The case's name in its keys: its ID and its first run's, the same in every run of it
        # (brief, D27).
        self.state = CaseState(f"{info.workflow_id}/{info.first_execution_run_id}")
        try:
            case = self.case = parse_case(start.definition)
            self.definition = start.definition  # as stored data, for the next run's start
            named = None if start.release is None else self.released_on(case, start.release)
            if start.carried is None:
                await self.ask_to_open(pinned=start.parent is not None)
                parent = start.parent
                opened = Opened(
                    start.file,
                    start.opened_by,
                    at=now(),
                    engine=engine(),
                    release=named,
                    roles=frozenset(start.opener_roles),
                    # The children its release pins; and, for a child, its parent, the sources
                    # its parent gave, and whom its parent excluded (brief, D74).
                    cases={} if start.release is None else dict(start.release.cases),
                    parent=None if parent is None else (parent.case, parent.entry),
                    sources=None
                    if parent is None
                    else {name: frozenset(given) for name, given in parent.sources.items()},
                    excluded={} if parent is None else dict(parent.excluded),
                )
                self.decide(case, opened)
            else:
                # A case continued as new: each value read back by its type, so a date, which
                # crossed as text, is a day again (brief, D66).
                types = case_types(case, self.catalog)
                self.state = state_from_data(start.carried, types)
                self.registered = start.environment
        except (CaseInvalid, CaseRefused) as refused:
            if start.carried is not None:
                # A run continued as new: its start was read and checked when the case opened, so
                # one that no longer reads, or no longer gives its release's digest, means the code
                # changed. The workflow task fails, and the case waits for code that reads it,
                # never failed for good (brief, D17) (brief, D51).
                raise StartUnread(
                    f"{info.workflow_id} can't read the start it continued with: {refused}: deploy "
                    "code that reads it"
                ) from None
            # A case that can't open fails at once, saying why. Any other exception fails only the
            # workflow task, which Temporal retries until fixed code is deployed (brief, D17).
            kind = type(refused).__name__
            raise ApplicationError(str(refused), type=kind, non_retryable=True) from None
        if start.carried is not None:
            self.ask_open_children()  # this run holds no handle on them (brief, D75)
            self.check_daily()
        told_registry = False
        while True:
            await self.until_closed_and_written(start)
            if self.registered is not None and not told_registry:
                # Its registry lists it open until it says it closed: retried until the registry
                # answers, so the workflow can't end while its registry is unreachable
                # (brief, D5).
                await self.ask_registry(Asked(self.registered, closing=workflow.info().workflow_id))
                told_registry = True
            # What came with the close, or while the registry was asked, is refused and
            # recorded, never dropped while its sender's send succeeded (brief, D41, as added in
            # 11d's tutor review), and its record written too before the case ends (brief, D77).
            # Temporal fails a completion that a newer signal overtakes, so this run records that
            # signal too.
            if not self.inbox:
                break
        report = self.report()
        if start.parent is not None:
            # A child's last act: ring its parent, by its workflow ID, never a run ID, with the
            # entry only; the parent reads this report itself (brief, D75).
            ended = ending_of(start.parent.entry, self.case, self.state, now())
            report.ending = ending_data(ended)
            await ring(start.parent)
        return report

    async def until_closed_and_written(self, start: CaseStart) -> None:
        """Decide each event as it comes, until the case is closed, every record of it written, and
        nothing waits in its inbox. Once closed, an event is refused, its refusal recorded; while
        the export is behind, only the export's own events are decided (brief, D77)."""
        while self.state.phase != "closed" or self.unwritten() or self.inbox:
            self.export_due()
            await self.until_something_comes()
            self.woken = False
            if self.broken is not None:
                # An engine bug is never lost: it fails the workflow task, which Temporal retries
                # until fixed code is deployed (brief, D17); the log keeps its type (brief, D31).
                raise self.broken
            if self.state.phase == "closed" or self.holding():
                self.take_while_closed_or_held()
                continue
            # Before an event stamped `t`, every timer due by `t` fires, each stamped with its own
            # due time; with nothing in the inbox, every timer due by now (brief, D44).
            # The case's definition now: a migration may have moved it (brief, D53).
            if self.fire_due(self.case, self.inbox[0].at if self.inbox else now()):
                continue  # the case may have closed: the loop asks again
            if not self.inbox:
                if self.time_to_switch():
                    self.switch(start)
                continue
            await self.take(self.inbox.pop(0))

    async def take(self, event: Event) -> None:
        """Decide `event`; a refusal is recorded, and the case waits on as if it hadn't come."""
        try:
            names_its_entry(event, self.state)
            refuse_an_engine_not_opened(event)
            await self.ask_to_move(event)
            self.decide(self.case, event)
        except REFUSALS as refused:
            # In memory a refusal raises to the test; here nobody is there to catch it. It is
            # recorded, line and record, and the case waits on as if it hadn't come: `decide`
            # changed nothing (8b, slice 0) (brief, D76). Never queued for later (layer 6).
            self.state = record_refused(self.case, self.state, event, refused)

    def take_while_closed_or_held(self) -> None:
        """Once closed, refuse each event but the export's own; while the case holds, leave them
        waiting in the inbox, in order. The export's own events are decided either way."""
        waiting: list[Event] = []
        for event in self.inbox:
            if isinstance(event, ExportFailed | ExportRetried):
                try:
                    self.decide(self.case, event)
                except REFUSALS as refused:
                    self.state = record_refused(self.case, self.state, event, refused)
            elif self.state.phase == "closed":
                self.state = record_refused(self.case, self.state, event, CaseIsClosed())
            else:
                waiting.append(event)  # the case holds: decided once the export catches up
        self.inbox = waiting

    def unwritten(self) -> bool:
        """Whether the case has records not yet written to its store (brief, D77)."""
        return self.state.engine >= RECORDS_FROM and bool(self.state.audit)

    def holding(self) -> bool:
        """Whether so much waits unwritten that the case decides nothing new: a switch never
        carries more than the bound, and nothing is decided without its record (brief, D77)."""
        if self.state.phase == "closed" or not self.unwritten():
            return False
        return waiting_size(self.state.audit) >= self.audit_bound

    def export_due(self) -> None:
        """Write the records not yet written, one export at a time, unless it has failed and
        waits for an operator."""
        if self.exporting or not self.unwritten() or self.state.export_failed:
            return
        if self.state.phase != "closed" and not self.holding() and self.switch_due():
            # The records cross the switch in the state, and the next run writes them: an export
            # started now would hold the switch back for as long as it runs (brief, D27).
            return
        self.exporting = True
        self.running += 1  # the case never switches while its export is under way (brief, D27)
        self.beside(self.export())

    async def export(self) -> None:
        """Send the records not yet written to the case worker's store; once written, they leave
        the state, and their numbers are never given again. After its retries, the case is told it
        failed (brief, D17) (brief, D77)."""
        sending = list(self.state.audit)
        sent = ExportSent(
            workflow.info().workflow_id,
            [record_as_data(each) for each in sending],
            {name: list(roles) for name, roles in sensitive_fields(self.case).items()},
            {name: list(roles) for name, roles in restricted_fields(self.case).items()},
        )
        try:
            await workflow.execute_activity(
                "ventoux.audit.append",
                sent,
                start_to_close_timeout=EXPORT_CALL,
                retry_policy=self.export_retries,
            )
            last = sending[-1].number
            self.state.audit = [each for each in self.state.audit if each.number > last]
        except ActivityError as error:
            reason, service = export_failure(error)
            self.inbox.append(ExportFailed(reason, service, at=now()))
        finally:
            self.exporting = False
            self.running -= 1
            self.woken = True

    async def ask_to_open(self, pinned: bool) -> None:
        """In an environment, ask its registry whether the case may open: on its package's
        active release, with that digest, on the queue it was activated on; a draft only where
        drafts run; a child, `pinned`, on the release its parent pins, whichever is active
        (brief, D75). Refused, `CaseRefused`, and nothing is decided (brief, D54). The answer comes
        from an activity, recorded in this history: a replay reads it there, and never asks
        again. Behind a patch, so a case opened before 12e replays as it was recorded."""
        if self.environment is None or not workflow.patched(REGISTRY_PATCH):
            return
        self.registered = self.environment
        info = workflow.info()
        released = None
        if self.release is not None:
            released = Released(self.release.name, self.release.release, self.release.digest)
        answer = await self.ask_registry(
            Asked(
                self.environment,
                opening=Opening(info.workflow_id, info.task_queue, released, pinned=pinned),
            )
        )
        if not answer.done:
            raise CaseRefused(answer.said[0])

    async def ask_to_move(self, event: Event) -> None:
        """Before an answer that would apply a migration, ask the case's registry whether the
        target may run here: activated, not retired, with its digest. Found by deciding the
        answer on a copy first: `decide` is pure, so the copy decides exactly what the case
        would. Refused, `ChangeRefused`, recorded as a refused answer, and the request waits on
        (brief, D53) (brief, D54)."""
        if self.registered is None or not isinstance(event, Answered):
            return
        try:
            _, commands = decide(self.case, self.catalog, self.state, event)
        except REFUSALS:
            return  # the case refuses it itself, as always
        for command in commands:
            if isinstance(command, UseRelease):
                target = command.migration
                digest = Hash(target.method, target.sha256)
                moving = Moving(
                    workflow.info().workflow_id, Released(target.name, target.release, digest)
                )
                answer = await self.ask_registry(Asked(self.registered, moving=moving))
                if not answer.done:
                    raise ChangeRefused(answer.said[0])

    async def ask_registry(self, asked: Asked) -> Answer:
        """The registry's answer, through the case worker's activity, retried until it comes."""
        answer: Answer = await workflow.execute_activity(
            "ventoux.registry.asked", asked, start_to_close_timeout=CALL, result_type=Answer
        )
        return answer

    def released_on(self, case: Any, release: ReleaseStart) -> str:
        """The release's name, `refund 1`, once the case has checked that what it was given is
        that release's package; otherwise `CaseRefused`, so it never opens on behaviour nobody
        released. Depends on nothing the client did (brief, D34) (brief, D51)."""
        named = f"{release.name} {release.release}"
        if not is_release(case, release.plans, release.digest, release.cases):
            raise CaseRefused(
                f"{workflow.info().workflow_id} can't open on {named}: what it was given isn't "
                f"{named}'s package"
            )
        self.its_plans = release.plans  # only its release's plans, never the deployment's
        self.release = release
        return named

    async def until_something_comes(self) -> None:
        """Wait for an event, the time to continue as new, an engine bug, or the earliest timer's
        due time, whichever comes first. A case with no timer waits as it did before 11f, so its
        history replays the same; one with a timer waits on one workflow timer, for the soonest
        (brief, D44)."""
        # Closed, or holding, the case fires no timer: it decides nothing new (brief, D77).
        due = None if self.state.phase == "closed" or self.holding() else soonest(self.state)
        if due is not None and due <= workflow.now().timestamp():
            return  # one has fallen due already, as across a switch: it fires at once
        # Temporal: with a timeout, `wait_condition` starts a workflow timer, which history
        # records, and raises `TimeoutError` when it fires first; it is cancelled otherwise.
        timeout = None if due is None else due - workflow.now().timestamp()
        try:
            await workflow.wait_condition(self.something_came, timeout=timeout)
        except TimeoutError:
            pass  # the timer's time has come

    def something_came(self) -> bool:
        """Whether the loop has something to do: an engine bug, an export ended, an event it may
        decide, or the time to continue as new."""
        if self.broken is not None or self.woken:
            return True
        if self.state.phase == "closed":
            return bool(self.inbox)  # a closed case never switches: it waits for its export
        if self.holding():
            # Only the export's own events are taken while the case holds.
            return any(isinstance(each, ExportFailed | ExportRetried) for each in self.inbox)
        return bool(self.inbox) or self.time_to_switch()

    def fire_due(self, case: Any, at: int) -> bool:
        """Decide every timer due by `at`, one at a time and in order, each stamped with its own
        due time: a firing may set or end timers, so the next is asked for afresh. Whether any
        fired (brief, D44)."""
        fired = False
        while self.state.phase != "closed" and (due := next_due(self.state, at)) is not None:
            self.decide(case, due)
            fired = True
        return fired

    def time_to_switch(self) -> bool:
        """Whether the case should continue as new now: enough events in this run, or Temporal
        suggests it (its history is getting large); and nothing is running, whose result would
        come back to a run that has ended (brief, D27)."""
        return self.running == 0 and self.switch_due()

    def switch_due(self) -> bool:
        """Enough events in this run, or Temporal suggests continuing as new."""
        enough = self.decided >= self.events_per_run
        return enough or workflow.info().is_continue_as_new_suggested()

    def switch(self, start: CaseStart) -> None:
        """Continue as new, carrying the whole state. Only at a quiet point: no event waiting to
        be decided, nothing running, no signal handler part-way. A signal that arrives while the
        switch is committed fails it, and this run decides that signal first: no answer is ever
        carried as a queue (brief, D27)."""
        assert not self.inbox and self.running == 0 and workflow.all_handlers_finished()
        # The definition and release it runs now, which a migration may have moved (brief, D53).
        carried = CaseStart(
            self.definition,
            {},
            start.opened_by,
            state_as_data(self.state),
            self.release,
            self.registered,
            parent=start.parent,  # a child rings the same parent from whichever run (brief, D75)
        )
        # Temporal: ends this run and starts the next one of the same workflow, with `carried`.
        workflow.continue_as_new(carried)

    def decide(self, case: Any, event: Event) -> None:
        """Decide `event`, then start what the case asks for."""
        self.decided += 1
        self.state, commands = decide(case, self.catalog, self.state, event)
        for command in commands:
            self.carry(command)

    def carry(self, command: Command) -> None:
        """Start the command; what it gives comes back to the inbox when it arrives."""
        if isinstance(command, UseRelease):
            self.use_release(command.migration)
            return
        if isinstance(command, StopPlan):
            self.beside(self.stop_plan(command))
            return
        if isinstance(command, CancelWorkflow):
            self.cancel_workflow(command)
            return
        if isinstance(command, CloseCase):
            self.beside(self.close_child(command))
            return
        if isinstance(command, ReadChild):
            self.running += 1  # the read is recorded before the case may switch
            self.beside(self.until_back(self.read_child(command)))
            return
        if isinstance(command, OpenCase):
            self.stopping.pop(command.entry, None)  # a retry is a new attempt (brief, D26)
            self.running += 1  # until its start is recorded
            self.starting.add(command.entry)
            self.beside(self.open_child(command))
            return
        self.running += 1
        # A start is a new attempt, an operator's retry under the same entry included: a stop
        # asked of an earlier one no longer applies. One decided after it, in the same decision,
        # is carried after it, and asks again (brief, D26) (brief, D40).
        self.stopping.pop(command.entry, None)
        if isinstance(command, StartPlan):
            self.beside(self.until_back(self.run_plan(command)))
        elif isinstance(command, StartWorkflow):
            self.beside(self.until_back(self.run_workflow(command)))
        else:
            self.beside(self.until_back(self.run_activity(command)))

    def use_release(self, migration: Migration) -> None:
        """Decide from now on with the target's definition, run its plans, and carry both across
        every continue-as-new, as the start a case opens with does. A plan already running keeps
        the plan in its own start (brief, D28) (brief, D53)."""
        self.definition = dict(migration.case)
        self.case = parse_case(self.definition)
        digest = Hash(migration.method, migration.sha256)
        plans = dict(migration.plans)
        cases = dict(migration.cases)  # the children the target pins (brief, D74)
        self.release = ReleaseStart(migration.name, migration.release, digest, plans, cases)
        self.its_plans = plans

    def beside(self, work: Coroutine[Any, Any, None]) -> None:
        """Run `work` in a task beside the loop. An exception it raises is an engine bug: kept
        for the loop to raise, never left in the task, where nobody would retrieve it and
        Temporal's SDK would log the task's description, quoting it (layer 9c)."""
        # asyncio: a task runs alongside the loop; Temporal's event loop runs it deterministically.
        asyncio.create_task(self.watched(work))

    async def watched(self, work: Coroutine[Any, Any, None]) -> None:
        try:
            await work
        except Exception as bug:  # noqa: BLE001 (every kind of bug: none may vanish)
            self.broken = bug

    async def until_back(self, carried: Coroutine[Any, Any, None]) -> None:
        """Run `carried`, which puts what happened in the inbox; then it no longer runs."""
        try:
            await carried
        finally:
            self.running -= 1

    async def run_plan(self, command: StartPlan) -> None:
        """Run the step's plan as a child workflow, `<case ID>/<entry>`, and put how it ended in
        the inbox (brief, D28): succeeded is done, a failed final state the outcome `failed`, a
        plan that stops or can't start fails the step."""
        try:
            plan = supplied(self.its_plans, command.plan)
        except PlanNotSupplied as missing:
            self.inbox.append(Failed(command.entry, str(missing), at=now()))  # fail closed
            return
        if (wrong := wrong_references(plan, command)) is not None:
            self.inbox.append(Failed(command.entry, wrong, at=now()))  # fail closed
            return
        fields = {
            name: Given(given.value, sorted(given.sources))
            for name, given in command.fields.items()
        }
        steered = {steering.said: sorted(steering.sources) for steering in command.steered}
        start = PlanStart(
            self.its_plans[command.plan],
            fields,
            command.run,
            dict(command.excluded),
            steered or None,
        )
        try:
            # Temporal: a child workflow is a workflow the case starts and waits for; its own
            # history holds its waits and activities. Its ID names the step run; a retry starts it
            # again under the same ID, with the same keys (brief, D26).
            child = await workflow.start_child_workflow(
                self.plan_workflow,
                start,
                id=f"{workflow.info().workflow_id}/{command.entry}",
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                result_type=RunReport,
            )
            self.children[command.entry] = child
            if command.entry in self.stopping:  # stopped while the child was starting
                await signal_stop(child, self.stopping[command.entry])
            ran: RunReport = await child
        except ChildWorkflowError as error:
            cause = error.cause
            said = cause.message if isinstance(cause, FailureError) else str(error)
            self.inbox.append(
                Failed(command.entry, f"{plan.plan}@{plan.version} can't start: {said}", at=now())
            )
            return
        finally:
            self.children.pop(command.entry, None)
        # What the plan decided, for the record of the step's end (brief, D77).
        decided = tuple(self.plan_ran(command.entry, ran))
        if ran.status == "cancelled":
            # Ended by the close, with what finished or failed in it after the close (brief, D28).
            self.inbox.append(
                PlanCancelled(command.entry, tuple(ran.after_stop), at=now(), ran=decided)
            )
        elif ran.status == "succeeded":
            self.inbox.append(Completed(command.entry, {}, at=now(), ran=decided))
        elif ran.status == "failed":
            self.inbox.append(
                Completed(command.entry, {}, "failed", at=now(), ran=decided)
            )  # a failed final state
        else:
            self.inbox.append(
                Failed(
                    command.entry, f"{command.plan} stopped: {ran.reason}", at=now(), ran=decided
                )
            )

    def plan_ran(self, entry: str, ran: RunReport) -> list[Decision]:
        """What the plan run `entry` decided, as its report gives it, each naming its step and
        run."""
        step = entry.split("#")[0]
        # A plan's inputs aren't the case's fields: each comes back as it crossed.
        return [
            replace(decision_from_data(each, {}), step=step, entry=entry) for each in ran.decisions
        ]

    async def run_workflow(self, command: StartWorkflow) -> None:
        """Run the workflow step as a child workflow, `<case ID>/<entry>`, of the type and on the
        task queue its binding names, for at most its contract's timeout; put what it gave in the
        inbox (brief, D6). Its output is checked and tagged by `decide`, from the contract."""
        binding = self.workflows.get(command.workflow)
        if binding is None:
            self.inbox.append(
                Failed(command.entry, unbound(command.workflow), at=now())
            )  # fail closed
            return
        contract = self.catalog.workflow(command.workflow)
        try:
            # Temporal: the team's workflow runs on their worker; the case waits for its result,
            # recorded in its history. A retry starts it again under the same ID (brief, D26). Its
            # handle is kept, to cancel it if its contract says it may be: the case then waits for
            # it to end, whatever it does (brief, D40).
            child = await workflow.start_child_workflow(
                binding.workflow,
                command.inputs,
                id=f"{workflow.info().workflow_id}/{command.entry}",
                task_queue=binding.task_queue,
                execution_timeout=timedelta(seconds=contract.timeout),
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                cancellation_type=workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
                result_type=dict,
            )
            self.children[command.entry] = child
            if command.entry in self.stopping:  # cancelled while the child was starting
                # Temporal: a child's handle is a task; cancelling it, with a reason, sends the
                # cancellation request, and awaiting it then waits for the child to end.
                child.cancel(self.stopping[command.entry])
            output: dict[str, Any] = await child
        except ChildWorkflowError as error:
            if isinstance(error.cause, CancelledError) and command.entry in self.stopping:
                # Ended cancelled, as the case asked: its team promises nothing it started
                # completed after the request (brief, D40). A cancellation the case never asked
                # for, from outside, is a failure like any other: a person looks at it
                # (brief, D17).
                self.inbox.append(WorkflowCancelled(command.entry, at=now()))
            else:
                failure = workflow_failure(command.workflow, contract, error)
                self.inbox.append(Failed(command.entry, failure, at=now()))
            return
        finally:
            self.children.pop(command.entry, None)
        self.inbox.append(Completed(command.entry, output, at=now()))

    async def open_child(self, command: OpenCase) -> None:
        """Start the step's child case as its own workflow, `<case ID>/<entry>`, under the case's
        key, on its pinned release, abandoned to itself when this run continues as new: the case
        closes it itself (brief, D75). Then watch it beside the loop, never holding a switch."""
        info = workflow.info()
        child_id = f"{info.workflow_id}/{command.entry}"
        try:
            start = self.child_start(command)
            # Temporal: a child workflow with `ABANDON` outlives its parent's run, which the
            # default policy would terminate when the parent continues as new. A retry starts it
            # again under the same ID only if the earlier attempt failed (brief, D26).
            child = await workflow.start_child_workflow(
                info.workflow_type,
                start,
                id=child_id,
                task_queue=info.task_queue,
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
                result_type=CaseReport,
            )
        except (ChildWorkflowError, CaseInvalid) as error:
            cause = error.cause if isinstance(error, ChildWorkflowError) else None
            said = cause.message if isinstance(cause, FailureError) else str(error)
            self.inbox.append(
                Failed(command.entry, f"{command.case} can't start: {said}", at=now())
            )
            return
        finally:
            self.running -= 1
            self.starting.discard(command.entry)
        self.check_daily()
        if command.entry in self.stopping:  # closed while it was starting: told once started
            await self.close_child(CloseCase(command.entry, self.stopping.pop(command.entry)))
        await self.watch_child(command, child)

    def child_start(self, command: OpenCase) -> CaseStart:
        """What the child opens with: its definition, its pinned release with its own plans and
        digest, its opening, and its parent (brief, D74)."""
        assert self.release is not None  # only a release pins children
        child = parse_case(dict(cast_data(command.definition)))
        named = {s.plan for s in child.steps.values() if isinstance(s, PlanStep)}
        plans = {reference: self.its_plans[reference] for reference in named}
        parsed = {reference: parse_plan(data) for reference, data in plans.items()}
        digest = behaviour_digest(child, parsed)
        release = int(command.case.split("@")[1])
        return CaseStart(
            dict(cast_data(command.definition)),
            {name: given.value for name, given in command.fields.items()},
            None,  # opened by its parent case, never by a person (brief, D74)
            release=ReleaseStart(child.case, release, digest, plans),
            parent=ParentStart(
                workflow.info().workflow_id,
                command.entry,
                {name: sorted(given.sources) for name, given in command.fields.items()},
                dict(command.excluded),
            ),
        )

    async def watch_child(
        self, command: OpenCase, child: workflow.ChildWorkflowHandle[Any, CaseReport]
    ) -> None:
        """Wait beside the loop for the child this run started. Its report comes by its
        doorbell; a child that ends without one is said at once, never waited for in silence
        (brief, D17) (brief, D75)."""
        try:
            await child
        except ChildWorkflowError as error:
            cause = error.cause
            if isinstance(cause, ApplicationError) and cause.type == "CaseRefused":
                said = f"{command.case} refused its opening: {cause.message}"
                self.inbox.append(Failed(command.entry, said, at=now()))
                return
            self.inbox.append(ChildNotEnded(command.entry, ended_how(cause), at=now()))

    async def read_child(self, command: ReadChild) -> None:
        """Read the child's end from its own result, through the case worker's activity, and
        decide on that, never on what rang (brief, D75)."""
        asked = ChildAsked(command.run, settle=SETTLE)  # the child that rang may be ending
        read = await workflow.execute_activity(
            "ventoux.child.read", asked, start_to_close_timeout=CALL, result_type=ChildRead
        )
        self.inbox.append(event_of(command.entry, read, now()))

    def open_children(self) -> list[str]:
        """The entries of the case's child cases still open, as its state says."""
        steps = self.case.steps
        running = (run for run in self.state.runs if run.status == "running")
        return [run.entry for run in running if isinstance(steps.get(run.step), CaseStep)]

    def ask_open_children(self) -> None:
        """Ask how each open child stands: a run after a switch can't watch a child another run
        started, so it asks as it starts. A child ended without reporting fails its step, never
        waited for in silence (brief, D17) (brief, D75)."""
        for entry in self.open_children():
            self.running += 1  # the read is recorded before the case may switch
            self.beside(self.until_back(self.ask_child(entry)))

    def check_daily(self) -> None:
        """While the case has an open child, ask how each stands once a day: a child that ended
        without ringing, and that no watch heard, goes unnoticed a day at most (brief, D17)
        (brief, D75). A case with no child sets no timer, so histories recorded before 18d
        replay as they were."""
        if self.checking or not self.open_children():
            return
        self.checking = True
        self.beside(self.daily_checks())

    async def daily_checks(self) -> None:
        while self.open_children():
            # Temporal: a durable timer, recorded in history; it holds no switch, and a run that
            # ends while it waits simply drops it.
            await workflow.sleep(self.child_check)
            self.ask_open_children()
        self.checking = False

    async def ask_child(self, entry: str) -> None:
        """Read how the child at `entry` stands; one still open changes nothing, unrecorded."""
        asked = ChildAsked(f"{workflow.info().workflow_id}/{entry}")
        read = await workflow.execute_activity(
            "ventoux.child.read", asked, start_to_close_timeout=CALL, result_type=ChildRead
        )
        if read.ending is None and read.how == "open":
            return
        self.inbox.append(event_of(entry, read, now()))

    async def close_child(self, command: CloseCase) -> None:
        """Close the child case, saying why, through its own signal, once its start is recorded,
        asked once (brief, D40) (brief, D75)."""
        if command.entry in self.starting:
            self.stopping[command.entry] = command.reason  # starting: told once started
            return
        child = workflow.get_external_workflow_handle(
            f"{workflow.info().workflow_id}/{command.entry}"
        )
        try:
            await child.signal("close_by_parent", command.reason)
        except ApplicationError as error:
            if error.type != ENDED:
                raise  # an engine bug, never lost (brief, D17)

    async def stop_plan(self, command: StopPlan) -> None:
        """Stop a child plan because the case is closing or a rule stops it (brief, D28)
        (brief, D40). A signal, not Temporal's cancellation: cancellation would cut short the
        await on an activity running in the plan, which must finish (brief, D10); the signal lets
        the plan's driver cancel its open wait and start nothing new, and the plan ends
        `cancelled`. Its reason names only the entry that asked; a close's is the default, so a
        history recorded before 11c, whose signal gave none, replays the same."""
        if command.entry in self.stopping:
            return  # asked once, never twice
        self.stopping[command.entry] = command.reason
        child = self.children.get(command.entry)
        if child is not None:  # else it is starting: `run_plan` signals it once started
            await signal_stop(child, command.reason)

    def cancel_workflow(self, command: CancelWorkflow) -> None:
        """Cancel a workflow step whose contract says it may be: Temporal asks the child to
        cancel, with the reason, and the case waits for it to end (brief, D40). Asked once."""
        if command.entry in self.stopping:
            return
        self.stopping[command.entry] = command.reason
        child = self.children.get(command.entry)
        if child is not None:  # else it is starting: `run_workflow` cancels it once started
            child.cancel(command.reason)

    async def run_activity(self, command: Schedule) -> None:
        """Run the activity, retried and timed out as its contract says (brief, D17), and put
        what happened in the inbox: its output, a declared outcome, or a failure."""
        contract = self.catalog.get(command.activity)
        try:
            # Temporal: the result is recorded in history; on replay it is read back, never
            # called again.
            output: dict[str, Any] = await workflow.execute_activity(
                command.activity, command.inputs, **activity_options(contract), result_type=dict
            )
        except ActivityError as error:
            cause = error.cause
            if isinstance(cause, ApplicationError) and cause.type == OUTCOME:
                self.inbox.append(Completed(command.entry, {}, cause.message, at=now()))
                return
            said = cause.message if isinstance(cause, FailureError) else str(error)
            # Never recorded: it may quote a sensitive value (brief, D31).
            self.inbox.append(
                Failed(
                    command.entry,
                    f"{command.activity} failed with {raised(error)}: {Sensitive(said)}",
                    at=now(),
                )
            )
            return
        self.inbox.append(Completed(command.entry, output, at=now()))


async def signal_stop(child: workflow.ChildWorkflowHandle[Any, Any], reason: str) -> None:
    """Signal a child plan to stop, with the reason. A child that has just ended can't be
    signalled, and needs nothing: its result is already on its way to the case. Any other
    failure is an engine bug, never lost (brief, D17)."""
    try:
        await child.signal("stop", reason)
    except ApplicationError as error:
        if error.type != ENDED:
            raise


async def ring(parent: ParentStart) -> None:
    """A child's doorbell, to its parent's workflow ID: whichever run is current hears it. A
    parent that has already ended needs nothing (brief, D75)."""
    handle = workflow.get_external_workflow_handle(parent.case)
    try:
        await handle.signal("child_ended", parent.entry)
    except ApplicationError as error:
        if error.type != ENDED:
            raise


def ended_how(cause: BaseException | None) -> str:
    """How a child's workflow ended without its report, as the parent's line says it."""
    if isinstance(cause, TerminatedError):
        return "it was terminated"
    if isinstance(cause, TemporalTimeout):
        return "it timed out"
    if isinstance(cause, CancelledError):
        return "it was cancelled"
    return "it failed"


def cast_data(data: object) -> dict[str, Any]:
    """Stored data as the dict it is: a definition crosses as JSON's object."""
    assert isinstance(data, dict)
    return data


# How Temporal says a workflow signalled has already ended.
ENDED = "ExternalWorkflowExecutionNotFound"


def workflow_failure(reference: str, contract: WorkflowContract, error: ChildWorkflowError) -> str:
    """Why a workflow step failed, as the history says it: past its timeout, or what it said."""
    cause = error.cause
    if isinstance(cause, TemporalTimeout):
        return f"{reference} didn't finish within its timeout of {contract.timeout}s"
    said = cause.message if isinstance(cause, FailureError) else str(error)
    # Its type, never what it said (brief, D31).
    return f"{reference} failed with {raised(error)}: {Sensitive(said)}"


# Ventoux's own refusals of an export, whose words never quote a value: said whole.
EXPORT_REFUSALS = ("ExportRefused", "AuditRefused")
# The key service's errors, met sealing for the export (brief, D78).
KEY_SERVICE = ("KeyUnavailable", "KeyRefused")


class CaseIsClosed(Exception):
    """An event that came once the case had closed: refused, its refusal recorded."""

    def __str__(self) -> str:
        return "the case is closed"


def export_failure(error: ActivityError) -> tuple[str, str]:
    """Why the export failed, as the case says it, and which service failed. Ventoux's own
    refusals, and the key service's errors (Ventoux's own words, naming the case and the service,
    never a value), are said whole; anything else is the store's, by its type alone, since a
    store's error may quote anything (brief, D31) (brief, D78)."""
    cause = error.cause
    kind = cause.type if isinstance(cause, ApplicationError) and cause.type else None
    if kind in EXPORT_REFUSALS:
        assert isinstance(cause, ApplicationError)  # its kind says so
        return cause.message, "the store"
    if kind in KEY_SERVICE:
        assert isinstance(cause, ApplicationError)
        return cause.message, "the key service"
    return f"the store failed with {kind or 'an error'}: {Sensitive('')}", "the store"


def waiting_size(records: list[AuditRecord]) -> int:
    """How much the records waiting take, measured as data, each sealed value at what sealing
    adds to it: what the switch would carry, and close to what the export writes."""

    def measured(value: object) -> str:
        return "x" * SEALED_SIZE if isinstance(value, Sensitive) else str(value)

    return sum(len(json.dumps(record_as_data(each), default=measured)) for each in records)


# What sealing a value adds, at most, as the export writes it: its ciphertext in base64, its part
# and who may see it.
SEALED_SIZE = 512


def engine() -> int:
    """The engine version a case opens at: asked of Temporal's patch markers, newest first, so a
    replay reads the version its history recorded (brief, D51). Temporal: `patched` says whether
    a marker is in force, adding it when the run is new; asked only at the opening."""
    return opening_engine(OPENING, lambda version: workflow.patched(f"ventoux-engine-{version}"))


def now() -> int:
    """The workflow's time as each event reaches the case, in whole seconds since the epoch.
    Temporal's workflow time is recorded in history, so a replay stamps the same times; the case
    itself reads no clock (brief, D33)."""
    return int(workflow.now().timestamp())  # whole seconds, rounded down


def names_its_entry(event: Event, state: CaseState) -> None:
    """On Temporal an answer names the entry it answers (`review#1`), never a step: after a
    rework, an answer to `review` would answer `review#2`, which its sender never saw (layer 6).
    The in-memory script may answer by step: it runs in order, with no one clicking."""
    if isinstance(event, Answered) and "#" not in event.entry:
        step = event.entry
        open_now = [
            entry for entry in state.waiting if entry.split("#")[0] in (step, f"{step}.approval")
        ]
        example = open_now[0] if open_now else f"{step}#1"
        raise AnswerRefused(f"name the entry it answers, such as {example}")


def refuse_an_engine_not_opened(event: Event) -> None:
    """A migration to an engine version this code knows, but opens no case at, is refused when
    proposed, saying so. Opening one there would leave a case deciding as a version not yet
    finished, which a later release of it would decide differently (brief, D51). In memory it
    stays possible: the engine's own tests decide as it. Checked at the proposal only: a request
    reaches a case no other way, and code that didn't know the version refused it there too."""
    if not isinstance(event, ChangeProposed) or not isinstance(event.value, Migration):
        return
    if event.value.engine in KNOWN and event.value.engine not in OPENING:
        opened = ", ".join(str(version) for version in OPENING)
        raise ChangeRefused(
            f"engine {event.value.engine} is one this code knows but doesn't run cases at yet "
            f"(it runs them at {opened})"
        )


async def start_case(
    client: Client,
    workflow: type[CaseWorkflow],
    opening_on: Record | dict[str, Any],
    file: Mapping[str, Any],
    id: str,
    task_queue: str,
    opened_by: str | None = None,
    opener_roles: Sequence[str] = (),
) -> WorkflowHandle[CaseWorkflow, CaseReport]:
    """Open a case with `file`, as a run of `workflow`, on a release's record, or on a definition,
    which makes it a draft (brief, D51). `id` is the case (`refund-A-1001`): a second case with the
    same ID is refused (brief, D27). The case's key is made first, and never again: if starting
    then fails, the ID is spent (brief, D31). `opener_roles` are the opener's roles, as the API
    states them, so an assignment rule asking the opener can judge them (brief, D71)."""
    keys = keys_of(client)
    # The codec finds a key from the part of a workflow ID before its first `/` (brief, D31).
    if "/" in id:
        raise ValueError(f'{id} can\'t name a case: a case ID has no "/"')
    await asyncio.to_thread(keys.create, id)  # off the event loop (brief, D78)
    await client.start_workflow(
        workflow.run,
        opening(opening_on, file, opened_by, opener_roles),
        id=id,
        task_queue=task_queue,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
    return case_handle(client, workflow, id)


def opening(
    opening_on: Record | dict[str, Any],
    file: Mapping[str, Any],
    opened_by: str | None = None,
    opener_roles: Sequence[str] = (),
) -> CaseStart:
    """What a case opens with: a release's case and plans, read from its record as the engine
    reads a definition, numbers as exact decimals (brief, D20); or a definition, for a draft."""
    if isinstance(opening_on, Record):
        definition = json.loads(opening_on.written.case, parse_float=Decimal)
        # Every plan in the package, its children's too (one reference is one plan), and the
        # children it pins (brief, D74).
        plans = {
            reference: json.loads(text, parse_float=Decimal)
            for reference, text in all_plans(opening_on.written)
        }
        cases = {
            reference: json.loads(child.case, parse_float=Decimal)
            for reference, child in opening_on.written.cases.items()
        }
        release = ReleaseStart(opening_on.name, opening_on.release, opening_on.digest, plans, cases)
    else:
        definition, release = opening_on, None
    # Each sensitive field's value wrapped: it crosses Temporal in its own part, sealed with the
    # case's key (brief, D31). The workflow checks the definition; here a field marked anything
    # but `false` counts as sensitive, so a malformed mark never sends a value in plain text.
    fields = definition.get("fields", {})
    sensitive = {
        name for name, field in fields.items() if dict(field).get("sensitive", False) is not False
    }
    sealed = {
        name: Sensitive(value) if name in sensitive else value for name, value in file.items()
    }
    start = CaseStart(definition, sealed, opened_by, None, release)
    start.opener_roles = sorted(opener_roles)
    return start


def wording_of(kept: Record) -> Wording:
    """The wording of a release record, or of one of its wording revisions, to show a case in."""
    plans = dict(kept.written.plans)
    return Wording(kept.name, kept.release, kept.wording, kept.written.case, plans)


def case_handle(
    client: Client, workflow: type[CaseWorkflow], id: str
) -> WorkflowHandle[CaseWorkflow, CaseReport]:
    """The case `id`, by its ID alone, so it always reaches its latest run (brief, D27)."""
    return client.get_workflow_handle_for(workflow.run, id)


async def answer(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    entry: str,
    outcome: str,
    by: str,
    roles: list[str],
    form: Mapping[str, Any] | None = None,
    wording: int | None = None,
) -> None:
    """Answer the open `entry` (`review#1`, as `report` shows it in `waiting_at`) with `outcome`,
    as the person `by`, who has `roles`. The caller vouches for who `by` is and their roles: only
    the Ventoux API may send answers (brief, D19). Every value of `form` crosses sealed: the
    client can't tell which fields are sensitive, and the case keeps sealed only those
    (brief, D31)."""
    sealed = None if form is None else {name: Sensitive(value) for name, value in form.items()}
    sent = CaseAnswer(entry, outcome, by, sorted(roles), sealed, wording)
    await case.signal(CaseWorkflow.answer, sent)


async def propose(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    step: str,
    by: str,
    roles: list[str],
    suggested_by: Literal["step-advisor"] | None = None,
) -> None:
    """Propose starting `step`, as the person `by`, who has `roles`, perhaps on the step
    advisor's suggestion; admission decides (brief, D61)."""
    await case.signal(CaseWorkflow.propose, CaseRequest(step, by, sorted(roles), suggested_by))


async def shown_to_advisor(
    case: WorkflowHandle[CaseWorkflow, CaseReport], by: str, roles: list[str], at: int
) -> AdvisorView:
    """What the step advisor is shown of the case for `by`, who has `roles`, at `at`: a query,
    computed in the worker (brief, D62)."""
    return await case.query(CaseWorkflow.advisor_view, AdvisorAsked(by, sorted(roles), at))


async def refused_proposal(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    step: str,
    by: str,
    roles: list[str],
    at: int,
) -> str | None:
    """Why `by`'s proposal of `step` would be refused at `at`, or None: a query, deciding
    nothing (brief, D61)."""
    asked = ProposalAsked(step, by, sorted(roles), at)
    return (await case.query(CaseWorkflow.proposal_refused, asked)).reason


async def claim(
    case: WorkflowHandle[CaseWorkflow, CaseReport], entry: str, by: str, roles: list[str]
) -> None:
    """Claim the open `entry` (`review#1`) for `by`, who has `roles`: they become the one asked to
    answer it, never more (brief, D69). The caller vouches for who `by` is (brief, D19)."""
    await case.signal(CaseWorkflow.claim, CaseRequest(entry, by, sorted(roles)))


async def assign(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    entry: str,
    to: str,
    to_roles: list[str],
    by: str,
    roles: list[str],
) -> None:
    """Give the open `entry` to `to`, who has `to_roles`, as `by`, whose role assigns: whoever
    holds it now (brief, D70). The caller vouches for both people and their roles (brief, D19)."""
    sent = CaseAssignment(entry, to, sorted(to_roles), by, sorted(roles))
    await case.signal(CaseWorkflow.assign, sent)


async def unassign(
    case: WorkflowHandle[CaseWorkflow, CaseReport], entry: str, by: str, roles: list[str]
) -> None:
    """Return the held `entry` to its queue, without its holder, as `by`, whose role assigns
    (brief, D70)."""
    await case.signal(CaseWorkflow.unassign, CaseRequest(entry, by, sorted(roles)))


async def give_back(
    case: WorkflowHandle[CaseWorkflow, CaseReport], entry: str, by: str, roles: list[str]
) -> None:
    """Give the held `entry` back to its queue, as its holder `by` (brief, D69)."""
    await case.signal(CaseWorkflow.give_back, CaseRequest(entry, by, sorted(roles)))


async def retry(
    case: WorkflowHandle[CaseWorkflow, CaseReport], entry: str, by: str, roles: list[str]
) -> None:
    """Retry the failed run `entry` (`pay#1`), as an operator: the same run, the same key
    (brief, D26)."""
    await case.signal(CaseWorkflow.retry, CaseRequest(entry, by, sorted(roles)))


async def retry_export(
    case: WorkflowHandle[CaseWorkflow, CaseReport], by: str, roles: list[str]
) -> None:
    """Retry the case's failed audit export, as an operator, once its store is back
    (brief, D26) (brief, D77)."""
    await case.signal(CaseWorkflow.retry_export, CaseRequest("audit export", by, sorted(roles)))


async def close(
    case: WorkflowHandle[CaseWorkflow, CaseReport], reason: str, by: str, roles: list[str]
) -> None:
    """Close the case with the declared `reason`, as the person `by` (brief, D10)."""
    await case.signal(CaseWorkflow.close, CaseRequest(reason, by, sorted(roles)))


async def propose_change(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    kind: str,
    target: str,
    value: Any,
    by: str,
    roles: list[str],
) -> None:
    """Propose a change to the case, as the person `by`, who has `roles`: `edit` the field
    `target` to `value`, or `skip` the failed run `target` (`pay#1`) with `value` None. Someone
    else approves it by answering its entry (`case.change#1`, as `report` shows it in
    `waiting_at`). An edit's value crosses sealed, as an answer's form does (brief, D31)
    (brief, D52)."""
    sealed = None if value is None else Sensitive(value)
    await case.signal(CaseWorkflow.change, CaseChange(kind, target, sealed, by, sorted(roles)))


async def propose_migration(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    record: Record,
    mapping: Mapping[str, Mapping[str, str]],
    by: str,
    roles: list[str],
    engine: int = ENGINE,
) -> None:
    """Propose moving the case to the release `record` keeps, renaming names by `mapping`, as the
    person `by`, who has `roles`; the case moves to engine version `engine`, by default this
    code's. Someone else approves it by answering its entry (`case.change#1`). The caller vouches
    that `record` is the release store's (brief, D19) (brief, D53)."""
    await case.signal(CaseWorkflow.migrate, migration_sent(record, mapping, engine, by, roles))


def migration_sent(
    record: Record,
    mapping: Mapping[str, Mapping[str, str]],
    engine: int,
    by: str,
    roles: list[str],
) -> CaseMigration:
    """A migration to `record`, as it crosses to a case."""
    target = migration_of(record, {kind: dict(names) for kind, names in mapping.items()}, engine)
    return CaseMigration(
        target.name,
        target.release,
        target.method,
        target.sha256,
        dict(target.case),
        dict(target.plans),
        {kind: dict(names) for kind, names in target.mapping.items()},
        target.engine,
        by,
        sorted(roles),
        dict(target.cases),
    )


async def preview_migrations(
    client: Client,
    workflow: type[CaseWorkflow],
    cases: list[str],
    record: Record,
    mapping: Mapping[str, Mapping[str, str]],
    engine: int = ENGINE,
    at: int | None = None,
) -> dict[str, PreviewAnswer]:
    """What moving each case in `cases`, by ID, to `record` would do, at `at` (the API's own clock
    by default): each case in the answer, in order, with what it would get or why not, a case
    that can't be read included, never skipped (brief, D53). The cohort is the IDs given: finding
    the open cases of a release comes with 12e's registry."""
    if at is None:
        at = int(datetime.now(UTC).timestamp())  # whole seconds, rounded down
    asked = MigrationAsked(migration_sent(record, mapping, engine, "", []), at)
    seen: dict[str, PreviewAnswer] = {}
    for id in cases:
        try:
            seen[id] = await case_handle(client, workflow, id).query(
                CaseWorkflow.migration_preview, asked
            )
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
            seen[id] = PreviewAnswer([f"{id} is not a case: no workflow has its ID"], [])
        except WorkflowQueryFailedError as failed:
            # The worker replays the case to answer, and its key provider refuses a destroyed key.
            if FORGOTTEN not in str(failed):
                raise
            seen[id] = PreviewAnswer([f"{id} was forgotten: its case file can't be read"], [])
    return seen


async def shown(
    case: WorkflowHandle[CaseWorkflow, CaseReport], field: str, by: str, roles: list[str]
) -> None:
    """Record that the person `by` was shown the record behind the reference `field`, as the API
    does after asking its system's resolver (brief, D16)."""
    await case.signal(CaseWorkflow.shown, CaseRequest(field, by, sorted(roles)))


async def send_event(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    event: str,
    payload: Mapping[str, Any],
    by: str,
    roles: list[str] | None = None,
) -> None:
    """Send the case the event `event`, carrying `payload`, as `by`: `system:portal` for a
    system, or a person's identifier with their `roles`. The caller vouches for who sent it: only
    the Ventoux API may send events (brief, D19). The case's own refusals are recorded in its
    history; a closed case refuses here, raising `EventRefused`: an event never opens a case
    again (brief, D41)."""
    sent = CaseEvent(event, dict(payload), by, sorted(roles or []))
    try:
        # Temporal: never signal-with-start, which would start a workflow for a case that ended.
        await case.signal(CaseWorkflow.event, sent)
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        # Temporal says the same of a workflow that ended and of one that never was: asked which.
        try:
            await case.describe()
        except RPCError as missing:
            if missing.status == RPCStatusCode.NOT_FOUND:
                raise EventRefused(f"{case.id} is not a case: no workflow has its ID") from None
            raise
        raise EventRefused(f"{case.id} is closed: it takes no more events") from None


async def view(
    case: WorkflowHandle[CaseWorkflow, CaseReport], roles: list[str], wording: Wording | None = None
) -> CaseView:
    """The case file as a person holding `roles` sees it, filtered in the worker (brief, D30);
    with `wording`, in that wording revision of the case's release, refused if it isn't one
    (brief, D51). A forgotten case has no case file left to read: refused, saying so
    (brief, D32)."""
    try:
        if wording is not None:
            worded = await case.query(CaseWorkflow.worded_view, ViewAsked(sorted(roles), wording))
            if worded.view is None:
                raise WordingRefused(worded.refused)
            return worded.view
        return await case.query(CaseWorkflow.view, sorted(roles))
    except WorkflowQueryFailedError as failed:
        # The worker replays the case to answer, and its key provider refuses a destroyed key.
        if FORGOTTEN in str(failed):
            raise CaseForgotten(f"{case.id} was forgotten: its case file can't be read") from None
        raise


# A report asked at the moment the case continues as new can reach the run that is ending, which
# no longer answers; asked again, it reaches the new run (layer 8c). So each question waits a
# little, and is asked again a few times.
ASK = timedelta(seconds=2)
ASKS = 10
UNANSWERED = (RPCStatusCode.CANCELLED, RPCStatusCode.DEADLINE_EXCEEDED)


class CaseUnanswered(Exception):
    """A case that didn't answer, however many times it was asked."""


async def report(case: WorkflowHandle[CaseWorkflow, CaseReport]) -> CaseReport:
    """How the case is going: what it waits for, and its history so far. A case that has closed
    gives the report it returned then: lines and placeholders, no sensitive part, so it reads
    without a key, even once the case is forgotten (brief, D32). Asked with a short timeout, and
    again a bounded number of times, so it never hangs while the case continues as new
    (brief, D27)."""
    for _ in range(ASKS):
        try:
            described = await case.describe(rpc_timeout=ASK)
            if described.status == WorkflowExecutionStatus.COMPLETED:
                return await case.result(rpc_timeout=ASK)
            return await case.query(CaseWorkflow.report, rpc_timeout=ASK)
        except RPCError as error:
            # Temporal: no answer in time, as when the query reached a run that was ending. The
            # SDK says so as `CANCELLED` ("Timeout expired") when the client's own timeout ends
            # the call, and as `DEADLINE_EXCEEDED` when the server's does.
            if error.status not in UNANSWERED:
                raise
    raise CaseUnanswered(
        f"{case.id} didn't answer in {ASKS} tries of {ASK.total_seconds():g}s: ask again later"
    )


async def approval_sheet(
    case: WorkflowHandle[CaseWorkflow, CaseReport],
    entry: str,
    roles: list[str],
    at: int | None = None,
    wording: Wording | None = None,
) -> ApprovalSheet:
    """The open approval `entry`'s sheet as a person holding `roles` reads it at `at`, seconds
    since the epoch: by default the API's own clock, now. A sheet is a query, read and never
    decided on, so the reader's time is safe here, outside the case (brief, D33). An approval
    that isn't open is refused, saying so."""
    if at is None:
        at = int(datetime.now(UTC).timestamp())  # whole seconds, rounded down
    try:
        answered = await case.query(
            CaseWorkflow.approval_sheet, SheetAsked(entry, sorted(roles), at, wording)
        )
    except WorkflowQueryFailedError as failed:
        # The worker replays the case to answer, and its key provider refuses a destroyed key.
        if FORGOTTEN in str(failed):
            raise CaseForgotten(f"{case.id} was forgotten: its case file can't be read") from None
        raise
    if answered.sheet is None:
        if answered.wording_refused:
            raise WordingRefused(answered.wording_refused)
        raise SheetRefused(answered.refused)
    return answered.sheet
