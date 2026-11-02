"""Change requests: a person proposes a change to an open case, someone else approves it, and the
case applies it, checked again against the case as it is then (brief, D52). Layer 12c.

One lifecycle for every kind: proposed, then approved and applied (or not applied, saying why),
rejected, or cancelled when the case closes. A kind is what it refuses when proposed, who it keeps
from approving, and what applying it does: an edit of a field's value, or a skip of a failed run.
See docs/layers/12-releases.md (12c).
"""

from ventoux.case.admission import latest_run
from ventoux.case.answers import AnswerRefused, offers
from ventoux.case.definition import CallStep, CaseDefinition, PlanStep, rule_fields
from ventoux.case.migrations import Moved, apply, problems_of, released
from ventoux.case.state import (
    Answered,
    CaseState,
    ChangeProposed,
    ChangeRequest,
    Migration,
    Obtained,
    StepRun,
)
from ventoux.case.visibility import may_see, seen_by
from ventoux.core.approval import inputs_digest, not_someone_else
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import ExpressionError, OptionType, Var, a_kind
from ventoux.core.expressions.check import a_type
from ventoux.core.form import fits, form_problem
from ventoux.core.person import identifier_problem
from ventoux.core.plan import APPROVE, REJECT
from ventoux.core.roles import role_that_counts
from ventoux.core.sensitive import Sensitive, plain

EDIT = "edit"  # a declared field's value
SKIP = "skip"  # a failed step run
MIGRATE = "migrate"  # the case's release (brief, D53)
KINDS = (EDIT, SKIP, MIGRATE)
# Each kind as a refusal names it: `an edit is proposed by …`.
NOUNS = {EDIT: "an edit", SKIP: "a skip", MIGRATE: "a migration"}


class ChangeRefused(Exception):
    """A proposed change the engine won't take, with the reason. Nothing is pending."""


def who_may(catalog: Catalog, kind: str) -> list[str]:
    """The roles that may propose or approve a change of `kind`: an edit, the roles registered to
    edit; a skip, the operating roles, who act on failed steps (brief, D26) (brief, D52); a
    migration, the roles registered to migrate (brief, D53)."""
    if kind == MIGRATE:
        return catalog.migrators
    return catalog.editors if kind == EDIT else catalog.operators


def described(kind: str, target: str) -> str:
    """A request as its lines name it: `edit approved_amount`, `skip pay#1`, `migrate to refund
    2`."""
    return f"migrate to {target}" if kind == MIGRATE else f"{kind} {target}"


def kind_role(catalog: Catalog, kind: str, roles: frozenset[str]) -> str | None:
    """The role among `roles` that lets a person propose or approve a change of `kind`; None if
    none does. Fail closed: a role the catalog didn't register for it counts for nothing."""
    return role_that_counts(tuple(who_may(catalog, kind)), roles, catalog.roles)


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
        raise ChangeRefused(
            f"{event.kind} is not a kind of change: a change is an edit, a skip or a migration"
        )
    role = kind_role(catalog, event.kind, event.roles)
    if role is None:
        raise ChangeRefused(no_role(catalog, event.kind, event.by, event.roles, "proposed"))
    state.requested += 1  # numbered once it is taken: a refusal below raises, changing nothing
    # A dot no name holds: a step may be named `change`, and its runs are `change#1`.
    entry = f"case.change#{state.requested}"
    if event.kind == EDIT:
        if (hidden := unseen(case, catalog, event.target, event.by, event.roles)) is not None:
            raise ChangeRefused(hidden)
        value = kept(case, event.target, event.value)
        if (problem := edit_problem(case, state, event.target, value)) is not None:
            raise ChangeRefused(problem)
        against = inputs_digest({event.target: Var(var=event.target)}, state.values)
        request = ChangeRequest(entry, "edit", event.target, event.by, role, value, against)
    elif event.kind == SKIP:
        if (problem := skip_problem(case, state, event.target)) is not None:
            raise ChangeRefused(problem)
        request = ChangeRequest(entry, "skip", event.target, event.by, role)
    else:
        migration = event.value
        # Fail closed: a migration is its release and its mapping, never anything else.
        if not isinstance(migration, Migration) or migration.label != event.target:
            raise ChangeRefused(f"a migration to {event.target} carries that release")
        if problems := problems_of(case, catalog, state, migration):
            raise ChangeRefused("\n".join(problems))
        where = released(case, state)  # applied only if the case is still there
        request = ChangeRequest(entry, "migrate", event.target, event.by, role, migration, where)
    state.changes[entry] = request
    approvers = " or ".join(who_may(catalog, event.kind))
    said = described(event.kind, event.target)
    state.waiting[entry] = f"approval of {entry} ({said}) by {approvers}"
    state.history.append(f"{event.by} proposed {entry}: {said}, to be approved by {approvers}")


