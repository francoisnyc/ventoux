"""Judging a person's answer to a case: a task's, or an approval's (layer 8).

Every answer is judged the same way, in the same order, with `core`'s checks, as in a plan
(brief, D23). The runtime checks the first two: the person is written as an identifier, and the
entry is open. Then: the outcome is offered, the person has a role it names, the form fits. An
approval adds its own checks last: the role may approve the activity's risk, the person sees every
value the step reads (brief, D30), and the person is someone else: not the opener, not the
proposer, and not whoever's answer feeds the step (brief, D11).
"""

from collections.abc import Mapping

from ventoux.case.admission import latest_run
from ventoux.case.called import called
from ventoux.case.definition import CallStep, CaseDefinition, TaskStep, rule_fields
from ventoux.case.state import Answered, CaseState, RuleStart
from ventoux.case.visibility import may_see, seen_by
from ventoux.core.approval import approver_role, not_someone_else, risk_refusal
from ventoux.core.catalog import Catalog
from ventoux.core.form import form_problem
from ventoux.core.plan import APPROVE, REJECT
from ventoux.core.provenance import fields_read
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
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    entry: str,
    name: str,
    step: CallStep,
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
    contract = called(catalog, step)
    approver = approver_role(roles, answer.roles, contract, catalog)
    if approver is None:
        raise AnswerRefused(risk_refusal(role, catalog, contract))
    # An approver judges what they see: approve or reject, never values hidden from them
    # (brief, D30).
    refuse_unless(unseen(case, catalog, answer, name, step))
    # The person who opened the case approves none of its steps (brief, D11).
    if answer.by == state.opened_by:
        raise AnswerRefused(f"{answer.by} opened the case, so cannot approve its steps")
    # Nor does the person who proposed this run: their proposal decides that it runs (brief, D25).
    if answer.by == state.proposers.get(name):
        raise AnswerRefused(f"{answer.by} proposed {name}, so cannot approve it")
    # Nor does anyone whose answer the condition of the rule that started it read: it decided
    # that the step runs (brief, D11) (brief, D39). Kept with the run, since a rule remembers
    # nothing: a value changed since still excludes them.
    asked = state.proposed_by_rules.get(name)
    if asked is not None and answer.by in asked.read_from:
        raise AnswerRefused(decided_by(answer.by, asked.read_from[answer.by], asked))
    # A retried run is the same run: whoever its first start excluded still can't approve it,
    # though the proposal behind it is spent (brief, D26).
    latest = latest_run(state, name)
    if latest is not None and latest.status == "retrying" and answer.by in latest.excluded:
        raise AnswerRefused(latest.excluded[answer.by])
    refuse_unless(someone_else(case, state.sources, answer.by, name, step))
    return approver


def someone_else(
    case: CaseDefinition, sources: Mapping[str, frozenset[str]], by: str, name: str, step: CallStep
) -> str | None:
    """Why `by` may not approve the step: their answer flows into its inputs or its `when`
    (brief, D11). None: they are someone else."""
    conditions = [step.when] if step.when is not None else []
    inputs = list(step.inputs.values())
    return not_someone_else(by, name, inputs, conditions, sources, computed=rule_fields(case))


def unseen(
    case: CaseDefinition, catalog: Catalog, answer: Answered, name: str, step: CallStep
) -> str | None:
    """Why `answer`'s person can't judge the step `name`: a value it reads (its inputs, its `when`,
    its approval's `when`) is hidden from their roles. None: they see every one."""
    read = list(step.inputs.values())
    if step.when is not None:
        read.append(step.when)
    if step.approval is not None and step.approval.when is not None:
        read.append(step.approval.when)
    fields = {field for expression in read for field in fields_read(expression)}
    for field in sorted(fields):
        if not may_see(case, field, answer.roles, catalog.roles):
            needs = " or ".join(seen_by(case, field))
            return f"{answer.by} can't see {field}, which {name} reads: it needs {needs}"
    return None


def offers(what: str, outcomes: tuple[str, ...], outcome: str) -> str:
    """`review offers approve or reject, and the answer is 'aprove'`."""
    return f"{what} offers {' or '.join(outcomes)}, and the answer is {outcome!r}"


def decided_by(person: str, field: str, asked: RuleStart) -> str:
    """Why `person` approves nothing a rule started: their answer decided that it starts."""
    return (
        f"{person} set {field}, which decided that {asked.entry} started {asked.step}, so cannot "
        "approve it"
    )
