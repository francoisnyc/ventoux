"""Who sees what in a case file, and the view each person gets (layer 9a).

A field is seen by anyone holding a role the case names, unless its `visible_to` narrows it; a
step's outcome and outputs are seen like an ordinary field (brief, D16) (brief, D30). The view is
filtered here, where the case runs, before anything is sent: a hidden field is absent from it.
See docs/layers/09-case-data.md and docs/guides/case-data.md.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ventoux.case.definition import CallStep, CaseDefinition, TaskStep, read_by
from ventoux.case.freshness import ago, refuse_unless_whole
from ventoux.case.state import CaseState
from ventoux.core.expressions import ReferenceType
from ventoux.core.provenance import fields_read
from ventoux.core.sensitive import Sensitive


class SheetRefused(Exception):
    """An approval sheet that can't be read: why."""


def roles_named(case: CaseDefinition) -> tuple[str, ...]:
    """Every role the case names, in order: who answers, approves, proposes, closes, sends an
    event (brief, D41) or sees."""
    named: set[str] = set()
    for step in case.steps.values():
        named.update(step.proposed_by)
        if isinstance(step, TaskStep):
            named.update(step.roles)
        elif isinstance(step, CallStep) and step.approval is not None:
            named.update(step.approval.roles)
    for reason in case.close_reasons.values():
        named.update(reason.roles)
    for event in case.events.values():
        named.update(event.sent_by.roles or ())
    for field in case.fields.values():
        named.update(field.visible_to or ())
    return tuple(sorted(named))


def seen_by(case: CaseDefinition, name: str) -> tuple[str, ...]:
    """The roles that see `name`: a declared field's `visible_to`, if it narrows; otherwise, as
    for an outcome or an output, every role the case names."""
    declared = case.fields.get(name)
    if declared is not None and declared.visible_to is not None:
        return tuple(sorted(declared.visible_to))
    return roles_named(case)


def may_see(
    case: CaseDefinition, name: str, roles: Iterable[str], registered: Collection[str]
) -> bool:
    """Whether a person holding `roles` sees the field, outcome or output `name`. Only a role in
    `registered`, the catalog's, counts: one the engine doesn't know gives sight of nothing, as it
    answers nothing (brief, D22) (brief, D35)."""
    counting = {role for role in roles if role in registered}
    return not set(seen_by(case, name)).isdisjoint(counting)


@dataclass(frozen=True)
class CaseView:
    """The case file as one person sees it: only what their roles may see, and what is hidden."""

    # Each value they may see, by name: fields, outcomes, outputs. `Any`, not `object`: Temporal
    # reads a query's result back to its type hints, and leaves `Any` as the JSON gave it.
    values: dict[str, Any]
    # Where each of those values came from, in order: a tuple, not a set, so it crosses Temporal
    # as JSON (a set has no JSON form).
    sources: dict[str, tuple[str, ...]]
    hidden: dict[str, tuple[str, ...]]  # each field hidden from them, and the roles that see it
    lines: list[str]  # one per declared field, in the definition's order, as people read it
    systems: dict[str, str]  # each reference field they may see, and the system it names
    # When each of those values was obtained, in seconds since the epoch (brief, D18). A hidden
    # field's time is hidden with it; a sensitive one's isn't sensitive.
    obtained: dict[str, int]


def case_view(
    case: CaseDefinition, state: CaseState, roles: Iterable[str], registered: Collection[str]
) -> CaseView:
    """The case file of `state` as a person holding `roles` sees it; only the `registered` roles
    count."""
    held = frozenset(roles)
    names = [*case.fields, *(name for name in state.values if name not in case.fields)]
    visible = [name for name in names if may_see(case, name, held, registered)]
    hidden = {name: seen_by(case, name) for name in names if name not in visible}
    values = {name: state.values[name] for name in visible if name in state.values}
    sources = {name: tuple(sorted(state.sources[name])) for name in values}
    lines = []
    for name, declared in case.fields.items():
        title = declared.display.title
        if name in hidden:
            lines.append(f"{title}: hidden (needs {' or '.join(hidden[name])})")
        elif name in values:
            lines.append(
                f"{title}: {as_read(values[name])}, from {', '.join(sorted(sources[name]))}"
            )
        else:
            lines.append(f"{title}: not set")
    systems = {
        name: declared.declared.system
        for name, declared in case.fields.items()
        if name in visible and isinstance(declared.declared, ReferenceType)
    }
    obtained = {name: state.obtained[name].at for name in values if name in state.obtained}
    return CaseView(values, sources, hidden, lines, systems, obtained)


@dataclass(frozen=True)
class ApprovalSheet:
    """What an approver reads: each fact the approval depends on, with its age (brief, D18)."""

    entry: str  # the open approval, such as `pay.approval#1`
    lines: list[str]  # one per field its step reads, by name: `Order: ord-1, obtained 3 days ago`
    # Who has approved it so far, in order, and how many more people it needs (brief, D47).
    approved_by: tuple[str, ...] = ()
    needed: int = 1


def sheet_of(
    case: CaseDefinition,
    state: CaseState,
    entry: str,
    roles: Iterable[str],
    at: int,
    registered: Collection[str],
) -> ApprovalSheet:
    """The sheet of the open approval `entry` as a person holding `roles` reads it at `at`, the
    reader's own time: a sheet is read, never decided on, so the case's history is untouched.
    Only the `registered` roles count. Or `SheetRefused` if no such approval is open."""
    refuse_unless_whole(at)  # fail closed: an age is never told from a time that isn't one
    approval = next((a for a in state.approvals.values() if a.entry == entry), None)
    if approval is None:
        raise SheetRefused(f"{entry} is not open: there is no sheet to read")
    step = case.steps[approval.step]
    assert isinstance(step, CallStep)  # only an activity or a workflow is asked for one
    held = frozenset(roles)
    reads = sorted({field for expression in read_by(step) for field in fields_read(expression)})
    lines = [fact_line(case, state, name, held, at, registered) for name in reads]
    needed = approval.count - len(approval.approved)
    return ApprovalSheet(entry, lines, tuple(approval.approved), needed)


def fact_line(
    case: CaseDefinition,
    state: CaseState,
    name: str,
    roles: frozenset[str],
    at: int,
    registered: Collection[str],
) -> str:
    """One fact as the sheet says it: its value as read and its age, or that it is hidden. A
    sensitive value reads `‹sensitive›`, as everywhere a value is written (brief, D31)."""
    declared = case.fields.get(name)
    title = declared.display.title if declared is not None else name
    if not may_see(case, name, roles, registered):
        return f"{title}: hidden (needs {' or '.join(seen_by(case, name))})"
    if name not in state.values:
        return f"{title}: not set"
    obtained = state.obtained.get(name)
    age = "at an unknown time" if obtained is None else f"{ago(at - obtained.at)} ago"
    return f"{title}: {as_read(state.values[name])}, obtained {age}"


def as_read(value: object) -> str:
    """A value as people read it: `1200`, `cus-7`, `true`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value) if isinstance(value, Decimal | str | Sensitive) else repr(value)
