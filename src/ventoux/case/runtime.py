"""The case runtime: one event in; the case's new state and the commands to carry out out.

`decide` reads no clock, randomness or I/O, so the same events give the same decisions in memory
and, in layer 8c, inside a Temporal workflow on replay. A driver carries out the commands
(`case/memory.py` in tests) and feeds back what happened as the next event.
See docs/layers/08-case.md.
"""

import copy
from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import ValidationError

from ventoux.case.admission import (
    ProposalRefused,
    RetryRefused,
    StepStopped,
    holds,
    latest_run,
    proposal_refusal,
    requirements_met,
)
from ventoux.case.answers import AnswerRefused, judge_approval, judge_task
from ventoux.case.approvals import ask, follow, lapsed, needs_approval
from ventoux.case.definition import ActivityStep, CaseDefinition, TaskStep
from ventoux.case.sequence import requirements
from ventoux.case.state import (
    Answered,
    CaseState,
    Completed,
    Event,
    Failed,
    GivenApproval,
    OpenApproval,
    Opened,
    Proposed,
    Retried,
    Schedule,
    StepRun,
)
from ventoux.core.approval import inputs_digest
from ventoux.core.before_activity import InputRefused, checked_inputs, one_line
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import ActivityContract
from ventoux.core.expressions import ExpressionError, render
from ventoux.core.expressions.check import a_type
from ventoux.core.form import fits
from ventoux.core.person import identifier_problem
from ventoux.core.plan import APPROVE
from ventoux.core.provenance import provenance
from ventoux.core.roles import role_that_counts

# Where the case file's first values came from when a system opened the case (brief, D12).
OPENER = "system:opener"
# The outcome of an activity that did what it was asked.
DONE = "done"


class CaseRefused(Exception):
    """A case the engine won't open: what is wrong with its first values."""


def decide(
    case: CaseDefinition, catalog: Catalog, state: CaseState, event: Event
) -> tuple[CaseState, list[Schedule]]:
    """The case's state after `event`, and the activities to schedule. A refused event raises
    (`AnswerRefused`, `ProposalRefused`, `CaseRefused`) and changes nothing; a step the engine
    can't run fails, and the case needs attention (brief, D17)."""
    state = copy.deepcopy(state)  # the state passed in is never changed
    commands: list[Schedule] = []
    if isinstance(event, Opened):
        open_case(case, state, event)
    elif isinstance(event, Answered):
        if state.closed:
            raise AnswerRefused("the case is closed: nothing waits for an answer")
        answer(case, catalog, state, event)
    elif isinstance(event, Proposed):
        propose(case, catalog, state, event, commands)
    elif isinstance(event, Failed):
        failed(state, event)
    elif isinstance(event, Retried):
        retry(case, catalog, state, event)
    else:
        complete(case, catalog, state, event)
    admit(case, catalog, state, commands)
    # A case closes when nothing is left to do (brief, D10).
    if not state.closed and not pending(state):
        state.closed = True
        state.history.append("closed: nothing left to do")
    return state, commands


def open_case(case: CaseDefinition, state: CaseState, event: Opened) -> None:
    """The case file's first values, each of its field's type and saying where it came from:
    the person who opened the case, or the system that did (brief, D12)."""
    if event.by is not None and (wrong := identifier_problem(event.by)) is not None:
        raise CaseRefused(wrong)
    refuse_to_open(case, event.file)
    state.opened_by = event.by
    origin = OPENER if event.by is None else f"person:{event.by}"
    for name, value in event.file.items():
        state.values[name] = value
        state.sources[name] = marked(case, name, origin)
    state.history.append(f"opened by {event.by or OPENER}, with {listed(sorted(event.file))}")


