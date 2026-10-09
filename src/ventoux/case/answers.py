"""Judging a person's answer to a case: a task's, or an approval's (layer 8).

Every answer is judged the same way, in the same order, with `core`'s checks, as in a plan
(brief, D23). The runtime checks the first two: the person is written as an identifier, and the
entry is open. Then: the outcome is offered, the person has a role it names, the form fits. An
approval adds its own checks last: the role may approve the activity's risk, and the person is
someone else: not the opener, not the proposer, and not whoever's answer feeds the step
(brief, D11).
"""

from collections.abc import Mapping

from ventoux.case.definition import ActivityStep, CaseDefinition, TaskStep
from ventoux.case.state import Answered, CaseState
from ventoux.core.approval import approver_role, not_someone_else, risk_refusal
from ventoux.core.catalog import Catalog
from ventoux.core.form import form_problem
from ventoux.core.plan import APPROVE, REJECT
from ventoux.core.roles import no_role, role_that_counts


class AnswerRefused(Exception):
    """A person's answer the engine will not accept, with the reason."""


def refuse_unless(reason: str | None) -> None:
    if reason is not None:
        raise AnswerRefused(reason)


def judge_task(
    case: CaseDefinition,
    catalog: Catalog,
    entry: str,
    name: str,
    step: TaskStep,
    answer: Answered,
) -> str:
    """The role that lets `answer` answer `entry`, a run of the task `name`, or `AnswerRefused`."""
    # A task's outcomes are a closed list (brief, D9): anything else is refused, never guessed.
    if answer.outcome not in step.outcomes:
        raise AnswerRefused(offers(name, tuple(step.outcomes), answer.outcome))
    role = role_that_counts(step.roles, answer.roles, catalog.roles)
    if role is None:
        raise AnswerRefused(no_role(entry, step.roles, answer.by, answer.roles, catalog.roles))
    types = {field_name: field.declared for field_name, field in case.fields.items()}
    sets = step.outcomes[answer.outcome].sets
    refuse_unless(form_problem(answer.outcome, sets, answer.form, types))
    return role


def judge_approval(
    catalog: Catalog,
    state: CaseState,
    entry: str,
    name: str,
    step: ActivityStep,
    answer: Answered,
) -> str:
    """The role that lets `answer` answer the approval `entry` of the step `name`, or
    `AnswerRefused`."""
    assert step.approval is not None  # only a step with an approval is asked for one
    # An approval's outcomes are a closed list: a misspelling is refused, never "not approved".
    if answer.outcome not in (APPROVE, REJECT):
        raise AnswerRefused(offers(f"{name}'s approval", (APPROVE, REJECT), answer.outcome))
    roles = step.approval.roles
    role = role_that_counts(roles, answer.roles, catalog.roles)
    if role is None:
        raise AnswerRefused(no_role(entry, roles, answer.by, answer.roles, catalog.roles))
    refuse_unless(form_problem(answer.outcome, (), answer.form, {}))
    contract = catalog.get(step.activity)
    approver = approver_role(roles, answer.roles, contract, catalog)
    if approver is None:
        raise AnswerRefused(risk_refusal(role, catalog, contract))
    # The person who opened the case approves none of its steps (brief, D11).
    if answer.by == state.opened_by:
        raise AnswerRefused(f"{answer.by} opened the case, so cannot approve its steps")
    # Nor does the person who proposed this run: their proposal decides that it runs (brief, D25).
    if answer.by == state.proposers.get(name):
        raise AnswerRefused(f"{answer.by} proposed {name}, so cannot approve it")
    refuse_unless(someone_else(state.sources, answer.by, name, step))
    return approver


def someone_else(
    sources: Mapping[str, frozenset[str]], by: str, name: str, step: ActivityStep
) -> str | None:
    """Why `by` may not approve the step: their answer flows into its inputs or its `when`
    (brief, D11). None: they are someone else."""
    conditions = [step.when] if step.when is not None else []
    return not_someone_else(by, name, list(step.inputs.values()), conditions, sources)


def offers(what: str, outcomes: tuple[str, ...], outcome: str) -> str:
    """`review offers approve or reject, and the answer is 'aprove'`."""
    return f"{what} offers {' or '.join(outcomes)}, and the answer is {outcome!r}"