def no_role(catalog: Catalog, kind: str, by: str, roles: frozenset[str], act: str) -> str:
    """`an edit is proposed by support or support-lead, and omar has operations`."""
    allowed = " or ".join(who_may(catalog, kind)) or "a role registered for it"
    known = ", ".join(sorted(role for role in roles if role in catalog.roles)) or "no role"
    return f"{NOUNS[kind]} is {act} by {allowed}, and {by} has {known}"


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
    # An edit is checked for its type, never asked of a system: so it never sets an option, which
    # only a person's answer gives, where its system vouches for it (brief, D52) (brief, D67).
    if isinstance(declared.declared, OptionType):
        system = declared.declared.system
        return (
            f"{name} is an option of {system}, given only by a person's answer, where {system} "
            "checks it: an edit is never checked, so give it in the answer to the task that sets it"
        )
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


def skip_problem(case: CaseDefinition, state: CaseState, entry: str) -> str | None:
    """Why the run `entry` can't be skipped now; None if it can: it is its step's latest run, and
    failed. Asked when the skip is proposed, and again when it is applied (brief, D52)."""
    run = next((run for run in state.runs if run.entry == entry), None)
    if run is None:
        return f"{entry} is not a run of {case.case}"
    latest = latest_run(state, run.step)
    if latest is not None and latest is not run:
        return (
            f"{entry} can't be skipped: {latest.entry} has run since, and only a step's latest "
            "run is skipped"
        )
    if run.status != "failed":
        return f"{entry} can't be skipped: it hasn't failed"
    return None


def answer_change(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    request: ChangeRequest,
    event: Answered,
    worded: str,
) -> Moved | None:
    """Judge an answer to the request, then apply it if approved; or `AnswerRefused`, and the
    request waits on. `worded` is what the answer's line says of the wording its person read. An
    applied migration gives the release the case moved to (brief, D53)."""
    # A request's outcomes are a closed list: a misspelling is refused, never "not approved".
    if event.outcome not in (APPROVE, REJECT):
        raise AnswerRefused(offers(request.entry, (APPROVE, REJECT), event.outcome))
    role = kind_role(catalog, request.kind, event.roles)
    if role is None:
        act = "approved" if event.outcome == APPROVE else "rejected"
        raise AnswerRefused(no_role(catalog, request.kind, event.by, event.roles, act))
    if (problem := form_problem(event.outcome, (), event.form, {})) is not None:
        raise AnswerRefused(problem)
    if event.outcome == APPROVE and (why := excluded(case, catalog, state, request, event)):
        raise AnswerRefused(why)
    del state.changes[request.entry]
    del state.waiting[request.entry]
    state.history.append(f"{event.by} answered {request.entry} {event.outcome} as {role}{worded}")
    if event.outcome == REJECT:
        state.history.append(f"{request.entry} not applied: {event.by} rejected it")
        return None
    if request.kind == EDIT:
        apply_edit(case, state, request, event.by, event.at)
    elif request.kind == SKIP:
        apply_skip(case, state, request, event.by)
    else:
        return apply_migration(case, catalog, state, request, event.by, event.at)
    return None