def refuse_to_open(case: CaseDefinition, file: Mapping[str, object]) -> None:
    """Refuse first values that aren't the case's fields, of their types, given at the opening."""
    setters = set_by(case)
    problems: list[str] = []
    for name, value in file.items():
        if name not in case.fields:
            fields = listed(sorted(case.fields))
            problems.append(f"{name} is not a field of {case.case}: its fields are {fields}")
        # One source per field: a person's form sets it, so the opening never gives it.
        elif name in setters:
            problems.append(
                f"{name} is set by a person in {setters[name]}, never given at the opening"
            )
        elif not fits(value, declared := case.fields[name].declared):
            problems.append(f"{name} is {a_type(declared)}, and the opening gives {shown(value)}")
    if problems:
        raise CaseRefused("\n".join(problems))


def shown(value: object) -> str:
    """A value as its JSON reads: `1001`, `0.1`, `'ord-1'`."""
    return str(value) if isinstance(value, Decimal) else repr(value)


def set_by(case: CaseDefinition) -> dict[str, str]:
    """Each field a task's form sets, and the first task that sets it."""
    found: dict[str, str] = {}
    for name, step in case.steps.items():
        if isinstance(step, TaskStep):
            for outcome in step.outcomes.values():
                for field in outcome.sets:
                    found.setdefault(field, name)
    return found


def marked(case: CaseDefinition, name: str, origin: str) -> frozenset[str]:
    """Where a value of the field `name` came from: `origin`, and the field's declared mark. A
    mark adds distrust, never removes it (brief, D12)."""
    declared = case.fields[name].source if name in case.fields else None
    return frozenset({origin} | ({declared} if declared else set()))


def answer(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Answered) -> None:
    """Record a person's answer, once judged (brief, D23); or `AnswerRefused`."""
    # Who answered is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise AnswerRefused(wrong)
    found = open_entry(state, event.entry)
    if isinstance(found, StepRun):
        answer_task(case, catalog, state, found, event)
    else:
        answer_approval(case, catalog, state, found, event)


def open_entry(state: CaseState, entry: str) -> StepRun | OpenApproval:
    """The open task run or approval `entry` names; a step's name names its open one."""
    for run in state.runs:
        if run.status == "open" and entry in (run.entry, run.step):
            return run
    for approval in state.approvals.values():
        if entry in (approval.entry, approval.step):
            return approval
    if entry in state.withdrawn:
        raise AnswerRefused(f"{entry} was withdrawn: {state.withdrawn[entry]}")
    raise AnswerRefused(f"{entry} is not open: nothing there waits for an answer")


def propose(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    event: Proposed,
    commands: list[Schedule],
) -> None:
    """Start the step a person proposes, if they may and admission accepts it; or
    `ProposalRefused`. The engine decides, a person only asks."""
    # Who proposed is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise ProposalRefused(wrong)
    if state.closed:
        raise ProposalRefused("the case is closed: nothing starts")
    if event.step not in case.steps:
        raise ProposalRefused(f"{event.step} is not a step of {case.case}")
    step = case.steps[event.step]
    if not step.proposed_by:
        raise ProposalRefused(f"{event.step} starts by itself: nobody proposes it")
    role = role_that_counts(step.proposed_by, event.roles, catalog.roles)
    if role is None:
        counted = sorted(r for r in event.roles if r in catalog.roles)
        known = listed(counted) if counted else "no role"
        raise ProposalRefused(
            f"{event.step} is proposed by {' or '.join(step.proposed_by)}, and {event.by} has "
            f"{known}"
        )
    refusal = proposal_refusal(case, event.step, requirements(case)[event.step], state)
    if refusal is not None:
        raise ProposalRefused(refusal)
    if step.when is not None:
        try:
            decided = holds(step.when, state.values, f"{event.step}'s condition")
        except StepStopped as unreadable:
            raise ProposalRefused(str(unreadable)) from None  # fail closed: nothing starts
        if not decided:
            raise ProposalRefused(f"{event.step} doesn't run now: {render(step.when)} is false")
    state.history.append(f"{event.by} proposed {event.step} as {role}")
    state.proposers[event.step] = event.by  # never its approver (brief, D25)
    start(catalog, state, event.step, step, commands)


