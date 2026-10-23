"""Migrations: an open case moves to another release, as a change request (brief, D53). Layer 12d.

Names map by name, never by position: a name the mapping doesn't rename keeps its name. What the
case holds under a name the target lacks refuses the migration, never ends it: a run, a milestone,
a value, a failed rule. Running work finishes under what it started with. The same pure check is
the preview and the apply, so the approver reads what will happen, and the apply checks it again
on the case as it is then (brief, D34). See docs/layers/12-releases.md (12d).
"""

import dataclasses
import functools
import json
from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal

from ventoux.case.approvals import withdraw
from ventoux.case.definition import (
    ActivityStep,
    After,
    AnsweredTask,
    CallStep,
    CaseDefinition,
    CaseInvalid,
    EventArrived,
    PlanStep,
    Reached,
    Started,
    TaskStep,
    WaitStep,
    parse_case,
    sent_by,
)
from ventoux.case.engine import KNOWN
from ventoux.case.freshness import seconds_in
from ventoux.case.releases import Hash, Record, canonical, is_release
from ventoux.case.sequence import requirements
from ventoux.case.state import CaseState, Migration, StepRun, Timer
from ventoux.case.timers import named, utc
from ventoux.case.visibility import seen_by
from ventoux.core.approval import inputs_digest
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import ActivityContract
from ventoux.core.expressions import Var
from ventoux.core.expressions.check import a_type
from ventoux.core.plan import ActivityState, PlanInvalid, parse_plan
from ventoux.core.sensitive import Sensitive


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


# The kinds of name a mapping renames, each its section, and how a line names one of it.
SECTIONS = {
    "steps": "step",
    "milestones": "milestone",
    "fields": "field",
    "rules": "rule",
    "events": "event",
}


def declared(case: CaseDefinition, section: str) -> Collection[str]:
    """The names of one kind `case` declares: its steps, milestones, fields, rules or events."""
    names: dict[str, Collection[str]] = {
        "steps": case.steps,
        "milestones": case.milestones,
        "fields": case.fields,
        "rules": case.rules,
        "events": case.events,
    }
    return names[section]


def renamed(migration: Migration, section: str, name: str) -> str:
    """`name`, of the kind `section`, as the target names it: mapped, or its own (brief, D53)."""
    return migration.mapping.get(section, {}).get(name, name)


def mapping_problems(
    case: CaseDefinition, target: CaseDefinition, state: CaseState, migration: Migration
) -> list[str]:
    """What is wrong with the mapping: a section it doesn't know, a name either release doesn't
    declare as that kind, two names mapped to one. Data, read strictly: nothing is guessed."""
    problems: list[str] = []
    sections = ", ".join(list(SECTIONS)[:-1]) + f" and {list(SECTIONS)[-1]}"
    current = state.release or "the draft"
    for section, names in migration.mapping.items():
        if section not in SECTIONS:
            problems.append(f"the mapping has no section {section}: its sections are {sections}")
            continue
        kind = SECTIONS[section]
        mapped_to: dict[str, str] = {}
        for old, new in names.items():
            if old not in declared(case, section):
                problems.append(f"{section}.{old}: {current} has no {kind} {old}")
            if new not in declared(target, section):
                problems.append(f"{section}.{old}: {migration.label} has no {kind} {new}")
            if new in mapped_to:
                problems.append(f"{section}: {mapped_to[new]} and {old} are both mapped to {new}")
            mapped_to[new] = old
    return problems


def problems_of(
    case: CaseDefinition, catalog: Catalog, state: CaseState, migration: Migration
) -> list[str]:
    """Everything that refuses the migration now, all at once; empty if it may apply. The target
    first, then the mapping, then what the case holds: each needs the one before to be read."""
    target, problems = target_problems(case, catalog, state, migration)
    if target is None or problems:
        return problems
    if problems := mapping_problems(case, target, state, migration):
        return problems
    return depending(case, target, catalog, state, migration)


