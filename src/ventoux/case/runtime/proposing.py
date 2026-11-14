"""A person proposes a step: started now, if they may and admission accepts it.
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from ventoux.case.admission import (
    ProposalRefused,
    StepStopped,
    holds,
    proposal_refusal,
)
from ventoux.case.closing import (
    close_held,
)
from ventoux.case.definition import (
    CallStep,
    CaseDefinition,
    PlanStep,
)
from ventoux.case.owed import owed
from ventoux.case.runtime.admitting import held_close_refusal
from ventoux.case.runtime.refreshing import StoppedRefresh, refresh_stale
from ventoux.case.runtime.runs import fail, listed
from ventoux.case.runtime.starting import start
from ventoux.case.sequence import requirements
from ventoux.case.state import (
    CaseState,
    Command,
    Proposed,
)
from ventoux.case.types import expression_problem
from ventoux.core.before_activity import (
    InputRefused,
)
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.expressions import (
    render,
)
from ventoux.core.person import identifier_problem
from ventoux.core.roles import role_that_counts


def propose(  # noqa: C901
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    event: Proposed,
    commands: list[Command],
) -> None:
    """Start the step a person proposes, if they may and admission accepts it; or
    `ProposalRefused`. The engine decides, a person only asks."""
    # Who proposed is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise ProposalRefused(wrong)
    # Only the step advisor suggests: anything else would be a caller's words in the history
    # (brief, D61).
    if event.suggested_by not in (None, "step-advisor"):
        raise ProposalRefused(
            "a proposal is suggested by the step advisor or by nobody; this one names something else"
        )
    if state.phase != "open":
        raise ProposalRefused(f"the case is {state.phase}: nothing starts")
    # While the close is held, only an owed step starts: it is what the close waits for
    # (brief, D72).
    if close_held(case, state) and event.step not in owed(case, state):
        raise ProposalRefused(held_close_refusal(case, state))
    if event.step not in case.steps:
        raise ProposalRefused(f"{event.step} is not a step of {case.case}")
    step = case.steps[event.step]
    if not step.proposed_by:
        # A step that doesn't start by itself and names nobody is started only by a rule: the
        # definition is refused otherwise (brief, D39).
        how = "starts by itself" if step.automatic else "is started only by a rule"
        raise ProposalRefused(f"{event.step} {how}: nobody proposes it")
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
    # Its expressions checked over the case's types before any is read (brief, D35).
    if (problem := expression_problem(case, catalog, event.step, state.cases)) is not None:
        raise ProposalRefused(problem)
    suggested = ", suggested by the step advisor" if event.suggested_by is not None else ""
    state.history.append(f"{event.by} proposed {event.step} as {role}{suggested}")
    state.proposers[event.step] = event.by  # never its approver (brief, D25)
    # Hers is the proposal now: a rule's start whose approval was withdrawn is over (brief, D39).
    state.proposed_by_rules.pop(event.step, None)
    # Freshness first, before the condition, the approval and the start, as for any start
    # (brief, D33): a stale read is fetched again and the proposal waits for it; a fact nothing
    # can fetch again refuses the proposal, saying why (brief, D39). A refusal changes nothing.
    if isinstance(step, CallStep | PlanStep):  # a task or a wait needs no fact fresh
        try:
            fresh = refresh_stale(case, catalog, state, event.step, step, event.at, commands)
        except StoppedRefresh as stopped:
            raise ProposalRefused(stopped.to_proposer(event.step)) from None
        except StepStopped as stale:
            raise ProposalRefused(str(stale)) from None
        if fresh != "fresh":
            state.waiting_to_start.append(event.step)  # admission takes it up once it lands
            return
    if step.when is not None:
        try:
            decided = holds(step.when, state.values, f"{event.step}'s condition")
        except StepStopped as unreadable:
            raise ProposalRefused(str(unreadable)) from None  # fail closed: nothing starts
        if not decided:
            raise ProposalRefused(f"{event.step} doesn't run now: {render(step.when)} is false")
    try:
        start(case, catalog, state, event.step, step, commands)
    except (StepStopped, InputRefused, NotInCatalog) as error:
        # Accepted, and it can't be made: the run fails and waits for a person, as when the step
        # starts by itself, never raised out of the decision (brief, D17) (brief, D39).
        fail(state, event.step, str(error))
