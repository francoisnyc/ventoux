"""Change requests: a person proposes a change to an open case, someone else approves it, and the
case applies it, checked again against the case as it is then (brief, D52). Layer 12c.

One lifecycle for every kind: proposed, then approved and applied (or not applied, saying why),
rejected, or cancelled when the case closes. A kind is what it refuses when proposed, who it keeps
from approving, and what applying it does: an edit of a field's value, or a skip of a failed run.
See docs/layers/12-releases.md (12c).
"""

from ventoux.case.answers import AnswerRefused, offers
from ventoux.case.definition import CallStep, CaseDefinition
from ventoux.case.state import Answered, CaseState, ChangeProposed, ChangeRequest, Obtained
from ventoux.case.visibility import may_see, seen_by
from ventoux.core.approval import inputs_digest
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import ExpressionError, Var, a_kind
from ventoux.core.expressions.check import a_type
from ventoux.core.form import fits, form_problem
from ventoux.core.person import identifier_problem
from ventoux.core.plan import APPROVE, REJECT
from ventoux.core.roles import role_that_counts
from ventoux.core.sensitive import Sensitive, plain

EDIT = "edit"
KINDS = (EDIT,)


class ChangeRefused(Exception):
    """A proposed change the engine won't take, with the reason. Nothing is pending."""


def who_may(catalog: Catalog) -> list[str]:
    """The roles that may propose or approve an edit: the ones registered to edit (brief, D52)."""
    return catalog.editors


def kind_role(catalog: Catalog, roles: frozenset[str]) -> str | None:
    """The role among `roles` that lets a person propose or approve the change; None if none
    does. Fail closed: a role the catalog didn't register for it counts for nothing."""
    return role_that_counts(tuple(who_may(catalog)), roles, catalog.roles)


def propose_change(
    case: CaseDefinition, catalog: Catalog, state: CaseState, event: ChangeProposed
) -> None:
    """Record the proposed change as an entry waiting for someone else's approval, once it is
    checked against the case as it is now; or `ChangeRefused`, and nothing is pending."""
    # Who proposed is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise ChangeRefused(wrong)
    if state.phase != "open":
        raise ChangeRefused(f"the case is {state.phase}: nothing changes it")
    # Fail closed: a kind the engine doesn't know is refused, never read as one it does.
    if event.kind not in KINDS:
        raise ChangeRefused(f"{event.kind} is not a kind of change: a change is an edit")
    role = kind_role(catalog, event.roles)
    if role is None:
        raise ChangeRefused(no_role(catalog, event.kind, event.by, event.roles, "proposed"))
    if (hidden := unseen(case, catalog, event.target, event.by, event.roles)) is not None:
        raise ChangeRefused(hidden)
    value = kept(case, event.target, event.value)
    if (problem := edit_problem(case, state, event.target, value)) is not None:
        raise ChangeRefused(problem)
    state.requested += 1
    # A dot no name holds: a step may be named `change`, and its runs are `change#1`.
    entry = f"case.change#{state.requested}"
    against = inputs_digest({event.target: Var(var=event.target)}, state.values)
    state.changes[entry] = ChangeRequest(
        entry, "edit", event.target, event.by, role, value, against
    )
    approvers = " or ".join(who_may(catalog))
    state.waiting[entry] = f"approval of {entry} ({event.kind} {event.target}) by {approvers}"
    state.history.append(
        f"{event.by} proposed {entry}: {event.kind} {event.target}, to be approved by {approvers}"
    )


def no_role(catalog: Catalog, kind: str, by: str, roles: frozenset[str], act: str) -> str:
    """`an edit is proposed by support or support-lead, and omar has operations`."""
    allowed = " or ".join(who_may(catalog)) or "a role registered for it"
    known = ", ".join(sorted(role for role in roles if role in catalog.roles)) or "no role"
    return f"an {kind} is {act} by {allowed}, and {by} has {known}"


def unseen(
    case: CaseDefinition, catalog: Catalog, name: str, by: str, roles: frozenset[str]
) -> str | None:
    """Why `by` can't judge an edit of `name`: it is hidden from their roles. None: they see it,
    or it isn't a declared field, which the edit's own checks refuse."""
    if name in case.fields and not may_see(case, name, roles, catalog.roles):
        return f"{by} can't see {name}: it needs {' or '.join(seen_by(case, name))}"
    return None


def kept(case: CaseDefinition, name: str, value: object) -> object:
    """An edit's value as the case file would keep it: sealed for a sensitive field, plain
    otherwise. The client seals every value, since it can't tell which fields are sensitive."""
    sensitive = name in case.fields and case.fields[name].sensitive
    return value if sensitive else plain(value)


