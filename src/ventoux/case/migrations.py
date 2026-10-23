"""Migrations: an open case moves to another release, as a change request (brief, D53). Layer 12d.

Names map by name, never by position: a name the mapping doesn't rename keeps its name. What the
case holds under a name the target lacks refuses the migration, never ends it: a run, a milestone,
a value, a failed rule. Running work finishes under what it started with. The same pure check is
the preview and the apply, so the approver reads what will happen, and the apply checks it again
on the case as it is then (brief, D34). See docs/layers/12-releases.md (12d).
"""

import json
from dataclasses import dataclass
from decimal import Decimal

from ventoux.case.approvals import withdraw
from ventoux.case.definition import CallStep, CaseDefinition, CaseInvalid, parse_case
from ventoux.case.engine import KNOWN
from ventoux.case.releases import Hash, Record, canonical, is_release
from ventoux.case.sequence import requirements
from ventoux.case.state import CaseState, Migration
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.plan import ActivityState, PlanInvalid, parse_plan


@dataclass(frozen=True)
class Moved:
    """A migration applied: the definition the case now decides with, and what moved it."""

    case: CaseDefinition
    migration: Migration


def migration_of(record: Record, mapping: dict[str, dict[str, str]], engine: int) -> Migration:
    """A migration to the release `record` keeps, with `mapping`, moving the case to `engine`:
    the package as written, read as the engine reads a definition, numbers as exact decimals
    (brief, D20)."""
    return Migration(
        record.name,
        record.release,
        record.digest.method,
        record.digest.sha256,
        json.loads(record.written.case, parse_float=Decimal),
        {ref: json.loads(text, parse_float=Decimal) for ref, text in record.written.plans.items()},
        mapping,
        engine,
    )


def released(case: CaseDefinition, state: CaseState) -> str:
    """Where the case is, as a migration's lines name it: `refund 1, engine 2`, or `draft`."""
    return f"{state.release or 'draft'}, engine {state.engine}"


def target_of(case: CaseDefinition, migration: Migration) -> CaseDefinition | str:
    """The target's case definition, once its package is checked to give its digest; else why
    not. The case checks the package, depending on nothing the client did; that the digest is the
    store's release is the trusted API's to vouch for, until 12e's registry (brief, D51)
    (brief, D53)."""
    label = migration.label
    if migration.name != case.case:
        return f"{label} is a release of {migration.name}, and this case is a {case.case}"
    given = Hash(migration.method, migration.sha256)
    try:
        target = parse_case(dict(migration.case))
    except CaseInvalid:
        return f"what was given as {label} doesn't give its digest"
    if target.case != migration.name or not is_release(target, migration.plans, given):
        return f"what was given as {label} doesn't give its digest"
    return target


def target_problems(
    case: CaseDefinition, catalog: Catalog, state: CaseState, migration: Migration
) -> tuple[CaseDefinition | None, list[str]]:
    """The target, and what refuses it before any name is read: its package, the contracts it
    calls, the engine version it moves to, and whether it moves anything (brief, D53)."""
    target = target_of(case, migration)
    if isinstance(target, str):
        return None, [target]
    problems = [
        f"{migration.label} calls {reference}, which this worker's catalog doesn't have"
        for reference in called_by(target, migration)
        if not in_catalog(catalog, reference)
    ]
    # Fail closed: a version this code doesn't know is never read as one it does (brief, D51).
    if migration.engine not in KNOWN:
        versions = ", ".join(str(each) for each in KNOWN)
        problems.append(
            f"engine {migration.engine} is one this code doesn't know (it knows {versions})"
        )
    elif migration.engine < state.engine:
        problems.append(
            f"engine {migration.engine} is older than the case's engine {state.engine}: the "
            "engine never goes back"
        )
    elif migration.label == state.release and migration.engine == state.engine:
        problems.append(f"the case is already on {released(case, state)}: nothing to move")
    return target, problems


def called_by(target: CaseDefinition, migration: Migration) -> list[str]:
    """Every contract the target calls, its plans' included, in order."""
    called = {step.called for step in target.steps.values() if isinstance(step, CallStep)}
    for data in migration.plans.values():
        try:
            plan = parse_plan(data)
        except PlanInvalid:
            continue  # the digest check refused it first
        called |= {s.activity for s in plan.states.values() if isinstance(s, ActivityState)}
    return sorted(called)


def in_catalog(catalog: Catalog, reference: str) -> bool:
    try:
        catalog.lookup(reference)
    except NotInCatalog:
        return False
    return True


def problems_of(
    case: CaseDefinition, catalog: Catalog, state: CaseState, migration: Migration
) -> list[str]:
    """Everything that refuses the migration now, all at once; empty if it may apply."""
    _, problems = target_problems(case, catalog, state, migration)
    return problems


def apply(
    case: CaseDefinition, catalog: Catalog, state: CaseState, migration: Migration
) -> CaseDefinition:
    """Move the case to the target, once nothing refuses it: what it holds follows the target,
    each change said; the case then decides as the target (brief, D53)."""
    target, problems = target_problems(case, catalog, state, migration)
    assert target is not None and not problems  # checked by the caller, just before
    label = migration.label
    for name, approval in list(state.approvals.items()):
        if not same_behaviour(case, target, name):
            withdraw(state, approval, f"{label} changed {name}")
    for name, given in list(state.given.items()):
        if not same_behaviour(case, target, name):
            del state.given[name]
            state.history.append(f"lapsed {given.entry}: {label} changed {name}")
    for run in state.runs:
        if run.approved is not None and not same_behaviour(case, target, run.step):
            state.history.append(f"lapsed {run.approved.entry}: {label} changed {run.step}")
            run.approved = None
    state.release = label
    state.engine = migration.engine
    return target


def same_behaviour(case: CaseDefinition, target: CaseDefinition, name: str) -> bool:
    """Whether the step `name` is the same behaviour in the target, word for word, what it
    requires included (a `sequence` says it outside the step): what an approval of it approved
    still holds (brief, D53)."""
    if name not in target.steps:
        return False
    before = (canonical(case.steps[name]), requirements(case)[name])
    return before == (canonical(target.steps[name]), requirements(target)[name])
