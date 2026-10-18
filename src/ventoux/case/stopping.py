"""Stopping a step: what a close does to the whole case, done to one step (layer 11c).

A rule's `stop` ends the run going on now: an open task is cancelled, an approval withdrawn, and
a running activity finishes, since a side effect can't be cut off halfway (brief, D10). A failed
run is never stopped (brief, D17) (brief, D26). See docs/layers/11-rules.md (11c).
"""

from ventoux.case.admission import latest_run, requirements_met
from ventoux.case.closing import close_held
from ventoux.case.definition import CaseDefinition, PlanStep, TaskStep, WorkflowStep
from ventoux.case.freshness import stale_facts
from ventoux.case.sequence import requirements
from ventoux.case.state import CLOSING, CancelWorkflow, CaseState, Command, StepRun, StopPlan
from ventoux.core.catalog import Catalog


def stop_step(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    by: str,
    said: str,
    commands: list[Command],
    at: int,
) -> None:
    """Stop the run of `name` going on now, for the rule's firing `by`; `said` begins the line
    the history writes when there is nothing to stop; `at` is the time of the event being
    decided, against which facts' ages are measured. The step may start again later
    (brief, D40)."""
    latest = latest_run(state, name)
    if latest is not None and latest.status in ("failed", "retrying"):
        # Nothing is skipped automatically: an operator retries it, or closes the case
        # (brief, D17) (brief, D26). A run being retried is the failed run being rescued.
        where = "needs attention" if latest.status == "failed" else "is retried by an operator"
        state.history.append(
            f"{said}: {name} not stopped: {latest.entry} {where}, and a failed run is never stopped"
        )
        return
    if latest is not None and latest.status == "running":
        stop_running(case, catalog, state, latest, by, said, commands)
        return
    if latest is not None and latest.status == "open":
        # A task waiting for a person: cancelled, as a close cancels it (brief, D10). An answer
        # to it is refused as closed.
        latest.status = "cancelled"
        del state.waiting[latest.entry]
        state.history.append(f"cancelled {latest.entry}: stopped by {by}")
        return
    if not stop_coming_run(case, state, name, by, at):
        state.history.append(f"{said}: {name} not stopped: no run of {name} is going on")


def stop_coming_run(case: CaseDefinition, state: CaseState, name: str, by: str, at: int) -> bool:
    """Stop the run about to start, if there is one: its approval asked is withdrawn, the
    approval given lapses, or a start waiting for a fact, a person's or the step's own, is
    dropped; and the run is recorded `cancelled`, so the step doesn't start by itself again
    (brief, D25) (brief, D40). Whether there was one. A refresh on its way for it still lands."""
    why = f"stopped by {by}"
    waits = waits_for_its_fact(case, state, name, at)  # read before anything below changes
    approval = state.approvals.pop(name, None)
    if approval is not None:
        del state.waiting[approval.entry]
        state.withdrawn[approval.entry] = why  # an answer to it is refused, saying why
        state.history.append(f"cancelled {approval.entry}: {why}")
    given = state.given.pop(name, None)  # approved, and waiting for its fact: it lapses
    proposed = name in state.waiting_to_start
    if proposed:
        state.waiting_to_start.remove(name)
    if approval is None and given is None and not proposed and not waits:
        return False
    entry = f"{name}#{sum(1 for run in state.runs if run.step == name) + 1}"
    state.runs.append(StepRun(entry, name, "cancelled", started=False))
    # Whoever proposed it, a person or a rule, proposed a run that is over (brief, D25).
    state.proposers.pop(name, None)
    state.proposed_by_rules.pop(name, None)
    state.history.append(f"{entry} cancelled: {why}")
    return True


def stop_running(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    run: StepRun,
    by: str,
    said: str,
    commands: list[Command],
) -> None:
    """A rule's stop of a running run: marked, so it is asked once and never twice, then asked to
    stop as its kind declares. It hasn't ended until it has its final status (brief, D40)."""
    if run.stop_requested:
        state.history.append(f"{said}: {run.step} not stopped: its stop is already requested")
        return
    run.stop_requested = by
    state.history.append(f"{run.entry}: stop requested by {by}")
    ask_to_stop(case, catalog, run, f"stopped by {by}", commands)


def stop_children(
    case: CaseDefinition, catalog: Catalog, state: CaseState, commands: list[Command]
) -> None:
    """The case begins closing: ask each running run to stop, as its kind declares, unless a rule
    asked already (brief, D10) (brief, D28) (brief, D40)."""
    for run in state.runs:
        if run.status == "running" and not run.stop_requested:
            ask_to_stop(case, catalog, run, CLOSING, commands)


def ask_to_stop(
    case: CaseDefinition, catalog: Catalog, run: StepRun, reason: str, commands: list[Command]
) -> None:
    """The one place that stops a running child, for a close and for a rule's stop, each by the
    mechanism its kind declares: a plan by its stop signal, whose open waits are a decision one
    level down (brief, D28); a workflow whose contract declares it cancellable, by Temporal's
    cancellation (brief, D40). An activity, or a workflow that isn't cancellable, is asked
    nothing: it finishes, since a side effect can't be cut off halfway (brief, D10). A later kind
    of child adds its mechanism here."""
    step = case.steps[run.step]
    if isinstance(step, PlanStep):
        commands.append(StopPlan(run.entry, reason))
    elif isinstance(step, WorkflowStep) and catalog.workflow(step.workflow).cancellable:
        commands.append(CancelWorkflow(run.entry, reason))


def waits_for_its_fact(case: CaseDefinition, state: CaseState, name: str, at: int) -> bool:
    """Whether the step is about to start by itself once a fact it needs fresh is fetched again,
    asked as admission asks it (brief, D33): it may start by itself, having never run; its
    requirements are met and the close isn't held; and a fact it reads is too old for it now,
    with a refresh of it running. A refresh another step asked for doesn't make it wait."""
    step = case.steps[name]
    if isinstance(step, TaskStep) or not step.automatic or latest_run(state, name) is not None:
        return False
    if not requirements_met(requirements(case)[name], state) or close_held(case, state):
        return False
    for stale in stale_facts(step.max_age, state, at):
        prior = state.refreshing.get(stale.field)
        if prior is not None and prior != stale.run:
            refresh = next(run for run in state.runs if run.entry == prior)
            if refresh.status == "running":
                return True
    return False
