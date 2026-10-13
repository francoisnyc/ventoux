"""Who sees what in a case file, and the view each person gets (layer 9a).

A field is seen by anyone holding a role the case names, unless its `visible_to` narrows it; a
step's outcome and outputs are seen like an ordinary field (brief, D16) (brief, D30). The view is
filtered here, where the case runs, before anything is sent: a hidden field is absent from it.
See docs/layers/09-case-data.md and docs/guides/case-data.md.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ventoux.case.definition import CallStep, CaseDefinition, TaskStep
from ventoux.case.state import CaseState
from ventoux.core.expressions import ReferenceType


def roles_named(case: CaseDefinition) -> tuple[str, ...]:
    """Every role the case names, in order: who answers, approves, proposes, closes or sees."""
    named: set[str] = set()
    for step in case.steps.values():
        named.update(step.proposed_by)
        if isinstance(step, TaskStep):
            named.update(step.roles)
        elif isinstance(step, CallStep) and step.approval is not None:
            named.update(step.approval.roles)
    for reason in case.close_reasons.values():
        named.update(reason.roles)
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


def may_see(case: CaseDefinition, name: str, roles: Iterable[str]) -> bool:
    """Whether a person holding `roles` sees the field, outcome or output `name`."""
    return not set(seen_by(case, name)).isdisjoint(roles)


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


def case_view(case: CaseDefinition, state: CaseState, roles: Iterable[str]) -> CaseView:
    """The case file of `state` as a person holding `roles` sees it."""
    held = frozenset(roles)
    names = [*case.fields, *(name for name in state.values if name not in case.fields)]
    visible = [name for name in names if may_see(case, name, held)]
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
    return CaseView(values, sources, hidden, lines, systems)


def as_read(value: object) -> str:
    """A value as people read it: `1200`, `cus-7`, `true`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value) if isinstance(value, Decimal | str) else repr(value)
