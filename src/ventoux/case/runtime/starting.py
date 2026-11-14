"""One run starts: a task or a wait opens, an activity is checked and scheduled, a plan or a
child case begins, each with what steered it.
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from collections.abc import Mapping

from ventoux.case.admission import (
    StepStopped,
    latest_counted,
    latest_run,
)
from ventoux.case.approvals import (
    ask,
    asked_anyway,
    lapsed,
    needs_approval,
)
from ventoux.case.assignment_rules import follow_rule
from ventoux.case.called import called
from ventoux.case.claims import (
    keep_holder,
)
from ventoux.case.definition import (
    CallStep,
    CaseDefinition,
    CaseStep,
    PlanStep,
    Step,
    TaskStep,
    WaitStep,
    WorkflowStep,
    sent_by,
)
from ventoux.case.recording import decided_start, starting_rule
from ventoux.case.runtime.runs import (
    coming_run,
    may_not_approve,
    next_entry,
    origins,
    proposal_spent,
)
from ventoux.case.sequence import requirements
from ventoux.case.state import (
    CaseState,
    Command,
    GivenApproval,
    OpenCase,
    Schedule,
    StartPlan,
    StartWorkflow,
)
from ventoux.case.writers import read_sources, untrusted_of
from ventoux.core.before_activity import (
    InputRefused,
    Steering,
    checked_inputs,
    given_as_reference,
)
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import (
    Expression,
    ExpressionError,
    evaluate,
)
from ventoux.core.provenance import NoSources, Sourced, provenance
from ventoux.core.sensitive_inputs import kept_sensitive, reads_sensitive


def start(  # noqa: C901
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: TaskStep | CallStep | PlanStep | CaseStep | WaitStep,
    commands: list[Command],
) -> None:
    """Open a task's run, or a wait's; start a plan; ask for an activity's or a workflow's
    approval, or start it."""
    rule = starting_rule(state, name, step)  # before the proposal is spent, below
    if isinstance(step, PlanStep):
        start_plan(case, catalog, state, name, step, commands, rule)
        return
    if isinstance(step, CaseStep):
        open_child(state, name, step, commands, rule)
        return
    if isinstance(step, WaitStep):
        # Open until the event's next arrival: pending work, listed with what it waits for
        # (brief, D10) (brief, D24) (brief, D41).
        run = coming_run(state, name, "open")
        run.steered = steering(case, catalog, state, name, step)  # read before it is spent
        entry = run.entry
        proposal_spent(state, name)  # a wait has no approval: the proposed run has started
        state.waiting[entry] = f"{step.event} {sent_by(case.events[step.event])}"
        state.history.append(f"started {entry}: waiting for {state.waiting[entry]}")
        decided_start(state, name, step, entry, rule)
        return
    if isinstance(step, TaskStep):
        run = coming_run(state, name, "open")
        run.steered = steering(case, catalog, state, name, step)  # read before it is spent
        entry = run.entry
        proposal_spent(state, name)  # a task has no approval: the proposed run has started
        state.waiting[entry] = f"{name} by {' or '.join(step.roles)}"
        state.history.append(
            f"started {entry}: waiting for {' or '.join(step.outcomes)} by "
            f"{' or '.join(step.roles)}"
        )
        decided_start(state, name, step, entry, rule)
        if step.assign is not None:
            follow_rule(case, catalog, state, run, step.assign)
        return
    given = state.given.pop(name, None)  # spent, whatever happens next
    latest = latest_run(state, name)
    if given is None and latest is not None and latest.status == "retrying":
        given = latest.approved  # a retry keeps the approval spent on its run (brief, D26)
    if given is None:
        # Read first, so a condition that can't be read stops the step; then, if it read
        # untrusted data, the approval is asked whatever it gave (brief, D11) (brief, D39).
        needed = needs_approval(state, name, step)
        anyway = asked_anyway(case, catalog, state, step)
        if needed or anyway is not None:
            ask(state, name, step, anyway)
            asked = state.approvals[name]
            keep_holder(case, catalog, state, asked)
            # A person's choice outranks the definition's default: the rule picks only when
            # nobody was kept (brief, D71).
            assert step.approval is not None  # it was just asked
            if asked.entry not in state.holders and step.approval.assign is not None:
                follow_rule(case, catalog, state, asked, step.approval.assign)
            return
    if given is not None:
        lapsed(state, name, step, given)
    schedule(case, catalog, state, name, step, given, commands)
    # The proposed run has started. Spent here, never in `schedule`: a refresh of the step for
    # another step's fact isn't the run anyone proposed, and its proposer still may not approve
    # it (brief, D25).
    proposal_spent(state, name)


def schedule(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: CallStep,
    approved: GivenApproval | None,
    commands: list[Command],
    also_steered: tuple[Steering, ...] = (),
) -> None:
    """Check the inputs against the real sources (layer 5), then schedule the activity, or start
    the workflow, with a key naming the case and the step run (brief, D17). A workflow step is
    checked exactly as an activity step is (brief, D6). `also_steered` is what else steered the
    run: for a refresh, what steered the step it fetches for (brief, D43)."""
    contract = called(catalog, step)  # fail closed: a contract the catalog lacks stops it
    # Checked again at runtime, on nothing case validation did (learning question 34).
    if contract.risk == "high" and step.approval is None:
        raise StepStopped(f"{contract.reference} is high risk, and {name} has no approval")
    latest = latest_run(state, name)
    entry = latest.entry if latest is not None and latest.status == "retrying" else None
    entry = entry or next_entry(state, name)
    key = f"{state.case}/{entry}"
    types = {name: field.declared for name, field in case.fields.items()}
    # A retry starts the same run again, with what its first start kept (brief, D26).
    kept = latest.steered if latest is not None and latest.status == "retrying" else ()
    steered = tuple(
        dict.fromkeys((*kept, *steering(case, catalog, state, name, step), *also_steered))
    )
    inputs = checked_inputs(contract, step.inputs, state.values, state.sources, key, types, steered)
    if isinstance(step, WorkflowStep):
        refuse_sensitive_inputs(contract.reference, step.inputs, state.values)
    run = coming_run(state, name, "running")
    run.approved, run.steered = approved, steered
    run.excluded = may_not_approve(state, name, run)  # read before the proposal is spent
    if isinstance(step, WorkflowStep):
        # The run's name names its child workflow on Temporal, as a plan step's does.
        state.history.append(
            f"started {entry}: workflow {contract.reference} ({origins(step.inputs, state)}), "
            f"run {key}"
        )
        decided_start(state, name, step, entry, starting_rule(state, name, step))
        commands.append(StartWorkflow(entry, contract.reference, inputs, key))
        return
    keyed = f", key {key}" if contract.idempotency_key is not None else ""
    state.history.append(
        f"scheduled {entry}: {contract.reference} ({origins(step.inputs, state)}){keyed}"
    )
    decided_start(state, name, step, entry, starting_rule(state, name, step))
    commands.append(Schedule(entry, contract.reference, inputs))


def steering(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: Step,
) -> tuple[Steering, ...]:
    """What decided that the step runs, and the untrusted values it read: its own `when`, read
    now, and the `when` of the rule that started it, as it read it then, with what steered the
    start that rule fired on (brief, D38) (brief, D39) (brief, D43)."""
    steered = [
        Steering(f"{name}'s condition reads {field}", sources)
        for field, sources in untrusted_of(read_sources(case, catalog, state, step.when)).items()
    ]
    if (asked := state.proposed_by_rules.get(name)) is not None:
        steered += [
            Steering(f"{asked.entry}'s condition, which started {name}, reads {field}", sources)
            for field, sources in asked.untrusted.items()
        ]
        steered += asked.steered
    return (*steered, *required_steering(case, state, name))


def required_steering(case: CaseDefinition, state: CaseState, name: str) -> tuple[Steering, ...]:
    """What steered the done run of each step `name` requires: a step its run lets start is
    steered by it too, unless it is a task, whose answer is a person's, who is where untrusted
    data's influence ends (brief, D43)."""
    found: list[Steering] = []
    for required in requirements(case)[name]:
        if required not in case.steps or isinstance(case.steps[required], TaskStep):
            continue  # a milestone is reached only by a trusted decision or a person
        done = latest_counted(state, required)
        if done is not None and done.status == "done":
            found += [
                Steering(f"{name} requires {required}, and {steering.said}", steering.sources)
                for steering in done.steered
            ]
    return tuple(found)