def answer_task(
    case: CaseDefinition, catalog: Catalog, state: CaseState, run: StepRun, event: Answered
) -> None:
    """The task run is done; its outcome, and the fields its form sets, land in the case file."""
    step = case.steps[run.step]
    assert isinstance(step, TaskStep)  # only a task's run is ever open
    role = judge_task(case, catalog, run.entry, run.step, step, event)
    run.status = "done"
    del state.waiting[run.entry]
    who = f"person:{event.by}"
    # The latest answer is the outcome (brief, D9), and a form's values replace earlier ones.
    state.values[f"{run.step}.outcome"] = event.outcome
    state.sources[f"{run.step}.outcome"] = frozenset({who})
    sets = step.outcomes[event.outcome].sets
    for name in sets:
        state.values[name] = (event.form or {})[name]
        state.sources[name] = marked(case, name, who)
    setting = f", setting {listed(list(sets))}" if sets else ""
    state.history.append(f"{event.by} answered {run.entry} {event.outcome} as {role}{setting}")
    state.history.append(f"{run.entry} done")
    reach(state, (*step.outcomes[event.outcome].reaches, *step.reaches))


def answer_approval(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    approval: OpenApproval,
    event: Answered,
) -> None:
    """An approval given, tied to the inputs it saw; or a rejection: the step won't run."""
    step = case.steps[approval.step]
    assert isinstance(step, ActivityStep)  # only an activity is asked for an approval
    role = judge_approval(catalog, state, approval.entry, approval.step, step, event)
    del state.approvals[approval.step]
    del state.waiting[approval.entry]
    state.history.append(f"{event.by} answered {approval.entry} {event.outcome} as {role}")
    if event.outcome == APPROVE:
        try:
            digest = inputs_digest(step.inputs, state.values)
        except ExpressionError as error:
            # Fail closed: an approval of inputs nobody can read approves nothing.
            fail(state, approval.step, f"the inputs of {approval.step} can't be read: {error}")
            return
        state.given[approval.step] = GivenApproval(approval.entry, event.by, digest)
        return
    # A rejection is an outcome: the step doesn't run (brief, D23).
    entry = next_entry(state, approval.step)
    state.proposers.pop(approval.step, None)  # the proposed run is over
    state.runs.append(StepRun(entry, approval.step, "rejected"))
    state.history.append(f"{entry} won't run: {event.by} rejected {approval.entry}")


def complete(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Completed) -> None:
    """A scheduled activity finished: its outcome lands in the case file, tagged with the contract
    that declares it. Its output is recorded here, not in the case file (layer 8d)."""
    run = next(run for run in state.runs if run.entry == event.entry)
    step = case.steps[run.step]
    assert isinstance(step, ActivityStep)  # only an activity is scheduled
    contract = catalog.get(step.activity)
    problem = outcome_problem(contract, event)
    if problem is not None:
        run.status, run.reason = "failed", problem
        state.history.append(f"{run.entry} failed: {problem}")
        return
    run.status = "done"
    state.values[f"{run.step}.outcome"] = event.outcome
    # Trusted: the contract, owned by the platform team, declares the outcomes (brief, D12).
    state.sources[f"{run.step}.outcome"] = frozenset({f"system:{contract.reference}"})
    if event.outcome != DONE:
        state.history.append(f"{run.entry} gave {event.outcome}")
        return  # a step's milestones are reached only when it is done with `done`
    giving = f", giving {listed(sorted(event.output))}" if event.output else ""
    state.history.append(f"{run.entry} done{giving}")
    reach(state, step.reaches)