def depending(
    case: CaseDefinition,
    target: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    migration: Migration,
) -> list[str]:
    """What the case holds under a name the target lacks, or in a shape it can't hold: refused,
    never terminated, each said with what to map or wait for (brief, D53)."""
    label = migration.label
    problems: list[str] = []
    latest = {run.step: run for run in state.runs}  # each step's latest run
    for step, run in latest.items():
        if (new := renamed(migration, "steps", step)) not in target.steps:
            wait = ", or migrate after it finishes" if run.status == "running" else ""
            problems.append(
                f"{run.entry} is {run.status}, and {label} has no step {new}: map it{wait}"
            )
        elif run.status in UNTIL:
            problems += unfinished(case, target, migration, run, new)
    for milestone in state.milestones:
        if (new := renamed(migration, "milestones", milestone)) not in target.milestones:
            problems.append(
                f"{milestone} is reached, and {label} has no milestone {new}: map it, since a "
                "milestone reached is never undone"
            )
    for name in state.values:
        problems += value_problems(case, target, catalog, state, migration, name)
    for firing in state.firings:
        new = renamed(migration, "rules", firing.rule)
        if firing.status == "failed" and new not in target.rules:
            problems.append(
                f"{firing.entry} failed, and {label} has no rule {new}: map it, or retry it first"
            )
    waiting = [
        *((approval.entry, approval.step, "is open") for approval in state.approvals.values()),
        *((given.entry, step, "is given") for step, given in state.given.items()),
        *((step, step, f"waits on {who}'s proposal") for step, who in state.proposers.items()),
        *(
            (asked.step, asked.step, f"waits on {asked.entry}")
            for asked in state.proposed_by_rules.values()
        ),
    ]
    for what, step, how in waiting:
        if (new := renamed(migration, "steps", step)) not in target.steps:
            problems.append(f"{what} {how}, and {label} has no step {new}: map it")
    for asked in state.proposed_by_rules.values():
        rule = asked.entry.rpartition("#")[0]
        if (new := renamed(migration, "rules", rule)) not in target.rules:
            problems.append(
                f"{asked.step} waits on {asked.entry}, and {label} has no rule {new}: map it"
            )
    return list(dict.fromkeys(problems))  # each said once


# What a run that hasn't ended waits for, as a refusal tells when to migrate.
UNTIL = {
    "open": "it is answered",
    "running": "it finishes",
    "failed": "it is retried or skipped",
    "retrying": "it is retried or skipped",
}


def unfinished(
    case: CaseDefinition, target: CaseDefinition, migration: Migration, run: StepRun, new: str
) -> list[str]:
    """Why a run that hasn't ended can't go on under the target: its step is another kind there,
    calls another contract, runs another plan, or waits for another event. A result is checked
    against what ran it, and a retry is the same run with the same key (brief, D26) (brief, D53)."""
    before, after, label = case.steps[run.step], target.steps[new], migration.label
    when = f"migrate after {UNTIL[run.status]}"
    if type(before) is not type(after):
        return [f"{run.entry} is {run.status}, and {label}'s {new} is another kind of step: {when}"]
    if (
        isinstance(before, CallStep)
        and isinstance(after, CallStep)
        and before.called != after.called
    ):
        return [
            (
                f"{run.entry} is {run.status} on {before.called}, and {label}'s {new} calls "
                f"{after.called}: {when}"
            )
        ]
    if isinstance(before, PlanStep) and isinstance(after, PlanStep) and before.plan != after.plan:
        return [
            (
                f"{run.entry} is {run.status} on {before.plan}, and {label}'s {new} runs "
                f"{after.plan}: {when}"
            )
        ]
    if (
        isinstance(before, WaitStep)
        and isinstance(after, WaitStep)
        and renamed(migration, "events", before.event) != after.event
    ):
        return [
            (
                f"{run.entry} waits for {before.event}, and {label}'s {new} waits for "
                f"{after.event}: migrate after it arrives"
            )
        ]
    return []


def value_problems(
    case: CaseDefinition,
    target: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    migration: Migration,
    name: str,
) -> list[str]:
    """Why the target can't hold the value of `name` as it is: values are never converted, and
    nothing loosens on the way (brief, D53). Never quotes the value, save an outcome, which is a
    name the definition declares."""
    label, current = migration.label, state.release or "the draft"
    if name in case.fields:
        new = renamed(migration, "fields", name)
        if new not in target.fields:
            return [f"{name} holds a value, and {label} has no field {new}: map it"]
        before, after = case.fields[name], target.fields[new]
        if before.declared != after.declared:
            return [
                (
                    f"{name} is {a_type(before.declared)} in {current}, and {new} is "
                    f"{a_type(after.declared)} in {label}: values are never converted"
                )
            ]
        if before.sensitive and not after.sensitive:
            return [
                f"{name} is sensitive in {current}, and {new} isn't in {label}: a migration never loosens it"
            ]
        if widened(case, target, name, new):
            return [
                (
                    f"{new} is seen by more roles in {label} than {name} in {current}: a "
                    "migration never loosens it"
                )
            ]
        return []
    owner, _, part = name.partition(".")
    if owner in case.steps:
        new_step = renamed(migration, "steps", owner)
        if new_step not in target.steps:
            return []  # its run says so
        if part == "outcome":
            outcome = state.values[name]
            if outcome not in outcomes_of(target.steps[new_step], catalog):
                return [
                    (
                        f"{name} is {outcome}, which {label}'s {new_step} doesn't declare: "
                        "values are never converted"
                    )
                ]
            return []
        return output_problems(case, target, catalog, migration, owner, new_step, part)
    if owner in case.events:
        new_event = renamed(migration, "events", owner)
        if new_event not in target.events:
            return [f"{owner} has arrived, and {label} has no event {new_event}: map it"]
        before_field = case.events[owner].payload[part]
        after_field = target.events[new_event].payload.get(part)
        if after_field is None or after_field.declared != before_field.declared:
            return [
                (
                    f"{name} was carried by {owner}, and {label}'s {new_event} doesn't carry "
                    f"{part} as it was: values are never converted"
                )
            ]
        return []
    # Fail closed: a value nothing declares is never carried over unread.
    return [f"{name} is in the case file, and {label} declares nothing that holds it"]


