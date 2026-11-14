"""After every event: each step that may start now is started, until none more can, and what
is held back or left unstarted is said (brief, D34) (brief, D39).
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from ventoux.case.admission import (
    StepStopped,
    ended_requirement,
    holds,
    latest_run,
    proposal_refusal,
    requirements_met,
)
from ventoux.case.approvals import (
    follow,
)
from ventoux.case.closing import (
    close_held,
)
from ventoux.case.definition import (
    ActivityStep,
    CallStep,
    CaseDefinition,
    CaseStep,
    PlanStep,
    TaskStep,
    WaitStep,
)
from ventoux.case.owed import owed
from ventoux.case.recording import decided_failure
from ventoux.case.rules import fire_rules
from ventoux.case.runtime.items import start_items
from ventoux.case.runtime.refreshing import never_waits, refresh_stale
from ventoux.case.runtime.runs import fail, listed
from ventoux.case.runtime.starting import start
from ventoux.case.sequence import requirements
from ventoux.case.state import (
    CaseState,
    Command,
    RuleStart,
    StepRun,
)
from ventoux.case.types import expression_problem
from ventoux.core.before_activity import (
    InputRefused,
)
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.expressions import (
    render,
)


def proposed_by_a_rule(state: CaseState, asked: RuleStart) -> None:
    """The step's coming run is the rule's proposal, with what its condition read, kept with the
    run until it starts (brief, D38) (brief, D39). A person's earlier proposal, whose approval was
    withdrawn, is over."""
    state.proposed_by_rules[asked.step] = asked
    state.proposers.pop(asked.step, None)


def left_unstarted(case: CaseDefinition, state: CaseState) -> None:
    """Record each start a rule asked for that no admission took up: the case stopped deciding
    first, as when a retried rule reaches the last `closes_when` milestone. Never dropped in
    silence (brief, D39)."""
    for asked in state.rule_starts:
        if case.closes_when and all(m in state.milestones for m in case.closes_when):
            why = nothing_new(case, state)
        else:
            why = f"the case is {state.phase}, so nothing new starts"
        state.history.append(f"{asked.entry} on {asked.moment}: {asked.step} not started: {why}")
    state.rule_starts.clear()


def nothing_new(case: CaseDefinition, state: CaseState) -> str:
    """Why nothing new starts once every `closes_when` milestone is reached: the case closes,
    now or once what failed is retried (brief, D34)."""
    if holding(state):
        return held_close_refusal(case, state)
    verb = "is" if len(case.closes_when) == 1 else "are"
    return f"{listed(list(case.closes_when))} {verb} reached, so the case closes and nothing new starts"


def holding(state: CaseState) -> list[str]:
    """The failed runs and rules the close waits for, as their entries: each waits for a person
    (brief, D26) (brief, D38)."""
    runs = [run.entry for run in state.runs if run.status in ("failed", "retrying")]
    return runs + [firing.entry for firing in state.firings if firing.status == "failed"]


def held_close_refusal(case: CaseDefinition, state: CaseState) -> str:
    """Why nothing starts while the close is held: what was reached, and what the case waits for
    before it closes: a failed run retried (brief, D34), a required step done (brief, D72)."""
    reached = listed(list(case.closes_when))
    verb = "is" if len(case.closes_when) == 1 else "are"
    failed, owing = holding(state), owed(case, state)
    waits = []
    if failed:
        waits.append(f"{listed(failed)} {'is' if len(failed) == 1 else 'are'} retried")
    if owing:
        waits.append(f"{listed(owing)} {'is' if len(owing) == 1 else 'are'} done")
    but = f" but {listed(owing)}" if owing else ""
    return (
        f"{reached} {verb} reached, so the case closes once {' and '.join(waits)}, or a person "
        f"closes it: nothing new starts{but}"
    )


def admit(  # noqa: C901
    case: CaseDefinition, catalog: Catalog, state: CaseState, commands: list[Command], at: int
) -> None:
    """Start every step that may start now, until no more can: no position, only admission.
    `at` is the time of the event being decided, against which facts' ages are measured."""
    required = requirements(case)
    started = True
    while started:
        started = False
        # The moments that came, before any step is asked again.
        fire_rules(case, catalog, state, commands, at)
        # An open approval follows the case file (brief, D25), before any start is decided: a
        # start is refused only by an approval that still stands.
        follow(case, state)
        # The engine's proposals, from the rules that fired: admission decides (brief, D39).
        if start_from_rules(case, catalog, state, commands, at):
            started = True
        for name, step in case.steps.items():
            # A repeated step starts by itself, a run per item, and is never proposed (brief, D73).
            if isinstance(step, TaskStep | ActivityStep) and step.for_each is not None:
                if start_items(case, catalog, state, name, step, required[name], commands):
                    started = True
                continue
            if not free_to_start(state, name, step):
                continue
            latest = latest_run(state, name)
            retried = latest if latest is not None and latest.status == "retrying" else None
            # Once the close is only held by a failed run, nothing new starts, whatever the
            # step's requirements: only the run an operator retries (brief, D34).
            if close_held(case, state) and retried is None and name not in owed(case, state):
                let_go_while_held(case, state, name)
                continue
            if not requirements_met(required[name], state):
                # A retry or an approval given waits for it, until admission settles (below).
                drop_waiting(state, name, "its requirements are no longer met")
                continue
            try:
                # Every expression it reads is checked over the case's types first, so a misspelt
                # outcome fails the step instead of reading as false (brief, D35).
                if (problem := expression_problem(case, catalog, name, state.cases)) is not None:
                    raise StepStopped(problem)
                # Freshness first, before the condition, the approval and the start, so each
                # reads fresh facts (brief, D18) (brief, D33).
                if isinstance(step, CallStep | PlanStep):  # a task or a wait needs none fresh
                    waits = refresh_stale(case, catalog, state, name, step, at, commands)
                    if waits == "refreshing":
                        started = True  # a refresh was scheduled: admission goes round again
                    if waits != "fresh":
                        continue
                # Read only once `requires` are met: a field nobody has set fails the step.
                if step.when is not None and not holds(
                    step.when, state.values, f"{name}'s condition"
                ):
                    if retried is not None:  # nothing can let it start now
                        why = f"{render(step.when)} is false now"
                        retry_fails(state, retried, why, "retry it once it holds")
                    drop_waiting(state, name, f"{render(step.when)} is false")
                    continue
                taken_up(state, name)
                start(case, catalog, state, name, step, commands)
            except (StepStopped, InputRefused, NotInCatalog) as error:
                # Nothing is skipped automatically: the step fails, and waits for a person; the
                # other steps go on (brief, D17).
                taken_up(state, name)
                fail(state, name, str(error))
            started = True
    nothing_on_its_way(case, state, required)