def outcome_problem(contract: ActivityContract, event: Completed) -> str | None:
    """Why what the activity gave can't be taken, or None: an outcome its contract doesn't
    declare, or an output its contract doesn't describe. Fail closed: neither is read as done."""
    if event.outcome != DONE:
        if event.outcome in contract.outcomes:
            return None
        declared = ", ".join(contract.outcomes) or "none"
        return (
            f"{contract.reference} gave the outcome {event.outcome}, which its contract doesn't "
            f"declare: its outcomes are {declared}"
        )
    try:
        # Pydantic: `model_validate` checks a dict against the model's fields, or raises.
        contract.output.model_validate(event.output)
    except ValidationError as error:
        return (
            f"{contract.reference} gave an output its contract doesn't declare: {one_line(error)}"
        )
    return None


def failed(state: CaseState, event: Failed) -> None:
    """A scheduled activity failed after its retries: its run fails, and waits for a person."""
    run = next(run for run in state.runs if run.entry == event.entry)
    run.status, run.reason = "failed", event.reason
    state.history.append(f"{run.entry} failed: {event.reason}")


def fail(state: CaseState, name: str, reason: str) -> None:
    """The step's coming run fails before it is scheduled, with the reason (brief, D17)."""
    run = coming_run(state, name, "failed")
    run.reason = reason
    state.history.append(f"{run.entry} failed: {reason}")


def retry(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Retried) -> None:
    """An operator retries a failed run: it runs again as the same run, with the same key, once
    the step is checked again (brief, D26). Or `RetryRefused`."""
    # Who retried is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise RetryRefused(wrong)
    if state.closed:
        raise RetryRefused("the case is closed: nothing starts")
    run = next((run for run in state.runs if run.entry == event.entry), None)
    if run is None or run.status != "failed":
        raise RetryRefused(f"{event.entry} has not failed: nothing to retry")
    counted = sorted(role for role in event.roles if role in catalog.operators)
    if not counted:
        registered = sorted(role for role in event.roles if role in catalog.roles)
        known = listed(registered) if registered else ""
        raise RetryRefused(
            f"{event.entry} is retried by an operating role "
            f"({', '.join(catalog.operators) or 'none registered'}), and {event.by} has "
            f"{known or 'no role'}"
        )
    step = case.steps[run.step]
    # The step is checked again: what made it fail may still hold. Fail closed: nothing starts.
    for requirement in requirements(case)[run.step]:
        if not requirements_met((requirement,), state):
            raise RetryRefused(
                f"{event.entry} can't be retried: {run.step} requires {requirement}, which "
                "hasn't completed"
            )
    if step.when is not None:
        try:
            decided = holds(step.when, state.values, f"{run.step}'s condition")
        except StepStopped as unreadable:
            raise RetryRefused(f"{event.entry} can't be retried: {unreadable}") from None
        if not decided:
            raise RetryRefused(f"{event.entry} can't be retried: {render(step.when)} is false now")
    run.status, run.reason = "retrying", ""
    state.history.append(f"{event.by} retried {event.entry} as {counted[0]}")


def reach(state: CaseState, milestones: tuple[str, ...]) -> None:
    """Record each milestone reached: a fact, never undone."""
    for milestone in milestones:
        if milestone not in state.milestones:
            state.milestones.append(milestone)
            state.history.append(f"reached {milestone}")


def admit(
    case: CaseDefinition, catalog: Catalog, state: CaseState, commands: list[Schedule]
) -> None:
    """Start every step that may start now, until no more can: no position, only admission."""
    required = requirements(case)
    started = True
    while started:
        started = False
        follow(case, state)  # an open approval follows the case file (brief, D25)
        for name, step in case.steps.items():
            if not free_to_start(state, name, step) or not requirements_met(required[name], state):
                continue
            try:
                # Read only once `requires` are met: a field nobody has set fails the step.
                if step.when is not None and not holds(
                    step.when, state.values, f"{name}'s condition"
                ):
                    continue
                start(catalog, state, name, step, commands)
            except (StepStopped, InputRefused, NotInCatalog) as error:
                # Nothing is skipped automatically: the step fails, and waits for a person; the
                # other steps go on (brief, D17).
                fail(state, name, str(error))
            started = True