def refuse_sensitive_inputs(
    reference: str, inputs: Mapping[str, Expression], values: Mapping[str, object]
) -> None:
    """A workflow step is never given a sensitive value: its worker belongs to another team and
    doesn't hold the case's key (brief, D31)."""
    for expression in inputs.values():
        for field in reads_sensitive(expression, values):
            raise InputRefused(
                f"{reference} is a workflow step and can't be given {field}, a sensitive field: "
                "its worker doesn't hold the case's key"
            )


def start_plan(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: PlanStep,
    commands: list[Command],
    rule: str,
) -> None:
    """Start the step's plan with its fields, each with where its value came from, so the plan's
    own checks see the real sources (brief, D28). The plan checks its fields when it starts."""
    fields: dict[str, Sourced] = {}
    for field, expression in step.inputs.items():
        try:
            value = evaluate(expression, state.values)
            fields[field] = Sourced(
                kept_sensitive(expression, state.values, value),  # wrapped into the plan too
                provenance(expression, state.sources),
            )
        except (ExpressionError, NoSources) as error:
            # Fail closed: a field that can't be read gets no default; the step fails.
            raise InputRefused(f"{field} can't be evaluated: {error}") from None
    run = coming_run(state, name, "running")
    # Who may approve nothing in the plan crosses into it, or a plan step would be a way around
    # them (brief, D25). Read before the proposal is spent: the rule's record is part of it, and
    # a retry starts the same run again, with what its first start kept (brief, D26) (brief, D39).
    excluded = may_not_approve(state, name, run)
    steered = tuple(dict.fromkeys((*run.steered, *steering(case, catalog, state, name, step))))
    run.excluded, run.steered = excluded, steered
    proposal_spent(state, name)  # the proposed run has started
    plan_run = f"{state.case}/{run.entry}"
    state.history.append(
        f"started {run.entry}: plan {step.plan} ({origins(step.inputs, state)}), run {plan_run}"
    )
    decided_start(state, name, step, run.entry, rule)
    types = {field: declared.declared for field, declared in case.fields.items()}
    references = {
        field: given_as_reference(expression, types) for field, expression in step.inputs.items()
    }
    commands.append(
        StartPlan(run.entry, step.plan, fields, plan_run, excluded, references, steered)
    )