def nothing_on_its_way(
    case: CaseDefinition, state: CaseState, required: dict[str, tuple[str, ...]]
) -> None:
    """Once admission has settled, what waits for a step's requirement that ended without
    completing waits for nothing: an approval given lapses, then a retried run fails again, each
    saying which. Read on the settled state, so a requirement a rule stopped and another started
    again in this decision is on its way. A requirement still on its way keeps both: the approval
    tied to the values it saw, the retry shown through it (brief, D11) (brief, D17) (brief, D26)."""
    for name in case.steps:
        ended = ended_requirement(state, required[name])
        if ended is None:
            continue
        why = f"{name} requires {ended}, which hasn't completed"
        if (given := state.given.pop(name, None)) is not None:
            state.history.append(f"lapsed {given.entry}: {why}")
        latest = latest_run(state, name)
        if latest is not None and latest.status == "retrying":
            retry_fails(state, latest, why, "retry it once it has")


def let_go_while_held(case: CaseDefinition, state: CaseState, name: str) -> None:
    """While the close is held nothing new starts, so nothing waits to: an approval given for
    the step is let go, and a person's proposal waiting for its fact is dropped, each saying
    why, never kept as pending work nobody sees (brief, D34) (brief, D39)."""
    why = nothing_new(case, state)
    if state.given.pop(name, None) is not None:
        state.history.append(f"{name} not started: {why}")
    drop_waiting(state, name, why)