def free_to_start(state: CaseState, name: str, step: TaskStep | ActivityStep) -> bool:
    """Whether the step may start by itself: it isn't waiting for its approval, and it starts by
    itself and hasn't started before; or its approval was just given."""
    if name in state.approvals:
        return False  # waiting for its approval
    if name in state.given:
        return True  # approved, so it starts now
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying":
        return True  # an operator retried it
    # A step starts by itself at most once; again, or at all if not automatic, only if proposed.
    return step.automatic and latest_run(state, name) is None


def start(
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: TaskStep | ActivityStep,
    commands: list[Schedule],
) -> None:
    """Open a task's run; ask for an activity's approval, or schedule the activity."""
    if isinstance(step, TaskStep):
        entry = coming_run(state, name, "open").entry
        state.proposers.pop(name, None)  # a task has no approval: the proposed run has started
        state.waiting[entry] = f"{name} by {' or '.join(step.roles)}"
        state.history.append(
            f"started {entry}: waiting for {' or '.join(step.outcomes)} by "
            f"{' or '.join(step.roles)}"
        )
        return
    given = state.given.pop(name, None)  # spent, whatever happens next
    latest = latest_run(state, name)
    if given is None and latest is not None and latest.status == "retrying":
        given = latest.approved  # a retry keeps the approval spent on its run (brief, D26)
    if given is None and needs_approval(state, name, step):
        ask(state, name, step)
        return
    if given is not None:
        lapsed(state, name, step, given)
    schedule(catalog, state, name, step, given, commands)


def schedule(
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: ActivityStep,
    approved: GivenApproval | None,
    commands: list[Schedule],
) -> None:
    """Check the activity's inputs against the real sources (layer 5), then schedule it, with a
    key naming the case and the step run (brief, D17)."""
    contract = catalog.get(step.activity)  # fail closed: an activity the catalog lacks stops it
    # Checked again at runtime, on nothing case validation did (learning question 34).
    if contract.risk == "high" and step.approval is None:
        raise StepStopped(f"{contract.reference} is high risk, and {name} has no approval")
    latest = latest_run(state, name)
    entry = latest.entry if latest is not None and latest.status == "retrying" else None
    entry = entry or next_entry(state, name)
    key = f"{state.case}/{entry}"
    inputs = checked_inputs(contract, step.inputs, state.values, state.sources, key)
    coming_run(state, name, "running").approved = approved
    state.proposers.pop(name, None)  # the proposed run has started
    origins = "; ".join(
        f"{field} from {', '.join(sorted(provenance(expression, state.sources))) or 'the case'}"
        for field, expression in step.inputs.items()
    )
    keyed = f", key {key}" if contract.idempotency_key is not None else ""
    state.history.append(f"scheduled {entry}: {contract.reference} ({origins}){keyed}")
    commands.append(Schedule(entry, contract.reference, inputs))


def coming_run(
    state: CaseState, name: str, status: Literal["open", "running", "failed"]
) -> StepRun:
    """The step's coming run, now `status`: the run an operator retried, which keeps its entry and
    so its key (brief, D26), or else a new one."""
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying":
        latest.status = status
        return latest
    run = StepRun(next_entry(state, name), name, status)
    state.runs.append(run)
    return run


def next_entry(state: CaseState, name: str) -> str:
    """The step's next run: `review#1`, then `review#2`."""
    return f"{name}#{sum(1 for run in state.runs if run.step == name) + 1}"


def pending(state: CaseState) -> bool:
    """Whether anything is left to do: a task open, an activity running, a step failed, an
    approval asked or given and not yet spent (brief, D10, D17)."""
    unfinished = any(run.status in ("open", "running", "failed", "retrying") for run in state.runs)
    return unfinished or bool(state.approvals) or bool(state.given)


def listed(names: list[str]) -> str:
    """`nothing`, `amount`, `amount and order_id`, `a, b and c`."""
    if len(names) <= 1:
        return names[0] if names else "nothing"
    return f"{', '.join(names[:-1])} and {names[-1]}"