def open_child(
    state: CaseState, name: str, step: CaseStep, commands: list[Command], rule: str
) -> None:
    """Open the step's child case with its opening, each value with where it came from, so the
    child's own checks see the real sources (brief, D74). The child checks its opening when it
    opens, as any case does."""
    if step.case not in state.cases:
        # Fail closed: a child its start didn't give is never guessed at; the step fails and
        # waits for a person (brief, D17).
        raise InputRefused(
            f"{step.case} isn't a child this case holds: its start gives the children its release "
            "pins"
        )
    fields: dict[str, Sourced] = {}
    for field, expression in step.inputs.items():
        try:
            value = evaluate(expression, state.values)
            fields[field] = Sourced(
                kept_sensitive(expression, state.values, value),  # wrapped into the child too
                provenance(expression, state.sources),
            )
        except (ExpressionError, NoSources) as error:
            # Fail closed: a field that can't be read gets no default; the step fails.
            raise InputRefused(f"{field} can't be evaluated: {error}") from None
    run = coming_run(state, name, "running")
    # Who may approve nothing in the child crosses into it, as into a plan (brief, D25).
    excluded = may_not_approve(state, name, run)
    run.excluded = excluded
    proposal_spent(state, name)  # the proposed run has started
    # The child's own workflow ID, under its parent's: the first part of this case's name is its
    # workflow ID (`claim-7`), so the codec seals the child under the parent's key (brief, D75).
    child_run = f"{state.case.split('/')[0]}/{run.entry}"
    state.history.append(
        f"started {run.entry}: case {step.case} ({origins(step.inputs, state)}), run {child_run}"
    )
    decided_start(state, name, step, run.entry, rule)
    definition = state.cases[step.case]
    commands.append(OpenCase(run.entry, step.case, definition, fields, child_run, excluded))
