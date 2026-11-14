"""The runtime's front door: one event in, the case's new state and the commands to carry
out; and what a proposal or a migration would do, decided the same way without keeping it.
Moved from `case/runtime.py` (docs/layers/runtime-split.md); see docs/layers/08-case.md.
"""

import copy
from dataclasses import dataclass

from ventoux.case.admission import (
    ProposalRefused,
)
from ventoux.case.answers import (
    AnswerRefused,
)
from ventoux.case.assigning import assign, unassign
from ventoux.case.claims import (
    claim,
    give_back,
    let_go_of_ended,
)
from ventoux.case.closing import (
    begin_closing,
    close_when_reached,
    refuse_to_close,
    settle,
)
from ventoux.case.definition import (
    CaseDefinition,
)
from ventoux.case.exporting import export_failed, export_retried
from ventoux.case.forgetting import forget
from ventoux.case.freshness import refuse_unless_whole
from ventoux.case.migrations import apply, problems_of, released
from ventoux.case.recording import recorded
from ventoux.case.requests import propose_change
from ventoux.case.rules import fire_rules, nothing_decided
from ventoux.case.runtime.admitting import admit, left_unstarted
from ventoux.case.runtime.answering import answer, check_failed, entry_to_hold
from ventoux.case.runtime.completing import (
    child_not_ended,
    child_rang,
    complete,
    failed,
    plan_cancelled,
    workflow_cancelled,
)
from ventoux.case.runtime.opening import open_case
from ventoux.case.runtime.proposing import propose
from ventoux.case.runtime.receiving import receive, record_shown
from ventoux.case.runtime.retrying import retry
from ventoux.case.state import (
    Answered,
    Assigned,
    CaseState,
    ChangeProposed,
    ChildNotEnded,
    ChildRang,
    Claimed,
    CloseAsked,
    ClosedByParent,
    Command,
    Event,
    ExportFailed,
    ExportRetried,
    Failed,
    ForgetApproved,
    GivenBack,
    Migration,
    Opened,
    PlanCancelled,
    Proposed,
    Retried,
    Sent,
    Shown,
    TimerDue,
    Unassigned,
    UseRelease,
    WorkflowCancelled,
)
from ventoux.case.stopping import stop_children
from ventoux.case.timers import cancel_timers, end_with_their_runs, fire_timer
from ventoux.core.catalog import Catalog


def decide(  # noqa: C901
    case: CaseDefinition, catalog: Catalog, state: CaseState, event: Event
) -> tuple[CaseState, list[Command]]:
    """The case's state after `event`, and the activities to schedule. A refused event raises
    (`AnswerRefused`, `ProposalRefused`, `CaseRefused`, `TimeRefused`, `TimerRefused`) and changes
    nothing; a step the engine
    can't run fails, and the case needs attention (brief, D17)."""
    refuse_unless_whole(event.at)  # time is only ever event data, so it is checked first
    state = copy.deepcopy(state)  # the state passed in is never changed
    state.started_by_rules.clear()  # a guard for this decision only (brief, D39)
    since = len(state.history)  # the lines this act adds, which its audit record keeps
    commands: list[Command] = []
    was_open = state.phase == "open"
    if isinstance(event, Opened):
        open_case(case, catalog, state, event)
    elif isinstance(event, Answered):
        if state.phase != "open":
            raise AnswerRefused(f"the case is {state.phase}: nothing waits for an answer")
        if (moved := answer(case, catalog, state, event, commands)) is not None:
            # A migration applied: the rest of this decision, and every one after, is the
            # target's, and the driver is told to use it from now on (brief, D53).
            case = moved.case
            commands.append(UseRelease(moved.migration))
    elif isinstance(event, Proposed):
        propose(case, catalog, state, event, commands)
    elif isinstance(event, Failed):
        if not check_failed(case, catalog, state, event):
            failed(state, event)
    elif isinstance(event, PlanCancelled):
        plan_cancelled(state, event)
    elif isinstance(event, ChildRang):
        child_rang(case, state, event, commands)
    elif isinstance(event, ChildNotEnded):
        child_not_ended(case, state, event)
    elif isinstance(event, ClosedByParent):
        # Closed as a person's close is, saying its parent asked (brief, D74).
        begin_closing(
            state,
            f"closed by its parent: {event.reason}",
            f"by its parent: {event.reason}",
            None,
        )
    elif isinstance(event, WorkflowCancelled):
        workflow_cancelled(state, event)
    elif isinstance(event, Retried):
        retry(case, catalog, state, event, commands)
    elif isinstance(event, Claimed):
        claim(case, catalog, state, entry_to_hold(case, state, event), event)
    elif isinstance(event, GivenBack):
        give_back(state, entry_to_hold(case, state, event), event)
    elif isinstance(event, Assigned):
        assign(case, catalog, state, entry_to_hold(case, state, event), event)
    elif isinstance(event, Unassigned):
        unassign(case, catalog, state, entry_to_hold(case, state, event), event)
    elif isinstance(event, Shown):
        record_shown(case, catalog, state, event)
    elif isinstance(event, Sent):
        receive(case, catalog, state, event)
    elif isinstance(event, ForgetApproved):
        forget(case, catalog, state, event)
    elif isinstance(event, ChangeProposed):
        propose_change(case, catalog, state, event)
    elif isinstance(event, TimerDue):
        fire_timer(state, event)
    elif isinstance(event, ExportFailed):
        export_failed(state, event)
    elif isinstance(event, ExportRetried):
        export_retried(catalog, state, event)
    elif isinstance(event, CloseAsked):
        role = refuse_to_close(case, catalog, state, event)
        state.history.append(f"{event.by} closed the case as {event.reason}, as {role}")
        why = f"closed as {event.reason} by {event.by}"
        state.closed_as = event.reason  # a child reports it as its outcome (brief, D74)
        state.closed_by = event.by
        begin_closing(state, why, f"{event.reason}, by {event.by}", f"close_reasons.{event.reason}")
    else:
        complete(case, catalog, state, event)
    decide_again(case, catalog, state, commands, event.at, was_open)
    let_go_of_ended(state)
    recorded(case, state, event, since)  # the act, as data, beside its lines (brief, D76)
    return state, commands


