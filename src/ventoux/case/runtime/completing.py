"""What a run gives back lands: completed, failed, cancelled, or a child case's end.
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from ventoux.case.audit import Decision
from ventoux.case.called import called
from ventoux.case.definition import (
    CallStep,
    CaseDefinition,
    CaseStep,
    PlanStep,
)
from ventoux.case.recording import decided_failure
from ventoux.case.runtime.answering import check_answered, checked_answer
from ventoux.case.runtime.outcomes import outcome_problem, plan_outcome_problem, write_outputs
from ventoux.case.runtime.runs import (
    DONE,
    flag,
    flag_if_stopping,
    listed,
    reach_unless_steered,
    stopped_because,
)
from ventoux.case.state import (
    CaseEnded,
    CaseState,
    ChildNotEnded,
    ChildRang,
    Command,
    Completed,
    Failed,
    Obtained,
    PlanCancelled,
    ReadChild,
    StepRun,
    WorkflowCancelled,
)
from ventoux.core.catalog import Catalog


def complete(
    case: CaseDefinition, catalog: Catalog, state: CaseState, event: Completed | CaseEnded
) -> None:
    """A scheduled activity, a workflow or a plan finished: its outcome lands in the case file,
    tagged with the contract (or plan) that declares it, and so does an activity's or a workflow's
    output, each field tagged with its contract's source (brief, D29). A run untrusted data
    steered adds what steered it to each, and reaches nothing (brief, D43)."""
    run = next((run for run in state.runs if run.entry == event.entry), None)
    if isinstance(event, CaseEnded):
        if run is None or run.status != "running":
            # Its doorbell and a new run's question can both read the same end: the second
            # changes nothing, and its report never lands twice (brief, D75).
            state.history.append(f"{event.entry} ended again: nothing read")
            return
        step = case.steps[run.step]
        assert isinstance(step, CaseStep)  # only a case step opens a child
        child_ended(state, run, step, event)
        return
    if (checking := checked_answer(state, event.entry)) is not None:
        check_answered(case, catalog, state, checking, event)
        return
    run = next(run for run in state.runs if run.entry == event.entry)
    step = case.steps[run.step]
    assert isinstance(step, CallStep | PlanStep)  # only an activity, a workflow or a plan completes
    if isinstance(step, PlanStep):
        declares, problem = step.plan, plan_outcome_problem(step, event)
    else:
        contract = called(catalog, step)
        declares, problem = contract.reference, outcome_problem(contract, event)
    if problem is not None:
        failed(state, Failed(event.entry, problem, at=event.at))
        return
    run.status = "done"
    state.deciding.append(
        Decision("completed", step=run.step, entry=run.entry, rule=f"steps.{run.step}")
    )
    if run.item is not None:
        # A repeated run's outcome and outputs aren't written under its step's name, where each
        # run would overwrite the last; nothing reads them (brief, D73).
        ended = "" if event.outcome == DONE else f" with {event.outcome}"
        state.history.append(f"{run.entry} done{ended}")
        flag_if_stopping(state, run)
        return
    state.values[f"{run.step}.outcome"] = event.outcome
    # Trusted: the contract, owned by the platform team, or the reviewed plan, declares the
    # outcomes (brief, D12). But what only untrusted data made exist is untrusted: a steered
    # run's outcome and outputs carry what steered it (brief, D43).
    steered = frozenset().union(*(steering.sources for steering in run.steered))
    state.sources[f"{run.step}.outcome"] = frozenset({f"system:{declares}"}) | steered
    state.obtained[f"{run.step}.outcome"] = Obtained(event.at, run.entry)  # by this run
    if event.outcome != DONE:
        state.history.append(f"{run.entry} gave {event.outcome}")
        flag_if_stopping(state, run)
        return  # a step's milestones are reached only when it is done with `done`
    given = (
        {}
        if isinstance(step, PlanStep)
        else write_outputs(state, run.step, contract, event, steered)
    )
    giving = "; ".join(f"{name} from {given[name]}" for name in sorted(given))
    state.history.append(f"{run.entry} done{f', giving {giving}' if giving else ''}")
    reach_unless_steered(state, run, step.reaches)
    flag_if_stopping(state, run)


def failed(state: CaseState, event: Failed) -> None:
    """A scheduled activity failed after its retries: its run fails, and waits for a person. While
    the case is closing, nobody will retry it: it is cancelled, and the case is flagged."""
    run = next(run for run in state.runs if run.entry == event.entry)
    run.status, run.reason = "failed", event.reason
    # A run that fails after its stop was asked needs attention like any other: nobody knows what
    # it did, and a later run would get a new key (brief, D17) (brief, D40).
    after = f" after its stop was requested by {run.stop_requested}" if run.stop_requested else ""
    state.history.append(f"{run.entry} failed{after}: {event.reason}")
    decided_failure(state, run.step, run.entry, event.reason)
    if state.phase == "closing":
        run.status = "cancelled"
        flag(state, f"{run.entry} failed after the close was requested: {event.reason}")


def plan_cancelled(state: CaseState, event: PlanCancelled) -> None:
    """A plan stopped by the close or by a rule has ended: its step run is cancelled, and the case
    can close. Each activity in it that finished or failed after the stop flags the case, as a
    step's run would (brief, D10): a payment made after a close never disappears into
    "cancelled" (brief, D28) (brief, D40)."""
    run = next(run for run in state.runs if run.entry == event.entry)
    if run.status != "running":
        return  # it ended before the stop reached it: what it gave is already recorded
    run.status = "cancelled"
    state.history.append(f"{run.entry} cancelled: {stopped_because(run)}")
    for ended in event.after_stop:
        flag(state, f"{run.entry}: {ended}")


def workflow_cancelled(state: CaseState, event: WorkflowCancelled) -> None:
    """A cancellable workflow step, asked to stop, ended cancelled: its run is cancelled, and the
    case is flagged, since what it did before the request stands (brief, D40)."""
    run = next(run for run in state.runs if run.entry == event.entry)
    if run.status != "running":
        return  # it ended before the cancellation reached it: what it gave is already recorded
    if not run.stop_requested and state.phase != "closing":
        # Fail closed: the case asked nothing of it, so nothing explains it; never read as a close.
        why = "it ended cancelled, though the case asked nothing of it: retry it, or close the case"
        failed(state, Failed(run.entry, why, at=event.at))
        return
    run.status = "cancelled"
    state.history.append(f"{run.entry} cancelled: {stopped_because(run)}")
    if run.stop_requested:
        flag(state, f"{run.entry} cancelled after its stop was requested by {run.stop_requested}")
    else:
        flag(state, f"{run.entry} cancelled after the close was requested")


def child_rang(
    case: CaseDefinition, state: CaseState, event: ChildRang, commands: list[Command]
) -> None:
    """A doorbell: read the child's own end, if the entry is an open child of this case; else it
    finds nothing to read, recorded, and changes nothing, whoever rang (brief, D75)."""
    run = next((run for run in state.runs if run.entry == event.entry), None)
    open_child = (
        run is not None
        and run.status == "running"
        and isinstance(case.steps.get(run.step), CaseStep)
    )
    if not open_child:
        state.history.append(f"child_ended for {event.entry}, which is no open child: nothing read")
        return
    commands.append(ReadChild(event.entry, f"{state.case.split('/')[0]}/{event.entry}"))


def child_not_ended(case: CaseDefinition, state: CaseState, event: ChildNotEnded) -> None:
    """What reading a child found when it had no report: still open, so nothing changes; or its
    workflow ended without reporting, so its step fails and waits for a person, never waited for
    in silence (brief, D17) (brief, D75)."""
    run = next((run for run in state.runs if run.entry == event.entry), None)
    if run is None or run.status != "running":
        return  # it ended meanwhile: what it gave is already recorded
    step = case.steps[run.step]
    assert isinstance(step, CaseStep)  # only a case step's run is read as a child
    if event.how == "open":
        state.history.append(
            f"child_ended for {event.entry}, whose case is still open: nothing read"
        )
        return
    why = f"{step.case} ended without reporting: {event.how}: look at the child, then "
    failed(state, Failed(event.entry, why + "retry or close", at=event.at))


def child_ended(state: CaseState, run: StepRun, step: CaseStep, event: CaseEnded) -> None:
    """A case step's child closed: its outcome, and each field it reports, land as the step's
    outputs, each with its sources in the child and `case:<child>`, the route it came by. A child
    never writes into its parent's case file (brief, D74)."""
    if run.stop_requested or state.phase == "closing":
        # Closed by its parent: it has ended, and its report changes nothing here (brief, D74).
        run.status = "cancelled"
        state.history.append(f"{run.entry} cancelled: {stopped_because(run)}")
        return
    route = f"case:{step.case.split('@')[0]}"
    run.status = "done"
    completed = Decision("completed", step=run.step, entry=run.entry, rule=f"steps.{run.step}")
    state.deciding.append(completed)
    state.values[f"{run.step}.outcome"] = event.outcome
    # Trusted: the child's reviewed release declares its close reasons, as a plan its outcomes.
    # But which reason was chosen is a person's act, as a task's outcome is: who closed it decided
    # it, and approves nothing it feeds (brief, D11).
    chose = frozenset() if event.closed_by is None else frozenset({f"person:{event.closed_by}"})
    state.sources[f"{run.step}.outcome"] = frozenset({route}) | chose
    state.obtained[f"{run.step}.outcome"] = Obtained(event.at, run.entry)
    for field, given in event.report.items():
        state.values[f"{run.step}.{field}"] = given.value
        state.sources[f"{run.step}.{field}"] = given.sources | {route}
        state.obtained[f"{run.step}.{field}"] = Obtained(event.at, run.entry)
    child = step.case.split("@")[0]
    reaching = f", reaching {listed(list(event.reached))}" if event.reached else ""
    reported = listed(sorted(event.report)) or "nothing"
    state.history.append(
        f"{run.entry} done: {child} closed, {event.closed}{reaching}; reporting {reported}"
    )
    if event.outcome == DONE:
        reach_unless_steered(state, run, step.reaches)
    flag_if_stopping(state, run)