def excluded(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    request: ChangeRequest,
    event: Answered,
) -> str | None:
    """Why `event`'s person may not approve the request; None if they may. A change is decided by
    two people: nobody approves their own; and the person who opened the case approves no change
    to it, as none of its steps (brief, D25) (brief, D52)."""
    by = event.by
    if by == request.by:
        return f"{by} proposed {request.entry}, so cannot approve it"
    if by == state.opened_by:
        return f"{by} opened the case, so cannot approve a change to it"
    if request.kind == SKIP:
        run = next(run for run in state.runs if run.entry == request.target)
        return skip_excluded(case, state, run, by)
    # An approver judges what they see: never a value hidden from them (brief, D30).
    if (hidden := unseen(case, catalog, request.target, by, event.roles)) is not None:
        return hidden
    # An edit overrules whoever gave the field its value: they don't judge it (brief, D11).
    if f"person:{by}" in state.sources.get(request.target, ()):
        return f"{by} set {request.target}, so cannot approve a change to it"
    return None


def skip_excluded(case: CaseDefinition, state: CaseState, run: StepRun, by: str) -> str | None:
    """Why `by` may not approve skipping `run`: skipping decides its fate, as approving it did, so
    whoever may not approve the run may not approve its skip, nor whoever proposed or approved
    it (brief, D11) (brief, D25) (brief, D39) (brief, D52)."""
    nor = f", nor skip {run.entry}"
    if by in run.excluded:  # kept with the run when it started (brief, D26)
        return run.excluded[by] + nor
    if state.proposers.get(run.step) == by:  # a run that failed before it started
        return f"{by} proposed {run.step}, so cannot approve it{nor}"
    if run.approved is not None and by in run.approved.approvers:
        return f"{by} approved {run.approved.entry}, so cannot approve skipping {run.entry}"
    step = case.steps[run.step]
    if isinstance(step, CallStep | PlanStep):
        conditions = [step.when] if step.when is not None else []
        inputs = list(step.inputs.values())
        computed = rule_fields(case)
        why = not_someone_else(by, run.step, inputs, conditions, state.sources, computed)
        if why is not None:
            return why + nor
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


def apply_skip(
    case: CaseDefinition, state: CaseState, request: ChangeRequest, approved_by: str
) -> None:
    """The failed run ends skipped: neither done nor failed, so nothing requiring it starts, it
    reaches nothing, and a close it held completes; unless it no longer can be (brief, D52)."""
    if (problem := skip_problem(case, state, request.target)) is not None:
        state.history.append(f"{request.entry} not applied: {problem}")
        return
    run = next(run for run in state.runs if run.entry == request.target)
    run.status, run.reason = "skipped", ""
    # The run anyone proposed is over: its proposer, a person or a rule, is forgotten.
    state.proposers.pop(run.step, None)
    state.proposed_by_rules.pop(run.step, None)
    state.history.append(
        f"applied {request.entry}: {run.entry} skipped by {request.by}, approved by {approved_by}"
    )


def apply_migration(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    request: ChangeRequest,
    approved_by: str,
    at: int,
) -> Moved | None:
    """Move the case to the target, at `at`, checked again against the case as it is now, depending on
    nothing the proposal's check did; unless something refuses it, every problem said at once
    (brief, D34) (brief, D53)."""
    migration = request.value
    assert isinstance(migration, Migration)  # a migration's request carries its migration
    if released(case, state) != request.against:
        moved = f"the case moved to {released(case, state)} since it was proposed"
        state.history.append(f"{request.entry} not applied: {moved}: propose it again")
        return None
    if problems := problems_of(case, catalog, state, migration):
        state.history.append(f"{request.entry} not applied: {'; '.join(problems)}")
        return None
    state.history.append(
        f"applied {request.entry}: migrated from {request.against} to {migration.label}, engine "
        f"{migration.engine}, proposed by {request.by}, approved by {approved_by}"
    )
    return Moved(apply(case, catalog, state, migration, at), migration)


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