def decide_again(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    commands: list[Command],
    at: int,
    was_open: bool,
) -> None:
    """What the case decides once an event has landed, at `at`: whether it closes, what may start
    now, what the rules say, which timers end, and whether it is done."""
    close_when_reached(case, state)
    if state.phase == "open":
        admit(case, catalog, state, commands, at)  # nothing new starts once closing
        close_when_reached(case, state)  # a rule may have reached the last of closes_when
    if was_open and state.phase == "closing":
        stop_children(case, catalog, state, commands)
    # Moments left because the case is no longer open: each rule on them says it wasn't applied
    # (brief, D38).
    fire_rules(case, catalog, state, commands, at)
    left_unstarted(case, state)  # none is taken up once the case no longer decides (brief, D38)
    state.started_by_rules.clear()
    # A timer ends with its purpose: its run ended, or nothing new is decided while the close is
    # held, which never goes back to deciding, so it could never act (brief, D34) (brief, D44).
    end_with_their_runs(state)
    if state.timers and (held := nothing_decided(case, state)) is not None:
        cancel_timers(state, held)
    settle(case, catalog, state)


@dataclass(frozen=True)
class MigrationPreview:
    """What a migration would do to a case now: every problem refusing it, or the lines its
    history would gain. Never both (brief, D53)."""

    refused: tuple[str, ...] = ()
    lines: tuple[str, ...] = ()


def preview_migration(
    case: CaseDefinition, catalog: Catalog, state: CaseState, migration: Migration, at: int
) -> MigrationPreview:
    """What applying `migration` at `at` would do to the case, decided as the apply decides it,
    on a copy of its state: the approver reads it before approving, and the case is unchanged.
    The apply checks again, depending on nothing this said (brief, D34) (brief, D53)."""
    state = copy.deepcopy(state)  # the state passed in is never changed
    if state.phase != "open":
        return MigrationPreview(refused=(f"the case is {state.phase}: nothing changes it",))
    if problems := problems_of(case, catalog, state, migration):
        return MigrationPreview(refused=tuple(problems))
    seen = len(state.history)
    state.history.append(
        f"from {released(case, state)} to {migration.label}, engine {migration.engine}"
    )
    target = apply(case, catalog, state, migration, at)
    decide_again(target, catalog, state, [], at, was_open=True)  # its commands are never carried
    return MigrationPreview(lines=tuple(state.history[seen:]))


def proposal_refused(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    step: str,
    by: str,
    roles: frozenset[str],
    at: int,
) -> str | None:
    """Why `by`, holding `roles`, couldn't propose `step` at `at`, or None if admission would
    accept it. Decided as their proposal would be, by `decide` on a copy of the state, so it
    checks everything a person's proposal meets, never a second set of checks; the case is
    unchanged (brief, D61)."""
    try:
        decide(case, catalog, state, Proposed(step, by, roles, at=at))  # `decide` copies the state
    except ProposalRefused as refused:
        return str(refused)
    return None