def retry_fails(state: CaseState, run: StepRun, why: str, then: str) -> None:
    """A retried run that nothing can let start any more goes back to failed, saying why and
    what to do, never kept waiting for nothing: an operator retries it again, or closes the case
    (brief, D17) (brief, D26)."""
    run.status = "failed"
    run.reason = f"its retry can't start: {why}: {then}, or close the case"
    state.history.append(f"{run.entry} failed again: its retry can't start: {why}")
    decided_failure(state, run.step, run.entry, run.reason)


def free_to_start(
    state: CaseState, name: str, step: TaskStep | CallStep | PlanStep | CaseStep | WaitStep
) -> bool:
    """Whether the step may start by itself: it isn't waiting for its approval, and it starts by
    itself and hasn't started before; or its approval was just given; or a person proposed it,
    and it waited for a fact fetched again."""
    if name in state.approvals:
        return False  # waiting for its approval
    if name in state.given:
        return True  # approved, so it starts now
    if name in state.waiting_to_start:
        return True  # proposed, and waiting for a fact fetched again (brief, D39)
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying":
        return True  # an operator retried it
    # A step starts by itself at most once; again, or at all if not automatic, only if proposed.
    return step.automatic and latest_run(state, name) is None


def start_from_rules(  # noqa: C901
    case: CaseDefinition, catalog: Catalog, state: CaseState, commands: list[Command], at: int
) -> bool:
    """Take each start the rules asked for, in order: the engine proposes, and admission decides,
    as for a person's proposal (brief, D39). A start it refuses is recorded, and nothing runs; one
    that can't be made fails the step, which waits for a person. Whether any started."""
    required = requirements(case)
    started = False
    while state.rule_starts:
        asked = state.rule_starts.pop(0)
        name, said = asked.step, f"{asked.entry} on {asked.moment}"
        step = case.steps[name]
        # Read first: a rule that stopped a step could otherwise start it again, for ever, in one
        # decision (brief, D39).
        if name in state.started_by_rules:
            refusal: str | None = "a rule already started it in this decision"
        elif close_held(case, state):
            # Once every closes_when milestone is reached, nothing new starts, a rule's start
            # included, even one decided on the moment that reached the last (brief, D34).
            refusal = nothing_new(case, state)
        else:
            refusal = proposal_refusal(case, name, required[name], state)
        if refusal is None:
            try:
                if (problem := expression_problem(case, catalog, name, state.cases)) is not None:
                    raise StepStopped(problem)
                if isinstance(step, CallStep | PlanStep):
                    never_waits(case, catalog, state, name, step, at)
                if step.when is not None and not holds(
                    step.when, state.values, f"{name}'s condition"
                ):
                    refusal = f"{name} doesn't run now: {render(step.when)} is false"
            except StepStopped as error:
                state.history.append(f"{said}: starting {name}")
                state.started_by_rules.append(name)
                # Kept with the failed run: an operator's retry starts it on what the rule read,
                # which still counts for its inputs and its approvers (brief, D38) (brief, D39).
                proposed_by_a_rule(state, asked)
                fail(state, name, str(error))  # nothing is skipped: a person decides (brief, D17)
                started = True
                continue
        if refusal is not None:
            state.history.append(f"{said}: {name} not started: {refusal}")
            continue
        state.history.append(f"{said}: starting {name}")
        state.started_by_rules.append(name)
        proposed_by_a_rule(state, asked)
        try:
            start(case, catalog, state, name, step, commands)
        except (StepStopped, InputRefused, NotInCatalog) as error:
            fail(state, name, str(error))
        started = True
    return started


def taken_up(state: CaseState, name: str) -> None:
    """A proposal that waited for a fact is taken up: the step starts, or fails, now."""
    if name in state.waiting_to_start:
        state.waiting_to_start.remove(name)


def drop_waiting(state: CaseState, name: str, why: str) -> None:
    """A proposal that waited for a fact no longer holds once it has landed: dropped, saying
    why, and its proposer with it (brief, D39)."""
    if name in state.waiting_to_start:
        state.waiting_to_start.remove(name)
        proposer = state.proposers.pop(name)
        state.history.append(f"dropped {proposer}'s proposal of {name}: {why}")