def output_problems(
    case: CaseDefinition,
    target: CaseDefinition,
    catalog: Catalog,
    migration: Migration,
    step: str,
    new_step: str,
    part: str,
) -> list[str]:
    """Why the target can't hold the output `part` a run of `step` gave: its step in the target
    calls a contract that gives the same field, of the same type."""
    before, after = case.steps[step], target.steps[new_step]
    assert isinstance(before, CallStep)  # only an activity or a workflow gives outputs
    given = catalog.lookup(before.called).output.model_fields[part].annotation
    if isinstance(after, CallStep) and in_catalog(catalog, after.called):
        fields = catalog.lookup(after.called).output.model_fields
        if part in fields and fields[part].annotation == given:
            return []
    calls = f"calls {after.called}, " if isinstance(after, CallStep) else ""
    return [
        (
            f"{step}.{part} was given by {before.called}, and {migration.label}'s {new_step} "
            f"{calls}which doesn't give {part} as it was: values are never converted"
        )
    ]


def outcomes_of(step: object, catalog: Catalog) -> tuple[str, ...]:
    """The outcomes a step declares: a task's, `done` and its contract's for an activity, `done`
    for a workflow, `done` and `failed` for a plan (brief, D9) (brief, D28)."""
    if isinstance(step, TaskStep):
        return tuple(step.outcomes)
    if isinstance(step, ActivityStep) and in_catalog(catalog, step.called):
        contract = catalog.lookup(step.called)
        assert isinstance(contract, ActivityContract)  # an activity step calls an activity
        return ("done", *contract.outcomes)
    if isinstance(step, PlanStep):
        return ("done", "failed")
    return ("done",)


def widened(case: CaseDefinition, target: CaseDefinition, name: str, new: str) -> bool:
    """Whether the target widens the field's declared `visible_to`: drops it, or adds a role to
    it (brief, D30). A field declaring none is seen by every role its case names, and follows
    the target's: a release adding a step for a new role lets that role see it."""
    before = case.fields[name].visible_to
    if before is None:
        return False
    return not set(seen_by(target, new)) <= set(before)


def apply(
    case: CaseDefinition, catalog: Catalog, state: CaseState, migration: Migration, at: int
) -> CaseDefinition:
    """Move the case to the target at `at`, once nothing refuses it: approvals of what changed
    withdrawn, names renamed, timers kept, moved or cancelled, then the case decides as the
    target; each change said (brief, D53)."""
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
    rename(case, target, state, migration)
    follow_timers(case, target, state, migration, at)
    state.release = label
    state.engine = migration.engine
    return target


