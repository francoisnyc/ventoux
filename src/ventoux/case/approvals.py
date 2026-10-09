"""Approvals in a case: when one is asked, how an open one follows the case file, and the lapse
of a given one (brief, D11, layer 8).

An approval is asked when its step is about to start. While it is open, the case goes on: a review
can be sent back, a field set again. So an open approval is withdrawn as soon as its step stops
being admitted, or a value the step reads changes, and asked again with a new entry if the step
is admitted again. Nobody approves values they didn't see (brief, D25).
"""

from ventoux.case.admission import StepStopped, holds, latest_run, requirements_met
from ventoux.case.definition import ActivityStep, CaseDefinition
from ventoux.case.sequence import requirements
from ventoux.case.state import CaseState, GivenApproval, OpenApproval
from ventoux.core.approval import inputs_digest
from ventoux.core.expressions import ExpressionError
from ventoux.core.provenance import fields_read


def needs_approval(state: CaseState, name: str, step: ActivityStep) -> bool:
    """Whether the step needs an approval now: it has one, and its `when` holds (or it has none).
    Fail closed: a condition that can't be read stops the case, never reads as "not needed"."""
    if step.approval is None:
        return False
    condition = step.approval.when
    return condition is None or holds(condition, state.values, f"{name}'s approval condition")


def ask(state: CaseState, name: str, step: ActivityStep) -> None:
    """Ask for the step's approval, as its own entry (`pay.approval#1`), noting what it reads."""
    assert step.approval is not None  # only a step with an approval is asked for one
    state.asked[name] = state.asked.get(name, 0) + 1
    entry = f"{name}.approval#{state.asked[name]}"
    state.approvals[name] = OpenApproval(entry, name, what_it_reads(step, state.values))
    roles = " or ".join(step.approval.roles)
    state.waiting[entry] = f"approval of {name} by {roles}"
    state.history.append(f"asked {entry}: approval of {name} by {roles}")


def what_it_reads(step: ActivityStep, values: dict[str, object]) -> dict[str, object]:
    """The values the step reads now, by field: its inputs, its `when` and its approval's `when`.
    A field nobody has set is left out, so setting it later is a change too."""
    expressions = [*step.inputs.values()]
    if step.when is not None:
        expressions.append(step.when)
    if step.approval is not None and step.approval.when is not None:
        expressions.append(step.approval.when)
    fields = {field for expression in expressions for field in fields_read(expression)}
    return {field: values[field] for field in sorted(fields) if field in values}


def follow(case: CaseDefinition, state: CaseState) -> None:
    """Withdraw each open approval whose step is no longer admitted, or whose values changed."""
    required = requirements(case)
    for name, approval in list(state.approvals.items()):
        step = case.steps[name]
        assert isinstance(step, ActivityStep)  # only an activity is asked for an approval
        reason = not_admitted(case, required[name], state) or changed(approval, step, state)
        if reason is not None:
            withdraw(state, approval, reason)


def not_admitted(case: CaseDefinition, required: tuple[str, ...], state: CaseState) -> str | None:
    """Why a step admitted when its approval was asked no longer is: a step it requires started
    again. A milestone, once reached, stays reached."""
    for requirement in required:
        if not requirements_met((requirement,), state):
            latest = latest_run(state, requirement)
            return f"{requirement} started again" if latest else f"{requirement} is not met"
    return None


def changed(approval: OpenApproval, step: ActivityStep, state: CaseState) -> str | None:
    """Which values the step reads changed since its approval was asked, or None."""
    now = what_it_reads(step, state.values)
    fields = sorted(set(approval.seen) | set(now))
    different = [
        f for f in fields if (f in now, now.get(f)) != (f in approval.seen, approval.seen.get(f))
    ]
    return f"{', '.join(different)} changed" if different else None


def withdraw(state: CaseState, approval: OpenApproval, reason: str) -> None:
    """Close the open approval, saying why; an answer to it is refused with the reason."""
    del state.approvals[approval.step]
    del state.waiting[approval.entry]
    state.withdrawn[approval.entry] = reason
    state.history.append(f"withdrew {approval.entry}: {reason}")


def lapsed(state: CaseState, name: str, step: ActivityStep, given: GivenApproval) -> None:
    """Stop the step if its inputs changed since the approval saw them: it has lapsed
    (brief, D11), and a person decides what happens next (brief, D23). In a case the approval is
    spent in the decision that gives it, so only a change request (layer 12) could come between;
    the check depends on nothing else."""
    try:
        now = inputs_digest(step.inputs, state.values)
    except ExpressionError:
        return  # can't be read: the input check stops the step, saying why
    if now != given.digest:
        raise StepStopped(
            f"the inputs of {name} changed since {given.by} approved them: a new approval is needed"
        )