def edit_problem(case: CaseDefinition, state: CaseState, name: str, value: object) -> str | None:
    """Why `name` can't be edited to `value` now; None if it can. Asked when the edit is proposed,
    and again when it is applied (brief, D52)."""
    if name not in case.fields:
        # An outcome or an output records what happened: it is never edited.
        return f"{name} is not a field of {case.case}: only a declared field is edited"
    declared = case.fields[name]
    if name not in state.values:
        return f"{name} holds no value yet: an edit changes a value, never gives the first"
    if declared.sensitive and not isinstance(value, Sensitive):
        return (
            f"{name} is sensitive and was given in plain text: send it through "
            "ventoux.temporal.cases, which encrypts it"
        )
    # The type, never the value: a refusal reaches people who may not see it (brief, D30).
    if not fits(plain(value), declared.declared):
        return f"{name} is {a_type(declared.declared)}, and the edit gives {a_kind(plain(value))}"
    # Its only effect would be to re-stamp the value's sources: an untrusted value would read as
    # two people's. A new value is a person's decision; the same one is not (brief, D52).
    if plain(value) == plain(state.values[name]):
        return f"{name} already holds that value: an edit changes it"
    return None


def answer_change(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    request: ChangeRequest,
    event: Answered,
    worded: str,
) -> None:
    """Judge an answer to the request, then apply it if approved; or `AnswerRefused`, and the
    request waits on. `worded` is what the answer's line says of the wording its person read."""
    # A request's outcomes are a closed list: a misspelling is refused, never "not approved".
    if event.outcome not in (APPROVE, REJECT):
        raise AnswerRefused(offers(request.entry, (APPROVE, REJECT), event.outcome))
    role = kind_role(catalog, event.roles)
    if role is None:
        act = "approved" if event.outcome == APPROVE else "rejected"
        raise AnswerRefused(no_role(catalog, request.kind, event.by, event.roles, act))
    if (problem := form_problem(event.outcome, (), event.form, {})) is not None:
        raise AnswerRefused(problem)
    if event.outcome == APPROVE:
        # An approver judges what they see: never a value hidden from them (brief, D30).
        hidden = unseen(case, catalog, request.target, event.by, event.roles)
        if (why := hidden or not_someone_else(state, request, event.by)) is not None:
            raise AnswerRefused(why)
    del state.changes[request.entry]
    del state.waiting[request.entry]
    state.history.append(f"{event.by} answered {request.entry} {event.outcome} as {role}{worded}")
    if event.outcome == REJECT:
        state.history.append(f"{request.entry} not applied: {event.by} rejected it")
        return
    apply_edit(case, state, request, event.by, event.at)


def not_someone_else(state: CaseState, request: ChangeRequest, by: str) -> str | None:
    """Why `by` may not approve the request; None if they may. A change is decided by two people:
    nobody approves their own; and the person who opened the case approves no change to it, as
    none of its steps (brief, D25) (brief, D52)."""
    if by == request.by:
        return f"{by} proposed {request.entry}, so cannot approve it"
    if by == state.opened_by:
        return f"{by} opened the case, so cannot approve a change to it"
    # An edit overrules whoever gave the field its value: they don't judge it (brief, D11).
    if f"person:{by}" in state.sources.get(request.target, ()):
        return f"{by} set {request.target}, so cannot approve a change to it"
    return None


def apply_edit(
    case: CaseDefinition, state: CaseState, request: ChangeRequest, approved_by: str, at: int
) -> None:
    """The field takes its new value, from the two people who decided it, obtained now by no run;
    unless the case changed since it was proposed (brief, D52)."""
    name = request.target
    problem = edit_problem(case, state, name, request.value)
    if problem is None and inputs_digest({name: Var(var=name)}, state.values) != request.against:
        problem = f"{name} changed since it was proposed: propose it again"
    if problem is not None:
        state.history.append(f"{request.entry} not applied: {problem}")
        return
    state.values[name] = request.value
    # Both people decided it, so neither approves a step that reads it (brief, D11); a mark the
    # field declares adds distrust, never removed by an edit (brief, D12).
    deciders = {f"person:{request.by}", f"person:{approved_by}"}
    declared = case.fields[name].source
    state.sources[name] = frozenset(deciders | ({declared} if declared else set()))
    state.obtained[name] = Obtained(at, None)  # from people, not a run
    state.history.append(
        f"applied {request.entry}: {name} edited by {request.by}, approved by {approved_by}"
    )
    lapse_spent(case, state, name)


def lapse_spent(case: CaseDefinition, state: CaseState, name: str) -> None:
    """An approval spent on a run that failed, whose inputs the edit changed, lapses: its retry
    asks again, never stops on a change two people approved. An open or given approval follows
    the case file by itself (`approvals.follow`); one spent on a failed run is kept for its retry
    (brief, D26), so the edit lapses it here (brief, D25) (brief, D52)."""
    for run in state.runs:
        step = case.steps[run.step]
        if run.status != "failed" or run.approved is None or not isinstance(step, CallStep):
            continue
        try:
            changed = inputs_digest(step.inputs, state.values) != run.approved.digest
        except ExpressionError:
            continue  # can't be read: the retry's own checks stop it, saying why
        if changed:
            state.history.append(f"lapsed {run.approved.entry}: {name} changed")
            run.approved = None