def rename(
    case: CaseDefinition, target: CaseDefinition, state: CaseState, migration: Migration
) -> None:
    """Every name the case holds, as the target names it; a run keeps its entry, so its key. A
    value keeps its sources, and takes a mark the target declares (brief, D12) (brief, D53)."""
    for section, names in migration.mapping.items():
        for old, new in names.items():
            state.history.append(f"renamed {SECTIONS[section]} {old} to {new}")

    def key(name: str) -> str:
        if name in case.fields:
            return renamed(migration, "fields", name)
        owner, dot, part = name.partition(".")
        for section in ("steps", "events"):
            if owner in declared(case, section):
                return renamed(migration, section, owner) + dot + part
        return name

    # A pending edit's digest names its field: one still on the value it was proposed against is
    # taken again under the new name; one that isn't stays apart, and isn't applied (brief, D52).
    unchanged = {
        request.entry
        for request in state.changes.values()
        if request.kind == "edit" and digest_of(request.target, state) == request.against
    }
    state.values = {key(name): value for name, value in state.values.items()}
    state.sources = {key(name): sources for name, sources in state.sources.items()}
    state.obtained = {key(name): obtained for name, obtained in state.obtained.items()}
    for name in state.sources:
        if name in target.fields and (mark := target.fields[name].source) is not None:
            state.sources[name] = state.sources[name] | {mark}  # adds distrust, never removes it
    state.milestones = [renamed(migration, "milestones", m) for m in state.milestones]
    state.refreshing = {key(name): run for name, run in state.refreshing.items()}
    for run in state.runs:
        run.step = renamed(migration, "steps", run.step)
    step = functools.partial(renamed, migration, "steps")
    state.approvals = {step(name): approval for name, approval in state.approvals.items()}
    state.given = {step(name): given for name, given in state.given.items()}
    state.asked = {step(name): count for name, count in state.asked.items()}
    state.proposers = {step(name): who for name, who in state.proposers.items()}
    state.waiting_to_start = [step(name) for name in state.waiting_to_start]
    state.proposed_by_rules = {
        step(name): dataclasses.replace(
            asked,
            step=step(asked.step),
            read_from={person: key(field) for person, field in asked.read_from.items()},
            untrusted={key(field): sources for field, sources in asked.untrusted.items()},
        )
        for name, asked in state.proposed_by_rules.items()
    }
    for firing in state.firings:
        firing.rule = renamed(migration, "rules", firing.rule)
    state.arrived = {
        renamed(migration, "events", event): count for event, count in state.arrived.items()
    }
    # A pending edit follows its field's new name, and is checked again when applied (brief, D52).
    for request in state.changes.values():
        old = request.target
        if request.kind == "edit" and (new := key(old)) != old:
            request.target = new
            if request.entry in unchanged:
                request.against = digest_of(new, state)
            line = state.waiting[request.entry]
            state.waiting[request.entry] = line.replace(f"(edit {old})", f"(edit {new})")
    # What an open run waits for, as the target says it: its roles, its event's sender
    # (brief, D24).
    for run in state.runs:
        if run.status != "open":
            continue
        waits = target.steps[run.step]
        if isinstance(waits, TaskStep):
            state.waiting[run.entry] = f"{run.step} by {' or '.join(waits.roles)}"
        elif isinstance(waits, WaitStep):
            state.waiting[run.entry] = f"{waits.event} {sent_by(target.events[waits.event])}"


def follow_timers(
    case: CaseDefinition,
    target: CaseDefinition,
    state: CaseState,
    migration: Migration,
    at: int,
) -> None:
    """Each timer set, as its rule in the target says: kept if its rule waits on the same moment
    for the same age; measured again from when it was set if the age changed, firing right after
    the migration if that has passed, never in the past; cancelled if the rule is gone or waits
    on another moment. Nothing is set for a moment that came before (brief, D44) (brief, D53)."""
    kept: list[Timer] = []
    for timer in state.timers:
        rule = renamed(migration, "rules", timer.rule)
        before = case.rules[timer.rule].on
        after = target.rules[rule].on if rule in target.rules else None
        if after is None:
            state.history.append(f"cancelled {named(timer)}: {migration.label} has no rule {rule}")
            continue
        assert isinstance(before, After)  # only a rule waiting for time sets a timer
        # The old moment, named as the target names it, against the target's own.
        if not isinstance(after, After) or moment(before.since, migration) != moment(after.since):
            state.history.append(
                f"cancelled {named(timer)}: {migration.label}'s {rule} waits on another moment"
            )
            continue
        since = timer.since
        if isinstance(before.since, Reached):  # `reached paid` names its milestone
            since = f"reached {renamed(migration, 'milestones', before.since.reached)}"
        moved = dataclasses.replace(timer, rule=rule, since=since)
        if after.after != timer.after:
            due = timer.due - seconds_in(timer.after) + seconds_in(after.after)
            if due > at:
                said = f"due {utc(due)}"
            else:
                due, said = at, "already past, so it fires now"
            state.history.append(f"moved {named(timer)}: now {after.after} after it, {said}")
            moved = dataclasses.replace(moved, after=after.after, due=due)
        kept.append(moved)
    state.timers = kept


def moment(on: object, migration: Migration | None = None) -> tuple[str, str]:
    """A rule's moment as a pair, its kind and what it names, renamed as the target names it if
    `migration` is given: so two releases' moments compare."""
    if isinstance(on, Started | AnsweredTask | Reached | EventArrived):
        kind, name = next(iter(on.model_dump().items()))
        section = {"started": "steps", "answered": "steps", "reached": "milestones"}.get(
            kind, "events"
        )
        return kind, name if migration is None else renamed(migration, section, name)
    return str(on), ""


def digest_of(field: str, state: CaseState) -> str | Sensitive:
    """The digest of `field`'s value, as an edit records what it was proposed against."""
    return inputs_digest({field: Var(var=field)}, state.values)


def same_behaviour(case: CaseDefinition, target: CaseDefinition, name: str) -> bool:
    """Whether the step `name` is the same behaviour in the target, word for word, what it
    requires included (a `sequence` says it outside the step): what an approval of it approved
    still holds (brief, D53)."""
    if name not in target.steps:
        return False
    before = (canonical(case.steps[name]), requirements(case)[name])
    return before == (canonical(target.steps[name]), requirements(target)[name])
