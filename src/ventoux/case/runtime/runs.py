"""What the other files of the runtime share: a step's coming run and entry, failing and
flagging a run, and small wording.
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from collections.abc import Mapping
from typing import Literal

from ventoux.case.admission import (
    latest_run,
)
from ventoux.case.answers import (
    decided_by,
)
from ventoux.case.definition import (
    CaseDefinition,
)
from ventoux.case.recording import decided_failure
from ventoux.case.rules import reach, said_steered
from ventoux.case.state import (
    CLOSING,
    CaseState,
    Moment,
    StepRun,
)
from ventoux.core.expressions import (
    Expression,
)
from ventoux.core.provenance import provenance

# The outcome of an activity that did what it was asked, or of a plan that succeeded.
DONE = "done"


# The outcome of a plan step whose plan ended in a failed final state (brief, D28).
FAILED = "failed"


def marked(case: CaseDefinition, name: str, origin: str) -> frozenset[str]:
    """Where a value of the field `name` came from: `origin`, and the field's declared mark. A
    mark adds distrust, never removes it (brief, D12)."""
    declared = case.fields[name].source if name in case.fields else None
    return frozenset({origin} | ({declared} if declared else set()))


def reach_unless_steered(state: CaseState, run: StepRun, milestones: tuple[str, ...]) -> None:
    """Reach the milestones a done run reaches, unless untrusted data steered its start: then it
    reaches nothing, and says what steered it, never a value. Untrusted data informs; it never
    decides (brief, D38) (brief, D43). A task's run never comes here: its answer is a person's."""
    if not milestones:
        return
    if run.steered:
        state.history.append(
            f"{run.entry} reaches nothing: {said_steered(run.steered)}, and untrusted data "
            "can't decide"
        )
        return
    reach(state, milestones, run.entry, f"steps.{run.step}.reaches")


def flag_if_stopping(state: CaseState, run: StepRun) -> None:
    """Flag a run that completed though a close or a stop was asked: what it did stands, and a
    person decides on a reversal (brief, D10) (brief, D40)."""
    if run.held_retry:
        # The close waited for it, whether the case is closing yet or still held by another
        # failed run: flagged as that retry, never hidden (brief, D28) (brief, D34).
        flag(state, f"{run.entry} completed on {run.held_retry}")
    elif state.phase == "closing":
        flag(state, f"{run.entry} completed after the close was requested")
    elif run.stop_requested:
        flag(state, f"{run.entry} completed after its stop was requested by {run.stop_requested}")


def stopped_because(run: StepRun) -> str:
    """Why a run asked to stop ended cancelled: a rule's stop, naming its entry, or the close."""
    return f"stopped by {run.stop_requested}" if run.stop_requested else CLOSING


def flag(state: CaseState, why: str) -> None:
    """Flag the case for a person: something happened that a close didn't stop (brief, D10)."""
    state.flags.append(why)
    state.history.append(f"flagged: {why}")


def fail(state: CaseState, name: str, reason: str) -> None:
    """The step's coming run fails before it is scheduled, with the reason (brief, D17). An
    approval given for it goes with the failed run, which a retry keeps (brief, D26): left
    given, it would admit the step again in the same decision, and fail it for ever."""
    run = coming_run(state, name, "failed")
    run.reason = reason
    given = state.given.pop(name, None)
    if given is not None:
        run.approved = given
    state.history.append(f"{run.entry} failed: {reason}")
    decided_failure(state, name, run.entry, reason)


def proposal_spent(state: CaseState, name: str) -> None:
    """The proposed run started, or is over: who proposed it, a person or a rule, is forgotten."""
    state.proposers.pop(name, None)
    state.proposed_by_rules.pop(name, None)


def origins(inputs: Mapping[str, Expression], state: CaseState) -> str:
    """Where each input's value came from, as the history says it: `amount from person:ana`."""
    return "; ".join(
        f"{field} from {', '.join(sorted(provenance(expression, state.sources))) or 'the case'}"
        for field, expression in inputs.items()
    )


def may_not_approve(state: CaseState, name: str, run: StepRun) -> dict[str, str]:
    """Who may approve nothing in the step's run, and why: whoever its first start excluded, kept
    with the run for its retry (brief, D26); the person who opened the case (brief, D11); who
    proposed it (brief, D25); and whoever's answer the condition of the rule that started it read
    (brief, D11) (brief, D39)."""
    excluded = dict(run.excluded)
    if state.opened_by is not None:
        excluded[state.opened_by] = (
            f"{state.opened_by} opened the case, so cannot approve its steps"
        )
    if (proposer := state.proposers.get(name)) is not None:
        excluded.setdefault(proposer, f"{proposer} proposed {name}, so cannot approve it")
    if (asked := state.proposed_by_rules.get(name)) is not None:
        for person, field in asked.read_from.items():
            excluded.setdefault(person, decided_by(person, field, asked))
    return excluded


def coming_run(
    state: CaseState, name: str, status: Literal["open", "running", "failed"]
) -> StepRun:
    """The step's coming run, now `status`: the run an operator retried, which keeps its entry and
    so its key (brief, D26), or else a new one."""
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying":
        latest.status = status
        # The same run, so it starts nothing again (brief, D26) (brief, D38); but one that failed
        # before it started starts now, for the first time: `started` fires once (brief, D38, as
        # amended in 11b).
        if status != "failed" and not latest.started:
            latest.started = True
            state.moments.append(Moment(f"started {name}", latest.entry, latest.entry))
        return latest
    run = StepRun(next_entry(state, name), name, status, started=status != "failed")
    state.runs.append(run)
    if run.started:  # a run that fails before it starts never started
        state.moments.append(Moment(f"started {name}", run.entry, run.entry))
    return run


def coming_entry(state: CaseState, name: str) -> str:
    """The entry the step's coming run takes: the run an operator retried, or a new one."""
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying":
        return latest.entry
    return next_entry(state, name)


def next_entry(state: CaseState, name: str) -> str:
    """The step's next run: `review#1`, then `review#2`."""
    return f"{name}#{sum(1 for run in state.runs if run.step == name) + 1}"


def listed(names: list[str]) -> str:
    """`nothing`, `amount`, `amount and order_id`, `a, b and c`."""
    if len(names) <= 1:
        return names[0] if names else "nothing"
    return f"{', '.join(names[:-1])} and {names[-1]}"
