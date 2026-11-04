"""Following a definition's assignment rule when an entry opens (layer 17c).

A rule names someone the case already knows: the opener, or whoever gave a task's latest answer.
They are judged as their claim would be, with the roles they stated when they acted, and become
the holder; a rule never stops a case, so one that finds nobody, or someone who couldn't answer,
leaves the entry in its queue, saying why (brief, D71). See docs/layers/17-assignment.md (17c).
"""

from ventoux.case.answers import AnswerRefused
from ventoux.case.claims import ClaimRefused, role_to_hold
from ventoux.case.definition import Assign, CaseDefinition
from ventoux.case.state import CaseState, Holder, OpenApproval, StepRun
from ventoux.core.catalog import Catalog


def follow_rule(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    found: StepRun | OpenApproval,
    rule: Assign,
) -> None:
    """Make whom `rule` picks the holder of `found`, just opened; or say why it is in its queue."""
    picked = picked_by(state, rule)
    if isinstance(picked, str):
        state.history.append(f"{found.entry} in its queue: its rule found nobody: {picked}")
        return
    # Being asked grants nothing: the pick is judged as their claim would be (brief, D69).
    try:
        role_to_hold(case, catalog, state, found, picked)
    except (AnswerRefused, ClaimRefused) as refused:
        state.history.append(f"{found.entry} in its queue: {refused}")
        return
    state.holders[found.entry] = picked
    state.history.append(f"{found.entry} assigned to {picked.by} by its rule")


def picked_by(state: CaseState, rule: Assign) -> Holder | str:
    """The person `rule` asks, with the roles they stated when they acted; or why it finds none."""
    if rule.to == "opener":
        if state.opened_by is None:
            return "a system opened the case"
        if state.opener is None:
            return "the case opened before its opener's roles were kept"  # fail closed
        return state.opener
    assert rule.step is not None  # `answered` names its task, checked when the definition is read
    answered = state.answerers.get(rule.step)
    if answered is None:
        return f"{rule.step} hasn't been answered"
    return answered
